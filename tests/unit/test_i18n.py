"""Unit tests for the i18n F1-lite label pipeline (SPEC §7, ADR-0001 D7).

Composes labels over the synthetic fixture canonical dataset: native
food names (fr/en, status native), vocabulary en (official) and the
minimal hand-curated pt-PT list (curated). Empty labels fail high (P7).
"""

from __future__ import annotations

from shutil import copyfile
from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.i18n import I18nError, build, normalize_label
from nutridb.paths import project_root
from nutridb.sources.ciqual import extract
from nutridb.transform import transform

if TYPE_CHECKING:
    from pathlib import Path

FIXTURE = project_root() / "tests" / "fixtures" / "synthetic_ciqual"
ROOT = project_root()

_FIXTURE_MAP = {
    "alim_2025_11_03.xml": "alim_synthetic.xml",
    "alim_grp_2025_11_03.xml": "alim_grp_synthetic.xml",
    "compo_2025_11_03.xml": "compo_synthetic.xml",
    "const_2025_11_03.xml": "const_synthetic.xml",
    "sources_2025_11_03.xml": "sources_synthetic.xml",
}


def _canonical(base: Path) -> Path:
    cache = base / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for official, synthetic in _FIXTURE_MAP.items():
        copyfile(FIXTURE / synthetic, cache / official)
    extract(cache, base / "i")
    transform(base / "i", base / "c", ROOT)
    return base / "c"


def _labels(base: Path) -> pl.DataFrame:
    return pl.read_parquet(base / "c" / "label.parquet")


def test_normalize_label() -> None:
    assert normalize_label("Énergie") == "energie"
    assert normalize_label("cœur") == "coeur"
    assert normalize_label("açaí") == "acai"
    assert normalize_label("Água") == "agua"
    assert normalize_label("Açúcares") == "acucares"


def test_build_counts_and_statuses(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path)
    report = build(canonical, ROOT)
    assert report["labels"] == 3 + 3 + 157 + 11
    labels = _labels(tmp_path)
    statuses = {r["status"]: r["count"] for r in labels["status"].value_counts().rows(named=True)}
    assert statuses == {"native": 6, "official": 157, "curated": 11}
    assert report["fr"] == 3  # foods only (CIQUAL native language)
    assert report["en"] == 3 + 157
    assert report["pt-PT"] == 11
    assert report["pt-BR"] == 0


def test_native_labels_from_records(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path)
    build(canonical, ROOT)
    labels = _labels(tmp_path)
    foods = labels.filter(pl.col("ref_kind") == "food")
    assert foods.height == 6
    fr = foods.filter(pl.col("locale") == "fr")
    assert set(fr["text"].to_list()) == {"Eau de vie de fruits", "Gin", "Pastis"}
    assert fr["status"].to_list() == ["native"] * 3
    normalized = sorted(labels["text_normalized"].unique().to_list())
    assert "pastis" in normalized
    assert "eau de vie de fruits" in normalized


def test_vocab_labels_official_and_curated(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path)
    build(canonical, ROOT)
    labels = _labels(tmp_path)
    water = labels.filter(pl.col("ref") == "WATER", pl.col("ref_kind") == "nutrient")
    by_locale = {r["locale"]: r for r in water.rows(named=True)}
    assert by_locale["en"]["text"] == "Water (by difference is not allowed)"
    assert by_locale["en"]["status"] == "official"
    assert by_locale["pt-PT"]["text"] == "Água"
    assert by_locale["pt-PT"]["status"] == "curated"
    assert by_locale["pt-PT"]["text_normalized"] == "agua"


def test_missing_canonical_fails_high(tmp_path: Path) -> None:
    with pytest.raises(I18nError, match="canonical dataset missing"):
        build(tmp_path / "c", ROOT)


def test_empty_curated_label_fails_high(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nutridb import i18n as i18n_module

    canonical = _canonical(tmp_path)
    real_load = i18n_module.load_csv

    def fake_load(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
        if "vocab_pt_PT" in str(path):
            return [{"tagname": "WATER", "label": "  "}]
        return real_load(path, columns)

    monkeypatch.setattr(i18n_module, "load_csv", fake_load)
    with pytest.raises(I18nError, match="empty label for pt-PT WATER"):
        build(canonical, ROOT)


def test_i18n_deterministic(tmp_path: Path) -> None:
    a = _canonical(tmp_path / "a")
    b = _canonical(tmp_path / "b")
    build(a, ROOT)
    build(b, ROOT)
    assert (a / "label.parquet").read_bytes() == (b / "label.parquet").read_bytes()
