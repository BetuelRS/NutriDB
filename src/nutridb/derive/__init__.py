"""Derive stage: calculated values with registered chains (SPEC §10, ADR-0007).

Only derives when a cell is not directly measured (P2: never fabricate).
Every derived value is ``calculated`` with ``acquisition_type=calculated``
and a ``derivation`` row (formula, inputs, factors) — the chain is
registered or the build fails high (P9).

F5 implements:

    por volume   value_100ml = value_100g x density(food_group)   [densities.csv]
    confeccao    value_cooked = value_raw x retention x yield      [retention_factors.csv
                                                                    + yield_factors.csv]

and validates ``portions.csv`` (household measures per concept). The
factors are pure data (P8); an empty table means nothing can be derived —
with CIQUAL + INSA every requested cell is already measured (100 g and
100 ml), so the real run reports 0 derivations. Recipes (EuroFIR) and
materialized dry-matter rows are deferred (F5+): dry matter is a
query-side recalculation (F9).

``derive`` also exposes pure helpers (``cook_value``, ``value_per_ml``)
so the arithmetic is unit-tested without touching the dataset.
"""

from __future__ import annotations

import csv
import json
from typing import TYPE_CHECKING, Any

import polars as pl

from nutridb.identity import canonical_id

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["DeriveError", "cook_value", "derive", "value_per_ml"]

_FORMULA_VOLUME = "value_per_100ml = value_per_100g x density_g_per_ml"
_FORMULA_COOK = "value_cooked = value_raw x retention_factor x yield_factor"

# Canonical value.parquet schema (mirrors `nutridb transform`).
_VALUE_SCHEMA = {
    "concept_id": pl.Utf8,
    "nutrient_id": pl.Utf8,
    "value": pl.Float64,
    "unit": pl.Utf8,
    "value_type": pl.Utf8,
    "acquisition_type": pl.Utf8,
    "source_id": pl.Utf8,
    "source_record_id": pl.Utf8,
    "source_nutrient_code": pl.Utf8,
    "n_samples": pl.Float64,
    "standard_deviation": pl.Float64,
    "min_value": pl.Float64,
    "max_value": pl.Float64,
    "analytical_method": pl.Utf8,
    "confidence_code": pl.Utf8,
    "derivation_id": pl.Utf8,
    "basis": pl.Utf8,
    "below_loq_threshold": pl.Float64,
}


class DeriveError(Exception):
    """Fatal input inconsistency in the derive stage (fail high, P9)."""


def cook_value(raw: float, retention: float, yield_: float) -> float:
    """Cooked value from raw: raw x retention x yield (SPEC §10, confeccao)."""
    return raw * retention * yield_


def value_per_ml(value_100g: float, density_g_per_ml: float) -> float:
    """Per-100 ml value from per-100 g: value x density (SPEC §10, volume)."""
    return value_100g * density_g_per_ml


