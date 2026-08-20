"""Tests for deterministic release metadata, SBOM and attestation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nutridb.paths import project_root
from nutridb.release import (
    SIGNING_KEY_ENV,
    ReleaseError,
    verify_release,
    write_attestation,
    write_release_metadata,
)


def _private_pem(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def _public_pem(key: Ed25519PrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )


def _build_release(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    artifact = tmp_path / "nutridb-core-0.1.0.sqlite"
    artifact.write_bytes(b"synthetic artifact")
    info = write_release_metadata(artifact, project_root(), "core")
    return artifact, info


def test_release_manifest_contains_registry_and_hashes(tmp_path: Path) -> None:
    artifact, result = _build_release(tmp_path)

    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["schema"] == "release-1"
    assert manifest["artifact"] == artifact.name
    assert manifest["profile"] == "core"
    assert {source["id"] for source in manifest["sources"]} == {"ciqual", "insa"}
    assert len(manifest["sha256"]) == 64
    checksums = Path(result["checksums"]).read_text(encoding="utf-8")
    assert artifact.name in checksums
    assert Path(result["manifest"]).name in checksums
    assert Path(result["sbom"]).name in checksums


def test_sbom_is_cyclonedx_and_deterministic(tmp_path: Path) -> None:
    artifact, result = _build_release(tmp_path)
    first = Path(result["sbom"]).read_bytes()

    _artifact, second_result = _build_release(tmp_path)
    assert Path(second_result["sbom"]).read_bytes() == first

    sbom = json.loads(first.decode("utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert sbom["serialNumber"].startswith("urn:uuid:")
    assert "timestamp" not in sbom.get("metadata", {})
    root = sbom["metadata"]["component"]
    assert root["type"] == "file"
    assert root["name"] == artifact.name
    source_ids = {c["bom-ref"] for c in sbom["components"]}
    assert source_ids == {"source:ciqual", "source:insa"}
    assert all(c["type"] == "data" for c in sbom["components"])
    assert all(c["licenses"] for c in sbom["components"])


def test_attestation_unsigned_without_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    artifact, _ = _build_release(tmp_path)
    info = write_attestation(artifact, project_root(), "core")

    attestation = json.loads(Path(info["attestation"]).read_text(encoding="utf-8"))
    assert attestation["schema"] == "attestation-1"
    assert attestation["signature"] is None
    assert info["signed"] == "no"
    assert attestation["subject"][0]["name"] == artifact.name
    assert attestation["digests"]["artifact"] == attestation["subject"][0]["sha256"]
    assert "built_at" in attestation["build_metadata"]


def test_attestation_signed_and_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(SIGNING_KEY_ENV, _private_pem(key))
    artifact, _ = _build_release(tmp_path)
    info = write_attestation(artifact, project_root(), "core")
    assert info["signed"] == "yes"

    attestation = json.loads(Path(info["attestation"]).read_text(encoding="utf-8"))
    assert attestation["signature"]["algorithm"] == "Ed25519"
    assert verify_release(artifact, public_key=_public_pem(key))["signature"] == "verified"
    assert verify_release(artifact)["signature"] == "unverified"


def test_attestation_invalid_key_fails_high(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "not-a-key")
    artifact, _ = _build_release(tmp_path)
    with pytest.raises(ReleaseError, match="invalid"):
        write_attestation(artifact, project_root(), "core")


def test_verify_release_fails_on_tampered_artifact(tmp_path: Path) -> None:
    artifact, _ = _build_release(tmp_path)
    write_attestation(artifact, project_root(), "core")
    artifact.write_bytes(b"tampered artifact")
    with pytest.raises(ReleaseError, match="does not match"):
        verify_release(artifact)


def test_verify_release_ok_with_env_public_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(SIGNING_KEY_ENV, _private_pem(key))
    artifact, _ = _build_release(tmp_path)
    write_attestation(artifact, project_root(), "core")
    assert verify_release(artifact, public_key=_public_pem(key))["signature"] == "verified"
