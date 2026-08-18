"""Canonical transform: shared intermediates -> canonical dataset (SPEC §8).

Reads every source's shared intermediate contract (ADR-0005: `food`,
`food_group`, `constituent`, `value` under ``build/intermediates/<source>/``),
the frozen vocabulary (F1.1) and the per-source mapping tables (P8) and
writes ONE canonical dataset under ``build/canonical/``:

    source          one row per source with intermediates (registry is the
                    authority for license facts; P8)
    coverage        (source, nutrient): the source measures this nutrient.
                    Absence is materialized at this level (ADR-0001 D5),
                    never as an invented per-cell cross-product.
    source_record   every raw record that backs data: foods (kind "food",
                    record JSON = names + raw source fields, P1) and
                    composition cells (kind "value", raw cell JSON verbatim).
    concept         canonical entities, one per (source, food), eternal
                    ULID (P4). F2 loads every source's foods as distinct
                    concepts; F3 merges identity links from
                    ``mappings/links.csv`` (see ``_apply_identity_links``).
    concept_link    concept <-> source_record, status "automatic" (source
                    membership) or "automatic"/"adjudicated" (F3 cross
                    links). "review" rows wait for human adjudication.
    value           typed cells: measured / trace / below_loq with the
                    threshold preserved; per-nutrient unit conversion by
                    mapping factor; energy with the registered method;
                    full provenance (source, source_record, source_nutrient_code).
    derivation      empty schema: calculated values require registered
                    formulas and inputs (P2); nothing is derived yet.
    tombstone       merged concepts with their successor (P4): every F3
                    identity link tombstones the absorbed concept and
                    reassigns its values to the survivor.

Absence (P3, D5): the source's missing cells are explicit "not measured";
they are NOT materialized as rows (that would rebuild the Cartesian product
the ADR rejects) but are recoverable as coverage(nutrient) AND no ``value``
row for (concept, nutrient).

The transform has no per-source branches (SPEC §16 F2): per-source facts
live in the mapping CSVs and in the registry, never in code.
"""

from __future__ import annotations

import csv
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

# Shared intermediate contract (ADR-0005 §3.1), per source.
CONTRACT_FILES = ("food", "food_group", "constituent", "value")

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

_VALUE_TYPE_BY_KIND = {"number": "measured", "trace": "trace", "below_loq": "below_loq"}


class TransformError(Exception):
    """Fatal input inconsistency in the canonical transform (fail high, P9)."""


def transform(intermediates_dir: Path, out_dir: Path, root: Path) -> dict[str, int]:
    """Build the canonical dataset from the shared intermediates; counts.

    Iterates ``intermediates_dir/*/`` (sorted); every source directory must
    have a registry entry and the four contract tables. Raises
    ``TransformError`` (never a silent partial write) otherwise.
    """
    source_ids = sorted(
        (d.name for d in intermediates_dir.iterdir() if d.is_dir())
        if intermediates_dir.is_dir()
        else ()
    )
    if not source_ids:
        raise TransformError(f"no source intermediates under {intermediates_dir}")
    registry = load_registry(root / "sources" / "registry.toml")
    for source_id in source_ids:
        registry.by_id(source_id)  # raises KeyError for unknown sources
        missing = [
            f"{name}.parquet"
            for name in CONTRACT_FILES
            if not (intermediates_dir / source_id / f"{name}.parquet").is_file()
        ]
        if missing:
            raise TransformError(
                f"source {source_id}: intermediates missing {missing}; "
                f"run `uv run nutridb extract` first"
            )
    out_dir.mkdir(parents=True, exist_ok=True)

    source_rows: list[tuple[object, ...]] = []
    coverage_rows: list[tuple[str, str]] = []
    record_rows: list[tuple[str, str, str, str, str]] = []
    concept_rows: list[tuple[str, str, str]] = []
    link_rows: list[tuple[str, str, str]] = []
    value_rows: list[tuple[object, ...]] = []
    tombstone_rows: list[tuple[str, str, str]] = []
    totals: dict[str, int] = {
        "foods": 0,
        "concepts": 0,
        "source_records": 0,
        "coverage": 0,
        "values": 0,
        "measured": 0,
        "trace": 0,
        "below_loq": 0,
        "not_measured": 0,
        "conversions_x10": 0,
        "identity_links": 0,
    }

    for source_id in source_ids:
        source_dir = intermediates_dir / source_id
        _load_source(
            source_id,
            source_dir,
            root,
            registry,
            source_rows,
            coverage_rows,
            record_rows,
            concept_rows,
            link_rows,
            value_rows,
            totals,
        )

    # -- identity links: consume the P8 adjudication record (F3) --------------
    food_codes: dict[str, set[str]] = {}
    for source_id in source_ids:
        foods = pl.read_parquet(intermediates_dir / source_id / "food.parquet")
        food_codes[source_id] = set(foods["food_code"].to_list())
    links_csv = root / "mappings" / "links.csv"
    if links_csv.is_file():
        applied = _apply_identity_links(
            links_csv,
            food_codes,
            link_rows,
            tombstone_rows,
            value_rows,
        )
        totals["identity_links"] = applied

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
        sorted(source_rows, key=lambda row: str(row[0])),
    )
    _write(
        out_dir / "coverage.parquet",
        {"source_id": pl.Utf8, "nutrient_id": pl.Utf8},
        sorted(coverage_rows, key=lambda row: (row[0], row[1])),
    )
    _write(
        out_dir / "source_record.parquet",
        {
            "source_record_id": pl.Utf8,
            "source_id": pl.Utf8,
            "kind": pl.Utf8,
            "ref": pl.Utf8,
            "record": pl.Utf8,
        },
        sorted(record_rows, key=lambda row: str(row[0])),
    )
    _write(
        out_dir / "concept.parquet",
        {"concept_id": pl.Utf8, "kind": pl.Utf8, "food_group": pl.Utf8},
        sorted(concept_rows, key=lambda row: str(row[0])),
    )
    _write(
        out_dir / "concept_link.parquet",
        {"concept_id": pl.Utf8, "source_record_id": pl.Utf8, "status": pl.Utf8},
        sorted(link_rows, key=lambda row: (row[0], row[1])),
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
        },
        sorted(value_rows, key=lambda row: (str(row[0]), str(row[1]), str(row[7]))),
    )

    # -- derivation / tombstone: typed schemas (P2, P4) ----------------------
    _write(
        out_dir / "derivation.parquet",
        {"derivation_id": pl.Utf8, "formula": pl.Utf8, "inputs": pl.Utf8, "factors": pl.Utf8},
        [],
    )
    _write(
        out_dir / "tombstone.parquet",
        {"tombstone_id": pl.Utf8, "successor_id": pl.Utf8, "reason": pl.Utf8},
        sorted(tombstone_rows, key=lambda row: str(row[0])),
    )

    totals["sources"] = len(source_ids)
    return totals


