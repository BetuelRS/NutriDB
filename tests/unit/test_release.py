"""Tests for deterministic release metadata."""

from __future__ import annotations

import json
from pathlib import Path

from nutridb.paths import project_root
from nutridb.release import write_release_metadata


def test_release_manifest_contains_registry_and_hashes(tmp_path: Path) -> None:
    artifact = tmp_path / "nutridb-core-0.1.0.sqlite"
    artifact.write_bytes(b"synthetic artifact")
    result = write_release_metadata(artifact, project_root(), "core")

    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["schema"] == "release-1"
    assert manifest["artifact"] == artifact.name
    assert manifest["profile"] == "core"
    assert {source["id"] for source in manifest["sources"]} == {"ciqual", "insa"}
    assert len(manifest["sha256"]) == 64
    checksums = Path(result["checksums"]).read_text(encoding="utf-8")
    assert artifact.name in checksums
    assert Path(result["manifest"]).name in checksums
