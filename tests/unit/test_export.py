"""Unit tests for JSONL exports (SPEC §2 deliverable)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.export import ExportError, export_all, export_jsonl

if TYPE_CHECKING:
    from pathlib import Path


def _write_canonical(path: Path) -> None:
    path.mkdir(parents=True)
    pl.DataFrame(
        {
            "concept_id": ["nfx_B", "nfx_A"],
            "kind": ["food", "food"],
            "food_group": ["fruits", "dairy"],
        }
    ).write_parquet(path / "concept.parquet")
    pl.DataFrame({"source_id": ["ciqual"], "name": ["CIQUAL"], "version": ["2025"]}).write_parquet(
        path / "source.parquet"
    )
    for table in ("coverage", "value", "tombstone"):
        pl.DataFrame({"x": []}).write_parquet(path / f"{table}.parquet")


def test_export_jsonl_is_sorted_and_parseable(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    _write_canonical(canonical)
    target = export_jsonl("concept", canonical, tmp_path / "exports")
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert [row["concept_id"] for row in parsed] == ["nfx_A", "nfx_B"]


def test_export_all_covers_every_table(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    _write_canonical(canonical)
    counts = export_all(canonical, tmp_path / "exports")
    assert set(counts) == {"concept", "source", "coverage", "value", "tombstone"}
    assert counts["concept"] == 2
    assert all(count >= 0 for count in counts.values())


def test_unknown_table_fails_high(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        export_jsonl("not_a_table", tmp_path, tmp_path)


def test_missing_canonical_fails_high(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        export_jsonl("value", tmp_path / "missing", tmp_path)