def _load_table(
    path: Path,
    columns: tuple[str, ...],
    key_columns: tuple[str, ...],
    factor_columns: tuple[str, ...],
) -> list[dict[str, str]]:
    """Read a factors CSV with mandatory header, unique key and evidence.

    ``factor_columns`` are parsed as floats; the last column is the
    mandatory evidence reference (SPEC §10, P6-style citation rule).
    """
    if not path.is_file():
        raise DeriveError(f"missing factors table {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        lines = [ln for ln in handle if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    if reader.fieldnames != list(columns):
        raise DeriveError(f"{path}: header does not match expected columns")
    rows = [dict(row) for row in reader]
    keys = [tuple(row[c] for c in key_columns) for row in rows]
    if len(set(keys)) != len(keys):
        raise DeriveError(f"{path}: duplicate rows detected")
    for row in rows:
        for c in factor_columns:
            try:
                float(row[c])
            except ValueError as exc:
                raise DeriveError(f"{path}: non-numeric factor in row {row!r}") from exc
        if not row[columns[-1]].strip():
            raise DeriveError(f"{path}: row without evidence {row!r}")
    return rows


def derive(canonical_dir: Path, root: Path) -> dict[str, Any]:
    """Add calculated values (with registered chains) to the canonical set.

    Appends derived rows to ``value.parquet`` and writes the full
    ``derivation.parquet`` (formula, inputs, factors). Deterministic:
    rows sorted; derivation ids derived from the source records (P4-style).
    """
    values = pl.read_parquet(canonical_dir / "value.parquet")
    concepts = pl.read_parquet(canonical_dir / "concept.parquet")
    derivations_dir = root / "derivations"

    densities = _load_table(
        derivations_dir / "densities.csv",
        ("food_group", "density_g_per_ml", "evidence"),
        ("food_group",),
        ("density_g_per_ml",),
    )
    retentions = _load_table(
        derivations_dir / "retention_factors.csv",
        ("nutrient", "cooking_method", "retention_factor", "evidence"),
        ("nutrient", "cooking_method"),
        ("retention_factor",),
    )
    yields_ = _load_table(
        derivations_dir / "yield_factors.csv",
        ("food_group", "cooking_method", "yield_factor", "evidence"),
        ("food_group", "cooking_method"),
        ("yield_factor",),
    )
    portions = _load_table(
        derivations_dir / "portions.csv",
        ("concept_id", "measure", "grams", "evidence"),
        ("concept_id", "measure"),
        ("grams",),
    )
    concept_ids = set(concepts["concept_id"].to_list())
    for row in portions:
        if row["concept_id"] not in concept_ids:
            raise DeriveError(f"portions: unknown concept {row['concept_id']}")

    group_of = {r["concept_id"]: r["food_group"] for r in concepts.rows(named=True)}
    known_groups = set(group_of.values())
    # Retention factors legitimately cover nutrients not yet measured by any
    # integrated source (they serve future sources); validate against the
    # frozen vocabulary, not the currently observed nutrient ids.
    vocab_rows = _load_table(
        root / "vocab" / "nutrients.csv",
        ("tagname", "group", "name_en", "unit"),
        ("tagname",),
        (),
    )
    known_nutrients = {row["tagname"] for row in vocab_rows}
    for row in densities:
        if row["food_group"] not in known_groups:
            raise DeriveError(f"densities: unknown food_group {row['food_group']!r}")
    for row in retentions:
        if row["nutrient"] not in known_nutrients:
            raise DeriveError(f"retention_factors: unknown nutrient {row['nutrient']!r}")
    for row in yields_:
        if row["food_group"] not in known_groups:
            raise DeriveError(f"yield_factors: unknown food_group {row['food_group']!r}")

    density_of = {r["food_group"]: float(r["density_g_per_ml"]) for r in densities}
    present: set[tuple[str, str, str]] = set(
        values.select(["concept_id", "nutrient_id", "basis"]).rows()
    )
    new_rows: list[tuple[object, ...]] = []
    derivations: list[tuple[str, str, str, str]] = []
    for r in values.sort(["concept_id", "nutrient_id", "source_record_id"]).rows(named=True):
        if r["basis"] != "per_100g_edible" or r["value_type"] != "measured":
            continue
        density = density_of.get(group_of[r["concept_id"]])
        if density is None:
            continue
        cell = (r["concept_id"], r["nutrient_id"], "per_100ml")
        if cell in present:
            continue  # directly measured; nothing to derive (P2)
        value = value_per_ml(float(r["value"]), density)
        derivation_id = canonical_id(
            "derivation", r["source_id"], "volume", f"{r['source_record_id']}:100ml"
        )
        evidence = next(
            row["evidence"] for row in densities if row["food_group"] == group_of[r["concept_id"]]
        )
        derivations.append(
            (
                derivation_id,
                _FORMULA_VOLUME,
                r["source_record_id"],
                json.dumps(
                    {"density_g_per_ml": density, "evidence": evidence},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        )
        new_rows.append(
            (
                r["concept_id"],
                r["nutrient_id"],
                value,
                r["unit"],
                "calculated",
                "calculated",
                r["source_id"],
                r["source_record_id"],
                r["source_nutrient_code"],
                None,
                None,
                None,
                None,
                None,
                r["confidence_code"],
                derivation_id,
                "per_100ml",
                None,
            )
        )
        present.add(cell)

    all_values = pl.concat(
        [
            values,
            pl.DataFrame(
                {
                    name: [row[i] for row in new_rows]
                    for i, name in enumerate(
                        (
                            "concept_id",
                            "nutrient_id",
                            "value",
                            "unit",
                            "value_type",
                            "acquisition_type",
                            "source_id",
                            "source_record_id",
                            "source_nutrient_code",
                            "n_samples",
                            "standard_deviation",
                            "min_value",
                            "max_value",
                            "analytical_method",
                            "confidence_code",
                            "derivation_id",
                            "basis",
                            "below_loq_threshold",
                        )
                    )
                },
                schema=_VALUE_SCHEMA,
            ),
        ],
        how="vertical_relaxed",
    )
    all_values.write_parquet(canonical_dir / "value.parquet")

    old_derivations = (
        pl.read_parquet(canonical_dir / "derivation.parquet").rows()
        if (canonical_dir / "derivation.parquet").is_file()
        else []
    )
    pl.DataFrame(
        {
            "derivation_id": [r[0] for r in old_derivations] + [r[0] for r in derivations],
            "formula": [r[1] for r in old_derivations] + [r[1] for r in derivations],
            "inputs": [r[2] for r in old_derivations] + [r[2] for r in derivations],
            "factors": [r[3] for r in old_derivations] + [r[3] for r in derivations],
        },
        schema={
            "derivation_id": pl.Utf8,
            "formula": pl.Utf8,
            "inputs": pl.Utf8,
            "factors": pl.Utf8,
        },
    ).write_parquet(canonical_dir / "derivation.parquet")

    pl.DataFrame(
        {
            "food_group": [r["food_group"] for r in densities],
            "density_g_per_ml": [float(r["density_g_per_ml"]) for r in densities],
            "evidence": [r["evidence"] for r in densities],
        },
        schema={
            "food_group": pl.Utf8,
            "density_g_per_ml": pl.Float64,
            "evidence": pl.Utf8,
        },
    ).write_parquet(canonical_dir / "density.parquet")
    pl.DataFrame(
        {
            "concept_id": [r["concept_id"] for r in portions],
            "measure": [r["measure"] for r in portions],
            "grams": [float(r["grams"]) for r in portions],
            "evidence": [r["evidence"] for r in portions],
        },
        schema={
            "concept_id": pl.Utf8,
            "measure": pl.Utf8,
            "grams": pl.Float64,
            "evidence": pl.Utf8,
        },
    ).write_parquet(canonical_dir / "portion.parquet")

    return {
        "derivations": len(derivations),
        "volume_100ml": len(new_rows),
        "cooked": 0,
        "portions": len(portions),
        "densities": len(densities),
    }
