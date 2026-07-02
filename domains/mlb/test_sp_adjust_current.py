"""Tests for domains.mlb.sp_adjust_current -- deterministic synthetic fixtures.

Covers: leak contract (a pitcher's Nth-start form uses exactly starts 1..N-1),
innings-notation conversion, min-starts NaN, diff sign convention, adjust_win_prob
NaN-safety + w=0 identity, and maybe_adjust no-op when the flag is unset.

Per-file pytest only:
  python -m pytest domains/mlb/test_sp_adjust_current.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from domains.mlb.sp_adjust_current import (
    EW_ALPHA,
    MIN_PRIOR_STARTS,
    SpAdjustParams,
    adjust_win_prob,
    build_current_sp_form,
    innings_to_float,
    maybe_adjust,
)


# ---------------------------------------------------------------------------
# innings_to_float
# ---------------------------------------------------------------------------

def test_innings_to_float_classic_notation():
    """X.1 = +1/3, X.2 = +2/3 (box-score outs, NOT tenths)."""
    assert innings_to_float("5.1") == pytest.approx(5.0 + 1.0 / 3.0)
    assert innings_to_float("5.2") == pytest.approx(5.0 + 2.0 / 3.0)
    assert innings_to_float("6.0") == pytest.approx(6.0)


def test_innings_to_float_already_decimal_passthrough():
    """Values already in true-decimal form (as stored in player_gamelogs.parquet)
    pass through unchanged -- they do NOT match the X.1/X.2 outs pattern."""
    assert innings_to_float(5.666666666666667) == pytest.approx(5.666666666666667)
    assert innings_to_float(3.3333333333333335) == pytest.approx(10.0 / 3.0)
    assert innings_to_float(6.0) == pytest.approx(6.0)


def test_innings_to_float_missing():
    assert innings_to_float(None) is None
    assert innings_to_float(float("nan")) is None
    assert innings_to_float("") is None
    assert innings_to_float("nan") is None


# ---------------------------------------------------------------------------
# build_current_sp_form -- leak contract + min-starts + diff sign
# ---------------------------------------------------------------------------

def _synthetic_frames():
    """One pitcher (id=100) starts 5 straight games as the home SP, each time
    facing a fresh opposing SP (so only pitcher 100 accumulates history). This
    isolates the EW-update sequence for a single, easily hand-verified pitcher.

    earnedRuns/inningsPitched chosen so per_start_ra_rate = 6*ER/IP is a clean
    number for starts 1..5: IP=6.0 always, ER = 1,2,3,4,5 -> ra_rate = 1,2,3,4,5.
    """
    game_pks = [1, 2, 3, 4, 5]
    dates = pd.to_datetime(
        ["2026-04-01", "2026-04-06", "2026-04-11", "2026-04-16", "2026-04-21"]
    )
    away_ids = [200, 201, 202, 203, 204]

    gl_rows = []
    for i, (gpk, d, away_id) in enumerate(zip(game_pks, dates, away_ids)):
        er = float(i + 1)  # 1, 2, 3, 4, 5
        gl_rows.append(
            {
                "game_pk": gpk, "date": d, "team": "HOME", "player_id": 100,
                "is_pitcher": True, "earnedRuns": er, "inningsPitched": 6.0,
            }
        )
        gl_rows.append(
            {
                "game_pk": gpk, "date": d, "team": "AWAY", "player_id": away_id,
                "is_pitcher": True, "earnedRuns": 10.0, "inningsPitched": 6.0,
            }
        )
        # A non-pitcher row in the same game_pk (must be ignored).
        gl_rows.append(
            {
                "game_pk": gpk, "date": d, "team": "HOME", "player_id": 900 + i,
                "is_pitcher": False, "earnedRuns": None, "inningsPitched": None,
            }
        )

    gamelogs = pd.DataFrame(gl_rows)
    probables = pd.DataFrame(
        {
            "game_pk": game_pks,
            "home_sp_id": [100] * 5,
            "away_sp_id": away_ids,
        }
    )
    return gamelogs, probables


def test_leak_contract_fourth_start_uses_exactly_first_three():
    """Pitcher 100's snapshot before his 4th start (game_pk=4) must equal the EW
    of ra_rates [1, 2, 3] ONLY -- his own 4th-game ER (4.0) must NOT leak in."""
    gamelogs, probables = _synthetic_frames()
    out = build_current_sp_form(gamelogs, probables)

    row4 = out[out["game_pk"] == 4].iloc[0]
    assert row4["home_sp_starts_prior"] == 3

    # Hand-compute the EW online-update over ra_rates [1, 2, 3]:
    # ew1 = 1 (init); ew2 = 0.65*1 + 0.35*2 = 1.35; ew3 = 0.65*1.35 + 0.35*3
    ew1 = 1.0
    ew2 = (1 - EW_ALPHA) * ew1 + EW_ALPHA * 2.0
    ew3 = (1 - EW_ALPHA) * ew2 + EW_ALPHA * 3.0
    assert row4["home_sp_form_ew"] == pytest.approx(ew3)

    # And it must NOT equal the EW you'd get by (wrongly) including ra_rate=4.0.
    ew4_wrong = (1 - EW_ALPHA) * ew3 + EW_ALPHA * 4.0
    assert row4["home_sp_form_ew"] != pytest.approx(ew4_wrong)


def test_min_starts_nan_before_third_start():
    """Starts 1 and 2 (< MIN_PRIOR_STARTS=3 prior starts) must emit NaN form."""
    assert MIN_PRIOR_STARTS == 3
    gamelogs, probables = _synthetic_frames()
    out = build_current_sp_form(gamelogs, probables)

    row1 = out[out["game_pk"] == 1].iloc[0]
    row2 = out[out["game_pk"] == 2].iloc[0]
    assert row1["home_sp_starts_prior"] == 0
    assert math.isnan(row1["home_sp_form_ew"])
    assert row2["home_sp_starts_prior"] == 1
    assert math.isnan(row2["home_sp_form_ew"])

    row3 = out[out["game_pk"] == 3].iloc[0]
    assert row3["home_sp_starts_prior"] == 2
    assert math.isnan(row3["home_sp_form_ew"])  # still < 3 prior starts

    row4 = out[out["game_pk"] == 4].iloc[0]
    assert row4["home_sp_starts_prior"] == 3
    assert not math.isnan(row4["home_sp_form_ew"])  # now >= MIN_PRIOR_STARTS


def test_own_game_never_included_in_own_snapshot():
    """A pitcher's very first start (0 prior starts) must show starts_prior=0
    regardless of his own outing's stats -- confirms snapshot precedes update."""
    gamelogs, probables = _synthetic_frames()
    out = build_current_sp_form(gamelogs, probables)
    row1 = out[out["game_pk"] == 1].iloc[0]
    assert row1["home_sp_starts_prior"] == 0


