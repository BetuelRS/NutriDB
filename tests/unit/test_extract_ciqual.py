"""Unit tests for the CIQUAL 2025 XML extractor (F2, ADR-0005 contract).

Uses the synthetic fixture under tests/fixtures/synthetic_ciqual/ (rule
§17.7: fictional data, marked as such, isolated).
"""

from __future__ import annotations

from shutil import copyfile
from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.paths import project_root
from nutridb.sources.ciqual import (
    CiqualExtractError,
    extract,
    parse_aliments,
)

if TYPE_CHECKING:
    from pathlib import Path

FIXTURE = project_root() / "tests" / "fixtures" / "synthetic_ciqual"

_FIXTURE_MAP = {
    "alim_2025_11_03.xml": "alim_synthetic.xml",
    "alim_grp_2025_11_03.xml": "alim_grp_synthetic.xml",
    "compo_2025_11_03.xml": "compo_synthetic.xml",
    "const_2025_11_03.xml": "const_synthetic.xml",
    "sources_2025_11_03.xml": "sources_synthetic.xml",
}

_CONTRACT_FILES = ("food", "food_group", "constituent", "value")


def _make_cache(base: Path) -> Path:
    """Synthetic fixtures copied under their official cache names (ADR-0003)."""
    cache = base / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for official, synthetic in _FIXTURE_MAP.items():
        copyfile(FIXTURE / synthetic, cache / official)
    return cache


def _run(base: Path) -> dict[str, int]:
    return extract(_make_cache(base), base / "i")


def test_extract_counts_and_reports(tmp_path: Path) -> None:
    report = _run(tmp_path)
    assert report == {
        "foods": 3,
        "constituents": 5,
        "groups": 3,
        "sources": 2,
        "values": 9,
    }
    for name in _CONTRACT_FILES:
        assert (tmp_path / "i" / f"{name}.parquet").is_file()


def test_extract_values_typed(tmp_path: Path) -> None:
    _run(tmp_path)
    values = pl.read_parquet(tmp_path / "i" / "value.parquet")
    by_pair = {(r["food_code"], r["nutrient_code"]): r for r in values.rows(named=True)}
    assert by_pair[("1000", "327")]["value_kind"] == "number"
    assert by_pair[("1000", "327")]["value"] == 1140.0
    assert by_pair[("1000", "400")]["value"] == 59.7
    assert by_pair[("1000", "400")]["min_value"] == 58.7
    assert by_pair[("1000", "400")]["max_value"] == 60.4
    assert by_pair[("1000", "34100")]["value_kind"] == "trace"
    assert by_pair[("1000", "34100")]["value"] is None
    assert by_pair[("1001", "400")]["value_kind"] == "missing"
    assert by_pair[("1001", "400")]["value"] is None
    assert by_pair[("1001", "400")]["confidence_code"] is None
    assert by_pair[("1001", "34100")]["value_kind"] == "number"
    assert by_pair[("1001", "34100")]["value"] == 0.0
    assert by_pair[("1002", "34100")]["value_kind"] == "below_loq"
    assert by_pair[("1002", "34100")]["threshold"] == 1.5
    assert by_pair[("1002", "34100")]["value"] is None
    assert by_pair[("1002", "400")]["value"] == 0.0009
    assert by_pair[("1002", "400")]["min_value"] == 1e-6
    assert by_pair[("1002", "400")]["max_value"] == 10.2
    assert by_pair[("1000", "40302")]["value"] == 0.5
    assert by_pair[("1000", "40302")]["min_value"] == 0.4
    assert by_pair[("1000", "40302")]["max_value"] == 0.6
    assert all(r["basis"] == "per_100g_edible" for r in values.rows(named=True))


def test_extract_keeps_provenance_in_json(tmp_path: Path) -> None:
    _run(tmp_path)
    values = pl.read_parquet(tmp_path / "i" / "value.parquet")
    row = values.filter(pl.col("food_code") == "1000", pl.col("nutrient_code") == "400").row(0)
    record = row[-1]
    assert '"teneur":"59,7"' in record
    assert '"code_confiance":"D"' in record
    assert '"source_code":"444"' in record


def test_extract_preserves_constituent_name_and_unit(tmp_path: Path) -> None:
    _run(tmp_path)
    const = pl.read_parquet(tmp_path / "i" / "constituent.parquet")
    codes = {r["nutrient_code"]: r for r in const.rows(named=True)}
    assert codes["34100"]["unit"] == "g"
    assert codes["34100"]["name"] == "Fibres alimentaires (g/100 g)"


def test_extract_food_records(tmp_path: Path) -> None:
    _run(tmp_path)
    foods = pl.read_parquet(tmp_path / "i" / "food.parquet")
    assert foods.height == 3
    row = foods.filter(pl.col("food_code") == "1000").row(0)
    assert row[1] == "Pastis"
    assert '"fr":"Pastis"' in row[2] and '"en":' in row[2]
    assert '"1":"06"' in row[3] and '"3":"060303"' in row[3]
    assert '"facteur_jones":6.25' in row[4]