def _load_source(
    source_id: str,
    source_dir: Path,
    root: Path,
    registry: Any,
    source_rows: list[tuple[object, ...]],
    coverage_rows: list[tuple[str, str]],
    record_rows: list[tuple[str, str, str, str, str]],
    concept_rows: list[tuple[str, str, str]],
    link_rows: list[tuple[str, str, str]],
    value_rows: list[tuple[object, ...]],
    totals: dict[str, int],
) -> None:
    """Load one source's intermediates into the canonical row accumulators."""
    foods = pl.read_parquet(source_dir / "food.parquet")
    constituents = pl.read_parquet(source_dir / "constituent.parquet")
    values = pl.read_parquet(source_dir / "value.parquet")

    nutrients = load_nutrient_mapping(root, source_id)
    nutrient_by_code = {row["nutrient_code"]: row for row in nutrients}
    food_groups = load_foodgroup_mapping(root, source_id)
    source_meta = registry.by_id(source_id)

    def nutrient_id(nutrient_code: str) -> str:
        row = nutrient_by_code.get(nutrient_code)
        if row is None:
            raise TransformError(f"{source_id}: unmapped source nutrient code {nutrient_code!r}")
        return row["tagname"]

    # -- source (registry is the authority; P8) --------------------------------
    source_rows.append(
        (
            source_meta.id,
            source_meta.name,
            source_meta.version,
            source_meta.license_id,
            source_meta.license_url,
            source_meta.url,
            source_meta.attribution,
        )
    )

    # -- coverage: (source, nutrient) absence materialization (D5) -------------
    codes = sorted({r["nutrient_code"] for r in constituents.rows(named=True)})
    for code in codes:
        coverage_rows.append((source_id, nutrient_id(code)))
    totals["coverage"] += len(codes)

    # -- source_record: foods + composition cells (raw JSON kept, P1) ---------
    food_records: dict[str, str] = {}
    for r in foods.sort("food_code").rows(named=True):
        record_id = canonical_id("source_record", source_id, "food", r["food_code"])
        food_records[r["food_code"]] = record_id
        record_rows.append(
            (
                record_id,
                source_id,
                "food",
                r["food_code"],
                r["record"],
            )
        )
    for r in values.sort(["food_code", "nutrient_code"]).rows(named=True):
        record_rows.append(
            (
                canonical_id(
                    "source_record",
                    source_id,
                    "value",
                    f"{r['food_code']}:{r['nutrient_code']}",
                ),
                source_id,
                "value",
                f"{r['food_code']}:{r['nutrient_code']}",
                r["record"],
            )
        )

    # -- concept + concept_link: one canonical entity per food (P4) -----------
    concept_by_food: dict[str, str] = {}
    for r in foods.sort("food_code").rows(named=True):
        concept_id = canonical_id("concept", source_id, "food", r["food_code"])
        concept_by_food[r["food_code"]] = concept_id
        group_path = json.loads(r["group_path"])
        food_group = resolve_food_group(food_groups, group_path)
        if food_group is None:
            raise TransformError(
                f"{source_id}: food {r['food_code']}: no mapped food group "
                f"(group_path={group_path!r})"
            )
        concept_rows.append((concept_id, "food", food_group))
        link_rows.append((concept_id, food_records[r["food_code"]], "automatic"))

    # -- value: typed cells with provenance (SPEC §8, P1/P3) ------------------
    total_pairs = len(values)
    conversions = 0
    for r in values.sort(["food_code", "nutrient_code"]).rows(named=True):
        if r["value_kind"] == "missing":
            continue  # not measured via coverage + absence (D5)
        mapping = nutrient_by_code.get(r["nutrient_code"])
        if mapping is None:
            raise TransformError(
                f"{source_id}: unmapped source nutrient code {r['nutrient_code']!r}"
            )
        factor = float(mapping["factor"])
        if factor <= 0 or factor != factor:  # factor == factor guards NaN
            raise TransformError(
                f"{source_id} {r['nutrient_code']}: invalid conversion factor {factor!r}"
            )
        if factor != 1.0:
            conversions += 1
        value_type = _VALUE_TYPE_BY_KIND[r["value_kind"]]
        totals[value_type] += 1
        concept_id = concept_by_food[r["food_code"]]
        method = mapping["energy_method"]
        value_rows.append(
            (
                concept_id,
                mapping["tagname"],
                None if value_type == "below_loq" else _convert(r["value"], factor),
                mapping["unit"],
                value_type,
                None,  # acquisition_type: sources do not classify acquisition
                source_id,
                canonical_id(
                    "source_record",
                    source_id,
                    "value",
                    f"{r['food_code']}:{r['nutrient_code']}",
                ),
                r["nutrient_code"],
                None,  # n_samples (not in source)
                None,  # standard_deviation (not in source)
                _convert(r["min_value"], factor),
                _convert(r["max_value"], factor),
                method if method != "-" else None,
                r["confidence_code"],
                None,  # derivation_id (P2: nothing derived yet)
                r["basis"],
                _convert(r["threshold"], factor) if value_type == "below_loq" else None,
            )
        )

    totals["foods"] += len(foods)
    totals["concepts"] += len(concept_by_food)
    totals["source_records"] += len(food_records) + total_pairs
    present = sum(1 for r in values.rows(named=True) if r["value_kind"] != "missing")
    totals["values"] += present
    totals["not_measured"] += total_pairs - present
    totals["conversions_x10"] += conversions


