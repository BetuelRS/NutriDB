"""Quality suite over the canonical dataset and the artefact (SPEC §11, F6).

Runs the SPEC §11 checks with explicit severities — ``error`` blocks the
release (the CLI exits 1), ``warning`` enters the report (revision
queue), ``info`` feeds metrics — and produces ``build/qa/report.html``
plus ``build/qa/metrics.json``.

Coherence checks only look at **measured** values (P2: never compare
against an absence) on the ``per_100g_edible`` basis; energy is
recomputed with the factors of the method registered in the mapping
(P1: energy always has a registered method) and skipped where no method
was published. Every check is deterministic (P5).
"""

# ruff: noqa: RUF001 -- pt-PT legitimately uses the multiplication sign.

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["Finding", "QualityError", "run_quality", "write_report"]

MAX_EXAMPLES = 5

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_SEVERITY_COLOR = {"error": "#b91c1c", "warning": "#b45309", "info": "#1d4ed8"}

# Proximates sum must land in [100-3, 100+3] g/100 g (SPEC §11).
_PROXIMATES = ("WATER", "PROCNT", "FAT", "CHOAVL", "FIBTG", "ASH", "ALC")
_PROXIMATES_LO, _PROXIMATES_HI = 97.0, 103.0

# Reg. UE 1169/2011 (Annex XIV) — the method registered for the CIQUAL
# energy rows (mappings/nutrients/ciqual.csv): kcal/g factors.
_ENERGY_FACTORS = {  # Reg. UE 1169/2011 Annex XIV; POLYL optional (CIQUAL maps it)
    "PROCNT": 4.0,
    "FAT": 9.0,
    "CHOAVL": 4.0,
    "FIBTG": 2.0,
    "ALC": 7.0,
    "POLYL": 2.4,
}
_ENERGY_REQUIRED = ("PROCNT", "FAT", "CHOAVL", "FIBTG", "ALC")
_ENERGY_METHOD = "Reg. UE 1169/2011 (Atwater)"
_ENERGY_TOL = 0.05
_ENERGY_ABS_FLOOR = 5.0  # kcal: relative tolerance is meaningless near zero

_FATTY_ACIDS = ("FASAT", "FAMS", "FAPU", "FATRN")
_FATTY_ACIDS_TOL = 1.02
_SUGARS_INDIVIDUAL = ("GLUS", "FRUS", "GALS", "SUCS", "LACS", "MALS")
_SUGARS_TOL = 1.02
_AMINO_ACIDS = (
    "ALA",
    "ARG",
    "ASP",
    "CYS",
    "GLU",
    "GLY",
    "HIS",
    "ILE",
    "LEU",
    "LYS",
    "MET",
    "PHE",
    "PRO",
    "SER",
    "THR",
    "TRP",
    "TYR",
    "VAL",
)
_AA_LO, _AA_HI = 0.85, 1.15
_SALT_TO_SODIUM = 2.5
_SALT_TOL = 0.10

# g-unit nutrients whose per-100 g value cannot exceed 100 g.
_G_UNIT_NUTRIENTS = (
    "WATER",
    "PROCNT",
    "FAT",
    "FASAT",
    "FAMS",
    "FAPU",
    "CHOAVL",
    "FIBTG",
    "SUGAR",
    "STARCH",
    "ASH",
    "ALC",
    "NACL",
    "SALTEQ",
)

_ZSCORE_THRESHOLD = 4.0
_ZSCORE_MIN_N = 10


class QualityError(Exception):
    """Fatal input problem for the quality suite (fail high, P9)."""


@dataclass(frozen=True)
class Finding:
    """One check result: stable id, severity, metric and capped examples."""

    check: str
    severity: str
    title: str
    detail: str
    count: int
    examples: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "check": self.check,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "count": self.count,
            "examples": list(self.examples),
        }


