"""Determinism gate (SPEC P5): two consecutive full builds must be
byte-identical except for the temporal build_metadata block.

Usage: uv run python scripts/check_determinism.py
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(db: Path) -> Path:
    """Copy the database with build_metadata frozen to sentinel values."""
    target = db.with_name(db.name + ".norm")
    shutil.copyfile(db, target)
    conn = sqlite3.connect(target)
    try:
        for key, _ in conn.execute("SELECT key, value FROM build_metadata"):
            conn.execute(
                "UPDATE build_metadata SET value = ? WHERE key = ?",
                ("<deterministic>", key),
            )
        conn.commit()
    finally:
        conn.close()
    return target


def main() -> int:
    subprocess.run(["uv", "run", "nutridb", "build", "--full"], check=True, cwd=ROOT)
    artifact = next((ROOT / "build" / "artifacts").glob("nutridb-*.sqlite"))
    first = sha256(normalize(artifact))

    subprocess.run(["uv", "run", "nutridb", "build", "--full"], check=True, cwd=ROOT)
    second = sha256(normalize(artifact))

    if first != second:
        print(f"P5 FAIL: normalized artifacts differ\n  build1 {first}\n  build2 {second}")
        return 1
    print(f"P5 OK: two builds byte-identical (build_metadata excluded) {first}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
