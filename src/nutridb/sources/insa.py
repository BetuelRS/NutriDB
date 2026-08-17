"""INSA/TCA 7.1 extractor: official XLSX -> shared intermediate contract.

Reads the pinned ``insa_tca.xlsx`` from the cache (ADR-0004; sha256 fixed
in the registry) and writes the four shared contract tables (ADR-0005)
under `build/intermediates/insa/`.

Format (verified against the official file, ADR-0004 §2):
  * sheet "INSA - BDCA_v 7.1 - 2026": row 1 = group header, row 2 = column
    header (Cod | Nome do alimento | Nível 1..3 | 48 components with unit),
    rows 3+ = data (1 376 foods);
  * numbers are stored natively in the XLSX (no text cell for values): the
    "raw" record of a cell is the exact float plus the official column name
    and unit (P1; nothing is invented);
  * empty value cells mean "not measured" (P3 -> value_kind missing; absence
    is materialized by coverage, ADR-0001 D5); zero is a measured zero;
  * values are per 100 g of edible part EXCEPT the FoodEx2 level-1 group
    "Bebidas alcoólicas", per 100 ml -> per-cell basis (ADR-0005 §3.1);
  * sheet "Componentes-Correspondência" lists the official INFOODS/EuroFIR
    codes per component; the extractor validates that every data column
    matches exactly one component (the codes themselves are recorded in
    mappings/nutrients/insa.csv as evidence, P8).

No per-value provenance is published by the source (ADR-0004 §5): records
carry the cell itself, not a citation. The XLSX is parsed with the standard
library (zipfile + xml.etree) — no new dependencies (ADR-0005 §3.4).
"""

from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = ["InsaExtractError", "extract", "extract_report"]

CACHE_FILE = "insa_tca.xlsx"
SHEET_DATA = "INSA - BDCA_v 7.1 - 2026"
SHEET_CORRESPONDENCE = "Componentes-Correspondência"
ALCOHOL_LEVEL1 = "Bebidas alcoólicas"
VALUE_HEADER_COLUMNS = 48
FIRST_VALUE_COLUMN = 5

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DOC_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")
_UNIT_RE = re.compile(r"\[(kcal|kJ|mg|µg|g)\]")
_COL_RE = re.compile(r"^([A-Z]+)\d+$")


class InsaExtractError(Exception):
    """Fail high: anything unexpected in the official dump stops the build."""


def _normalize_name(text: str) -> str:
    """Collapse whitespace (headers and component names carry stray spaces)."""
    return " ".join(text.split())


# Source orthography inconsistency (verified in the official file): the data
# sheet spells alpha-tocopherol with the Greek letter, the correspondence
# sheet spells it out. The correspondence spelling is translated to the data
# spelling (the data sheet is the authority for column identity). Data, not a
# code branch (P8).
_KEY_ALIASES = {"alfa_tocoferol_mg": "a_tocoferol_mg"}


_UNIT_TO_KEY = {"kcal": "kcal", "kJ": "kj", "mg": "mg", "µg": "ug", "g": "g"}


def _normalize_key(text: str) -> str:
    """Text -> stable ASCII key (NFKD, lowercase, non-alphanumerics -> '_')."""
    transliterated = text.replace("\u03b1", "a").replace("\u03b2", "b")
    decomposed = unicodedata.normalize("NFKD", transliterated)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", stripped.casefold()).strip("_")


def _nutrient_key(text: str) -> str:
    """Stable key of a component column: ``<name>_<canonical_unit>``.

    The unit is part of the identity (Energia exists per kcal and per kJ) and
    is appended canonically — the raw header spells it ``[µg]`` while other
    columns say ``[g]``; naively normalizing would collapse them (P9).
    """
    unit_match = _UNIT_RE.search(text)
    if unit_match is None:
        raise InsaExtractError(f"component name without unit: {text!r}")
    unit = _UNIT_TO_KEY[unit_match.group(1)]
    key = _normalize_key(text[: unit_match.start()])
    if not key:
        raise InsaExtractError(f"empty normalized key for {text!r}")
    return f"{key}_{unit}"


def _col_index(ref: str) -> int | None:
    """Excel column index of a cell ref like ``"F3"`` (A=0)."""
    match = _COL_RE.match(ref)
    if match is None:
        return None
    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _sheet_targets(path: Path) -> dict[str, str]:
    """Map sheet name -> zip entry path via workbook rels."""
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels
        if rel.tag == f"{_PACKAGE_REL_NS}Relationship"
    }
    sheets: dict[str, str] = {}
    for sheet in workbook.iter(f"{_NS}sheet"):
        name = sheet.attrib["name"]
        target = rid_to_target[sheet.attrib[f"{_DOC_REL_NS}id"]]
        if not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        sheets[name] = target
    return sheets