def run_quality(
    canonical_dir: Path,
    vocab_dir: Path,
    root: Path,
    artifact: Path | None = None,
) -> list[Finding]:
    """Run the SPEC §11 suite; return findings ordered by severity.

    Severity policy (F6 triage, ADR-0009): the pipeline reproduces the
    sources verbatim (P1, proven by the golden tests), so a coherence
    violation *inside one source* is the source's review item, never a
    release blocker: severity ``warning``, with the offending (concept,
    nutrient, source) as evidence. ``error`` is reserved for checks of
    *our* contract: units, negatives, structural integrity, translations
    and the unmapped gate.
    """
    from nutridb.vocab import SCHEMAS, load_csv

    vocab_units = {
        row["tagname"]: row["unit"]
        for row in load_csv(vocab_dir / "nutrients.csv", SCHEMAS["nutrients.csv"])
    }
    values = _measured_values(canonical_dir)
    concepts = _concepts(canonical_dir)
    findings: list[Finding] = []
    findings.extend(_coherence_internal(values, concepts, vocab_units))
    findings.extend(_coherence_external(values, concepts))
    if artifact is not None:
        findings.extend(_structure(artifact, root))
    else:
        findings.append(
            Finding(
                "artifact_structure",
                "info",
                "Integridade estrutural",
                "sem artefacto para verificar (integridade/FK/órfãos) — passa o caminho",
                0,
            )
        )
    findings.append(_check_unmapped(root))
    findings.sort(key=lambda f: _SEVERITY_ORDER[f.severity])
    return findings


def _measured_values(canonical_dir: Path) -> pl.DataFrame:
    path = canonical_dir / "value.parquet"
    if not path.is_file():
        raise QualityError(f"canonical value table missing: {path}")
    return (
        pl.read_parquet(path)
        .filter(
            (pl.col("value_type") == "measured")
            & pl.col("value").is_not_null()
            & (pl.col("basis") == "per_100g_edible")
        )
        .select("concept_id", "nutrient_id", "value", "unit", "analytical_method", "source_id")
    )


def _concepts(canonical_dir: Path) -> pl.DataFrame:
    path = canonical_dir / "concept.parquet"
    if not path.is_file():
        raise QualityError(f"canonical concept table missing: {path}")
    return pl.read_parquet(path).select("concept_id", "food_group")


_UNIT_TO_G = {"g": 1.0, "mg": 1e-3, "ug": 1e-6}


def _per_source_g(
    values: pl.DataFrame, nutrients: tuple[str, ...]
) -> dict[tuple[str, str], dict[str, float]]:
    """Measured value per (concept, source) for the given nutrients,
    normalized to grams (the vocab stores e.g. NA and FATRN in mg; sums
    must not mix units).

    Coherence is a property of each source alone: the mv mixes sources
    per nutrient by design (ADR-0001), so cross-source sums would compare
    e.g. CIQUAL water with INSA carbohydrates.
    """
    subset = values.filter(pl.col("nutrient_id").is_in(nutrients))
    out: dict[tuple[str, str], dict[str, float]] = {}
    for row in subset.rows(named=True):
        key = (row["concept_id"], row["source_id"])
        out.setdefault(key, {})[row["nutrient_id"]] = row["value"] * _UNIT_TO_G.get(
            row["unit"], 1.0
        )
    return out


