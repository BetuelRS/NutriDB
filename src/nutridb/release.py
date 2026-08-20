"""Release manifest, checksum, SBOM and attestation writers (SPEC §2/P5/P6, ADR-0015).

Deterministic outputs (P5): ``<artifact>.manifest.json`` (schema
``release-1``), ``<artifact>.sbom.json`` (CycloneDX 1.6) and
``SHA256SUMS``. Non-deterministic by design (carries the temporal block):
``<artifact>.attestation.json`` (schema ``attestation-1``), Ed25519-signed
when ``NUTRIDB_SIGNING_KEY`` is set.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from nutridb import __version__
from nutridb.sbom import write_sbom
from nutridb.signing import SigningError, load_signing_key, sign_bytes
from nutridb.sources.registry import load_registry

__all__ = [
    "ReleaseError",
    "verify_release",
    "write_attestation",
    "write_release_metadata",
]

SIGNING_KEY_ENV = "NUTRIDB_SIGNING_KEY"
PUBLIC_KEY_ENV = "NUTRIDB_PUBLIC_KEY"


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
    sbom_path = Path(write_sbom(artifact, root, profile))
    checksums = artifact.parent / "SHA256SUMS"
    entries = {
        artifact.name: _sha256(artifact),
        manifest_path.name: _sha256(manifest_path),
        sbom_path.name: _sha256(sbom_path),
    }
    checksums.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(entries.items())),
        encoding="utf-8",
    )
    return {
        "manifest": str(manifest_path),
        "sbom": str(sbom_path),
        "checksums": str(checksums),
    }


def _git_metadata(root: Path) -> dict[str, str]:
    """Commit and branch of the repository root, best effort (P9: no failures)."""
    metadata: dict[str, str] = {}
    for name, args in (
        ("git_commit", ["rev-parse", "HEAD"]),
        ("git_branch", ["rev-parse", "--abbrev-ref", "HEAD"]),
    ):
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            metadata[name] = result.stdout.strip()
    return metadata


def _attestation_body(attestation: dict[str, Any]) -> str:
    """Deterministic JSON body of an attestation (signature slot nulled)."""
    body = dict(attestation)
    body["signature"] = None
    return json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_attestation(
    artifact: Path,
    root: Path,
    profile: str,
    qa_metrics: Path | None = None,
) -> dict[str, str]:
    """Write ``<artifact>.attestation.json`` (schema ``attestation-1``).

    The attestation carries the temporal build block (ADR-0015) and the
    Ed25519 signature of its own exact bytes when ``NUTRIDB_SIGNING_KEY``
    is set; a present-but-invalid key fails the build (P9).
    """
    if not artifact.is_file():
        raise ReleaseError(f"artifact missing: {artifact}")
    manifest = json.loads(artifact.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    sbom = json.loads(artifact.with_name(artifact.stem + ".sbom.json").read_text(encoding="utf-8"))
    checksums = artifact.parent / "SHA256SUMS"
    if not checksums.is_file():
        raise ReleaseError(f"checksums missing: {checksums}")
    digests: dict[str, str] = {
        "artifact": _sha256(artifact),
        "manifest": _sha256(artifact.with_suffix(".manifest.json")),
        "sbom": _sha256(artifact.with_name(artifact.stem + ".sbom.json")),
        "checksums": _sha256(checksums),
    }
    if qa_metrics is not None and qa_metrics.is_file():
        digests["qa_metrics"] = _sha256(qa_metrics)
    build_metadata: dict[str, Any] = {
        **_git_metadata(root),
        "uv_version": os.environ.get("UV_VERSION", ""),
        "host": platform.platform(),
        "python_version": platform.python_version(),
        "ci": os.environ.get("CI") == "true",
        "built_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
    }
    attestation: dict[str, Any] = {
        "schema": "attestation-1",
        "nutridb_version": __version__,
        "profile": profile,
        "artifact": artifact.name,
        "manifest_schema": manifest.get("schema"),
        "sbom_spec": sbom.get("specVersion"),
        "subject": [
            {"name": artifact.name, "sha256": _sha256(artifact)},
        ],
        "digests": digests,
        "build_metadata": build_metadata,
        "signature": None,
    }
    key_value = os.environ.get(SIGNING_KEY_ENV)
    if key_value:
        try:
            key = load_signing_key(key_value)
        except SigningError as exc:
            raise ReleaseError(f"{SIGNING_KEY_ENV} present but invalid: {exc}") from exc
        payload = _attestation_body(attestation)
        attestation["signature"] = {
            "algorithm": "Ed25519",
            "value": sign_bytes(payload.encode("utf-8"), key),
        }
    out = artifact.with_name(artifact.stem + ".attestation.json")
    out.write_text(
        json.dumps(attestation, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    signed = attestation["signature"] is not None
    return {
        "attestation": str(out),
        "signed": "yes" if signed else "no",
    }


def _read_sha256sums(checksums: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in checksums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        entries[name] = digest
    return entries


def verify_release(
    artifact: Path,
    public_key: str | None = None,
) -> dict[str, str]:
    """Verify a release directory: hashes, SBOM digests and signature (ADR-0015).

    Fails high (P9) on any mismatch. A signed attestation without a public
    key reports ``signature: unverified`` (warning, not failure).
    """
    if not artifact.is_file():
        raise ReleaseError(f"artifact missing: {artifact}")
    manifest = json.loads(artifact.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    sbom = json.loads(artifact.with_name(artifact.stem + ".sbom.json").read_text(encoding="utf-8"))
    attestation = json.loads(
        artifact.with_name(artifact.stem + ".attestation.json").read_text(encoding="utf-8")
    )
    checksums = artifact.parent / "SHA256SUMS"
    if not checksums.is_file():
        raise ReleaseError(f"checksums missing: {checksums}")

    actual = _sha256(artifact)
    if actual != manifest.get("sha256"):
        raise ReleaseError("artifact sha256 does not match manifest")
    root_hashes = sbom.get("metadata", {}).get("component", {}).get("hashes", [])
    if not any(h.get("alg") == "SHA-256" and h.get("content") == actual for h in root_hashes):
        raise ReleaseError("artifact sha256 does not match SBOM root component")
    entries = _read_sha256sums(checksums)
    if entries.get(artifact.name) != actual:
        raise ReleaseError("artifact sha256 does not match SHA256SUMS")
    if entries.get(artifact.with_suffix(".manifest.json").name) != _sha256(
        artifact.with_suffix(".manifest.json")
    ):
        raise ReleaseError("manifest sha256 does not match SHA256SUMS")
    sbom_path = artifact.with_name(artifact.stem + ".sbom.json")
    if entries.get(sbom_path.name) != _sha256(sbom_path):
        raise ReleaseError("sbom sha256 does not match SHA256SUMS")

    digests = attestation.get("digests", {})
    if digests.get("artifact") != actual:
        raise ReleaseError("artifact sha256 does not match attestation digests")
    if digests.get("manifest") != _sha256(artifact.with_suffix(".manifest.json")):
        raise ReleaseError("manifest sha256 does not match attestation digests")
    if digests.get("sbom") != _sha256(sbom_path):
        raise ReleaseError("sbom sha256 does not match attestation digests")
    if digests.get("checksums") != _sha256(checksums):
        raise ReleaseError("checksums sha256 does not match attestation digests")

    signature = attestation.get("signature")
    if signature is None:
        return {"signature": "unsigned"}
    if public_key is None:
        return {"signature": "unverified"}
    from nutridb.signing import load_public_key, verify_bytes

    try:
        key = load_public_key(public_key)
    except SigningError as exc:
        raise ReleaseError(str(exc)) from exc
    body = _attestation_body(attestation)
    if not verify_bytes(body.encode("utf-8"), signature["value"], key):
        raise ReleaseError("attestation signature verification failed")
    return {"signature": "verified"}