def _shared_strings(archive: zipfile.ZipFile, entry: str) -> list[str]:
    root = ET.fromstring(archive.read(entry))
    out: list[str] = []
    for item in root.iter(f"{_NS}si"):
        out.append("".join(t.text or "" for t in item.iter(f"{_NS}t")))
    return out


def _cell_value(cell: ET.Element, shared: list[str]) -> str | None:
    """Text of one cell (shared/inline string or numeric); None when empty."""
    kind = cell.attrib.get("t")
    value_node = cell.find(f"{_NS}v")
    if kind == "s":
        if value_node is None or value_node.text is None:
            return None
        return shared[int(value_node.text)]
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{_NS}t"))
    if kind == "b":
        raise InsaExtractError(f"cell {cell.attrib.get('r', '?')}: unexpected boolean cell")
    return value_node.text if value_node is not None else None


def _sheet_rows(archive: zipfile.ZipFile, entry: str, shared: list[str]) -> list[dict[int, str]]:
    """Rows of one sheet as {column_index: text}, file order."""
    root = ET.fromstring(archive.read(entry))
    rows: list[dict[int, str]] = []
    for row in root.iter(f"{_NS}row"):
        cells: dict[int, str] = {}
        for cell in row:
            index = _col_index(cell.attrib.get("r", ""))
            if index is None:
                raise InsaExtractError(f"unreadable cell ref {cell.attrib.get('r', '?')!r}")
            value = _cell_value(cell, shared)
            if value is not None:
                cells[index] = value
        rows.append(cells)
    return rows


def _find_header_row(rows: list[dict[int, str]]) -> int:
    """The row with the official column headers (Cod, Nome do alimento)."""
    for index, row in enumerate(rows):
        if _normalize_name(row.get(0, "")) == "Cod" and _normalize_name(row.get(1, "")) == (
            "Nome do alimento"
        ):
            return index
    raise InsaExtractError("column header row (Cod | Nome do alimento) not found")


def _parse_value_cell(raw: str | None, where: str) -> tuple[float | None, str]:
    """XLSX value cells are native numbers; empty means not measured (P3)."""
    if raw is None or not raw.strip():
        return None, "missing"
    if _NUMBER_RE.match(raw):
        return float(raw), "number"
    raise InsaExtractError(f"{where}: unexpected value cell {raw!r}")


def _headers(header_row: dict[int, str]) -> list[tuple[str, str, str]]:
    """Value columns as (key, official_name, unit); fail high on surprises."""
    columns: list[tuple[str, str, str]] = []
    for index in range(FIRST_VALUE_COLUMN, FIRST_VALUE_COLUMN + VALUE_HEADER_COLUMNS):
        name = header_row.get(index, "")
        key = _nutrient_key(name)
        unit_match = _UNIT_RE.search(name)
        if unit_match is None:
            raise InsaExtractError(f"column {index}: missing unit bracket in header {name!r}")
        unit = _UNIT_TO_KEY[unit_match.group(1)]
        columns.append((key, name, unit))
    return columns


def _component_keys(rows: list[dict[int, str]]) -> set[str]:
    """Nutrient keys of the correspondence-sheet component names."""
    keys: set[str] = set()
    for row in rows:
        name = _normalize_name(row.get(0, ""))
        if not name or name.casefold().startswith("componentes"):
            continue  # sheet header row ("Componentes [Unidades]")
        if re.match(r"^\d+\s", name) or name == "NaN":
            continue  # numbered legend rows and empty-cell placeholders
        keys.add(_KEY_ALIASES.get(_nutrient_key(name), _nutrient_key(name)))
    return keys


def _frame(columns: dict[str, type], rows: Sequence[tuple[object, ...]]) -> pl.DataFrame:
    data = {name: [row[index] for row in rows] for index, name in enumerate(columns)}
    return pl.DataFrame(data, schema=columns)


