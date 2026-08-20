"""Synthetic property tests for numeric and deterministic helpers (P2/P5)."""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from nutridb.identity.matching import LinkProposal, resolve_one_to_one
from nutridb.merge import _divergence
from nutridb.transform import _convert

_FINITE_NON_NEGATIVE = st.floats(
    min_value=0.0,
    max_value=1_000_000.0,
    allow_nan=False,
    allow_infinity=False,
)
_POSITIVE_FACTOR = st.floats(
    min_value=1e-9,
    max_value=1_000.0,
    allow_nan=False,
    allow_infinity=False,
)


@given(value=_FINITE_NON_NEGATIVE, factor=_POSITIVE_FACTOR)
def test_conversion_roundtrip(value: float, factor: float) -> None:
    converted = _convert(value, factor)
    assert converted is not None
    restored = _convert(converted, 1.0 / factor)
    assert restored is not None
    assert math.isclose(restored, value, rel_tol=1e-12, abs_tol=1e-9)


@given(left=_FINITE_NON_NEGATIVE, right=_FINITE_NON_NEGATIVE)
def test_divergence_is_symmetric_and_bounded(left: float, right: float) -> None:
    def candidate(value: float) -> dict[str, object]:
        return {"value_type": "measured", "value": value}

    forward = _divergence(candidate(left), [candidate(right)])
    reverse = _divergence(candidate(right), [candidate(left)])
    assert forward == reverse
    assert 0.0 <= forward[1] <= 1.0


@given(order=st.permutations([("insa-1", "ciqual-1"), ("insa-1", "ciqual-2")]))
def test_identity_resolution_is_input_order_invariant(
    order: list[tuple[str, str]],
) -> None:
    proposals = [
        LinkProposal(
            insa_code=insa,
            ciqual_code=ciqual,
            pt_name=insa,
            cq_name=ciqual,
            terms=1.0,
            sim=0.9 if ciqual.endswith("1") else 0.8,
            group=True,
            score=0.9 if ciqual.endswith("1") else 0.8,
            vetoed=False,
            distinctive_conflict=False,
            numeric_conflict=False,
            single_term_pair=False,
        )
        for insa, ciqual in order
    ]
    winners = resolve_one_to_one(proposals)
    assert [(p.insa_code, p.ciqual_code) for p in winners] == [("insa-1", "ciqual-1")]
