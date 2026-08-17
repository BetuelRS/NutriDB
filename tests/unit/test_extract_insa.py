"""INSA/TCA extractor unit tests against a synthetic workbook (F2, ADR-0005).

The XLSX is generated at test time with the standard library (zipfile +
xml.etree) mirroring the official layout verified in ADR-0004 §2: data sheet
"INSA - BDCA_v 7.1 - 2026" (row 1 group header, row 2 column header, rows 3+
foods) and correspondence sheet "Componentes-Correspondência". All numbers
are SYNTHETIC (SPEC §17.7); the structure, header names and orthography
quirk (data sheet writes alpha-tocopherol with the Greek letter, the
correspondence spells it out) are the real ones.
"""

from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

import polars as pl
import pytest

from nutridb.sources.insa import InsaExtractError, extract

if TYPE_CHECKING:
    from pathlib import Path

# Value column headers, verbatim from the official workbook (ADR-0004 §2):
# the data sheet spells alpha-tocopherol as "\u03b1-tocoferol", the
# correspondence sheet as "Alfa-tocoferol" — the extractor maps via
# _KEY_ALIASES (the data sheet is the authority).
HEADERS = [
    "Energia\n[kcal] ",
    "Energia\n[kJ] ",
    "Lípidos\n[g]",
    "Ácidos gordos saturados\n[g] ",
    "Ácidos gordos monoinsaturados \n[g]",
    "Ácidos gordos polinsaturados \n[g]",
    "Ácido linoleico \n[g] ",
    "Ácidos gordos trans \n[g]",
    "Hidratos de carbono \n[g]",
    "Açúcares \n[g] ",
    "Oligossacáridos \n[g] ",
    "Amido \n[g]",
    "Sal  \n[g]",
    "Fibra  \n[g]",
    "Proteínas \n[g] ",
    "Álcool \n[g] ",
    "Água \n[g] ",
    "Ácidos orgânicos \n[g] ",
    "Colesterol \n[mg]",
    "Vitamina A  \n[µg]",
    "Equivalentes de β-caroteno \n[µg]",
    "\u03b1-caroteno\n[\u00b5g]",
    "β-caroteno, total\n[µg]",
    "β-criptoxantina\n[µg]",
    "Licopeno\n[µg]",
    "Luteína\n[µg]",
    "Zeaxantina\n[µg]",
    "Vitamina D \n[µg]",
    "\u03b1-tocoferol \n[mg]",
    "Tiamina \n[mg] ",
    "Riboflavina \n[mg] ",
    "Niacina \n[mg]",
    "Equivalentes de niacina \n[mg]",
    "Triptofano/60 \n[mg]",
    "Vitamina B6 \n[mg]",
    "Vitamina B12 \n[µg]",
    "Vitamina C \n[mg]",
    "Folatos \n[µg]",
    "Cinza \n[g]",
    "Sódio \n[mg]",
    "Potássio \n[mg] ",
    "Cálcio \n[mg]",
    "Fósforo \n[mg]",
    "Magnésio \n[mg]",
    "Ferro \n[mg]",
    "Zinco \n[mg]",
    "Selénio \n[µg]",
    "Iodo \n[µg]",
]

# Correspondence-sheet component names (units column in col 1), with the
# real legend/placeholder rows the official sheet carries.
CORRESPONDENCE = [
    "Componentes [Unidades]",
    "1 Energia [kcal]",
    "2 Energia [kJ]",
    "Energia [kcal]",
    "Energia [kJ]",
    "Lípidos [g]",
    "Ácidos gordos saturados [g]",
    "Ácidos gordos monoinsaturados [g]",
    "Ácidos gordos polinsaturados [g]",
    "Ácido linoleico [g]",
    "Ácidos gordos trans [g]",
    "Hidratos de carbono [g]",
    "Açúcares [g]",
    "Oligossacáridos [g]",
    "Amido [g]",
    "Sal [g]",
    "Fibra [g]",
    "Proteínas [g]",
    "Álcool [g]",
    "Água [g]",
    "Ácidos orgânicos [g]",
    "Colesterol [mg]",
    "Vitamina A [µg]",
    "Equivalentes de β-caroteno [µg]",
    "\u03b1-caroteno [\u00b5g]",
    "β-caroteno, total [µg]",
    "β-criptoxantina [µg]",
    "Licopeno [µg]",
    "Luteína [µg]",
    "Zeaxantina [µg]",
    "Vitamina D [µg]",
    "Alfa-tocoferol [mg]",
    "Tiamina [mg]",
    "Riboflavina [mg]",
    "Niacina [mg]",
    "Equivalentes de niacina [mg]",
    "Triptofano/60 [mg]",
    "Vitamina B6 [mg]",
    "Vitamina B12 [µg]",
    "Vitamina C [mg]",
    "Folatos [µg]",
    "Cinza [g]",
    "Sódio [mg]",
    "Potássio [mg]",
    "Cálcio [mg]",
    "Fósforo [mg]",
    "Magnésio [mg]",
    "Ferro [mg]",
    "Zinco [mg]",
    "Selénio [µg]",
    "Iodo [µg]",
    "NaN",
]

