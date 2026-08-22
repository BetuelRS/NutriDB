"""Read-only REST API over a packaged NutriDB artifact (SPEC §2, P5).

Standard library only (http.server + json). Endpoints:

    GET /openapi.json
    GET /api/v1/search?q=&locale=&limit=&kind=&food_group=
    GET /api/v1/nutrients/{nutrient_id}/foods?locale=&limit=&food_group=
    GET /api/v1/foods/{concept_id}?locale=
    GET /api/v1/health

Errors are JSON: {"error": "..."} with 400 (user) or 404 (not found).
The server never mutates the artifact: the SQLite connection opens in
read-only mode via the api layer.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from nutridb import __version__
from nutridb.api import ApiError, foods_for_nutrient, search

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_LIMIT = 100


def _food_values(db_path: Path, concept_id: str, locale: str) -> list[dict[str, Any]]:
    from nutridb.api import _chain, _open_readonly

    conn = _open_readonly(db_path)
    try:
        chain = _chain(locale, None)
        for candidate in chain:
            rows = conn.execute(
                "SELECT concept_id, label, locale, food_group, nutrient_id, "
                "value, unit, basis FROM mv_food_value "
                "WHERE concept_id = ? AND locale = ? AND value IS NOT NULL "
                "ORDER BY nutrient_id",
                (concept_id, candidate),
            ).fetchall()
            if rows:
                return [
                    {
                        "concept_id": r[0],
                        "label": r[1],
                        "locale": r[2],
                        "food_group": r[3],
                        "nutrient_id": r[4],
                        "value": r[5],
                        "unit": r[6],
                        "basis": r[7],
                    }
                    for r in rows
                ]
        return []
    finally:
        conn.close()


class NutriDBHandler(BaseHTTPRequestHandler):
    """JSON request dispatcher; db_path injected via server attribute."""

    server_version = f"NutriDB/{__version__}"

    # populated by make_server
    db_path: Path = Path("")

    def log_message(self, format: str, *args: Any) -> None:
        pass  # keep stdout quiet; structured logs belong to the operator

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        path = parsed.path.rstrip("/") or "/"
        handlers: dict[str, Callable[[], tuple[int, Any]]] = {
            "/openapi.json": self._openapi,
            "/api/v1/health": self._health,
        }
        try:
            if path == "/api/v1/search":
                self._json(*self._search(params))
            elif path.startswith("/api/v1/foods/") and len(path) > len("/api/v1/foods/"):
                self._json(*self._food(path.rsplit("/", 1)[1], params))
            elif path.startswith("/api/v1/nutrients/") and path.endswith("/foods"):
                nutrient_id = path[len("/api/v1/nutrients/") : -len("/foods")]
                self._json(*self._ranking(nutrient_id, params))
            elif path in handlers:
                self._json(*handlers[path]())
            else:
                self._json(404, {"error": f"unknown path {path}"})
        except ApiError as exc:
            self._json(400, {"error": str(exc)})

    def _search(self, params: dict[str, str]) -> tuple[int, Any]:
        query = params.get("q", "")
        locale = params.get("locale", "en")
        limit = int(params.get("limit", "20"))
        kind = params.get("kind") or None
        food_group = params.get("food_group") or None
        results = search(
            self.db_path,
            query,
            locale,
            limit=limit,
            kind=kind,
            food_group=food_group,
        )
        return 200, {"count": len(results), "results": [asdict(r) for r in results]}

    def _food(self, concept_id: str, params: dict[str, str]) -> tuple[int, Any]:
        locale = params.get("locale", "en")
        values = _food_values(self.db_path, concept_id, locale)
        if not values:
            return 404, {"error": f"no values for concept {concept_id!r} in {locale}"}
        return 200, {"concept_id": concept_id, "count": len(values), "values": values}

    def _ranking(self, nutrient_id: str, params: dict[str, str]) -> tuple[int, Any]:
        locale = params.get("locale", "en")
        limit = int(params.get("limit", "20"))
        food_group = params.get("food_group") or None
        rows = foods_for_nutrient(
            self.db_path,
            nutrient_id,
            locale,
            limit=limit,
            food_group=food_group,
        )
        return 200, {
            "nutrient_id": nutrient_id,
            "count": len(rows),
            "foods": [asdict(r) for r in rows],
        }

    def _health(self) -> tuple[int, Any]:
        return 200, {"status": "ok", "version": __version__}

    def _openapi(self) -> tuple[int, Any]:
        return 200, OPENAPI


OPENAPI: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {
        "title": "NutriDB REST API",
        "version": __version__,
        "description": (
            "Read-only access to a packaged NutriDB artifact. "
            "Every value keeps source-level provenance."
        ),
    },
    "paths": {
        "/api/v1/search": {
            "get": {
                "summary": "Full-text search across labels",
                "parameters": [
                    {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                    {
                        "name": "locale",
                        "in": "query",
                        "schema": {"type": "string", "default": "en"},
                    },
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20}},
                    {
                        "name": "kind",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["food", "nutrient"]},
                    },
                    {"name": "food_group", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "Search hits"}},
            }
        },
        "/api/v1/foods/{concept_id}": {
            "get": {
                "summary": "All preferred values for one food concept",
                "parameters": [
                    {
                        "name": "concept_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "locale",
                        "in": "query",
                        "schema": {"type": "string", "default": "en"},
                    },
                ],
                "responses": {
                    "200": {"description": "Value matrix row set"},
                    "404": {"description": "Unknown concept"},
                },
            }
        },
        "/api/v1/nutrients/{nutrient_id}/foods": {
            "get": {
                "summary": "Foods ranked by nutrient content",
                "parameters": [
                    {
                        "name": "nutrient_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "locale",
                        "in": "query",
                        "schema": {"type": "string", "default": "en"},
                    },
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20}},
                    {"name": "food_group", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "Ranked foods"}},
            }
        },
        "/api/v1/health": {
            "get": {"summary": "Liveness", "responses": {"200": {"description": "OK"}}}
        },
    },
}


def make_server(db_path: Path, host: str = "127.0.0.1", port: int = 8600) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (NutriDBHandler,), {"db_path": db_path})
    return ThreadingHTTPServer((host, port), handler)


def serve(db_path: Path, host: str = "127.0.0.1", port: int = 8600) -> None:
    httpd = make_server(db_path, host, port)
    print(f"NutriDB API serving {db_path.name} at http://{host}:{port} (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
