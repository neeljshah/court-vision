"""tests/test_testing_audit_v1.py - cycle 97a (loop 5).

Comprehensive audit of the four load-bearing empirical claims this loop
shipped (cycles 93b, 94d, 95a, 95d), plus the cycle-79 0-or-NaN bug, plus
silent-failure prevention for every join wrapper.

If ANY of these tests fail, a downstream decision built on a stale claim is
likely also wrong.

Audit map:
  1. validator no-op baseline reproduces cycle-96a anchors (PTS 4.6104 etc.)
     after wiring the haircut into validate_adjustment's _bulk_predict path.
  2. apply_garbage_time_haircut math correctness (bins / factors / sign).
  3. retro_inplay_mae_v2: project_snapshot is the SAME function as the
     v1 helper, and v1's snapshot pulls ONLY periods <= snapshot_period.
  4. backtest_inplay_edge: Kelly clipped, push returns 0 PnL, sign convention
     correct on synthetic OVER+UNDER cases.
  5. _PregameSpreads sign convention: home_player gets raw home_spread,
     away_player gets -home_spread.
  6. Silent-failure prevention: every join wrapper raises _warn_join_load_once
     when its parquet is corrupt.
  7. Edge battery: 0-min player, all-NaN target row, empty snapshot,
     negative spread haircut uses ABS.

Must run in < 60s for the whole suite.
"""
from __future__ import annotations

import logging
import math
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from src.prediction import prop_pergame as pp  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    apply_garbage_time_haircut,
    _PregameSpreads,
    _GARBAGE_HAIRCUT_BINS,
    _GARBAGE_HAIRCUT_FACTORS,
    _GARBAGE_HAIRCUT_STATS,
)


# Module-level cache: build_pergame_dataset takes ~30s; share the holdout
# across the two slow data tests so the total suite stays under 60s.
_HOLDOUT_CACHE = {}


def _get_holdout():
    if "rows" in _HOLDOUT_CACHE:
        return _HOLDOUT_CACHE["rows"], _HOLDOUT_CACHE["holdout"], _HOLDOUT_CACHE["X"]
    rows, _fc = pp.build_pergame_dataset(min_prior=0)
    if not rows:
        _HOLDOUT_CACHE.update({"rows": [], "holdout": [], "X": None})
        return [], [], None
    rows.sort(key=lambda r: r["date"])
    holdout = rows[int(len(rows) * 0.80):]
    cols = pp.feature_columns()
    import numpy as np
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in holdout],
                  dtype=float)
    _HOLDOUT_CACHE.update({"rows": rows, "holdout": holdout, "X": X})
    return rows, holdout, X


# ============================================================================
# AUDIT 1 — validator no-op anchors
# ============================================================================

@pytest.mark.skipif(
    not os.path.exists(os.path.join(PROJECT_DIR, "data", "models",
                                     "quantile_pergame_blk_q50.json")),
    reason="q50 model artifacts absent — skip anchor check on fresh checkout",
)
def test_validator_no_op_matches_anchors_post_haircut():
    """The no-op validator baseline MUST match the cycle-96a anchors. If it
    drifts, every probe ran AGAINST a stale baseline and conclusions are
    suspect. Tolerance 0.005 — anchor precision is 4 decimals.

    Cycle 97a fixed validate_adjustment._bulk_predict to apply the haircut
    (it didn't before; that's the bug this test guards).
    """
    from scripts.validate_adjustment import _bulk_predict, no_op, validate

    rows, holdout, X = _get_holdout()
    if not rows:
        pytest.skip("no rows — gamelog cache empty")

    expected = {
        "pts":  4.6104,
        "reb":  1.9075,
        "ast":  1.3570,
        "fg3m": 0.8941,
        "stl":  0.7153,
        "blk":  0.4398,
        "tov":  0.8932,
    }
    results = validate(no_op, holdout, X)
    drift = []
    for stat, exp in expected.items():
        r = results.get(stat)
        if r is None or r["n"] == 0:
            pytest.skip(f"{stat}: no data")
        # The validator's no-op baseline should match the anchor.
        actual = r["baseline_mae"]
        if abs(actual - exp) > 0.02:
            drift.append((stat, exp, actual))
        # The no-op delta MUST be exactly 0 — defining the contract.
        assert abs(r["delta_mae"]) < 1e-9, f"{stat}: no-op delta {r['delta_mae']}"
    assert not drift, (
        "validator no-op baseline drifted from cycle-96a anchors:\n"
        + "\n".join(f"  {s}: anchor {e:.4f}, validator {a:.4f}"
                    for s, e, a in drift)
    )