# (food_code, name, nivel_1, nivel_2, nivel_3, [value or None x48])
FOOD_100_VALUES: list[str | None] = [None] * 48
FOOD_100_VALUES[0] = "176"  # energia_kcal
FOOD_100_VALUES[1] = "734"  # energia_kj
FOOD_100_VALUES[2] = "8.9"  # lipidos
FOOD_100_VALUES[7] = "0.4"  # acidos gordos trans
FOOD_100_VALUES[9] = "1.2"  # acucares
FOOD_100_VALUES[14] = "2.4"  # proteinas
FOOD_100_VALUES[16] = "77.5"  # agua
FOOD_100_VALUES[18] = "0"  # colesterol (zero real)
FOOD_100_VALUES[28] = "0.2"  # a_tocoferol

FOOD_200_VALUES: list[str | None] = [None] * 48
FOOD_200_VALUES[0] = "70.0"  # energia_kcal
FOOD_200_VALUES[15] = "9.0"  # alcool
FOOD_200_VALUES[9] = "0.1"  # acucares
FOOD_200_VALUES[16] = "88.5"  # agua

FOODS = [
    (
        "100",
        "Batata frita",
        "Raízes, tubérculos, bolbos e derivados",
        "Batata",
        "Batata frita",
        FOOD_100_VALUES,
    ),
    ("200", "Vinho tinto", "Bebidas alcoólicas", "Vinho", "Vinho tinto", FOOD_200_VALUES),
]


def _col_ref(col: int, row: int) -> str:
    out = ""
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return f"{out}{row}"


def _write_xlsx(path: Path, data_rows: list[list[str | None]], correspondence: list[str]) -> None:
    """Minimal OOXML workbook: two sheets, shared strings, native numbers."""
    shared: list[str] = []
    index_of: dict[str, int] = {}

    def shared_index(text: str) -> int:
        if text not in index_of:
            index_of[text] = len(shared)
            shared.append(text)
        return index_of[text]

    def sheet_xml(rows: list[list[str | None]], row_offset: int) -> str:
        row_xml: list[str] = []
        for r, row in enumerate(rows, start=row_offset):
            cells: list[str] = []
            for c, value in enumerate(row):
                if value is None:
                    continue
                ref = _col_ref(c, r)
                if value.isdigit() or value.replace(".", "", 1).isdigit():
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="s"><v>{shared_index(value)}</v></c>')
            row_xml.append(f"<row>{''.join(cells)}</row>")
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(row_xml)}</sheetData>"
            "</worksheet>"
        )

    group_header = ["", "", "Grupo 1", "Grupo 2", "Grupo 3"] + [None] * 48
    column_header: list[str | None] = [
        "Cod",
        "Nome do alimento",
        "Nível 1 ",
        "Nível 2",
        "Nível 3 ",
        *HEADERS,
    ]
    data_sheet = sheet_xml([group_header, column_header, *data_rows], 1)
    correspondence_xml = "".join(
        f'<row><c r="A{r}" t="s"><v>{shared_index(name)}</v></c></row>'
        for r, name in enumerate(correspondence, start=1)
    )
    corr_sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{correspondence_xml}</sheetData></worksheet>"
    )
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{escape(text)}</t></si>" for text in shared)
        + "</sst>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="INSA - BDCA_v 7.1 - 2026" sheetId="1" r:id="rId1"/>'
        '<sheet name="Componentes-Correspondência" sheetId="2" r:id="rId2"/>'
        "</sheets></workbook>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", data_sheet)
        archive.writestr("xl/worksheets/sheet2.xml", corr_sheet)
        archive.writestr("xl/sharedStrings.xml", shared_xml)


def _food_rows() -> list[list[str | None]]:
    return [[*row[:5], *row[5]] for row in FOODS]


@pytest.fixture()
def cache(tmp_path: Path) -> Path:
    out = tmp_path / "cache"
    out.mkdir()
    _write_xlsx(out / "insa_tca.xlsx", _food_rows(), CORRESPONDENCE)
    return out


def _read(path: Path, name: str) -> pl.DataFrame:
    return pl.read_parquet(path / f"{name}.parquet")


def test_insa_extract_report_and_contract(cache: Path, tmp_path: Path) -> None:
    report = extract(cache, tmp_path / "out")
    assert report == {"foods": 2, "constituents": 48, "values": 96}
    out = tmp_path / "out"
    for table in ("food", "food_group", "constituent", "value"):
        assert (out / f"{table}.parquet").is_file()

    value_columns = [
        "food_code",
        "nutrient_code",
        "value",
        "value_kind",
        "threshold",
        "min_value",
        "max_value",
        "confidence_code",
        "basis",
        "record",
    ]
    assert _read(out, "value").columns == value_columns
    assert _read(out, "food").columns == ["food_code", "name", "names", "group_path", "record"]
    assert _read(out, "food_group").columns == ["level", "code", "name"]
    assert _read(out, "constituent").columns == ["nutrient_code", "name", "unit"]


