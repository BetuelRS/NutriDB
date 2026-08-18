"""Internationalization (SPEC §7, ADR-0001 D7, ADR-0006 F4).

Composes the ``label`` table of the canonical dataset:

    ref_kind   'food' | 'nutrient'
    ref        concept_id (food) or tagname (nutrient)
    locale     active composition locale
    status     native | official | curated   (P7: mt_unreviewed has no
               place in `core`; the build fails on it)
    text       display text
    text_normalized  locale-aware normalized form (NFKD, diacritics
               stripped, lowercased) for accent-insensitive search

Label sources (ADR-0005 D7, ADR-0006 §3.1), priority high -> low:

    * reviewed:   i18n/labels/reviewed_<locale>.csv — decisions of the
                  review flow (CLI `i18n review`), status curated;
    * native:     names straight from the immutable source records
                  (CIQUAL: fr/en; TCA: pt);
    * glossary:   i18n/glossary/<locale>.csv — hand-verified terminology
                  for the 161 nutrient tagnames (status curated);
                  `en` comes from the frozen vocabulary (official);
    * divergences: i18n/divergences.csv — curated regional variant labels
                  (pt-PT/pt-BR) for concepts with a registered divergence.

Gates (ADR-0006 §3.2, fail high P7/P9):

    * any label with status mt_unreviewed aborts the build;
    * every active locale must cover the 161 nutrient tagnames;
    * per locale, >= 95% of labels must be native/official/curated;
    * a ref registered in divergences.csv (pt pair) needs its own
      pt-PT and pt-BR label and must NOT have a generic `pt` label
      (SPEC §7: "o build falha se um rótulo pt genérico for usado onde
      existe divergência conhecida"); food refs must exist as concepts;
      nutrient rows must match the glossary variant labels (no drift).
"""

from __future__ import annotations

import csv
import json
import tomllib
import unicodedata
from typing import TYPE_CHECKING, Any

import polars as pl

from nutridb.vocab import load_csv

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "I18nError",
    "build",
    "load_csv",
    "load_divergences",
    "load_locales",
    "normalize_label",
]

LABEL_COLUMNS = (
    "ref_kind",
    "ref",
    "locale",
    "status",
    "text",
    "text_normalized",
)

NUTRIENT_COUNT = 161
_STATUS_OK = {"native", "official", "curated"}
_STATUS_GATE = 0.95


class I18nError(Exception):
    """Fatal input inconsistency in the label composition (fail high, P9)."""


