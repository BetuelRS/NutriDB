"""Core packaging: canonical dataset -> nutridb-core-*.sqlite (SPEC §8, F1.7).

The artefact is a single immutable SQLite file: every §8 central table
(plus the frozen vocabulary reference tables and the F1 `coverage`
table), one external-content FTS5 index per locale with labels (plus a
trigram variant for substring search, schema 4, emenda A8), a
pre-computed denormalised read table (`mv_food_value`) for the explorer,
covering indexes for the read patterns, ``page_size`` tuned for
byte-range downloads, and ``ANALYZE`` at the end (P5: deterministic —
the only temporal block is `build_metadata`; no WAL, journal OFF; the
file is treated as immutable after build).

The ``rowid`` of `label` is the stable insertion order of the sorted
canonical table, so FTS rowids line up deterministically.
"""

from __future__ import annotations

import datetime as _dt
import platform
import sqlite3
from typing import TYPE_CHECKING, Any

import polars as pl

from nutridb import __version__
from nutridb.sources.registry import ArtifactProfile, load_registry
from nutridb.vocab import load_csv

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["PackageError", "package"]

PAGE_SIZE = 8192

# §8 central tables; empty ones in F1 keep a typed schema so the schema is
# complete and later phases only load data (SPEC §8 "o desenho fino é teu").
_SCHEMA = {
    "source": (
        "CREATE TABLE source (source_id TEXT NOT NULL, name TEXT NOT NULL, "
        "version TEXT NOT NULL, license_id TEXT NOT NULL, "
        "license_url TEXT NOT NULL, url TEXT NOT NULL, attribution TEXT)"
    ),
    "coverage": ("CREATE TABLE coverage (source_id TEXT NOT NULL, nutrient_id TEXT NOT NULL)"),
    "source_record": (
        "CREATE TABLE source_record (source_record_id TEXT PRIMARY KEY, "
        "source_id TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL, "
        "record TEXT NOT NULL)"
    ),
    "concept": (
        "CREATE TABLE concept (concept_id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
        "food_group TEXT NOT NULL)"
    ),
    "concept_link": (
        "CREATE TABLE concept_link (concept_id TEXT NOT NULL, "
        "source_record_id TEXT NOT NULL, status TEXT NOT NULL)"
    ),
    # -- empty in F1 (no FoodEx2/LanguaL/Wikidata codes yet) -------------------
    "concept_classification": (
        "CREATE TABLE concept_classification (concept_id TEXT NOT NULL, "
        "scheme TEXT NOT NULL, code TEXT NOT NULL, status TEXT NOT NULL)"
    ),
    "concept_facet": (
        "CREATE TABLE concept_facet (concept_id TEXT NOT NULL, facet TEXT NOT NULL, "
        "value TEXT NOT NULL, status TEXT NOT NULL)"
    ),
    "label": (
        "CREATE TABLE label (ref_kind TEXT NOT NULL, ref TEXT NOT NULL, "
        "locale TEXT NOT NULL, status TEXT NOT NULL, text TEXT NOT NULL, "
        "text_normalized TEXT NOT NULL)"
    ),
    "nutrient": (
        "CREATE TABLE nutrient (tagname TEXT PRIMARY KEY, grp TEXT NOT NULL, "
        "name_en TEXT NOT NULL, unit TEXT NOT NULL)"
    ),
    "nutrient_relation": (
        "CREATE TABLE nutrient_relation (parent TEXT NOT NULL, child TEXT NOT NULL)"
    ),
    "food_group": (
        "CREATE TABLE food_group (id TEXT PRIMARY KEY, name_en TEXT NOT NULL, "
        "name_pt TEXT NOT NULL)"
    ),
    "unit": ("CREATE TABLE unit (id TEXT PRIMARY KEY, name_en TEXT NOT NULL)"),
    "value_type": (
        "CREATE TABLE value_type (id TEXT PRIMARY KEY, name_en TEXT NOT NULL, "
        "is_absence INTEGER NOT NULL, description TEXT NOT NULL)"
    ),
    "acquisition_type": (
        "CREATE TABLE acquisition_type (id TEXT PRIMARY KEY, name_en TEXT NOT NULL, "
        "description TEXT NOT NULL)"
    ),
    "analytical_method": (
        "CREATE TABLE analytical_method (id TEXT PRIMARY KEY, name_en TEXT NOT NULL, "
        "description TEXT NOT NULL)"
    ),
    "value": (
        "CREATE TABLE value (concept_id TEXT NOT NULL, nutrient_id TEXT NOT NULL, "
        "value REAL, unit TEXT NOT NULL, value_type TEXT NOT NULL, "
        "acquisition_type TEXT, source_id TEXT NOT NULL, "
        "source_record_id TEXT NOT NULL, source_nutrient_code TEXT, "
        "n_samples REAL, standard_deviation REAL, min_value REAL, max_value REAL, "
        "analytical_method TEXT, confidence_code TEXT, derivation_id TEXT, "
        "basis TEXT NOT NULL, below_loq_threshold REAL)"
    ),
    "portion": (
        "CREATE TABLE portion (concept_id TEXT NOT NULL, measure TEXT NOT NULL, "
        "grams REAL NOT NULL, evidence TEXT NOT NULL)"
    ),
    "density": (
        "CREATE TABLE density (food_group TEXT NOT NULL, density_g_per_ml REAL NOT NULL, "
        "evidence TEXT NOT NULL)"
    ),
    "derivation": (
        "CREATE TABLE derivation (derivation_id TEXT PRIMARY KEY, formula TEXT, "
        "inputs TEXT, factors TEXT)"
    ),
    "reference_value": (
        "CREATE TABLE reference_value (nutrient_id TEXT NOT NULL, "
        "authority TEXT NOT NULL, age_min INTEGER, age_max INTEGER, sex TEXT, "
        "state TEXT, value REAL NOT NULL, unit TEXT NOT NULL)"
    ),
    "tombstone": (
        "CREATE TABLE tombstone (tombstone_id TEXT PRIMARY KEY, "
        "successor_id TEXT NOT NULL, reason TEXT NOT NULL)"
    ),
    # Materialized read table (SPEC §8/§9, ADR-0007): denormalized
    # convenience, built by the merge stage, never edited. One row per
    # (concept, nutrient, locale, basis) with the preferred value by
    # priority, the non-preferred sources kept as alternatives, and the
    # divergence signal for measured pairs rel >= 0.30.
    "mv_food_value": (
        "CREATE TABLE mv_food_value (concept_id TEXT NOT NULL, locale TEXT NOT NULL, "
        "label TEXT NOT NULL, food_group TEXT NOT NULL, nutrient_id TEXT NOT NULL, "
        "value REAL, unit TEXT, value_type TEXT NOT NULL, "
        "confidence_code TEXT, acquisition_type TEXT, source_id TEXT, "
        "source_record_id TEXT, below_loq_threshold REAL, "
        "basis TEXT NOT NULL, alternatives TEXT, divergence_flag INTEGER NOT NULL, "
        "divergence_max REAL, derivation_id TEXT, override_justification TEXT)"
    ),
    "build_metadata": ("CREATE TABLE build_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"),
}