def _coherence_internal(
    values: pl.DataFrame, concepts: pl.DataFrame, vocab_units: dict[str, str]
) -> list[Finding]:
    """SPEC §11 coherence checks, per (concept, source) on measured values.

    Severity ``warning``: the pipeline reproduces the source verbatim
    (P1), so an incoherence inside one source is a source review item
    with evidence, never a pipeline fault (ADR-0009 triage). The raw
    source record stays the authority: these checks feed the revision
    queue.
    """
    found: list[Finding] = []

    # -- proximates sum (SPEC §11) -----------------------------------------
    by_source = _per_source_g(values, _PROXIMATES)
    prox_offenders: list[tuple[str, str, float]] = []
    checked = 0
    for (concept_id, source_id), cells in by_source.items():
        if not all(n in cells for n in _PROXIMATES):
            continue
        checked += 1
        total = sum(cells[n] for n in _PROXIMATES)
        if not (_PROXIMATES_LO <= total <= _PROXIMATES_HI):
            prox_offenders.append((concept_id, source_id, total))
    found.append(
        Finding(
            "proximates_sum",
            "warning" if prox_offenders else "info",
            "Soma dos proximados",
            f"{checked} (conceito, fonte) completos; soma fora de "
            f"[{_PROXIMATES_LO}, {_PROXIMATES_HI}] g/100 g (verbatim na fonte)",
            len(prox_offenders),
            tuple(
                f"{cid} [{src}]: {total:.2f}" for cid, src, total in prox_offenders[:MAX_EXAMPLES]
            ),
        )
    )

    # -- energy recalculation with the registered method (P1) ---------------
    by_source = _per_source_g(values, ("ENERC_KCAL", *_ENERGY_FACTORS))
    energy_rows = values.filter(
        (pl.col("nutrient_id") == "ENERC_KCAL") & (pl.col("analytical_method") == _ENERGY_METHOD)
    )
    method_sources = {(row["concept_id"], row["source_id"]) for row in energy_rows.rows(named=True)}
    energy_offenders: list[tuple[str, str, float, float, float]] = []
    skipped = 0
    for (concept_id, source_id), cells in by_source.items():
        if (concept_id, source_id) not in method_sources:
            skipped += 1
            continue
        if not all(n in cells for n in ("ENERC_KCAL", *_ENERGY_REQUIRED)):
            continue
        declared = cells["ENERC_KCAL"]
        recalc = sum(cells[n] * f for n, f in _ENERGY_FACTORS.items() if n in cells)
        rel = abs(recalc - declared) / declared if declared != 0 else 0.0
        if rel > _ENERGY_TOL and abs(recalc - declared) > _ENERGY_ABS_FLOOR:
            energy_offenders.append((concept_id, source_id, declared, recalc, rel))
    found.append(
        Finding(
            "energy_recalc",
            "warning" if energy_offenders else "info",
            "Energia recalculada",
            f"método {_ENERGY_METHOD!r} ±{_ENERGY_TOL:.0%} (piso absoluto "
            f"{_ENERGY_ABS_FLOOR:.0f} kcal); {skipped} (conceito, fonte) sem método "
            "registado (P2, não verificados)",
            len(energy_offenders),
            tuple(
                f"{cid} [{src}]: declarado {d} vs recalculado {r:.1f} (rel {rel:.2%})"
                for cid, src, d, r, rel in energy_offenders[:MAX_EXAMPLES]
            ),
        )
    )

    # -- sum of fatty acids <= fat (SPEC §11) -------------------------------
    by_source = _per_source_g(values, ("FAT", *_FATTY_ACIDS))
    fatty_offenders: list[tuple[str, str, float, float]] = []
    checked = 0
    for (concept_id, source_id), cells in by_source.items():
        if not all(n in cells for n in ("FAT", *_FATTY_ACIDS)):
            continue
        checked += 1
        total = sum(cells[n] for n in _FATTY_ACIDS)
        if total > cells["FAT"] * _FATTY_ACIDS_TOL:
            fatty_offenders.append((concept_id, source_id, total, cells["FAT"]))
    found.append(
        Finding(
            "fatty_acids_le_fat",
            "warning" if fatty_offenders else "info",
            "Ácidos gordos ≤ gordura",
            f"{checked} (conceito, fonte) com os 4 AG medidos; ΣAG > gordura × {_FATTY_ACIDS_TOL}",
            len(fatty_offenders),
            tuple(
                f"{cid} [{src}]: ΣAG {total:.2f} vs gordura {fat:.2f}"
                for cid, src, total, fat in fatty_offenders[:MAX_EXAMPLES]
            ),
        )
    )

    # -- sugars: individual <= total <= available carbs (SPEC §11) ----------
    by_source = _per_source_g(values, ("SUGAR", "CHOAVL", *_SUGARS_INDIVIDUAL))
    offenders_total: list[tuple[str, str, float, float]] = []
    offenders_carbs: list[tuple[str, str, float, float]] = []
    checked = 0
    for (concept_id, source_id), cells in by_source.items():
        if not all(n in cells for n in ("SUGAR", "CHOAVL", *_SUGARS_INDIVIDUAL)):
            continue
        checked += 1
        individual = sum(cells[n] for n in _SUGARS_INDIVIDUAL)
        if individual > cells["SUGAR"] * _SUGARS_TOL:
            offenders_total.append((concept_id, source_id, individual, cells["SUGAR"]))
        if cells["SUGAR"] > cells["CHOAVL"] * _SUGARS_TOL:
            offenders_carbs.append((concept_id, source_id, cells["SUGAR"], cells["CHOAVL"]))
    found.append(
        Finding(
            "sugars_individual_le_total",
            "warning" if offenders_total else "info",
            "Σ açúcares individuais ≤ açúcares totais",
            f"{checked} (conceito, fonte) completos; Σ individual > total × {_SUGARS_TOL}",
            len(offenders_total),
            tuple(
                f"{cid} [{src}]: Σ {s:.2f} vs total {t:.2f}"
                for cid, src, s, t in offenders_total[:MAX_EXAMPLES]
            ),
        )
    )
    found.append(
        Finding(
            "sugars_total_le_carbs",
            "warning" if offenders_carbs else "info",
            "Açúcares totais ≤ hidratos disponíveis",
            f"{checked} (conceito, fonte) completos; total > CHOAVL × {_SUGARS_TOL}",
            len(offenders_carbs),
            tuple(
                f"{cid} [{src}]: açúcares {s:.2f} vs CHOAVL {c:.2f}"
                for cid, src, s, c in offenders_carbs[:MAX_EXAMPLES]
            ),
        )
    )

    # -- amino acids vs protein (SPEC §11) ----------------------------------
    by_source = _per_source_g(values, ("PROCNT", *_AMINO_ACIDS))
    aa_offenders: list[tuple[str, str, float, float, float]] = []
    checked = 0
    for (concept_id, source_id), cells in by_source.items():
        if not all(n in cells for n in ("PROCNT", *_AMINO_ACIDS)):
            continue
        checked += 1
        total = sum(cells[n] for n in _AMINO_ACIDS)
        ratio = total / cells["PROCNT"] if cells["PROCNT"] != 0 else 0.0
        if not (_AA_LO <= ratio <= _AA_HI):
            aa_offenders.append((concept_id, source_id, total, cells["PROCNT"], ratio))
    found.append(
        Finding(
            "amino_acids_vs_protein",
            "warning" if aa_offenders else "info",
            "Σ aminoácidos vs proteína",
            f"{checked} (conceito, fonte) completos; Σ fora de [{_AA_LO}, {_AA_HI}] da proteína",
            len(aa_offenders),
            tuple(
                f"{cid} [{src}]: ΣAA {t:.2f} vs PROCNT {p:.2f} ({ratio:.2%})"
                for cid, src, t, p, ratio in aa_offenders[:MAX_EXAMPLES]
            ),
        )
    )

    # -- salt vs sodium (SPEC §11) ------------------------------------------
    by_source = _per_source_g(values, ("NACL", "NA"))
    salt_offenders: list[tuple[str, str, float, float]] = []
    checked = 0
    for (concept_id, source_id), cells in by_source.items():
        if not all(n in cells for n in ("NACL", "NA")):
            continue
        checked += 1
        expected = cells["NA"] * _SALT_TO_SODIUM
        rel = abs(cells["NACL"] - expected) / expected if expected != 0 else 0.0
        if rel > _SALT_TOL:
            salt_offenders.append((concept_id, source_id, cells["NACL"], expected))
    found.append(
        Finding(
            "salt_vs_sodium",
            "warning" if salt_offenders else "info",
            "Sal ≈ sódio × 2,5",
            f"{checked} (conceito, fonte) com sal e sódio; desvio > {_SALT_TOL:.0%}",
            len(salt_offenders),
            tuple(
                f"{cid} [{src}]: sal {s:.2f} vs sódio×2,5 {e:.2f}"
                for cid, src, s, e in salt_offenders[:MAX_EXAMPLES]
            ),
        )
    )

    # -- vitamin A RAE consistency (SPEC §11) --------------------------------
    by_source = _per_source_g(values, ("VITA_RAE", "RETOL"))
    vita_offenders: list[tuple[str, str, float, float]] = []
    checked = 0
    for (concept_id, source_id), cells in by_source.items():
        if not all(n in cells for n in ("VITA_RAE", "RETOL")):
            continue
        checked += 1
        if cells["VITA_RAE"] < cells["RETOL"] * 0.95:
            vita_offenders.append((concept_id, source_id, cells["VITA_RAE"], cells["RETOL"]))
    found.append(
        Finding(
            "vita_rae_consistent",
            "warning" if vita_offenders else "info",
            "Vitamina A RAE consistente",
            f"{checked} (conceito, fonte) com RAE e retinol; RAE < retinol × 0,95",
            len(vita_offenders),
            tuple(
                f"{cid} [{src}]: RAE {r:.2f} vs retinol {t:.2f}"
                for cid, src, r, t in vita_offenders[:MAX_EXAMPLES]
            ),
        )
    )

    # -- no negative values (SPEC §11) ---------------------------------------
    negatives = values.filter(pl.col("value") < 0)
    found.append(
        Finding(
            "no_negative_values",
            "error" if negatives.height else "info",
            "Nenhum valor negativo",
            "valores medidos negativos",
            negatives.height,
            tuple(
                f"{row['concept_id']} {row['nutrient_id']}: {row['value']}"
                for row in negatives.head(MAX_EXAMPLES).rows(named=True)
            ),
        )
    )

    # -- units within the nutrient domain (SPEC §11) ------------------------
    g_rows = values.filter(
        (pl.col("nutrient_id").is_in(_G_UNIT_NUTRIENTS)) & (pl.col("value") > 100.0)
    )
    found.append(
        Finding(
            "unit_domain_g",
            "error" if g_rows.height else "info",
            "Unidades no domínio (g/100 g)",
            "valores > 100 g/100 g em nutrientes de gramas",
            g_rows.height,
            tuple(
                f"{row['concept_id']} {row['nutrient_id']}: {row['value']}"
                for row in g_rows.head(MAX_EXAMPLES).rows(named=True)
            ),
        )
    )
    unit_rows = values.filter(
        pl.col("unit") != pl.col("nutrient_id").replace_strict(vocab_units, default="__unknown__")
    )
    found.append(
        Finding(
            "unit_domain_vocab",
            "error" if unit_rows.height else "info",
            "Unidades do vocabulário",
            "value.unit fora do domínio do tagname (vocab/nutrients.csv)",
            unit_rows.height,
            tuple(
                f"{row['concept_id']} {row['nutrient_id']}: {row['unit']}"
                for row in unit_rows.head(MAX_EXAMPLES).rows(named=True)
            ),
        )
    )
    return found


