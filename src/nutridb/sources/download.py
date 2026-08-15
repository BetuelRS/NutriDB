"""Download and hash verification for sources (SPEC §17.8, P5/P10).

Registry entries pin a sha256 by hand (data, reviewed in diff). `sync`
downloads when needed and refuses anything that is not pinned — fail high,
never a silent guess (P9). Sources that ship several official files (e.g.
CIQUAL's XML set) pin one sha256 per file under `files` in the registry.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from nutridb.paths import paths
from nutridb.sources.registry import Registry, SourceEntry, SourceFile, sha256_of

if TYPE_CHECKING:
    from http.client import HTTPResponse

__all__ = ["RequiresPin", "download", "fetch_unpinned", "sync_sources", "verify_or_download"]

log = structlog.get_logger()


class RequiresPin(Exception):
    """Raised when a source is not pinned in the registry."""


def _single_file(entry: SourceEntry) -> SourceFile:
    """The file a legacy single-file entry pins, or fail high (P9)."""
    if entry.files:
        raise RequiresPin(
            f"{entry.id}: pinned per-file hashes under 'files'; "
            f"use the per-file flow (no single 'sha256' pinned)."
        )
    if entry.sha256 is None:
        raise RequiresPin(
            f"{entry.id}: no sha256 pinned in sources/registry.toml. "
            f"Download '{entry.url}', compute sha256, add the 'sha256' field, "
            f"then re-run sync. Never pin a hash you have not reviewed."
        )
    return SourceFile(
        name=entry.filename or Path(entry.url).name or f"{entry.id}.bin",
        sha256=entry.sha256,
        url=entry.url,
    )


def cached_path(entry: SourceEntry, file: SourceFile | None = None) -> Path:
    """Expected location of a source dump in the cache."""
    cache = paths()["cache"]
    if file is not None:
        return cache / entry.id / file.name
    return cache / _single_file(entry).name


def _urlopen(url: str) -> HTTPResponse:
    request = urllib.request.Request(
        url, headers={"User-Agent": "nutridb/0.1 (+https://github.com/BetuelRS/NutriDB)"}
    )
    response: HTTPResponse = urllib.request.urlopen(request, timeout=120)
    return response


def _verify_or_download_one(entry: SourceEntry, file: SourceFile, *, force: bool) -> Path:
    """Verify one pinned file in the cache, downloading it when missing."""
    destination = cached_path(entry, file)
    url = file.url or entry.url
    if destination.is_file() and not force:
        actual = sha256_of(destination)
        if actual == file.sha256:
            log.info("cache_hit", source=entry.id, path=str(destination))
            return destination
        log.warning("hash_mismatch", source=entry.id, expected=file.sha256, actual=actual)
        destination.unlink()  # refuse to trust a corrupted file (P5)

    destination.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading", source=entry.id, url=url)
    with _urlopen(url) as response, destination.open("wb") as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)

    actual = sha256_of(destination)
    if actual != file.sha256:
        destination.unlink()
        raise ValueError(
            f"{entry.id}/{file.name}: hash mismatch after download — expected "
            f"{file.sha256}, got {actual}. The upstream file changed or the "
            f"registry is stale."
        )
    log.info("downloaded_ok", source=entry.id, file=file.name, sha256=actual)
    return destination


def download(entry: SourceEntry, *, force: bool = False) -> Path:
    """Download the source files into the cache; verify the pinned hashes.

    Unpinned sources raise :class:`RequiresPin` with instructions to pin.
    """
    files = entry.files or [_single_file(entry)]
    last: Path | None = None
    for file in files:
        last = _verify_or_download_one(entry, file, force=force)
    assert last is not None
    return last


def verify_or_download(entry: SourceEntry, *, force: bool = False) -> Path:
    """Return a byte-verified cached file for the source."""
    return download(entry, force=force)


def sync_sources(registry: Registry, source: str | None = None) -> None:
    """Synchronize the cache for the given (or all) registry sources."""
    entries = (
        [registry.by_id(source)]
        if source
        else sorted(registry.sources.values(), key=lambda s: s.id)
    )
    failures = 0
    for entry in entries:
        try:
            verify_or_download(entry)
        except RequiresPin as exc:
            log.error("not_pinned", source=entry.id)
            print(str(exc), file=sys.stderr)
            failures += 1
        except Exception as exc:
            log.error("sync_failed", source=entry.id, error=str(exc))
            failures += 1
    if failures:
        raise SystemExit(f"sync: {failures} source(s) failed to verify")


def fetch_unpinned(entry: SourceEntry) -> str:
    """Download a legacy single-file source to the cache and return its sha256.

    Used by `sources fetch` for sources that are not yet pinned: the hash is
    printed for the human to review and pin in the registry — the registry is
    never modified by tooling (P8). Multi-file sources already pin per file.
    """
    file = _single_file(entry)
    destination = cached_path(entry)
    if destination.is_file():
        return sha256_of(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _urlopen(file.url or entry.url) as response, destination.open("wb") as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)
    return sha256_of(destination)
