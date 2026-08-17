"""F2 — mapping CSVs: completeness, validity and the empty-_unmapped gate.

Golden data mirrors the official dumps (CIQUAL 2025 const_2025_11_03.xml,
verified 2026-08-15; INSA/TCA 7.1 Componentes-Correspondência sheet, verified
2026-08-16). Tests needing the real intermediates are skipped when absent
(CI never syncs the cache — rule §17.8).
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from nutridb.mappings import (
    load_foodgroup_mapping,
    load_nutrient_mapping,
    resolve_food_group,
)
from nutridb.paths import project_root
from nutridb.vocab import load_csv

ROOT = project_root()

CIQUAL_2025_CODES = {
    "327",
    "328",
    "332",
    "333",
    "400",
    "10000",
    "10004",
    "10110",
    "10120",
    "10150",
    "10170",
    "10190",
    "10200",
    "10251",
    "10260",
    "10290",
    "10300",
    "10340",
    "10530",
    "25000",
    "25003",
    "31000",
    "32000",
    "32210",
    "32220",
    "32250",
    "32410",
    "32430",
    "32480",
    "33110",
    "34000",
    "34100",
    "40000",
    "40302",
    "40303",
    "40304",
    "40400",
    "40600",
    "40800",
    "41000",
    "41200",
    "41400",
    "41600",
    "41800",
    "41819",
    "41826",
    "41833",
    "42046",
    "42053",
    "42263",
    "51104",
    "51200",
    "51330",
    "52100",
    "52200",
    "52300",
    "53100",
    "54101",
    "54104",
    "55100",
    "56100",
    "56200",
    "56310",
    "56400",
    "56500",
    "56600",
    "56700",
    "56702",
    "56704",
    "56708",
    "60000",
    "65000",
    "71010",
    "75100",
}

# INSA/TCA 7.1: 48 columns of the data sheet, keyed <name>_<unit>
# (ADR-0004 §2, verified against the Componentes-Correspondência sheet).
INSA_2025_CODES = {
    "energia_kcal",
    "energia_kj",
    "lipidos_g",
    "acidos_gordos_saturados_g",
    "acidos_gordos_monoinsaturados_g",
    "acidos_gordos_polinsaturados_g",
    "acido_linoleico_g",
    "acidos_gordos_trans_g",
    "hidratos_de_carbono_g",
    "acucares_g",
    "oligossacaridos_g",
    "amido_g",
    "sal_g",
    "fibra_g",
    "proteinas_g",
    "alcool_g",
    "agua_g",
    "acidos_organicos_g",
    "colesterol_mg",
    "vitamina_a_ug",
    "equivalentes_de_b_caroteno_ug",
    "a_caroteno_ug",
    "b_caroteno_total_ug",
    "b_criptoxantina_ug",
    "licopeno_ug",
    "luteina_ug",
    "zeaxantina_ug",
    "vitamina_d_ug",
    "a_tocoferol_mg",
    "tiamina_mg",
    "riboflavina_mg",
    "niacina_mg",
    "equivalentes_de_niacina_mg",
    "triptofano_60_mg",
    "vitamina_b6_mg",
    "vitamina_b12_ug",
    "vitamina_c_mg",
    "folatos_ug",
    "cinza_g",
    "sodio_mg",
    "potassio_mg",
    "calcio_mg",
    "fosforo_mg",
    "magnesio_mg",
    "ferro_mg",
    "zinco_mg",
    "selenio_ug",
    "iodo_ug",
}

_NUTS: dict[str, list[dict[str, str]]] = {
    "ciqual": load_nutrient_mapping(ROOT, "ciqual"),
    "insa": load_nutrient_mapping(ROOT, "insa"),
}
_FG: dict[str, dict[tuple[str, str], str]] = {
    "ciqual": load_foodgroup_mapping(ROOT, "ciqual"),
    "insa": load_foodgroup_mapping(ROOT, "insa"),
}
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


def test_nutrients_mapping_covers_all_source_codes() -> None:
    assert {r["nutrient_code"] for r in _NUTS["ciqual"]} == CIQUAL_2025_CODES
    assert {r["nutrient_code"] for r in _NUTS["insa"]} == INSA_2025_CODES


def test_nutrients_unique_codes() -> None:
    for source_id, rows in _NUTS.items():
        codes = [r["nutrient_code"] for r in rows]
        assert len(codes) == len(set(codes)), f"{source_id}: duplicate nutrient_code rows"


def test_nutrients_tagnames_and_units_valid() -> None:
    for source_id, rows in _NUTS.items():
        for row in rows:
            tag, unit, factor, method = (
                row["tagname"],
                row["unit"],
                row["factor"],
                row["energy_method"],
            )
            assert tag in UNIT_BY_TAG, (
                f"{source_id} {row['nutrient_code']}: unknown tagname {tag!r}"
            )
            assert unit == UNIT_BY_TAG[tag], (
                f"{source_id} {row['nutrient_code']}: unit {unit!r} != vocab {UNIT_BY_TAG[tag]!r}"
            )
            assert float(factor) > 0, f"{row['nutrient_code']}: factor must be positive"
            assert method == "-" or tag in ENERGY_TAGS, (
                f"{source_id} {row['nutrient_code']}: method on {tag!r}"
            )


def test_nutrients_energy_pinned() -> None:
    ciqual_energy = {
        r["nutrient_code"]: (r["tagname"], r["energy_method"])
        for r in _NUTS["ciqual"]
        if r["energy_method"] != "-"
    }
    assert set(ciqual_energy) == {"327", "328", "332", "333"}
    assert ciqual_energy["328"][0] == "ENERC_KCAL" and ciqual_energy["327"][0] == "ENERC_KJ"
    assert ciqual_energy["332"][0] == "ENERC_KJ" and ciqual_energy["333"][0] == "ENERC_KCAL"
    assert (
        ciqual_energy["327"][1] == ciqual_energy["328"][1]
        and "1169/2011" in ciqual_energy["327"][1]
    )
    assert (
        ciqual_energy["332"][1] == ciqual_energy["333"][1]
        and ciqual_energy["332"][1] != ciqual_energy["327"][1]
    )
    # INSA/TCA does not publish the energy method (ADR-0004 §5): pinned '-'.
    insa_energy = [r for r in _NUTS["insa"] if r["tagname"] in ENERGY_TAGS]
    assert {r["nutrient_code"] for r in insa_energy} == {"energia_kcal", "energia_kj"}
    assert all(r["energy_method"] == "-" for r in insa_energy)


def test_nutrients_absence_rules_are_absence_types() -> None:
    absence_ids = {r["id"] for r in _VOCAB_VALUE_TYPES if r["is_absence"] == "true"}
    for source_id, rows in _NUTS.items():
        for row in rows:
            for col in ("value_type_missing", "value_type_trace", "value_type_below_loq"):
                value = row[col]
                assert value in absence_ids, (
                    f"{source_id} {row['nutrient_code']}: {col}={value!r} is not an absence type"
                )


def test_insa_trans_mapping_converts_to_mg() -> None:
    trans = next(r for r in _NUTS["insa"] if r["tagname"] == "FATRN")
    assert trans["factor"] == "1000" and trans["unit"] == "mg"


def test_foodgroups_valid() -> None:
    for source_id, mapping in _FG.items():
        seen: set[tuple[str, str]] = set()
        for (level, code), group in mapping.items():
            assert level in ("1", "2", "3"), f"{source_id}: bad level {level}/{code}"
            assert group in _VOCAB_FOOD_GROUPS, (
                f"{source_id} {level}/{code}: unknown group {group!r}"
            )
            assert (level, code) not in seen, f"{source_id}: duplicate row {level}/{code}"
            seen.add((level, code))
        assert ("1", "00") not in mapping or source_id == "ciqual", (
            f"{source_id}: placeholder code mapped"
        )


def test_unmapped_gate_is_empty() -> None:
    files = list((ROOT / "mappings" / "_unmapped").glob("*.csv"))
    assert files == [], f"_unmapped/ must stay empty; found {files}"


_INTERMEDIATES = ROOT / "build" / "intermediates"

golden = pytest.mark.skipif(
    not (_INTERMEDIATES / "ciqual" / "food.parquet").is_file(),
    reason="real intermediates absent (cache never synced in CI, rule §17.8)",
)


@golden
def test_foodgroups_resolve_every_food() -> None:
    unresolved: list[tuple[str, str]] = []
    for source_id, mapping in _FG.items():
        foods = pl.read_parquet(_INTERMEDIATES / source_id / "food.parquet")
        for row in foods.rows(named=True):
            if resolve_food_group(mapping, json.loads(row["group_path"])) is None:
                unresolved.append((source_id, row["food_code"]))
    assert not unresolved, f"unresolved foods: {unresolved[:20]}"


@golden
def test_foodgroups_rows_exist_in_intermediates() -> None:
    stale: list[tuple[str, str, str]] = []
    for source_id, mapping in _FG.items():
        groups = pl.read_parquet(_INTERMEDIATES / source_id / "food_group.parquet")
        present = {(r["level"], r["code"]) for r in groups.rows(named=True)}
        for level, code in mapping:
            if (level, code) == ("1", "00"):
                continue  # CIQUAL emits 00 only in foods, never in alim_grp
            if (level, code) not in present:
                stale.append((source_id, level, code))
    assert not stale, f"mapping rows without source group: {stale[:20]}"


@golden
def test_nutrient_codes_exist_in_intermediates() -> None:
    for source_id, rows in _NUTS.items():
        constituents = pl.read_parquet(_INTERMEDIATES / source_id / "constituent.parquet")
        present = {r["nutrient_code"] for r in constituents.rows(named=True)}
        mapped = {r["nutrient_code"] for r in rows}
        assert mapped == present, f"{source_id}: mapping does not match constituents"
