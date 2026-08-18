"""Shared test fixtures (synthetic, isolated; SPEC §17.7).

``sandbox_root``: a copy of the configuration-as-data directories
(mappings, sources, vocab, i18n) without ``mappings/links.csv`` — tests
must not consume the repository's real adjudication record (F3 gate).
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from nutridb.paths import project_root

if TYPE_CHECKING:
    from pathlib import Path

SANDBOX_DIRS = ("mappings", "sources", "vocab", "i18n")


def make_sandbox_root(base: Path) -> Path:
    """Configuration root without mappings/links.csv (P8 isolation)."""
    root = base / "root"
    for name in SANDBOX_DIRS:
        shutil.copytree(project_root() / name, root / name)
    links = root / "mappings" / "links.csv"
    if links.is_file():
        links.unlink()
    return root


@pytest.fixture()
def sandbox_root(tmp_path: Path) -> Path:
    return make_sandbox_root(tmp_path)
