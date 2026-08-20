"""Primary-source golden set for 200 stratified CIQUAL foods (F6.5)."""

from __future__ import annotations

import csv
import json
import math
import sqlite3

import polars as pl
import pytest

from nutridb.paths import project_root

ROOT = project_root()
GOLDEN = ROOT / "tests" / "golden" / "ciqual_200.csv"
SQLITE = ROOT / "build" / "artifacts" / "nutridb-core-0.1.0.sqlite"
CANONICAL = ROOT / "build" / "canonical" / "value.parquet"

pytestmark = pytest.mark.skipif(
    not (SQLITE.is_file() or CANONICAL.is_file()),
    reason="real artefact not built; run `uv run nutridb build` first",
)

_CONST_BY_TAG = {
    "ENERC_KCAL": "328",
    "PROCNT": "25000",
    "FAT": "40000",
    "CHOAVL": "31000",
    "WATER": "400",
}


def _rows() -> list[dict[str, str]]:
    with GOLDEN.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_golden_200_shape_and_primary_evidence() -> None:
    rows = _rows()
    assert len({row["alim_code"] for row in rows}) == 200
    assert len(rows) == 943
    assert {row["tagname"] for row in rows} <= set(_CONST_BY_TAG)
    for row in rows:
        assert row["expected"]
        assert row["const_code"] == _CONST_BY_TAG[row["tagname"]]
        assert row["ref"].startswith("compo_2025_11_03.xml alim ")


def _actual_sqlite() -> dict[tuple[str, str], tuple[float, str]]:
    connection = sqlite3.connect(SQLITE)
    try:
        return {
            (row[0], row[1]): (row[2], row[3])
            for row in connection.execute(
                "SELECT m.label, m.nutrient_id, m.value, r.record "
                "FROM mv_food_value m JOIN source_record r "
                "ON r.source_record_id = m.source_record_id "
                "WHERE m.locale = 'fr' AND m.basis = 'per_100g_edible' "
                "AND m.value IS NOT NULL"
            )
        }
    finally:
        connection.close()


def _actual_canonical() -> dict[tuple[str, str], tuple[float, str]]:
    values = pl.read_parquet(CANONICAL)
    records = {
        row["source_record_id"]: row["record"]
        for row in pl.read_parquet(ROOT / "build" / "canonical" / "source_record.parquet").rows(
            named=True
        )
    }
    labels = pl.read_parquet(ROOT / "build" / "canonical" / "label.parquet")
    label_by_concept = {
        row["ref"]: row["text"]
        for row in labels.filter(
            (pl.col("ref_kind") == "food") & (pl.col("locale") == "fr")
        ).rows(named=True)
    }
    return {
        (label_by_concept[row["concept_id"]], row["nutrient_id"]): (
            row["value"],
            records[row["source_record_id"]],
        )
        for row in values.filter(
            (pl.col("value_type") == "measured")
            & (pl.col("value").is_not_null())
            & (pl.col("basis") == "per_100g_edible")
        ).rows(named=True)
    }


def test_golden_200_values_and_provenance_match() -> None:
    actual = _actual_sqlite() if SQLITE.is_file() else _actual_canonical()
    failures: list[str] = []
    for row in _rows():
        hit = actual.get((row["food_fr"], row["tagname"]))
        expected = float(row["expected"])
        if hit is None:
            failures.append(f"{row['food_fr']} | {row['tagname']}: missing")
            continue
        value, record = hit
        if not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-9 * max(1.0, abs(expected))):
            failures.append(f"{row['food_fr']} | {row['tagname']}: {value} != {expected}")
        raw = json.loads(record)
        raw_value = str(raw["teneur"]).replace(",", ".")
        if float(raw_value) != expected:
            failures.append(f"{row['food_fr']} | {row['tagname']}: raw {raw_value} != {expected}")
        if str(raw["const_code"]) != row["const_code"]:
            failures.append(f"{row['food_fr']} | {row['tagname']}: wrong source code")
    assert not failures, "golden 200 failures:\n" + "\n".join(failures[:20])
