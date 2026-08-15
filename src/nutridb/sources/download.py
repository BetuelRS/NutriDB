"""Download and hash verification for sources (SPEC §17.8, P5/P10).

Registry entries pin a sha256 by hand (data, reviewed in diff). `sync`
downloads when needed and refuses anything that is not pinned — fail high,
never a silent guess (P9).
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from nutridb.paths import paths
from nutridb.sources.registry import Registry, SourceEntry, sha256_of

if TYPE_CHECKING:
    from http.client import HTTPResponse

__all__ = ["RequiresPin", "download", "sync_sources", "verify_or_download"]

log = structlog.get_logger()


class RequiresPin(Exception):
    """Raised when a source is not pinned in the registry."""


def cached_path(entry: SourceEntry) -> Path:
    """Expected location of a source dump in the cache."""
    cache = paths()["cache"]
    if entry.filename:
        return cache / entry.filename
    name = Path(entry.url).name or f"{entry.id}.bin"
    return cache / name


def _urlopen(url: str) -> HTTPResponse:
    request = urllib.request.Request(
        url, headers={"User-Agent": "nutridb/0.1 (+https://github.com/BetuelRS/NutriDB)"}
    )
    response: HTTPResponse = urllib.request.urlopen(request, timeout=120)
    return response


def download(entry: SourceEntry, *, force: bool = False) -> Path:
    """Download the source file into the cache; verify the pinned hash.

    Unpinned sources raise :class:`RequiresPin` with instructions to pin.
    """
    if entry.sha256 is None:
        raise RequiresPin(
            f"{entry.id}: no sha256 pinned in sources/registry.toml. "
            f"Download '{entry.url}', compute sha256, add the 'sha256' field, "
            f"then re-run sync. Never pin a hash you have not reviewed."
        )
    destination = cached_path(entry)
    if destination.is_file() and not force:
        actual = sha256_of(destination)
        if actual == entry.sha256:
            log.info("cache_hit", source=entry.id, path=str(destination))
            return destination
        log.warning("hash_mismatch", source=entry.id, expected=entry.sha256, actual=actual)
        destination.unlink()  # refuse to trust a corrupted file (P5)

    destination.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading", source=entry.id, url=entry.url)
    with _urlopen(entry.url) as response, destination.open("wb") as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)

    actual = sha256_of(destination)
    if actual != entry.sha256:
        destination.unlink()
        raise ValueError(
            f"{entry.id}: hash mismatch after download — expected {entry.sha256}, "
            f"got {actual}. The upstream file changed or the registry is stale."
        )
    log.info("downloaded_ok", source=entry.id, sha256=actual)
    return destination


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
    """Download an unpinned source to the cache and return its sha256.

    Used by `sources fetch`: the hash is printed for the human to review and
    pin in the registry — the registry is never modified by tooling (P8).
    """
    destination = cached_path(entry)
    if destination.is_file():
        return sha256_of(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _urlopen(entry.url) as response, destination.open("wb") as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)
    return sha256_of(destination)
