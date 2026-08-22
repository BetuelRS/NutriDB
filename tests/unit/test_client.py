"""Tests for the public read client (PyPI surface)."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from nutridb.client import NutriDBClient
from nutridb.package.__init__ import _SCHEMA

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def artifact(tmp_path: Path) -> Path:
    path = tmp_path / "client.sqlite"
    conn = sqlite3.connect(path)
    for name in ("label", "mv_food_value", "nutrient", "concept"):
        conn.execute(_SCHEMA[name])
    conn.execute("INSERT INTO concept VALUES ('c1', 'food', 'dairy')")
    conn.execute(
        "INSERT INTO label VALUES "
        "('food','c1','en','native','Milk','milk'),"
        "('food','c1','pt','native','Leite','leite')"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE label_fts_en USING fts5("
        "text, text_normalized, content='label', content_rowid='rowid')"
    )
    conn.execute(
        "CREATE VIRTUAL TABLE label_fts_en_tri USING fts5("
        "text, text_normalized, tokenize='trigram', "
        "content='label', content_rowid='rowid')"
    )
    for table in ("label_fts_en", "label_fts_en_tri"):
        conn.execute(
            f"INSERT INTO {table} (rowid, text, text_normalized) "
            "SELECT rowid, text, text_normalized FROM label WHERE locale='en'"
        )
    conn.execute(
        "INSERT INTO mv_food_value (concept_id, locale, label, food_group, "
        "nutrient_id, value, unit, value_type, basis, divergence_flag) VALUES "
        "('c1','en','Milk','dairy','ENERC_KCAL',60,'kcal','measured','per_100g_edible',0)"
    )
    conn.execute(
        "INSERT INTO nutrient (tagname, grp, name_en, unit) "
        "VALUES ('PROCNT','proximates','Protein','g')"
    )
    conn.commit()
    conn.close()
    return path


def test_search_and_values(artifact: Path) -> None:
    with NutriDBClient(artifact) as db:
        hits = db.search("milk", locale="en")
        assert hits and hits[0]["ref"] == "c1"
        values = db.food_values("c1")
        assert values["locale"] == "en"
        assert values["values"][0]["nutrient_id"] == "ENERC_KCAL"


def test_available_locales(artifact: Path) -> None:
    with NutriDBClient(artifact) as db:
        assert "en" in db.available_locales()


def test_missing_artifact_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        NutriDBClient(tmp_path / "missing.sqlite")
