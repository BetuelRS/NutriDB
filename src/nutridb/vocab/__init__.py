"""Canonical vocabulary: CSV loaders and invariant checks (SPEC §5, P8).

The vocabulary is configuration-as-data, hand-maintained and frozen by
commit. `check_vocabulary` fails high (P9) on any structural violation;
the CLI exposes it as `nutridb vocab check`.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = ["VocabReport", "check_vocabulary", "load_csv"]

_TAGNAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_FACET_FILES = (
    "base_terms",
    "parts",
    "states",
    "cooking_methods",
    "media",
    "treatments",
    "qualifiers",
)
_FACET_NAME_COLUMNS = (
    "name_en",
    "name_pt",
    "name_fr",
    "name_es",
    "name_de",
    "name_it",
    "name_pt_PT",
    "name_pt_BR",
)
_REQUIRED_ABSENCE_TYPES = {
    "not_measured",
    "not_detected",
    "below_loq",
    "trace",
    "not_applicable",
    "assumed_zero",
}
_ENERGY_TAGS = {"ENERC_KJ", "ENERC_KCAL"}

SCHEMAS = {
    "nutrients.csv": ("tagname", "group", "name_en", "unit"),
    "nutrient_groups.csv": ("id", "name_en", "name_pt"),
    "units.csv": ("id", "name_en"),
    "value_types.csv": ("id", "name_en", "is_absence", "description"),
    "acquisition_types.csv": ("id", "name_en", "description"),
    "analytical_methods.csv": ("id", "name_en", "description"),
    "food_groups.csv": ("id", "name_en", "name_pt"),
    "nutrient_relation.csv": ("parent", "child"),
}
for _fname in _FACET_FILES:
    SCHEMAS[f"facets/{_fname}"] = ("id", *_FACET_NAME_COLUMNS)


@dataclass
class VocabReport:
    """Validation outcome: counts per file plus a list of human-readable errors."""

    counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_csv(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    """Read a vocabulary CSV: UTF-8, exact header, '#' comment lines skipped.

    Any deviation (missing file, wrong header, malformed line) is a hard
    error — configuration is data and must parse cleanly (P8/P9).
    """
    with path.open("r", encoding="utf-8", newline="") as handle:
        return _load_csv_handle(handle, path, columns)


def _load_csv_handle(handle: IO[str], path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    lines = [ln for ln in handle if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    if reader.fieldnames != list(columns):
        raise ValueError(
            f"{path}: header {reader.fieldnames!r} does not match expected {list(columns)!r}"
        )
    rows = [dict(row) for row in reader]
    for row in rows:
        if len(row) != len(columns):
            raise ValueError(
                f"{path}: row has {len(row)} fields, expected {len(columns)} "
                f"(unescaped comma in a cell?)"
            )
        if any(not row.get(col, "").strip() for col in columns):
            raise ValueError(f"{path}: empty cell in row {row!r}")
    return rows


def check_vocabulary(root: Path) -> VocabReport:
    """Validate every vocabulary file under `root/vocab` (fail high, P9)."""
    report = VocabReport()
    vocab_dir = root / "vocab"

    try:
        nutrients = load_csv(vocab_dir / "nutrients.csv", SCHEMAS["nutrients.csv"])
        groups = load_csv(vocab_dir / "nutrient_groups.csv", SCHEMAS["nutrient_groups.csv"])
        units = load_csv(vocab_dir / "units.csv", SCHEMAS["units.csv"])
        value_types = load_csv(vocab_dir / "value_types.csv", SCHEMAS["value_types.csv"])
        acquisition_types = load_csv(
            vocab_dir / "acquisition_types.csv", SCHEMAS["acquisition_types.csv"]
        )
        analytical_methods = load_csv(
            vocab_dir / "analytical_methods.csv", SCHEMAS["analytical_methods.csv"]
        )
        food_groups = load_csv(vocab_dir / "food_groups.csv", SCHEMAS["food_groups.csv"])
        relations = load_csv(vocab_dir / "nutrient_relation.csv", SCHEMAS["nutrient_relation.csv"])
    except FileNotFoundError as exc:
        report.errors.append(f"missing vocabulary file: {exc.filename}")
        return report
    except ValueError as exc:
        report.errors.append(f"malformed vocabulary: {exc}")
        return report

    report.counts["nutrients"] = len(nutrients)
    report.counts["nutrient_groups"] = len(groups)
    report.counts["units"] = len(units)
    report.counts["value_types"] = len(value_types)
    report.counts["acquisition_types"] = len(acquisition_types)
    report.counts["analytical_methods"] = len(analytical_methods)
    report.counts["food_groups"] = len(food_groups)
    report.counts["nutrient_relations"] = len(relations)

    for fname in _FACET_FILES:
        try:
            rows = load_csv(vocab_dir / "facets" / f"{fname}.csv", SCHEMAS[f"facets/{fname}"])
        except (FileNotFoundError, ValueError) as exc:
            report.errors.append(f"facets/{fname}: {exc}")
            continue
        report.counts[f"facets/{fname}"] = len(rows)
        _check_unique(report, f"facets/{fname} id", (row["id"] for row in rows))

    group_ids = {row["id"] for row in groups}
    unit_ids = {row["id"] for row in units}
    _check_unique(report, "nutrient_groups id", (row["id"] for row in groups))
    _check_unique(report, "units id", (row["id"] for row in units))
    _check_unique(report, "value_types id", (row["id"] for row in value_types))
    _check_unique(report, "acquisition_types id", (row["id"] for row in acquisition_types))
    _check_unique(report, "analytical_methods id", (row["id"] for row in analytical_methods))
    _check_unique(report, "food_groups id", (row["id"] for row in food_groups))

    tagnames = {row["tagname"] for row in nutrients}
    _check_unique(report, "nutrients tagname", (row["tagname"] for row in nutrients))
    units_by_tag: dict[str, str] = {}
    for row in nutrients:
        tag, group, unit = row["tagname"], row["group"], row["unit"]
        if not _TAGNAME_RE.match(tag):
            report.errors.append(f"nutrients: tagname {tag!r} violates INFOODS pattern")
        if group not in group_ids:
            report.errors.append(f"nutrients: tagname {tag!r} references unknown group {group!r}")
        if unit not in unit_ids:
            report.errors.append(f"nutrients: tagname {tag!r} references unknown unit {unit!r}")
        if tag in units_by_tag and units_by_tag[tag] != unit:
            report.errors.append(f"nutrients: tagname {tag!r} has conflicting units")
        units_by_tag[tag] = unit

    if not _ENERGY_TAGS.issubset(tagnames):
        report.errors.append(
            f"nutrients: required energy tags missing: {sorted(_ENERGY_TAGS - tagnames)}"
        )

    present_absence = {row["id"] for row in value_types if row["is_absence"] == "true"}
    missing_absence = _REQUIRED_ABSENCE_TYPES - present_absence
    if missing_absence:
        report.errors.append(f"value_types: missing absence types: {sorted(missing_absence)}")
    bad_flags = [r["id"] for r in value_types if r["is_absence"] not in ("true", "false")]
    if bad_flags:
        report.errors.append(f"value_types: is_absence must be true/false, got {bad_flags}")

    pairs: set[tuple[str, str]] = set()
    for row in relations:
        parent, child = row["parent"], row["child"]
        if parent not in tagnames:
            report.errors.append(f"nutrient_relation: parent {parent!r} not in nutrients")
        if child not in tagnames:
            report.errors.append(f"nutrient_relation: child {child!r} not in nutrients")
        if parent == child:
            report.errors.append(f"nutrient_relation: self relation {parent!r}")
        if (parent, child) in pairs:
            report.errors.append(f"nutrient_relation: duplicate pair ({parent}, {child})")
        pairs.add((parent, child))

    _check_acyclic(report, pairs, tagnames)
    return report


def _check_unique(report: VocabReport, what: str, values: Iterable[str]) -> None:
    seen: set[str] = set()
    collisions: list[str] = []
    for value in values:
        if value in seen:
            collisions.append(value)
        seen.add(value)
    if collisions:
        report.errors.append(f"{what}: duplicates {sorted(collisions)}")


def _check_acyclic(report: VocabReport, pairs: set[tuple[str, str]], nodes: set[str]) -> None:
    edges: dict[str, set[str]] = {}
    for parent, child in pairs:
        edges.setdefault(parent, set()).add(child)
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> None:
        if node in done:
            return
        if node in visiting:
            report.errors.append(f"nutrient_relation: cycle at {node!r}")
            return
        visiting.add(node)
        for child in edges.get(node, ()):
            visit(child)
        visiting.discard(node)
        done.add(node)

    for node in nodes:
        visit(node)
