"""Unit tests for the CIQUAL 2025 XML extractor (F1.2).

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
        "aliments": 3,
        "constituents": 4,
        "groups": 3,
        "sources": 2,
        "values": 8,
    }
    for name in ("foods", "food_groups", "constituents", "sources", "values"):
        assert (tmp_path / "i" / f"{name}.parquet").is_file()


def test_extract_values_typed(tmp_path: Path) -> None:
    _run(tmp_path)
    values = pl.read_parquet(tmp_path / "i" / "values.parquet")
    typed = values.sort(["alim_code", "const_code"]).with_columns(
        [pl.col("teneur_raw").alias("raw")]
    )
    by_pair = {(r["alim_code"], r["const_code"]): r for r in typed.rows(named=True)}
    assert by_pair[(1000, 327)]["raw"] == "1140"
    assert by_pair[(1000, 327)]["teneur_kind"] == "number"
    assert by_pair[(1000, 327)]["teneur_value"] == 1140.0
    assert by_pair[(1000, 400)]["raw"] == "59,7"
    assert by_pair[(1000, 400)]["teneur_value"] == 59.7
    assert by_pair[(1000, 400)]["min_value"] == 58.7
    assert by_pair[(1000, 400)]["max_value"] == 60.4
    assert by_pair[(1000, 34100)]["teneur_kind"] == "trace"
    assert by_pair[(1000, 34100)]["teneur_value"] is None
    assert by_pair[(1001, 400)]["teneur_kind"] == "missing"
    assert by_pair[(1001, 400)]["teneur_value"] is None
    assert by_pair[(1001, 400)]["code_confiance"] is None
    assert by_pair[(1001, 400)]["source_code"] is None
    assert by_pair[(1001, 34100)]["teneur_kind"] == "number"
    assert by_pair[(1001, 34100)]["teneur_value"] == 0.0
    assert by_pair[(1002, 34100)]["teneur_kind"] == "below_loq"
    assert by_pair[(1002, 34100)]["teneur_value"] == 1.5
    assert by_pair[(1002, 400)]["teneur_value"] == 0.0009
    assert by_pair[(1002, 400)]["min_value"] == 1e-6
    assert by_pair[(1002, 400)]["max_value"] == 10.2
    assert by_pair[(1000, 40302)]["teneur_raw"] == "0,5"
    assert by_pair[(1000, 40302)]["teneur_value"] == 0.5
    assert by_pair[(1000, 40302)]["min_value"] == 0.4
    assert by_pair[(1000, 40302)]["max_value"] == 0.6


def test_extract_keeps_provenance_in_json(tmp_path: Path) -> None:
    _run(tmp_path)
    values = pl.read_parquet(tmp_path / "i" / "values.parquet")
    row = values.filter(pl.col("alim_code") == 1000, pl.col("const_code") == 400).row(0)
    assert '"teneur":"59,7"' in row[-1]
    assert '"code_confiance":"D"' in row[-1]
    assert '"source_code":"444"' in row[-1]


def test_extract_preserves_infooods_of_constituents(tmp_path: Path) -> None:
    _run(tmp_path)
    const = pl.read_parquet(tmp_path / "i" / "constituents.parquet")
    codes = {r["const_code"]: r for r in const.rows(named=True)}
    assert codes[34100]["code_INFOODS"] == "FIB-"
    assert codes[34100]["const_nom_fr"] == "Fibres alimentaires (g/100 g)"


def test_extract_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    _run(first)
    _run(second)
    for name in ("foods", "food_groups", "constituents", "sources", "values"):
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
    assert foods[0][0] == 1000
    assert foods[0][7] == 6.25
    assert foods[0][4] == "06"
    assert len(foods) == 3
