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
from nutridb.derive import derive as run_derive
from nutridb.i18n import build as build_labels
from nutridb.merge import merge as run_merge
from nutridb.package import package
from nutridb.paths import project_root
from nutridb.sources.ciqual import extract
from nutridb.transform import transform

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

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
    run_derive(canonical, root)
    run_merge(canonical, root)
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
    # es FTS has no food labels; "water" hits the en index, but the label
    # resolves through the es chain -> es label (F4: find the concept,
    # display it in the query locale)
    es = search(db_path, "water", "es")
    water = [h for h in es if h.ref == "WATER"]
    assert water
    assert water[0].text == "Agua"
    assert water[0].locale == "es"
    assert water[0].status == "curated"


def test_search_cross_lingual_resolves_label(db_path: str) -> None:
    # "energy" hits the en FTS (no es label matches), but the concept's
    # display label resolves through the es chain -> es label (F4, SPEC §7)
    hits = search(db_path, "energy", "es")
    energy = [h for h in hits if h.ref == "ENERC_KCAL"]
    assert energy
    assert energy[0].text == "Energía"
    assert energy[0].locale == "es"
    assert energy[0].status == "curated"


def test_search_reviewed_override_searches_and_dedupes(db_path: str, tmp_path: Path) -> None:
    from conftest import make_sandbox_root

    base = tmp_path / "search_review"
    base.mkdir()
    root = make_sandbox_root(base)
    labels_dir = root / "i18n" / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    (labels_dir / "reviewed_pt-PT.csv").write_text(
        "# approved decision (CLI `i18n review --apply`)\n"
        "ref_kind,ref,label\nnutrient,WATER,Água (H2O)\n",
        encoding="utf-8",
    )
    cache = base / "cache"
    cache.mkdir()
    for official, synthetic in _FIXTURE_MAP.items():
        copyfile(FIXTURE / synthetic, cache / official)
    extract(cache, base / "i" / "ciqual")
    canonical = base / "c"
    transform(base / "i", canonical, root)
    build_labels(canonical, root)
    run_derive(canonical, root)
    run_merge(canonical, root)
    info = package(canonical, root / "vocab", base / "out", root)
    hits = search(str(info["path"]), "h2o", "pt-PT")
    water = [h for h in hits if h.ref == "WATER"]
    assert len(water) == 1  # override + glossary rows deduplicated by concept
    assert water[0].text == "Água (H2O)"
    assert water[0].status == "curated"


def test_search_empty_and_unknown_locale(db_path: str) -> None:
    assert search(db_path, "   ", "pt-PT") == []
    with pytest.raises(ApiError, match="unknown locale"):
        search(db_path, "pastis", "zz-ZZ")


def test_search_never_creates_missing_database(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(ApiError):
        search(missing, "pastis", "fr")
    assert not missing.exists()


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
        expected = sorted(
            f"label_fts_{loc}" + suffix
            for loc in ("de", "en", "es", "fr", "it", "pt", "pt_BR", "pt_PT")
            for suffix in ("", "_tri")
        )
        assert [f[0] for f in frames] == expected
    finally:
        conn.close()


def test_search_trigram_substring(db_path: str) -> None:
    # "vie" is a substring of "Eau de vie de fruits": the prefix index
    # ("vie"*) misses it, the trigram index finds it (emenda A8).
    hits = search(db_path, "vie", "fr")
    assert "Eau de vie de fruits" in _texts(hits)
    brandy = search(db_path, "brandy", "en")
    assert "Fruit brandy or eau-de-vie" in _texts(brandy)


def test_search_short_term_falls_back_to_prefix(db_path: str) -> None:
    # 2-char terms have no trigrams; the API falls back to the prefix index.
    hits = search(db_path, "gi", "fr")
    assert "Gin" in _texts(hits)


def test_search_kind_nutrient(db_path: str) -> None:
    hits = search(db_path, "energ", "pt-PT", kind="nutrient")
    assert all(r.ref_kind == "nutrient" for r in hits)
    assert {r.ref for r in hits} == {"ENERC_KCAL", "ENERC_KJ"}


def test_search_kind_food_excludes_nutrients(db_path: str) -> None:
    hits = search(db_path, "energ", "pt-PT", kind="food")
    assert all(r.ref_kind == "food" for r in hits)


def test_search_invalid_kind_fails(db_path: str) -> None:
    with pytest.raises(ApiError, match="kind"):
        search(db_path, "eau", "fr", kind="category")


def test_search_food_group_filter(db_path: str) -> None:
    beverages = search(db_path, "eau", "fr", food_group="alcoholic_beverages")
    assert beverages
    assert all(r.ref_kind == "food" for r in beverages)
    assert search(db_path, "eau", "fr", food_group="dairy") == []


def test_foods_for_nutrient_ranks_by_value(db_path: str) -> None:
    from nutridb.api import foods_for_nutrient

    foods = foods_for_nutrient(db_path, "WATER", "fr")
    assert foods
    assert all(f.nutrient_id == "WATER" and f.value is not None for f in foods)
    values = [v for v in (f.value for f in foods) if v is not None]
    assert values == sorted(values, reverse=True)
    assert foods[0].basis == "per_100g_edible"
    assert foods[0].food_group == "alcoholic_beverages"


def test_foods_for_nutrient_group_filter_and_limit(db_path: str) -> None:
    from nutridb.api import ApiError, foods_for_nutrient

    assert foods_for_nutrient(db_path, "WATER", "fr", food_group="dairy") == []
    with pytest.raises(ApiError, match="limit"):
        foods_for_nutrient(db_path, "WATER", "fr", limit=0)
