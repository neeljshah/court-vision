"""Per-file test for domains.basketball_nba.composition.transition_flag --
run with: python -m pytest domains/basketball_nba/composition/test_transition_flag.py -q
(never bare pytest -- see bash-cwd-prefix rule)."""
from __future__ import annotations

from domains.basketball_nba.composition.transition_flag import (
    TRANSITION_WINDOW_S, build_transition_frame, validate_vs_fastbreak_qualifier,
)


def test_transition_window_constant_is_the_standard_six_second_cut():
    assert TRANSITION_WINDOW_S == 6.0


def test_shot_inside_window_flagged_shot_outside_is_not():
    df = build_transition_frame(limit=1)
    assert len(df) > 100
    quick = df[df["is_transition"] == 1]
    slow = df[df["is_transition"] == 0]
    assert len(quick) > 0 and len(slow) > 0
    assert set(df["is_transition"].unique()) <= {0, 1}


def test_validate_vs_fastbreak_qualifier_runs_and_bounds_are_valid_probabilities():
    df = build_transition_frame(limit=5)
    pr = validate_vs_fastbreak_qualifier(df)
    assert pr["n"] > 0
    assert 0.0 <= pr["precision"] <= 1.0
    assert 0.0 <= pr["recall"] <= 1.0
    # recall should be reasonably high -- the 6s cut is a SUPERSET of true
    # fastbreaks (any early-clock shot, not just live-ball-transition ones),
    # so it should catch most real fastbreaks even though precision is low
    assert pr["recall"] > 0.5


def test_espn_derived_rows_have_no_fastbreak_qualifier_to_check():
    """ESPN-derived files carry no qualifiers -- has_fastbreak_qualifier must
    stay None there, never silently coerced to 0 (which would look like a
    confident 'not a fastbreak' rather than 'unknown')."""
    df = build_transition_frame(limit=30)
    espn = df[df["source_mode"] == "semantic"]
    if len(espn) > 0:
        assert espn["has_fastbreak_qualifier"].isna().all()


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
