"""Property tests (P5): two packages of the same input must be equivalent.

The artefact contains one temporal block by design (SPEC §16 / P5:
`build_metadata.built_at` and tool versions), so byte-equality is tested
for everything else: schema, every data table, FTS content and indexes.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from shutil import copyfile
from typing import TYPE_CHECKING, Any

import pytest

from nutridb.i18n import build as build_labels
from nutridb.package import package
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

_TEMPORAL_TABLES = {"build_metadata"}


@pytest.fixture()
def two_packages(tmp_path: Path) -> tuple[str, str]:
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for official, synthetic in _FIXTURE_MAP.items():
        copyfile(FIXTURE / synthetic, cache / official)
    extract(cache, tmp_path / "i")
    canonical = tmp_path / "c"
    transform(tmp_path / "i", canonical, ROOT)
    build_labels(canonical, ROOT)
    first = package(canonical, ROOT / "vocab", tmp_path / "a", ROOT)
    second = package(canonical, ROOT / "vocab", tmp_path / "b", ROOT)
    return str(first["path"]), str(second["path"])


def _snapshot(
    path: str,
) -> tuple[str, dict[str, list[tuple[Any, ...]] | None], dict[str, list[tuple[str, str]]]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    objects: dict[str, list[tuple[str, str]]] = {}
    for kind in ("table", "index", "view", "trigger"):
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE type = ? "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name",
            (kind,),
        ).fetchall()
        objects[kind] = [(row["name"], row["sql"]) for row in rows]
    data: dict[str, list[tuple[Any, ...]] | None] = {}
    for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','virtual') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall():
        name = row["name"]
        if name in _TEMPORAL_TABLES:
            data[name] = None
            continue
        if name.startswith("label_fts_"):
            try:
                data[name] = [
                    tuple(r) for r in conn.execute(f"SELECT * FROM {name} ORDER BY rowid")
                ]
            except sqlite3.OperationalError:
                data[name] = []
            continue
        data[name] = [tuple(r) for r in conn.execute(f"SELECT * FROM {name} ORDER BY rowid")]
    conn.close()
    return path, data, objects


def test_core_package_deterministic_except_temporal_block(two_packages: tuple[str, str]) -> None:
    first_path, second_path = two_packages
    _, data_a, objects_a = _snapshot(first_path)
    _, data_b, objects_b = _snapshot(second_path)

    assert objects_a == objects_b, "schema/index definitions differ between builds"
    for table in data_a:
        if data_a[table] is None:
            continue
        assert data_a[table] == data_b[table], f"{table} differs between builds"
    for table in data_b:
        assert table in data_a, f"{table} only exists in the second build"

    conn = sqlite3.connect(first_path)
    meta_a = dict(conn.execute("SELECT key, value FROM build_metadata").fetchall())
    conn.close()
    conn = sqlite3.connect(second_path)
    meta_b = dict(conn.execute("SELECT key, value FROM build_metadata").fetchall())
    conn.close()
    for iso in (meta_a["built_at"], meta_b["built_at"]):
        assert iso.endswith("+00:00")
        datetime.fromisoformat(iso)
    assert meta_a["nutridb_version"] == meta_b["nutridb_version"]
    assert meta_a["profile"] == meta_b["profile"] == "core"