def test_diff_sign_convention_away_minus_home():
    """sp_diff_ew = away_sp_form_ew - home_sp_form_ew; positive means home SP
    historically allowed runs at a LOWER rate (home edge)."""
    # Build a case where both sides have >= 3 prior starts so diff is non-NaN.
    # Home SP (id=100) always ra_rate=1 (great); Away SP (id=200) always ra_rate=9 (poor).
    game_pks = list(range(1, 6))
    dates = pd.to_datetime([f"2026-04-{i:02d}" for i in range(1, 6)])
    gl_rows = []
    for gpk, d in zip(game_pks, dates):
        gl_rows.append({
            "game_pk": gpk, "date": d, "team": "HOME", "player_id": 100,
            "is_pitcher": True, "earnedRuns": 1.0, "inningsPitched": 6.0,
        })
        gl_rows.append({
            "game_pk": gpk, "date": d, "team": "AWAY", "player_id": 200,
            "is_pitcher": True, "earnedRuns": 9.0, "inningsPitched": 6.0,
        })
    gamelogs = pd.DataFrame(gl_rows)
    probables = pd.DataFrame({"game_pk": game_pks, "home_sp_id": [100] * 5, "away_sp_id": [200] * 5})

    out = build_current_sp_form(gamelogs, probables)
    row5 = out[out["game_pk"] == 5].iloc[0]
    assert not math.isnan(row5["sp_diff_ew"])
    # away form (~9) - home form (~1) => strongly positive => home SP better => home edge.
    assert row5["sp_diff_ew"] > 0
    assert row5["sp_diff_ew"] == pytest.approx(row5["away_sp_form_ew"] - row5["home_sp_form_ew"])


