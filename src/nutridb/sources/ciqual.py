"""CIQUAL 2025 extractor: official XML set -> canonical Parquet intermediates.

Reads the five pinned XML files from the cache (ADR-0003), validates every
cell (fail high, P9) and writes deterministic Parquet files under
`build/intermediates/ciqual/`. Raw source cells are preserved verbatim;
typing to value_type happens in the transform stage (F1.4).
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

_LEVELS = ("grp", "ssgrp", "ssssgrp")

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


def _frame(columns: Mapping[str, type], rows: list[tuple[object, ...]]) -> pl.DataFrame:
    """Build a DataFrame with an explicit, deterministic schema."""
    schema = {name: dtype for name, dtype in columns.items()}
    data = {name: [row[index] for row in rows] for index, name in enumerate(columns)}
    return pl.DataFrame(data, schema=schema)


def parse_aliments(
    path: Path,
) -> list[tuple[int, str, str, str | None, str, str, str, float | None]]:
    rows: list[tuple[int, str, str, str | None, str, str, str, float | None]] = []
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
                code,
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


def parse_groups(path: Path) -> list[tuple[str, str, str, str]]:
    """Parse alim_grp: one leaf row per ssssgrp with all levels denormalised.

    The official dump emits every row with all three levels filled; missing
    lower levels use all-zero placeholder codes and name '-'. Emit one record
    per (level, code) actually present, preserving the official order; a
    repeated (level, code) is only valid if names agree (fail high otherwise).
    """
    rows: list[tuple[str, str, str, str]] = []
    seen: dict[tuple[str, str], tuple[str, str]] = {}
    for rec in _iter_records(path, "ALIM_GRP"):
        for level in _LEVELS:
            code = rec.get(f"alim_{level}_code")
            if code is None or _is_placeholder(code):
                continue
            names = (
                _required(rec[f"alim_{level}_nom_fr"], f"group {code}"),
                _required(rec[f"alim_{level}_nom_eng"], f"group {code}"),
            )
            previous = seen.get((level, code))
            if previous is not None:
                if previous != names:
                    raise CiqualExtractError(f"alim_grp: conflicting names for {(level, code)}")
                continue
            seen[(level, code)] = names
            rows.append((level, code, *names))
    return rows


def parse_constituents(path: Path) -> list[tuple[int, str, str, str | None]]:
    rows: list[tuple[int, str, str, str | None]] = []
    seen: set[int] = set()
    for rec in _iter_records(path, "CONST"):
        code = _int(rec["const_code"], "const_code")
        if code in seen:
            raise CiqualExtractError(f"const: duplicate const_code {code}")
        seen.add(code)
        rows.append(
            (
                code,
                _required(rec["const_nom_fr"], f"const {code}"),
                _required(rec["const_nom_eng"], f"const {code}"),
                rec["code_INFOODS"],
            )
        )
    return rows


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
        int,
        int,
        str,
        float | None,
        str,
        str | None,
        float | None,
        str | None,
        float | None,
        str | None,
        int | None,
        str,
    ]
]:
    rows: list[
        tuple[
            int,
            int,
            str,
            float | None,
            str,
            str | None,
            float | None,
            str | None,
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
                alim_code,
                const_code,
                teneur_raw,
                teneur_value,
                teneur_kind,
                rec["min"],
                min_value,
                rec["max"],
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


def extract(cache_dir: Path, out_dir: Path) -> dict[str, int]:
    """Parse the five XML files and write the canonical intermediates.

    Returns a report of counts (fail high on any inconsistency).
    """
    files = _ensure_cache(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    groups = parse_groups(files["alim_grp_2025_11_03.xml"])
    group_codes = {code for _, code, _, _ in groups}
    aliments = parse_aliments(files["alim_2025_11_03.xml"])
    for code, _, _, _, grp, ssgrp, sssgrp, _ in aliments:
        for gcode in (grp, ssgrp, sssgrp):
            if _is_placeholder(gcode):
                continue
            if gcode not in group_codes:
                raise CiqualExtractError(f"alim {code}: group code {gcode!r} not in alim_grp")

    constituents = parse_constituents(files["const_2025_11_03.xml"])
    sources = parse_sources(files["sources_2025_11_03.xml"])
    values = parse_compo(files["compo_2025_11_03.xml"])

    alim_codes = {code for code, *_ in aliments}
    const_codes = {code for code, *_ in constituents}
    source_codes = {code for code, _ in sources}
    for alim_code, const_code, *_rest, source_code_found, _ in values:
        if alim_code not in alim_codes:
            raise CiqualExtractError(f"compo: orphan alim_code {alim_code}")
        if const_code not in const_codes:
            raise CiqualExtractError(f"compo: orphan const_code {const_code}")
        if source_code_found is not None and source_code_found not in source_codes:
            raise CiqualExtractError(f"compo: unknown source_code {source_code_found}")

    _frame(
        {
            "alim_code": pl.Int64,
            "alim_nom_fr": pl.Utf8,
            "alim_nom_eng": pl.Utf8,
            "alim_nom_sci": pl.Utf8,
            "alim_grp_code": pl.Utf8,
            "alim_ssgrp_code": pl.Utf8,
            "alim_ssssgrp_code": pl.Utf8,
            "facteur_jones": pl.Float64,
        },
        aliments,  # type: ignore[arg-type]
    ).write_parquet(out_dir / "foods.parquet")
    _frame(
        {"level": pl.Utf8, "code": pl.Utf8, "nom_fr": pl.Utf8, "nom_eng": pl.Utf8},
        groups,  # type: ignore[arg-type]
    ).write_parquet(out_dir / "food_groups.parquet")
    _frame(
        {
            "const_code": pl.Int64,
            "const_nom_fr": pl.Utf8,
            "const_nom_eng": pl.Utf8,
            "code_INFOODS": pl.Utf8,
        },
        constituents,  # type: ignore[arg-type]
    ).write_parquet(out_dir / "constituents.parquet")
    _frame(
        {"source_code": pl.Int64, "ref_citation": pl.Utf8},
        sources,  # type: ignore[arg-type]
    ).write_parquet(out_dir / "sources.parquet")
    _frame(
        {
            "alim_code": pl.Int64,
            "const_code": pl.Int64,
            "teneur_raw": pl.Utf8,
            "teneur_value": pl.Float64,
            "teneur_kind": pl.Utf8,
            "min_raw": pl.Utf8,
            "min_value": pl.Float64,
            "max_raw": pl.Utf8,
            "max_value": pl.Float64,
            "code_confiance": pl.Utf8,
            "source_code": pl.Int64,
            "source_record": pl.Utf8,
        },
        values,  # type: ignore[arg-type]
    ).write_parquet(out_dir / "values.parquet")

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
        "aliments": len(aliments),
        "constituents": len(constituents),
        "groups": len(groups),
        "sources": len(sources),
        "values": len(values),
    }
