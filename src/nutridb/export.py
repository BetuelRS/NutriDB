"""JSONL exports of canonical tables (SPEC §2 deliverable).

One JSON object per line, UTF-8, LF line endings, deterministic order
(sorted by primary key). Exports land in ``build/exports/<table>.jsonl``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["EXPORTABLE", "ExportError", "export_jsonl"]

EXPORTABLE = ("concept", "source", "coverage", "value", "tombstone")


class ExportError(Exception):
    """Unknown table or missing canonical data (fail high, P9)."""


def _json_safe(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items()}


def export_jsonl(table: str, canonical_dir: Path, out_dir: Path) -> Path:
    if table not in EXPORTABLE:
        raise ExportError(f"table '{table}' is not exportable (choose from {EXPORTABLE})")
    source = canonical_dir / f"{table}.parquet"
    if not source.is_file():
        raise ExportError(f"canonical parquet missing: {source}")
    frame = pl.read_parquet(source)
    sort_keys = [column for column in frame.columns[:1]]
    frame = frame.sort(sort_keys)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{table}.jsonl"
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for record in frame.iter_rows(named=True):
            handle.write(json.dumps(_json_safe(record), ensure_ascii=False, default=str) + "\n")
    return target


def export_all(canonical_dir: Path, out_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in EXPORTABLE:
        path = export_jsonl(table, canonical_dir, out_dir)
        counts[table] = sum(1 for _ in path.open(encoding="utf-8"))
    return counts


JSONLD_CONTEXT: dict[str, Any] = {
    "nutridb": "https://nutridb.dev/vocab#",
    "schema": "https://schema.org/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "dct": "http://purl.org/dc/terms/",
    "label": {"@id": "rdfs:label", "@language": None},
    "foodGroup": {"@id": "nutridb:foodGroup"},
    "source": {"@id": "dct:source", "@type": "@id"},
    "nutrient": {"@id": "nutridb:nutrient", "@type": "@id"},
    "value": {"@id": "schema:value"},
    "unit": {"@id": "schema:unitText"},
    "basis": {"@id": "nutridb:basis"},
    "valueType": {"@id": "nutridb:valueType"},
    "successor": {"@id": "nutridb:successor", "@type": "@id"},
}


def export_jsonld(canonical_dir: Path, out_dir: Path, include_values: bool = False) -> Path:
    """Stream a JSON-LD graph of concepts (+ optional value observations)."""
    required = ["concept", "label"]
    if include_values:
        required.append("value")
    for table in required:
        if not (canonical_dir / f"{table}.parquet").is_file():
            raise ExportError(f"canonical parquet missing: {table}")

    concepts = pl.read_parquet(canonical_dir / "concept.parquet").sort("concept_id")
    labels = pl.read_parquet(canonical_dir / "label.parquet")
    food_labels = labels.filter(pl.col("ref_kind") == "food")
    label_map: dict[str, list[dict[str, Any]]] = {}
    for row in food_labels.iter_rows(named=True):
        label_map.setdefault(str(row["ref"]), []).append(
            {"@language": row["locale"], "@value": row["text"]}
        )

    values_by_concept: dict[str, list[dict[str, Any]]] = {}
    if include_values:
        values = pl.read_parquet(canonical_dir / "value.parquet")
        for row in values.filter(pl.col("value").is_not_null()).iter_rows(named=True):
            values_by_concept.setdefault(str(row["concept_id"]), []).append(
                {
                    "nutrient": str(row["nutrient_id"]),
                    "value": row["value"],
                    "unit": row["unit"],
                    "basis": row["basis"],
                    "valueType": row["value_type"],
                    "source": f"urn:nutridb:source:{row['source_id']}",
                }
            )

    tombstones_tbl = canonical_dir / "tombstone.parquet"
    successors: dict[str, str] = {}
    if tombstones_tbl.is_file():
        for row in pl.read_parquet(tombstones_tbl).iter_rows(named=True):
            successor = row.get("successor_id") or row.get("successor")
            if successor:
                successors[str(row["tombstone_id"])] = str(successor)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "nutridb.jsonld"
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"@context": JSONLD_CONTEXT}, ensure_ascii=False) + "\n")
        for row in concepts.iter_rows(named=True):
            concept_id = str(row["concept_id"])
            node: dict[str, Any] = {
                "@id": f"urn:nutridb:concept:{concept_id}",
                "@type": "nutridb:FoodConcept",
                "foodGroup": row.get("food_group"),
            }
            if concept_id in label_map:
                node["label"] = label_map[concept_id]
            if concept_id in values_by_concept:
                node["nutridb:observation"] = values_by_concept[concept_id]
            if concept_id in successors:
                node["successor"] = f"urn:nutridb:concept:{successors[concept_id]}"
            handle.write(json.dumps(node, ensure_ascii=False) + "\n")
    return target