def _apply_identity_links(
    links_csv: Path,
    food_codes: dict[str, set[str]],
    link_rows: list[tuple[str, str, str]],
    tombstone_rows: list[tuple[str, str, str]],
    value_rows: list[tuple[object, ...]],
) -> int:
    """Apply the F3 identity links from ``mappings/links.csv`` (P8 gate).

    Columns: ``concept_id, source, source_code, status`` (the survivor
    concept per pair, ADR-0006). Rows with status ``automatic`` or
    ``adjudicated`` merge the other side's concept into the survivor:
    the absorbed concept is tombstoned (P4), its values are reassigned
    to the survivor and a cross ``concept_link`` records the merge.
    ``review`` rows are the human queue and are ignored here.
    Unknown sources, unknown codes or duplicated absorbed concepts
    fail high (P9): the adjudication record is the authority.
    """
    consumed = {"automatic", "adjudicated"}
    absorbed_to: dict[str, tuple[str, str, str, str]] = {}
    with links_csv.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["status"] is None or row["status"].lstrip().startswith("#"):
                continue  # header comments (the F1-era empty gate record)
            status = row["status"].strip()
            source = row["source"].strip()
            source_code = row["source_code"].strip()
            concept_id = row["concept_id"].strip()
            if status not in consumed | {"review"}:
                raise TransformError(
                    f"links.csv: unknown status {status!r} (expected automatic|adjudicated|review)"
                )
            if status == "review":
                continue
            if source not in food_codes:
                raise TransformError(f"links.csv: unknown source {source!r}")
            if source_code not in food_codes[source]:
                raise TransformError(
                    f"links.csv: {source} food {source_code!r} has no intermediates"
                )
            absorbed = canonical_id("concept", source, "food", source_code)
            if absorbed == concept_id:
                continue  # the survivor's own source membership row
            if absorbed in absorbed_to:
                raise TransformError(
                    f"links.csv: {source} {source_code!r} linked to more than one survivor"
                )
            absorbed_to[absorbed] = (concept_id, source, source_code, status)

    for i, value_row in enumerate(value_rows):
        candidate = value_row[0]
        if isinstance(candidate, str):
            merge = absorbed_to.get(candidate)
            if merge is None:
                continue
            value_rows[i] = (merge[0], *value_row[1:])
    for absorbed, (survivor, source, source_code, status) in absorbed_to.items():
        tombstone_rows.append((absorbed, survivor, "identity_link_f3"))
        link_rows.append(
            (
                survivor,
                canonical_id("source_record", source, "food", source_code),
                status,
            )
        )
    return len(absorbed_to)


def _write(path: Path, schema: dict[str, Any], rows: Sequence[tuple[object, ...]]) -> None:
    data = {name: [row[i] for row in rows] for i, name in enumerate(schema)}
    pl.DataFrame(data, schema=schema).write_parquet(path)


def _convert(raw: float | None, factor: float) -> float | None:
    return None if raw is None else raw * factor