def _coherence_external(values: pl.DataFrame, concepts: pl.DataFrame) -> list[Finding]:
    found: list[Finding] = []

    # -- z-score by (nutrient, food_group); |z| > 4 -> revision (SPEC §11) ---
    frame = values.join(concepts, on="concept_id")
    offenders: list[tuple[str, str, float]] = []
    checked_groups = 0
    for (nutrient_id, _food_group), group in frame.group_by(
        ["nutrient_id", "food_group"], maintain_order=True
    ):
        vals = group["value"].to_list()
        if len(vals) < _ZSCORE_MIN_N:
            continue
        checked_groups += 1
        mean = statistics.fmean(vals)
        stdev = statistics.stdev(vals)
        if stdev == 0:
            continue
        for concept_id, value in zip(group["concept_id"].to_list(), vals, strict=True):
            if abs((value - mean) / stdev) > _ZSCORE_THRESHOLD:
                offenders.append((concept_id, nutrient_id, value))
    found.append(
        Finding(
            "zscore_group",
            "warning" if offenders else "info",
            "Z-score por (nutriente, grupo)",
            f"{checked_groups} grupos com n ≥ {_ZSCORE_MIN_N}; |z| > {_ZSCORE_THRESHOLD} → revisão",
            len(offenders),
            tuple(f"{cid} {n}: {v}" for cid, n, v in offenders[:MAX_EXAMPLES]),
        )
    )

    # -- cross-source divergences for the same concept (SPEC §11) ------------
    # The mv picks one source per nutrient (ADR-0001); the divergences
    # between the alternatives are reported here, metric-level: they feed
    # the explorer's source comparison (ADR-0007, 1 597 ≥ 30% at F5).
    dup = (
        values.select("concept_id", "nutrient_id", "value", "source_id")
        .filter(pl.col("value") > 0)
        .unique(["concept_id", "nutrient_id", "source_id"])
    )
    pairs = dup.join(
        dup,
        on=["concept_id", "nutrient_id"],
        how="inner",
        suffix="_b",
    ).filter(pl.col("source_id") < pl.col("source_id_b"))  # unordered pairs only
    pairs = pairs.with_columns(
        (
            (pl.col("value") - pl.col("value_b")).abs()
            / pl.max_horizontal(pl.col("value").abs(), pl.col("value_b").abs())
        ).alias("div")
    )
    diverged = pairs.filter(pl.col("div") >= 0.30)
    found.append(
        Finding(
            "cross_source_divergence",
            "info",
            "Divergências entre fontes (≥ 30%)",
            "pares (conceito, nutriente) com ≥ 2 fontes medidas e divergência relativa ≥ 30%",
            diverged.height,
            tuple(
                f"{row['concept_id']} {row['nutrient_id']}: {row['value']} ({row['source_id']}) "
                f"vs {row['value_b']} ({row['source_id_b']})"
                for row in diverged.head(MAX_EXAMPLES).rows(named=True)
            ),
        )
    )
    return found


