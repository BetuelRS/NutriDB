"""SBOM writer — CycloneDX 1.6, deterministic (SPEC P5/P6, ADR-0015).

The SBOM covers the release artefact (root component) and every licensed
data source from the registry (one ``data`` component each, with SPDX
license id when known and an honest ``UNKNOWN`` otherwise). No timestamp
and a UUID5 serial number keep the file byte-deterministic for a given
artifact + registry.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import TYPE_CHECKING, Any

from nutridb import __version__
from nutridb.sources.registry import load_registry

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["SBOMError", "write_sbom"]

_SERIAL_NAMESPACE = "https://nutridb.openfood.dev/artifacts/"


class SBOMError(Exception):
    """Fatal SBOM inconsistency (P9)."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _license(license_id: str) -> dict[str, Any]:
    if license_id:
        return {"license": {"id": license_id}}
    return {"license": {"name": "UNKNOWN"}}


def write_sbom(artifact: Path, root: Path, profile: str) -> str:
    """Write ``<artifact>.sbom.json`` and return its path."""
    if not artifact.is_file():
        raise SBOMError(f"artifact missing: {artifact}")
    registry = load_registry(root / "sources" / "registry.toml")
    artifact_sha256 = _sha256(artifact)

    components: list[dict[str, Any]] = []
    for source in sorted(registry.sources.values(), key=lambda entry: entry.id):
        hashes = [
            {"alg": "SHA-256", "content": file.sha256}
            for file in sorted(source.files, key=lambda item: item.name)
        ]
        properties: list[dict[str, str]] = [
            {"name": "nutridb:source:id", "value": source.id},
            {"name": "nutridb:source:license_url", "value": source.license_url or ""},
            {
                "name": "nutridb:source:attribution_required",
                "value": str(source.attribution_required),
            },
            {"name": "nutridb:source:share_alike", "value": str(source.share_alike)},
            {"name": "nutridb:source:commercial_use", "value": str(source.commercial_use)},
        ]
        if source.attribution:
            properties.append({"name": "nutridb:source:attribution", "value": source.attribution})
        components.append(
            {
                "type": "data",
                "bom-ref": f"source:{source.id}",
                "name": source.name,
                "version": source.version,
                "licenses": [_license(source.license_id)],
                "hashes": hashes,
                "properties": properties,
            }
        )

    bom: dict[str, Any] = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:"
        + str(uuid.uuid5(uuid.NAMESPACE_URL, _SERIAL_NAMESPACE + artifact_sha256)),
        "version": 1,
        "metadata": {
            "tools": {
                "components": [{"type": "application", "name": "nutridb", "version": __version__}]
            },
            "component": {
                "type": "file",
                "bom-ref": f"artifact:{artifact.name}",
                "name": artifact.name,
                "version": __version__,
                "hashes": [{"alg": "SHA-256", "content": artifact_sha256}],
            },
            "properties": [{"name": "nutridb:profile", "value": profile}],
        },
        "components": components,
        "dependencies": [
            {
                "ref": f"artifact:{artifact.name}",
                "dependsOn": [
                    f"source:{source.id}"
                    for source in sorted(registry.sources.values(), key=lambda entry: entry.id)
                ],
            }
        ],
    }

    out = artifact.with_name(artifact.stem + ".sbom.json")
    out.write_text(
        json.dumps(bom, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(out)
