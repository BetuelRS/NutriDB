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

Emenda A8 (schema 4, searchability): each locale also has a trigram FTS
index (``label_fts_<locale>_tri``) for substring matching — queries whose
terms are all >= 3 characters run on the trigram index, shorter terms
fall back to the prefix index; ``search`` can restrict ``kind`` (food /
nutrient) and ``food_group`` (facet filter); ``foods_for_nutrient`` ranks
the foods carrying a nutrient by value.

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

__all__ = ["ApiError", "FoodValue", "SearchResult", "foods_for_nutrient", "search"]

_MAX_LIMIT = 100

_FFS5_ESCAPE = re.compile(r"[\"*]")

_TRIGRAM_MIN_TERM = 3


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


@dataclass(frozen=True)
class FoodValue:
    """One preferred value cell from ``mv_food_value`` (schema 3/4)."""

    concept_id: str
    label: str
    locale: str
    food_group: str
    nutrient_id: str
    value: float | None
    unit: str | None
    basis: str


def _chain(locale: str, locales_file: Path | None) -> tuple[str, ...]:
    if locales_file is None:
        from nutridb.paths import project_root

        locales_file = project_root() / "i18n" / "locales.toml"
    locales = load_locales(locales_file)
    chains = locales["chains"]
    if locale not in chains:
        raise ApiError(f"unknown locale {locale!r}")
    return (locale, *chains[locale])


def search(
    db_path: Path | str,
    query: str,
    locale: str,
    limit: int = 20,
    locales_file: Path | None = None,
    kind: str | None = None,
    food_group: str | None = None,
) -> list[SearchResult]:
    """Full-text search over labels; accent-insensitive, fallback-resolved.

    ``kind`` restricts to ``food`` or ``nutrient`` labels; ``food_group``
    facets on the concept's food group (only meaningful for foods). Terms
    of >= 3 characters run on the per-locale trigram index (substring
    matching); shorter terms fall back to the prefix index.
    """
    if not query.strip():
        return []
    if limit <= 0 or limit > _MAX_LIMIT:
        raise ApiError(f"limit must be in 1..{_MAX_LIMIT}, got {limit}")
    if kind is not None and kind not in ("food", "nutrient"):
        raise ApiError(f"kind must be 'food' or 'nutrient', got {kind!r}")
    terms = normalize_label(query).split()
    if not terms:
        return []
    if all(len(term) >= _TRIGRAM_MIN_TERM for term in terms):
        suffix = ""
        trigram = True
    else:
        suffix = "*"
        trigram = False
    match = " AND ".join(f'"{_FFS5_ESCAPE.sub("", term)}"{suffix}' for term in terms)

    conn = sqlite3.connect(db_path)
    try:
        chain = _chain(locale, locales_file)
        results: list[SearchResult] = []
        for candidate in chain:
            table = f"label_fts_{candidate.replace('-', '_')}"
            if trigram:
                table += "_tri"
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                continue
            sql = (
                f"SELECT l.ref_kind, l.ref, l.locale, l.status, l.text, f.rank "
                f"FROM {table} f JOIN label l ON l.rowid = f.rowid "
                f"WHERE {table} MATCH ? "
                f"AND (? IS NULL OR l.ref_kind = ?) "
                f"AND (? IS NULL OR EXISTS (SELECT 1 FROM concept c "
                f"WHERE c.concept_id = l.ref AND c.food_group = ?)) "
                f"ORDER BY f.rank LIMIT ?"
            )
            params: tuple[object, ...] = (match, kind, kind, food_group, food_group, limit)
            rows = conn.execute(sql, params).fetchall()
            results += [
                SearchResult(
                    ref_kind=r[0], ref=r[1], locale=r[2], status=r[3], text=r[4], score=r[5]
                )
                for r in rows
            ]
            if results:
                break  # first locale with hits wins; chain is consulted only on empty
        return _resolve_labels(conn, results, chain, limit)
    except sqlite3.OperationalError as exc:
        raise ApiError(f"FTS query failed: {exc}") from exc
    finally:
        conn.close()


def foods_for_nutrient(
    db_path: Path | str,
    nutrient_id: str,
    locale: str,
    limit: int = 20,
    locales_file: Path | None = None,
    food_group: str | None = None,
) -> list[FoodValue]:
    """Foods carrying a nutrient, ranked by value (per-100 g basis, schema 3).

    Walks the locale chain over the materialised ``mv_food_value`` rows
    (which exist in the source locales); the first locale with rows wins.
    """
    if limit <= 0 or limit > _MAX_LIMIT:
        raise ApiError(f"limit must be in 1..{_MAX_LIMIT}, got {limit}")
    conn = sqlite3.connect(db_path)
    try:
        chain = _chain(locale, locales_file)
        for candidate in chain:
            sql = (
                "SELECT concept_id, label, locale, food_group, nutrient_id, "
                "value, unit, basis FROM mv_food_value "
                "WHERE nutrient_id = ? AND locale = ? AND value IS NOT NULL "
                "AND (? IS NULL OR food_group = ?) "
                "ORDER BY value DESC LIMIT ?"
            )
            rows = conn.execute(
                sql, (nutrient_id, candidate, food_group, food_group, limit)
            ).fetchall()
            if rows:
                return [
                    FoodValue(
                        concept_id=r[0],
                        label=r[1],
                        locale=r[2],
                        food_group=r[3],
                        nutrient_id=r[4],
                        value=r[5],
                        unit=r[6],
                        basis=r[7],
                    )
                    for r in rows
                ]
        return []
    except sqlite3.OperationalError as exc:
        raise ApiError(f"mv_food_value query failed: {exc}") from exc
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