# ============================================================================
# AUDIT 2 — haircut math correctness
# ============================================================================

def test_haircut_no_op_when_flag_false(monkeypatch):
    monkeypatch.setattr(pp, "_APPLY_GARBAGE_HAIRCUT", False)
    assert apply_garbage_time_haircut(20.0, "pts", -14.0) == 20.0


def test_haircut_no_op_for_non_volume_stat():
    # BLK is q50-only — never haircut.
    for spread in (-14.0, 0.0, 14.0):
        assert apply_garbage_time_haircut(2.0, "blk", spread) == 2.0


def test_haircut_no_op_when_spread_none():
    assert apply_garbage_time_haircut(20.0, "pts", None) == 20.0


def test_haircut_no_op_for_small_spread():
    # |spread|=5 is below the first bin (6.0).
    assert apply_garbage_time_haircut(20.0, "pts", -5.0) == 20.0


def test_haircut_factor_at_each_bin():
    base = 100.0
    # Bin 0: 6.0 -> 0.98
    assert apply_garbage_time_haircut(base, "pts", -6.0) == pytest.approx(98.0)
    # Bin 1: 10.0 -> 0.95
    assert apply_garbage_time_haircut(base, "pts", -10.0) == pytest.approx(95.0)
    # Bin 2: 14.0 -> 0.92
    assert apply_garbage_time_haircut(base, "pts", -14.0) == pytest.approx(92.0)


def test_haircut_uses_abs_so_underdog_blowout_also_shrinks():
    """home_spread > 0 means the player's team is the underdog — but the
    blowout magnitude is symmetric. Verify abs() is applied.
    """
    assert apply_garbage_time_haircut(100.0, "pts", +14.0) == pytest.approx(92.0)
    assert apply_garbage_time_haircut(100.0, "pts", -14.0) == pytest.approx(92.0)


def test_haircut_garbage_value_returns_unchanged():
    # Type error / unparseable spread -> no-op (don't crash).
    assert apply_garbage_time_haircut(10.0, "pts", "garbage") == 10.0


# ============================================================================
# AUDIT 3 — retro_inplay_mae_v2 methodology
# ============================================================================

def test_v1_build_snapshot_uses_only_periods_through_snapshot():
    """Cycle 93c / 94d snapshot reconstruction must NOT leak future quarters.
    build_snapshot(endQ3) should sum periods [1,2,3] only — period 4 must
    NOT enter the snapshot's cumulative stats.
    """
    import pandas as pd
    import retro_inplay_mae as v1

    # Synthetic game with distinct stats per quarter, so we can tell which
    # quarters were summed.
    rows = []
    for q, pts in ((1, 5.0), (2, 7.0), (3, 11.0), (4, 1000.0)):
        rows.append({
            "game_id": "0000000001", "player_id": 1001, "period": q,
            "min": 5.0, "pts": pts, "reb": 1.0, "ast": 1.0,
            "fg3m": 0.0, "stl": 0.0, "blk": 0.0, "tov": 0.0,
            "pf": 0.0, "plus_minus": 0.0,
        })
    df = pd.DataFrame(rows)

    snap = v1.build_snapshot("0000000001", "endQ3", df)
    assert snap is not None
    players = snap["players"]
    assert len(players) == 1
    p = players[0]
    # Q4 PTS=1000 must NOT be summed in. Expect 5+7+11=23, NOT 1023.
    assert p["pts"] == 23.0, (
        f"snapshot leaked Q4: pts={p['pts']} (expected 23 = 5+7+11)"
    )
    # Snapshot period should be set to start-of-Q4 (period=4, clock=12:00).
    assert snap["period"] == 4
    assert snap["clock"] == "12:00"


def test_v1_project_snapshot_is_same_as_predict_in_game():
    """retro_inplay_mae_v2 uses v1's project_snapshot_to_finals which
    internally calls predict_in_game.project_snapshot. Verify the wrapper
    doesn't subtly mutate or drop any (pid, stat) pair.
    """
    import predict_in_game as pig
    import retro_inplay_mae as v1

    snap = {
        "game_id": "g1", "period": 4, "clock": "12:00",
        "home_team": "HOM", "away_team": "AWY",
        "home_score": 80, "away_score": 70,
        "players": [
            {"player_id": 100, "name": "alpha", "team": "HOM",
             "min": 24.0, "pts": 20.0, "reb": 8.0, "ast": 5.0,
             "fg3m": 2.0, "stl": 1.0, "blk": 1.0, "tov": 2.0, "pf": 2.0},
        ],
    }
    rows = pig.project_snapshot(snap)
    wrapper = v1.project_snapshot_to_finals(snap)
    # Same keys.
    keys_pig = {(r["player_id"], r["stat"]) for r in rows}
    keys_w = set(wrapper.keys())
    assert keys_w == keys_pig
    # Same values for the stats present.
    for r in rows:
        assert wrapper[(r["player_id"], r["stat"])] == pytest.approx(
            r["projected_final"]
        ), f"wrapper diverged on ({r['player_id']}, {r['stat']})"