# Explorer read patterns (SPEC §8): concept -> nutrients; nutrient -> concepts;
# FTS label lookups; provenance walk from a value cell.
_INDEXES = {
    "idx_concept_link": ("CREATE INDEX idx_concept_link ON concept_link (concept_id)"),
    "idx_label_ref": ("CREATE INDEX idx_label_ref ON label (ref_kind, ref, locale)"),
    "idx_label_norm": ("CREATE INDEX idx_label_norm ON label (locale, text_normalized)"),
    "idx_value_concept": ("CREATE INDEX idx_value_concept ON value (concept_id, nutrient_id)"),
    "idx_value_nutrient": ("CREATE INDEX idx_value_nutrient ON value (nutrient_id)"),
    "idx_value_record": ("CREATE INDEX idx_value_record ON value (source_record_id)"),
    "idx_record_kind": ("CREATE INDEX idx_record_kind ON source_record (kind, ref)"),
    "idx_coverage_nutrient": ("CREATE INDEX idx_coverage_nutrient ON coverage (nutrient_id)"),
    "idx_mv_food_value_nutrient": (
        "CREATE INDEX idx_mv_food_value_nutrient ON mv_food_value (nutrient_id)"
    ),
    "idx_mv_food_value_concept_locale": (
        "CREATE INDEX idx_mv_food_value_concept_locale "
        "ON mv_food_value (concept_id, locale, nutrient_id)"
    ),
}

