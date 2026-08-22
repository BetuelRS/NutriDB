"""Value-level diff between two packaged NutriDB artifacts (SPEC F8).

Compares the materialised ``mv_food_value`` read model of two builds and
reports added / removed / changed preferred values plus identity churn
(tombstones). Output: deterministic JSON report.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["DiffError", "diff_artifacts"]


class DiffError(Exception):
    """Unreadable artifact or missing table (fail high, P9)."""


def _load_rows(db_path: Path) -> dict[tuple[str, str], tuple[Any, ...]]:
    if not db_path.is_file():
        raise DiffError(f"artifact not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        try:
            rows = conn.execute(
                "SELECT concept_id, nutrient_id, locale, value, unit, source_id FROM mv_food_value"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise DiffError(f"{db_path}: {exc}") from exc
    finally:
        conn.close()
    out = {(r[0], r[1]): (r[2], r[3], r[4], r[5]) for r in rows}
    return out


def diff_artifacts(previous: Path, current: Path, max_samples: int = 20) -> dict[str, Any]:
    prev = _load_rows(previous)
    curr = _load_rows(current)

    def value_of(row: tuple[Any, ...]) -> tuple[Any, ...]:
        return row[1], row[2]  # value, unit

    keys_prev, keys_curr = set(prev), set(curr)
    added_keys = sorted(keys_curr - keys_prev)
    removed_keys = sorted(keys_prev - keys_curr)
    changed = []
    for key in sorted(keys_prev & keys_curr):
        if value_of(prev[key]) != value_of(curr[key]):
            changed.append(key)

    def sample_label(db: Path, concept_id: str) -> str:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT text FROM label WHERE ref_kind='food' AND ref=? AND locale IN ('en','fr') "
                "ORDER BY CASE locale WHEN 'en' THEN 0 ELSE 1 END LIMIT 1",
                (concept_id,),
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row else concept_id

    def entry(
        key: tuple[str, str], old: tuple[Any, ...] | None, new: tuple[Any, ...] | None
    ) -> dict[str, Any]:
        def cell(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
            return None if row is None else {"value": row[1], "unit": row[2]}

        return {
            "concept_id": key[0],
            "label": sample_label(current, key[0]),
            "nutrient_id": key[1],
            "old": cell(old),
            "new": cell(new),
        }

    report = {
        "previous": str(previous),
        "current": str(current),
        "rows_previous": len(prev),
        "rows_current": len(curr),
        "added_count": len(added_keys),
        "removed_count": len(removed_keys),
        "changed_count": len(changed),
        "samples": {
            "added": [entry(k, None, curr[k]) for k in added_keys[:max_samples]],
            "removed": [entry(k, prev[k], None) for k in removed_keys[:max_samples]],
            "changed": [entry(k, prev[k], curr[k]) for k in changed[:max_samples]],
        },
    }
    return report


def write_report(report: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
