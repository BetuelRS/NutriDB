"""Filesystem layout helpers: locate the repository root and standard dirs."""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["paths", "project_root"]


def project_root(module_path: str | os.PathLike[str] = "") -> Path:
    """Return the repository root.

    Resolution order: NUTRIDB_ROOT env var, then walk up from the current
    working directory, then walk up from this module (installed/elsewhere).
    ``module_path`` is injectable for tests.
    """
    env = os.environ.get("NUTRIDB_ROOT")
    if env:
        return Path(env).resolve()

    anchors: list[Path] = [Path.cwd()]
    module = Path(module_path).resolve().parent if module_path else Path(__file__).resolve().parent
    anchors.append(module)
    for anchor in anchors:
        for candidate in (anchor, *anchor.parents):
            if (candidate / "SPEC.md").is_file() and (candidate / "sources").is_dir():
                return candidate
    raise FileNotFoundError(
        "NUTRIDB root not found: run from inside the repository or set NUTRIDB_ROOT"
    )


def paths() -> dict[str, Path]:
    """Return standard paths relative to the repository root."""
    root = project_root()
    return {
        "root": root,
        "sources": root / "sources",
        "cache": root / "sources" / "cache",
        "registry": root / "sources" / "registry.toml",
        "build": root / "build",
        "mappings": root / "mappings",
        "unmapped": root / "mappings" / "_unmapped",
        "vocab": root / "vocab",
    }
