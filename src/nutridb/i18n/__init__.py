"""Internationalization F1-lite (SPEC Â§7, ADR-0001 D7).

Composes the ``label`` table of the canonical dataset:

    ref_kind   'food' | 'nutrient'
    ref        concept_id (food) or tagname (nutrient)
    locale     active composition locale
    status     native | official | curated   (P7: mt_unreviewed has no
               place in F1; machine translation is a later phase)
    text       display text
    text_normalized  locale-aware normalized form (NFKD, diacritics
               stripped, lowercased) for accent-insensitive search

Label sources in F1:
    * native names (fr/en) straight from the immutable source records;
      a food the source names in one language has one label; the other
      locale resolves through the fallback chain at query time (fallback
      is never frozen into the table);
    * vocabulary labels: en from the frozen vocabulary (status official)
      and the minimal hand-curated pt-PT list under i18n/labels/ (status
      curated).

Fail high (P7/P9): a label row with empty text aborts the build; a
curated tagname that does not exist in the vocabulary aborts the build.
"""

from __future__ import annotations

import json
import tomllib
import unicodedata
from typing import TYPE_CHECKING, Any

import polars as pl

from nutridb.vocab import load_csv

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["I18nError", "build", "load_csv", "load_locales", "normalize_label"]

LABEL_COLUMNS = (
    "ref_kind",
    "ref",
    "locale",
    "status",
    "text",
    "text_normalized",
)

_NATIVE_FIELDS = {"fr": "alim_nom_fr", "en": "alim_nom_eng"}


class I18nError(Exception):
    """Fatal input inconsistency in the label composition (fail high, P9)."""


def build(canonical_dir: Path, root: Path) -> dict[str, int]:
    """Compose ``label.parquet`` into ``canonical_dir``; return counts.

    Reads the canonical dataset (concept_link, source_record) and the
    i18n configuration as data; writes a sorted, deterministic table.
    """
    required = (canonical_dir / "concept_link.parquet").is_file() and (
        canonical_dir / "source_record.parquet"
    ).is_file()
    if not required:
        raise I18nError("canonical dataset missing; run `uv run nutridb transform` first")

    config = load_locales(root / "i18n" / "locales.toml")

    # -- native labels: foods, straight from immutable records ---------------
    links = pl.read_parquet(canonical_dir / "concept_link.parquet")
    records = pl.read_parquet(canonical_dir / "source_record.parquet")
    food_records = records.filter(pl.col("kind") == "food")
    by_record = {r["source_record_id"]: r for r in food_records.rows(named=True)}
    by_concept = {
        r["concept_id"]: r["source_record_id"]
        for r in links.filter(pl.col("status") == "automatic").rows(named=True)
    }

    labels: list[tuple[str, ...]] = []
    for concept_id in sorted(by_concept):
        raw = json.loads(by_record[by_concept[concept_id]]["record"])
        for locale, field in _NATIVE_FIELDS.items():
            text = raw.get(field)
            if not text:
                continue  # source provides no name in this language; fallback
            _require_text(text, f"food {concept_id} {locale}")
            labels.append(_row("food", concept_id, locale, "native", text))

    # -- vocabulary labels: en (official) + pt-PT curated --------------------
    vocab = load_csv(root / "vocab" / "nutrients.csv", ("tagname", "group", "name_en", "unit"))
    tags = {row["tagname"] for row in vocab}
    for row in sorted(vocab, key=lambda r: r["tagname"]):
        _require_text(row["name_en"], f"vocab {row['tagname']} en")
        labels.append(_row("nutrient", row["tagname"], "en", "official", row["name_en"]))

    curated = load_csv(root / "i18n" / "labels" / "vocab_pt_PT.csv", ("tagname", "label"))
    for row in sorted(curated, key=lambda r: r["tagname"]):
        if row["tagname"] not in tags:
            raise I18nError(f"pt-PT label for unknown tagname {row['tagname']!r}")
        _require_text(row["label"], f"pt-PT {row['tagname']}")
        labels.append(_row("nutrient", row["tagname"], "pt-PT", "curated", row["label"]))

    # -- build the table (sorted -> deterministic, P5) ------------------------
    labels.sort(key=lambda row: (row[0], row[1], row[2]))
    data = {name: [row[i] for row in labels] for i, name in enumerate(LABEL_COLUMNS)}
    frame = pl.DataFrame(data, schema={name: pl.Utf8 for name in LABEL_COLUMNS})
    frame.write_parquet(canonical_dir / "label.parquet")

    counts = {"labels": len(labels), "vocab_en": len(vocab)}
    for locale in config["active"]:
        counts[locale] = frame.filter(pl.col("locale") == locale).height
    return counts


def normalize_label(text: str) -> str:
    """F1 normalization: transliterate ligatures, NFKD, strip marks, lowercase.

    ``cœur`` -> ``coeur``, ``açaí`` -> ``acai``, ``Água`` -> ``agua``,
    ``Straße`` -> ``strasse``. The transliteration map covers the common
    European ligatures (unified NFKD does not decompose them); F1 uses one
    normalization for every locale (the per-locale hook is the schema's).
    """
    translit = str.maketrans(_LIGATURES)
    decomposed = unicodedata.normalize("NFKD", text.translate(translit))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return stripped.casefold()


_LIGATURES = {
    "œ": "oe",
    "Œ": "OE",
    "æ": "ae",
    "Æ": "AE",
    "ß": "ss",
}


def _row(
    ref_kind: str, ref: str, locale: str, status: str, text: str
) -> tuple[str, str, str, str, str, str]:
    return (ref_kind, ref, locale, status, text, normalize_label(text))


def _require_text(text: str, where: str) -> None:
    if not text.strip():
        raise I18nError(f"empty label for {where}")


def load_locales(path: Path) -> dict[str, Any]:
    """Read and validate i18n/locales.toml: active list + fallback chains."""
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    locales = {name: section["fallback"] for name, section in config.get("locale", {}).items()}
    for locale, chain in locales.items():
        for hop in chain:
            if hop not in locales:
                raise I18nError(f"locale {locale}: unknown fallback {hop!r}")
            if hop == locale or locale in locales.get(hop, []):
                raise I18nError(f"locale {locale}: fallback cycle via {hop}")
    active = config.get("active", [])
    if not active:
        raise I18nError("locales.toml: active list is empty")
    return {"active": list(active), "chains": locales}
