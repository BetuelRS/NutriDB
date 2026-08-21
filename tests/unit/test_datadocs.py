"""Tests for generated data documentation (SPEC §2)."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from nutridb.datadocs import DataDocsError, attributions, data_dictionary

if TYPE_CHECKING:
    from pathlib import Path


def _tiny_artifact(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE concept (concept_id TEXT NOT NULL, kind TEXT)")
    conn.execute("INSERT INTO concept VALUES ('nfx_A', 'food')")
    conn.commit()
    conn.close()


def test_data_dictionary_documents_tables(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.sqlite"
    _tiny_artifact(artifact)
    out = tmp_path / "data_dictionary.md"
    count = data_dictionary(artifact, out)
    assert count >= 1
    text = out.read_text(encoding="utf-8")
    assert "## `concept`" in text
    assert "`concept_id`" in text


def test_dictionary_fails_high_without_artifact(tmp_path: Path) -> None:
    with pytest.raises(DataDocsError):
        data_dictionary(tmp_path / "missing.sqlite", tmp_path / "out.md")


def test_attributions_renders_registry(tmp_path: Path) -> None:
    registry = {
        "sources": {
            "demo": {
                "id": "demo",
                "name": "Demo Source",
                "url": "https://example.org",
                "license_id": "CC0-1.0",
                "license_url": "https://spdx.org/licenses/CC0-1.0.html",
                "version": "1",
                "attribution_required": False,
                "commercial_use": True,
                "share_alike": False,
                "artifacts": ["core"],
                "files": [],
                "attribution": "Demo attribution line.",
            }
        }
    }
    out = tmp_path / "ATTRIBUTIONS.md"
    count = attributions(registry, out)
    assert count == 1
    text = out.read_text(encoding="utf-8")
    assert "Demo Source" in text and "CC0-1.0" in text


def test_attributions_fail_high_on_empty_registry(tmp_path: Path) -> None:
    with pytest.raises(DataDocsError):
        attributions({"sources": {}}, tmp_path / "ATTRIBUTIONS.md")
