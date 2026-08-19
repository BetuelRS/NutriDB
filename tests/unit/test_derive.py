"""Unit tests for the derive stage (F5, SPEC §10, ADR-0007).

Every derived value is ``calculated`` with a registered chain
(``derivation.parquet``); nothing is derived when the factors tables are
empty; missing factor tables fail high (P9); the arithmetic helpers are
tested directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.derive import DeriveError, cook_value, derive, value_per_ml

if TYPE_CHECKING:
    from pathlib import Path

_VALUES = {
    "concept_id": ["c1", "c1", "c2"],
    "nutrient_id": ["ENERC_KJ", "FASAT", "ENERC_KJ"],
    "value": [100.0, 5.0, 200.0],
    "unit": ["kJ", "g", "kJ"],
    "value_type": ["measured", "measured", "measured"],
    "acquisition_type": ["measured", "measured", "measured"],
    "source_id": ["insa", "insa", "ciqual"],
    "source_record_id": ["insa:1", "insa:2", "ciqual:1"],
    "source_nutrient_code": ["energia_kj", "acidos_gordos_saturados_g", "327"],
    "n_samples": [None, None, None],
    "standard_deviation": [None, None, None],
    "min_value": [None, None, None],
    "max_value": [None, None, None],
    "analytical_method": [None, None, None],
    "confidence_code": ["A", "A", "A"],
    "derivation_id": [None, None, None],
    "basis": ["per_100g_edible"] * 3,
    "below_loq_threshold": [None, None, None],
}


def _canonical(tmp_path: Path) -> Path:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    pl.DataFrame(_VALUES).write_parquet(canonical / "value.parquet")
    pl.DataFrame(
        {
            "concept_id": ["c1", "c2"],
            "kind": ["food", "food"],
            "food_group": ["beverages", "beverages"],
        }
    ).write_parquet(canonical / "concept.parquet")
    pl.DataFrame(
        {
            "derivation_id": [],
            "formula": [],
            "inputs": [],
            "factors": [],
        }
    ).write_parquet(canonical / "derivation.parquet")
    return canonical


def _densities(tmp_path: Path, rows: list[tuple[str, str, str]]) -> Path:
    path = tmp_path / "densities.csv"
    path.write_text(
        "# synthetic densities (sandbox)\n"
        "food_group,density_g_per_ml,evidence\n" + "".join(",".join(r) + "\n" for r in rows),
        encoding="utf-8",
    )
    return path


def _portions(tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    path = tmp_path / "portions.csv"
    path.write_text(
        "# synthetic portions (sandbox)\n"
        "concept_id,measure,grams,evidence\n" + "".join(",".join(r) + "\n" for r in rows),
        encoding="utf-8",
    )
    return path


class TestArithmetic:
    def test_value_per_ml(self) -> None:
        assert value_per_ml(100.0, 1.03) == pytest.approx(103.0)

    def test_cook_value(self) -> None:
        assert cook_value(10.0, 0.9, 0.8) == pytest.approx(7.2)


class TestDerive:
    def test_empty_factors_derive_nothing(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        report = derive(canonical, sandbox_root)
        assert report["derivations"] == 0
        values = pl.read_parquet(canonical / "value.parquet")
        assert values.height == 3
        assert values["derivation_id"].null_count() == 3

    def test_volume_derivation_registers_chain(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "densities.csv").write_bytes(
            _densities(tmp_path, [("beverages", "1.03", "densimetro NIST 2024")]).read_bytes()
        )
        report = derive(canonical, sandbox_root)
        assert report["derivations"] == 3
        assert report["volume_100ml"] == 3
        values = pl.read_parquet(canonical / "value.parquet")
        assert values.height == 6
        derived = values.filter(pl.col("basis") == "per_100ml")
        assert derived.height == 3
        expected = {
            r["source_record_id"]: float(r["value"]) * 1.03
            for r in pl.DataFrame(_VALUES).rows(named=True)
        }
        for row in derived.rows(named=True):
            assert row["value_type"] == "calculated"
            assert row["acquisition_type"] == "calculated"
            assert row["value"] == pytest.approx(expected[row["source_record_id"]])
            assert row["derivation_id"] is not None
        derivations = pl.read_parquet(canonical / "derivation.parquet")
        assert derivations.height == 3
        formula = derivations["formula"].unique().to_list()
        assert formula == ["value_per_100ml = value_per_100g x density_g_per_ml"]

    def test_no_double_derivation(self, tmp_path: Path, sandbox_root: Path) -> None:
        """A directly measured 100 ml row blocks the derivation (P2)."""
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "densities.csv").write_bytes(
            _densities(tmp_path, [("beverages", "1.03", "densimetro NIST 2024")]).read_bytes()
        )
        extra = pl.DataFrame(
            {
                "concept_id": ["c1"],
                "nutrient_id": ["ENERC_KJ"],
                "value": [99.0],
                "unit": ["kJ"],
                "value_type": ["measured"],
                "acquisition_type": ["measured"],
                "source_id": ["insa"],
                "source_record_id": ["insa:9"],
                "source_nutrient_code": ["energia_kj"],
                "n_samples": [None],
                "standard_deviation": [None],
                "min_value": [None],
                "max_value": [None],
                "analytical_method": [None],
                "confidence_code": ["A"],
                "derivation_id": [None],
                "basis": ["per_100ml"],
                "below_loq_threshold": [None],
            }
        )
        merged = pl.concat([pl.read_parquet(canonical / "value.parquet"), extra])
        merged.write_parquet(canonical / "value.parquet")
        report = derive(canonical, sandbox_root)
        assert report["derivations"] == 2  # c1 ENERK blocked, c1 FASAT + c2 ENERK derived
        derived = pl.read_parquet(canonical / "value.parquet").filter(
            pl.col("basis") == "per_100ml"
        )
        assert derived.height == 3
        assert (
            derived.filter(pl.col("concept_id") == "c1", pl.col("nutrient_id") == "ENERC_KJ")[
                "value_type"
            ].item()
            == "measured"
        )

    def test_missing_densities_fails_high(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "densities.csv").unlink()
        with pytest.raises(DeriveError, match="missing factors table"):
            derive(canonical, sandbox_root)

    def test_unknown_food_group_fails_high(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "densities.csv").write_bytes(
            _densities(tmp_path, [("cereals", "1.03", "densimetro NIST 2024")]).read_bytes()
        )
        with pytest.raises(DeriveError, match="unknown food_group"):
            derive(canonical, sandbox_root)

    def test_duplicate_density_fails_high(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "densities.csv").write_bytes(
            _densities(
                tmp_path,
                [("beverages", "1.03", "a"), ("beverages", "1.05", "b")],
            ).read_bytes()
        )
        with pytest.raises(DeriveError, match="duplicate rows"):
            derive(canonical, sandbox_root)

    def test_non_numeric_factor_fails_high(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "densities.csv").write_bytes(
            _densities(tmp_path, [("beverages", "denso", "densimetro NIST 2024")]).read_bytes()
        )
        with pytest.raises(DeriveError, match="non-numeric factor"):
            derive(canonical, sandbox_root)

    def test_row_without_evidence_fails_high(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "densities.csv").write_bytes(
            _densities(tmp_path, [("beverages", "1.03", " ")]).read_bytes()
        )
        with pytest.raises(DeriveError, match="without evidence"):
            derive(canonical, sandbox_root)

    def test_portion_validated_against_concepts(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "portions.csv").write_bytes(
            _portions(tmp_path, [("ghost", "1 copo", "200", "FNDDS 2023-2024")]).read_bytes()
        )
        with pytest.raises(DeriveError, match="unknown concept"):
            derive(canonical, sandbox_root)

    def test_portions_written_to_canonical(self, tmp_path: Path, sandbox_root: Path) -> None:
        canonical = _canonical(tmp_path)
        (sandbox_root / "derivations" / "portions.csv").write_bytes(
            _portions(tmp_path, [("c1", "1 copo", "200", "FNDDS 2023-2024")]).read_bytes()
        )
        report = derive(canonical, sandbox_root)
        assert report["portions"] == 1
        portions = pl.read_parquet(canonical / "portion.parquet")
        assert portions.rows() == [("c1", "1 copo", 200.0, "FNDDS 2023-2024")]
