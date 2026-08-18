"""Public read API over a packaged artefact (SPEC §8 / §12, emenda A7).

F1 carries one public query: ``search`` — accent-insensitive, per locale,
resolving the locale fallback chain from ``i18n/locales.toml`` at runtime.
It queries the per-locale external-content FTS5 index on the normalized
label column (built by F1.7) and maps hits back to labels and concepts.

F4 (cross-lingual search, SPEC §7): the FTS pass still walks the fallback
chain (first locale with hits wins), but the returned label is resolved
through the query locale's chain — writing "chicken" in locale `es` finds
the concept whose display label resolves to the English name — and hits
are deduplicated by concept.

Everything here is read-only and immutable: the artefact never changes
after packaging (P5), so the API is a thin, deterministic lens.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nutridb.i18n import load_locales, normalize_label

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["ApiError", "SearchResult", "search"]

_MAX_LIMIT = 100

_FFS5_ESCAPE = re.compile(r"[\"*]")


class ApiError(Exception):
    """User-facing API error (locales, malformed queries)."""


@dataclass(frozen=True)
class SearchResult:
    """One label hit: the concept ref, the label itself and its provenance."""

    ref_kind: str
    ref: str
    locale: str
    status: str
    text: str
    score: float


def search(
    db_path: Path | str,
    query: str,
    locale: str,
    limit: int = 20,
    locales_file: Path | None = None,
) -> list[SearchResult]:
    """Full-text search over labels; accent-insensitive, fallback-resolved."""
    if not query.strip():
        return []
    if limit <= 0 or limit > _MAX_LIMIT:
        raise ApiError(f"limit must be in 1..{_MAX_LIMIT}, got {limit}")
    if locales_file is None:
        from nutridb.paths import project_root

        locales_file = project_root() / "i18n" / "locales.toml"
    locales = load_locales(locales_file)
    chains = locales["chains"]
    if locale not in chains:
        raise ApiError(f"unknown locale {locale!r}")
    terms = normalize_label(query).split()
    if not terms:
        return []
    match = " AND ".join(f'"{term}"*' for term in (_FFS5_ESCAPE.sub("", term) for term in terms))

    conn = sqlite3.connect(db_path)
    try:
        results: list[SearchResult] = []
        for candidate in (locale, *chains[locale]):
            table = f"label_fts_{candidate.replace('-', '_')}"
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                continue
            rows = conn.execute(
                f"SELECT l.ref_kind, l.ref, l.locale, l.status, l.text, f.rank "
                f"FROM {table} f JOIN label l ON l.rowid = f.rowid "
                f"WHERE {table} MATCH ? ORDER BY f.rank LIMIT ?",
                (match, limit),
            ).fetchall()
            results += [
                SearchResult(
                    ref_kind=r[0], ref=r[1], locale=r[2], status=r[3], text=r[4], score=r[5]
                )
                for r in rows
            ]
            if results:
                break  # first locale with hits wins; chain is consulted only on empty
        return _resolve_labels(conn, results, (locale, *chains[locale]), limit)
    except sqlite3.OperationalError as exc:
        raise ApiError(f"FTS query failed: {exc}") from exc
    finally:
        conn.close()


def _resolve_labels(
    conn: sqlite3.Connection,
    hits: list[SearchResult],
    chain: tuple[str, ...],
    limit: int,
) -> list[SearchResult]:
    """Resolve each hit's display label through the query locale chain
    (preferring the query locale) and deduplicate by concept (SPEC §7:
    cross-lingual search finds the concept, not the matched language)."""
    resolved: dict[tuple[str, str], SearchResult] = {}
    for hit in hits:
        if (hit.ref_kind, hit.ref) in resolved:
            continue
        best = hit
        for hop in chain:
            row = conn.execute(
                "SELECT locale, status, text FROM label "
                "WHERE ref_kind = ? AND ref = ? AND locale = ?",
                (hit.ref_kind, hit.ref, hop),
            ).fetchone()
            if row is not None:
                best = SearchResult(
                    ref_kind=hit.ref_kind,
                    ref=hit.ref,
                    locale=row[0],
                    status=row[1],
                    text=row[2],
                    score=hit.score,
                )
                break
        resolved[(hit.ref_kind, hit.ref)] = best
    ordered = sorted(resolved.values(), key=lambda r: r.score)
    return ordered[:limit]
