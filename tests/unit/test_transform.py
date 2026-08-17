"""Unit tests for the canonical transform (F2, SPEC §8, ADR-0001 D5).

Runs the extractors over the synthetic fixtures and asserts the canonical
dataset: typed values, unit conversion, absence semantics (coverage +
explicit flags, never a Cartesian product), provenance and determinism.
"""

from __future__ import annotations

import json
from shutil import copyfile
from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.paths import project_root
from nutridb.sources.ciqual import extract as extract_ciqual
from nutridb.transform import TransformError, transform

if TYPE_CHECKING:
    from pathlib import Path

FIXTURE = project_root() / "tests" / "fixtures" / "synthetic_ciqual"
ROOT = project_root()

_FIXTURE_MAP = {
    "alim_2025_11_03.xml": "alim_synthetic.xml",
    "alim_grp_2025_11_03.xml": "alim_grp_synthetic.xml",
    "compo_2025_11_03.xml": "compo_synthetic.xml",
    "const_2025_11_03.xml": "const_synthetic.xml",
    "sources_2025_11_03.xml": "sources_synthetic.xml",
}


def _make_cache(base: Path) -> Path:
    cache = base / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for official, synthetic in _FIXTURE_MAP.items():
        copyfile(FIXTURE / synthetic, cache / official)
    return cache


def _run(base: Path) -> dict[str, int]:
    extract_ciqual(_make_cache(base), base / "i" / "ciqual")
    return transform(base / "i", base / "c", ROOT)


def _read(base: Path, name: str) -> pl.DataFrame:
    return pl.read_parquet(base / "c" / f"{name}.parquet")


