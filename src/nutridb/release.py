"""Release manifest and checksum writers (SPEC §2/P5/P6)."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from nutridb import __version__
from nutridb.sources.registry import load_registry

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["ReleaseError", "write_release_metadata"]


class ReleaseError(Exception):
    """Fatal release metadata inconsistency (P9)."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_release_metadata(
    artifact: Path,
    root: Path,
    profile: str,
    qa_metrics: Path | None = None,
) -> dict[str, str]:
    """Write a deterministic manifest and SHA256SUMS beside ``artifact``."""
    if not artifact.is_file():
        raise ReleaseError(f"artifact missing: {artifact}")
    registry = load_registry(root / "sources" / "registry.toml")
    sources: list[dict[str, Any]] = []
    for source in sorted(registry.sources.values(), key=lambda entry: entry.id):
        sources.append(
            {
                "id": source.id,
                "name": source.name,
                "version": source.version,
                "license_id": source.license_id,
                "license_url": source.license_url,
                "attribution_required": source.attribution_required,
                "attribution": source.attribution,
                "share_alike": source.share_alike,
                "commercial_use": source.commercial_use,
                "artifacts": sorted(source.artifacts),
                "files": [
                    {
                        "name": file.name,
                        "sha256": file.sha256,
                        "url": file.url,
                        "size": file.size,
                    }
                    for file in sorted(source.files, key=lambda item: item.name)
                ],
            }
        )
    manifest: dict[str, Any] = {
        "schema": "release-1",
        "nutridb_version": __version__,
        "artifact": artifact.name,
        "profile": profile,
        "sha256": _sha256(artifact),
        "sources": sources,
    }
    if qa_metrics is not None and qa_metrics.is_file():
        qa = json.loads(qa_metrics.read_text(encoding="utf-8"))
        manifest["qa"] = {"schema": qa.get("schema"), "counts": qa.get("counts")}

    manifest_path = artifact.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checksums = artifact.parent / "SHA256SUMS"
    entries = {
        artifact.name: _sha256(artifact),
        manifest_path.name: _sha256(manifest_path),
    }
    checksums.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(entries.items())),
        encoding="utf-8",
    )
    return {"manifest": str(manifest_path), "checksums": str(checksums)}