def extract(cache_dir: Path, out_dir: Path) -> dict[str, int]:
    """Parse the official XLSX and write the shared intermediate contract."""
    source = cache_dir / CACHE_FILE
    if not source.is_file():
        raise InsaExtractError(
            f"cache missing {CACHE_FILE}; run `uv run nutridb sources sync` first"
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = _sheet_targets(source)
    if SHEET_DATA not in targets:
        raise InsaExtractError(f"sheet {SHEET_DATA!r} not found in the workbook")
    if SHEET_CORRESPONDENCE not in targets:
        raise InsaExtractError(f"sheet {SHEET_CORRESPONDENCE!r} not found in the workbook")

    with zipfile.ZipFile(source) as archive:
        shared = _shared_strings(archive, "xl/sharedStrings.xml")
        data_rows = _sheet_rows(archive, targets[SHEET_DATA], shared)
        correspondence_rows = _sheet_rows(archive, targets[SHEET_CORRESPONDENCE], shared)

    header_index = _find_header_row(data_rows)
    header_row = data_rows[header_index]
    columns = _headers(header_row)
    data = data_rows[header_index + 1 :]

    components = _component_keys(correspondence_rows)
    header_keys = {
        _nutrient_key(header_row.get(index, ""))
        for index in range(FIRST_VALUE_COLUMN, FIRST_VALUE_COLUMN + VALUE_HEADER_COLUMNS)
    }
    missing_components = header_keys - components
    if missing_components:
        raise InsaExtractError(
            f"{len(missing_components)} value columns without a correspondence row: "
            f"{sorted(missing_components)}"
        )

    foods: list[tuple[str, str, str, str, str]] = []
    values: list[tuple[str, str, float | None, str, str, str]] = []
    seen_foods: set[str] = set()
    for row in data:
        cod = row.get(0)
        if cod is None or not cod.strip():
            continue  # trailing empty rows
        cod = cod.strip()
        if cod in seen_foods:
            raise InsaExtractError(f"duplicate food code {cod!r}")
        seen_foods.add(cod)
        name = _normalize_name(row.get(1, ""))
        if not name:
            raise InsaExtractError(f"food {cod}: missing name")
        levels = {
            level: _normalize_name(row.get(index, ""))
            for level, index in (("1", 2), ("2", 3), ("3", 4))
            if row.get(index) is not None
        }
        basis = "per_100ml" if levels.get("1") == ALCOHOL_LEVEL1 else "per_100g_edible"
        foods.append(
            (
                cod,
                name,
                json.dumps({"pt": name}, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                json.dumps(levels, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                json.dumps(
                    {
                        "names": {"pt": name},
                        "raw": {
                            "cod": cod,
                            **{f"nivel_{level}": value for level, value in levels.items()},
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
        for index, (key, official_name, unit) in enumerate(columns):
            cell_index = FIRST_VALUE_COLUMN + index
            raw = row.get(cell_index)
            value, value_kind = _parse_value_cell(raw, f"food {cod} {key}")
            values.append(
                (
                    cod,
                    key,
                    value,
                    value_kind,
                    basis,
                    json.dumps(
                        {"cod": cod, "nutrient": official_name, "unit": unit, "value": value},
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )

    _frame(
        {
            "food_code": pl.Utf8,
            "name": pl.Utf8,
            "names": pl.Utf8,
            "group_path": pl.Utf8,
            "record": pl.Utf8,
        },
        sorted(foods, key=lambda row: str(row[0])),
    ).write_parquet(out_dir / "food.parquet")
    groups: list[tuple[str, str, str]] = []
    for food_row in foods:
        for level, group in json.loads(food_row[3]).items():
            groups.append((level, group, group))
    _frame(
        {"level": pl.Utf8, "code": pl.Utf8, "name": pl.Utf8},
        sorted(set(groups), key=lambda row: (row[0], row[1])),
    ).write_parquet(out_dir / "food_group.parquet")
    _frame(
        {"nutrient_code": pl.Utf8, "name": pl.Utf8, "unit": pl.Utf8},
        sorted(((key, name, unit) for key, name, unit in columns), key=lambda row: str(row[0])),
    ).write_parquet(out_dir / "constituent.parquet")
    _frame(
        {
            "food_code": pl.Utf8,
            "nutrient_code": pl.Utf8,
            "value": pl.Float64,
            "value_kind": pl.Utf8,
            "threshold": pl.Float64,
            "min_value": pl.Float64,
            "max_value": pl.Float64,
            "confidence_code": pl.Utf8,
            "basis": pl.Utf8,
            "record": pl.Utf8,
        },
        sorted(
            ((*row[:4], None, None, None, None, *row[4:]) for row in values),
            key=lambda row: (row[0], row[1]),
        ),
    ).write_parquet(out_dir / "value.parquet")

    return extract_report(len(foods), len(columns), len(values))


def extract_report(foods: int, constituents: int, values: int) -> dict[str, int]:
    return {"foods": foods, "constituents": constituents, "values": values}