def _by_pair(rows: pl.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    return {
        (r["concept_id"], r["source_nutrient_code"]): r
        for r in rows.sort(["concept_id", "source_nutrient_code"]).rows(named=True)
    }


def test_transform_counts_and_tables(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report["foods"] == 3
    assert report["concepts"] == 3
    assert report["coverage"] == 5
    assert report["values"] == 8
    assert report["not_measured"] == 1
    assert report.setdefault("conversions_x10", 0) == 0
    for name in (
        "source",
        "coverage",
        "source_record",
        "concept",
        "concept_link",
        "value",
        "derivation",
        "tombstone",
    ):
        assert (tmp_path / "c" / f"{name}.parquet").is_file(), name


def test_value_typing_and_unit_conversion(tmp_path: Path) -> None:
    _run(tmp_path)
    values = _read(tmp_path, "value")
    nutrients = values["nutrient_id"].to_list()

    row = values.filter(pl.col("source_nutrient_code") == "40302").row(0)
    assert row[values.columns.index("value")] == 0.5  # AG stay in g (INFOODS unit)
    assert row[values.columns.index("unit")] == "g"
    assert row[values.columns.index("value_type")] == "measured"
    assert row[values.columns.index("min_value")] == 0.4
    assert row[values.columns.index("max_value")] == 0.6

    energy = values.filter(pl.col("source_nutrient_code") == "327").row(0)
    assert energy[values.columns.index("value")] == 1140.0
    assert energy[values.columns.index("unit")] == "kj"
    assert energy[values.columns.index("analytical_method")] == "Reg. UE 1169/2011 (Atwater)"
    assert "ENERC_KJ" in nutrients

    water = values.filter(
        pl.col("source_nutrient_code") == "400", pl.col("min_value").is_not_null()
    ).row(0)
    assert water[values.columns.index("value")] == 59.7
    assert water[values.columns.index("min_value")] == 58.7
    assert water[values.columns.index("max_value")] == 60.4
    assert water[values.columns.index("basis")] == "per_100g_edible"

    loq = values.filter(pl.col("value_type") == "below_loq").row(0)
    assert loq[values.columns.index("value")] is None
    assert loq[values.columns.index("below_loq_threshold")] == 1.5
    assert values.filter(pl.col("value_type") == "trace").height == 1


def test_absence_via_coverage_never_cross_product(tmp_path: Path) -> None:
    _run(tmp_path)
    values = _read(tmp_path, "value")
    coverage = _read(tmp_path, "coverage")

    assert {"ENERC_KJ", "ENERC_KCAL", "WATER", "FIBTG", "FASAT"} == set(coverage["nutrient_id"])
    assert coverage["nutrient_id"].unique().len() == coverage.height
    assert coverage["source_id"].to_list() == ["ciqual"] * 5

    pairs = values.select(pl.col("concept_id").alias("f"), "nutrient_id")
    expected = 3 * 4  # full Cartesian product that must NOT exist in `value`
    assert pairs.height < expected, "never materialize the per-cell cross-product"
    assert pairs.is_unique().all()

    zero = values.filter(pl.col("value") == 0.0)
    assert zero.height == 1
    assert zero["value_type"].to_list() == ["measured"]  # legal zero preserved


def test_value_provenance_full_chain(tmp_path: Path) -> None:
    _run(tmp_path)
    values = _read(tmp_path, "value")
    records = _read(tmp_path, "source_record")
    concepts = _read(tmp_path, "concept")
    links = _read(tmp_path, "concept_link")

    cell = values.filter(pl.col("source_nutrient_code") == "400", pl.col("value") == 59.7).row(0)
    concept_id = cell[values.columns.index("concept_id")]
    record_id = cell[values.columns.index("source_record_id")]
    assert cell[values.columns.index("source_id")] == "ciqual"
    assert cell[values.columns.index("source_nutrient_code")] == "400"
    assert cell[values.columns.index("confidence_code")] == "D"

    raw = json.loads(records.filter(pl.col("source_record_id") == record_id)["record"].to_list()[0])
    assert raw["teneur"] == "59,7"
    assert raw["source_code"] == "444"

    food_record = links.filter(pl.col("concept_id") == concept_id)["source_record_id"].to_list()[0]
    food_json = json.loads(
        records.filter(pl.col("source_record_id") == food_record)["record"].to_list()[0]
    )
    assert food_json["raw"]["alim_nom_fr"] == "Pastis"

    row = concepts.filter(pl.col("concept_id") == concept_id).row(0)
    assert row[concepts.columns.index("kind")] == "food"
    assert row[concepts.columns.index("food_group")] == "alcoholic_beverages"


def test_concept_links_automatic_1_to_1(tmp_path: Path) -> None:
    _run(tmp_path)
    links = _read(tmp_path, "concept_link")
    assert links.height == 3
    assert set(links["status"].unique()) == {"automatic"}
    assert links["concept_id"].is_unique().all()


def test_derivation_and_tombstone_empty_schema(tmp_path: Path) -> None:
    _run(tmp_path)
    for name, columns in (
        ("derivation", {"derivation_id", "formula", "inputs", "factors"}),
        ("tombstone", {"tombstone_id", "successor_id", "reason"}),
    ):
        table = _read(tmp_path, name)
        assert table.height == 0
        assert set(table.columns) == columns


def test_source_row_from_registry(tmp_path: Path) -> None:
    _run(tmp_path)
    source = _read(tmp_path, "source")
    assert source.height == 1
    row = source.row(0, named=True)
    assert row["source_id"] == "ciqual"
    assert row["license_id"] == "etalab-2.0"
    assert "CIQUAL" in row["name"]


def test_transform_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    _run(first)
    _run(second)
    for name in (
        "source",
        "coverage",
        "source_record",
        "concept",
        "concept_link",
        "value",
        "derivation",
        "tombstone",
    ):
        a = (first / "c" / f"{name}.parquet").read_bytes()
        b = (second / "c" / f"{name}.parquet").read_bytes()
        assert a == b, f"{name}.parquet is not byte-identical"


def test_missing_intermediates_fail_high(tmp_path: Path) -> None:
    with pytest.raises(TransformError, match="no source intermediates"):
        transform(tmp_path / "i", tmp_path / "c", ROOT)


def test_missing_contract_table_fails_high(tmp_path: Path) -> None:
    (tmp_path / "i" / "ciqual").mkdir(parents=True)
    (tmp_path / "i" / "ciqual" / "food.parquet").write_bytes(b"x")
    with pytest.raises(TransformError, match="intermediates missing"):
        transform(tmp_path / "i", tmp_path / "c", ROOT)


def test_unmapped_constituent_fails_high(tmp_path: Path) -> None:
    cache = _make_cache(tmp_path)
    cache.joinpath("const_2025_11_03.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><TABLE>'
        "<CONST><const_code>99999</const_code>"
        "<const_nom_fr>Fantasme (g/100 g)</const_nom_fr>"
        "<const_nom_eng>Fantasy (g/100 g)</const_nom_eng>"
        "<code_INFOODS>XXXXX</code_INFOODS></CONST></TABLE>",
        encoding="utf-8",
    )
    cache.joinpath("compo_2025_11_03.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><TABLE><COMPO>'
        "<alim_code>1000</alim_code><const_code>99999</const_code>"
        "<teneur>1</teneur><min></min><max></max>"
        "<code_confiance>D</code_confiance><source_code>444</source_code>"
        "</COMPO></TABLE>",
        encoding="utf-8",
    )
    extract_ciqual(cache, tmp_path / "i" / "ciqual")
    with pytest.raises(TransformError, match="unmapped source nutrient code '99999'"):
        transform(tmp_path / "i", tmp_path / "c", ROOT)
