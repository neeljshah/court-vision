"""Per-file unit tests for ingame_prop_repricer (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_ingame_prop_repricer.py -q

ACCEPTANCE (all tested here):
  - Pregame (frac=0) returns same number as engine pregame p_over.
  - Mid-game freshness shrink reduces P(over line) when no stat realized yet.
  - realized_so_far >= line short-circuits to 1.0 (already cleared).
  - residual < 0 (line - realized) short-circuits to 1.0 (already cleared).
  - FINAL (frac >= 1.0) returns None (no in-game bet -- settler handles).
  - Bad inputs (None lam, NaN frac, negative lam) -> None (clean skip).
  - reprice_from_dist passes through engine dist correctly + rejects bad status.
  - Non-additive stat falls back to pregame p_over at original line.
  - No $ / pnl / roi field anywhere (the module returns floats only).
"""
from __future__ import annotations

import math

import pytest

from scripts.platformkit.ingame.ingame_prop_repricer import (
    reprice_from_dist,
    reprice_prop,
)


def _poisson_p_over_factory(lam: float):
    """Build a vanilla Poisson p_over(line) callable for assertion deltas.

    P(X > line) for integer-line semantics = 1 - CDF(floor(line)). Matches the
    soccer engine's _make_p_over Poisson branch.
    """
    def p_over(line: float) -> float:
        # P(X > line) when line is e.g. 1.5 -> P(X >= 2) = 1 - CDF(1).
        k = int(math.floor(float(line)))
        if k < 0:
            return 1.0
        cdf = 0.0
        for i in range(k + 1):
            cdf += math.exp(-lam) * (lam ** i) / math.factorial(i)
        return max(0.0, min(1.0, 1.0 - cdf))
    return p_over


# ----------------------------------------------------------------------------- #
# Happy path
# ----------------------------------------------------------------------------- #

def test_pregame_frac_zero_matches_engine_full_pover():
    """frac_elapsed=0 -> same number the pregame p_over gives at this line."""
    lam = 2.0  # e.g. expected hits = 2.0 over full game
    line = 1.5
    p_engine = _poisson_p_over_factory(lam)(line)
    p_rep = reprice_prop(lam_full=lam, line=line, frac_elapsed=0.0,
                         stat_canonical="Hits")
    assert p_rep is not None
    assert abs(p_rep - p_engine) < 1e-9


def test_midgame_freshness_shrinks_p_over_when_no_realized():
    """Half-game in, no hits yet -> P(over 1.5) drops below the pregame number."""
    lam = 2.0
    line = 1.5
    p_pre = reprice_prop(lam_full=lam, line=line, frac_elapsed=0.0,
                         stat_canonical="Hits")
    p_mid = reprice_prop(lam_full=lam, line=line, frac_elapsed=0.5,
                         stat_canonical="Hits")
    assert p_pre is not None and p_mid is not None
    assert p_mid < p_pre, "freshness should shrink P(over) with no realized"


def test_late_game_with_realized_above_line_returns_one():
    """Already cleared 1.5 with 2 hits at frac=0.8 -> P=1.0 (no remaining needed)."""
    p = reprice_prop(lam_full=2.0, line=1.5, frac_elapsed=0.8,
                     realized_so_far=2.0, stat_canonical="Hits")
    assert p == 1.0


def test_realized_pushes_residual_below_zero_returns_one():
    """line 0.5, realized 1 -> residual -0.5 -> auto-clear at any frac."""
    p = reprice_prop(lam_full=1.0, line=0.5, frac_elapsed=0.3,
                     realized_so_far=1.0, stat_canonical="RBIs")
    assert p == 1.0


def test_partial_progress_increases_p_over_above_no_progress_baseline():
    """At the SAME frac elapsed, 1 hit toward 1.5 line beats 0 hits."""
    common = dict(lam_full=2.0, line=1.5, frac_elapsed=0.5,
                  stat_canonical="Hits")
    p_no_progress = reprice_prop(realized_so_far=0.0, **common)
    p_one_hit = reprice_prop(realized_so_far=1.0, **common)
    assert p_no_progress is not None and p_one_hit is not None
    assert p_one_hit > p_no_progress


# ----------------------------------------------------------------------------- #
# Clean skips (None) -- never fabricated numbers
# ----------------------------------------------------------------------------- #

def test_final_returns_none():
    """frac_elapsed >= 1.0 -> None (no in-game bet)."""
    assert reprice_prop(lam_full=2.0, line=1.5, frac_elapsed=1.0,
                        stat_canonical="Hits") is None
    assert reprice_prop(lam_full=2.0, line=1.5, frac_elapsed=1.5,
                        stat_canonical="Hits") is None


def test_none_lam_returns_none():
    assert reprice_prop(lam_full=None, line=1.5, frac_elapsed=0.4,
                        stat_canonical="Hits") is None


