"""Source mappings: source codes -> canonical vocabulary (SPEC §5, P8).

Configuration-as-data under `mappings/`; every decision lives in a CSV and
is reviewable in diff. Loaders reuse the vocabulary CSV reader and fail high
on malformed files. `resolve_food_group` picks the finest non-placeholder
level that has a mapping row (grp/ssgrp/ssssgrp).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nutridb.vocab import load_csv

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "MAPPING_FILES",
    "PLACEHOLDER_GROUP_CODES",
    "load_foodgroup_mapping",
    "load_nutrient_mapping",
    "resolve_food_group",
]

MAPPING_FILES = {
    "nutrients/ciqual.csv": (
        "const_code",
        "tagname",
        "factor",
        "energy_method",
        "value_type_missing",
        "value_type_trace",
        "value_type_below_loq",
        "unit",
        "is_default",
    ),
    "foodgroups/ciqual.csv": ("level", "code", "food_group"),
}

PLACEHOLDER_GROUP_CODES = {"00", "0000", "000000"}
_LEVELS = ("ssssgrp", "ssgrp", "grp")


def load_nutrient_mapping(root: Path) -> list[dict[str, str]]:
    """CIQUAL const_code -> canonical nutrient rows (mappings/nutrients/ciqual.csv)."""
    return load_csv(
        root / "mappings" / "nutrients" / "ciqual.csv", MAPPING_FILES["nutrients/ciqual.csv"]
    )


def load_foodgroup_mapping(root: Path) -> dict[tuple[str, str], str]:
    """CIQUAL (level, code) -> canonical food_group (mappings/foodgroups/ciqual.csv)."""
    rows = load_csv(
        root / "mappings" / "foodgroups" / "ciqual.csv", MAPPING_FILES["foodgroups/ciqual.csv"]
    )
    return {(row["level"], row["code"]): row["food_group"] for row in rows}


def resolve_food_group(
    mapping: dict[tuple[str, str], str], alim: dict[str, str | None]
) -> str | None:
    """Finest mapped level for one food; None when nothing matches (fail high upstream).

    The CIQUAL dump fills every food with all three levels; all-zero codes
    ('00'/'0000'/'000000') mean "no finer group in the source". The mapping
    table is the authority: a row for ('grp', '00') is a real decision
    ("sem grupo na fonte" -> other); unmapped codes fall through to the
    next level up.
    """
    for level in _LEVELS:
        code = alim.get(f"alim_{level}_code")
        if code is None:
            continue
        food_group = mapping.get((level, code))
        if food_group is not None:
            return food_group
    return None
