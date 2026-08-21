"""Generated data documentation (SPEC §2 deliverables).

- ``data_dictionary``: markdown table reference built from the packaged
  SQLite schema (PRAGMA table_info), one section per table.
- ``attributions``: markdown attributions page generated from the source
  registry (P6: licence and attribution per artefact).

Both outputs are deterministic given their inputs.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["DataDocsError", "attributions", "data_dictionary"]


class DataDocsError(Exception):
    """Missing artifact or registry (fail high, P9)."""


def data_dictionary(artifact_path: Path, out_path: Path) -> int:
    if not artifact_path.is_file():
        raise DataDocsError(f"artifact not found: {artifact_path}")
    conn = sqlite3.connect(f"file:{artifact_path}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'label_fts_%' AND name NOT LIKE '%_data' "
                "AND name NOT LIKE '%_idx' AND name NOT LIKE '%_docsize' "
                "AND name NOT LIKE '%_config' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        lines = [
            "# NutriDB data dictionary",
            "",
            "Generated from the packaged SQLite schema by",
            "`nutridb docs dictionary`. Do not edit by hand.",
            "",
        ]
        count = 0
        for table in tables:
            columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
            if not columns:
                continue
            rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            lines += [f"## `{table}`", "", f"Rows: {rows:,}", ""]
            lines += ["| # | column | type | notnull |", "|---|---|---|---|"]
            for position, name, col_type, notnull, _default, _pk in columns:
                lines.append(
                    f"| {position + 1} | `{name}` | {col_type or 'TEXT'} "
                    f"| {'yes' if notnull else ''} |"
                )
            lines.append("")
            count += 1
    finally:
        conn.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def attributions(registry_data: dict[str, Any], out_path: Path) -> int:
    sources = registry_data.get("sources", {})
    if not sources:
        raise DataDocsError("registry has no sources")
    lines = [
        "# Attributions",
        "",
        "Generated from `sources/registry.toml` by `nutridb docs attributions`.",
        "Each artefact carries these obligations per source (P6).",
        "",
    ]
    for source_id in sorted(sources):
        source = sources[source_id]
        files = source.get("files", [])
        file_hashes = ", ".join(
            f"`{item.get('name', '?')}`" for item in files if isinstance(item, dict)
        )
        lines += [
            f"## {source.get('name', source_id)} (`{source_id}`)",
            "",
            f"- Version: {source.get('version', '-')}",
            f"- Homepage: {source.get('url', '-')}",
            f"- Licence: `{source.get('license_id', '-')}` ({source.get('license_url', '-')})",
            f"- Attribution required: {str(source.get('attribution_required', False)).lower()}",
            f"- Commercial use allowed: {str(source.get('commercial_use', False)).lower()}",
            f"- Share-alike: {str(source.get('share_alike', False)).lower()}",
            f"- Allowed profiles: {', '.join(source.get('artifacts', []))}",
            f"- Pinned files: {file_hashes or '-'}",
            "",
            "> " + str(source.get("attribution", "")).replace("\n", " "),
            "",
        ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(sources)