def test_negative_lam_returns_none():
    assert reprice_prop(lam_full=-0.1, line=1.5, frac_elapsed=0.4,
                        stat_canonical="Hits") is None


def test_nan_lam_returns_none():
    assert reprice_prop(lam_full=float("nan"), line=1.5, frac_elapsed=0.4,
                        stat_canonical="Hits") is None


def test_bad_frac_returns_none():
    """frac < 0 or NaN -> None."""
    assert reprice_prop(lam_full=2.0, line=1.5, frac_elapsed=-0.1,
                        stat_canonical="Hits") is None
    assert reprice_prop(lam_full=2.0, line=1.5, frac_elapsed=float("nan"),
                        stat_canonical="Hits") is None


def test_bad_line_returns_none():
    assert reprice_prop(lam_full=2.0, line="not-a-number",  # type: ignore[arg-type]
                        frac_elapsed=0.5, stat_canonical="Hits") is None


# ----------------------------------------------------------------------------- #
# Non-additive fallback
# ----------------------------------------------------------------------------- #

def test_non_additive_stat_falls_back_to_pregame_p_over():
    """An unknown / non-additive stat re-uses the supplied pregame p_over at line."""
    pregame_p_over = _poisson_p_over_factory(0.7)
    p = reprice_prop(lam_full=0.7, line=0.5, frac_elapsed=0.4,
                     p_over_full=pregame_p_over,
                     stat_canonical="Anytime Goal")
    expected = pregame_p_over(0.5)
    assert p is not None
    assert abs(p - expected) < 1e-9


def test_non_additive_without_pregame_callable_returns_none():
    """No callable provided + non-additive stat -> None (never fabricated)."""
    p = reprice_prop(lam_full=0.7, line=0.5, frac_elapsed=0.4,
                     stat_canonical="Anytime Goal")
    assert p is None


# ----------------------------------------------------------------------------- #
# reprice_from_dist wrapper
# ----------------------------------------------------------------------------- #

def test_reprice_from_dist_ok_path():
    """Wrapper passes lam/model through and returns shrunken P(over)."""
    dist = {"lam": 2.0, "model": "poisson", "p_over": _poisson_p_over_factory(2.0),
            "status": "ok"}
    p_pre = reprice_from_dist(dist, line=1.5, frac_elapsed=0.0,
                              stat_canonical="Hits")
    p_mid = reprice_from_dist(dist, line=1.5, frac_elapsed=0.5,
                              stat_canonical="Hits")
    assert p_pre is not None and p_mid is not None
    assert p_mid < p_pre


def test_reprice_from_dist_rejects_non_ok_status():
    """status != 'ok' (unknown rate / exposure) -> None."""
    dist = {"lam": None, "model": None, "p_over": None, "status": "unknown"}
    assert reprice_from_dist(dist, line=1.5, frac_elapsed=0.5,
                             stat_canonical="Hits") is None


def test_reprice_from_dist_rejects_non_dict():
    assert reprice_from_dist(None, line=1.5, frac_elapsed=0.5,  # type: ignore[arg-type]
                             stat_canonical="Hits") is None
    assert reprice_from_dist("not a dict", line=1.5, frac_elapsed=0.5,  # type: ignore[arg-type]
                             stat_canonical="Hits") is None


# ----------------------------------------------------------------------------- #
# Probability bounds + safety
# ----------------------------------------------------------------------------- #

def test_output_always_in_unit_interval():
    """Across a sweep of fracs / lines / realized values, output stays in [0,1]."""
    for lam in (0.1, 1.0, 5.0):
        for line in (0.5, 1.5, 3.5):
            for frac in (0.0, 0.25, 0.5, 0.75, 0.99):
                for realized in (0.0, 1.0, 2.0):
                    p = reprice_prop(lam_full=lam, line=line,
                                     frac_elapsed=frac,
                                     realized_so_far=realized,
                                     stat_canonical="Hits")
                    if p is not None:
                        assert 0.0 <= p <= 1.0, (
                            "out of bounds: lam=%s line=%s frac=%s realized=%s "
                            "p=%s" % (lam, line, frac, realized, p))


def test_never_raises_on_pathological_inputs():
    """Pathological inputs -> None, never an exception."""
    pathological = [
        (None, 1.5, 0.5, 0.0),
        (float("inf"), 1.5, 0.5, 0.0),
        (2.0, float("inf"), 0.5, 0.0),
        (2.0, 1.5, -1.0, 0.0),
        (2.0, 1.5, 0.5, -1.0),  # negative realized -> coerced to 0
    ]
    for lam, line, frac, realized in pathological:
        p = reprice_prop(lam_full=lam, line=line, frac_elapsed=frac,
                         realized_so_far=realized, stat_canonical="Hits")
        # None or a valid float -- never raises.
        assert p is None or (isinstance(p, float) and 0.0 <= p <= 1.0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