def test_extract_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    _run(first)
    _run(second)
    for name in _CONTRACT_FILES:
        a = (first / "i" / f"{name}.parquet").read_bytes()
        b = (second / "i" / f"{name}.parquet").read_bytes()
        assert a == b, f"{name}.parquet is not byte-identical"


def _write_mini_cache(tmp_path: Path, compo: str) -> Path:
    cache = _make_cache(tmp_path)
    cache.joinpath("compo_2025_11_03.xml").write_text(compo, encoding="utf-8")
    return cache


def test_unknown_cell_fails_high(tmp_path: Path) -> None:
    bad = (
        '<?xml version="1.0" encoding="utf-8"?><TABLE><COMPO>'
        "<alim_code>1000</alim_code><const_code>400</const_code>"
        "<teneur>??</teneur>"
        '<min missing=" "/><max missing=" "/>'
        "<code_confiance>D</code_confiance><source_code>444</source_code>"
        "</COMPO></TABLE>"
    )
    cache = _write_mini_cache(tmp_path, bad)
    with pytest.raises(CiqualExtractError, match="unexpected teneur cell"):
        extract(cache, tmp_path / "out")


def test_duplicate_pair_fails_high(tmp_path: Path) -> None:
    block = (
        "<COMPO><alim_code>1000</alim_code><const_code>400</const_code>"
        "<teneur>1</teneur><min></min><max></max>"
        "<code_confiance>D</code_confiance><source_code>1</source_code></COMPO>"
    )
    duplicate = (
        '<?xml version="1.0" encoding="utf-8"?><TABLE>'
        f"{block}{block.replace('<teneur>1</teneur>', '<teneur>2</teneur>')}"
        "</TABLE>"
    )
    cache = _write_mini_cache(tmp_path, duplicate)
    with pytest.raises(CiqualExtractError, match="duplicate pair"):
        extract(cache, tmp_path / "out")


def test_orphan_alim_code_fails_high(tmp_path: Path) -> None:
    block = (
        "<COMPO><alim_code>9999</alim_code><const_code>400</const_code>"
        "<teneur>1</teneur><min></min><max></max>"
        "<code_confiance>D</code_confiance><source_code>1</source_code></COMPO>"
    )
    cache = _write_mini_cache(
        tmp_path, '<?xml version="1.0" encoding="utf-8"?><TABLE>' + block + "</TABLE>"
    )
    with pytest.raises(CiqualExtractError, match="orphan alim_code"):
        extract(cache, tmp_path / "out")


def test_unknown_source_code_fails_high(tmp_path: Path) -> None:
    block = (
        "<COMPO><alim_code>1000</alim_code><const_code>400</const_code>"
        "<teneur>1</teneur><min></min><max></max>"
        "<code_confiance>D</code_confiance><source_code>999</source_code></COMPO>"
    )
    cache = _write_mini_cache(
        tmp_path, '<?xml version="1.0" encoding="utf-8"?><TABLE>' + block + "</TABLE>"
    )
    with pytest.raises(CiqualExtractError, match="unknown source_code"):
        extract(cache, tmp_path / "out")


def test_missing_group_reference_fails_high(tmp_path: Path) -> None:
    bad_alim = (
        '<?xml version="1.0" encoding="utf-8"?><TABLE><ALIM>'
        "<alim_code>1000</alim_code><alim_nom_fr>x</alim_nom_fr><alim_nom_eng>x</alim_nom_eng>"
        '<alim_nom_sci missing=" "/>'
        "<alim_grp_code>99</alim_grp_code><alim_ssgrp_code>9901</alim_ssgrp_code>"
        "<alim_ssssgrp_code>990101</alim_ssssgrp_code>"
        "<facteur_Jones>6.25</facteur_Jones></ALIM></TABLE>"
    )
    cache = _make_cache(tmp_path)
    cache.joinpath("alim_2025_11_03.xml").write_text(bad_alim, encoding="utf-8")
    with pytest.raises(CiqualExtractError, match="not in alim_grp"):
        extract(cache, tmp_path / "out")


def test_unexpected_min_max_fails_high(tmp_path: Path) -> None:
    bad = (
        '<?xml version="1.0" encoding="utf-8"?><TABLE><COMPO>'
        "<alim_code>1000</alim_code><const_code>400</const_code>"
        "<teneur>1</teneur><min>muito</min><max></max>"
        "<code_confiance>D</code_confiance><source_code>444</source_code>"
        "</COMPO></TABLE>"
    )
    cache = _write_mini_cache(tmp_path, bad)
    with pytest.raises(CiqualExtractError, match="min/max"):
        extract(cache, tmp_path / "out")


def test_aliments_parse_factor_and_names() -> None:
    foods = parse_aliments(FIXTURE / "alim_synthetic.xml")
    assert foods[0][0] == "1000"
    assert foods[0][7] == 6.25
    assert foods[0][4] == "06"
    assert len(foods) == 3
