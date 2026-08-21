"""Generate derivations/retention_factors.csv from the official USDA
Nutrient Retention Factors Release 6 (2007) CSV (CC0 1.0).

Reproducibility (P10): run after `sources sync`-style cache download:

    uv run python scripts/build_retention_factors.py

Policy (ADR-0018):
- nutrient mapping Nutr_No -> INFOODS tagname, only into existing vocab;
  USDA 318 (Vitamin A IU) and 338 (Lutein+Zeaxanthin combined) are skipped.
- cooking_method classified from RetnDesc keywords (first match wins);
  unclassified rows are reported and excluded from the factor table but
  kept in the full-fidelity reference file.
- one factor per (nutrient, cooking_method): the MEDIAN of all matching
  USDA rows; evidence records row count, min-max spread and DOI.
"""

from __future__ import annotations

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_TXT = ROOT / "sources" / "cache" / "usda_retn06" / "retn06.txt"
OUT_FACTORS = ROOT / "derivations" / "retention_factors.csv"
OUT_REFERENCE = ROOT / "derivations" / "usda_r6_reference.csv"
DOI = "10.15482/USDA.ADC/1409034"

NUTRIENT_MAP: dict[str, str] = {
    "221": "ALC",
    "301": "CA",
    "303": "FE",
    "304": "MG",
    "305": "P",
    "306": "K",
    "307": "NA",
    "309": "ZN",
    "312": "CU",
    "321": "CARTB",
    "322": "CARTA",
    "334": "CRYPXB",
    "337": "LYCPN",
    "392": "VITA_RAE",
    "401": "VITC",
    "404": "THIA",
    "405": "RIBF",
    "406": "NIA",
    "415": "VITB6A",
    "417": "FOL",
    "418": "VITB12",
    "421": "CHOLN",
    "431": "FOLAC",
    "432": "FOLFD",
}

METHOD_RULES: list[tuple[str, str]] = [
    ("MICROWAVE", "microwaved"),
    ("REHEAT", "reheated"),
    ("CANNED", "canned"),
    ("BLANCH", "blanched"),
    ("POACH", "poached"),
    ("BOIL", "boiled"),
    ("STEAM", "steamed"),
    ("BRAIS", "braised"),
    ("STEW", "stewed"),
    ("SIMMER", "simmered"),
    ("SIMMR", "simmered"),
    ("ROAST", "roasted"),
    ("BROIL", "broiled"),
    ("FRY", "fried"),
    ("SAUTE", "fried"),
    ("FRIED", "fried"),
    ("BAKE", "baked"),
    ("GRILL", "grilled"),
    ("COOKED", "cooked"),
    ("CKD", "cooked"),
    ("HEATED", "cooked"),
]


def classify(desc: str) -> str | None:
    upper = desc.upper()
    for needle, method in METHOD_RULES:
        if needle in upper:
            return method
    return None


def main() -> None:
    if not SOURCE_TXT.is_file():
        sys.exit(f"missing {SOURCE_TXT} — download USDA R6 first (see ADR-0018)")
    rows: list[dict[str, str]] = []
    for line in SOURCE_TXT.read_text(encoding="ascii", errors="strict").splitlines():
        if not line.strip():
            continue
        fields = [field.strip("~") for field in line.split("^")]
        if len(fields) != 7:
            sys.exit(f"unexpected field count in source line: {line!r}")
        rows.append(
            dict(
                zip(
                    [
                        "Retn_Code",
                        "FdGrp_CD",
                        "RetnDesc",
                        "Nutr_No",
                        "NutrDesc",
                        "Retn_Factor",
                        "Date",
                    ],
                    fields,
                    strict=True,
                )
            )
        )
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    reference_rows: list[list[str]] = []
    unclassified = 0
    blank_factors = 0
    unmapped_nutrients: set[str] = set()

    for row in rows:
        tagname = NUTRIENT_MAP.get(row["Nutr_No"])
        method = classify(row["RetnDesc"])
        raw_factor = row["Retn_Factor"]
        reference_rows.append(
            [
                row["Retn_Code"],
                row["FdGrp_CD"],
                row["RetnDesc"],
                row["Nutr_No"],
                tagname or "",
                method or "",
                raw_factor,
                row["Date"],
            ]
        )
        if not raw_factor:
            # Official publication leaves the factor blank where the
            # component does not apply (e.g. minerals in distilled spirits).
            blank_factors += 1
            continue
        factor = int(raw_factor)
        if tagname is None:
            unmapped_nutrients.add(row["Nutr_No"])
            continue
        if method is None:
            unclassified += 1
            continue
        buckets[(tagname, method)].append(factor)

    with OUT_REFERENCE.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "retn_code",
                "usda_fdgrp",
                "retn_desc",
                "nutr_no",
                "tagname",
                "cooking_method",
                "retention_factor_pct",
                "source_date",
            ]
        )
        writer.writerows(reference_rows)

    header = [
        "# Fatores de retencao (SPEC §10, ADR-0007/0018). Fonte: USDA Table of",
        "# Nutrient Retention Factors Release 6 (2007), CC0 1.0,",
        f"# DOI {DOI}. Fonte primaria: retn06.txt (ASCII caret-delimited),",
        "# SHA-256 5B71867F6649E801DB3BF88C6CD1887B0673E853D4BA94AA0AF2B3C091E983F9.",
        "# Gerado por scripts/build_retention_factors.py — nao editar a mao.",
        "# Politica: mediana por (nutriente, metodo); espaco min-max na evidencia;",
        "# referencia integral em usda_r6_reference.csv.",
        "nutrient,cooking_method,retention_factor,evidence",
    ]
    with OUT_FACTORS.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(header) + "\n")
        writer = csv.writer(handle)
        for tagname, method in sorted(buckets):
            values = buckets[(tagname, method)]
            median = round(statistics.median(values) / 100, 4)
            evidence = (
                f"USDA R6 DOI:{DOI}; median of {len(values)} rows; "
                f"min {min(values)}% max {max(values)}%"
            )
            writer.writerow([tagname, method, median, evidence])

    methods = sorted({m for _, m in buckets})
    print(
        f"factors written: {sum(len(v) for v in buckets.values())} rows -> "
        f"{len(buckets)} (nutrient, method) pairs across methods: {methods}"
    )
    print(f"reference rows: {len(reference_rows)} -> {OUT_REFERENCE.name}")
    print(f"unmapped nutrients skipped: {sorted(unmapped_nutrients)}")
    print(f"blank source factors skipped: {blank_factors}")
    print(f"unclassified rows excluded from factors: {unclassified}")


if __name__ == "__main__":
    main()
