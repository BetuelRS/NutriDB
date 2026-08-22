"""Integration tests for the read-only REST server (F9, SPEC §2)."""

from __future__ import annotations

import json
import sqlite3
import threading
import urllib.request
from typing import TYPE_CHECKING

import pytest

from nutridb.package.__init__ import _SCHEMA
from nutridb.server import make_server

if TYPE_CHECKING:
    from pathlib import Path


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "api.sqlite"
    conn = sqlite3.connect(path)
    for name in (
        "label",
        "mv_food_value",
        "nutrient",
        "source",
        "food_group",
        "concept",
        "build_metadata",
    ):
        conn.execute(_SCHEMA[name])
    conn.execute(
        "INSERT INTO label VALUES "
        "('food','c1','en','native','Milk','milk'),"
        "('food','c1','pt','native','Leite','leite')"
    )
    conn.execute(
        "INSERT INTO mv_food_value (concept_id, locale, label, food_group, "
        "nutrient_id, value, unit, value_type, basis, divergence_flag) VALUES "
        "('c1','en','Milk','dairy','ENERC_KCAL',60,'kcal','measured','per_100g_edible',0),"
        "('c1','en','Milk','dairy','PROCNT',3.2,'g','measured','per_100g_edible',0)"
    )
    conn.execute(
        "INSERT INTO nutrient (tagname, grp, name_en, unit) "
        "VALUES ('PROCNT','proximates','Protein','g')"
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
    conn.execute(
        "INSERT INTO label_fts_en (rowid, text, text_normalized) "
        "SELECT rowid, text, text_normalized FROM label WHERE locale='en'"
    )
    conn.execute(
        "INSERT INTO label_fts_en_tri (rowid, text, text_normalized) "
        "SELECT rowid, text, text_normalized FROM label WHERE locale='en'"
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def server(tmp_path: Path):
    httpd = make_server(_artifact(tmp_path), "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, json.loads(response.read())


def test_health(server: str) -> None:
    status, payload = _get(f"{server}/api/v1/health")
    assert status == 200 and payload["status"] == "ok"


def test_search_and_food_values(server: str) -> None:
    status, payload = _get(f"{server}/api/v1/search?q=milk&locale=en")
    assert status == 200 and payload["count"] >= 1
    concept = payload["results"][0]["ref"]
    status, food = _get(f"{server}/api/v1/foods/{concept}?locale=en")
    assert status == 200 and food["count"] == 2
    nutrients = {v["nutrient_id"] for v in food["values"]}
    assert nutrients == {"ENERC_KCAL", "PROCNT"}


def test_ranking_endpoint(server: str) -> None:
    status, payload = _get(f"{server}/api/v1/nutrients/PROCNT/foods?locale=en&limit=5")
    assert status == 200 and payload["foods"][0]["value"] == 3.2


def test_openapi_document(server: str) -> None:
    status, payload = _get(f"{server}/openapi.json")
    assert status == 200 and payload["openapi"].startswith("3.")
    assert "/api/v1/search" in payload["paths"]


def test_unknown_path_is_json_404(server: str) -> None:
    try:
        _get(f"{server}/nope")
        raised = False
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        raised = True
        assert exc.code == 404
    assert raised
