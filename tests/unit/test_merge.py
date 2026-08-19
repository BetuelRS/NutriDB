"""Unit tests for the merge stage (F5, SPEC §9, ADR-0007).

Covers priority resolution (specificity, wildcards, fail high), the
preferred/alternatives/divergence materialization, tie-breaks, overrides
with mandatory justification and the deterministic parquet output.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.merge import MergeError, load_priorities, merge, resolve_priority

if TYPE_CHECKING:
    from pathlib import Path


def _rules(tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    path = tmp_path / "source_priority.csv"
    path.write_text(
        "# synthetic priorities (sandbox)\n"
        "locale,food_group,nutrient,source_order\n" + "".join(",".join(r) + "\n" for r in rows),
        encoding="utf-8",
    )
    return path


def _overrides(tmp_path: Path, rows: list[tuple[str, str, str, str, str, str]]) -> Path:
    path = tmp_path / "overrides.csv"
    path.write_text(
        "# synthetic overrides (sandbox)\n"
        "concept_id,nutrient_id,basis,value,unit,justification\n"
        + "".join(",".join(r) + "\n" for r in rows),
        encoding="utf-8",
    )
    return path


def _canonical(tmp_path: Path) -> Path:
    """Synthetic canonical dataset: two sources, one concept, two nutrients.

    Codes mirror the real mappings (ciqual 327/40302, insa energia_kj/
    acidos_gordos_saturados_g are defaults); ciqual 332 is the non-default
    Jones kcal-method row, excluded from the mv view (ADR-0007).
    """
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    pl.DataFrame(
        {
            "concept_id": ["c1", "c1", "c1", "c1", "c1"],
            "nutrient_id": ["ENERC_KJ", "ENERC_KJ", "ENERC_KJ", "FASAT", "FASAT"],
            "value": [100.0, 90.0, 95.0, 5.0, 8.0],
            "unit": ["kJ", "kJ", "kJ", "g", "g"],
            "value_type": ["measured", "measured", "measured", "measured", "measured"],
            "acquisition_type": ["measured", "measured", "measured", "measured", "measured"],
            "source_id": ["ciqual", "insa", "ciqual", "ciqual", "insa"],
            "source_record_id": ["ciqual:1", "insa:1", "ciqual:3", "ciqual:2", "insa:2"],
            "source_nutrient_code": [
                "327",
                "energia_kj",
                "332",
                "40302",
                "acidos_gordos_saturados_g",
            ],
            "n_samples": [None, None, None, None, None],
            "standard_deviation": [None, None, None, None, None],
            "min_value": [None, None, None, None, None],
            "max_value": [None, None, None, None, None],
            "analytical_method": [None, None, None, None, None],
            "confidence_code": ["A", "A", "A", "A", "A"],
            "derivation_id": [None, None, None, None, None],
            "basis": ["per_100g_edible"] * 5,
            "below_loq_threshold": [None, None, None, None, None],
        }
    ).write_parquet(canonical / "value.parquet")
    pl.DataFrame(
        {
            "concept_id": ["c1"],
            "kind": ["food"],
            "food_group": ["vegetables"],
        }
    ).write_parquet(canonical / "concept.parquet")
    pl.DataFrame(
        {
            "ref_kind": ["food", "food"],
            "ref": ["c1", "c1"],
            "locale": ["pt", "fr"],
            "status": ["native", "native"],
            "text": ["Cenoura", "Carotte"],
            "text_normalized": ["cenoura", "carotte"],
        }
    ).write_parquet(canonical / "label.parquet")
    return canonical


class TestPriorities:
    def test_specificity_wins(self, tmp_path: Path) -> None:
        rules = load_priorities(
            _rules(
                tmp_path,
                [
                    ("pt", "*", "*", "ciqual>insa"),
                    ("pt", "vegetables", "*", "insa>ciqual"),
                    ("pt", "vegetables", "FASAT", "insa>ciqual"),
                    ("pt", "vegetables", "ENERC_KJ", "ciqual>insa"),
                ],
            )
        )
        assert resolve_priority(rules, "pt", "vegetables", "FASAT") == ("insa", "ciqual")
        assert resolve_priority(rules, "pt", "vegetables", "ENERC_KJ") == ("ciqual", "insa")
        assert resolve_priority(rules, "pt", "vegetables", "WATER") == ("insa", "ciqual")
        assert resolve_priority(rules, "pt", "cereals", "FASAT") == ("ciqual", "insa")
        assert resolve_priority(rules, "pt", "cereals", "WATER") == ("ciqual", "insa")

    def test_locale_without_rule_fails_high(self, tmp_path: Path) -> None:
        rules = load_priorities(_rules(tmp_path, [("pt", "*", "*", "ciqual>insa")]))
        with pytest.raises(MergeError, match="no priority rule"):
            resolve_priority(rules, "en", "vegetables", "WATER")

    def test_duplicate_rule_fails_high(self, tmp_path: Path) -> None:
        with pytest.raises(MergeError, match="duplicate rule"):
            load_priorities(
                _rules(
                    tmp_path,
                    [
                        ("pt", "*", "*", "ciqual>insa"),
                        ("pt", "*", "*", "insa>ciqual"),
                    ],
                )
            )

    def test_unknown_source_fails_high(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        priorities = _rules(tmp_path, [("pt", "*", "*", "mystery>ciqual")])
        (sandbox_root / "mappings" / "source_priority.csv").write_bytes(priorities.read_bytes())
        with pytest.raises(MergeError, match="unknown source"):
            merge(canonical, sandbox_root)


class TestMerge:
    def test_preferred_by_priority_and_alternatives(
        self, tmp_path: Path, sandbox_root: Path
    ) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "mappings" / "source_priority.csv").write_bytes(
            _rules(
                tmp_path,
                [("pt", "*", "*", "insa>ciqual"), ("fr", "*", "*", "ciqual>insa")],
            ).read_bytes()
        )
        report = merge(canonical, sandbox_root)
        assert report["mv_rows"] == 4  # 2 nutrients x 2 locales
        mv = pl.read_parquet(canonical / "mv_food_value.parquet")
        pt = mv.filter(pl.col("locale") == "pt")
        fr = mv.filter(pl.col("locale") == "fr")
        assert pt.filter(pl.col("nutrient_id") == "ENERC_KJ")["value"].item() == 90.0  # insa
        assert fr.filter(pl.col("nutrient_id") == "ENERC_KJ")["value"].item() == 100.0  # ciqual
        row = pt.filter(pl.col("nutrient_id") == "FASAT").row(0, named=True)
        assert row["value"] == 8.0  # insa wins for pt
        assert row["source_id"] == "insa"
        alternatives = json.loads(row["alternatives"])
        assert alternatives == [
            {
                "source_id": "ciqual",
                "source_record_id": "ciqual:2",
                "value": 5.0,
                "unit": "g",
                "value_type": "measured",
                "derivation_id": None,
            }
        ]

    def test_divergence_flag_and_max(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "mappings" / "source_priority.csv").write_bytes(
            _rules(
                tmp_path,
                [("pt", "*", "*", "insa>ciqual"), ("fr", "*", "*", "ciqual>insa")],
            ).read_bytes()
        )
        merge(canonical, sandbox_root)
        mv = pl.read_parquet(canonical / "mv_food_value.parquet")
        fasat = mv.filter(pl.col("nutrient_id") == "FASAT").row(0, named=True)
        # |8-5|/8 = 0.375 >= 0.30 -> flag; |90-100|/100 = 0.10 -> no flag
        assert fasat["divergence_flag"]
        assert fasat["divergence_max"] == pytest.approx(0.375)
        enerc = mv.filter(pl.col("nutrient_id") == "ENERC_KJ").row(0, named=True)
        assert not enerc["divergence_flag"]
        assert enerc["divergence_max"] == pytest.approx(0.1)

    def test_no_averaging_between_sources(self, tmp_path: Path, sandbox_root: Path) -> None:
        """The mv value is one source's value, never a mean (SPEC §9/P2)."""
        canonical = _canonical(tmp_path)
        (sandbox_root / "mappings" / "source_priority.csv").write_bytes(
            _rules(
                tmp_path,
                [("fr", "*", "*", "ciqual>insa"), ("pt", "*", "*", "insa>ciqual")],
            ).read_bytes()
        )
        merge(canonical, sandbox_root)
        mv = pl.read_parquet(canonical / "mv_food_value.parquet")
        fr = mv.filter(pl.col("locale") == "fr")
        values = {r["nutrient_id"]: r["value"] for r in fr.rows(named=True)}
        assert values == {"ENERC_KJ": 100.0, "FASAT": 5.0}

    def test_override_with_justification(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "mappings" / "source_priority.csv").write_bytes(
            _rules(
                tmp_path,
                [("pt", "*", "*", "insa>ciqual"), ("fr", "*", "*", "ciqual>insa")],
            ).read_bytes()
        )
        (sandbox_root / "mappings" / "overrides.csv").write_bytes(
            _overrides(
                tmp_path,
                [("c1", "FASAT", "per_100g_edible", "6.0", "g", "valores verificados a mao")],
            ).read_bytes()
        )
        report = merge(canonical, sandbox_root)
        assert report["overrides"] == 1
        mv = pl.read_parquet(canonical / "mv_food_value.parquet")
        row = mv.filter(pl.col("nutrient_id") == "FASAT").row(0, named=True)
        assert row["value"] == 6.0
        assert row["acquisition_type"] == "declared"
        assert row["source_id"] is None
        assert row["override_justification"] == "valores verificados a mao"

    def test_override_without_justification_fails_high(
        self, tmp_path: Path, sandbox_root: Path
    ) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "mappings" / "source_priority.csv").write_bytes(
            _rules(tmp_path, [("pt", "*", "*", "insa>ciqual")]).read_bytes()
        )
        (sandbox_root / "mappings" / "overrides.csv").write_bytes(
            _overrides(tmp_path, [("c1", "FASAT", "per_100g_edible", "6.0", "g", " ")]).read_bytes()
        )
        with pytest.raises(MergeError, match="without justification"):
            merge(canonical, sandbox_root)

    def test_override_unknown_concept_fails_high(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "mappings" / "source_priority.csv").write_bytes(
            _rules(tmp_path, [("pt", "*", "*", "insa>ciqual")]).read_bytes()
        )
        (sandbox_root / "mappings" / "overrides.csv").write_bytes(
            _overrides(
                tmp_path, [("ghost", "FASAT", "per_100g_edible", "6.0", "g", "verificado")]
            ).read_bytes()
        )
        with pytest.raises(MergeError, match="unknown concept"):
            merge(canonical, sandbox_root)

    def test_only_default_codes_in_mv(self, tmp_path: Path, sandbox_root: Path) -> None:
        """The mv view keeps the default method per tagname (ADR-0007)."""
        canonical = _canonical(tmp_path)
        (sandbox_root / "mappings" / "source_priority.csv").write_bytes(
            _rules(
                tmp_path,
                [("pt", "*", "*", "ciqual>insa"), ("fr", "*", "*", "ciqual>insa")],
            ).read_bytes()
        )
        merge(canonical, sandbox_root)
        mv = pl.read_parquet(canonical / "mv_food_value.parquet")
        records = mv.select("source_id", "source_record_id").unique().rows()
        assert ("ciqual", "ciqual:1") in records  # 327: default
        assert ("ciqual", "ciqual:3") not in records, "332 is not the default energy method"
