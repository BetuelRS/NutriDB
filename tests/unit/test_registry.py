"""Unit tests for the source registry model and validation."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import pytest

from nutridb.paths import project_root
from nutridb.sources.registry import Registry, SourceEntry, load_registry, sha256_of

if TYPE_CHECKING:
    from pathlib import Path


def test_registry_loads_ciqual_from_disk() -> None:
    registry = load_registry()
    assert "ciqual" in registry.sources
    ciqual = registry.by_id("ciqual")
    assert ciqual.license_id == "etalab-2.0"
    assert ciqual.share_alike is False
    assert ciqual.commercial_use is True
    assert "core" in ciqual.artifacts


def test_registry_toml_is_parseable_and_schema_versioned() -> None:
    root = project_root()
    raw = tomllib.loads((root / "sources" / "registry.toml").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert "ciqual" in raw["sources"]


def test_unpinned_source_is_flagged() -> None:
    registry = load_registry()
    assert registry.by_id("ciqual").sha256 is None  # pinned during F1.0/ADR-0003


def test_bad_sha256_rejected() -> None:
    with pytest.raises(ValueError, match="sha256"):
        SourceEntry(
            id="x",
            name="x",
            url="https://example.com/x",
            license_id="etalab-2.0",
            license_url="https://example.com/lo",
            version="1",
            sha256="not-a-hash",
            artifacts=["core"],
        )


def test_odbl_source_cannot_target_artifacts() -> None:
    with pytest.raises(ValueError, match="ODbL"):
        SourceEntry(
            id="off",
            name="Open Food Facts",
            url="https://off.openfoodfacts.org/data",
            license_id="odbl",
            license_url="https://opendatacommons.org/licenses/odbl/",
            version="1",
            artifacts=["core"],
        )


def test_unknown_profile_rejected() -> None:
    with pytest.raises(ValueError, match="artifact profile"):
        SourceEntry(
            id="x",
            name="x",
            url="https://example.com/x",
            license_id="etalab-2.0",
            license_url="https://example.com/lo",
            version="1",
            artifacts=["super"],
        )


def test_compatible_with_filters_and_sorts(tmp_path: Path) -> None:
    registry = Registry(
        schema_version=1,
        sources={
            "zeta": SourceEntry(
                id="zeta",
                name="z",
                url="u",
                license_id="l",
                license_url="lu",
                version="1",
                artifacts=["core"],
            ),
            "alpha": SourceEntry(
                id="alpha",
                name="a",
                url="u",
                license_id="l",
                license_url="lu",
                version="1",
                artifacts=["core", "extended"],
            ),
            "none": SourceEntry(
                id="none",
                name="n",
                url="u",
                license_id="l",
                license_url="lu",
                version="1",
                artifacts=["extended"],
            ),
        },
    )
    assert [s.id for s in registry.compatible_with("core")] == ["alpha", "zeta"]
    assert [s.id for s in registry.compatible_with("extended")] == ["alpha", "none"]


def test_sha256_of_streams_content(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    target.write_bytes(b"hello world")
    assert sha256_of(target) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
