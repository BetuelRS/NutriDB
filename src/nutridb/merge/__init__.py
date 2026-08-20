"""Merge stage: priorities, alternatives, divergences (SPEC §9, ADR-0007).

Reads the canonical dataset (``value``, ``concept``, ``label``) plus the
priority rules in ``mappings/source_priority.csv`` (P8: priorities are
pure data) and the human ``mappings/overrides.csv`` record, and writes
``build/canonical/mv_food_value.parquet``:

    one row per (concept_id, nutrient_id, locale, basis)
    preferred      the highest-priority candidate (measured > trace >
                   below_loq; then source_record_id asc — deterministic)
    alternatives   the non-preferred candidates, kept consultable
    divergence     measured preferred vs measured alternatives with
                   rel = |a-b| / max(|a|,|b|) >= 0.30 are flagged
                   (0/0 = 0); divergence_max = worst rel

Priority resolution per (locale, food_group, nutrient): the most specific
rule wins — (l,g,n) > (l,g,*) > (l,*,n) > (l,*,*). A locale without a
rule fails high (P9). No averaging between sources, ever (SPEC §9/P2):
an average of incompatible measurements is a third wrong measurement with
the appearance of consensus.

Overrides (SPEC §9): ``mappings/overrides.csv`` forces a value and
REQUIRES a filled justification column; the stage rejects overrides
without it or with unknown concept/nutrient/basis (fail high). An applied
override is a declared human decision: acquisition_type "declared",
justification recorded on the row.
"""

from __future__ import annotations

import csv
import json
from typing import TYPE_CHECKING, Any

import polars as pl

from nutridb.sources.registry import load_registry

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["MergeError", "load_priorities", "merge", "resolve_priority"]

# mv_food_value.parquet schema (canonical, consumed by `nutridb package`).
MV_COLUMNS = (
    "concept_id",
    "locale",
    "label",
    "food_group",
    "nutrient_id",
    "value",
    "unit",
    "value_type",
    "confidence_code",
    "acquisition_type",
    "source_id",
    "source_record_id",
    "below_loq_threshold",
    "basis",
    "alternatives",
    "divergence_flag",
    "divergence_max",
    "derivation_id",
    "override_justification",
)

DIVERGENCE_THRESHOLD = 0.30
_BASIS_OK = {"per_100g_edible", "per_100ml"}
_TYPE_RANK = {"measured": 0, "trace": 1, "below_loq": 2}
_MV_SCHEMA = {
    "concept_id": pl.Utf8,
    "locale": pl.Utf8,
    "label": pl.Utf8,
    "food_group": pl.Utf8,
    "nutrient_id": pl.Utf8,
    "value": pl.Float64,
    "unit": pl.Utf8,
    "value_type": pl.Utf8,
    "confidence_code": pl.Utf8,
    "acquisition_type": pl.Utf8,
    "source_id": pl.Utf8,
    "source_record_id": pl.Utf8,
    "below_loq_threshold": pl.Float64,
    "basis": pl.Utf8,
    "alternatives": pl.Utf8,
    "divergence_flag": pl.Boolean,
    "divergence_max": pl.Float64,
    "derivation_id": pl.Utf8,
    "override_justification": pl.Utf8,
}


class MergeError(Exception):
    """Fatal input inconsistency in the merge stage (fail high, P9)."""


