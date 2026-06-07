"""tests/test_w033_late_foul_state.py — W-033: CV_LATE_FOUL_STATE late-game fouling.

Validates all three components gated by CV_LATE_FOUL_STATE:

1.  sim._late_foul_poss_inflation — returns 1.0 when flag OFF (byte-identical).
2.  sim._late_foul_poss_inflation — returns >1.0 for trailing + low clock + bonus.
3.  sim._late_foul_poss_inflation — returns 1.0 when tied game.
4.  sim._late_foul_poss_inflation — returns 1.0 when clock > 3 min.
5.  sim._late_foul_poss_inflation — returns 1.0 when opp NOT in bonus.
6.  sim.RestOfGameSim._poss_remaining — flag OFF byte-identical to baseline.
7.  sim.RestOfGameSim._poss_remaining — flag ON inflates for trailing+bonus.
8.  inplay_winprob._cv_late_foul_state_enabled — respects env var.
9.  inplay_winprob._compute_late_foul_sharpening — returns 0.0 when no foul data.
10. inplay_winprob._compute_late_foul_sharpening — positive when home trailing+imbalance.
11. inplay_winprob.features_from_snapshot — flag OFF: no foul injection (byte-identical).
12. inplay_winprob.features_from_snapshot — flag ON: injects foul features at endQ3.
13. state_featurizer._compute_pace_state — flag OFF: no late_foul_active key.
14. state_featurizer._compute_pace_state — flag ON: late_foul_active=1 for active scenario.
15. state_featurizer._compute_pace_state — flag ON: late_foul_active=0 for non-active.
16. state_featurizer._compute_pace_state — flag ON: late_foul_active=0 when clock > 3 min.
17. sim inflation factor clamps at LATE_FOUL_INFLATION_BASE at max deficit.
18. sim inflation factor ramps linearly with margin.
19. inplay_winprob._compute_late_foul_sharpening — returns 0.0 for large margin (> 15).
20. RestOfGameSim.simulate — flag OFF produces same result as baseline (seed-matched).

All tests are offline — no network, no filesystem access.
"""
from __future__ import annotations

import copy
import importlib
import os
import sys
from typing import Any, Dict
from unittest import mock

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_flag(monkeypatch, value: str) -> None:
    """Set CV_LATE_FOUL_STATE env var for the duration of a test."""
    monkeypatch.setenv("CV_LATE_FOUL_STATE", value)
    # Force re-evaluation of the module-level bool in state_featurizer
    import src.ingame.state_featurizer as sf
    monkeypatch.setattr(sf, "_CV_LATE_FOUL_STATE",
                        value.lower() in ("1", "true", "yes"))


def _poss_row(
    rem_sec: float,
    margin: float,
    home_in_bonus: int,
    away_in_bonus: int,
    total_poss: float = 60.0,
    elapsed: float = 2520.0,
) -> Dict[str, Any]:
    """Minimal game_row for _poss_remaining tests."""
    return {
        "game_remaining_sec": rem_sec,
        "total_poss_count": total_poss,
        "game_elapsed_sec": elapsed,
        "score_margin": margin,
        "home_in_bonus": home_in_bonus,
        "away_in_bonus": away_in_bonus,
    }


def _pace_kwargs(
    game_sec: int = 2520,
    game_rem: int = 360,
    team_fouls: Dict | None = None,
    score_deltas=None,
) -> Dict[str, Any]:
    """Minimal kwargs for _compute_pace_state."""
    return dict(
        game_sec=game_sec,
        game_rem=game_rem,
        poss_count={"home": 30, "away": 30},
        last_fg_sec=None,
        last_score_sec=None,
        last_home_fg_sec=None,
        last_away_fg_sec=None,
        score_event_deltas=score_deltas or [(2, 0), (0, 2)] * 30,
        team_fouls_period=team_fouls or {"home": 5, "away": 3},
        home_prior_pace=98.0,
        away_prior_pace=100.0,
    )


