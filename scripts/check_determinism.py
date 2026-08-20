"""Determinism gate (SPEC P5): two consecutive full builds must be
byte-identical except for the temporal build_metadata block.

The deterministic metadata files (manifest, SBOM, SHA256SUMS) embed
fingerprints of the physical artifact hash, which itself includes the
temporal block; the gate blanks those references before comparing, so
only deterministic content is compared.

Usage: uv run python scripts/check_determinism.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "<deterministic>"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_artifact(db: Path) -> Path:
    """Copy the database with build_metadata frozen to sentinel values."""
    target = db.with_name(db.name + ".norm")
    shutil.copyfile(db, target)
    conn = sqlite3.connect(target)
    try:
        for key, _ in conn.execute("SELECT key, value FROM build_metadata"):
            conn.execute(
                "UPDATE build_metadata SET value = ? WHERE key = ?",
                (SENTINEL, key),
            )
        conn.commit()
    finally:
        conn.close()
    return target


def _blank_node(node: Any, artifact_hash: str) -> Any:
    if isinstance(node, str):
        if node == artifact_hash:
            return SENTINEL
        return node
    if isinstance(node, list):
        return [_blank_node(item, artifact_hash) for item in node]
    if isinstance(node, dict):
        return {key: _blank_node(item, artifact_hash) for key, item in node.items()}
    return node


def normalize_metadata(path: Path, artifact_hash: str) -> Path:
    """Copy a JSON metadata file, blanking fingerprints of the artifact hash.

    The manifest ``sha256`` and the SBOM ``serialNumber`` (a UUID5 derived
    from the artifact hash) plus root ``hashes`` encode the physical
    artifact; they change with the temporal block and are blanked here.
    """
    target = path.with_name(path.name + ".norm")
    data = json.loads(path.read_text(encoding="utf-8"))
    data = _blank_node(data, artifact_hash)
    if isinstance(data.get("serialNumber"), str):
        data["serialNumber"] = SENTINEL
    target.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def normalize_checksums(path: Path) -> Path:
    """Copy SHA256SUMS with every digest blanked (they fingerprint files
    that embed the physical artifact hash)."""
    target = path.with_name(path.name + ".norm")
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.split("  ", 1)[1]
        lines.append(f"{SENTINEL}  {name}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _snapshot(
    artifact: Path,
    manifest: Path,
    sbom: Path,
    checksums: Path,
) -> dict[str, str]:
    artifact_hash = sha256(artifact)
    normalized: list[tuple[str, Path]] = [
        (artifact.name, normalize_artifact(artifact)),
        (manifest.name, normalize_metadata(manifest, artifact_hash)),
        (sbom.name, normalize_metadata(sbom, artifact_hash)),
        ("SHA256SUMS", normalize_checksums(checksums)),
    ]
    try:
        return {name: sha256(path) for name, path in normalized}
    finally:
        for _, path in normalized:
            path.unlink(missing_ok=True)


def main() -> int:
    subprocess.run(["uv", "run", "nutridb", "build", "--full"], check=True, cwd=ROOT)
    artifact = next((ROOT / "build" / "artifacts").glob("nutridb-*.sqlite"))
    manifest = artifact.with_suffix(".manifest.json")
    sbom = artifact.with_name(artifact.stem + ".sbom.json")
    checksums = ROOT / "build" / "artifacts" / "SHA256SUMS"

    first = _snapshot(artifact, manifest, sbom, checksums)
    subprocess.run(["uv", "run", "nutridb", "build", "--full"], check=True, cwd=ROOT)
    second = _snapshot(artifact, manifest, sbom, checksums)

    if first != second:
        print("P5 FAIL: normalized artifacts differ across builds")
        for name in first.keys() | second.keys():
            if first.get(name) != second.get(name):
                print(f"  {name} differs across builds")
        return 1
    print(
        f"P5 OK: two builds byte-identical "
        f"(temporal block and its fingerprints excluded) {first[artifact.name]}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
