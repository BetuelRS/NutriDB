"""Golden values against the official CIQUAL 2025 file (F1.9, SPEC §13).

`tests/golden/ciqual_20.csv` holds 61 cells extracted from the official
release (ADR-0003 evidence): 20 well-known foods x 2-4 constituents. The
`expected` column is the primary XML cell (compo_2025_11_03.xml, verbatim
`teneur`), referenced per row; the legacy XLS cell and its coordinates are
recorded as cross-evidence (the XLS is known to diverge on cells the legacy
format lost, e.g. calcium of Eau du robinet: XML 7,13 vs XLS 0).

The test reads the packaged artefact (or the canonical Parquet when the
SQLite is absent, e.g. CI without a local build) and asserts the pipeline
delivers exactly the official values: nothing is ever invented.
"""

from __future__ import annotations

import csv
import math

import polars as pl
import pytest

from nutridb.paths import project_root

ROOT = project_root()
GOLDEN = ROOT / "tests" / "golden" / "ciqual_20.csv"
SQLITE = ROOT / "build" / "artifacts" / "nutridb-core-0.1.0.sqlite"
CANONICAL = ROOT / "build" / "canonical" / "ciqual" / "value.parquet"

_ARTIFACT_AVAILABLE = SQLITE.is_file() or CANONICAL.is_file()

pytestmark = pytest.mark.skipif(
    not _ARTIFACT_AVAILABLE,
    reason="real artefact not built; run `uv run nutridb transform` first",
)


def _rows() -> list[dict[str, str]]:
    with open(GOLDEN, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_golden_file_shape_and_evidence() -> None:
    rows = _rows()
    assert len(rows) == 61
    foods = {row["food_fr"] for row in rows}
    assert len(foods) == 20
    for row in rows:
        assert row["expected"]
        assert row["ref"].startswith("compo_2025_11_03.xml alim ")
        assert row["xls_ref"].startswith("linha ")
        assert row["unit"] in {"g", "mg", "ug", "kcal", "kj"}


def _values_from_sqlite() -> dict[tuple[str, str], float]:
    import sqlite3

    conn = sqlite3.connect(SQLITE)
    try:
        return {
            (row[0], row[1]): row[2]
            for row in conn.execute(
                "SELECT label_fr, nutrient_id, value FROM mv_food_value WHERE value IS NOT NULL"
            )
        }
    finally:
        conn.close()


def _values_from_canonical() -> dict[tuple[str, str], float]:
    values = pl.read_parquet(CANONICAL)
    labels = pl.read_parquet(ROOT / "build" / "canonical" / "ciqual" / "label.parquet")
    label_fr = {
        row["ref"]: row["text"]
        for row in labels.filter(pl.col("ref_kind") == "food", pl.col("locale") == "fr").rows(
            named=True
        )
    }
    out: dict[tuple[str, str], float] = {}
    for row in values.rows(named=True):
        name = label_fr.get(row["concept_id"])
        if name is None or row["value"] is None:
            continue
        out[(name, row["nutrient_id"])] = row["value"]
    return out


def test_golden_values_match_the_artefact() -> None:
    actual = _values_from_sqlite() if SQLITE.is_file() else _values_from_canonical()
    mismatches = []
    for row in _rows():
        got = actual.get((row["food_fr"], row["tagname"]))
        expected = float(str(row["expected"]))
        ok = got is not None and math.isclose(
            got, expected, rel_tol=0.0, abs_tol=1e-9 * max(1.0, abs(expected))
        )
        if not ok:
            mismatches.append(f"{row['food_fr']} | {row['tagname']}: expected {expected} got {got}")
    assert not mismatches, "\n".join(mismatches)


def test_golden_foods_exist_in_the_artefact() -> None:
    values = pl.read_parquet(CANONICAL)
    labels = pl.read_parquet(ROOT / "build" / "canonical" / "ciqual" / "label.parquet")
    fr = set(labels.filter(pl.col("ref_kind") == "food", pl.col("locale") == "fr")["text"])
    concepts = set(values["concept_id"])
    missing = [
        row["food_fr"]
        for row in _rows()
        if row["food_fr"] not in fr
        or labels.filter(
            pl.col("ref_kind") == "food",
            pl.col("locale") == "fr",
            pl.col("text") == row["food_fr"],
        )["ref"].to_list()[0]
        not in concepts
    ]
    assert not missing, f"golden foods missing from the artefact: {missing}"