def test_insa_values_typed_and_basis(cache: Path, tmp_path: Path) -> None:
    extract(cache, tmp_path / "out")
    values = _read(tmp_path / "out", "value")
    assert values.height == 96
    filled = sum(1 for row in FOODS for cell in row[5] if cell is not None)
    assert values.null_count()["value"].item() == 96 - filled

    potato = values.filter(pl.col("food_code") == "100")
    assert potato.filter(pl.col("nutrient_code") == "energia_kcal").row(0)[2] == 176.0
    assert potato.filter(pl.col("nutrient_code") == "colesterol_mg").row(0)[2] == 0.0
    assert potato.filter(pl.col("nutrient_code") == "acidos_gordos_trans_g").row(0)[2] == 0.4
    assert potato.filter(pl.col("nutrient_code") == "vitamina_b12_ug").row(0)[3] == "missing"
    assert potato["basis"].unique().to_list() == ["per_100g_edible"]

    wine = values.filter(pl.col("food_code") == "200")
    assert wine["basis"].unique().to_list() == ["per_100ml"]
    raw = json.loads(wine.filter(pl.col("nutrient_code") == "energia_kcal").row(0)[9])
    assert raw == {"cod": "200", "nutrient": "Energia\n[kcal] ", "unit": "kcal", "value": 70.0}


def test_insa_foods_and_groups(cache: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    extract(cache, out)
    foods = _read(out, "food")
    assert foods["name"].to_list() == ["Batata frita", "Vinho tinto"]
    potato = foods.filter(pl.col("food_code") == "100").row(0, named=True)
    assert json.loads(potato["names"]) == {"pt": "Batata frita"}
    assert json.loads(potato["group_path"]) == {
        "1": "Raízes, tubérculos, bolbos e derivados",
        "2": "Batata",
        "3": "Batata frita",
    }
    assert json.loads(potato["record"]) == {
        "names": {"pt": "Batata frita"},
        "raw": {
            "cod": "100",
            "nivel_1": "Raízes, tubérculos, bolbos e derivados",
            "nivel_2": "Batata",
            "nivel_3": "Batata frita",
        },
    }
    groups = _read(out, "food_group")
    assert groups.height == 6  # 2 foods x 3 levels
    assert groups.filter(pl.col("level") == "1")["code"].to_list() == [
        "Bebidas alcoólicas",
        "Raízes, tubérculos, bolbos e derivados",
    ]


def test_insa_constituents_units_and_alias(cache: Path, tmp_path: Path) -> None:
    extract(cache, tmp_path / "out")
    constituents = _read(tmp_path / "out", "constituent")
    assert constituents.height == 48
    by_code = {r["nutrient_code"]: r["unit"] for r in constituents.rows(named=True)}
    assert by_code["energia_kcal"] == "kcal"
    assert by_code["energia_kj"] == "kj"
    assert by_code["acidos_gordos_trans_g"] == "g"
    assert by_code["vitamina_a_ug"] == "ug"
    assert by_code["a_tocoferol_mg"] == "mg"  # alias: Alfa-tocoferol -> a_tocoferol
    assert by_code["equivalentes_de_b_caroteno_ug"] == "ug"


def test_insa_duplicate_food_code_fails_high(cache: Path, tmp_path: Path) -> None:
    rows = [*_food_rows(), [x for x in _food_rows()[0]]]
    _write_xlsx(cache / "insa_tca.xlsx", rows, CORRESPONDENCE)
    with pytest.raises(InsaExtractError, match="duplicate food code"):
        extract(cache, tmp_path / "out")


def test_insa_missing_correspondence_component_fails_high(cache: Path, tmp_path: Path) -> None:
    _write_xlsx(cache / "insa_tca.xlsx", _food_rows(), CORRESPONDENCE[:-2])
    with pytest.raises(InsaExtractError, match="without a correspondence row"):
        extract(cache, tmp_path / "out")


def test_insa_non_numeric_value_fails_high(cache: Path, tmp_path: Path) -> None:
    bad = _food_rows()
    bad[0][5] = "muitas"
    _write_xlsx(cache / "insa_tca.xlsx", bad, CORRESPONDENCE)
    with pytest.raises(InsaExtractError, match="unexpected value cell"):
        extract(cache, tmp_path / "out")


def test_insa_missing_cache_file_fails_high(tmp_path: Path) -> None:
    with pytest.raises(InsaExtractError, match="cache missing"):
        extract(tmp_path / "nope", tmp_path / "out")
