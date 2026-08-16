"""Eternal deterministic identifiers (P4, P5).

Identifiers are ULID-shaped (26 chars, Crockford base32 — no I/L/O/U)
with the ``nfx_`` prefix, but derived deterministically from a content
seed instead of wall-clock time + randomness: two builds of the same
input must be byte-identical (P5), so the "timestamp" and "randomness"
fields both come from SHA-256 of the seed. The result is still a valid,
sortable-looking ULID string; it is not a real creation timestamp (the
eternal identity is the string, not its embedded clock).

IDs are assigned once by convention: the seed is *source + kind + ref*,
so every rebuild regenerates the same ULID for the same record without
any state (P10). Merges produce tombstones with a successor id (P4);
tombstoning itself is handled by the merge layer.
"""

from __future__ import annotations

import hashlib

__all__ = ["CROCKFORD_ALPHABET", "ID_PREFIX", "canonical_id", "ulid"]

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ID_PREFIX = "nfx_"
ULID_CHARS = 26


def ulid(seed: str) -> str:
    """Deterministic ULID-shaped 26-char string for `seed`."""
    digest = hashlib.sha256(f"{ID_PREFIX}:{seed}".encode()).digest()
    return _to_crockford(digest[:16])


def canonical_id(kind: str, *parts: str) -> str:
    """Deterministic canonical id: ``nfx_`` + ULID over kind + parts.

    ``kind`` separates id spaces (concept, source_record, value projection,
    derivation, tombstone); ``parts`` identify the record within the source
    (e.g. ``("ciqual", "food", "24999")``).
    """
    return f"{ID_PREFIX}{ulid('|'.join((kind, *parts)))}"


def _to_crockford(payload: bytes) -> str:
    value = int.from_bytes(payload, "big")
    chars: list[str] = []
    for _ in range(ULID_CHARS):
        chars.append(CROCKFORD_ALPHABET[value & 0b11111])
        value >>= 5
    return "".join(reversed(chars))
