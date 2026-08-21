"""JSONL exports of canonical tables (SPEC §2 deliverable).

One JSON object per line, UTF-8, LF line endings, deterministic order
(sorted by primary key). Exports land in ``build/exports/<table>.jsonl``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["EXPORTABLE", "ExportError", "export_jsonl"]

EXPORTABLE = ("concept", "source", "coverage", "value", "tombstone")


class ExportError(Exception):
    """Unknown table or missing canonical data (fail high, P9)."""


def _json_safe(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items()}


def export_jsonl(table: str, canonical_dir: Path, out_dir: Path) -> Path:
    if table not in EXPORTABLE:
        raise ExportError(f"table '{table}' is not exportable (choose from {EXPORTABLE})")
    source = canonical_dir / f"{table}.parquet"
    if not source.is_file():
        raise ExportError(f"canonical parquet missing: {source}")
    frame = pl.read_parquet(source)
    sort_keys = [column for column in frame.columns[:1]]
    frame = frame.sort(sort_keys)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{table}.jsonl"
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for record in frame.iter_rows(named=True):
            handle.write(json.dumps(_json_safe(record), ensure_ascii=False, default=str) + "\n")
    return target


def export_all(canonical_dir: Path, out_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in EXPORTABLE:
        path = export_jsonl(table, canonical_dir, out_dir)
        counts[table] = sum(1 for _ in path.open(encoding="utf-8"))
    return counts