def build(canonical_dir: Path, root: Path) -> dict[str, Any]:
    """Compose ``label.parquet`` into ``canonical_dir``; return counts.

    Reads the canonical dataset (concept_link, source_record, concept),
    the i18n configuration and glossaries; writes a sorted,
    deterministic table. Gates per ADR-0006 §3.2 (P7/P9).
    """
    required = (
        (canonical_dir / "concept_link.parquet").is_file()
        and (canonical_dir / "source_record.parquet").is_file()
        and (canonical_dir / "concept.parquet").is_file()
    )
    if not required:
        raise I18nError("canonical dataset missing; run `uv run nutridb transform` first")

    config = load_locales(root / "i18n" / "locales.toml")
    active = config["active"]
    labels: list[tuple[str, ...]] = []

    # -- 1. reviewed overrides (i18n/labels/reviewed_<locale>.csv) ----------
    reviewed = _load_reviewed(root, active)
    for (kind, ref, locale), text in reviewed.items():
        labels.append(_row(kind, ref, locale, "curated", text))

    # -- 2. native food labels, straight from immutable records (P1) --------
    links = pl.read_parquet(canonical_dir / "concept_link.parquet")
    records = pl.read_parquet(canonical_dir / "source_record.parquet")
    food_records = records.filter(pl.col("kind") == "food")
    by_record = {r["source_record_id"]: r for r in food_records.rows(named=True)}
    by_concept: dict[str, list[str]] = {}
    for r in links.filter(pl.col("status").is_in(["automatic", "adjudicated"])).rows(named=True):
        by_concept.setdefault(r["concept_id"], []).append(r["source_record_id"])

    divergences = load_divergences(root / "i18n" / "divergences.csv")
    divergent_pt = {(r["ref_kind"], r["ref"]) for r in divergences if r["ptPT"] and r["ptBR"]}
    for concept_id in sorted(by_concept):
        names: dict[str, str] = {}
        for record_id in sorted(by_concept[concept_id]):
            for locale, text in json.loads(by_record[record_id]["record"])["names"].items():
                if text and locale not in names:
                    names[locale] = text  # first non-empty wins, deterministic
        for locale, text in sorted(names.items()):
            if locale == "pt" and ("food", concept_id) in divergent_pt:
                continue  # generic label forbidden where variants diverge
            if locale not in active:
                continue
            _require_text(text, f"food {concept_id} {locale}")
            labels.append(_row("food", concept_id, locale, "native", text))

    # -- 3. vocabulary labels: en official (INFOODS, frozen) ----------------
    vocab = load_csv(root / "vocab" / "nutrients.csv", ("tagname", "group", "name_en", "unit"))
    tags = {row["tagname"] for row in vocab}
    if len(tags) != NUTRIENT_COUNT:
        raise I18nError(f"vocabulary has {len(tags)} tagnames, expected {NUTRIENT_COUNT}")
    for row in sorted(vocab, key=lambda r: r["tagname"]):
        _require_text(row["name_en"], f"vocab {row['tagname']} en")
        labels.append(_row("nutrient", row["tagname"], "en", "official", row["name_en"]))

    # -- 4. glossary labels per active locale (status curated) --------------
    glossary: dict[str, dict[str, str]] = {}
    for locale in active:
        path = root / "i18n" / "glossary" / f"{locale}.csv"
        if not path.is_file():
            continue  # en has no glossary: official vocabulary labels
        rows = load_csv(path, ("tagname", "label", "status", "evidence"))
        terms = {r["tagname"]: r["label"] for r in rows}
        missing = tags - set(terms)
        if missing:
            raise I18nError(f"glossary {locale}: missing tagnames {sorted(missing)}")
        for tagname in sorted(terms):
            if locale == "pt" and ("nutrient", tagname) in divergent_pt:
                continue  # generic label forbidden where variants diverge
            _require_text(terms[tagname], f"glossary {locale} {tagname}")
            labels.append(_row("nutrient", tagname, locale, "curated", terms[tagname]))
        glossary[locale] = terms

    # -- 5. divergence labels (curated regional variants) -------------------
    concepts = {
        r["concept_id"] for r in pl.read_parquet(canonical_dir / "concept.parquet").rows(named=True)
    }
    for row in divergences:
        if row["ptPT"] and row["ptBR"]:
            if row["ref_kind"] == "food" and row["ref"] not in concepts:
                raise I18nError(f"divergences: unknown food concept {row['ref']}")
            if row["ref_kind"] == "nutrient":
                for locale, label in (("pt-PT", row["ptPT"]), ("pt-BR", row["ptBR"])):
                    if glossary.get(locale, {}).get(row["ref"]) != label:
                        raise I18nError(
                            f"divergences: {row['ref']} {locale} label drifts "
                            f"from glossary ({label!r})"
                        )
            else:
                for locale, label in (("pt-PT", row["ptPT"]), ("pt-BR", row["ptBR"])):
                    if locale in active:
                        labels.append(_row("food", row["ref"], locale, "curated", label))

    # -- 6. gates (ADR-0006 §3.2, P7/P9) -------------------------------------
    table = _frame(labels)
    bad_status = table.filter(pl.col("status").eq("mt_unreviewed"))
    if bad_status.height:
        raise I18nError(
            f"mt_unreviewed labels must not enter core: "
            f"{bad_status.select(['ref_kind', 'ref', 'locale']).rows()[:5]}"
        )
    for locale in active:
        by_locale = table.filter(pl.col("locale").eq(locale))
        nutrient_tags = set(by_locale.filter(pl.col("ref_kind").eq("nutrient"))["ref"].to_list())
        expected_tags = tags
        if locale == "pt":
            # generic labels are forbidden for divergent refs (SPEC §7);
            # the regional variants carry those tagnames instead
            expected_tags = tags - {r["ref"] for r in divergences if r["ptPT"] and r["ptBR"]}
        missing_tags = expected_tags - nutrient_tags
        if missing_tags:
            raise I18nError(f"locale {locale}: missing nutrient labels {sorted(missing_tags)}")
        ok_share = (
            by_locale.filter(pl.col("status").is_in(_STATUS_OK)).height / by_locale.height
            if by_locale.height
            else 0.0
        )
        if ok_share < _STATUS_GATE:
            raise I18nError(
                f"locale {locale}: only {ok_share:.1%} labels are "
                f"native/official/curated (gate {_STATUS_GATE:.0%})"
            )
    for kind, ref in sorted(divergent_pt):
        pt_rows = table.filter(
            (pl.col("ref_kind").eq(kind)) & (pl.col("ref").eq(ref)) & (pl.col("locale").eq("pt"))
        )
        if pt_rows.height:
            raise I18nError(
                f"divergences: generic pt label used for divergent ref "
                f"{kind} {ref} (forbidden, SPEC §7)"
            )
        for variant in ("pt-PT", "pt-BR"):
            present = table.filter(
                (pl.col("ref_kind").eq(kind))
                & (pl.col("ref").eq(ref))
                & (pl.col("locale").eq(variant))
            )
            if not present.height:
                raise I18nError(f"divergences: {kind} {ref} lacks {variant} label")

    # -- 7. write the table (sorted -> deterministic, P5) --------------------
    frame = _frame(labels)
    frame.write_parquet(canonical_dir / "label.parquet")

    counts: dict[str, Any] = {
        "labels": len(labels),
        "vocab_en": len(vocab),
        "divergences": len(divergences),
        "reviewed": len(reviewed),
    }
    for locale in active:
        by_locale = frame.filter(pl.col("locale") == locale)
        counts[locale] = by_locale.height
        counts[f"{locale}_status"] = by_locale["status"].value_counts().rows()
    return counts


