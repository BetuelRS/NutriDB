"""Unit tests for the i18n label pipeline (SPEC §7, ADR-0001 D7, ADR-0006 F4).

Composes labels over the synthetic fixture canonical dataset: native food
names (fr/en, status native), vocabulary en (official) and hand-verified
glossaries per active locale (curated). Sandbox divergences are derived
from the glossary pt-PT/pt-BR diffs (no real concept ids). Gates per
ADR-0006 §3.2: mt_unreviewed aborts, 161 tagnames per locale, >= 95%
native/official/curated, no generic pt for divergent refs, no drift.
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

_FIXTURE_MAP = {
    "alim_2025_11_03.xml": "alim_synthetic.xml",
    "alim_grp_2025_11_03.xml": "alim_grp_synthetic.xml",
    "compo_2025_11_03.xml": "compo_synthetic.xml",
    "const_2025_11_03.xml": "const_synthetic.xml",
    "sources_2025_11_03.xml": "sources_synthetic.xml",
}

# sandbox divergences: 53 nutrient pairs where pt-PT != pt-BR (glossary diffs)
DIVERGENT = 53


def _canonical(base: Path, root: Path) -> Path:
    cache = base / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for official, synthetic in _FIXTURE_MAP.items():
        copyfile(FIXTURE / synthetic, cache / official)
    extract(cache, base / "i" / "ciqual")
    transform(base / "i", base / "c", root)
    return base / "c"


def _labels(base: Path) -> pl.DataFrame:
    return pl.read_parquet(base / "c" / "label.parquet")


def test_normalize_label() -> None:
    assert normalize_label("Énergie") == "energie"
    assert normalize_label("cœur") == "coeur"
    assert normalize_label("açaí") == "acai"
    assert normalize_label("Água") == "agua"
    assert normalize_label("Açúcares") == "acucares"
    assert normalize_label("Straße") == "strasse"


def test_build_counts_and_statuses(tmp_path: Path, sandbox_root: Path) -> None:
    canonical = _canonical(tmp_path, sandbox_root)
    report = build(canonical, sandbox_root)
    vocab_en = 161  # frozen F1.1 vocabulary + F2 additive: VITA, CARTBEQ, OLSAC, NIATRP
    native = 6  # 3 foods x (fr + en)
    curated = vocab_en * 6 + (vocab_en - DIVERGENT)  # fr, pt-PT, pt-BR, es, de, it + pt
    assert report["labels"] == native + vocab_en + curated
    assert report["divergences"] == DIVERGENT
    assert report["reviewed"] == 0
    labels = _labels(tmp_path)
    statuses = {r["status"]: r["count"] for r in labels["status"].value_counts().rows(named=True)}
    assert statuses == {"native": native, "official": vocab_en, "curated": curated}
    assert report["fr"] == 3 + vocab_en
    assert report["en"] == 3 + vocab_en
    assert report["pt"] == vocab_en - DIVERGENT  # generic pt dropped for divergent refs
    assert report["pt-PT"] == vocab_en
    assert report["pt-BR"] == vocab_en
    assert report["es"] == vocab_en
    assert report["de"] == vocab_en
    assert report["it"] == vocab_en


def test_native_labels_from_records(tmp_path: Path, sandbox_root: Path) -> None:
    canonical = _canonical(tmp_path, sandbox_root)
    build(canonical, sandbox_root)
    labels = _labels(tmp_path)
    foods = labels.filter(pl.col("ref_kind") == "food")
    assert foods.height == 6
    fr = foods.filter(pl.col("locale") == "fr")
    assert set(fr["text"].to_list()) == {"Eau de vie de fruits", "Gin", "Pastis"}
    assert fr["status"].to_list() == ["native"] * 3
    normalized = sorted(labels["text_normalized"].unique().to_list())
    assert "pastis" in normalized
    assert "eau de vie de fruits" in normalized


def test_vocab_labels_official_and_glossary_curated(tmp_path: Path, sandbox_root: Path) -> None:
    canonical = _canonical(tmp_path, sandbox_root)
    build(canonical, sandbox_root)
    labels = _labels(tmp_path)
    water = labels.filter(pl.col("ref") == "WATER", pl.col("ref_kind") == "nutrient")
    by_locale = {r["locale"]: r for r in water.rows(named=True)}
    assert by_locale["en"]["text"] == "Water (by difference is not allowed)"
    assert by_locale["en"]["status"] == "official"
    for locale in ("fr", "pt", "pt-PT", "pt-BR", "es", "de", "it"):
        assert by_locale[locale]["status"] == "curated"
        assert by_locale[locale]["text_normalized"] == normalize_label(by_locale[locale]["text"])
    choavl = labels.filter(pl.col("ref") == "CHOAVL", pl.col("ref_kind") == "nutrient")
    locales = {r["locale"]: r["text"] for r in choavl.rows(named=True)}
    assert "pt" not in locales  # generic pt forbidden for divergent refs
    assert locales["pt-PT"] == "Hidratos de carbono disponíveis"
    assert locales["pt-BR"] == "Carboidratos disponíveis"


def test_missing_canonical_fails_high(tmp_path: Path, sandbox_root: Path) -> None:
    with pytest.raises(I18nError, match="canonical dataset missing"):
        build(tmp_path / "c", sandbox_root)


def test_empty_glossary_label_fails_high(
    tmp_path: Path, sandbox_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nutridb import i18n as i18n_module

    canonical = _canonical(tmp_path, sandbox_root)
    real_load = i18n_module.load_csv

    def fake_load(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
        rows = real_load(path, columns)
        if "glossary" in str(path) and "pt-PT" in str(path):
            return [{**r, "label": "  " if r["tagname"] == "WATER" else r["label"]} for r in rows]
        return rows

    monkeypatch.setattr(i18n_module, "load_csv", fake_load)
    with pytest.raises(I18nError, match="empty label for glossary pt-PT WATER"):
        build(canonical, sandbox_root)


def test_mt_unreviewed_aborts_core(
    tmp_path: Path, sandbox_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nutridb import i18n as i18n_module

    canonical = _canonical(tmp_path, sandbox_root)
    real_row = i18n_module._row

    def poisoned_row(
        kind: str, ref: str, locale: str, status: str, text: str
    ) -> tuple[str, str, str, str, str, str]:
        if kind == "nutrient" and ref == "WATER" and locale == "pt-PT":
            return real_row(kind, ref, locale, "mt_unreviewed", text)
        return real_row(kind, ref, locale, status, text)

    monkeypatch.setattr(i18n_module, "_row", poisoned_row)
    with pytest.raises(I18nError, match="mt_unreviewed labels must not enter core"):
        build(canonical, sandbox_root)


def test_generic_pt_forbidden_for_divergent_ref(tmp_path: Path, sandbox_root: Path) -> None:
    canonical = _canonical(tmp_path, sandbox_root)
    (sandbox_root / "i18n" / "labels" / "reviewed_pt.csv").write_text(
        "# reviewer mistake: generic label for a divergent ref\n"
        "ref_kind,ref,label\nnutrient,CHOAVL,Hidratos de carbono\n",
        encoding="utf-8",
    )
    with pytest.raises(I18nError, match="generic pt label used for divergent ref"):
        build(canonical, sandbox_root)


def test_reviewed_overrides_win_and_stay_curated(tmp_path: Path, sandbox_root: Path) -> None:
    canonical = _canonical(tmp_path, sandbox_root)
    (sandbox_root / "i18n" / "labels" / "reviewed_pt-PT.csv").write_text(
        "# approved decision (CLI `i18n review --apply`)\n"
        "ref_kind,ref,label\nnutrient,WATER,Água (H2O)\n",
        encoding="utf-8",
    )
    report = build(canonical, sandbox_root)
    assert report["reviewed"] == 1
    labels = _labels(tmp_path)
    row = labels.filter(
        pl.col("ref") == "WATER", pl.col("ref_kind") == "nutrient", pl.col("locale") == "pt-PT"
    ).rows(named=True)[0]
    assert row["text"] == "Água (H2O)"
    assert row["status"] == "curated"


def test_divergence_drift_detected(tmp_path: Path, sandbox_root: Path) -> None:
    canonical = _canonical(tmp_path, sandbox_root)
    glossary = sandbox_root / "i18n" / "glossary" / "pt-PT.csv"
    text = glossary.read_text(encoding="utf-8").replace(
        "Hidratos de carbono disponíveis", "Hidratos disp"
    )
    glossary.write_text(text, encoding="utf-8")
    with pytest.raises(I18nError, match="drifts from glossary"):
        build(canonical, sandbox_root)


def test_unknown_food_concept_in_divergences(tmp_path: Path, sandbox_root: Path) -> None:
    canonical = _canonical(tmp_path, sandbox_root)
    with (sandbox_root / "i18n" / "divergences.csv").open("a", encoding="utf-8", newline="") as fh:
        fh.write("food,nfx_00NOPE00NOPE00NOPE00NOPE00,Curgete,Abobrinha,,\n")
    with pytest.raises(I18nError, match="unknown food concept"):
        build(canonical, sandbox_root)


def test_missing_glossary_fails_coverage_gate(tmp_path: Path, sandbox_root: Path) -> None:
    canonical = _canonical(tmp_path, sandbox_root)
    (sandbox_root / "i18n" / "glossary" / "es.csv").unlink()
    with pytest.raises(I18nError, match="locale es: missing nutrient labels"):
        build(canonical, sandbox_root)


def test_i18n_deterministic(tmp_path: Path, sandbox_root: Path) -> None:
    a = _canonical(tmp_path / "a", sandbox_root)
    b = _canonical(tmp_path / "b", sandbox_root)
    build(a, sandbox_root)
    build(b, sandbox_root)
    assert (a / "label.parquet").read_bytes() == (b / "label.parquet").read_bytes()