def _structure(artifact: Path, root: Path) -> list[Finding]:
    conn = sqlite3.connect(artifact)
    conn.row_factory = sqlite3.Row
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        found: list[Finding] = [
            Finding(
                "integrity_check",
                "error" if integrity != "ok" else "info",
                "Integridade SQLite",
                "PRAGMA integrity_check",
                0 if integrity == "ok" else 1,
                () if integrity == "ok" else ("integrity_check != ok",),
            )
        ]
        orphans: list[tuple[str, str]] = []
        for table, ref_col, parent, parent_col in (
            ("value", "concept_id", "concept", "concept_id"),
            ("value", "source_record_id", "source_record", "source_record_id"),
            ("concept_link", "concept_id", "concept", "concept_id"),
            ("concept_link", "source_record_id", "source_record", "source_record_id"),
            ("mv_food_value", "concept_id", "concept", "concept_id"),
            ("tombstone", "successor_id", "concept", "concept_id"),
        ):
            rows = conn.execute(
                f"SELECT DISTINCT child.{ref_col} FROM {table} child "
                f"LEFT JOIN {parent} p ON p.{parent_col} = child.{ref_col} "
                f"WHERE p.{parent_col} IS NULL LIMIT {MAX_EXAMPLES + 1}"
            ).fetchall()
            orphans.extend((table, row[ref_col]) for row in rows)
        found.append(
            Finding(
                "fk_orphans",
                "error" if orphans else "info",
                "Sem órfãos de chave",
                "filhos sem pai em concept/source_record (inclui lápides)",
                len(orphans),
                tuple(f"{t}: {r}" for t, r in orphans[:MAX_EXAMPLES]),
            )
        )
        nutrient_tags = {r[0] for r in conn.execute("SELECT tagname FROM nutrient")}
        label_orphans = conn.execute(
            "SELECT DISTINCT ref FROM label WHERE ref_kind = 'nutrient' LIMIT ?",
            (MAX_EXAMPLES + 1,),
        ).fetchall()
        bad = [r["ref"] for r in label_orphans if r["ref"] not in nutrient_tags]
        found.append(
            Finding(
                "label_nutrient_refs",
                "error" if bad else "info",
                "Rótulos de nutrientes resolvem",
                "label.ref_kind='nutrient' sem tagname no vocabulário",
                len(bad),
                tuple(bad[:MAX_EXAMPLES]),
            )
        )
        derived = conn.execute(
            "SELECT DISTINCT derivation_id FROM value WHERE derivation_id IS NOT NULL"
        ).fetchall()
        known_derivations = {r[0] for r in conn.execute("SELECT derivation_id FROM derivation")}
        missing = [
            r["derivation_id"] for r in derived if r["derivation_id"] not in known_derivations
        ]
        found.append(
            Finding(
                "derivation_chain",
                "error" if missing else "info",
                "Cadeias de derivação registadas",
                "value.derivation_id sem registo em derivation (P2)",
                len(missing),
                tuple(str(m) for m in missing[:MAX_EXAMPLES]),
            )
        )
        unreviewed = conn.execute(
            "SELECT count(*) FROM label WHERE status = 'mt_unreviewed'"
        ).fetchone()[0]
        found.append(
            Finding(
                "no_mt_unreviewed",
                "error" if unreviewed else "info",
                "Zero mt_unreviewed no core (P7)",
                "rótulos de tradução automática não revista",
                unreviewed,
            )
        )
        return found
    finally:
        conn.close()


