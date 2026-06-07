"""Tests for the routed in-game player-line ensemble.

Covers (the task's explicit acceptance criteria):
  * BOUNDARIES route correctly: at a held-out bucket CENTER the blend weight is
    1.0 on that cell's measured arg-min head, so the routed value == that head's
    value there; the per-(stat,bucket) winner equals the held-out arg-min loaded
    from eval_curve_v2.json.
  * FINALS-AT-t0 are sane: at/near tip the projection is finite, >= current
    accumulation, and in a reasonable range (it leans on pregame-L5 / season form
    in the opening window, never NaN/zero-collapse).
  * NO DISCONTINUITY: sweeping game-elapsed second-by-second across EVERY bucket
    boundary, the routed projection for a HELD-CONSTANT state row moves by no more
    than a small tolerance per step (the blend is a continuous linear handoff).
  * DISABLED-IS-NOOP: with CV_INGAME_SBS off, the router returns the production
    snapshot projection (pure pass-through; v2 head never loaded).
  * Weights are a proper convex combination (sum to 1, in [0,1]).

The v2 head is injected as a tiny deterministic stub so the tests are fast and do
not require a trained model file (mirrors tests/test_unified_projector.py).
"""
from __future__ import annotations

import json

import pytest

from src.ingame import routed_ensemble as re_
from src.ingame.routed_ensemble import (
    ROUTING_TABLE,
    build_routing_table,
    route_weights,
    project_player_lines_routed,
    PLAYER_STATS,
    HEADS,
    EVAL_CURVE_V2,
    _BUCKET_CENTERS,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _state_row(elapsed_grid_sec=1080):
    """A leak-free v2-namespace player state row (mid-Q2 by default).

    Shape mirrors src.ingame.sbs_shadow.snapshot_to_v2_rows output: clock feats +
    p_<stat>_so_far + p_prior_<stat> + an attached _l5 dict.
    """
    l5 = {"pts": 20.0, "reb": 8.0, "ast": 5.0, "fg3m": 2.0,
          "stl": 1.0, "blk": 0.5, "tov": 2.0, "min": 32.0}
    row = {
        "player_id": 203999, "name": "Test Player", "team": "DEN",
        "game_remaining_min": (2880 - elapsed_grid_sec) / 60.0,
        "period": 2, "played_share": elapsed_grid_sec / 2880.0,
        "p_min_so_far": 16.0,
        "p_pts_so_far": 12.0, "p_reb_so_far": 5.0, "p_ast_so_far": 3.0,
        "p_fg3m_so_far": 1.0, "p_stl_so_far": 1.0, "p_blk_so_far": 0.0,
        "p_tov_so_far": 1.0, "p_pf_so_far": 2.0,
        "p_fga_so_far": 9.0, "p_fgm_so_far": 5.0, "p_on_court": 1.0,
        "score_margin": 4.0, "total_so_far": 100.0,
        "_grid_sec": elapsed_grid_sec,
        "_l5": l5,
    }
    for s, v in l5.items():
        row[f"p_prior_{s}"] = v
    return row


class _StubV2:
    """Deterministic v2 head: project current + a fixed bump per stat."""

    def project(self, row):
        out = {}
        for s in PLAYER_STATS:
            cur = float(row.get(f"p_{s}_so_far", 0.0) or 0.0)
            out[s] = cur + 3.0
        return out


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("CV_INGAME_SBS", "1")
    assert re_.is_enabled() is True


# --------------------------------------------------------------------------- #
# Routing table == held-out arg-min (the weights come from the eval, not hand-fit)
# --------------------------------------------------------------------------- #
def test_routing_table_matches_heldout_argmin():
    """Every (stat, bucket) winner is the arg-min head in the held-out curve."""
    with open(EVAL_CURVE_V2, "r", encoding="utf-8") as fh:
        curve = json.load(fh)
    from src.ingame.sbs_shadow import GRID_LABELS
    label_to_sec = {lbl: sec for sec, lbl in GRID_LABELS.items()}
    pc = curve["player_curve"]

    checked = 0
    for label, per_stat in pc.items():
        sec = label_to_sec[label]
        for stat in PLAYER_STATS:
            cell = per_stat[stat]
            cands = {}
            for head, keys in (
                ("pregame_l5", ("pregame_l5",)),
                ("v2", ("v2_core",)),
                ("snapshot", ("snapshot",)),
            ):
                for k in keys:
                    if cell.get(k) is not None:
                        cands[head] = float(cell[k])
                        break
            expected = min(cands, key=cands.get)
            assert ROUTING_TABLE[stat][sec] == expected, (
                f"{stat}@{label}: table says {ROUTING_TABLE[stat][sec]}, "
                f"held-out arg-min is {expected} ({cands})"
            )
            checked += 1
    assert checked == len(PLAYER_STATS) * len(label_to_sec)


def test_build_routing_table_is_pure_reload():
    """Rebuilding from the curve reproduces the module-level table."""
    assert build_routing_table() == ROUTING_TABLE


# --------------------------------------------------------------------------- #
# Boundaries route correctly: at a center, weight 1.0 on the measured winner.
# --------------------------------------------------------------------------- #
def test_center_weight_is_one_on_winner():
    for stat in PLAYER_STATS:
        for sec in _BUCKET_CENTERS:
            w = route_weights(stat, sec)
            winner = ROUTING_TABLE[stat][sec]
            assert w[winner] == pytest.approx(1.0), (
                f"{stat}@{sec}: expected weight 1.0 on {winner}, got {w}"
            )
            for h in HEADS:
                if h != winner:
                    assert w[h] == pytest.approx(0.0)


def test_weights_are_convex_combination():
    for stat in PLAYER_STATS:
        for sec in range(0, 2900, 37):
            w = route_weights(stat, sec)
            assert all(0.0 - 1e-9 <= v <= 1.0 + 1e-9 for v in w.values())
            assert sum(w.values()) == pytest.approx(1.0)


def test_routed_value_equals_winning_head_at_center(enabled):
    """At a bucket center the routed projection == the winning head's value."""
    stub = _StubV2()
    for sec in _BUCKET_CENTERS:
        row = _state_row(elapsed_grid_sec=sec)
        out = project_player_lines_routed(
            row, game_time=sec, projector=stub, return_detail=True,
        )
        for stat in PLAYER_STATS:
            winner = ROUTING_TABLE[stat][sec]
            comp = out["components"][stat]  # keyed by HEAD name
            wts = out["weights"][stat]
            # at a center the blend puts all weight on the winning head, so the
            # winner is the ONLY component and the routed value == its value.
            assert winner in comp, (
                f"{stat}@{sec}: winner {winner} absent from components {comp}"
            )
            assert wts.get(winner) == pytest.approx(1.0)
            assert out["projected"][stat] == pytest.approx(comp[winner], abs=1e-6)


# --------------------------------------------------------------------------- #
# Finals-at-t0 sanity.
# --------------------------------------------------------------------------- #
def test_finals_at_t0_are_sane(enabled):
    """Near tip the projection is finite, >= current, and ~ season-form scale."""
    stub = _StubV2()
    row = _state_row(elapsed_grid_sec=1080)
    # force the moment to ~tip
    out = project_player_lines_routed(row, game_time=0.0, projector=stub)
    for stat in PLAYER_STATS:
        cur = float(row[f"p_{stat}_so_far"])
        val = out[stat]
        assert val == val  # not NaN
        assert val >= cur - 1e-9            # floored at current
        assert 0.0 <= val < 200.0           # sane range, no blow-up
    # at tip the opening window leans fully on pregame-L5 (frac=0): pts ~ L5 pts
    assert out["pts"] == pytest.approx(max(row["p_pts_so_far"], row["_l5"]["pts"]),
                                       abs=1e-6)


def test_finals_floored_at_current(enabled):
    stub = _StubV2()
    for sec in (0, 360, 1080, 1800, 2520):
        row = _state_row(elapsed_grid_sec=max(sec, 1))
        out = project_player_lines_routed(row, game_time=sec, projector=stub)
        for stat in PLAYER_STATS:
            assert out[stat] >= float(row[f"p_{stat}_so_far"]) - 1e-9


# --------------------------------------------------------------------------- #
# No discontinuity across boundaries.
# --------------------------------------------------------------------------- #
def test_no_discontinuity_jump_across_boundaries(enabled):
    """Sweep game-elapsed 1s at a time over the WHOLE game with the state row
    held constant; the routed projection must move continuously (no jump bigger
    than a small tolerance between adjacent seconds).

    Because the blend weights move linearly and the component head VALUES are
    held constant (same state row), the per-second change is bounded by
    (max component spread) * (max per-second weight delta). With centers >= 360s
    apart the weight delta per second is <= 1/360, so the jump is tiny.
    """
    stub = _StubV2()
    row = _state_row(elapsed_grid_sec=1080)

    # Component value spread is bounded; tolerance scaled generously.
    TOL = 0.25  # points/rebs/etc per 1-second step — comfortably continuous
    prev = None
    for t in range(0, 2881):
        out = project_player_lines_routed(row, game_time=float(t), projector=stub)
        if prev is not None:
            for stat in PLAYER_STATS:
                jump = abs(out[stat] - prev[stat])
                assert jump <= TOL, (
                    f"discontinuity for {stat} at t={t}: jumped {jump:.4f} "
                    f"({prev[stat]:.4f} -> {out[stat]:.4f})"
                )
        prev = out


def test_weights_continuous_in_time():
    """The weight vector itself is Lipschitz-continuous in game-elapsed."""
    for stat in PLAYER_STATS:
        prev = None
        for t in range(0, 2881, 1):
            w = route_weights(stat, float(t))
            if prev is not None:
                delta = sum(abs(w[h] - prev[h]) for h in HEADS)
                # two heads change by <= 1/min_gap each -> total <= 2/360
                assert delta <= 2.0 / 360.0 + 1e-9
            prev = w


# --------------------------------------------------------------------------- #
# Disabled-is-noop pass-through.
# --------------------------------------------------------------------------- #
def test_disabled_is_production_snapshot(monkeypatch):
    monkeypatch.delenv("CV_INGAME_SBS", raising=False)
    assert re_.is_enabled() is False
    row = _state_row(elapsed_grid_sec=1080)
    out = project_player_lines_routed(row, game_time=1080.0)
    # equals the production snapshot head applied to the same row
    snap = re_._snapshot_values(row)
    for stat in PLAYER_STATS:
        assert out[stat] == pytest.approx(max(float(row[f"p_{stat}_so_far"]),
                                              snap[stat]), abs=1e-9)


def test_disabled_does_not_load_v2(monkeypatch):
    """The disabled path must never touch the v2 head loader."""
    monkeypatch.delenv("CV_INGAME_SBS", raising=False)

    def _boom(*a, **k):
        raise AssertionError("v2 head must NOT load when flag is OFF")

    monkeypatch.setattr(
        "src.ingame.continuous_projection.UnifiedPlayerLineProjector.load",
        staticmethod(_boom), raising=True,
    )
    out = project_player_lines_routed(_state_row(), game_time=1080.0)
    assert set(out.keys()) == set(PLAYER_STATS)


def test_game_time_derived_from_row_when_omitted(enabled):
    """game_time=None derives elapsed from the row's _grid_sec stamp."""
    stub = _StubV2()
    row = _state_row(elapsed_grid_sec=2520)
    out_auto = project_player_lines_routed(row, projector=stub)
    out_explicit = project_player_lines_routed(row, game_time=2520.0, projector=stub)
    for stat in PLAYER_STATS:
        assert out_auto[stat] == pytest.approx(out_explicit[stat], abs=1e-9)
