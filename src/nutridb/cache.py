"""Content-addressed stage cache for the deterministic build (P5, P10).

Stages whose inputs are expensive to reprocess (extract, transform) can be
stored under ``build/cache/<stage>/<fingerprint>/``. The fingerprint is a
SHA-256 over every input: file contents (sources, intermediates), the
config CSV/TOML files the stage reads, the stage's own source modules and
the package version. Two builds with identical inputs produce the same
fingerprint, so the cached stage output is byte-identical to a fresh run
(P5); any change to an input produces a different fingerprint (new
directory, never mutated in place).

``build --full`` ignores the cache and recomputes every stage; the live
stage directories are refreshed from the cache by copy (never by move),
so a cached run is indistinguishable from a fresh one.
"""

from __future__ import annotations

import hashlib
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["CacheError", "fingerprint", "refresh_from_cache", "stage_cache_path"]


class CacheError(RuntimeError):
    """Raised when a cached stage cannot be trusted (fail high, P9)."""


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(version: str, files: list[Path]) -> str:
    """SHA-256 over the content of every input `files`.

    Missing inputs raise (fail high); directories are walked recursively
    with sorted entries so the hash is order-independent (P5). The package
    version is always mixed in: a code release invalidates every stage.
    """
    digest = hashlib.sha256(f"nutridb-stage-cache-v1:{version}\n".encode())
    for path in sorted(files):
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    digest.update(f"{child.relative_to(path)}:{_file_hash(child)}\n".encode())
        elif path.is_file():
            digest.update(f"{path.name}:{_file_hash(path)}\n".encode())
        else:
            raise CacheError(f"cache input missing: {path}")
    return digest.hexdigest()


def stage_cache_path(cache_root: Path, stage: str, value: str) -> Path:
    """Location of a cached stage output: ``<cache_root>/<stage>/<value>/``."""
    return cache_root / stage / value


def refresh_from_cache(cache_dir: Path, live_dir: Path, stage: str, value: str) -> None:
    """Copy the cached stage output into the live directory.

    The live directory is replaced wholesale: stale files from a previous
    (different-fingerprint) run must not leak into the build (P10).
    """
    cached = stage_cache_path(cache_dir, stage, value)
    if not cached.is_dir():
        raise CacheError(f"cached stage missing: {cached}")
    live_dir.mkdir(parents=True, exist_ok=True)
    for child in list(live_dir.iterdir()):
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for child in cached.iterdir():
        if child.is_dir():
            shutil.copytree(child, live_dir / child.name)
        else:
            shutil.copy2(child, live_dir / child.name)


def populate_cache(cache_dir: Path, stage: str, value: str, live_dir: Path) -> None:
    """Store the freshly produced stage output under its fingerprint."""
    cached = stage_cache_path(cache_dir, stage, value)
    if cached.is_dir():
        return
    cached.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(live_dir, cached)