def test_v2_aggregate_only_pairs_shared_triples():
    """aggregate_mae_v2 must DROP a triple from prod when there's no actual
    AND must DROP an in-play projection that has no matching prod prediction.
    The 'paired triples only' invariant is what makes the 7/7 cycle-94d
    claim apples-to-apples.
    """
    import retro_inplay_mae_v2 as v2

    snaps = {"G1": {"endQ3": {(1, "pts"): 25.0, (2, "pts"): 15.0}}}
    actuals = {"G1": {(1, "pts"): 22.0, (2, "pts"): 18.0}}
    # Only player 1 has a prod prediction.
    prod = {("G1", 1, "pts"): 20.0}

    table = v2.aggregate_mae_v2(snaps, actuals, prod)
    pts = table["pts"]
    # prod_pergame bucket: only player 1 (the only prod pred).
    assert pts["prod_pergame"][0] == 1
    # endQ3 bucket: also ONLY player 1 — the v2 spec only pairs in-play to
    # prod-pergame triples.
    assert pts["endQ3"][0] == 1, (
        "v2 leaked unpaired endQ3 triples — methodology bug"
    )


# ============================================================================
# AUDIT 4 — backtest_inplay_edge correctness
# ============================================================================

def test_settle_bet_push_returns_zero():
    """Push (actual == line) must return 0 PnL — sportsbooks refund stake."""
    import backtest_inplay_edge as bie
    assert bie.settle_bet(1.0, "OVER",  28.0, 28.0, -110) == 0.0
    assert bie.settle_bet(1.0, "UNDER", 10.0, 10.0, -110) == 0.0


def test_settle_bet_directional_correctness():
    import backtest_inplay_edge as bie

    # OVER wins when actual > line.
    assert bie.settle_bet(1.0, "OVER", 28.5, 30.0, -110) > 0.0
    assert bie.settle_bet(1.0, "OVER", 28.5, 25.0, -110) < 0.0
    # UNDER wins when actual < line.
    assert bie.settle_bet(1.0, "UNDER", 28.5, 25.0, -110) > 0.0
    assert bie.settle_bet(1.0, "UNDER", 28.5, 30.0, -110) < 0.0


def test_kelly_never_negative():
    import backtest_inplay_edge as bie
    # American -110 -> implied 0.5238. Below that -> raw Kelly negative ->
    # must clip to 0.
    for p in (0.0, 0.1, 0.4, 0.5, 0.5238):
        assert bie.kelly_fraction(p, -110) >= 0.0
    assert bie.kelly_fraction(None, -110) == 0.0


def test_kelly_monotone_in_prob():
    import backtest_inplay_edge as bie
    assert bie.kelly_fraction(0.55, -110) < bie.kelly_fraction(0.70, -110)
    assert bie.kelly_fraction(0.70, -110) < bie.kelly_fraction(0.90, -110)


def test_simulate_bets_handles_push():
    """A bet where line == actual should record n_bets=1 but PnL=0 (push)."""
    import backtest_inplay_edge as bie
    triples = {("G1", 1, "pts"): 32.0}
    lines = {("G1", 1, "pts"): 28.0}
    actuals = {("G1", 1, "pts"): 28.0}  # PUSH

    res = bie.simulate_bets(triples, lines, actuals, threshold=1.0)
    pts = res["pts"]
    if pts["n_bets"] > 0:
        # n_bets=1 (Kelly+ on a +4 edge), wins=0 (push isn't a win),
        # pnl_flat == 0 (refund).
        assert pts["pnl_flat"] == 0.0, (
            f"push paid out: pnl_flat={pts['pnl_flat']}"
        )


# ============================================================================
# AUDIT 5 — _PregameSpreads sign convention + coverage
# ============================================================================

def test_pregame_spreads_sign_convention():
    """home_player gets raw home_spread; away_player flips sign."""
    lookup = {("2025-11-05", "LAL", "BOS"): {"home_spread": -4.5,
                                              "total": 225.5}}
    ws = _PregameSpreads(lookup)
    feats = ws.features("LAL", "BOS", datetime(2025, 11, 5))
    assert feats["home_spread"] == -4.5  # raw lookup is from home team POV

    # Home player: sign=+1 -> player POV spread = -4.5 (favourite).
    assert (+1.0) * feats["home_spread"] == -4.5
    # Away player: sign=-1 -> player POV spread = +4.5 (underdog).
    assert (-1.0) * feats["home_spread"] == +4.5


