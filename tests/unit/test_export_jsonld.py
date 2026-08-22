"""Tests for JSON-LD export (SPEC §2)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.export import ExportError, export_jsonld

if TYPE_CHECKING:
    from pathlib import Path


def _canonical(tmp_path: Path) -> Path:
    pl.DataFrame(
        {
            "concept_id": ["c1", "c2"],
            "kind": ["food", "food"],
            "food_group": ["dairy", "fruits"],
        }
    ).write_parquet(tmp_path / "concept.parquet")
    pl.DataFrame(
        {
            "ref_kind": ["food", "food"],
            "ref": ["c1", "c1"],
            "locale": ["en", "pt"],
            "status": ["native", "native"],
            "text": ["Milk", "Leite"],
            "text_normalized": ["milk", "leite"],
        }
    ).write_parquet(tmp_path / "label.parquet")
    pl.DataFrame(
        {
            "concept_id": ["c1"],
            "nutrient_id": ["ENERC_KCAL"],
            "value": [60.0],
            "unit": ["kcal"],
            "value_type": ["measured"],
            "acquisition_type": ["declared"],
            "source_id": ["ciqual"],
            "source_record_id": ["r1"],
            "source_nutrient_code": ["328"],
            "n_samples": [None],
            "standard_deviation": [None],
            "min_value": [None],
            "max_value": [None],
            "analytical_method": [None],
            "confidence_code": ["A"],
            "derivation_id": [None],
            "basis": ["per_100g_edible"],
            "below_loq_threshold": [None],
        }
    ).write_parquet(tmp_path / "value.parquet")
    return tmp_path


def test_jsonld_concepts_with_labels_and_values(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path)
    out = export_jsonld(canonical, tmp_path / "exports", include_values=True)
    lines = out.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    assert "@context" in header
    nodes = [json.loads(line) for line in lines[1:]]
    by_id = {node["@id"]: node for node in nodes}
    milk = by_id["urn:nutridb:concept:c1"]
    assert milk["label"] == [
        {"@language": "en", "@value": "Milk"},
        {"@language": "pt", "@value": "Leite"},
    ]
    obs = milk["nutridb:observation"][0]
    assert obs["value"] == 60.0 and obs["unit"] == "kcal"


def test_jsonld_without_values_still_works(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path)
    (tmp_path / "value.parquet").unlink()
    out = export_jsonld(canonical, tmp_path / "exports", include_values=False)
    text = out.read_text(encoding="utf-8")
    assert '"nutridb:observation"' not in text


def test_missing_required_table_fails_high(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        export_jsonld(tmp_path, tmp_path / "exports")