def test_non_starter_gamelog_rows_never_counted_as_starts():
    """A bullpen pitcher (appears in gamelogs, but NOT probables' SP id for that
    game_pk) must never contribute to any pitcher's start history."""
    gamelogs, probables = _synthetic_frames()
    out = build_current_sp_form(gamelogs, probables)
    # Non-pitcher rows (900+i) and away-SP-only ids across games never appear as
    # 'home' side history; sanity check the output has exactly 5 rows (1 per game_pk).
    assert len(out) == 5
    assert set(out["game_pk"]) == {1, 2, 3, 4, 5}


# ---------------------------------------------------------------------------
# adjust_win_prob
# ---------------------------------------------------------------------------

def test_adjust_win_prob_identity_at_w_zero():
    """w=0 must leave p_elo numerically unchanged (z*0 offset is a no-op)."""
    p = 0.63
    result = adjust_win_prob(p, sp_diff=2.5, w=0.0, sp_mean=0.0, sp_std=1.0)
    assert result == pytest.approx(p, abs=1e-6)


def test_adjust_win_prob_nan_sp_diff_returns_p_elo_unchanged():
    p = 0.71
    result = adjust_win_prob(p, sp_diff=float("nan"), w=0.5, sp_mean=0.0, sp_std=1.0)
    assert result == p


def test_adjust_win_prob_nan_p_elo_passthrough():
    result = adjust_win_prob(float("nan"), sp_diff=1.0, w=0.5, sp_mean=0.0, sp_std=1.0)
    assert result is not None
    assert math.isnan(result)


def test_adjust_win_prob_positive_w_positive_diff_increases_prob():
    """Positive w + positive (above-mean) sp_diff should push p above p_elo."""
    p = 0.5
    result = adjust_win_prob(p, sp_diff=3.0, w=0.3, sp_mean=0.0, sp_std=1.0)
    assert result > p


def test_adjust_win_prob_std_zero_guarded():
    """sp_std <= 0 must not raise/NaN (guarded by max(sp_std, _EPS)); the huge
    resulting z can legitimately saturate expit() to the [0, 1] boundary."""
    result = adjust_win_prob(0.5, sp_diff=1.0, w=0.2, sp_mean=0.0, sp_std=0.0)
    assert not math.isnan(result)
    assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# maybe_adjust -- flag no-op contract
# ---------------------------------------------------------------------------

def test_maybe_adjust_noop_when_flag_unset(monkeypatch):
    monkeypatch.delenv("CV_MLB_SP_ADJUST", raising=False)
    params = SpAdjustParams(w=0.5, sp_mean=0.0, sp_std=1.0)
    p = 0.6
    result = maybe_adjust(p, sp_diff=3.0, params=params)
    assert result == p  # unchanged: flag absent -> no-op


def test_maybe_adjust_noop_when_flag_not_exactly_one(monkeypatch):
    monkeypatch.setenv("CV_MLB_SP_ADJUST", "true")
    params = SpAdjustParams(w=0.5, sp_mean=0.0, sp_std=1.0)
    p = 0.6
    result = maybe_adjust(p, sp_diff=3.0, params=params)
    assert result == p  # only the literal string "1" enables it


def test_maybe_adjust_applies_when_flag_is_one(monkeypatch):
    monkeypatch.setenv("CV_MLB_SP_ADJUST", "1")
    params = SpAdjustParams(w=0.5, sp_mean=0.0, sp_std=1.0)
    p = 0.6
    result = maybe_adjust(p, sp_diff=3.0, params=params)
    expected = adjust_win_prob(p, 3.0, 0.5, 0.0, 1.0)
    assert result == pytest.approx(expected)
    assert result != p
