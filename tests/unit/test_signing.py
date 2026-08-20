"""Tests for Ed25519 signing helpers (ADR-0015)."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nutridb.signing import (
    SigningError,
    load_public_key,
    load_signing_key,
    sign_bytes,
    verify_bytes,
)


@pytest.fixture()
def key_pair() -> tuple[Ed25519PrivateKey, str, str]:
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return key, private_pem, public_pem


def test_sign_and_verify_roundtrip(key_pair: tuple[Ed25519PrivateKey, str, str]) -> None:
    _key, private_pem, public_pem = key_pair
    payload = b"attestation bytes"
    signature = sign_bytes(payload, load_signing_key(private_pem))
    assert verify_bytes(payload, signature, load_public_key(public_pem))


def test_verify_rejects_tampered_payload(key_pair: tuple[Ed25519PrivateKey, str, str]) -> None:
    _key, private_pem, public_pem = key_pair
    signature = sign_bytes(b"original", load_signing_key(private_pem))
    assert not verify_bytes(b"tampered", signature, load_public_key(public_pem))


def test_sign_with_base64_seed() -> None:
    seed = base64.b64encode(b"x" * 32).decode("ascii")
    key = load_signing_key(seed)
    assert verify_bytes(b"data", sign_bytes(b"data", key), key.public_key())


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-a-key",
        base64.b64encode(b"short").decode("ascii"),
        "-----BEGIN RSA PRIVATE KEY-----\nAAAA\n-----END RSA PRIVATE KEY-----",
    ],
)
def test_load_signing_key_rejects_bad_material(bad: str) -> None:
    with pytest.raises(SigningError):
        load_signing_key(bad)


def test_load_public_key_rejects_bad_material() -> None:
    with pytest.raises(SigningError):
        load_public_key("not-a-key")
