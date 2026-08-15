"""Canonical transform: typed intermediates -> canonical dataset (SPEC §8).

Reads the CIQUAL intermediates (F1.2), the frozen vocabulary (F1.1) and
the mapping tables (F1.3) and writes the canonical dataset as one Parquet
per §8 table under ``build/canonical/ciqual/``:

    source          one row per data source (from sources/registry.toml)
    coverage        (source, nutrient): the source measures this nutrient.
                    Absence is materialized at this level (ADR-0001 D5),
                    never as an invented per-cell cross-product.
    source_record   every raw record that backs data: CIQUAL foods
                    (kind "food") and composition cells (kind "value");
                    the raw XML row is preserved verbatim as JSON (P1).
    concept         canonical entities, one per food, eternal ULID (P4).
    concept_link    concept <-> source_record, status "automatic" (F1).
    value           typed cells: measured / trace / below_loq with the
                    threshold preserved; per-nutrient unit conversion by
                    mapping factor; energy with the registered method; full
                    provenance (source, source_record, source_nutrient_code).
    derivation      empty schema in F1: calculated values require registered
                    formulas and inputs (P2); nothing is derived yet.
    tombstone       empty schema in F1: no merges exist yet (P4).

Absence (P3, D5): the source's "-" cells are explicit "not measured"; they
are NOT materialized as rows (that would rebuild the Cartesian product the
ADR rejects) but are recoverable as coverage(nutrient) AND no ``value`` row
for (concept, nutrient).

Determinism (P5): every table is sorted by a stable key before writing, so
two runs over the same intermediates are byte-identical.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl

from nutridb.identity import canonical_id
from nutridb.mappings import (
    load_foodgroup_mapping,
    load_nutrient_mapping,
    resolve_food_group,
)
from nutridb.sources.registry import load_registry

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = ["TransformError", "transform"]

INTERMEDIATE_FILES = ("foods", "food_groups", "constituents", "sources", "values")

# Canonical tables written by this stage, in stable write order.
CANONICAL_TABLES = (
    "source",
    "coverage",
    "source_record",
    "concept",
    "concept_link",
    "value",
    "derivation",
    "tombstone",
)

_SOURCE_ID = "ciqual"


class TransformError(Exception):
    """Fatal input inconsistency in the canonical transform (fail high, P9)."""


def transform(intermediates_dir: Path, out_dir: Path, root: Path) -> dict[str, int]:
    """Build the canonical dataset from intermediates; return a count report.

    Raises ``TransformError`` (never a silent partial write) when an
    intermediate file is missing or a source code has no mapping row —
    the `_unmapped/` gate (F1.3) already guarantees 100% coverage.
    """
    missing = [
        f"{name}.parquet"
        for name in INTERMEDIATE_FILES
        if not (intermediates_dir / f"{name}.parquet").is_file()
    ]
    if missing:
        raise TransformError(f"intermediates missing {missing}; run `uv run nutridb extract` first")
    out_dir.mkdir(parents=True, exist_ok=True)

    foods = pl.read_parquet(intermediates_dir / "foods.parquet")
    constituents = pl.read_parquet(intermediates_dir / "constituents.parquet")
    values = pl.read_parquet(intermediates_dir / "values.parquet")

    nutrients = load_nutrient_mapping(root)
    food_groups = load_foodgroup_mapping(root)
    registry = load_registry(root / "sources" / "registry.toml")
    source_meta = registry.by_id(_SOURCE_ID)

    nutrient_by_code: dict[int, dict[str, str]] = {}
    for row in nutrients:
        code = _int_code(row["const_code"])
        nutrient_by_code[code] = row

    def nutrient_id(const_code: int) -> str:
        row = nutrient_by_code.get(const_code)
        if row is None:
            raise TransformError(f"unmapped source nutrient code {const_code}")
        return row["tagname"]

    def food_id_and_group(alim_code: int, alim: dict[str, Any]) -> tuple[str, str]:
        concept_id = canonical_id("concept", _SOURCE_ID, "food", str(alim_code))
        food_group = resolve_food_group(food_groups, alim)
        if food_group is None:
            raise TransformError(f"food {alim_code}: no mapped food group")
        return concept_id, food_group

    # -- source (registry is the authority; P8) --------------------------------
    _write(
        out_dir / "source.parquet",
        {
            "source_id": pl.Utf8,
            "name": pl.Utf8,
            "version": pl.Utf8,
            "license_id": pl.Utf8,
            "license_url": pl.Utf8,
            "url": pl.Utf8,
            "attribution": pl.Utf8,
        },
        [
            (
                source_meta.id,
                source_meta.name,
                source_meta.version,
                source_meta.license_id,
                source_meta.license_url,
                source_meta.url,
                source_meta.attribution,
            )
        ],
    )

    # -- coverage: (source, nutrient) absence materialization (D5) ------------
    constituents = constituents.sort("const_code")
    coverage = [(r["const_code"],) for r in constituents.rows(named=True)]
    _write(
        out_dir / "coverage.parquet",
        {"source_id": pl.Utf8, "nutrient_id": pl.Utf8},
        [(_SOURCE_ID, nutrient_id(code)) for (code,) in coverage],
    )

    # -- source_record: foods + composition cells (raw JSON kept, P1) --------
    record_rows: list[tuple[str, str, str, str, str]] = []
    food_records: dict[int, str] = {}
    for r in foods.sort("alim_code").rows(named=True):
        record_id = canonical_id("source_record", _SOURCE_ID, "food", str(r["alim_code"]))
        food_records[int(r["alim_code"])] = record_id
        raw_record = {
            k: r[k]
            for k in (
                "alim_code",
                "alim_nom_fr",
                "alim_nom_eng",
                "alim_nom_sci",
                "alim_grp_code",
                "alim_ssgrp_code",
                "alim_ssssgrp_code",
                "facteur_jones",
            )
        }
        record_rows.append(
            (
                record_id,
                _SOURCE_ID,
                "food",
                str(r["alim_code"]),
                json.dumps(_json_safe(raw_record), ensure_ascii=False, sort_keys=True),
            )
        )
    for r in values.sort(["alim_code", "const_code"]).rows(named=True):
        record_rows.append(
            (
                canonical_id(
                    "source_record",
                    _SOURCE_ID,
                    "value",
                    f"{r['alim_code']}:{r['const_code']}",
                ),
                _SOURCE_ID,
                "value",
                f"{r['alim_code']}:{r['const_code']}",
                r["source_record"],
            )
        )
    record_rows.sort(key=lambda row: row[0])
    _write(
        out_dir / "source_record.parquet",
        {
            "source_record_id": pl.Utf8,
            "source_id": pl.Utf8,
            "kind": pl.Utf8,
            "ref": pl.Utf8,
            "record": pl.Utf8,
        },
        record_rows,
    )

    # -- concept + concept_link: one canonical entity per food (P4) -----------
    concept_rows: list[tuple[str, str, str]] = []
    link_rows: list[tuple[str, str, str]] = []
    concept_by_food: dict[int, str] = {}
    for r in foods.sort("alim_code").rows(named=True):
        alim_code = int(r["alim_code"])
        concept_id, food_group = food_id_and_group(alim_code, r)
        concept_by_food[alim_code] = concept_id
        concept_rows.append((concept_id, "food", food_group))
        link_rows.append((concept_id, food_records[alim_code], "automatic"))
    _write(
        out_dir / "concept.parquet",
        {"concept_id": pl.Utf8, "kind": pl.Utf8, "food_group": pl.Utf8},
        concept_rows,
    )
    _write(
        out_dir / "concept_link.parquet",
        {
            "concept_id": pl.Utf8,
            "source_record_id": pl.Utf8,
            "status": pl.Utf8,
        },
        link_rows,
    )

    # -- value: typed cells with provenance (SPEC §8, P1/P3) ------------------
    value_rows: list[tuple[object, ...]] = []
    total_pairs = len(values)
    counts = {"measured": 0, "trace": 0, "below_loq": 0}
    conversions = 0
    for r in values.sort(["alim_code", "const_code"]).rows(named=True):
        if r["teneur_kind"] == "missing":
            continue  # "-" cells: not_measured via coverage + absence (D5)
        mapping = nutrient_by_code.get(int(r["const_code"]))
        if mapping is None:
            raise TransformError(f"unmapped source nutrient code {r['const_code']}")
        factor = float(mapping["factor"])
        if factor <= 0 or factor != factor:  # factor == factor guards NaN
            raise TransformError(f"const {r['const_code']}: invalid conversion factor {factor!r}")
        if factor != 1.0:
            conversions += 1
        value_type = {
            "number": "measured",
            "trace": "trace",
            "below_loq": "below_loq",
        }[r["teneur_kind"]]
        counts[value_type] += 1
        alim_code = int(r["alim_code"])
        concept_id = concept_by_food[alim_code]
        method = mapping["energy_method"]
        value_rows.append(
            (
                concept_id,
                mapping["tagname"],
                None if value_type == "below_loq" else _convert(r["teneur_value"], factor),
                mapping["unit"],
                value_type,
                None,  # acquisition_type: CIQUAL A-D is a confidence ranking,
                # not an acquisition type; the raw letters stay in confidence_code.
                _SOURCE_ID,
                canonical_id(
                    "source_record",
                    _SOURCE_ID,
                    "value",
                    f"{alim_code}:{r['const_code']}",
                ),
                int(r["const_code"]),
                None,  # n_samples (not in source)
                None,  # standard_deviation (not in source)
                _convert(r["min_value"], factor),
                _convert(r["max_value"], factor),
                method if method != "-" else None,
                r["code_confiance"],
                None,  # derivation_id (P2: nothing derived in F1)
                "per_100g_edible",
                _convert(r["teneur_value"], factor) if value_type == "below_loq" else None,
            )
        )
    _write(
        out_dir / "value.parquet",
        {
            "concept_id": pl.Utf8,
            "nutrient_id": pl.Utf8,
            "value": pl.Float64,
            "unit": pl.Utf8,
            "value_type": pl.Utf8,
            "acquisition_type": pl.Utf8,
            "source_id": pl.Utf8,
            "source_record_id": pl.Utf8,
            "source_nutrient_code": pl.Int64,
            "n_samples": pl.Float64,
            "standard_deviation": pl.Float64,
            "min_value": pl.Float64,
            "max_value": pl.Float64,
            "analytical_method": pl.Utf8,
            "confidence_code": pl.Utf8,
            "derivation_id": pl.Utf8,
            "basis": pl.Utf8,
            "below_loq_threshold": pl.Float64,
        },
        value_rows,
    )

    # -- derivation / tombstone: empty typed schemas (P2, P4) -----------------
    _write(
        out_dir / "derivation.parquet",
        {
            "derivation_id": pl.Utf8,
            "formula": pl.Utf8,
            "inputs": pl.Utf8,
            "factors": pl.Utf8,
        },
        [],
    )
    _write(
        out_dir / "tombstone.parquet",
        {
            "tombstone_id": pl.Utf8,
            "successor_id": pl.Utf8,
            "reason": pl.Utf8,
        },
        [],
    )

    return {
        "foods": len(foods),
        "concepts": len(concept_rows),
        "source_records": len(record_rows),
        "coverage": len(coverage),
        "values": sum(counts.values()),
        "measured": counts["measured"],
        "trace": counts["trace"],
        "below_loq": counts["below_loq"],
        "not_measured": total_pairs - sum(counts.values()),
        "conversions_x10": conversions,
    }


def _write(path: Path, schema: dict[str, Any], rows: Sequence[tuple[object, ...]]) -> None:
    data = {name: [row[i] for row in rows] for i, name in enumerate(schema)}
    pl.DataFrame(data, schema=schema).write_parquet(path)


def _convert(raw: float | None, factor: float) -> float | None:
    return None if raw is None else raw * factor


def _json_safe(record: dict[str, Any]) -> dict[str, Any]:
    """Replace non-finite floats (NaN/inf from the source) with JSON null."""
    return {
        key: None if isinstance(value, float) and not _isfinite(value) else value
        for key, value in record.items()
    }


def _isfinite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def _int_code(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise TransformError(f"non-integer source nutrient code {raw!r}") from exc
