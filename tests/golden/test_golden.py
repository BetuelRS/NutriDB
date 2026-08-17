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
GOLDEN_INSA = ROOT / "tests" / "golden" / "insa_10.csv"
MAPPING_INSA = ROOT / "mappings" / "nutrients" / "insa.csv"
SQLITE = ROOT / "build" / "artifacts" / "nutridb-core-0.1.0.sqlite"
CANONICAL = ROOT / "build" / "canonical" / "value.parquet"

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
                "SELECT label, nutrient_id, value FROM mv_food_value "
                "WHERE value IS NOT NULL AND locale = 'fr'"
            )
        }
    finally:
        conn.close()


def _values_from_canonical() -> dict[tuple[str, str], float]:
    values = pl.read_parquet(CANONICAL)
    labels = pl.read_parquet(ROOT / "build" / "canonical" / "label.parquet")
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
    labels = pl.read_parquet(ROOT / "build" / "canonical" / "label.parquet")
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


def test_golden_provenance_walk_on_sqlite() -> None:
    """SPEC §16 F1: values carry provenance — concept -> mv -> source_record.

    Every golden (food, nutrient) cell must be reachable from the label
    through mv_food_value and its source_record raw JSON must contain the
    verbatim `teneur` of the official XML (P1, nothing invented).
    """
    if not SQLITE.is_file():
        pytest.skip("SQLite artefact not built; run `uv run nutridb build`")
    import json
    import sqlite3

    conn = sqlite3.connect(SQLITE)
    try:
        id_by_name = {
            row[1]: row[0]
            for row in conn.execute(
                "SELECT text, ref FROM label WHERE ref_kind='food' AND locale='fr'"
            )
        }
        rows = conn.execute(
            "SELECT concept_id, nutrient_id, source_record_id, value "
            "FROM mv_food_value WHERE value IS NOT NULL AND locale = 'fr'"
        ).fetchall()
        by_food = {(id_by_name[r[0]], r[1]): (r[2], r[3]) for r in rows if r[0] in id_by_name}
        records = {
            r[0]: r[1] for r in conn.execute("SELECT source_record_id, record FROM source_record")
        }
    finally:
        conn.close()

    missing = []
    for row in _rows():
        hit = by_food.get((row["food_fr"], row["tagname"]))
        if hit is None:
            missing.append(f"{row['food_fr']} | {row['tagname']}: no mv row")
            continue
        record_id, value = hit
        raw = records.get(record_id)
        if raw is None:
            missing.append(f"{row['food_fr']} | {row['tagname']}: record {record_id} missing")
            continue
        cell = json.loads(raw)
        expected = float(str(row["expected"]))
        if not math.isclose(value, expected, rel_tol=0.0, abs_tol=1e-9 * max(1.0, abs(expected))):
            missing.append(f"{row['food_fr']} | {row['tagname']}: value {value} != {expected}")
        if float(str(cell["teneur"]).replace(",", ".")) != expected:
            missing.append(
                f"{row['food_fr']} | {row['tagname']}: raw teneur {cell['teneur']} != {expected}"
            )
        if cell.get("const_code") != row["const_code"]:
            missing.append(
                f"{row['food_fr']} | {row['tagname']}: raw const {cell.get('const_code')}"
            )
    assert not missing, "provenance walk failed:\n" + "\n".join(missing)


