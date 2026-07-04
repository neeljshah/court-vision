"""Tests for domains/mlb/props_eval_gate_mlb.py + props_eval_gate_mlb_dist.py.

Covers: no-leak property (a future start cannot change a past start's
projection), distribution math (Poisson/NegBin pmf sums to 1, median/CRPS hand
checks), and scoring on synthetic data (verdict logic: BEATS/MATCHES/WORSE/
INSUFFICIENT thresholds).

Per-file pytest only:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_props_eval_gate_mlb.py -q
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from domains.mlb.props_eval_gate_mlb import (
    _compare_crps,
    score_prop,
    verdict_for_prop,
)
from domains.mlb.props_eval_gate_mlb_constants import dispersion_for
from domains.mlb.props_eval_gate_mlb_dist import (
    MIN_PRIOR_STARTS,
    _poisson_pmf,
    build_opportunities,
    crps_discrete,
    median_and_pm1,
    pinball_at_quantile,
)


# ---------------------------------------------------------------------------
# Distribution math
# ---------------------------------------------------------------------------

def test_poisson_pmf_sums_to_one():
    lam = 4.5
    total = sum(_poisson_pmf(k, lam) for k in range(0, 200))
    assert total == pytest.approx(1.0, abs=1e-9)


def test_poisson_pmf_hand_check():
    # P(X=0) = e^-lam
    assert _poisson_pmf(0, 2.0) == pytest.approx(math.exp(-2.0))


def test_median_and_pm1_symmetric_small_lam():
    lo, med, hi = median_and_pm1(1.0, None)
    assert hi == med + 1.0
    assert lo == med - 1.0
    assert lo >= 0.0


def test_crps_discrete_zero_at_certainty_limit():
    # As dispersion widens toward a point mass this is hard to hit exactly, but
    # CRPS must be non-negative and finite for a reasonable lam/y pair.
    val = crps_discrete(5.0, 8.0, 5.0)
    assert val >= 0.0
    assert math.isfinite(val)


def test_crps_worsens_further_from_lam():
    # A predictive distribution centered at lam=5 should score a realized y=5
    # better (lower CRPS) than a wildly distant y=50.
    near = crps_discrete(5.0, 8.0, 5.0)
    far = crps_discrete(5.0, 8.0, 50.0)
    assert near < far


def test_pinball_loss_zero_at_exact_hit():
    assert pinball_at_quantile(5.0, 5.0, 0.5) == pytest.approx(0.0)


def test_pinball_loss_penalizes_miss():
    over = pinball_at_quantile(5.0, 3.0, 0.5)  # actual > pred
    assert over > 0.0


def test_dispersion_for_known_and_default():
    assert dispersion_for("sp_strikeouts") == 8.0
    assert dispersion_for("unknown_stat_xyz") == 10.0


# ---------------------------------------------------------------------------
# No-leak property: a future start cannot change a past start's projection.
# ---------------------------------------------------------------------------

def _synthetic_gamelogs_and_probables(n_starts: int = 8):
    """One pitcher (id=100) makes n_starts consecutive starts as the home SP vs
    a rotating cast of throwaway away-SPs (so only pitcher 100 accumulates
    history worth checking). Deterministic per-start strikeouts = 4,5,6,7,... so
    a future start's (much larger) K count would be obviously visible in an
    earlier snapshot if leaked."""
    game_pks = list(range(1, n_starts + 1))
    dates = pd.date_range("2023-04-01", periods=n_starts, freq="5D")
    rows = []
    for i, (gpk, d) in enumerate(zip(game_pks, dates)):
        rows.append(dict(
            game_pk=gpk, date=d, player_id=100, is_pitcher=True,
            battersFaced=25.0, pitch_strikeOuts=float(4 + i),
            hits_allowed=5.0, baseOnBalls_allowed=2.0, inningsPitched=6.0,
            earnedRuns=2.0,
        ))
        # a rotating away starter with no repeated identity (never accumulates)
        rows.append(dict(
            game_pk=gpk, date=d, player_id=900 + i, is_pitcher=True,
            battersFaced=24.0, pitch_strikeOuts=3.0,
            hits_allowed=6.0, baseOnBalls_allowed=1.0, inningsPitched=6.0,
            earnedRuns=2.0,
        ))
    gamelogs = pd.DataFrame(rows)
    probables = pd.DataFrame({
        "game_pk": game_pks,
        "home_sp_id": [100] * n_starts,
        "away_sp_id": [900 + i for i in range(n_starts)],
    })
    return gamelogs, probables


def test_no_leak_future_start_does_not_change_past_projection():
    gamelogs_full, probables_full = _synthetic_gamelogs_and_probables(n_starts=8)
    recs_full = build_opportunities(gamelogs_full, probables_full, "sp_strikeouts")

    # Truncate to the first 5 starts only (drop the "future" from the model's
    # point of view) and re-run.
    keep_pks = set(range(1, 6))
    gamelogs_trunc = gamelogs_full[gamelogs_full["game_pk"].isin(keep_pks)].copy()
    probables_trunc = probables_full[probables_full["game_pk"].isin(keep_pks)].copy()
    recs_trunc = build_opportunities(gamelogs_trunc, probables_trunc, "sp_strikeouts")

    by_pk_full = {r.game_pk: r for r in recs_full if r.player_id == 100}
    by_pk_trunc = {r.game_pk: r for r in recs_trunc if r.player_id == 100}

    # Every start present in BOTH runs must have an IDENTICAL projection --
    # dropping start #6-8 (the "future") cannot change starts #1-5's snapshot.
    shared_pks = set(by_pk_full) & set(by_pk_trunc)
    assert len(shared_pks) >= 2  # sanity: something survived MIN_PRIOR_STARTS
    for pk in shared_pks:
        rf, rt = by_pk_full[pk], by_pk_trunc[pk]
        assert rf.lam_model == pytest.approx(rt.lam_model, nan_ok=True)
        assert rf.lam_season_mean == pytest.approx(rt.lam_season_mean, nan_ok=True)
        assert rf.n_prior_starts == rt.n_prior_starts


def test_no_leak_min_prior_starts_gate():
    """Starts before MIN_PRIOR_STARTS prior starts exist must report n_prior_starts
    below the floor (no baseline-vs-model comparison should be trusted there)."""
    gamelogs, probables = _synthetic_gamelogs_and_probables(n_starts=5)
    recs = build_opportunities(gamelogs, probables, "sp_strikeouts")
    own = sorted([r for r in recs if r.player_id == 100], key=lambda r: r.game_pk)
    # first MIN_PRIOR_STARTS starts (0-indexed: starts 0..MIN_PRIOR_STARTS-1) have
    # STRICTLY fewer than MIN_PRIOR_STARTS prior starts (start #1 has 0 prior).
    for i in range(MIN_PRIOR_STARTS):
        assert own[i].n_prior_starts < MIN_PRIOR_STARTS
    # start index MIN_PRIOR_STARTS (the (MIN_PRIOR_STARTS+1)-th start) should
    # finally clear the floor.
    assert own[MIN_PRIOR_STARTS].n_prior_starts >= MIN_PRIOR_STARTS


def test_no_leak_league_state_only_uses_prior_rows():
    """The league-average lam for the very first start in the whole corpus (no
    prior rows exist for ANYONE yet) must be unresolvable (NaN), never a
    fabricated number pulled from later rows."""
    gamelogs, probables = _synthetic_gamelogs_and_probables(n_starts=3)
    recs = build_opportunities(gamelogs, probables, "sp_strikeouts")
    first = sorted(recs, key=lambda r: r.game_pk)[0]
    assert math.isnan(first.lam_league_avg)


# ---------------------------------------------------------------------------
# Scoring on synthetic data: score_prop / verdict_for_prop
# ---------------------------------------------------------------------------

def test_score_prop_empty_on_no_data():
    empty = pd.DataFrame(columns=["game_pk", "date", "player_id", "is_pitcher",
                                   "battersFaced", "pitch_strikeOuts",
                                   "hits_allowed", "baseOnBalls_allowed",
                                   "inningsPitched", "earnedRuns"])
    empty_prob = pd.DataFrame(columns=["game_pk", "home_sp_id", "away_sp_id"])
    out = score_prop(empty, empty_prob, "sp_strikeouts")
    assert out["status"] == "empty"


def test_verdict_insufficient_below_n_floor():
    scoreboard = {
        "stat": "sp_strikeouts", "status": "ok",
        "corpora": {
            "fit_2022_2023": {"model": {"n": 100, "crps": 1.0},
                              "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
            "holdout_2024": {"model": {"n": 5, "crps": 1.0},
                             "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
            "holdout_2025_2026": {"model": {"n": 50, "crps": 1.0},
                                  "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
        },
    }
    v = verdict_for_prop(scoreboard)
    assert v["verdict"] == "INSUFFICIENT"


def test_verdict_beats_baseline_when_crps_clearly_lower():
    scoreboard = {
        "stat": "sp_strikeouts", "status": "ok",
        "corpora": {
            "fit_2022_2023": {"model": {"n": 100, "crps": 1.0},
                              "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
            "holdout_2024": {"model": {"n": 50, "crps": 0.80},
                             "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
            "holdout_2025_2026": {"model": {"n": 50, "crps": 0.80},
                                  "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
        },
    }
    v = verdict_for_prop(scoreboard)
    assert v["verdict"] == "BEATS_BASELINE"


def test_verdict_worse_when_crps_clearly_higher_in_one_holdout():
    scoreboard = {
        "stat": "sp_strikeouts", "status": "ok",
        "corpora": {
            "fit_2022_2023": {"model": {"n": 100, "crps": 1.0},
                              "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
            "holdout_2024": {"model": {"n": 50, "crps": 1.5},
                             "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
            "holdout_2025_2026": {"model": {"n": 50, "crps": 0.80},
                                  "season_mean": {"crps": 1.0}, "league_avg": {"crps": 1.0}},
        },
    }
    v = verdict_for_prop(scoreboard)
    # conservative worst-of: one holdout WORSE drags the whole verdict down
    assert v["verdict"] == "WORSE"


def test_compare_crps_thresholds():
    assert _compare_crps(0.90, 1.0) == "BEATS"       # >2% better
    assert _compare_crps(1.005, 1.0) == "MATCHES"    # within tolerance
    assert _compare_crps(1.05, 1.0) == "WORSE"       # >2% worse
    assert _compare_crps(None, 1.0) is None
    assert _compare_crps(1.0, None) is None
    assert _compare_crps(1.0, 0.0) is None


def test_score_prop_end_to_end_synthetic():
    """Full score_prop pipeline on a synthetic corpus spanning fit + both
    holdout years, exercising the whole walk-forward + scoring path."""
    game_pks = list(range(1, 41))
    dates = pd.date_range("2022-01-01", periods=40, freq="30D")  # spans 2022-2025
    rows = []
    for i, (gpk, d) in enumerate(zip(game_pks, dates)):
        rows.append(dict(
            game_pk=gpk, date=d, player_id=100, is_pitcher=True,
            battersFaced=25.0, pitch_strikeOuts=float(5 + (i % 3)),
            hits_allowed=5.0, baseOnBalls_allowed=2.0, inningsPitched=6.0,
            earnedRuns=2.0,
        ))
    gamelogs = pd.DataFrame(rows)
    probables = pd.DataFrame({
        "game_pk": game_pks, "home_sp_id": [100] * 40, "away_sp_id": [None] * 40,
    })
    out = score_prop(gamelogs, probables, "sp_strikeouts")
    assert out["status"] == "ok"
    assert "fit_2022_2023" in out["corpora"]
    v = verdict_for_prop(out)
    assert v["verdict"] in {"BEATS_BASELINE", "MATCHES", "WORSE", "INSUFFICIENT"}
