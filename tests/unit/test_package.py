"""Unit tests for core packaging (F2, SPEC §8, ADR-0005).

Builds the SQLite artefact over the synthetic-fixture canonical dataset
and asserts the §8 schema surface: central tables, external-content FTS5
per active locale, the materialized read table (one row per
(concept, nutrient, locale)), indexes, page size, VACUUM/ANALYZE effects
and build_metadata isolation.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from shutil import copyfile

import polars as pl
import pytest

from nutridb.derive import derive as run_derive
from nutridb.i18n import build as build_labels
from nutridb.merge import merge as run_merge
from nutridb.package import PackageError, package
from nutridb.paths import project_root
from nutridb.sources.ciqual import extract
from nutridb.transform import transform

FIXTURE = project_root() / "tests" / "fixtures" / "synthetic_ciqual"

_FIXTURE_MAP = {
    "alim_2025_11_03.xml": "alim_synthetic.xml",
    "alim_grp_2025_11_03.xml": "alim_grp_synthetic.xml",
    "compo_2025_11_03.xml": "compo_synthetic.xml",
    "const_2025_11_03.xml": "const_synthetic.xml",
    "sources_2025_11_03.xml": "sources_synthetic.xml",
}


def _prepare(base: Path, root: Path) -> tuple[Path, Path]:
    cache = base / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for official, synthetic in _FIXTURE_MAP.items():
        copyfile(FIXTURE / synthetic, cache / official)
    extract(cache, base / "i" / "ciqual")
    canonical = base / "c"
    transform(base / "i", canonical, root)
    build_labels(canonical, root)
    run_derive(canonical, root)
    run_merge(canonical, root)
    return canonical, root / "vocab"


def _open(artifact: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(artifact)
    conn.row_factory = sqlite3.Row
    return conn


def test_package_builds_artifact(tmp_path: Path, sandbox_root: Path) -> None:
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    info = package(canonical, vocab, tmp_path / "out", sandbox_root)
    assert info["artifact"] == "nutridb-core-0.1.0.sqlite"
    assert info["integrity"] == "ok"
    artifact = tmp_path / "out" / info["artifact"]
    assert artifact.is_file()
    assert info["size_bytes"] > 0
    assert info["page_size"] == 8192

    conn = _open(artifact)
    try:
        assert conn.execute("PRAGMA page_size").fetchone()[0] == 8192
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] != "wal"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        conn.close()


def test_schema_has_all_central_tables(tmp_path: Path, sandbox_root: Path) -> None:
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    info = package(canonical, vocab, tmp_path / "out", sandbox_root)
    conn = _open(tmp_path / "out" / info["artifact"])
    try:
        names = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for table in (
            "source",
            "coverage",
            "source_record",
            "concept",
            "concept_link",
            "concept_classification",
            "concept_facet",
            "label",
            "nutrient",
            "nutrient_relation",
            "value",
            "portion",
            "density",
            "derivation",
            "reference_value",
            "tombstone",
            "mv_food_value",
            "build_metadata",
        ):
            assert table in names, table
        virtual = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND sql LIKE 'CREATE VIRTUAL TABLE%'"
            ).fetchall()
        }
        assert {"label_fts_fr", "label_fts_en", "label_fts_pt_PT"} <= virtual
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'value'").fetchone()[0]
        assert "source_nutrient_code TEXT" in ddl
    finally:
        conn.close()


def test_rows_loaded_and_provenance_walkable(tmp_path: Path, sandbox_root: Path) -> None:
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    info = package(canonical, vocab, tmp_path / "out", sandbox_root)
    conn = _open(tmp_path / "out" / info["artifact"])
    try:
        assert conn.execute("SELECT count(*) FROM concept").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM value").fetchone()[0] == 8

        row = conn.execute(
            "SELECT * FROM mv_food_value WHERE nutrient_id = 'FASAT' AND locale = 'fr'"
        ).fetchone()
        assert row["value"] == 0.5  # AG stay in g (INFOODS unit, mapping factor 1)
        assert row["unit"] == "g"
        assert row["label"] == "Pastis"
        assert row["confidence_code"] == "A"

        provenance = conn.execute(
            "SELECT v.source_record_id, sr.record FROM value v "
            "JOIN source_record sr ON sr.source_record_id = v.source_record_id "
            "WHERE v.nutrient_id = 'WATER' AND v.value = 59.7"
        ).fetchone()
        assert '"teneur":"59,7"' in provenance["record"]

        fts = conn.execute(
            "SELECT count(*) FROM label_fts_en WHERE label_fts_en MATCH 'water'"
        ).fetchone()[0]
        assert fts >= 1
        accent_free = conn.execute(
            "SELECT count(*) FROM label_fts_fr WHERE label_fts_fr MATCH 'eau'"
        ).fetchone()[0]
        assert accent_free >= 1
    finally:
        conn.close()


def test_coverage_isolation_of_not_measured(tmp_path: Path, sandbox_root: Path) -> None:
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    info = package(canonical, vocab, tmp_path / "out", sandbox_root)
    conn = _open(tmp_path / "out" / info["artifact"])
    try:
        pairs = conn.execute(
            "SELECT count(*) FROM value v JOIN concept c ON c.concept_id = v.concept_id "
            "WHERE c.kind = 'food'"
        ).fetchone()[0]
        assert pairs == 8, "absence is never materialized per cell (D5)"
        assert conn.execute("SELECT count(*) FROM coverage").fetchone()[0] == 5
    finally:
        conn.close()


def test_mv_food_value_unique_per_food_nutrient_locale(tmp_path: Path, sandbox_root: Path) -> None:
    """Read table: exactly one row per (concept, nutrient, locale) (D7).

    The canonical `value` table keeps every method (P1); mv_food_value
    presents the default one: 327/328 (Reg. UE 1169/2011) over 332/333
    (Jones), 25000 (N x facteur de Jones) over 25003 (N x 6.25).
    """
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    info = package(canonical, vocab, tmp_path / "out", sandbox_root)
    conn = _open(tmp_path / "out" / info["artifact"])
    try:
        dup = conn.execute(
            "SELECT concept_id, nutrient_id, locale, count(*) FROM mv_food_value "
            "GROUP BY concept_id, nutrient_id, locale HAVING count(*) > 1"
        ).fetchall()
        assert dup == [], f"duplicate (concept, nutrient, locale) in mv_food_value: {dup}"

        codes = {
            row["source_nutrient_code"]
            for row in conn.execute("SELECT DISTINCT source_nutrient_code FROM value")
        }
        assert {"327", "333"} <= codes, "canonical value keeps every energy method (P1)"
        mv_energy = {
            row["nutrient_id"]
            for row in conn.execute("SELECT DISTINCT nutrient_id FROM mv_food_value")
        }
        assert "ENERC_KCAL" not in mv_energy, "Jones kcal (333) is not the default read value"
        assert "ENERC_KJ" in mv_energy
        locales = {
            row["locale"] for row in conn.execute("SELECT DISTINCT locale FROM mv_food_value")
        }
        assert locales == {"fr", "en"}
    finally:
        conn.close()


def test_build_metadata_isolated(tmp_path: Path, sandbox_root: Path) -> None:
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    first = Path(package(canonical, vocab, tmp_path / "a", sandbox_root)["path"])
    second = tmp_path / "b" / "nutridb-core-0.1.0.sqlite"
    second.parent.mkdir()
    package(canonical, vocab, second.parent, sandbox_root)
    conn = _open(first)
    try:
        meta_a = dict(conn.execute("SELECT key, value FROM build_metadata").fetchall())
    finally:
        conn.close()
    conn = _open(second)
    try:
        meta_b = dict(conn.execute("SELECT key, value FROM build_metadata").fetchall())
    finally:
        conn.close()
    assert set(meta_a) == set(meta_b)
    for iso in (meta_a["built_at"], meta_b["built_at"]):
        assert iso.endswith("+00:00")
        datetime.fromisoformat(iso)
    assert meta_a["schema_version"] == meta_b["schema_version"] == "4"
    assert meta_a["profile"] == "core"


def test_missing_label_fails_high(tmp_path: Path, sandbox_root: Path) -> None:
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    (canonical / "label.parquet").unlink()
    with pytest.raises(PackageError, match=r"label\.parquet missing"):
        package(canonical, vocab, tmp_path / "out", sandbox_root)


def test_invalid_acquisition_type_fails_high(tmp_path: Path, sandbox_root: Path) -> None:
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    values = pl.read_parquet(canonical / "value.parquet").with_columns(
        pl.lit("unknown").alias("acquisition_type")
    )
    values.write_parquet(canonical / "value.parquet")
    with pytest.raises(PackageError, match="acquisition_type"):
        package(canonical, vocab, tmp_path / "out", sandbox_root)


def test_incompatible_source_fails_high(tmp_path: Path, sandbox_root: Path) -> None:
    canonical, vocab = _prepare(tmp_path, sandbox_root)
    registry = sandbox_root / "sources" / "registry.toml"
    text = registry.read_text(encoding="utf-8").replace(
        'artifacts = ["core", "extended", "lite"]',
        'artifacts = ["extended", "lite"]',
    )
    registry.write_text(text, encoding="utf-8")
    with pytest.raises(PackageError, match="incompatible with profile 'core'"):
        package(canonical, vocab, tmp_path / "out", sandbox_root)
