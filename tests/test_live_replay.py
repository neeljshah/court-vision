"""Fast regression tests for the live-replay harness and win-probability module.

All tests use small n_sims (<=100) so the suite stays fast (<10s).
Cache-dependent tests are skip-guarded (mirrors test_sim_engine.py pattern).

Honesty: these tests verify paper scaffolds; no real-money or serve-path
wiring is exercised here.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts", "team_system"))

_CACHE = os.path.join(_REPO, "data", "cache", "team_system")
_PBP_DIR = os.path.join(_CACHE, "pbp")
_BOX_DIR = os.path.join(_CACHE, "box")

_FINALS_GID = "0042500401"
_HAS_FINALS = (
    os.path.exists(os.path.join(_PBP_DIR, f"{_FINALS_GID}.json"))
    and os.path.exists(os.path.join(_BOX_DIR, f"{_FINALS_GID}.json"))
)
_HAS_ANY_CACHE = os.path.exists(_PBP_DIR) and os.path.exists(_BOX_DIR)

# ---------------------------------------------------------------------------
# Lazy imports (avoids import errors when repo dependencies are not present)
# ---------------------------------------------------------------------------
def _import_harness():
    from live_replay_harness import (
        build_snapshot_through_k,
        load_pbp,
        load_box,
        replay_game,
        reconcile,
    )
    return build_snapshot_through_k, load_pbp, load_box, replay_game, reconcile


def _import_winprob():
    from live_winprob import (
        live_win_prob,
        reconcile_winprob_with_score,
        reliability_check,
    )
    return live_win_prob, reconcile_winprob_with_score, reliability_check


# ---------------------------------------------------------------------------
# 1. Leak-free snapshot: mutating actions[k+1:] must not change snapshot
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _HAS_FINALS, reason="Finals PBP/box cache required")
def test_leak_free_snapshot():
    build_snapshot_through_k, load_pbp, load_box, _, _ = _import_harness()
    actions = load_pbp(_FINALS_GID)
    box_meta = load_box(_FINALS_GID)

    k = min(50, len(actions) - 2)
    snap_original = build_snapshot_through_k(actions, k, box_meta)

    # Mutate the tail (future actions)
    actions_mutated = copy.deepcopy(actions)
    for i in range(k + 1, len(actions_mutated)):
        actions_mutated[i]["scoreHome"] = "999"
        actions_mutated[i]["scoreAway"] = "999"

    snap_mutated = build_snapshot_through_k(actions_mutated, k, box_meta)

    # Snapshot should be byte-identical (team scores + player stats unchanged)
    assert snap_original["home_score"] == snap_mutated["home_score"], (
        "home_score changed after mutating future actions — leak detected"
    )
    assert snap_original["away_score"] == snap_mutated["away_score"], (
        "away_score changed after mutating future actions — leak detected"
    )
    # Player stats through k should match
    orig_stats = {p["player_id"]: p for p in snap_original["players"]}
    mut_stats = {p["player_id"]: p for p in snap_mutated["players"]}
    for pid in orig_stats:
        if pid in mut_stats:
            for stat in ("pts", "reb", "tov"):
                assert orig_stats[pid][stat] == mut_stats[pid][stat], (
                    f"Player {pid} stat {stat} changed after mutating future — leak"
                )


# ---------------------------------------------------------------------------
# 2. Clock parse: ISO format and MM:SS format
# ---------------------------------------------------------------------------
def test_clock_parse():
    from src.sim.live_game_simulator import _clock_to_sec
    assert _clock_to_sec("PT10M53.00S") == pytest.approx(653.0)
    assert _clock_to_sec("5:00") == pytest.approx(300.0)
    assert _clock_to_sec("0:00") == pytest.approx(0.0)
    assert _clock_to_sec("PT00M00.00S") == pytest.approx(0.0)
    assert _clock_to_sec("PT12M00.00S") == pytest.approx(720.0)
    assert _clock_to_sec(None) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 3. Final reconstructed scores match official box scores
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _HAS_FINALS, reason="Finals PBP/box cache required")
def test_reconstruct_final_matches_box():
    build_snapshot_through_k, load_pbp, load_box, _, _ = _import_harness()
    actions = load_pbp(_FINALS_GID)
    box_meta = load_box(_FINALS_GID)

    k = len(actions) - 1
    snap = build_snapshot_through_k(actions, k, box_meta)

    # Team scores come directly from scoreHome/Away PBP strings — must be exact
    assert snap["home_score"] == box_meta["home_score"], (
        f"Home score mismatch: snap={snap['home_score']} box={box_meta['home_score']}"
    )
    assert snap["away_score"] == box_meta["away_score"], (
        f"Away score mismatch: snap={snap['away_score']} box={box_meta['away_score']}"
    )

    # Player PTS MAE should be small (PBP accumulation vs official box)
    snap_map = {int(p["player_id"]): p for p in snap["players"]}
    box_map = box_meta["players"]
    errs = []
    for pid in set(snap_map) & set(box_map):
        errs.append(abs(float(snap_map[pid]["pts"]) - float(box_map[pid]["pts"])))
    if errs:
        mae = sum(errs) / len(errs)
        # PBP pts should reconstruct well; loose tolerance to handle edge cases
        assert mae < 5.0, f"Player PTS MAE too high: {mae:.2f} (AST is acknowledged lossier)"


# ---------------------------------------------------------------------------
# 4. Win prob monotone with time: same margin, less time = higher confidence
# ---------------------------------------------------------------------------
def test_winprob_monotone_time():
    live_win_prob, _, _ = _import_winprob()
    margin = 6.0
    p_early = live_win_prob(margin, 1200.0)  # 20 min left
    p_mid   = live_win_prob(margin, 360.0)   # 6 min left
    p_late  = live_win_prob(margin, 30.0)    # 30 sec left
    assert p_early < p_mid, "Same +margin: win% should rise as time decreases"
    assert p_mid < p_late, "Same +margin: win% should rise further close to end"
    # All must be > 0.5 for a positive margin
    assert p_early > 0.5
    assert p_late > 0.5


# ---------------------------------------------------------------------------
# 5. Win prob bounds and tie invariant
# ---------------------------------------------------------------------------
def test_winprob_bounds_and_tie():
    live_win_prob, _, _ = _import_winprob()
    for margin in (-30.0, 0.0, 30.0):
        for sec in (0.1, 60.0, 600.0, 2880.0):
            p = live_win_prob(margin, sec)
            assert 0.0 <= p <= 1.0, f"Out of [0,1]: margin={margin} sec={sec} p={p}"

    # Tie -> exactly 0.5
    p_tie = live_win_prob(0.0, 300.0)
    assert abs(p_tie - 0.5) < 1e-9, f"Tie should be 0.5 but got {p_tie}"

    # Huge late lead -> very high
    p_huge = live_win_prob(30.0, 5.0)
    assert p_huge > 0.99, f"Huge late lead should be >0.99 but got {p_huge}"


# ---------------------------------------------------------------------------
# 6. Coherence: reconcile_winprob_with_score sign consistency
# ---------------------------------------------------------------------------
def test_coherence():
    _, reconcile_wp, _ = _import_winprob()
    # Home up: proj_home > proj_away -> win_prob > 0.5, coherent
    result = reconcile_wp(100, 90, 108.0, 100.0, 300.0)
    assert result["coherent"] is True
    assert result["win_prob"] > 0.5

    # Away up: proj_away > proj_home -> win_prob < 0.5, coherent
    result_away = reconcile_wp(90, 100, 100.0, 108.0, 300.0)
    assert result_away["coherent"] is True
    assert result_away["win_prob"] < 0.5

    # Tie: proj_margin=0 -> win_prob~0.5
    result_tie = reconcile_wp(95, 95, 105.0, 105.0, 120.0)
    assert result_tie["coherent"] is True
    assert abs(result_tie["win_prob"] - 0.5) < 0.01


# ---------------------------------------------------------------------------
# 7. Reprice latency recorded and positive
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _HAS_FINALS, reason="Finals PBP/box cache required")
def test_reprice_latency_recorded():
    _, _, _, replay_game, _ = _import_harness()
    # Use small n_sims and only the first ~20 steps (period mode = fast)
    steps = replay_game(
        _FINALS_GID,
        backend="rog",
        n_sims=50,
        step="period",
        cache=_CACHE,
    )
    assert len(steps) > 0, "No replay steps generated"
    for s in steps:
        assert s.reprice_ms > 0.0, f"reprice_ms should be positive, got {s.reprice_ms}"
        import math
        assert math.isfinite(s.reprice_ms), f"reprice_ms should be finite, got {s.reprice_ms}"


# ---------------------------------------------------------------------------
# 8. Win-prob reliability check runs without error (small-n honest)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _HAS_FINALS, reason="Finals PBP/box cache required")
def test_reliability_check_runs():
    _, _, reliability_check = _import_winprob()
    result = reliability_check([_FINALS_GID], cache=_CACHE)
    assert "n_games" in result
    assert "brier" in result
    assert "caveat" in result
    assert result["n_games"] >= 1
    assert "n_games=" in result["caveat"], "Caveat must report n_games"
    if result["brier"] is not None:
        assert 0.0 <= result["brier"] <= 1.0, "Brier should be in [0,1]"
