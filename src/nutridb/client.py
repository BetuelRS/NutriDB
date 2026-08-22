"""Public read client for packaged NutriDB artifacts (PyPI surface).

Example:
    from nutridb.client import NutriDBClient

    db = NutriDBClient("nutridb-core-0.1.0.sqlite")
    hits = db.search("leite", locale="pt", limit=5)
    food = db.food_values(hits[0].ref)
    rich = db.foods_for_nutrient("VITC", locale="pt", limit=10)

Read-only: the SQLite connection is opened in immutable read-only mode and
every method returns plain dictionaries.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from nutridb.api import ApiError, _open_readonly, foods_for_nutrient, search

__all__ = ["NutriDBClient"]


class NutriDBClient:
    """Convenience wrapper over the read-only api layer."""

    def __init__(self, artifact: str | Path, locales_file: Path | None = None) -> None:
        self.path = Path(artifact)
        if not self.path.is_file():
            raise FileNotFoundError(f"artifact not found: {self.path}")
        self.locales_file = locales_file
        self._conn = _open_readonly(self.path)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> NutriDBClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def available_locales(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'label_fts_%' AND name NOT LIKE '%_tri'"
        ).fetchall()
        return sorted(name[0].removeprefix("label_fts_").replace("_", "-") for name in rows)

    def search(
        self,
        query: str,
        locale: str = "en",
        limit: int = 20,
        kind: str | None = None,
        food_group: str | None = None,
    ) -> list[dict[str, Any]]:
        results = search(
            self.path,
            query,
            locale,
            limit=limit,
            locales_file=self.locales_file,
            kind=kind,
            food_group=food_group,
        )
        return [asdict(item) for item in results]

    def food_values(self, concept_id: str) -> dict[str, Any]:
        """Preferred values for one concept; first locale with rows wins."""
        for locale in ("en", "fr", "pt"):
            rows = self._conn.execute(
                "SELECT nutrient_id, value, unit, value_type, confidence_code, "
                "source_id, source_record_id, basis FROM mv_food_value "
                "WHERE concept_id = ? AND locale = ? ORDER BY nutrient_id",
                (concept_id, locale),
            ).fetchall()
            if rows:
                columns = [
                    "nutrient_id",
                    "value",
                    "unit",
                    "value_type",
                    "confidence_code",
                    "source_id",
                    "source_record_id",
                    "basis",
                ]
                return {
                    "concept_id": concept_id,
                    "locale": locale,
                    "values": [dict(zip(columns, row, strict=True)) for row in rows],
                }
        raise ApiError(f"no values for concept {concept_id!r}")

    def foods_for_nutrient(
        self,
        nutrient_id: str,
        locale: str = "en",
        limit: int = 20,
        food_group: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = foods_for_nutrient(
            self.path,
            nutrient_id,
            locale,
            limit=limit,
            locales_file=self.locales_file,
            food_group=food_group,
        )
        return [asdict(item) for item in rows]
