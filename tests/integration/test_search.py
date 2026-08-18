"""Integration tests for the public search API (F1.8, emenda A7).

Builds a package from the synthetic fixture and searches through the
per-locale FTS index: exact, accent-insensitive, phrase, fallback chains
and fail-high on unknown locales.
"""

from __future__ import annotations

import sqlite3
from shutil import copyfile
from typing import TYPE_CHECKING

import pytest

from nutridb.api import ApiError, SearchResult, search
from nutridb.i18n import build as build_labels
from nutridb.package import package
from nutridb.paths import project_root
from nutridb.sources.ciqual import extract
from nutridb.transform import transform

if TYPE_CHECKING:
    from collections.abc import Sequence

FIXTURE = project_root() / "tests" / "fixtures" / "synthetic_ciqual"

_FIXTURE_MAP = {
    "alim_2025_11_03.xml": "alim_synthetic.xml",
    "alim_grp_2025_11_03.xml": "alim_grp_synthetic.xml",
    "compo_2025_11_03.xml": "compo_synthetic.xml",
    "const_2025_11_03.xml": "const_synthetic.xml",
    "sources_2025_11_03.xml": "sources_synthetic.xml",
}


@pytest.fixture(scope="module")
def db_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    from conftest import make_sandbox_root

    base = tmp_path_factory.mktemp("search")
    root = make_sandbox_root(base)
    cache = base / "cache"
    cache.mkdir()
    for official, synthetic in _FIXTURE_MAP.items():
        copyfile(FIXTURE / synthetic, cache / official)
    extract(cache, base / "i" / "ciqual")
    canonical = base / "c"
    transform(base / "i", canonical, root)
    build_labels(canonical, root)
    info = package(canonical, root / "vocab", base / "out", root)
    return str(info["path"])


def _texts(results: Sequence[SearchResult]) -> set[str]:
    return {r.text for r in results}


def test_search_exact(db_path: str) -> None:
    hits = search(db_path, "pastis", "fr")
    assert "Pastis" in _texts(hits)
    assert all(r.locale == "fr" for r in hits)


def test_search_accent_insensitive(db_path: str) -> None:
    accents = search(db_path, "águ", "pt-PT")
    assert "Água" in _texts(accents)
    no_accents = search(db_path, "agua", "pt-PT")
    assert _texts(accents) == _texts(no_accents)


def test_search_english_labels(db_path: str) -> None:
    hits = search(db_path, "gin", "en")
    assert "Gin" in _texts(hits)
    water = search(db_path, "water", "en")
    assert "Water (by difference is not allowed)" in _texts(water)


def test_search_phrase_multi_token(db_path: str) -> None:
    hits = search(db_path, "eau de vie", "fr")
    assert "Eau de vie de fruits" in _texts(hits)


def test_search_fallback_chain(db_path: str) -> None:
    es = search(db_path, "water", "es")  # es -> en (no es labels in F1)
    assert "Water (by difference is not allowed)" in _texts(es)
    assert all(r.locale == "en" for r in es)


def test_search_empty_and_unknown_locale(db_path: str) -> None:
    assert search(db_path, "   ", "pt-PT") == []
    with pytest.raises(ApiError, match="unknown locale"):
        search(db_path, "pastis", "zz-ZZ")


def test_search_limit_enforced(db_path: str) -> None:
    with pytest.raises(ApiError, match="limit"):
        search(db_path, "pastis", "fr", limit=0)
    with pytest.raises(ApiError, match="limit"):
        search(db_path, "pastis", "fr", limit=101)


def test_search_results_are_labels_with_status(db_path: str) -> None:
    hits = search(db_path, "energ", "pt-PT")  # prefix hits both energia/energy
    energy = [h for h in hits if h.ref == "ENERC_KCAL"]
    assert energy
    assert energy[0].status == "curated"
    assert energy[0].ref_kind == "nutrient"
    assert energy[0].locale == "pt-PT"


def test_package_fts_visible_from_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        frames = conn.execute(
            "SELECT name FROM sqlite_master WHERE sql LIKE 'CREATE VIRTUAL TABLE%' ORDER BY name"
        ).fetchall()
        assert [f[0] for f in frames] == ["label_fts_en", "label_fts_fr", "label_fts_pt_PT"]
    finally:
        conn.close()
