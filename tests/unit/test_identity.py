"""Unit tests for deterministic eternal identifiers (F1.5, P4/P5).

The format is ULID-shaped: ``nfx_`` + 26 Crockford base32 chars (no
I/L/O/U). The value is a pure function of the seed: two builds of the
same input produce byte-identical identifiers.
"""

from __future__ import annotations

import re

from nutridb.identity import CROCKFORD_ALPHABET, ID_PREFIX, canonical_id, ulid

_ULID_RE = re.compile(rf"^{re.escape(ID_PREFIX)}[{CROCKFORD_ALPHABET}]{{26}}$")


def test_format_is_ulid_shaped() -> None:
    for seed in ("ciqual|food|24999", "ciqual|value|1000:327", "x", ""):
        assert _ULID_RE.fullmatch(f"{ID_PREFIX}{ulid(seed)}"), seed


def test_canonical_id_prefixed_and_namespaced() -> None:
    food = canonical_id("concept", "ciqual", "food", "24999")
    assert food.startswith(ID_PREFIX)
    assert len(food) == 4 + 26
    assert food != canonical_id("source_record", "ciqual", "food", "24999")
    assert food != canonical_id("concept", "ciqual", "food", "25000")


def test_deterministic() -> None:
    seed = "ciqual|food|açúcar"
    assert ulid(seed) == ulid(seed)


def test_unique_across_seeds() -> None:
    ids = {ulid(f"ciqual|value|{a}:{b}") for a in range(20) for b in range(20)}
    assert len(ids) == 400


def test_no_forbidden_chars() -> None:
    sample = [ulid(str(i)) for i in range(100)] + [
        canonical_id(k, "a", "b") for k in ("concept", "source_record", "tombstone")
    ]
    assert all("I" not in s and "L" not in s and "O" not in s and "U" not in s for s in sample)
