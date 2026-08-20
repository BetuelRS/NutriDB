"""Unit tests for the quality suite (SPEC §11, F6).

Each check is exercised with synthetic data that violates exactly that
rule; the suite must classify it (severity) and count it. Synthetic
values only, isolated in tmp_path (SPEC §17.7).
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.quality import Finding, QualityError, run_quality

if TYPE_CHECKING:
    from pathlib import Path

V = "measured"
NA: str | None = None

Row = tuple[str, str, float, str, str, str, str | None, str]


def _frames(
    rows: list[Row], groups: dict[str, str] | None = None
) -> tuple[pl.DataFrame, pl.DataFrame]:
    values = pl.DataFrame(
        [
            {
                "concept_id": r[0],
                "nutrient_id": r[1],
                "value": r[2],
                "unit": r[3],
                "value_type": r[4],
                "basis": r[5],
                "analytical_method": r[6],
                "source_id": r[7],
            }
            for r in rows
        ]
    )
    concepts = pl.DataFrame(
        [
            {"concept_id": cid, "food_group": (groups or {}).get(cid, "misc")}
            for cid in values["concept_id"].unique().to_list()
        ]
    )
    return values, concepts


def _row(
    concept: str,
    nutrient: str,
    value: float,
    unit: str,
    method: str | None = NA,
    source: str = "fixture",
) -> Row:
    return (concept, nutrient, value, unit, V, "per_100g_edible", method, source)


def _write(
    tmp_path: Path,
    values: pl.DataFrame,
    concepts: pl.DataFrame,
    unmapped: list[str] | tuple[str, ...] = (),
) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    values.write_parquet(canonical / "value.parquet")
    concepts.write_parquet(canonical / "concept.parquet")
    vocab = tmp_path / "vocab"
    vocab.mkdir(exist_ok=True)
    (vocab / "nutrients.csv").write_text(
        "tagname,group,name_en,unit\n"
        "WATER,proximates,Water,g\n"
        "PROCNT,proximates,Protein,g\n"
        "FAT,proximates,Fat,g\n"
        "CHOAVL,proximates,Carbs,g\n"
        "FIBTG,proximates,Fiber,g\n"
        "ASH,proximates,Ash,g\n"
        "ALC,proximates,Alcohol,g\n"
        "SUGAR,carbohydrates,Sugars,g\n"
        "GLUS,carbohydrates,Glucose,g\n"
        "FRUS,carbohydrates,Fructose,g\n"
        "GALS,carbohydrates,Galactose,g\n"
        "SUCS,carbohydrates,Sucrose,g\n"
        "LACS,carbohydrates,Lactose,g\n"
        "MALS,carbohydrates,Maltose,g\n"
        "FASAT,lipids,Saturated,g\n"
        "FAMS,lipids,Monounsaturated,g\n"
        "FAPU,lipids,Polyunsaturated,g\n"
        "FATRN,lipids,Trans,mg\n"
        "NA,minerals,Sodium,mg\n"
        "NACL,minerals,Salt,g\n"
        "VITA_RAE,vitamins,RAE,ug\n"
        "RETOL,vitamins,Retinol,ug\n"
        "ENERC_KCAL,energy,Energy,kcal\n"
        "POLYL,carbohydrates,Polyols,g\n",
        encoding="utf-8",
    )
    mappings = tmp_path / "mappings"
    unmapped_dir = mappings / "_unmapped"
    unmapped_dir.mkdir(parents=True, exist_ok=True)
    (unmapped_dir / "README.md").write_text("gate", encoding="utf-8")
    for name in unmapped:
        (unmapped_dir / name).write_text("x", encoding="utf-8")


def _run(
    tmp_path: Path,
    rows: list[Row],
    groups: dict[str, str] | None = None,
    unmapped: list[str] | tuple[str, ...] = (),
) -> list[Finding]:
    values, concepts = _frames(rows, groups)
    _write(tmp_path, values, concepts, unmapped)
    return run_quality(tmp_path / "canonical", tmp_path / "vocab", tmp_path)


def _by_check(findings: list[Finding], check: str) -> Finding:
    hits = [f for f in findings if f.check == check]
    assert hits, f"check {check} not found in {[f.check for f in findings]}"
    return hits[0]


def test_clean_data_produces_no_errors(tmp_path: Path) -> None:
    rows = [
        _row("c1", "WATER", 80.0, "g"),
        _row("c1", "PROCNT", 10.0, "g"),
        _row("c1", "FAT", 5.0, "g"),
        _row("c1", "CHOAVL", 4.0, "g"),
        _row("c1", "FIBTG", 1.0, "g"),
        _row("c1", "ASH", 0.5, "g"),
        _row("c1", "ALC", 0.0, "g"),
        _row("c1", "ENERC_KCAL", 101.0, "kcal", "Reg. UE 1169/2011 (Atwater)"),
        _row("c1", "SUGAR", 3.0, "g"),
        _row("c1", "GLUS", 1.0, "g"),
        _row("c1", "FRUS", 1.0, "g"),
        _row("c1", "GALS", 0.0, "g"),
        _row("c1", "SUCS", 1.0, "g"),
        _row("c1", "LACS", 0.0, "g"),
        _row("c1", "MALS", 0.0, "g"),
        _row("c1", "FASAT", 1.0, "g"),
        _row("c1", "FAMS", 2.0, "g"),
        _row("c1", "FAPU", 1.0, "g"),
        _row("c1", "FATRN", 500.0, "mg"),
        _row("c1", "NA", 200.0, "mg"),
        _row("c1", "NACL", 0.5, "g"),
        _row("c1", "VITA_RAE", 300.0, "ug"),
        _row("c1", "RETOL", 200.0, "ug"),
    ]
    findings = _run(tmp_path, rows)
    errors = [f for f in findings if f.severity == "error"]
    assert not errors, errors
    assert _by_check(findings, "proximates_sum").severity == "info"
    assert _by_check(findings, "energy_recalc").severity == "info"


def test_proximates_sum_violation_is_warning_with_evidence(tmp_path: Path) -> None:
    rows = [
        _row("c1", "WATER", 80.0, "g"),
        _row("c1", "PROCNT", 10.0, "g"),
        _row("c1", "FAT", 15.0, "g"),  # sum -> 110.5
        _row("c1", "CHOAVL", 4.0, "g"),
        _row("c1", "FIBTG", 1.0, "g"),
        _row("c1", "ASH", 0.5, "g"),
        _row("c1", "ALC", 0.0, "g"),
    ]
    prox = _by_check(_run(tmp_path, rows), "proximates_sum")
    assert prox.severity == "warning"
    assert prox.count == 1
    assert "c1 [fixture]" in prox.examples[0]


def test_coherence_checks_are_per_source(tmp_path: Path) -> None:
    """A concept whose proximates mix two sources must not fire: coherence
    is a property of each source alone (mv mixes per nutrient, ADR-0001)."""
    rows = [
        _row("c1", "WATER", 80.0, "g", source="src_a"),
        _row("c1", "PROCNT", 10.0, "g", source="src_a"),
        _row("c1", "FAT", 5.0, "g", source="src_a"),
        _row("c1", "CHOAVL", 5.0, "g", source="src_a"),  # sum 100.5 (coherent)
        _row("c1", "FIBTG", 0.0, "g", source="src_a"),
        _row("c1", "ASH", 0.5, "g", source="src_a"),
        _row("c1", "ALC", 0.0, "g", source="src_a"),
        _row("c1", "WATER", 89.7, "g", source="src_b"),
        _row("c1", "PROCNT", 0.63, "g", source="src_b"),
        _row("c1", "FAT", 0.13, "g", source="src_b"),
        _row("c1", "CHOAVL", 8.9, "g", source="src_b"),  # sum 100.01 (coherent)
        _row("c1", "FIBTG", 0.25, "g", source="src_b"),
        _row("c1", "ASH", 0.4, "g", source="src_b"),
        _row("c1", "ALC", 0.0, "g", source="src_b"),
    ]
    prox = _by_check(_run(tmp_path, rows), "proximates_sum")
    assert prox.count == 0, prox


def test_energy_recalc_with_registered_method(tmp_path: Path) -> None:
    rows = [
        _row("c1", "ENERC_KCAL", 300.0, "kcal", "Reg. UE 1169/2011 (Atwater)"),
        _row("c1", "PROCNT", 10.0, "g"),
        _row("c1", "FAT", 10.0, "g"),
        _row("c1", "CHOAVL", 40.0, "g"),
        _row("c1", "FIBTG", 0.0, "g"),
        _row("c1", "ALC", 0.0, "g"),
    ]
    # 4*10 + 9*10 + 4*40 = 290; declared 300 -> rel 3.4% < 5%: info
    assert _by_check(_run(tmp_path, rows), "energy_recalc").severity == "info"

    rows[0] = _row("c1", "ENERC_KCAL", 350.0, "kcal", "Reg. UE 1169/2011 (Atwater)")  # rel 20.7%
    energy = _by_check(_run(tmp_path, rows), "energy_recalc")
    assert energy.severity == "warning" and energy.count == 1, energy
    assert "c1 [fixture]" in energy.examples[0]


def test_energy_skipped_without_registered_method(tmp_path: Path) -> None:
    rows = [
        _row("c1", "ENERC_KCAL", 300.0, "kcal"),
        _row("c1", "PROCNT", 10.0, "g"),
        _row("c1", "FAT", 10.0, "g"),
        _row("c1", "CHOAVL", 40.0, "g"),
        _row("c1", "FIBTG", 0.0, "g"),
        _row("c1", "ALC", 0.0, "g"),
    ]
    energy = _by_check(_run(tmp_path, rows), "energy_recalc")
    assert energy.severity == "info" and energy.count == 0


def test_energy_uses_polyol_factor_when_present(tmp_path: Path) -> None:
    # Reg. UE 1169/2011 Annex XIV: polyols 2.4 kcal/g (CIQUAL maps POLYL).
    rows = [
        _row("c1", "ENERC_KCAL", 250.0, "kcal", "Reg. UE 1169/2011 (Atwater)"),
        _row("c1", "PROCNT", 0.1, "g"),
        _row("c1", "FAT", 0.4, "g"),
        _row("c1", "CHOAVL", 96.0, "g"),
        _row("c1", "FIBTG", 0.0, "g"),
        _row("c1", "ALC", 0.0, "g"),
        _row("c1", "POLYL", 95.0, "g"),
    ]
    energy = _by_check(_run(tmp_path, rows), "energy_recalc")
    # without polyols: 385.6; with 2.4/g: 157.6 -> rel 37% -> warning
    assert energy.count == 1, energy


def test_fatty_acids_violation_is_warning(tmp_path: Path) -> None:
    rows = [
        _row("c1", "FAT", 10.0, "g"),
        _row("c1", "FASAT", 5.0, "g"),
        _row("c1", "FAMS", 3.0, "g"),
        _row("c1", "FAPU", 3.0, "g"),  # sum 11.0 > 10.2
        _row("c1", "FATRN", 0.0, "mg"),
    ]
    fa = _by_check(_run(tmp_path, rows), "fatty_acids_le_fat")
    assert fa.severity == "warning" and fa.count == 1, fa


def test_fatty_acids_normalizes_trans_to_g(tmp_path: Path) -> None:
    rows = [
        _row("c1", "FAT", 100.0, "g"),
        _row("c1", "FASAT", 40.0, "g"),
        _row("c1", "FAMS", 40.0, "g"),
        _row("c1", "FAPU", 20.0, "g"),
        _row("c1", "FATRN", 16500.0, "mg"),  # 16.5 g -> sum 116.5 > 102 -> warning
    ]
    fa = _by_check(_run(tmp_path, rows), "fatty_acids_le_fat")
    assert fa.count == 1, fa


def test_sugars_violations(tmp_path: Path) -> None:
    rows = [
        _row("c1", "SUGAR", 1.0, "g"),
        _row("c1", "CHOAVL", 10.0, "g"),
        _row("c1", "GLUS", 1.0, "g"),
        _row("c1", "FRUS", 1.0, "g"),  # sum 2.0 > 1.02
        _row("c1", "GALS", 0.0, "g"),
        _row("c1", "SUCS", 0.0, "g"),
        _row("c1", "LACS", 0.0, "g"),
        _row("c1", "MALS", 0.0, "g"),
    ]
    indiv = _by_check(_run(tmp_path, rows), "sugars_individual_le_total")
    assert indiv.severity == "warning" and indiv.count == 1, indiv
    assert _by_check(_run(tmp_path, rows), "sugars_total_le_carbs").count == 0


def test_salt_vs_sodium_normalizes_units(tmp_path: Path) -> None:
    rows = [
        _row("c1", "NA", 200.0, "mg"),  # -> 0.2 g; x2.5 = 0.5 g
        _row("c1", "NACL", 0.5, "g"),
    ]
    salt = _by_check(_run(tmp_path, rows), "salt_vs_sodium")
    assert salt.severity == "info" and salt.count == 0, salt

    rows = [_row("c1", "NA", 200.0, "mg"), _row("c1", "NACL", 0.2, "g")]  # rel 60%
    salt = _by_check(_run(tmp_path, rows), "salt_vs_sodium")
    assert salt.severity == "warning" and salt.count == 1, salt


def test_vita_rae_inconsistency_is_warning(tmp_path: Path) -> None:
    rows = [
        _row("c1", "VITA_RAE", 100.0, "ug"),
        _row("c1", "RETOL", 300.0, "ug"),
    ]
    vita = _by_check(_run(tmp_path, rows), "vita_rae_consistent")
    assert vita.severity == "warning" and vita.count == 1, vita


def test_negative_values_are_error(tmp_path: Path) -> None:
    rows = [_row("c1", "WATER", -1.0, "g")]
    neg = _by_check(_run(tmp_path, rows), "no_negative_values")
    assert neg.severity == "error" and neg.count == 1, neg


def test_unit_domain_vocab_is_error(tmp_path: Path) -> None:
    rows = [_row("c1", "WATER", 80.0, "mg")]  # vocab unit is g
    unit = _by_check(_run(tmp_path, rows), "unit_domain_vocab")
    assert unit.severity == "error" and unit.count == 1, unit


def test_unit_domain_g_is_error(tmp_path: Path) -> None:
    rows = [_row("c1", "WATER", 150.0, "g")]
    unit = _by_check(_run(tmp_path, rows), "unit_domain_g")
    assert unit.severity == "error" and unit.count == 1, unit


def test_zscore_outlier_is_warning(tmp_path: Path) -> None:
    rows = [_row(f"c{i}", "NA", 100.0, "mg") for i in range(20)]  # n >= _ZSCORE_MIN_N
    rows.append(_row("c_out", "NA", 100000.0, "mg"))  # z ~ sqrt(21) >> 4
    groups = {f"c{i}": "g1" for i in range(20)} | {"c_out": "g1"}
    z = _by_check(_run(tmp_path, rows, groups=groups), "zscore_group")
    assert z.severity == "warning" and z.count == 1, z


def test_cross_source_divergence_reported(tmp_path: Path) -> None:
    rows = [
        _row("c1", "NA", 100.0, "mg", source="src_a"),
        _row("c1", "NA", 200.0, "mg", source="src_b"),  # 50% divergence
    ]
    div = _by_check(_run(tmp_path, rows), "cross_source_divergence")
    assert div.severity == "info" and div.count == 1, div


def test_unmapped_gate_is_error(tmp_path: Path) -> None:
    rows = [_row("c1", "WATER", 80.0, "g")]
    unmapped = _by_check(_run(tmp_path, rows, unmapped=["ciqual_999.csv"]), "unmapped_empty")
    assert unmapped.severity == "error" and unmapped.count == 1, unmapped


def test_structure_orphans_are_error(tmp_path: Path) -> None:
    values, concepts = _frames([_row("c1", "WATER", 80.0, "g")])
    _write(tmp_path, values, concepts)
    artifact = tmp_path / "artifact.sqlite"
    conn = sqlite3.connect(artifact)
    try:
        conn.execute("CREATE TABLE concept (concept_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE source_record (source_record_id TEXT PRIMARY KEY, record TEXT)")
        conn.execute(
            "CREATE TABLE value (concept_id TEXT, nutrient_id TEXT, value REAL, "
            "derivation_id TEXT, source_record_id TEXT)"
        )
        conn.execute("CREATE TABLE concept_link (concept_id TEXT, source_record_id TEXT)")
        conn.execute("CREATE TABLE mv_food_value (concept_id TEXT, nutrient_id TEXT, value REAL)")
        conn.execute("CREATE TABLE tombstone (successor_id TEXT, replaced_by TEXT)")
        conn.execute("CREATE TABLE label (ref TEXT, ref_kind TEXT, status TEXT)")
        conn.execute("CREATE TABLE nutrient (tagname TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE derivation (derivation_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO concept VALUES ('c1')")
        conn.execute("INSERT INTO source_record VALUES ('r1', '{}')")
        conn.execute("INSERT INTO value VALUES ('c1', 'WATER', 80.0, NULL, 'r1')")
        conn.execute("INSERT INTO concept_link VALUES ('c1', 'r1')")
        conn.execute("INSERT INTO mv_food_value VALUES ('c1', 'WATER', 80.0)")
        conn.execute("INSERT INTO tombstone VALUES ('nfx_missing', NULL)")
        conn.execute("INSERT INTO label VALUES ('WATER', 'nutrient', 'native')")
        conn.execute("INSERT INTO nutrient VALUES ('WATER')")
        conn.execute("INSERT INTO derivation VALUES ('d1')")
        conn.execute("INSERT INTO value VALUES ('c2', 'WATER', 1.0, 'd1', 'r1')")  # orphan
        conn.commit()
    finally:
        conn.close()
    findings = run_quality(tmp_path / "canonical", tmp_path / "vocab", tmp_path, artifact)
    fk = _by_check(findings, "fk_orphans")
    assert fk.severity == "error" and fk.count >= 1, fk
    assert _by_check(findings, "integrity_check").severity == "info"


def test_missing_canonical_fails_high(tmp_path: Path) -> None:
    values, concepts = _frames([_row("c1", "WATER", 80.0, "g")])
    _write(tmp_path, values, concepts)
    import shutil

    shutil.rmtree(tmp_path / "canonical")
    with pytest.raises(QualityError):
        run_quality(tmp_path / "canonical", tmp_path / "vocab", tmp_path)


def test_mt_unreviewed_is_error(tmp_path: Path) -> None:
    values, concepts = _frames([_row("c1", "WATER", 80.0, "g")])
    _write(tmp_path, values, concepts)
    artifact = tmp_path / "artifact.sqlite"
    conn = sqlite3.connect(artifact)
    try:
        conn.execute("CREATE TABLE concept (concept_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE source_record (source_record_id TEXT PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE value (concept_id TEXT, derivation_id TEXT, source_record_id TEXT)"
        )
        conn.execute("CREATE TABLE concept_link (concept_id TEXT, source_record_id TEXT)")
        conn.execute("CREATE TABLE mv_food_value (concept_id TEXT, nutrient_id TEXT, value REAL)")
        conn.execute("CREATE TABLE tombstone (successor_id TEXT, replaced_by TEXT)")
        conn.execute("CREATE TABLE label (ref TEXT, ref_kind TEXT, status TEXT)")
        conn.execute("CREATE TABLE nutrient (tagname TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE derivation (derivation_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO concept VALUES ('c1')")
        conn.execute("INSERT INTO source_record VALUES ('r1')")
        conn.execute("INSERT INTO value VALUES ('c1', NULL, 'r1')")
        conn.execute("INSERT INTO concept_link VALUES ('c1', 'r1')")
        conn.execute("INSERT INTO mv_food_value VALUES ('c1', 'WATER', 80.0)")
        conn.execute("INSERT INTO tombstone VALUES ('nfx_missing', NULL)")
        conn.execute("INSERT INTO nutrient VALUES ('WATER')")
        conn.execute("INSERT INTO label VALUES ('WATER', 'nutrient', 'mt_unreviewed')")
        conn.commit()
    finally:
        conn.close()
    findings = run_quality(tmp_path / "canonical", tmp_path / "vocab", tmp_path, artifact)
    unreviewed = _by_check(findings, "no_mt_unreviewed")
    assert unreviewed.severity == "error" and unreviewed.count == 1, unreviewed


def test_findings_ordered_by_severity(tmp_path: Path) -> None:
    rows = [_row("c1", "WATER", 150.0, "g")]  # unit_domain_g error
    findings = _run(tmp_path, rows, unmapped=["x.csv"])
    order = {"error": 0, "warning": 1, "info": 2}
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, key=lambda s: order[s]), severities


def test_write_report_emits_html_and_metrics(tmp_path: Path) -> None:
    from nutridb.quality import write_report

    values, concepts = _frames([_row("c1", "WATER", 80.0, "g")])
    _write(tmp_path, values, concepts)
    findings = run_quality(tmp_path / "canonical", tmp_path / "vocab", tmp_path)
    report_dir = tmp_path / "qa"
    write_report(report_dir, findings, None, 0.42)
    assert (report_dir / "report.html").is_file()
    assert (report_dir / "metrics.json").is_file()
    metrics = json.loads((report_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["schema"] == "qa-1"
    assert metrics["duration_s"] == 0.42
    assert metrics["counts"]["error"] == 0
    html = (report_dir / "report.html").read_text(encoding="utf-8")
    assert "SPEC §11" in html and "qa-1" not in html