def normalize_label(text: str) -> str:
    """Normalize for search: transliterate ligatures, NFKD, strip marks,
    lowercase.

    ``cœur`` -> ``coeur``, ``açaí`` -> ``acai``, ``Água`` -> ``agua``,
    ``Straße`` -> ``strasse``. The transliteration map covers the common
    European ligatures (unified NFKD does not decompose them); one
    normalization serves every locale (the per-locale hook is the
    schema's).
    """
    translit = str.maketrans(_LIGATURES)
    decomposed = unicodedata.normalize("NFKD", text.translate(translit))
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return stripped.casefold()


def load_divergences(path: Path) -> list[dict[str, str]]:
    """Read i18n/divergences.csv; rows must be well-formed (P8/P9)."""
    if not path.is_file():
        raise I18nError(f"missing divergences file {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        lines = [ln for ln in handle if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    if reader.fieldnames != ["ref_kind", "ref", "ptPT", "ptBR", "enGB", "enUS"]:
        raise I18nError(f"{path}: header does not match expected columns")
    rows = [dict(row) for row in reader]
    for row in rows:
        if row["ref_kind"] not in ("food", "nutrient") or not row["ref"]:
            raise I18nError(f"{path}: malformed divergence row {row!r}")
        if not (row["ptPT"] and row["ptBR"]) and not (row["enGB"] and row["enUS"]):
            raise I18nError(f"{path}: divergence needs a pt or en pair, got {row!r}")
    return rows


def _load_reviewed(root: Path, active: list[str]) -> dict[tuple[str, str, str], str]:
    """Read i18n/labels/reviewed_<locale>.csv overrides (status curated)."""
    reviewed: dict[tuple[str, str, str], str] = {}
    labels_dir = root / "i18n" / "labels"
    for locale in active:
        path = labels_dir / f"reviewed_{locale}.csv"
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            lines = [ln for ln in handle if not ln.lstrip().startswith("#")]
        reader = csv.DictReader(lines)
        if reader.fieldnames != ["ref_kind", "ref", "label"]:
            raise I18nError(f"{path}: header does not match expected columns")
        for row in reader:
            if row["ref_kind"] not in ("food", "nutrient") or not row["ref"]:
                raise I18nError(f"{path}: malformed reviewed row {row!r}")
            _require_text(row["label"], f"reviewed {locale} {row['ref']}")
            reviewed[(row["ref_kind"], row["ref"], locale)] = row["label"]
    return reviewed


def _frame(labels: list[tuple[str, ...]]) -> pl.DataFrame:
    labels.sort(key=lambda row: (row[0], row[1], row[2]))
    data = {name: [row[i] for row in labels] for i, name in enumerate(LABEL_COLUMNS)}
    return pl.DataFrame(data, schema={name: pl.Utf8 for name in LABEL_COLUMNS})


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


_LIGATURES = {
    "œ": "oe",
    "Œ": "OE",
    "æ": "ae",
    "Æ": "AE",
    "ß": "ss",
}