def load_priorities(path: Path) -> list[dict[str, str]]:
    """Read mappings/source_priority.csv (SPEC §9, P8).

    Columns: locale, food_group, nutrient, source_order. ``source_order``
    is a '>' separated list of registry sources; wildcards are ``*``.
    Duplicate (locale, food_group, nutrient) keys fail high.
    """
    if not path.is_file():
        raise MergeError(f"missing priorities file {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        lines = [ln for ln in handle if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    if reader.fieldnames != ["locale", "food_group", "nutrient", "source_order"]:
        raise MergeError(f"{path}: header does not match expected columns")
    rules = [dict(row) for row in reader]
    seen: set[tuple[str, str, str]] = set()
    for rule in rules:
        key = (rule["locale"], rule["food_group"], rule["nutrient"])
        if key in seen:
            raise MergeError(f"{path}: duplicate rule {key!r}")
        seen.add(key)
        if not rule["source_order"].strip():
            raise MergeError(f"{path}: rule {key!r} has empty source_order")
    return rules


def resolve_priority(
    rules: list[dict[str, str]], locale: str, food_group: str, nutrient: str
) -> tuple[str, ...]:
    """Resolve the source order for a cell; most specific rule wins.

    (l,g,n) > (l,g,*) > (l,*,n) > (l,*,*); a locale without any rule
    fails high (P9).
    """
    specificity = {
        ("*", "*"): 0,
        (food_group, "*"): 1,
        ("*", nutrient): 2,
        (food_group, nutrient): 3,
    }
    best: tuple[int, dict[str, str]] | None = None
    for rule in rules:
        if rule["locale"] != locale:
            continue
        key = (rule["food_group"], rule["nutrient"])
        if key not in specificity:
            continue
        if best is None or specificity[key] > best[0]:
            best = (specificity[key], rule)
    if best is None:
        raise MergeError(
            f"locale {locale}: no priority rule (food_group={food_group!r}, nutrient={nutrient!r})"
        )
    return tuple(s for s in best[1]["source_order"].split(">") if s)


def merge(canonical_dir: Path, root: Path) -> dict[str, Any]:
    """Build ``mv_food_value.parquet`` from the canonical dataset; report."""
    required = [
        f.is_file()
        for f in (
            canonical_dir / "value.parquet",
            canonical_dir / "concept.parquet",
            canonical_dir / "label.parquet",
        )
    ]
    if not all(required):
        raise MergeError(
            "canonical dataset incomplete; run `uv run nutridb build` through the i18n stage first"
        )
    registry = load_registry(root / "sources" / "registry.toml")
    rules = load_priorities(root / "mappings" / "source_priority.csv")
    known = {s.id for s in registry.sources.values()}
    for rule in rules:
        for source in rule["source_order"].split(">"):
            if source not in known:
                raise MergeError(f"priorities: unknown source {source!r} in rule {rule!r}")

    values = pl.read_parquet(canonical_dir / "value.parquet")
    concepts = pl.read_parquet(canonical_dir / "concept.parquet")
    labels = (
        pl.read_parquet(canonical_dir / "label.parquet")
        .filter(pl.col("ref_kind") == "food")
        .select(
            pl.col("ref").alias("concept_id"),
            pl.col("locale").alias("locale"),
            pl.col("text").alias("label"),
        )
        .unique(subset=["concept_id", "locale"])
    )
    default_codes = _default_codes(root)
    values = values.filter(pl.col("source_nutrient_code").is_in(list(default_codes)))

    overrides = _load_overrides(root / "mappings" / "overrides.csv")
    concept_ids = set(concepts["concept_id"].to_list())
    with (root / "vocab" / "nutrients.csv").open(encoding="utf-8", newline="") as handle:
        nutrient_ids = {
            row["tagname"]
            for row in csv.DictReader(ln for ln in handle if not ln.lstrip().startswith("#"))
        }
    for row in overrides:
        if row["concept_id"] not in concept_ids:
            raise MergeError(f"overrides: unknown concept {row['concept_id']}")
        if row["nutrient_id"] not in nutrient_ids:
            raise MergeError(f"overrides: unknown nutrient {row['nutrient_id']}")
        if row["basis"] not in _BASIS_OK:
            raise MergeError(f"overrides: unknown basis {row['basis']!r}")

    frame = values.join(concepts.select(["concept_id", "food_group"]), on="concept_id")
    candidates_map: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in frame.rows(named=True):
        candidates_map.setdefault((r["concept_id"], r["nutrient_id"], r["basis"]), []).append(r)
    label_map: dict[str, list[tuple[str, str]]] = {}
    for r in labels.rows(named=True):
        label_map.setdefault(r["concept_id"], []).append((r["locale"], r["label"]))

    rows: list[tuple[object, ...]] = []
    for (concept_id, nutrient_id, basis), candidates in candidates_map.items():
        for locale, label in label_map.get(concept_id, ()):
            order = resolve_priority(rules, locale, candidates[0]["food_group"], nutrient_id)
            ranked = sorted(
                candidates,
                key=lambda r: (
                    _rank_source(order, r["source_id"]),
                    _TYPE_RANK.get(r["value_type"], 3),
                    r["source_record_id"],
                ),
            )
            preferred = ranked[0]
            alternatives = [
                {
                    "source_id": r["source_id"],
                    "source_record_id": r["source_record_id"],
                    "value": r["value"],
                    "unit": r["unit"],
                    "value_type": r["value_type"],
                    "derivation_id": r["derivation_id"],
                }
                for r in ranked[1:]
            ]
            flag, max_rel = _divergence(preferred, alternatives)
            override = next(
                (
                    o
                    for o in overrides
                    if (o["concept_id"], o["nutrient_id"], o["basis"])
                    == (concept_id, nutrient_id, basis)
                ),
                None,
            )
            if override is not None:
                value: float | None = float(override["value"])
                unit: str | None = override["unit"]
                acquisition: str | None = "declared"
                src: str | None = None
                rec: str | None = None
                justification: str | None = override["justification"]
            else:
                value, unit, acquisition, src, rec, justification = (
                    preferred["value"],
                    preferred["unit"],
                    preferred["acquisition_type"],
                    preferred["source_id"],
                    preferred["source_record_id"],
                    None,
                )
            rows.append(
                (
                    concept_id,
                    locale,
                    label,
                    preferred["food_group"],
                    nutrient_id,
                    value,
                    unit,
                    preferred["value_type"],
                    preferred["confidence_code"],
                    acquisition,
                    src,
                    rec,
                    preferred["below_loq_threshold"],
                    basis,
                    json.dumps(alternatives, ensure_ascii=False, sort_keys=True),
                    flag,
                    max_rel,
                    preferred["derivation_id"],
                    justification,
                )
            )

    rows.sort(key=lambda r: (r[0], r[4], r[1], r[13]))
    data = {name: [row[i] for row in rows] for i, name in enumerate(MV_COLUMNS)}
    pl.DataFrame(data, schema=_MV_SCHEMA).write_parquet(canonical_dir / "mv_food_value.parquet")

    return {
        "mv_rows": len(rows),
        "divergence_flag": sum(1 for row in rows if row[15]),
        "overrides": len(overrides),
        "locales": len({row[1] for row in rows}),
    }


def _rank_source(order: tuple[str, ...], source: str) -> int:
    try:
        return order.index(source)
    except ValueError:
        return len(order)


def _divergence(
    preferred: dict[str, Any], alternatives: list[dict[str, Any]]
) -> tuple[bool, float]:
    """Divergence of measured alternatives vs the measured preferred value.

    rel = |a-b| / max(|a|,|b|); 0/0 = 0. Only measured values count.
    """
    if preferred["value_type"] != "measured" or preferred["value"] is None:
        return False, 0.0
    max_rel = 0.0
    flag = False
    for alt in alternatives:
        if alt["value_type"] != "measured" or alt["value"] is None:
            continue
        denom = max(abs(alt["value"]), abs(preferred["value"]))
        rel = 0.0 if denom == 0 else abs(alt["value"] - preferred["value"]) / denom
        max_rel = max(max_rel, rel)
        flag = flag or rel >= DIVERGENCE_THRESHOLD
    return flag, max_rel


def _load_overrides(path: Path) -> list[dict[str, str]]:
    """Read mappings/overrides.csv; every row needs a filled justification."""
    if not path.is_file():
        raise MergeError(f"missing overrides file {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        lines = [ln for ln in handle if not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    if reader.fieldnames != [
        "concept_id",
        "nutrient_id",
        "basis",
        "value",
        "unit",
        "justification",
    ]:
        raise MergeError(f"{path}: header does not match expected columns")
    rows: list[dict[str, str]] = []
    for row in reader:
        if not row["justification"].strip():
            raise MergeError(f"{path}: override without justification: {row!r}")
        if not row["value"].strip() or not row["unit"].strip():
            raise MergeError(f"{path}: override without value/unit: {row!r}")
        try:
            float(row["value"])
        except ValueError as exc:
            raise MergeError(f"{path}: override value not a number: {row!r}") from exc
        rows.append(row)
    return rows


def _default_codes(root: Path) -> set[str]:
    """Default source nutrient codes per tagname (the mv view, ADR-0007)."""
    from nutridb.mappings import load_nutrient_mapping

    codes: set[str] = set()
    for source in _registry_sources(root):
        codes |= {
            row["nutrient_code"]
            for row in load_nutrient_mapping(root, source)
            if row["is_default"] == "true"
        }
    if not codes:
        raise MergeError("no default nutrient codes in the mappings")
    return codes


def _registry_sources(root: Path) -> list[str]:
    registry = load_registry(root / "sources" / "registry.toml")
    return sorted(s.id for s in registry.sources.values())