def _insa_rows() -> list[dict[str, str]]:
    with open(GOLDEN_INSA, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _insa_mapping() -> dict[str, dict[str, str]]:
    with open(MAPPING_INSA, newline="", encoding="utf-8") as handle:
        return {
            row["nutrient_code"]: row
            for row in csv.DictReader(r for r in handle if not r.startswith("#"))
        }


def test_insa_golden_file_shape_and_evidence() -> None:
    rows = _insa_rows()
    assert len(rows) == 35
    foods = {row["food_pt"] for row in rows}
    assert len(foods) == 10
    mapping = _insa_mapping()
    assert {row["key"] for row in rows} <= set(mapping)
    for row in rows:
        assert row["expected"]
        assert row["ref"].startswith("insa_tca.xlsx INSA - BDCA_v 7.1 - 2026 alim ")
        assert row["xls_ref"].startswith("linha ")
        assert row["unit"] in {"g", "mg", "ug", "kcal", "kj"}
        assert mapping[row["key"]]["unit"] == row["unit"] or row["key"] == "acidos_gordos_trans_g"


def _insa_mv_from_sqlite() -> dict[tuple[str, str], tuple[float | None, str, str | None]]:
    import sqlite3

    conn = sqlite3.connect(SQLITE)
    try:
        methods = {
            (row[0], row[1]): row[2]
            for row in conn.execute("SELECT concept_id, nutrient_id, analytical_method FROM value")
        }
        return {
            (row[0], row[1]): (row[2], row[3], methods.get((row[4], row[1])))
            for row in conn.execute(
                "SELECT label, nutrient_id, value, basis, concept_id "
                "FROM mv_food_value WHERE locale = 'pt'"
            )
        }
    finally:
        conn.close()


def test_insa_golden_values_match_the_artefact() -> None:
    """Every golden INSA cell arrives in the mv exactly as the XLSX stores it
    (native floats), converted only by the audited mapping factor (FATRN g->mg)."""
    actual = _insa_mv_from_sqlite()
    mapping = _insa_mapping()
    mismatches = []
    for row in _insa_rows():
        tag = mapping[row["key"]]["tagname"]
        factor = float(mapping[row["key"]]["factor"])
        got = actual.get((row["food_pt"], tag))
        expected = float(str(row["expected"]))
        if (
            got is None
            or got[0] is None
            or not math.isclose(
                got[0],
                expected * factor,
                rel_tol=0.0,
                abs_tol=1e-9 * max(1.0, abs(expected * factor)),
            )
        ):
            mismatches.append(f"{row['food_pt']} | {tag}: expected {expected * factor} got {got}")
            continue
        want_basis = "per_100ml" if row["alim_code"] in {"250014", "250015"} else "per_100g_edible"
        if got[1] != want_basis:
            mismatches.append(f"{row['food_pt']} | {tag}: basis {got[1]} != {want_basis}")
        if tag == "ENERC_KCAL" and got[2] is not None:
            mismatches.append(f"{row['food_pt']} | {tag}: energy method published ({got[2]})")
    assert not mismatches, "INSA golden mismatches:\n" + "\n".join(mismatches)


def test_insa_golden_foods_exist_in_the_artefact() -> None:
    import sqlite3

    conn = sqlite3.connect(SQLITE)
    try:
        labels = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT text, ref FROM label WHERE ref_kind='food' AND locale='pt'"
            )
        }
        concepts_with_values = {
            row[0] for row in conn.execute("SELECT DISTINCT concept_id FROM mv_food_value")
        }
    finally:
        conn.close()
    missing = [
        row["food_pt"]
        for row in _insa_rows()
        if row["food_pt"] not in labels or labels[row["food_pt"]] not in concepts_with_values
    ]
    assert not missing, f"INSA golden foods missing from the artefact: {missing}"


def test_insa_golden_provenance_walk_on_sqlite() -> None:
    """P1: every INSA golden cell's mv row points at a source_record whose raw
    JSON holds the verbatim native cell value and the food code."""
    if not SQLITE.is_file():
        pytest.skip("SQLite artefact not built; run `uv run nutridb build`")
    import json
    import sqlite3

    conn = sqlite3.connect(SQLITE)
    try:
        id_by_name = {
            row[1]: row[0]
            for row in conn.execute(
                "SELECT text, ref FROM label WHERE ref_kind='food' AND locale='pt'"
            )
        }
        rows = conn.execute(
            "SELECT concept_id, nutrient_id, source_record_id, value "
            "FROM mv_food_value WHERE locale = 'pt'"
        ).fetchall()
        by_food = {(id_by_name[r[0]], r[1]): (r[2], r[3]) for r in rows if r[0] in id_by_name}
        records = {
            r[0]: r[1] for r in conn.execute("SELECT source_record_id, record FROM source_record")
        }
    finally:
        conn.close()

    mapping = _insa_mapping()
    missing = []
    for row in _insa_rows():
        tag = mapping[row["key"]]["tagname"]
        hit = by_food.get((row["food_pt"], tag))
        if hit is None:
            missing.append(f"{row['food_pt']} | {tag}: no mv row")
            continue
        record_id, value = hit
        raw = records.get(record_id)
        if raw is None:
            missing.append(f"{row['food_pt']} | {tag}: record {record_id} missing")
            continue
        cell = json.loads(raw)
        expected = float(str(row["expected"]))
        if not math.isclose(
            value,
            expected * float(mapping[row["key"]]["factor"]),
            rel_tol=0.0,
            abs_tol=1e-9 * max(1.0, abs(expected)),
        ):
            missing.append(f"{row['food_pt']} | {tag}: value {value} != {expected}")
        if float(str(cell["value"]).replace(",", ".")) != expected:
            missing.append(f"{row['food_pt']} | {tag}: raw value {cell['value']} != {expected}")
        if str(cell.get("cod")) != row["alim_code"]:
            missing.append(f"{row['food_pt']} | {tag}: raw cod {cell.get('cod')}")
    assert not missing, "INSA provenance walk failed:\n" + "\n".join(missing)