# ===========================================================================
# 1. sim._late_foul_poss_inflation — flag OFF → 1.0
# ===========================================================================
def test_late_foul_inflation_flag_off(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "0")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    row = _poss_row(rem_sec=120.0, margin=-8.0, home_in_bonus=0, away_in_bonus=1)
    from src.sim.rest_of_game_sim import _late_foul_poss_inflation
    # Re-import after reload
    result = sim_mod._late_foul_poss_inflation(row)
    assert result == 1.0, f"flag OFF should return 1.0, got {result}"


# ===========================================================================
# 2. sim._late_foul_poss_inflation — flag ON, trailing + low clock + bonus → >1
# ===========================================================================
def test_late_foul_inflation_active(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    # Home trailing by 8, 90s left.
    # Featurizer convention: home_in_bonus=1 means HOME has 5+ fouls (HOME in penalty)
    # → HOME fouls intentionally → AWAY player shoots FTs.
    row = _poss_row(rem_sec=90.0, margin=-8.0, home_in_bonus=1, away_in_bonus=0)
    result = sim_mod._late_foul_poss_inflation(row)
    assert result > 1.0, f"active foul scenario should inflate, got {result}"
    assert result <= 1.21, f"inflation too large: {result}"


# ===========================================================================
# 3. sim._late_foul_poss_inflation — tied game → 1.0
# ===========================================================================
def test_late_foul_inflation_tied(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    row = _poss_row(rem_sec=90.0, margin=0.0, home_in_bonus=1, away_in_bonus=1)
    result = sim_mod._late_foul_poss_inflation(row)
    assert result == 1.0, f"tied game should not inflate, got {result}"


# ===========================================================================
# 4. sim._late_foul_poss_inflation — clock > 3 min → 1.0
# ===========================================================================
def test_late_foul_inflation_clock_too_early(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    row = _poss_row(rem_sec=200.0, margin=-8.0, home_in_bonus=0, away_in_bonus=1)
    result = sim_mod._late_foul_poss_inflation(row)
    assert result == 1.0, f"clock > 3 min should return 1.0, got {result}"


# ===========================================================================
# 5. sim._late_foul_poss_inflation — trailing team NOT in penalty → 1.0
# ===========================================================================
def test_late_foul_inflation_no_bonus(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    # Home trailing but HOME NOT in penalty (home_in_bonus=0)
    row = _poss_row(rem_sec=90.0, margin=-8.0, home_in_bonus=0, away_in_bonus=0)
    result = sim_mod._late_foul_poss_inflation(row)
    assert result == 1.0, f"no penalty → should not inflate, got {result}"


# ===========================================================================
# 6. RestOfGameSim._poss_remaining — flag OFF byte-identical
# ===========================================================================
def test_poss_remaining_flag_off_identical(monkeypatch):
    """With flag OFF, _poss_remaining must be byte-identical to pre-patch baseline."""
    # Use a late-game trailing row with correct penalty convention
    row = _poss_row(rem_sec=120.0, margin=-8.0, home_in_bonus=1, away_in_bonus=0,
                    total_poss=60.0, elapsed=2760.0)
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "0")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    # We verify flag OFF equals the direct formula (no inflation):
    from src.sim.rest_of_game_sim import _shrunk_pace_per48, REG_GAME_LEN_SEC
    total_poss = row["total_poss_count"]
    elapsed = row["game_elapsed_sec"]
    rem_sec = row["game_remaining_sec"]
    one_team_per48 = _shrunk_pace_per48(total_poss, elapsed, None)
    expected_base = max(0.0, one_team_per48 * (rem_sec / REG_GAME_LEN_SEC))
    sim3 = sim_mod.RestOfGameSim(n_sims=100, seed=42)
    poss_off = sim3._poss_remaining(row, priors=None)
    assert abs(poss_off - expected_base) < 1e-9, \
        f"flag OFF should equal base formula: {poss_off} vs {expected_base}"


# ===========================================================================
# 7. RestOfGameSim._poss_remaining — flag ON inflates for trailing + penalty
# ===========================================================================
def test_poss_remaining_flag_on_inflates(monkeypatch):
    # Home trailing, home_in_bonus=1 (home is in penalty → intentional foul works)
    row = _poss_row(rem_sec=120.0, margin=-8.0, home_in_bonus=1, away_in_bonus=0,
                    total_poss=60.0, elapsed=2760.0)
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "0")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    sim2 = sim_mod.RestOfGameSim(n_sims=100, seed=42)
    poss_off = sim2._poss_remaining(row, priors=None)

    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    importlib.reload(sim_mod)
    sim = sim_mod.RestOfGameSim(n_sims=100, seed=42)
    poss_on = sim._poss_remaining(row, priors=None)

    assert poss_on > poss_off, f"flag ON should inflate: {poss_on} > {poss_off}"
    assert poss_on <= poss_off * 1.21, f"inflation too large: {poss_on} / {poss_off}"


# ===========================================================================
# 8. inplay_winprob._cv_late_foul_state_enabled — respects env var
# ===========================================================================
def test_cv_late_foul_state_enabled_off(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "0")
    import importlib
    import src.prediction.inplay_winprob as wp
    importlib.reload(wp)
    assert wp._cv_late_foul_state_enabled() is False


def test_cv_late_foul_state_enabled_on(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    import importlib
    import src.prediction.inplay_winprob as wp
    importlib.reload(wp)
    assert wp._cv_late_foul_state_enabled() is True


# ===========================================================================
# 9. inplay_winprob._compute_late_foul_sharpening — returns 0.0 when no foul data
# ===========================================================================
def test_sharpening_no_foul_data():
    import src.prediction.inplay_winprob as wp
    feats = {"score_margin": 5.0}   # no pf_imbalance
    result = wp._compute_late_foul_sharpening(feats)
    assert result == 0.0, f"no foul data should return 0.0, got {result}"


# ===========================================================================
# 10. inplay_winprob._compute_late_foul_sharpening — nonzero with pf_imbalance
# ===========================================================================
def test_sharpening_with_foul_imbalance():
    import src.prediction.inplay_winprob as wp
    # Home trailing (margin < 0), home has 3 more fouls (pf_imbalance = 3)
    feats = {"score_margin": -6.0, "pf_imbalance": 3.0}
    result = wp._compute_late_foul_sharpening(feats)
    # pf_imbalance > 0 means home has more fouls → sign = -1 → negative sharpening
    assert result < 0.0, f"positive imbalance should give negative sharpening, got {result}"
    assert abs(result) <= 0.5, f"sharpening too large: {result}"


def test_sharpening_away_imbalance():
    import src.prediction.inplay_winprob as wp
    feats = {"score_margin": 6.0, "pf_imbalance": -3.0}
    result = wp._compute_late_foul_sharpening(feats)
    # pf_imbalance < 0 → sign = +1 → positive sharpening
    assert result > 0.0, f"negative imbalance should give positive sharpening, got {result}"


# ===========================================================================
# 11. features_from_snapshot — flag OFF: no extra foul injection
# ===========================================================================
def test_features_from_snapshot_flag_off(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "0")
    monkeypatch.setenv("CV_WP_FOULS_ENDQ3", "0")
    import importlib
    import src.prediction.inplay_winprob as wp
    importlib.reload(wp)
    # period=4, clock="12:00" → endQ3 snapshot
    snap = {
        "period": 4, "clock": "12:00",
        "home_q1": 28, "away_q1": 25,
        "home_q2": 27, "away_q2": 30,
        "home_q3": 25, "away_q3": 24,
        "pregame_win_prob": 0.52,
        "home_team_id": 1610612752,
        "season": "2025-26",
        "home_team_pfs_cum": 14.0,
        "away_team_pfs_cum": 11.0,
    }
    feats = wp.features_from_snapshot(snap, inject_quarter=False)
    # With flag OFF, pf_imbalance should NOT be in feats
    assert "pf_imbalance" not in feats, "flag OFF: pf_imbalance should not be injected"


# ===========================================================================
# 12. features_from_snapshot — flag ON: injects foul features at endQ3
# ===========================================================================
def test_features_from_snapshot_flag_on_endq3(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    monkeypatch.setenv("CV_WP_FOULS_ENDQ3", "0")
    import importlib
    import src.prediction.inplay_winprob as wp
    importlib.reload(wp)
    # period=4, clock="12:00" → start of Q4 = end of Q3, rem=12.0 >= 11.95 → endQ3
    snap = {
        "period": 4, "clock": "12:00",
        "home_q1": 28, "away_q1": 25,
        "home_q2": 27, "away_q2": 30,
        "home_q3": 25, "away_q3": 24,
        "pregame_win_prob": 0.52,
        "home_team_id": 1610612752,
        "season": "2025-26",
        "home_team_pfs_cum": 14.0,
        "away_team_pfs_cum": 11.0,
    }
    feats = wp.features_from_snapshot(snap, inject_quarter=False)
    # With flag ON at endQ3, pf_imbalance should be injected
    assert feats, "features_from_snapshot should return non-empty at endQ3"
    assert "pf_imbalance" in feats, "flag ON: pf_imbalance should be injected at endQ3"
    assert feats["pf_imbalance"] == pytest.approx(3.0), \
        f"pf_imbalance should be 14-11=3, got {feats.get('pf_imbalance')}"


# ===========================================================================
# 13. state_featurizer._compute_pace_state — flag OFF: no late_foul_active key
# ===========================================================================
def test_state_featurizer_flag_off(monkeypatch):
    _set_flag(monkeypatch, "0")
    from src.ingame.state_featurizer import _compute_pace_state
    kwargs = _pace_kwargs(game_rem=90, team_fouls={"home": 3, "away": 5},
                          score_deltas=[(0, 2)] * 30 + [(2, 0)] * 2)
    result = _compute_pace_state(**kwargs)
    assert "late_foul_active" not in result, \
        "flag OFF: late_foul_active should NOT be emitted"


# ===========================================================================
# 14. state_featurizer._compute_pace_state — flag ON, active scenario → 1
# ===========================================================================
def test_state_featurizer_flag_on_active(monkeypatch):
    _set_flag(monkeypatch, "1")
    from src.ingame.state_featurizer import _compute_pace_state
    # Home trailing (score_deltas: away scores more) + home in penalty (home_in_bonus=1)
    # home_in_bonus = 1 when team_fouls["home"] >= BONUS_FOULS(5)
    # So team_fouls = {"home": 6, "away": 2} → home_in_bonus=True → home in penalty
    # Home trailing: score_deltas give away more points
    score_deltas = [(0, 2)] * 30  # away scores more → margin < 0
    kwargs = _pace_kwargs(
        game_sec=2700,
        game_rem=90,   # 90 s <= 180
        team_fouls={"home": 6, "away": 2},  # home in penalty → home_in_bonus=True
        score_deltas=score_deltas,
    )
    result = _compute_pace_state(**kwargs)
    assert "late_foul_active" in result, "flag ON: late_foul_active should be emitted"
    # Home trailing (sum away_pts > home_pts from deltas), home_in_bonus=True, rem<=180
    assert result["late_foul_active"] == 1, \
        f"should be active (home trailing + home in penalty + low clock), got {result['late_foul_active']}"


# ===========================================================================
# 15. state_featurizer._compute_pace_state — flag ON, not active (no bonus) → 0
# ===========================================================================
def test_state_featurizer_flag_on_no_bonus(monkeypatch):
    _set_flag(monkeypatch, "1")
    from src.ingame.state_featurizer import _compute_pace_state
    # Neither team in bonus
    kwargs = _pace_kwargs(
        game_rem=90,
        team_fouls={"home": 2, "away": 2},
        score_deltas=[(0, 2)] * 30,
    )
    result = _compute_pace_state(**kwargs)
    assert result.get("late_foul_active") == 0, \
        f"no bonus → late_foul_active should be 0, got {result.get('late_foul_active')}"


# ===========================================================================
# 16. state_featurizer._compute_pace_state — flag ON, clock > 3 min → 0
# ===========================================================================
def test_state_featurizer_flag_on_clock_too_early(monkeypatch):
    _set_flag(monkeypatch, "1")
    from src.ingame.state_featurizer import _compute_pace_state
    kwargs = _pace_kwargs(
        game_rem=200,  # > 180 s
        team_fouls={"home": 6, "away": 2},
        score_deltas=[(0, 2)] * 30,
    )
    result = _compute_pace_state(**kwargs)
    assert result.get("late_foul_active") == 0, \
        f"clock > 3 min → late_foul_active should be 0, got {result.get('late_foul_active')}"


# ===========================================================================
# 17. sim inflation factor caps at LATE_FOUL_INFLATION_BASE at max deficit
# ===========================================================================
def test_late_foul_inflation_max_cap(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    # Margin well above LATE_FOUL_FULL_MARGIN (10); home trailing + home in penalty
    row = _poss_row(rem_sec=120.0, margin=-25.0, home_in_bonus=1, away_in_bonus=0)
    result = sim_mod._late_foul_poss_inflation(row)
    expected = 1.0 + sim_mod._LATE_FOUL_INFLATION_BASE
    assert abs(result - expected) < 1e-9, \
        f"max deficit should give inflation={expected}, got {result}"


# ===========================================================================
# 18. sim inflation factor ramps linearly with margin
# ===========================================================================
def test_late_foul_inflation_linear_ramp(monkeypatch):
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    full = sim_mod._LATE_FOUL_FULL_MARGIN
    # At half the full margin → should give half the base inflation; home trailing + in penalty
    row_half = _poss_row(rem_sec=90.0, margin=-(full / 2), home_in_bonus=1, away_in_bonus=0)
    result_half = sim_mod._late_foul_poss_inflation(row_half)
    expected_half = 1.0 + sim_mod._LATE_FOUL_INFLATION_BASE * 0.5
    assert abs(result_half - expected_half) < 1e-9, \
        f"half margin: expected {expected_half}, got {result_half}"


# ===========================================================================
# 19. inplay_winprob._compute_late_foul_sharpening — 0.0 for large margin (> 15)
# ===========================================================================
def test_sharpening_large_margin():
    import src.prediction.inplay_winprob as wp
    feats = {"score_margin": 20.0, "pf_imbalance": 5.0}
    result = wp._compute_late_foul_sharpening(feats)
    assert result == 0.0, f"margin > 15 should return 0.0, got {result}"


# ===========================================================================
# 20. RestOfGameSim.simulate — flag OFF produces same result as no-inflation baseline
# ===========================================================================
def test_simulate_flag_off_identical_to_baseline(monkeypatch):
    """With flag OFF, simulate() output must be byte-identical to a non-trailing game."""
    # Use a NON-late game row (high clock remaining) — flag ON/OFF both produce same result
    monkeypatch.setenv("CV_LATE_FOUL_STATE", "0")
    import importlib
    import src.sim.rest_of_game_sim as sim_mod
    importlib.reload(sim_mod)
    game_row = {
        "home_score": 55.0, "away_score": 51.0,
        "game_remaining_sec": 1440.0,  # 24 min remaining
        "total_poss_count": 60.0, "game_elapsed_sec": 1440.0,
        "home_poss": 30.0, "away_poss": 30.0,
        "score_margin": 4.0,
        "home_in_bonus": 0, "away_in_bonus": 0,
        "home_fgm": 20, "away_fgm": 18,
        "home_ftm": 10, "away_ftm": 8,
        "home_fg3a": 15, "home_fga": 40,
        "away_fg3a": 12, "away_fga": 38,
    }
    sim_off = sim_mod.RestOfGameSim(n_sims=500, seed=7)
    result_off = sim_off.simulate(game_row)

    monkeypatch.setenv("CV_LATE_FOUL_STATE", "1")
    importlib.reload(sim_mod)
    sim_on = sim_mod.RestOfGameSim(n_sims=500, seed=7)
    result_on = sim_on.simulate(game_row)

    # With >3 min remaining AND no bonus → no inflation → results should be identical
    assert abs(result_off.home_win_prob - result_on.home_win_prob) < 1e-9, \
        f"flag ON should not change result for non-late game: " \
        f"{result_off.home_win_prob} vs {result_on.home_win_prob}"