_SCHEMA_VERSION = "4"


class PackageError(Exception):
    """Fatal input inconsistency while packaging (fail high, P9)."""


def package(
    canonical_dir: Path,
    vocab_dir: Path,
    out_dir: Path,
    root: Path,
    profile: str = ArtifactProfile.CORE,
) -> dict[str, Any]:
    """Build a licensed SQLite profile; return artefact information."""
    tables: dict[str, pl.DataFrame] = {
        name: pl.read_parquet(canonical_dir / f"{name}.parquet")
        for name in (
            "source",
            "coverage",
            "source_record",
            "concept",
            "concept_link",
            "value",
            "derivation",
            "portion",
            "density",
            "tombstone",
        )
    }
    label_path = canonical_dir / "label.parquet"
    if not label_path.is_file():
        raise PackageError("label.parquet missing; run `uv run nutridb i18n build` first")
    tables["label"] = pl.read_parquet(label_path)
    mv_path = canonical_dir / "mv_food_value.parquet"
    if not mv_path.is_file():
        raise PackageError("mv_food_value.parquet missing; run `uv run nutridb merge` first")
    tables["mv_food_value"] = pl.read_parquet(mv_path)
    _validate_profile_sources(tables["source"], root, profile)
    _validate_acquisition_types(tables["value"], tables["mv_food_value"], vocab_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / f"nutridb-{profile}-{__version__}.sqlite"
    if artifact.is_file():
        artifact.unlink()  # fresh build: no state leaks between runs (P10)

    conn = sqlite3.connect(artifact)
    try:
        conn.execute(f"PRAGMA page_size={PAGE_SIZE}")
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        for _name, ddl in _SCHEMA.items():
            conn.execute(ddl)
        _load(conn, tables)
        _load_vocabulary(conn, vocab_dir)
        _build_fts(conn, tables["label"])
        for _name, ddl in _INDEXES.items():
            conn.execute(ddl)
        _write_build_metadata(conn, profile)
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(artifact)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    if integrity != "ok":
        raise PackageError(f"SQLite integrity_check failed: {integrity}")

    counts = {name: frame.height for name, frame in tables.items()}
    return {
        "artifact": artifact.name,
        "path": str(artifact),
        "size_bytes": artifact.stat().st_size,
        "integrity": integrity,
        "tables": counts,
        "page_size": PAGE_SIZE,
    }


def _load(conn: sqlite3.Connection, tables: dict[str, pl.DataFrame]) -> None:
    for name, frame in tables.items():
        rows = frame.rows()
        conn.executemany(
            f"INSERT INTO {name} VALUES ({','.join('?' * len(frame.columns))})",
            rows,
        )


def _load_vocabulary(conn: sqlite3.Connection, vocab_dir: Path) -> None:
    nutrients = load_csv(vocab_dir / "nutrients.csv", ("tagname", "group", "name_en", "unit"))
    conn.executemany(
        "INSERT INTO nutrient (tagname, grp, name_en, unit) VALUES (?, ?, ?, ?)",
        [tuple(row.values()) for row in nutrients],
    )
    relations = load_csv(vocab_dir / "nutrient_relation.csv", ("parent", "child"))
    conn.executemany(
        "INSERT INTO nutrient_relation (parent, child) VALUES (?, ?)",
        [tuple(row.values()) for row in relations],
    )
    food_groups = load_csv(vocab_dir / "food_groups.csv", ("id", "name_en", "name_pt"))
    conn.executemany(
        "INSERT INTO food_group (id, name_en, name_pt) VALUES (?, ?, ?)",
        [tuple(row.values()) for row in food_groups],
    )
    units = load_csv(vocab_dir / "units.csv", ("id", "name_en"))
    conn.executemany(
        "INSERT INTO unit (id, name_en) VALUES (?, ?)",
        [tuple(row.values()) for row in units],
    )
    value_types = load_csv(
        vocab_dir / "value_types.csv", ("id", "name_en", "is_absence", "description")
    )
    conn.executemany(
        "INSERT INTO value_type (id, name_en, is_absence, description) VALUES (?, ?, ?, ?)",
        [
            (r["id"], r["name_en"], int(r["is_absence"] == "true"), r["description"])
            for r in value_types
        ],
    )
    acquisition = load_csv(vocab_dir / "acquisition_types.csv", ("id", "name_en", "description"))
    conn.executemany(
        "INSERT INTO acquisition_type (id, name_en, description) VALUES (?, ?, ?)",
        [tuple(row.values()) for row in acquisition],
    )
    methods = load_csv(vocab_dir / "analytical_methods.csv", ("id", "name_en", "description"))
    conn.executemany(
        "INSERT INTO analytical_method (id, name_en, description) VALUES (?, ?, ?)",
        [tuple(row.values()) for row in methods],
    )


def _validate_acquisition_types(
    values: pl.DataFrame, materialized: pl.DataFrame, vocab_dir: Path
) -> None:
    """Reject missing or uncontrolled acquisition types before release (P1/P9)."""
    allowed = {
        row["id"]
        for row in load_csv(vocab_dir / "acquisition_types.csv", ("id", "name_en", "description"))
    }
    for name, frame in (("value", values), ("mv_food_value", materialized)):
        nulls = frame.filter(pl.col("acquisition_type").is_null()).height
        if nulls:
            raise PackageError(f"{name}: {nulls} rows without acquisition_type (P1)")
        invalid = (
            frame.filter(~pl.col("acquisition_type").is_in(sorted(allowed)))
            .select("acquisition_type")
            .unique()
            .to_series()
            .to_list()
        )
        if invalid:
            raise PackageError(f"{name}: unknown acquisition_type values {invalid!r}")


def _validate_profile_sources(source_table: pl.DataFrame, root: Path, profile: str) -> None:
    """Apply the registry's per-artifact license gate before packaging (P6)."""
    if profile not in (
        ArtifactProfile.CORE,
        ArtifactProfile.EXTENDED,
        ArtifactProfile.LITE,
    ):
        raise PackageError(f"unknown artifact profile {profile!r}")
    registry = load_registry(root / "sources" / "registry.toml")
    source_ids = set(source_table["source_id"].to_list())
    compatible = {source.id for source in registry.compatible_with(profile)}
    incompatible = sorted(source_ids - compatible)
    if incompatible:
        raise PackageError(
            f"sources {incompatible!r} are incompatible with profile {profile!r}"
        )


def _build_fts(conn: sqlite3.Connection, labels: pl.DataFrame) -> None:
    locales = sorted(labels["locale"].unique().to_list())
    if not locales:
        raise PackageError("label table has no locales")
    for locale in locales:
        name = "label_fts_" + locale.replace("-", "_")
        conn.execute(
            "CREATE VIRTUAL TABLE "
            + name
            + " USING fts5(text, text_normalized, content='label', content_rowid='rowid')"
        )
        conn.execute(
            "INSERT INTO "
            + name
            + " (rowid, text, text_normalized) "
            + "SELECT rowid, text, text_normalized FROM label "
            + "WHERE locale = ? ORDER BY rowid",
            (locale,),
        )
        conn.execute(
            "CREATE VIRTUAL TABLE "
            + name
            + "_tri USING fts5(text, text_normalized, tokenize='trigram', "
            "content='label', content_rowid='rowid')"
        )
        conn.execute(
            "INSERT INTO "
            + name
            + "_tri (rowid, text, text_normalized) "
            + "SELECT rowid, text, text_normalized FROM label "
            + "WHERE locale = ? ORDER BY rowid",
            (locale,),
        )


def _write_build_metadata(conn: sqlite3.Connection, profile: str) -> None:
    metadata = {
        "built_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        "nutridb_version": __version__,
        "python_version": platform.python_version(),
        "polars_version": pl.__version__,
        "schema_version": _SCHEMA_VERSION,
        "profile": profile,
        "page_size": str(PAGE_SIZE),
    }
    conn.executemany(
        "INSERT INTO build_metadata (key, value) VALUES (?, ?)",
        list(metadata.items()),
    )
