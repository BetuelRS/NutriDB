"""Unit tests for canonical vocabulary invariants (SPEC §5, P8/P9).

Fixtures here are synthetic (rule §17.7): they only exercise validation
logic, never nutritional facts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nutridb.paths import project_root
from nutridb.vocab import check_vocabulary, load_csv

if TYPE_CHECKING:
    from pathlib import Path

NUTRIENTS_OK = """tagname,group,name_en,unit
# synthetic fixture — for validation tests only
ENERC_KCAL,energy,Energy (kcal),kcal
WATER,proximates,Water,g
FASAT,lipids,Fatty acids saturated,mg
F4D0,lipids,Fatty acid 4:0,mg
"""

GROUPS_OK = """id,name_en,name_pt
energy,Energy,Energia
proximates,Proximates,Proximados
lipids,Lipids,Lipidos
"""

UNITS_OK = """id,name_en
g,Gram
mg,Milligram
kcal,Kilocalorie
"""

VALUE_TYPES_OK = """id,name_en,is_absence,description
measured,Measured,false,x
assumed_zero,Assumed zero,true,x
not_measured,Not measured,true,x
not_detected,Not detected,true,x
below_loq,Below LOQ,true,x
trace,Trace,true,x
not_applicable,Not applicable,true,x
"""

FACET_OK = """id,name_en,name_pt,name_fr,name_es,name_de,name_it,name_pt_PT,name_pt_BR
breast,Breast,Peito,Poitrine,Pechuga,Brust,Petto,Peito,Peito
"""


def _write(tmp: Path, name: str, content: str) -> None:
    (tmp / name).write_text(content, encoding="utf-8")


def _synthetic_vocab(tmp: Path, *, nutrient_rows: str = NUTRIENTS_OK) -> Path:
    root = tmp / "repo"
    (root / "vocab" / "facets").mkdir(parents=True)
    _write(root / "vocab", "nutrients.csv", nutrient_rows)
    _write(root / "vocab", "nutrient_groups.csv", GROUPS_OK)
    _write(root / "vocab", "units.csv", UNITS_OK)
    _write(root / "vocab", "value_types.csv", VALUE_TYPES_OK)
    _write(root / "vocab", "acquisition_types.csv", "id,name_en,description\nA,Analytical,x\n")
    _write(root / "vocab", "analytical_methods.csv", "id,name_en,description\nhplc,HPLC,x\n")
    _write(root / "vocab", "food_groups.csv", "id,name_en,name_pt\ncereals,Cereals,Cereais\n")
    _write(root / "vocab", "nutrient_relation.csv", "parent,child\n")
    for facet in (
        "base_terms",
        "parts",
        "states",
        "cooking_methods",
        "media",
        "treatments",
        "qualifiers",
    ):
        _write(root / "vocab" / "facets", f"{facet}.csv", FACET_OK)
    return root


def test_load_csv_skips_comments_and_checks_header(tmp_path: Path) -> None:
    target = tmp_path / "sample.csv"
    target.write_text("# comment\nid,name_en\n# another\na,Alpha\n", encoding="utf-8")
    rows = load_csv(target, ("id", "name_en"))
    assert rows == [{"id": "a", "name_en": "Alpha"}]


def test_real_vocabulary_passes_invariants() -> None:
    report = check_vocabulary(project_root())
    assert report.ok, report.errors
    assert report.counts["nutrients"] >= 150
    assert report.counts["facets/base_terms"] >= 10


def test_duplicate_tagname_detected(tmp_path: Path) -> None:
    rows = NUTRIENTS_OK + "WATER,proximates,Water again,g\n"
    report = check_vocabulary(_synthetic_vocab(tmp_path, nutrient_rows=rows))
    assert not report.ok
    assert any("duplicates" in e and "tagname" in e for e in report.errors)


def test_unknown_group_detected(tmp_path: Path) -> None:
    rows = NUTRIENTS_OK.replace("WATER,proximates,", "WATER,no_such_group,")
    report = check_vocabulary(_synthetic_vocab(tmp_path, nutrient_rows=rows))
    assert not report.ok
    assert any("unknown group" in e for e in report.errors)


def test_unknown_unit_detected(tmp_path: Path) -> None:
    rows = NUTRIENTS_OK.replace(",kcal\n", ",litres\n", 1)
    report = check_vocabulary(_synthetic_vocab(tmp_path, nutrient_rows=rows))
    assert not report.ok
    assert any("unknown unit" in e for e in report.errors)


def test_bad_tagname_pattern_detected(tmp_path: Path) -> None:
    rows = NUTRIENTS_OK.replace("ENERC_KCAL", "1ENERC")
    report = check_vocabulary(_synthetic_vocab(tmp_path, nutrient_rows=rows))
    assert not report.ok
    assert any("violates INFOODS pattern" in e for e in report.errors)


def test_missing_relation_parent_detected(tmp_path: Path) -> None:
    root = _synthetic_vocab(tmp_path)
    (root / "vocab" / "nutrient_relation.csv").write_text(
        "parent,child\nNOT_A_TAG,F4D0\n", encoding="utf-8"
    )
    report = check_vocabulary(root)
    assert not report.ok
    assert any("parent" in e and "not in nutrients" in e for e in report.errors)


def test_relation_cycle_detected(tmp_path: Path) -> None:
    root = _synthetic_vocab(tmp_path)
    (root / "vocab" / "nutrient_relation.csv").write_text(
        "parent,child\nWATER,WATER\nFASAT,F4D0\n", encoding="utf-8"
    )
    report = check_vocabulary(root)
    assert not report.ok
    assert any("cycle" in e for e in report.errors)


def test_missing_absence_type_detected(tmp_path: Path) -> None:
    root = _synthetic_vocab(tmp_path)
    (root / "vocab" / "value_types.csv").write_text(
        VALUE_TYPES_OK.replace("trace,Trace,true,x\n", ""), encoding="utf-8"
    )
    report = check_vocabulary(root)
    assert not report.ok
    assert any("missing absence types" in e for e in report.errors)


def test_duplicate_facet_id_detected(tmp_path: Path) -> None:
    root = _synthetic_vocab(tmp_path)
    (root / "vocab" / "facets" / "parts.csv").write_text(
        "id,name_en,name_pt,name_fr,name_es,name_de,name_it,name_pt_PT,name_pt_BR\n"
        "breast,Breast,Peito,Poitrine,Pechuga,Brust,Petto,Peito,Peito\n"
        "breast,Breast,Peito,Poitrine,Pechuga,Brust,Petto,Peito,Peito\n",
        encoding="utf-8",
    )
    report = check_vocabulary(root)
    assert not report.ok
    assert any("facets/parts id" in e for e in report.errors)


def test_empty_facet_name_detected(tmp_path: Path) -> None:
    root = _synthetic_vocab(tmp_path)
    (root / "vocab" / "facets" / "parts.csv").write_text(
        "id,name_en,name_pt,name_fr,name_es,name_de,name_it,name_pt_PT,name_pt_BR\n"
        "breast,Breast,Peito,,Pechuga,Brust,Petto,Peito,Peito\n",
        encoding="utf-8",
    )
    report = check_vocabulary(root)
    assert not report.ok
    assert any("facets/parts" in e and "empty cell" in e for e in report.errors)


def test_wrong_header_detected(tmp_path: Path) -> None:
    root = _synthetic_vocab(tmp_path)
    (root / "vocab" / "units.csv").write_text("id,name\n", encoding="utf-8")
    report = check_vocabulary(root)
    assert not report.ok
    assert any("header" in e for e in report.errors)


def test_energy_tags_required(tmp_path: Path) -> None:
    rows = NUTRIENTS_OK.replace("ENERC_KCAL,energy,", "FAT,lipids,")
    report = check_vocabulary(_synthetic_vocab(tmp_path, nutrient_rows=rows))
    assert not report.ok
    assert any("ENERC" in e for e in report.errors)
