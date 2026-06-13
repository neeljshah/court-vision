"""tests.platform.test_hypothesis_enumerator — Unit tests for the hypothesis enumerator.

Checks:
  - Enumeration is deterministic (two calls produce identical output).
  - Result is finite and bounded within a sane upper limit.
  - Every base column appears in at least one candidate.
  - Coverage function runs against real catalog source files.
  - Tested count >= 0; enumerated > 0.
  - Summary text contains no edge / profitability claims.
"""
from __future__ import annotations

import math
from typing import Dict, List

import pytest

from scripts.research_harness.hypothesis_enumerator import (
    NBA_BASE_COLS,
    SINGLE_TRANSFORMS,
    PAIRWISE_JOINTS,
    SPORT_BASE_COLS,
    Candidate,
    CoverageResult,
    compute_all_coverage,
    compute_coverage,
    enumerate_candidates,
    extract_tested_names,
    format_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_SPORTS = list(SPORT_BASE_COLS.keys())

# Theoretical maximum per sport: n_cols * n_single + C(n_cols,2) * n_joint
def _theoretical_max(n_cols: int) -> int:
    return n_cols * len(SINGLE_TRANSFORMS) + math.comb(n_cols, 2) * len(PAIRWISE_JOINTS)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_enumeration_is_deterministic() -> None:
    """Two calls to enumerate_candidates must return identical output."""
    for sport, cols in SPORT_BASE_COLS.items():
        result_a = enumerate_candidates(sport, cols)
        result_b = enumerate_candidates(sport, cols)
        assert [c.name for c in result_a] == [c.name for c in result_b], (
            f"{sport}: enumeration not deterministic"
        )


def test_compute_coverage_is_deterministic() -> None:
    """compute_coverage called twice must yield the same candidate list and tested set."""
    for sport in ALL_SPORTS:
        r1 = compute_coverage(sport)
        r2 = compute_coverage(sport)
        assert [c.name for c in r1.candidates] == [c.name for c in r2.candidates]
        assert r1.tested_set == r2.tested_set


def test_compute_all_coverage_is_deterministic() -> None:
    """compute_all_coverage called twice must return the same result."""
    all_a = compute_all_coverage()
    all_b = compute_all_coverage()
    for sport in ALL_SPORTS:
        assert [c.name for c in all_a[sport].candidates] == [
            c.name for c in all_b[sport].candidates
        ]


# ---------------------------------------------------------------------------
# Finiteness and bounding
# ---------------------------------------------------------------------------


def test_enumeration_finite_and_bounded() -> None:
    """Each sport's candidate list must be finite and at or below the theoretical max."""
    for sport, cols in SPORT_BASE_COLS.items():
        candidates = enumerate_candidates(sport, cols)
        n = len(candidates)
        theoretical = _theoretical_max(len(cols))
        assert n > 0, f"{sport}: zero candidates enumerated"
        assert n == theoretical, (
            f"{sport}: expected exactly {theoretical} candidates, got {n}"
        )
        # Absolute sanity cap: no sport with <=10 base cols should exceed 500
        assert n <= 500, f"{sport}: unreasonably large candidate count {n}"


def test_all_sports_have_candidates() -> None:
    """compute_all_coverage must return a non-empty result for every known sport."""
    results = compute_all_coverage()
    assert set(results.keys()) == set(ALL_SPORTS)
    for sport, r in results.items():
        assert r.n_enumerated > 0, f"{sport}: no candidates"


# ---------------------------------------------------------------------------
# Column coverage
# ---------------------------------------------------------------------------


def test_every_base_col_appears_in_candidates() -> None:
    """Every base column must appear in at least one candidate for its sport."""
    for sport, cols in SPORT_BASE_COLS.items():
        candidates = enumerate_candidates(sport, cols)
        covered_cols = {col for c in candidates for col in c.cols}
        for col in cols:
            assert col in covered_cols, (
                f"{sport}: base col '{col}' not present in any candidate"
            )


# ---------------------------------------------------------------------------
# Coverage function (real catalog source files)
# ---------------------------------------------------------------------------


def test_extract_tested_names_runs_and_returns_list() -> None:
    """extract_tested_names must return a list (possibly empty) without raising."""
    for sport in ALL_SPORTS:
        names = extract_tested_names(sport)
        assert isinstance(names, list), f"{sport}: expected list, got {type(names)}"


def test_coverage_sane_counts() -> None:
    """Tested count must be in [0, n_enumerated]; n_enumerated must be positive."""
    for sport in ALL_SPORTS:
        r = compute_coverage(sport)
        assert r.n_enumerated > 0, f"{sport}: zero candidates"
        assert r.n_tested >= 0, f"{sport}: negative tested count"
        assert r.n_tested <= r.n_enumerated, (
            f"{sport}: tested ({r.n_tested}) > enumerated ({r.n_enumerated})"
        )
        assert r.n_untested == r.n_enumerated - r.n_tested
        assert 0.0 <= r.coverage_pct <= 100.0


def test_coverage_pct_formula() -> None:
    """coverage_pct must equal 100 * tested / enumerated."""
    for sport in ALL_SPORTS:
        r = compute_coverage(sport)
        expected = 100.0 * r.n_tested / r.n_enumerated if r.n_enumerated else 0.0
        assert abs(r.coverage_pct - expected) < 1e-9


def test_tested_names_are_strings() -> None:
    """All extracted tested names must be non-empty strings."""
    for sport in ALL_SPORTS:
        names = extract_tested_names(sport)
        for n in names:
            assert isinstance(n, str) and len(n) > 0, (
                f"{sport}: invalid tested name {n!r}"
            )


# ---------------------------------------------------------------------------
# No edge claims in output
# ---------------------------------------------------------------------------

_EDGE_WORDS = (
    "profitable", "profitability", "edge", "roi", "bet", "betting",
    "alpha", "arbitrage", "winning",
)


def test_summary_contains_no_edge_claims() -> None:
    """format_summary must not assert profitability or edge."""
    results = compute_all_coverage()
    summary = format_summary(results).lower()
    for word in _EDGE_WORDS:
        assert word not in summary, (
            f"format_summary contains edge-claim word '{word}'"
        )


def test_candidate_names_contain_no_edge_claims() -> None:
    """Candidate names must not assert profitability or edge."""
    results = compute_all_coverage()
    for sport, r in results.items():
        for c in r.candidates:
            name_lower = c.name.lower()
            for word in _EDGE_WORDS:
                assert word not in name_lower, (
                    f"{sport}: candidate name '{c.name}' contains '{word}'"
                )


# ---------------------------------------------------------------------------
# Structural invariants on Candidate
# ---------------------------------------------------------------------------


def test_candidate_single_has_one_col() -> None:
    """All 'single' kind candidates must have exactly one col."""
    for sport, cols in SPORT_BASE_COLS.items():
        for c in enumerate_candidates(sport, cols):
            if c.kind == "single":
                assert len(c.cols) == 1, f"{sport}: single candidate has {len(c.cols)} cols"


def test_candidate_joint_has_two_cols() -> None:
    """All 'joint' kind candidates must have exactly two distinct cols."""
    for sport, cols in SPORT_BASE_COLS.items():
        for c in enumerate_candidates(sport, cols):
            if c.kind == "joint":
                assert len(c.cols) == 2, f"{sport}: joint candidate has {len(c.cols)} cols"
                assert c.cols[0] != c.cols[1], f"{sport}: joint candidate has duplicate cols"


def test_candidate_names_are_unique() -> None:
    """All candidate names within a sport must be unique."""
    for sport, cols in SPORT_BASE_COLS.items():
        names = [c.name for c in enumerate_candidates(sport, cols)]
        assert len(names) == len(set(names)), f"{sport}: duplicate candidate names"


# ---------------------------------------------------------------------------
# NBA-specific tests — basketball_nba now included with 8 base cols
# ---------------------------------------------------------------------------


def test_nba_in_sport_base_cols() -> None:
    """basketball_nba must appear in SPORT_BASE_COLS with the 8 contracted base cols."""
    assert "basketball_nba" in SPORT_BASE_COLS
    assert set(SPORT_BASE_COLS["basketball_nba"]) == set(NBA_BASE_COLS)
    assert len(NBA_BASE_COLS) == 8


def test_nba_enumeration_returns_candidates() -> None:
    """compute_coverage('basketball_nba') must enumerate candidates for all 8 base cols."""
    r = compute_coverage("basketball_nba")
    assert r.n_enumerated > 0, "basketball_nba: zero candidates enumerated"
    # Exact count: 8 cols * 5 single + C(8,2)*4 joint = 40 + 112 = 152
    expected = _theoretical_max(len(NBA_BASE_COLS))
    assert r.n_enumerated == expected, (
        f"basketball_nba: expected {expected} candidates, got {r.n_enumerated}"
    )


def test_nba_every_base_col_in_candidates() -> None:
    """Every NBA base column must appear in at least one enumerated candidate."""
    candidates = enumerate_candidates("basketball_nba", NBA_BASE_COLS)
    covered = {col for c in candidates for col in c.cols}
    for col in NBA_BASE_COLS:
        assert col in covered, f"basketball_nba: base col '{col}' missing from candidates"


def test_nba_coverage_graceful_missing_catalog() -> None:
    """compute_coverage('basketball_nba') must not raise even if catalog files are absent."""
    r = compute_coverage("basketball_nba")
    # tested_names may be empty (catalog being built); that is fine
    assert isinstance(r.tested_names, list)
    assert r.n_tested >= 0
    assert r.n_tested <= r.n_enumerated


def test_nba_determinism() -> None:
    """Two calls to compute_coverage('basketball_nba') must produce identical results."""
    r1 = compute_coverage("basketball_nba")
    r2 = compute_coverage("basketball_nba")
    assert [c.name for c in r1.candidates] == [c.name for c in r2.candidates]
    assert r1.tested_set == r2.tested_set


def test_existing_three_sports_unchanged() -> None:
    """tennis, soccer, and mlb must still enumerate exactly as before."""
    expected_counts = {
        "tennis": _theoretical_max(5),   # 5 cols → 5*5 + C(5,2)*4 = 25 + 40 = 65
        "soccer": _theoretical_max(5),   # 5 cols → 65
        "mlb": _theoretical_max(6),      # 6 cols → 6*5 + C(6,2)*4 = 30 + 60 = 90
    }
    for sport, expected in expected_counts.items():
        r = compute_coverage(sport)
        assert r.n_enumerated == expected, (
            f"{sport}: expected {expected} candidates after NBA addition, got {r.n_enumerated}"
        )


# ---------------------------------------------------------------------------
# Unknown sport raises ValueError
# ---------------------------------------------------------------------------


def test_unknown_sport_raises() -> None:
    """compute_coverage with an unknown sport must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown sport"):
        compute_coverage("cricket")
