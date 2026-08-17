"""CIQUAL 2025 extractor: official XML set -> common intermediate contract.

Reads the five pinned XML files from the cache (ADR-0003), validates every
cell (fail high, P9) and writes the four shared contract tables (ADR-0005)
under `build/intermediates/ciqual/`:

    food            food_code, name, names {locale: text}, group_path
                    {"1"|"2"|"3": code}, record (raw JSON with names + raw)
    food_group      level "1"|"2"|"3", code, name
    constituent     nutrient_code, name, unit (parsed from the official name)
    value           typed cells (number|missing|trace|below_loq), basis,
                    raw cell JSON verbatim (P1)

The old per-source `sources.parquet` (1978 citations) is no longer an
intermediate: value rows keep the numeric `source_code` in their raw JSON
and the citations stay in the cached XML as evidence.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

__all__ = ["CiqualExtractError", "extract", "extract_report"]

_NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?$")
_BELOW_LOQ_RE = re.compile(r"^<\s*(\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?)$")
_UNIT_RE = re.compile(r"\((kcal|kJ|mg|µg|g)/100 (?:g|ml)\)")

_LEVELS = ("grp", "ssgrp", "ssssgrp")
_LEVEL_IDS = {"grp": "1", "ssgrp": "2", "ssssgrp": "3"}

CACHE_FILES = (
    "alim_2025_11_03.xml",
    "alim_grp_2025_11_03.xml",
    "compo_2025_11_03.xml",
    "const_2025_11_03.xml",
    "sources_2025_11_03.xml",
)


class CiqualExtractError(Exception):
    """Fail high: anything unexpected in the official dump stops the build."""


def _text(element: ET.Element) -> str | None:
    """Element text, stripped; None for empty/missing cells."""
    value = (element.text or "").strip()
    return value or None


def _iter_records(path: Path, tag: str) -> Iterator[dict[str, str | None]]:
    """Yield one dict per element with the given tag, releasing memory (P5)."""
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag != tag:
            continue
        record = {child.tag: _text(child) for child in elem}
        elem.clear()
        yield record


def _parse_cell(raw: str, where: str) -> tuple[float | None, str]:
    """Classify a teneur cell: number | missing | trace | below_loq (P3).

    The CIQUAL schema (doc 5.5) allows numbers, 'traces' and '-' here; '<N'
    is permitted by the schema and handled defensively. Anything else fails
    the build — no silent cell is ever dropped (P9).
    """
    if _NUMBER_RE.match(raw):
        return float(raw.replace(",", ".")), "number"
    if raw == "-":
        return None, "missing"
    if raw == "traces":
        return None, "trace"
    if match := _BELOW_LOQ_RE.match(raw):
        return float(match.group(1).replace(",", ".")), "below_loq"
    raise CiqualExtractError(f"{where}: unexpected teneur cell {raw!r}")


def _parse_pair(raw: str | None, where: str) -> float | None:
    """Parse a min/max cell: numeric only; empty cells are None."""
    if raw is None or _NUMBER_RE.match(raw):
        return float(raw.replace(",", ".")) if raw else None
    raise CiqualExtractError(f"{where}: unexpected min/max cell {raw!r}")


def _frame(columns: Mapping[str, type], rows: Sequence[tuple[object, ...]]) -> pl.DataFrame:
    """Build a DataFrame with an explicit, deterministic schema."""
    schema = {name: dtype for name, dtype in columns.items()}
    data = {name: [row[index] for row in rows] for index, name in enumerate(columns)}
    return pl.DataFrame(data, schema=schema)


def parse_aliments(
    path: Path,
) -> list[tuple[str, str, str, str | None, str, str, str, float | None]]:
    rows: list[tuple[str, str, str, str | None, str, str, str, float | None]] = []
    seen: set[int] = set()
    for rec in _iter_records(path, "ALIM"):
        code = _int(rec["alim_code"], "alim_code")
        if code in seen:
            raise CiqualExtractError(f"alim: duplicate alim_code {code}")
        seen.add(code)
        factor = rec["facteur_Jones"]
        if factor is not None and not _NUMBER_RE.match(factor):
            raise CiqualExtractError(f"alim {code}: unexpected facteur_Jones {factor!r}")
        rows.append(
            (
                str(code),
                _required(rec["alim_nom_fr"], f"alim {code}"),
                _required(rec["alim_nom_eng"], f"alim {code}"),
                rec["alim_nom_sci"],
                _required(rec["alim_grp_code"], f"alim {code}"),
                _required(rec["alim_ssgrp_code"], f"alim {code}"),
                _required(rec["alim_ssssgrp_code"], f"alim {code}"),
                float(factor.replace(",", ".")) if factor else None,
            )
        )
    return rows


def _is_placeholder(code: str | None) -> bool:
    """CIQUAL fills missing group levels with all-zero codes ('00'/'0000'/'000000')."""
    return code is not None and set(code) == {"0"}


def parse_groups(path: Path) -> list[tuple[str, str, str]]:
    """Parse alim_grp: one leaf row per ssssgrp with all levels denormalised.

    The official dump emits every row with all three levels filled; missing
    lower levels use all-zero placeholder codes and name '-'. Emit one record
    per (level, code) actually present, preserving the official order; a
    repeated (level, code) is only valid if names agree (fail high otherwise).
    """
    rows: list[tuple[str, str, str]] = []
    seen: dict[tuple[str, str], str] = {}
    for rec in _iter_records(path, "ALIM_GRP"):
        for level in _LEVELS:
            code = rec.get(f"alim_{level}_code")
            if code is None or _is_placeholder(code):
                continue
            name = _required(rec[f"alim_{level}_nom_fr"], f"group {code}")
            previous = seen.get((level, code))
            if previous is not None:
                if previous != name:
                    raise CiqualExtractError(f"alim_grp: conflicting names for {(level, code)}")
                continue
            seen[(level, code)] = name
            rows.append((_LEVEL_IDS[level], code, name))
    return rows


def parse_constituents(path: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    seen: set[int] = set()
    for rec in _iter_records(path, "CONST"):
        code = _int(rec["const_code"], "const_code")
        if code in seen:
            raise CiqualExtractError(f"const: duplicate const_code {code}")
        seen.add(code)
        name = _required(rec["const_nom_fr"], f"const {code}")
        unit = _parse_unit(name, f"const {code}")
        rows.append((str(code), name, unit))
    return rows


def _parse_unit(name: str, where: str) -> str:
    """Extract the official unit from the constituent name, e.g. '(mg/100 g)'."""
    match = _UNIT_RE.search(name)
    if match is None:
        raise CiqualExtractError(f"{where}: no unit in official name {name!r}")
    return {"kcal": "kcal", "kJ": "kj", "mg": "mg", "µg": "ug", "g": "g"}[match.group(1)]


def parse_sources(path: Path) -> list[tuple[int, str | None]]:
    rows: list[tuple[int, str | None]] = []
    seen: set[int] = set()
    for rec in _iter_records(path, "SOURCES"):
        code = _int(rec["source_code"], "source_code")
        if code in seen:
            raise CiqualExtractError(f"sources: duplicate source_code {code}")
        seen.add(code)
        rows.append((code, rec["ref_citation"]))
    return rows


def parse_compo(
    path: Path,
) -> list[
    tuple[
        str,
        str,
        float | None,
        str,
        float | None,
        float | None,
        float | None,
        str | None,
        int | None,
        str,
    ]
]:
    rows: list[
        tuple[
            str,
            str,
            float | None,
            str,
            float | None,
            float | None,
            float | None,
            str | None,
            int | None,
            str,
        ]
    ] = []
    seen: set[tuple[int, int]] = set()
    for rec in _iter_records(path, "COMPO"):
        alim_code = _int(rec["alim_code"], "compo.alim_code")
        const_code = _int(rec["const_code"], "compo.const_code")
        pair = (alim_code, const_code)
        if pair in seen:
            raise CiqualExtractError(f"compo: duplicate pair {pair}")
        seen.add(pair)

        teneur_raw = _required(rec["teneur"], f"compo {pair}")
        teneur_value, teneur_kind = _parse_cell(teneur_raw, f"compo {pair}")
        min_value = _parse_pair(rec["min"], f"compo {pair}")
        max_value = _parse_pair(rec["max"], f"compo {pair}")
        confidence = rec.get("code_confiance")
        if confidence is not None and confidence not in ("A", "B", "C", "D"):
            raise CiqualExtractError(f"compo {pair}: unexpected code_confiance {confidence!r}")
        source_code = rec.get("source_code")
        rows.append(
            (
                str(alim_code),
                str(const_code),
                teneur_value if teneur_kind == "number" else None,
                teneur_kind,
                teneur_value if teneur_kind == "below_loq" else None,
                min_value,
                max_value,
                confidence,
                _int(source_code, f"compo {pair}.source_code") if source_code else None,
                json.dumps(rec, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
        )
    return rows


def _int(raw: str | None, where: str) -> int:
    if raw is None:
        raise CiqualExtractError(f"{where}: missing integer cell")
    return int(raw)


def _required(raw: str | None, where: str) -> str:
    if raw is None:
        raise CiqualExtractError(f"{where}: missing required cell")
    return raw


def _ensure_cache(cache_dir: Path) -> dict[str, Path]:
    present = {path.name for path in cache_dir.iterdir() if path.is_file()}
    missing = [name for name in CACHE_FILES if name not in present]
    if missing:
        raise CiqualExtractError(
            f"cache missing {missing}; run `uv run nutridb sources sync` first"
        )
    return {name: cache_dir / name for name in CACHE_FILES}


def _json_safe(value: object) -> object:
    """Replace non-finite floats (NaN/inf from the source) with JSON null."""
    if isinstance(value, float) and not (
        value == value and value not in (float("inf"), float("-inf"))
    ):
        return None
    return value


def extract(cache_dir: Path, out_dir: Path) -> dict[str, int]:
    """Parse the five XML files and write the shared intermediate contract.

    Returns a report of counts (fail high on any inconsistency).
    """
    files = _ensure_cache(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    groups = parse_groups(files["alim_grp_2025_11_03.xml"])
    group_codes = {code for _, code, _ in groups}
    aliments = parse_aliments(files["alim_2025_11_03.xml"])
    for code, *_rest, grp, ssgrp, sssgrp, _ in aliments:
        for gcode in (grp, ssgrp, sssgrp):
            if _is_placeholder(gcode):
                continue
            if gcode not in group_codes:
                raise CiqualExtractError(f"alim {code}: group code {gcode!r} not in alim_grp")

    constituents = parse_constituents(files["const_2025_11_03.xml"])
    sources = parse_sources(files["sources_2025_11_03.xml"])
    values = parse_compo(files["compo_2025_11_03.xml"])

    alim_codes = {int(code) for code, *_ in aliments}
    const_codes = {int(code) for code, *_ in constituents}
    source_codes = {code for code, _ in sources}
    for value_row in values:
        alim_code = value_row[0]
        const_code = value_row[1]
        source_code_found = value_row[8]
        if int(alim_code) not in alim_codes:
            raise CiqualExtractError(f"compo: orphan alim_code {alim_code}")
        if int(const_code) not in const_codes:
            raise CiqualExtractError(f"compo: orphan const_code {const_code}")
        if source_code_found is not None and source_code_found not in source_codes:
            raise CiqualExtractError(f"compo: unknown source_code {source_code_found}")

    food_rows: list[tuple[str, str, str, str, str]] = []
    for code, nom_fr, nom_eng, nom_sci, grp, ssgrp, ssssgrp, factor in aliments:
        food_rows.append(
            (
                code,
                nom_fr,
                json.dumps(
                    {"fr": nom_fr, "en": nom_eng},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                json.dumps(
                    {"1": grp, "2": ssgrp, "3": ssssgrp},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                json.dumps(
                    {
                        "names": {"fr": nom_fr, "en": nom_eng},
                        "raw": {
                            "alim_code": code,
                            "alim_nom_fr": nom_fr,
                            "alim_nom_eng": nom_eng,
                            "alim_nom_sci": _json_safe(nom_sci),
                            "facteur_jones": _json_safe(factor),
                            "alim_grp_code": grp,
                            "alim_ssgrp_code": ssgrp,
                            "alim_ssssgrp_code": ssssgrp,
                        },
                    },
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
        food_rows,
    ).write_parquet(out_dir / "food.parquet")
    _frame(
        {"level": pl.Utf8, "code": pl.Utf8, "name": pl.Utf8},
        groups,
    ).write_parquet(out_dir / "food_group.parquet")
    _frame(
        {"nutrient_code": pl.Utf8, "name": pl.Utf8, "unit": pl.Utf8},
        constituents,
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
        [
            (*row[:8], "per_100g_edible", row[9])
            for row in values  # CIQUAL 2025: todas as células por 100 g (verificado const XML);
            # source_code (índice 8) fica preservado no record JSON, não é coluna do contrato
        ],
    ).write_parquet(out_dir / "value.parquet")

    return extract_report(aliments, constituents, groups, sources, values)


def extract_report(
    aliments: Sequence[object],
    constituents: Sequence[object],
    groups: Sequence[object],
    sources: Sequence[object],
    values: Sequence[object],
) -> dict[str, int]:
    """Report counts for the extraction (0 cells silently dropped by design)."""
    return {
        "foods": len(aliments),
        "constituents": len(constituents),
        "groups": len(groups),
        "sources": len(sources),
        "values": len(values),
    }