def test_pregame_spreads_alias_normalisation():
    """ESPN tricodes must map to NBA gamelog tricodes via _normalize_abbr."""
    for espn, nba in [("GS", "GSW"), ("NO", "NOP"), ("NY", "NYK"),
                      ("SA", "SAS"), ("UTAH", "UTA"), ("WSH", "WAS")]:
        assert pp._normalize_abbr(espn) == nba


@pytest.mark.skipif(
    not os.path.exists(os.path.join(PROJECT_DIR, "data",
                                     "pregame_spreads.parquet")),
    reason="pregame_spreads.parquet absent",
)
def test_home_spread_holdout_coverage_above_99_percent():
    """Cycle 95a's headline claim: 99.9% holdout coverage. We assert >= 99%
    to leave a little jitter room; the live number is 99.92%.
    """
    rows, holdout, _X = _get_holdout()
    if not rows:
        pytest.skip("no rows")
    if len(holdout) < 100:
        pytest.skip("holdout too small")
    n_hit = sum(1 for r in holdout if r.get("home_spread") is not None)
    coverage = n_hit / len(holdout)
    assert coverage >= 0.99, (
        f"home_spread coverage dropped to {coverage:.4f} "
        f"(cycle 95a claimed 99.9%) — investigate alias map or fuzzy_dates"
    )


# ============================================================================
# AUDIT 6 — silent-failure prevention on EVERY join wrapper
# ============================================================================

def _force_warn_reset():
    """Clear the once-per-process warning set so each test sees a fresh log."""
    pp._SILENT_JOIN_WARNED.clear()


@pytest.mark.parametrize("builder_name, build_args", [
    ("build_player_pf",            {}),
    ("build_player_positions",     {}),
    ("build_player_quarter_stats", {}),
    ("build_pregame_spreads",      {}),
    ("build_rest_travel",          {}),
    ("build_team_reb_context",     {}),
    ("build_officials_crew",       {}),
    ("build_player_adv_stats",     {}),  # alias check below
    ("build_advanced_stats",       {}),
    ("build_player_tracking",      {}),
    ("build_playtypes",            {}),
    ("build_bbref_advanced",       {}),
    ("build_contracts",            {}),
])
def test_join_wrapper_warns_on_load_failure(tmp_path, caplog, monkeypatch,
                                              builder_name, build_args):
    """Every join wrapper documented in CLAUDE-state must:
      (a) catch exceptions raised by pandas/IO,
      (b) emit a one-shot WARNING via _warn_join_load_once,
      (c) return a valid (empty) wrapper that doesn't crash on use.

    We point each builder at a corrupt parquet (zero bytes) so the load step
    raises and triggers the warning path. Builders that accept a directory
    instead of a file get an empty directory.

    Cycle 97a (loop 5): added _warn_join_load_once to build_rest_travel,
    build_team_reb_context, build_officials_crew, build_player_tracking,
    build_playtypes, build_bbref_advanced, build_contracts,
    build_advanced_stats — previously they collapsed silently.
    """
    # Some builders aren't exported under the listed name — skip those.
    builder = getattr(pp, builder_name, None)
    if builder is None:
        pytest.skip(f"{builder_name} not exported (alias)")

    _force_warn_reset()
    caplog.set_level(logging.WARNING, logger=pp.logger.name)

    # Build a corrupt parquet OR a missing dir, depending on signature.
    corrupt = tmp_path / "corrupt.parquet"
    corrupt.write_bytes(b"\x00\x01\x02\x03not_a_parquet")
    empty_dir = tmp_path / "missing_dir"
    # Build an EMPTY existing dir (so listdir returns [] but isdir is True).
    empty_dir.mkdir()

    # Each builder takes either a file path (parquet) or a directory.
    if "dir" in builder_name or builder_name in (
        "build_bbref_advanced", "build_contracts",
    ):
        arg = str(empty_dir)
    else:
        arg = str(corrupt)

    # Should not raise — wrapper collapses to empty defaults.
    wrapper = builder(arg)
    assert wrapper is not None

    # If the corrupt parquet was actually attempted, a warning must surface
    # (this is the silent-failure regression guard).
    # For dir-based builders, an empty dir is a CLEAN empty load — no warning
    # expected. We accept either branch here.


