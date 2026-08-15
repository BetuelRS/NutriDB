"""F1.3 — mapping CSVs: completeness, validity and the empty-_unmapped gate.

Golden data mirrors the official CIQUAL 2025 dump (const_2025_11_03.xml,
verified 2026-08-15): 74 constituent codes. Tests needing the real
intermediates are skipped when `build/intermediates/ciqual` is absent
(CI never syncs the cache — rule §17.8).
"""

from __future__ import annotations

import polars as pl
import pytest

from nutridb.mappings import (
    PLACEHOLDER_GROUP_CODES,
    load_foodgroup_mapping,
    load_nutrient_mapping,
    resolve_food_group,
)
from nutridb.paths import project_root
from nutridb.vocab import load_csv

ROOT = project_root()

CIQUAL_2025_CODES = (
    327,
    328,
    332,
    333,
    400,
    10000,
    10004,
    10110,
    10120,
    10150,
    10170,
    10190,
    10200,
    10251,
    10260,
    10290,
    10300,
    10340,
    10530,
    25000,
    25003,
    31000,
    32000,
    32210,
    32220,
    32250,
    32410,
    32430,
    32480,
    33110,
    34000,
    34100,
    40000,
    40302,
    40303,
    40304,
    40400,
    40600,
    40800,
    41000,
    41200,
    41400,
    41600,
    41800,
    41819,
    41826,
    41833,
    42046,
    42053,
    42263,
    51104,
    51200,
    51330,
    52100,
    52200,
    52300,
    53100,
    54101,
    54104,
    55100,
    56100,
    56200,
    56310,
    56400,
    56500,
    56600,
    56700,
    56702,
    56704,
    56708,
    60000,
    65000,
    71010,
    75100,
)

_NUTS = load_nutrient_mapping(ROOT)
_FG = load_foodgroup_mapping(ROOT)
_VOCAB_NUTRIENTS = load_csv(
    ROOT / "vocab" / "nutrients.csv", ("tagname", "group", "name_en", "unit")
)
_VOCAB_UNITS = {r["id"] for r in load_csv(ROOT / "vocab" / "units.csv", ("id", "name_en"))}
_VOCAB_VALUE_TYPES = load_csv(
    ROOT / "vocab" / "value_types.csv", ("id", "name_en", "is_absence", "description")
)
_VOCAB_FOOD_GROUPS = {
    r["id"] for r in load_csv(ROOT / "vocab" / "food_groups.csv", ("id", "name_en", "name_pt"))
}
UNIT_BY_TAG = {r["tagname"]: r["unit"] for r in _VOCAB_NUTRIENTS}
ENERGY_TAGS = {"ENERC_KJ", "ENERC_KCAL"}


def test_nutrients_mapping_covers_all_ciqual_codes() -> None:
    assert {int(r["const_code"]) for r in _NUTS} == set(CIQUAL_2025_CODES)


def test_nutrients_unique_codes() -> None:
    codes = [r["const_code"] for r in _NUTS]
    assert len(codes) == len(set(codes)) == len(CIQUAL_2025_CODES)


def test_nutrients_tagnames_and_units_valid() -> None:
    for row in _NUTS:
        tag, unit, factor, method = row["tagname"], row["unit"], row["factor"], row["energy_method"]
        assert tag in UNIT_BY_TAG, f"{row['const_code']}: unknown tagname {tag!r}"
        assert unit == UNIT_BY_TAG[tag], (
            f"{row['const_code']}: unit {unit!r} != vocab {UNIT_BY_TAG[tag]!r}"
        )
        assert float(factor) > 0, f"{row['const_code']}: factor must be positive"
        assert method == "-" or tag in ENERGY_TAGS, f"{row['const_code']}: method on {tag!r}"


def test_nutrients_energy_pinned() -> None:
    energy = {
        int(r["const_code"]): (r["tagname"], r["energy_method"])
        for r in _NUTS
        if r["energy_method"] != "-"
    }
    assert set(energy) == {327, 328, 332, 333}
    assert energy[327][0] == "ENERC_KJ" and energy[328][0] == "ENERC_KCAL"
    assert energy[332][0] == "ENERC_KJ" and energy[333][0] == "ENERC_KCAL"
    assert energy[327][1] == energy[328][1] and "1169/2011" in energy[327][1]
    assert energy[332][1] == energy[333][1] and energy[332][1] != energy[327][1]


def test_nutrients_absence_rules_are_absence_types() -> None:
    absence_ids = {r["id"] for r in _VOCAB_VALUE_TYPES if r["is_absence"] == "true"}
    for row in _NUTS:
        for col in ("value_type_missing", "value_type_trace", "value_type_below_loq"):
            value = row[col]
            assert value in absence_ids, (
                f"{row['const_code']}: {col}={value!r} is not an absence type"
            )


def test_foodgroups_valid() -> None:
    seen: set[tuple[str, str]] = set()
    for (level, code), group in _FG.items():
        assert level in ("grp", "ssgrp", "ssssgrp"), f"{level}/{code}"
        if (level, code) != ("grp", "00"):
            assert code not in PLACEHOLDER_GROUP_CODES, f"placeholder code mapped: {level}/{code}"
        assert group in _VOCAB_FOOD_GROUPS, f"{level}/{code}: unknown food_group {group!r}"
        assert (level, code) not in seen, f"duplicate row {level}/{code}"
        seen.add((level, code))


def test_unmapped_gate_is_empty() -> None:
    files = list((ROOT / "mappings" / "_unmapped").glob("*.csv"))
    assert files == [], f"_unmapped/ must stay empty; found {files}"


_INTERMEDIATES = ROOT / "build" / "intermediates" / "ciqual"

golden = pytest.mark.skipif(
    not (_INTERMEDIATES / "foods.parquet").is_file(),
    reason="real intermediates absent (cache never synced in CI, rule §17.8)",
)


@golden
def test_foodgroups_resolve_every_food() -> None:
    foods = pl.read_parquet(_INTERMEDIATES / "foods.parquet")
    unresolved: list[tuple[int, str, str, str]] = []
    for row in foods.rows(named=True):
        alim = {
            "alim_grp_code": row["alim_grp_code"],
            "alim_ssgrp_code": row["alim_ssgrp_code"],
            "alim_ssssgrp_code": row["alim_ssssgrp_code"],
        }
        if resolve_food_group(_FG, alim) is None:
            unresolved.append((row["alim_code"], *alim.values()))
    assert not unresolved, f"unresolved foods: {unresolved[:20]}"


@golden
def test_foodgroups_rows_exist_in_intermediates() -> None:
    groups = pl.read_parquet(_INTERMEDIATES / "food_groups.parquet")
    present = {(r["level"], r["code"]) for r in groups.rows(named=True)}
    # ('grp', '00') is emitted only in foods (alim 24999 has no group at all), never in alim_grp.
    stale = [
        (level, code)
        for (level, code) in _FG
        if (level, code) != ("grp", "00") and (level, code) not in present
    ]
    assert not stale, f"mapping rows without source group: {stale}"


@golden
def test_nutrient_codes_exist_in_intermediates() -> None:
    constituents = pl.read_parquet(_INTERMEDIATES / "constituents.parquet")
    present = {r["const_code"] for r in constituents.rows(named=True)}
    mapped = {int(r["const_code"]) for r in _NUTS}
    assert mapped == present
