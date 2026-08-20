"""Unit tests for deterministic eternal identifiers (F1.5, P4/P5).

The format is ULID-shaped: ``nfx_`` + 26 Crockford base32 chars (no
I/L/O/U). The value is a pure function of the seed: two builds of the
same input produce byte-identical identifiers.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import polars as pl
import pytest

from nutridb.identity import CROCKFORD_ALPHABET, ID_PREFIX, canonical_id, ulid
from nutridb.identity.matching import (
    LinkProposal,
    _status,
    evaluate,
    write_links_csv,
)

if TYPE_CHECKING:
    from pathlib import Path

_ULID_RE = re.compile(rf"^{re.escape(ID_PREFIX)}[{CROCKFORD_ALPHABET}]{{26}}$")


def _proposal(
    insa_code: str,
    ciqual_code: str,
    score: float,
    sim: float = 0.7,
    *,
    vetoed: bool = False,
    distinctive_conflict: bool = False,
    numeric_conflict: bool = False,
    single_term_pair: bool = False,
) -> LinkProposal:
    return LinkProposal(
        insa_code,
        ciqual_code,
        f"alimento {insa_code}",
        f"aliment {ciqual_code}",
        1.0,
        sim,
        True,
        score,
        vetoed,
        distinctive_conflict,
        numeric_conflict,
        single_term_pair,
    )


def test_format_is_ulid_shaped() -> None:
    for seed in ("ciqual|food|24999", "ciqual|value|1000:327", "x", ""):
        assert _ULID_RE.fullmatch(f"{ID_PREFIX}{ulid(seed)}"), seed


def test_canonical_id_prefixed_and_namespaced() -> None:
    food = canonical_id("concept", "ciqual", "food", "24999")
    assert food.startswith(ID_PREFIX)
    assert len(food) == 4 + 26
    assert food != canonical_id("source_record", "ciqual", "food", "24999")
    assert food != canonical_id("concept", "ciqual", "food", "25000")


def test_deterministic() -> None:
    seed = "ciqual|food|açúcar"
    assert ulid(seed) == ulid(seed)


def test_unique_across_seeds() -> None:
    ids = {ulid(f"ciqual|value|{a}:{b}") for a in range(20) for b in range(20)}
    assert len(ids) == 400


def test_no_forbidden_chars() -> None:
    sample = [ulid(str(i)) for i in range(100)] + [
        canonical_id(k, "a", "b") for k in ("concept", "source_record", "tombstone")
    ]
    assert all("I" not in s and "L" not in s and "O" not in s and "U" not in s for s in sample)


def test_ulid_golden_values() -> None:
    assert ulid("ciqual:food:24999") == "5CGDNX7JVCE01C6NZFGNC5GPFJ"
    assert canonical_id("concept", "ciqual", "food", "13002") == "nfx_5WAXNCVY3238REJ2NWP012390F"
    assert canonical_id("concept", "ciqual", "food", "20021") == "nfx_43XVY2CS429HC4KK3WZHM6R7H6"


def test_status_thresholds_and_flags() -> None:
    assert _status(_proposal("1", "2", score=0.90)) == "automatic"
    assert _status(_proposal("1", "2", score=0.49)) is None
    assert _status(_proposal("1", "2", score=0.70)) == "review"
    assert _status(_proposal("1", "2", score=0.99, vetoed=True)) is None
    assert _status(_proposal("1", "2", score=0.99, numeric_conflict=True)) == "review"
    assert _status(_proposal("1", "2", score=0.99, distinctive_conflict=True)) == "review"
    assert _status(_proposal("1", "2", score=0.50, sim=0.70, single_term_pair=True)) == "automatic"
    assert _status(_proposal("1", "2", score=0.50, sim=0.55, single_term_pair=True)) == "review"


def test_write_links_csv_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "links.csv"
    rows = write_links_csv(
        [
            _proposal("25", "19041", score=0.90),
            _proposal("26", "19042", score=0.70),
            _proposal("27", "19043", score=0.40),
        ],
        path,
    )
    assert rows == 4  # automatic + review pairs, dropped None
    frame = pl.read_csv(path, has_header=True)
    assert frame.height == 4
    assert set(frame["status"].unique().to_list()) == {"automatic", "review"}
    codes = [str(x) for x in frame.filter(pl.col("source") == "insa")["source_code"].to_list()]
    assert sorted(codes) == ["25", "26"]
    row = frame.filter(pl.col("source_code").cast(pl.Utf8) == "19041")
    survivor = row["concept_id"].to_list()[0]
    assert survivor == min(
        canonical_id("concept", "insa", "food", "25"),
        canonical_id("concept", "ciqual", "food", "19041"),
    )


def test_evaluate_precision_recall_and_food_level(tmp_path: Path) -> None:
    golden = tmp_path / "golden.csv"
    golden.write_text(
        "insa_code,ciqual_code,label,evidence\n"
        "1,11,true,auto\n"
        "1,12,false,review-sample\n"
        "2,21,true,auto\n"
        "2,22,true,review-sample\n"
        "3,31,false,missed\n"
        "4,41,true,auto\n"
        "5,51,true,auto\n",
        encoding="utf-8",
    )
    proposals = [
        _proposal("1", "11", score=0.90),  # automatic TP
        _proposal("1", "12", score=0.70),  # review FALSE pair
        _proposal("2", "22", score=0.70),  # review TRUE pair (adjudicated)
        _proposal("2", "23", score=0.95),  # automatic FP (not in golden)
        _proposal("3", "31", score=0.90),  # automatic FP (golden FALSE)
        _proposal("5", "51", score=0.60),  # review TRUE pair
    ]
    metrics = evaluate(proposals, golden)
    assert metrics["precision"] == pytest.approx(1 / 2)  # 1-11 true; 3-31 golden-false
    assert metrics["recall"] == pytest.approx(3 / 5)  # coverage: 1-11 final; 2-22, 5-51 review
    assert metrics["recall_confirmed"] == pytest.approx(1 / 5)  # only automatic final 1-11
    assert metrics["auto_finals"] == 3
    assert metrics["review_golden_true"] == 2  # 2-22 and 5-51 found but unconfirmed
    assert metrics["golden_foods"] == 4  # insa 1, 2, 4, 5
    assert metrics["covered_foods"] == 3  # 1, 2 and 5
    assert metrics["food_recall"] == pytest.approx(3 / 4)
