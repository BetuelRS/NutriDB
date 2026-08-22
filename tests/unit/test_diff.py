"""Tests for artifact diff (F8)."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from nutridb.diff import DiffError, diff_artifacts

if TYPE_CHECKING:
    from pathlib import Path


SCHEMA = (
    "CREATE TABLE mv_food_value (concept_id TEXT, locale TEXT, label TEXT, "
    "food_group TEXT, nutrient_id TEXT, value REAL, unit TEXT, "
    "value_type TEXT, confidence_code TEXT, acquisition_type TEXT, "
    "source_id TEXT, source_record_id TEXT, below_loq_threshold REAL, "
    "basis TEXT, alternatives TEXT, divergence_flag INTEGER, "
    "divergence_max REAL, derivation_id TEXT, override_justification TEXT);"
    "CREATE TABLE tombstone (concept_id TEXT PRIMARY KEY, successor TEXT, "
    "reason TEXT);"
    "CREATE TABLE label (ref_kind TEXT, ref TEXT, locale TEXT, status TEXT, "
    "text TEXT, text_normalized TEXT);"
)


def _build(path: Path, rows: list[tuple[str, str, str, float, str, str]]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO mv_food_value (concept_id, locale, nutrient_id, value, "
        "unit, source_id) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.execute("INSERT INTO label VALUES ('food','c1','en','native','Milk','milk')")
    conn.commit()
    conn.close()


def test_diff_reports_added_removed_changed(tmp_path: Path) -> None:
    old = tmp_path / "old.sqlite"
    new = tmp_path / "new.sqlite"
    _build(
        old,
        [
            ("c1", "en", "ENERC_KCAL", 60.0, "kcal", "ciqual"),
            ("c1", "en", "PROCNT", 3.0, "g", "ciqual"),
            ("c2", "en", "FAT", 10.0, "g", "insa"),
        ],
    )
    _build(
        new,
        [
            ("c1", "en", "ENERC_KCAL", 62.0, "kcal", "ciqual"),
            ("c1", "en", "PROCNT", 3.0, "g", "ciqual"),
            ("c3", "en", "SUGAR", 5.0, "g", "insa"),
        ],
    )
    report = diff_artifacts(old, new)
    assert report["added_count"] == 1
    assert report["removed_count"] == 1
    assert report["changed_count"] == 1
    changed = report["samples"]["changed"][0]
    assert changed["old"]["value"] == 60.0 and changed["new"]["value"] == 62.0
    assert changed["label"] == "Milk"


def test_missing_artifact_fails_high(tmp_path: Path) -> None:
    good = tmp_path / "good.sqlite"
    _build(good, [])
    with pytest.raises(DiffError):
        diff_artifacts(good, tmp_path / "missing.sqlite")
