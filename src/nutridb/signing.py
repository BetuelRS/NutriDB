"""Ed25519 signing and verification for release attestations (ADR-0015).

Keys are read as PKCS8 PEM or raw base64 seeds (32 bytes). ``sign_bytes``
signs the exact bytes that are written to disk so verification covers the
file verbatim.
"""

from __future__ import annotations

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

__all__ = ["SigningError", "load_public_key", "load_signing_key", "sign_bytes", "verify_bytes"]


class SigningError(Exception):
    """Invalid signing key material (fail high, P9)."""


def load_signing_key(key_value: str) -> Ed25519PrivateKey:
    """Parse a PKCS8 PEM key or a raw base64 seed (32 bytes)."""
    if not key_value:
        raise SigningError("empty signing key")
    try:
        data = base64.b64decode(key_value, validate=True)
    except (ValueError, TypeError):
        data = b""
    if len(data) == 32:
        return Ed25519PrivateKey.from_private_bytes(data)
    try:
        key = serialization.load_pem_private_key(key_value.encode(), password=None)
    except (ValueError, TypeError) as exc:
        raise SigningError("invalid Ed25519 private key (expect PKCS8 PEM or base64 seed)") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError(f"expected Ed25519 private key, got {type(key).__name__}")
    return key


def load_public_key(key_value: str) -> Ed25519PublicKey:
    """Parse a PKCS8/SubjectPublicKeyInfo PEM public key."""
    try:
        key = serialization.load_pem_public_key(key_value.encode())
    except (ValueError, TypeError) as exc:
        raise SigningError("invalid Ed25519 public key (expect PEM)") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise SigningError(f"expected Ed25519 public key, got {type(key).__name__}")
    return key


def sign_bytes(payload: bytes, key: Ed25519PrivateKey) -> str:
    """Return the base64 Ed25519 signature of ``payload``."""
    return base64.b64encode(key.sign(payload)).decode("ascii")


def verify_bytes(payload: bytes, signature_b64: str, key: Ed25519PublicKey) -> bool:
    """Verify a base64 Ed25519 signature; returns False on mismatch."""
    try:
        key.verify(base64.b64decode(signature_b64), payload)
    except (InvalidSignature, ValueError):
        return False
    return True
