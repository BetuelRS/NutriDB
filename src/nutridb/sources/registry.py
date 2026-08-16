"""Source registry: the single source of truth for every data source (SPEC §14).

`sources/registry.toml` is hand-maintained data (P8) — license facts, URLs,
hashes and artifact destinations. This module only defines and validates it.
"""

from __future__ import annotations

import hashlib
import tomllib
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from nutridb.paths import paths

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["ArtifactProfile", "Registry", "SourceEntry", "SourceFile", "load_registry"]

_SHA256_LEN = 64


class SourceFile(BaseModel):
    """A single pinned file of a source, in the official distribution."""

    name: str
    sha256: str
    url: str | None = None
    size: int | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> SourceFile:
        if len(self.sha256) != _SHA256_LEN or any(
            c not in "0123456789abcdef" for c in self.sha256.lower()
        ):
            raise ValueError(f"{self.name}: sha256 must be a {_SHA256_LEN}-char hex string")
        return self


class ArtifactProfile(str):
    """Allowed artifact profiles for a source."""

    CORE = "core"
    EXTENDED = "extended"
    LITE = "lite"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return str.__str__(self)


class SourceEntry(BaseModel):
    """A single entry of the registry, mapping one source (e.g. ciqual)."""

    id: str
    name: str
    url: str
    license_id: str
    license_url: str
    version: str
    sha256: str | None = None
    filename: str | None = None
    files: list[SourceFile] = Field(default_factory=list)
    attribution_required: bool = True
    attribution: str | None = None
    share_alike: bool = False
    commercial_use: bool | None = None
    artifacts: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> SourceEntry:
        if self.sha256 is not None and (
            len(self.sha256) != _SHA256_LEN
            or any(c not in "0123456789abcdef" for c in self.sha256.lower())
        ):
            raise ValueError(f"{self.id}: sha256 must be a {_SHA256_LEN}-char hex string")
        if self.files and (self.sha256 is not None or self.filename is not None):
            raise ValueError(
                f"{self.id}: 'files' and legacy single-file fields "
                f"(sha256/filename) are mutually exclusive"
            )
        if self.files and not any(f.name for f in self.files):
            raise ValueError(f"{self.id}: files must have non-empty names")
        for artifact in self.artifacts:
            if artifact not in (
                ArtifactProfile.CORE,
                ArtifactProfile.EXTENDED,
                ArtifactProfile.LITE,
            ):
                raise ValueError(
                    f"{self.id}: unknown artifact profile {artifact!r} "
                    f"(expected core|extended|lite)"
                )
        if self.artifacts and self.license_id == "odbl":  # SPEC §4: ODbL never distributed
            raise ValueError(f"{self.id}: ODbL sources cannot target any artifact")
        return self


class Registry(BaseModel):
    """The loaded registry."""

    schema_version: int = 1
    sources: dict[str, SourceEntry]

    def by_id(self, source_id: str) -> SourceEntry:
        try:
            return self.sources[source_id]
        except KeyError:
            raise KeyError(f"source {source_id!r} not present in the registry") from None

    def compatible_with(self, profile: str) -> list[SourceEntry]:
        """Sources declared compatible with an artifact profile, sorted by id."""
        return sorted(
            (s for s in self.sources.values() if profile in s.artifacts),
            key=lambda s: s.id,
        )


def load_registry(path: Path | None = None) -> Registry:
    """Load and validate the registry, failing loudly on any inconsistency."""
    registry_path = path or paths()["registry"]
    try:
        with registry_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"registry not found at {registry_path}; "
            f"create it (see sources/registry.toml in SPEC §3)"
        ) from exc

    sources_raw = dict(raw.get("sources", {}))
    if not isinstance(sources_raw, dict) or not sources_raw:
        raise ValueError(f"{registry_path}: expected a non-empty [sources] table")

    sources: dict[str, SourceEntry] = {}
    for source_id, entry in sources_raw.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{registry_path}: entry {source_id!r} is not a table")
        sources[source_id] = SourceEntry.model_validate({**entry, "id": source_id})

    registry = Registry(schema_version=raw.get("schema_version", 1), sources=sources)
    return registry


def sha256_of(path: Path) -> str:
    """Compute the sha256 hex digest of a file, streaming."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
