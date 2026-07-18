"""scripts.platformkit.answers.test_winprob_extreme_states -- property tests over
extreme game states (blowouts, 2OT, buzzer-beater, walk-off), never a $/ROI/edge
claim -- calibration/sharpness/crash-safety only.

LAYER 1 (always runs, synthetic): pure-function envelope + monotonicity checkers,
exercised against canned (including NaN-poisoned) envelopes -- no subprocess, no data/.

LAYER 2 (auto-skips without data): a module-level probe dispatch call; if the
worktree has no corpus (status != "ok") every real test in this layer calls
pytest.skip("corpus unavailable") so this file is green on a fresh clone AND on
the pod where predict_matchup has a real corpus wired.

Run: python -m pytest scripts/platformkit/answers/test_winprob_extreme_states.py -q
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

import pytest

from scripts.platformkit.answers.winprob_dispatch import dispatch

MONO_TOL = 0.02


def check_envelope(env: Dict[str, Any]) -> None:
    """Fail-closed shape check: status must be ok|no_data; ok must carry a
    finite p_home_win in [0,1]; no_data must carry a human-readable note."""
    status = env.get("status")
    assert status in ("ok", "no_data"), f"unexpected status: {env}"
    if status == "no_data":
        assert env.get("note"), f"no_data envelope missing note: {env}"
        return
    p = env.get("p_home_win")
    assert p is not None, f"ok envelope missing p_home_win: {env}"
    assert not (isinstance(p, float) and math.isnan(p)), f"p_home_win is NaN: {env}"
    assert 0.0 <= float(p) <= 1.0, f"p_home_win out of [0,1]: {env}"


def check_monotone(pairs: List[Tuple[Any, float]]) -> None:
    """pairs = [(state_label, p), ...] ordered by increasing home advantage;
    p must be non-decreasing within MONO_TOL."""
    for (s_prev, p_prev), (s_next, p_next) in zip(pairs, pairs[1:]):
        assert p_next >= p_prev - MONO_TOL, (
            f"monotonicity violation: {s_prev}->p={p_prev} then {s_next}->p={p_next}")


# ---------------------------------------------------------------------------
# LAYER 1 -- synthetic, always runs
# ---------------------------------------------------------------------------

def test_check_envelope_accepts_ok() -> None:
    check_envelope({"status": "ok", "p_home_win": 0.73})


def test_check_envelope_accepts_no_data_with_note() -> None:
    check_envelope({"status": "no_data", "note": "corpus unavailable"})


def test_check_envelope_rejects_no_data_without_note() -> None:
    with pytest.raises(AssertionError):
        check_envelope({"status": "no_data"})


def test_check_envelope_rejects_missing_prob() -> None:
    with pytest.raises(AssertionError):
        check_envelope({"status": "ok"})


def test_check_envelope_rejects_nan_prob() -> None:
    with pytest.raises(AssertionError):
        check_envelope({"status": "ok", "p_home_win": float("nan")})


def test_check_envelope_rejects_out_of_range_prob() -> None:
    with pytest.raises(AssertionError):
        check_envelope({"status": "ok", "p_home_win": 1.4})


def test_check_envelope_rejects_bad_status() -> None:
    with pytest.raises(AssertionError):
        check_envelope({"status": "weird"})


def test_check_monotone_accepts_nondecreasing() -> None:
    check_monotone([("lead+5", 0.55), ("lead+15", 0.70), ("lead+30", 0.97)])


def test_check_monotone_accepts_within_tolerance() -> None:
    check_monotone([("lead+5", 0.55), ("lead+15", 0.54)])  # within MONO_TOL


def test_check_monotone_rejects_real_violation() -> None:
    with pytest.raises(AssertionError):
        check_monotone([("lead+5", 0.60), ("lead+15", 0.30)])


# ---------------------------------------------------------------------------
# LAYER 2 -- real dispatch, auto-skips when the corpus is unavailable
# ---------------------------------------------------------------------------

_PROBE = dispatch("nba", "BOS", "LAL", {"elapsed": 24.0, "home_score": 60, "away_score": 55})


def _skip_if_no_corpus() -> None:
    if _PROBE.get("status") != "ok":
        pytest.skip(f"corpus unavailable: {_PROBE.get('note')}")


def test_nba_monotone_lead_at_elapsed_24() -> None:
    _skip_if_no_corpus()
    pairs = []
    for lead in (5, 15, 30):
        env = dispatch("nba", "BOS", "LAL",
                       {"elapsed": 24.0, "home_score": 60 + lead, "away_score": 60})
        check_envelope(env)
        pairs.append((f"lead+{lead}", env["p_home_win"]))
    check_monotone(pairs)


def test_nba_down_30_late_is_near_zero() -> None:
    _skip_if_no_corpus()
    env = dispatch("nba", "BOS", "LAL", {"elapsed": 40.0, "home_score": 60, "away_score": 90})
    check_envelope(env)
    if env["status"] == "ok":
        assert env["p_home_win"] <= 0.10, f"expected near-0 p, got {env}"


def test_nba_late_lead_12_is_near_one() -> None:
    _skip_if_no_corpus()
    env = dispatch("nba", "BOS", "LAL", {"elapsed": 47.9, "home_score": 100, "away_score": 88})
    check_envelope(env)
    if env["status"] == "ok":
        assert env["p_home_win"] >= 0.95, f"expected near-1 p, got {env}"


def test_nba_2ot_tie_is_near_coinflip() -> None:
    _skip_if_no_corpus()
    env = dispatch("nba", "BOS", "LAL", {"elapsed": 58.0, "home_score": 120, "away_score": 120})
    check_envelope(env)
    if env["status"] == "ok":
        assert 0.25 <= env["p_home_win"] <= 0.75, f"expected near-coinflip p, got {env}"


def test_nba_buzzer_beater_lead_3_is_near_one() -> None:
    _skip_if_no_corpus()
    env = dispatch("nba", "BOS", "LAL", {"elapsed": 47.99, "home_score": 100, "away_score": 97})
    check_envelope(env)
    if env["status"] == "ok":
        assert env["p_home_win"] >= 0.90, f"expected near-1 p, got {env}"


def test_mlb_bottom_9_up_9_is_near_one() -> None:
    _skip_if_no_corpus()
    env = dispatch("mlb", "NYY", "BOS",
                   {"inning": 9, "half": "bottom", "home_score": 10, "away_score": 1})
    check_envelope(env)
    if env["status"] == "ok":
        assert env["p_home_win"] >= 0.97, f"expected near-1 p, got {env}"


def test_mlb_top_9_down_9_is_near_zero() -> None:
    _skip_if_no_corpus()
    env = dispatch("mlb", "NYY", "BOS",
                   {"inning": 9, "half": "top", "home_score": 1, "away_score": 10})
    check_envelope(env)
    if env["status"] == "ok":
        assert env["p_home_win"] <= 0.05, f"expected near-0 p, got {env}"


def test_mlb_inning_5_tie_is_moderate() -> None:
    _skip_if_no_corpus()
    env = dispatch("mlb", "NYY", "BOS",
                   {"inning": 5, "half": "top", "home_score": 3, "away_score": 3})
    check_envelope(env)
    if env["status"] == "ok":
        assert 0.30 <= env["p_home_win"] <= 0.72, f"expected moderate p, got {env}"


def test_tennis_two_sets_up_no_crash() -> None:
    _skip_if_no_corpus()
    env = dispatch("tennis", "Player A", "Player B", {"sets_home": 2, "sets_away": 0})
    check_envelope(env)  # ok-with-p or honest no_data -- either is acceptable, never a crash


def test_soccer_late_lead_2_no_crash() -> None:
    _skip_if_no_corpus()
    env = dispatch("soccer", "Arsenal", "Chelsea", {"elapsed": 85.0, "home_score": 2, "away_score": 0})
    check_envelope(env)
    if env["status"] == "ok":
        assert env["p_home_win"] >= 0.90, f"expected near-1 p if in-game supported, got {env}"
