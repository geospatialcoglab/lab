"""Threshold boundary (Task 5.5, Property 6, Req 5.5).

check_threshold raises BelowThresholdError iff count < min_threshold. Tested at
0, threshold-1, threshold, threshold+1 across several thresholds.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scripts import generate_publications as gp
from scripts.generate_publications import Publication


def _pubs(n):
    """Build a list of n placeholder Publication values."""
    return [
        Publication(f"t{i}", "a", "v", 2000 + i, "https://x", "Link \u2192")
        for i in range(n)
    ]


@pytest.mark.parametrize("threshold", [1, 2, 3, 5, 10])
def test_boundary_cases(threshold):
    """0 and threshold-1 fail; threshold and threshold+1 pass."""
    # Below threshold -> raises.
    with pytest.raises(gp.BelowThresholdError):
        gp.check_threshold(_pubs(0), threshold)
    if threshold - 1 >= 0:
        with pytest.raises(gp.BelowThresholdError):
            gp.check_threshold(_pubs(threshold - 1), threshold)

    # At/above threshold -> returns the count.
    assert gp.check_threshold(_pubs(threshold), threshold) == threshold
    assert gp.check_threshold(_pubs(threshold + 1), threshold) == threshold + 1


@given(count=st.integers(min_value=0, max_value=30),
       threshold=st.integers(min_value=1, max_value=30))
@settings(max_examples=300)
def test_threshold_iff_property(count, threshold):
    """Raises iff count < threshold; returns count otherwise (Property 6)."""
    pubs = _pubs(count)
    if count < threshold:
        with pytest.raises(gp.BelowThresholdError):
            gp.check_threshold(pubs, threshold)
    else:
        assert gp.check_threshold(pubs, threshold) == count


def test_default_threshold_rejects_zero():
    """Default threshold of 1 rejects the zero-record case (Req 3.10)."""
    with pytest.raises(gp.BelowThresholdError):
        gp.check_threshold([])
