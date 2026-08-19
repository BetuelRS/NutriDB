"""Unit tests for the content-addressed stage cache (P5, P10)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from nutridb.cache import (
    CacheError,
    fingerprint,
    populate_cache,
    refresh_from_cache,
    stage_cache_path,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_fingerprint_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    first.write_text("hello", encoding="utf-8")
    second = tmp_path / "b.txt"
    second.write_text("world", encoding="utf-8")
    assert fingerprint("0.1.0", [first, second]) == fingerprint("0.1.0", [second, first])
    assert fingerprint("0.1.0", [first]) != fingerprint("0.1.1", [first])


def test_fingerprint_changes_with_content(tmp_path: Path) -> None:
    file = tmp_path / "data.csv"
    file.write_text("a,b\n1,2\n", encoding="utf-8")
    before = fingerprint("0.1.0", [file])
    file.write_text("a,b\n1,3\n", encoding="utf-8")
    assert fingerprint("0.1.0", [file]) != before


def test_fingerprint_walks_directories_sorted(tmp_path: Path) -> None:
    directory = tmp_path / "intermediates"
    (directory / "ciqual").mkdir(parents=True)
    (directory / "ciqual" / "food.parquet").write_bytes(b"food")
    (directory / "ciqual" / "value.parquet").write_bytes(b"value")
    (directory / "insa").mkdir()
    (directory / "insa" / "food.parquet").write_bytes(b"food")
    one = fingerprint("0.1.0", [directory])
    (directory / "ciqual" / "extra.parquet").write_bytes(b"extra")
    assert fingerprint("0.1.0", [directory]) != one


def test_fingerprint_fails_high_on_missing_input(tmp_path: Path) -> None:
    with pytest.raises(CacheError, match="missing"):
        fingerprint("0.1.0", [tmp_path / "nope.parquet"])


def test_cache_roundtrip_and_refresh(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    live = tmp_path / "live"
    live.mkdir()
    (live / "value.parquet").write_bytes(b"v1")

    populate_cache(cache_root, "extract", "fp123", live)
    assert stage_cache_path(cache_root, "extract", "fp123").is_dir()

    (live / "value.parquet").write_bytes(b"v2")
    (live / "extra.parquet").write_bytes(b"new")
    refresh_from_cache(cache_root, live, "extract", "fp123")
    assert (live / "value.parquet").read_bytes() == b"v1"
    assert not (live / "extra.parquet").exists()


def test_refresh_from_cache_fails_high_when_missing(tmp_path: Path) -> None:
    live = tmp_path / "live"
    live.mkdir()
    with pytest.raises(CacheError, match="cached stage missing"):
        refresh_from_cache(tmp_path / "cache", live, "extract", "nope")
