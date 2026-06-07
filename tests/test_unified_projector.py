"""Tests for the unified in-game projector (assembles the two validated heads).

Covers:
  * DISABLED-IS-NOOP-IDENTITY: with CV_INGAME_SBS unset/off, project_unified
    returns EXACTLY scripts.predict_in_game.project_snapshot(snapshot) — proving
    the production serving default is byte-identical (pure pass-through).
  * ENABLED returns the validated heads: a unified dict carrying SBS v2 player
    lines + possession-sim team score/win-prob + the production baseline.
  * The production baseline carried in the enabled payload is unchanged.

No trained v2 model file is needed: we inject a tiny stub player projector so the
test is fast/deterministic. The possession sim is pure NumPy and runs as-is with
a small n_sims. The real heads are exercised by their own tests
(test_sbs_v2_head / test_rest_of_game_sim) + the eval harnesses.
"""
from __future__ import annotations

import pytest

from src.ingame import unified_projector as up
from src.ingame.unified_projector import project_unified
from scripts.predict_in_game import project_snapshot


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _snapshot():
    """A canonical mid-Q2 live snapshot (within the validated v2 window)."""
    return {
        "game_id": "0022400123",
        "period": 2,
        "clock": "06:00",   # ~18 min elapsed -> midQ2 grid bucket
        "home_team": "DEN",
        "away_team": "LAL",
        "home_score": 52,
        "away_score": 48,
        "players": [
            {"player_id": 203999, "name": "Nikola Jokic", "team": "DEN",
             "min": 16.0, "pts": 14, "reb": 6, "ast": 5, "fg3m": 1,
             "stl": 1, "blk": 0, "tov": 2, "pf": 2},
            {"player_id": 2544, "name": "LeBron James", "team": "LAL",
             "min": 15.0, "pts": 12, "reb": 4, "ast": 6, "fg3m": 2,
             "stl": 0, "blk": 1, "tov": 1, "pf": 1},
        ],
    }


class _StubV2:
    """Minimal stand-in for UnifiedPlayerLineProjector.project()."""

    def project(self, row):
        out = {}
        for s in up.PLAYER_STATS:
            cur = float(row.get(f"p_{s}_so_far", 0.0) or 0.0)
            out[s] = cur + 2.0   # deterministic bump, floored at current by design
        return out


# --------------------------------------------------------------------------- #
# DISABLED — pure pass-through identity
# --------------------------------------------------------------------------- #
def test_disabled_is_noop_identity(monkeypatch):
    """Flag OFF => project_unified == production project_snapshot, byte-identical."""
    monkeypatch.delenv("CV_INGAME_SBS", raising=False)
    assert up.is_enabled() is False

    snap = _snapshot()
    expected = project_snapshot(dict(snap))   # production default
    got = project_unified(snap)

    # Identical type (a list of production rows), identical content.
    assert isinstance(got, list)
    assert got == expected


def test_disabled_for_each_falsy_spelling(monkeypatch):
    for val in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("CV_INGAME_SBS", val)
        assert up.is_enabled() is False
        snap = _snapshot()
        assert project_unified(snap) == project_snapshot(dict(snap))


def test_disabled_does_not_load_model(monkeypatch):
    """The disabled path must not even touch the v2 loader (no model file needed)."""
    monkeypatch.delenv("CV_INGAME_SBS", raising=False)

    def _boom(*a, **k):
        raise AssertionError("v2 head must NOT load when flag is OFF")

    # If the disabled path tried to load the head, this would raise.
    monkeypatch.setattr(
        "src.ingame.continuous_projection.UnifiedPlayerLineProjector.load",
        staticmethod(_boom), raising=True,
    )
    out = project_unified(_snapshot())
    assert isinstance(out, list)  # production rows, no model load


# --------------------------------------------------------------------------- #
# ENABLED — returns the two validated heads
# --------------------------------------------------------------------------- #
def test_enabled_returns_validated_heads(monkeypatch):
    monkeypatch.setenv("CV_INGAME_SBS", "1")
    assert up.is_enabled() is True

    out = project_unified(
        _snapshot(),
        device="cpu",
        n_sims=200,
        seed=0,
        player_projector=_StubV2(),   # skip disk load
    )

    assert isinstance(out, dict)
    assert out["enabled"] is True
    assert out["schema_version"] == "unified-1"

    # --- head 1: ROUTED player-line ensemble ---
    # The snapshot is midQ2 (period 2, 06:00 -> 18min elapsed, grid 1080s); at that
    # bucket the held-out routing table weights the v2 sub-head 1.0 for every stat,
    # so the injected stub v2 (+2 bump) flows through the route unchanged. This
    # both relabels the head as "routed" AND proves the route picks v2 mid-game.
    pl = out["player_lines"]
    assert isinstance(pl, list) and len(pl) > 0
    stats_seen = {r["stat"] for r in pl}
    assert stats_seen == set(up.PLAYER_STATS)
    for r in pl:
        assert r["head"] == "routed"
        assert r["route_head"] == "v2"          # midQ2 route is v2-dominant
        assert r["projected_final"] >= r["current"]   # floored at current
    # at midQ2 the route is pure v2, so the stub's +2 bump passes through
    jokic_pts = [r for r in pl
                 if r["player_id"] == 203999 and r["stat"] == "pts"][0]
    assert jokic_pts["current"] == 14.0
    assert jokic_pts["projected_final"] == 16.0

    # --- head 2: SCORE ENSEMBLE team score + win prob ---
    team = out["team"]
    assert team["head"] == "score_ensemble"
    # no ridge point injected -> the point falls back to the sim mean
    assert team["point_source"] == "sim_fallback"
    assert team["winprob_source"] == "possession_sim"
    assert 0.0 <= team["home_win_prob"] <= 1.0
    assert team["home_final_mean"] >= 52.0   # >= current home score
    assert team["away_final_mean"] >= 48.0
    assert team["n_sims"] == 200

    # --- production baseline carried + unchanged ---
    assert out["production_baseline"] == project_snapshot(dict(_snapshot()))


def test_enabled_win_prob_responds_to_lead(monkeypatch):
    monkeypatch.setenv("CV_INGAME_SBS", "1")
    base = _snapshot()
    big = dict(base)
    big["home_score"] = 80
    big["away_score"] = 48
    out_low = project_unified(base, device="cpu", n_sims=400,
                              player_projector=_StubV2())
    out_big = project_unified(big, device="cpu", n_sims=400,
                              player_projector=_StubV2())
    assert out_big["team"]["home_win_prob"] >= out_low["team"]["home_win_prob"]


def test_enabled_does_not_mutate_production_baseline(monkeypatch):
    """The unified heads must never overwrite the carried production output."""
    monkeypatch.setenv("CV_INGAME_SBS", "1")
    snap = _snapshot()
    out = project_unified(snap, device="cpu", n_sims=100,
                          player_projector=_StubV2())
    # baseline equals a fresh production call (heads did not touch it)
    assert out["production_baseline"] == project_snapshot(dict(snap))
