"""Unit tests for project root discovery and cache path resolution."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from nutridb.paths import paths, project_root


def test_project_root_found_from_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NUTRIDB_ROOT", raising=False)
    root = project_root()
    assert (root / "SPEC.md").is_file()
    assert (root / "sources" / "registry.toml").is_file()


def test_nutridb_root_env_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "elsewhere"
    fake.mkdir()
    monkeypatch.setenv("NUTRIDB_ROOT", str(fake))
    assert project_root() == fake.resolve()


def test_missing_root_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NUTRIDB_ROOT", raising=False)
    outside = Path(tempfile.mkdtemp(prefix="nutridb-noroot-"))
    try:
        monkeypatch.setattr(os, "getcwd", lambda: outside)
        with pytest.raises(FileNotFoundError, match="NUTRIDB root not found"):
            project_root(module_path=outside / "pkg" / "mod.py")
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def test_module_anchor_finds_root_outside_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NUTRIDB_ROOT", raising=False)
    outside = Path(tempfile.mkdtemp(prefix="nutridb-cwd-"))
    try:
        monkeypatch.setattr(os, "getcwd", lambda: outside)
        root = project_root()
        assert (root / "SPEC.md").is_file()
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def test_paths_layout() -> None:
    layout = paths()
    root = layout["root"]
    assert layout["cache"] == root / "sources" / "cache"
    assert layout["registry"] == root / "sources" / "registry.toml"
    assert layout["build"] == root / "build"
    assert layout["unmapped"] == root / "mappings" / "_unmapped"