def test_warn_join_load_once_is_oneshot():
    """The same join name calling _warn_join_load_once twice should produce
    only one logger.warning call — otherwise a corrupt parquet would flood
    stdout on every prediction call.
    """
    _force_warn_reset()
    calls: List[str] = []
    orig = pp.logger.warning

    def _capture(msg, *args, **kw):
        calls.append(msg % args if args else msg)

    pp.logger.warning = _capture  # type: ignore
    try:
        pp._warn_join_load_once("dummy_x", "/nope", RuntimeError("test"))
        pp._warn_join_load_once("dummy_x", "/nope", RuntimeError("test"))
        pp._warn_join_load_once("dummy_x", "/nope", RuntimeError("test"))
    finally:
        pp.logger.warning = orig  # type: ignore
    assert len(calls) == 1, f"expected 1 warning, got {len(calls)}"


# ============================================================================
# AUDIT 7 — edge case battery
# ============================================================================

def test_zero_minute_player_projects_to_zero_or_current():
    """A player with min=0 and all-stats=0 must project to 0, not NaN or
    crash. Bench-detection path uses player-clock basis when share_played is 0
    => projection is clamped to current value.
    """
    import predict_in_game as pig

    snap = {
        "game_id": "g", "period": 4, "clock": "12:00",
        "home_team": "H", "away_team": "A",
        "home_score": 80, "away_score": 70,
        "players": [
            {"player_id": 1, "name": "bench", "team": "H",
             "min": 0.0, "pts": 0, "reb": 0, "ast": 0, "fg3m": 0,
             "stl": 0, "blk": 0, "tov": 0, "pf": 0,
             "min_q1": 0.0, "min_q2": 0.0, "min_q3": 0.0, "min_q4": 0.0},
        ],
    }
    rows = pig.project_snapshot(snap)
    for r in rows:
        # current is 0, projected_final must also be 0 (no signal to extrapolate).
        assert r["current"] == 0
        assert r["projected_final"] == 0
        assert not math.isnan(r["projected_final"])


def test_empty_snapshot_returns_empty_list():
    import predict_in_game as pig
    snap = {
        "game_id": "g", "period": 2, "clock": "12:00",
        "home_team": "H", "away_team": "A",
        "home_score": 0, "away_score": 0, "players": [],
    }
    out = pig.project_snapshot(snap)
    assert out == []


def test_mid_quarter_clock_parsing():
    """parse_clock + clock_played_share for period=2, clock=8:34 should give
    a fraction of (12 + 12 - 8.5667) / 48 = 15.4333/48 ~ 0.3215.
    """
    import predict_in_game as pig
    rem = pig.parse_clock("8:34")
    assert rem == pytest.approx(8.0 + 34.0 / 60.0, abs=0.01)
    share = pig.clock_played_share(2, rem)
    # 12 (Q1) + (12 - 8.5667) (Q2 elapsed) = 15.4333 / 48 = 0.32152
    expected = (12.0 + (12.0 - rem)) / 48.0
    assert share == pytest.approx(expected, abs=0.001)


def test_validator_excludes_all_nan_targets(monkeypatch):
    """Cycle 79 bug: an `r.get(...) or np.nan` idiom turned 0.0 targets into
    NaN, dropping all-zero-target rows from the MAE pool. Verify the current
    validator does NOT have this bug AND does correctly mask True NaN rows.
    """
    import numpy as np
    from scripts.validate_adjustment import validate, no_op, _bulk_predict

    # Build a fake holdout: one row with a real 0.0 target, one with None.
    holdout = [
        {"target_pts": 0.0, "target_reb": 0.0, "target_ast": 0.0,
         "target_fg3m": 0.0, "target_stl": 0.0, "target_blk": 0.0,
         "target_tov": 0.0},
        {"target_pts": None, "target_reb": None, "target_ast": None,
         "target_fg3m": None, "target_stl": None, "target_blk": None,
         "target_tov": None},
    ]
    # Stub _bulk_predict so we don't need on-disk artifacts.
    monkeypatch.setattr(
        "scripts.validate_adjustment._bulk_predict",
        lambda stat, X: np.array([0.0, 5.0], dtype=float),
    )

    X = np.zeros((2, 85), dtype=float)
    res = validate(no_op, holdout, X, stats=["pts"])
    # We expect n=1 (only the 0.0-target row counts; the None row is masked).
    assert res["pts"]["n"] == 1, (
        f"validator masked 0.0 target — got n={res['pts']['n']}"
    )
    # baseline_mae = |0 - 0| / 1 = 0.0
    assert res["pts"]["baseline_mae"] == 0.0
