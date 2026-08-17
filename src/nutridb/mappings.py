"""Source mappings: source codes -> canonical vocabulary (SPEC §5, P8).

Configuration-as-data under `mappings/`; every decision lives in a CSV and
is reviewable in diff. Loaders reuse the vocabulary CSV reader and fail high
on malformed files. `resolve_food_group` picks the finest level that has a
mapping row (levels 3 -> 2 -> 1, ADR-0005).

The mapping tables are per source (``mappings/nutrients/<source_id>.csv``,
``mappings/foodgroups/<source_id>.csv``) but the column contract is shared:
`nutrient_code` is the source-native code as text; food-group levels are
"1"|"2"|"3". The transform iterates sources with no per-source branches
(SPEC §16 F2, ADR-0005).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nutridb.vocab import load_csv

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "FOODGROUP_MAPPING_COLUMNS",
    "NUTRIENT_MAPPING_COLUMNS",
    "load_foodgroup_mapping",
    "load_nutrient_mapping",
    "resolve_food_group",
]

NUTRIENT_MAPPING_COLUMNS = (
    "nutrient_code",
    "tagname",
    "factor",
    "energy_method",
    "value_type_missing",
    "value_type_trace",
    "value_type_below_loq",
    "unit",
    "is_default",
)

FOODGROUP_MAPPING_COLUMNS = ("level", "code", "food_group")

# Resolution order: finest mapped level first (ADR-0005 §3.2).
_LEVELS = ("3", "2", "1")


def load_nutrient_mapping(root: Path, source_id: str) -> list[dict[str, str]]:
    """Source nutrient_code -> canonical nutrient rows per source."""
    return load_csv(root / "mappings" / "nutrients" / f"{source_id}.csv", NUTRIENT_MAPPING_COLUMNS)


def load_foodgroup_mapping(root: Path, source_id: str) -> dict[tuple[str, str], str]:
    """Source (level, code) -> canonical food_group per source."""
    rows = load_csv(
        root / "mappings" / "foodgroups" / f"{source_id}.csv", FOODGROUP_MAPPING_COLUMNS
    )
    return {(row["level"], row["code"]): row["food_group"] for row in rows}


def resolve_food_group(
    mapping: dict[tuple[str, str], str], group_path: dict[str, str]
) -> str | None:
    """Finest mapped level for one food; None when nothing matches (fail high upstream).

    The source's group hierarchy (ADR-0005 `food.group_path`, levels "1".."3")
    is resolved against the mapping table: a row for a level is a real
    decision; unmapped codes fall through to the next level up. Placeholder
    codes (e.g. CIQUAL all-zero) are only resolved if the mapping has a row
    for them — as data, not as code branches (P8).
    """
    for level in _LEVELS:
        code = group_path.get(level)
        if code is None:
            continue
        food_group = mapping.get((level, code))
        if food_group is not None:
            return food_group
    return None