def _check_unmapped(root: Path) -> Finding:
    unmapped = root / "mappings" / "_unmapped"
    if not unmapped.is_dir():
        return Finding("unmapped_empty", "error", "_unmapped/ vazio", "diretório em falta", 1)
    files = [
        p.name
        for p in unmapped.iterdir()
        if p.is_file() and p.name != "README.md" and not p.name.startswith(".")
    ]
    return Finding(
        "unmapped_empty",
        "error" if files else "info",
        "_unmapped/ vazio",
        "entradas não mapeadas bloqueiam o gate (F1.3)",
        len(files),
        tuple(files[:MAX_EXAMPLES]),
    )


def write_report(
    report_dir: Path,
    findings: list[Finding],
    artifact: Path | None,
    duration: float,
) -> None:
    """Write build/qa/report.html and build/qa/metrics.json (F6)."""
    report_dir.mkdir(parents=True, exist_ok=True)
    counts = {s: sum(1 for f in findings if f.severity == s) for s in _SEVERITY_ORDER}
    generated_at = _now_utc()
    metrics: dict[str, object] = {
        "schema": "qa-1",
        "artifact": str(artifact) if artifact is not None else None,
        "generated_at": generated_at,
        "duration_s": round(duration, 3),
        "counts": counts,
        "findings": [f.as_dict() for f in findings],
    }
    import json

    (report_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    rows = []
    for finding in findings:
        color = _SEVERITY_COLOR[finding.severity]
        examples = "".join(f"<li><code>{_escape(ex)}</code></li>" for ex in finding.examples)
        rows.append(
            f"<tr><td style='color:{color};font-weight:700'>{finding.severity}</td>"
            f"<td><code>{finding.check}</code></td>"
            f"<td>{_escape(finding.title)}</td>"
            f"<td>{_escape(finding.detail)}</td>"
            f"<td style='text-align:right'>{finding.count}</td>"
            f"<td><ul style='margin:0;padding-left:1em'>{examples}</ul></td></tr>"
        )
    html = f"""<!doctype html>
<html lang="pt-PT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NutriDB — Relatório de qualidade</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 72rem; padding: 0 1rem; }}
h1 {{ font-size: 1.4rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
th, td {{ border: 1px solid #d1d5db; padding: 0.35rem 0.5rem; }}
th {{ background: #f3f4f6; }}
.pass {{ color: #15803d; font-weight: 700; }}
.bad {{ color: #b91c1c; font-weight: 700; }}
code {{ background: #f3f4f6; padding: 0 0.2em; }}
</style>
</head>
<body>
<h1>NutriDB — Relatório de qualidade (SPEC §11, F6)</h1>
<p>Gerado em {_escape(generated_at)} · duração {duration:.1f} s ·
artefacto: <code>{_escape(str(artifact) if artifact is not None else "—")}</code></p>
<p class="{"pass" if counts["error"] == 0 else "bad"}">
erros: {counts["error"]} · avisos: {counts["warning"]} · info: {counts["info"]}
</p>
<table>
<thead><tr><th>severidade</th><th>check</th><th>título</th><th>detalhe</th><th>n</th><th>exemplos</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
</body>
</html>
"""
    (report_dir / "report.html").write_text(html, encoding="utf-8")


def _now_utc() -> str:
    import datetime

    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
