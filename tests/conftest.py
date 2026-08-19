"""Shared test fixtures (synthetic, isolated; SPEC §17.7).

``sandbox_root``: a copy of the configuration-as-data directories
(mappings, sources, vocab, i18n) without ``mappings/links.csv`` — tests
must not consume the repository's real adjudication record (F3 gate) —
and with a synthetic ``i18n/divergences.csv``: the real file references
real concept ids that do not exist in synthetic fixtures, so the sandbox
derives the nutrient pt-PT/pt-BR divergence pairs from the glossaries
(F4 gate: divergent refs need their variant labels and no generic one).
"""

from __future__ import annotations

import csv
import shutil
from typing import TYPE_CHECKING

import pytest

from nutridb.paths import project_root

if TYPE_CHECKING:
    from pathlib import Path

SANDBOX_DIRS = ("mappings", "sources", "vocab", "i18n", "derivations")


def make_sandbox_root(base: Path) -> Path:
    """Configuration root without real adjudication/divergence records."""
    root = base / "root"
    for name in SANDBOX_DIRS:
        shutil.copytree(project_root() / name, root / name)
    links = root / "mappings" / "links.csv"
    if links.is_file():
        links.unlink()

    def _glossary(locale: str) -> dict[str, str]:
        path = root / "i18n" / "glossary" / f"{locale}.csv"
        lines = [ln for ln in path.open(encoding="utf-8") if not ln.lstrip().startswith("#")]
        return {r["tagname"]: r["label"] for r in csv.DictReader(lines)}

    pt_pt, pt_br = _glossary("pt-PT"), _glossary("pt-BR")
    rows = sorted((tag, pt_pt[tag], pt_br[tag]) for tag in pt_pt if pt_pt[tag] != pt_br[tag])
    with (root / "i18n" / "divergences.csv").open("w", encoding="utf-8", newline="") as fh:
        fh.write("# synthetic divergences (sandbox): nutrient pairs from the glossaries\n")
        writer = csv.writer(fh)
        writer.writerow(("ref_kind", "ref", "ptPT", "ptBR", "enGB", "enUS"))
        writer.writerows(("nutrient", tag, a, b, "", "") for tag, a, b in rows)
    return root


@pytest.fixture()
def sandbox_root(tmp_path: Path) -> Path:
    return make_sandbox_root(tmp_path)
