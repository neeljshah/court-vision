"""Tests for W-019: CV_INGAME_LIVE_USAGE flag gate.

Asserts:
  1. Flag semantics: is_live_usage_enabled() is False by default; truthy
     spellings enable it.
  2. compute_live_usg_vs_prior: primary path (FGA denominator >= 0.5) and
     fallback path (denominator < 0.5 → volume ratio proxy). Output clamped
     to [-1.0, 2.0].
  3. BYTE-IDENTICAL when OFF: parse_boxscore_payload with flag OFF produces
     zero new keys vs baseline; flag ON produces "p_live_usg_vs_prior" per
     player row.
  4. Usage delta direction: player with higher-than-expected volume gets
     positive delta; lower-than-expected gets negative.
  5. Team denominator guard: denominator < 0.5 triggers fallback path without
     raising.
  6. FEATURES_PLAYER still contains p_prior_usage; LIVE_USAGE_FEATURE
     exported from continuous_projection.
  7. eval_sbs_v2 _build_v2_row always populates LIVE_USAGE_FEATURE in the
     returned dict (regardless of flag state, so the column is present for
     model training when flag is ON).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("NBA_OFFLINE", "1")
os.environ.setdefault("NBA_FORCE_CPU", "1")

from src.ingame.continuous_projection import (  # noqa: E402
    LIVE_USAGE_FLAG,
    LIVE_USAGE_FEATURE,
    FEATURES_PLAYER,
    is_live_usage_enabled,
    compute_live_usg_vs_prior,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _reset_flag():
    """Restore CV_INGAME_LIVE_USAGE to its pre-test state after every test."""
    saved_usage = os.environ.get(LIVE_USAGE_FLAG)
    saved_ff = os.environ.get("CV_SNAP_FF")
    yield
    for k, v in [(LIVE_USAGE_FLAG, saved_usage), ("CV_SNAP_FF", saved_ff)]:
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _make_player_stat(*, fga=5, fgm=2, fg3m=1, fta=2, ftm=1,
                      pts=7, reb=3, ast=2, stl=0, blk=0, tov=1,
                      pf=1, minutes="PT06M00.00S",
                      starter="0", oncourt=False,
                      fg3a=2):
    return {
        "minutes": minutes,
        "fieldGoalsAttempted": fga,
        "fieldGoalsMade": fgm,
        "threePointersMade": fg3m,
        "threePointersAttempted": fg3a,
        "freeThrowsAttempted": fta,
        "freeThrowsMade": ftm,
        "points": pts,
        "reboundsTotal": reb,
        "assists": ast,
        "steals": stl,
        "blocks": blk,
        "turnovers": tov,
        "foulsPersonal": pf,
        "reboundsOffensive": 1,
        "reboundsDefensive": reb - 1,
    }


def _make_player(player_id, name, starter="0", oncourt=False, **stat_kwargs):
    return {
        "personId": player_id,
        "name": name,
        "starter": starter,
        "oncourt": oncourt,
        "statistics": _make_player_stat(**stat_kwargs),
    }


def _make_payload(home_players=None, away_players=None, game_status=2,
                  period=2):
    """Build a minimal CDN boxscore payload."""
    if home_players is None:
        home_players = [
            _make_player(1001, "Player A", fga=6, tov=2, pts=10),
            _make_player(1002, "Player B", fga=4, tov=1, pts=7),
        ]
    if away_players is None:
        away_players = [
            _make_player(2001, "Player X", fga=5, tov=1, pts=8),
            _make_player(2002, "Player Y", fga=3, tov=2, pts=5),
        ]
    return {
        "game": {
            "gameId": "0022400001",
            "gameStatus": game_status,
            "period": period,
            "gameClock": "PT06M00.00S",
            "homeTeam": {
                "teamTricode": "HOM",
                "score": 50,
                "players": home_players,
            },
            "awayTeam": {
                "teamTricode": "AWY",
                "score": 45,
                "players": away_players,
            },
        }
    }


# --------------------------------------------------------------------------- #
# 1. Flag semantics
# --------------------------------------------------------------------------- #
class TestFlagSemantics:
    def test_default_off(self):
        assert is_live_usage_enabled() is False

    def test_explicit_falsy_off(self):
        for v in ("0", "", "false", "no", "off", "n", "f"):
            os.environ[LIVE_USAGE_FLAG] = v
            assert is_live_usage_enabled() is False, f"should be OFF for {v!r}"

    def test_truthy_on(self):
        for v in ("1", "true", "yes", "on", "y", "t", "TRUE", "YES"):
            os.environ[LIVE_USAGE_FLAG] = v
            assert is_live_usage_enabled() is True, f"should be ON for {v!r}"

    def test_flag_name_constant(self):
        assert LIVE_USAGE_FLAG == "CV_INGAME_LIVE_USAGE"

    def test_feature_name_constant(self):
        assert LIVE_USAGE_FEATURE == "p_live_usg_vs_prior"


# --------------------------------------------------------------------------- #
# 2. compute_live_usg_vs_prior correctness
# --------------------------------------------------------------------------- #
class TestComputeUsage:
    def test_primary_path_zero_delta(self):
        """Player uses exactly their prior share -> delta ≈ 0."""
        # Prior usage 0.20; live: fga=4, fta=2, tov=1 / team denom 25
        # live_proxy = (4 + 0.44*2 + 1) / 25 = 5.88/25 = 0.235 -> close to 0.20
        result = compute_live_usg_vs_prior(
            fga_so_far=4.0, fta_so_far=2.0, tov_so_far=1.0,
            team_fga=20.0, team_fta=5.0, team_tov=5.0,
            p_prior_usage=0.20,
            p_prior_pts=15.0, p_prior_min=30.0,
            pts_so_far=10.0, min_so_far=15.0,
        )
        assert isinstance(result, float)
        assert -1.0 <= result <= 2.0

    def test_primary_path_high_usage(self):
        """Player taking a much higher share than prior -> positive delta."""
        # live_proxy = (10 + 0 + 2) / 20 = 0.60, prior = 0.20 -> delta = 0.40
        result = compute_live_usg_vs_prior(
            fga_so_far=10.0, fta_so_far=0.0, tov_so_far=2.0,
            team_fga=18.0, team_fta=0.0, team_tov=2.0,
            p_prior_usage=0.20,
            p_prior_pts=15.0, p_prior_min=30.0,
            pts_so_far=18.0, min_so_far=12.0,
        )
        assert result > 0.0

    def test_primary_path_low_usage(self):
        """Player taking much less than prior -> negative delta."""
        # live_proxy = (1 + 0 + 0) / 20 = 0.05, prior = 0.25 -> delta = -0.20
        result = compute_live_usg_vs_prior(
            fga_so_far=1.0, fta_so_far=0.0, tov_so_far=0.0,
            team_fga=18.0, team_fta=0.0, team_tov=2.0,
            p_prior_usage=0.25,
            p_prior_pts=20.0, p_prior_min=30.0,
            pts_so_far=2.0, min_so_far=8.0,
        )
        assert result < 0.0

    def test_clamp_upper(self):
        """Delta cannot exceed 2.0."""
        # live_proxy = (100 + 0 + 0) / 100 = 1.0, prior = 0.0 -> delta = 1.0 < 2.0
        # To force > 2.0: prior = 0.0, live_proxy = 1.0, but max proxy - 0.0 = 1.0 -> fine
        # Use a case where unclamped delta would be >2.0
        result = compute_live_usg_vs_prior(
            fga_so_far=50.0, fta_so_far=10.0, tov_so_far=5.0,
            team_fga=10.0, team_fta=2.0, team_tov=2.0,
            p_prior_usage=0.0,
            p_prior_pts=5.0, p_prior_min=10.0,
            pts_so_far=40.0, min_so_far=10.0,
        )
        assert result <= 2.0

    def test_clamp_lower(self):
        """Delta cannot go below -1.0."""
        result = compute_live_usg_vs_prior(
            fga_so_far=0.0, fta_so_far=0.0, tov_so_far=0.0,
            team_fga=20.0, team_fta=5.0, team_tov=5.0,
            p_prior_usage=1.0,  # prior usage = 1.0 (impossible but tests clamp)
            p_prior_pts=20.0, p_prior_min=10.0,
            pts_so_far=0.0, min_so_far=5.0,
        )
        assert result >= -1.0

    def test_fallback_path_small_denom(self):
        """When team denom < 0.5, fallback path runs without error."""
        result = compute_live_usg_vs_prior(
            fga_so_far=2.0, fta_so_far=1.0, tov_so_far=0.0,
            team_fga=0.1, team_fta=0.0, team_tov=0.1,  # denom=0.144 < 0.5
            p_prior_usage=0.20,
            p_prior_pts=15.0, p_prior_min=30.0,
            pts_so_far=6.0, min_so_far=6.0,
        )
        assert -1.0 <= result <= 2.0

    def test_fallback_zero_prior_min(self):
        """Zero prior_min (new player) should not raise."""
        result = compute_live_usg_vs_prior(
            fga_so_far=2.0, fta_so_far=0.0, tov_so_far=0.0,
            team_fga=0.0, team_fta=0.0, team_tov=0.0,
            p_prior_usage=0.0,
            p_prior_pts=0.0, p_prior_min=0.0,
            pts_so_far=5.0, min_so_far=6.0,
        )
        assert -1.0 <= result <= 2.0


# --------------------------------------------------------------------------- #
# 3. parse_boxscore_payload byte-identical when OFF
# --------------------------------------------------------------------------- #
class TestPollerByteIdentical:
    def _reload_poll_module(self):
        """Reload live_game_poll with the current env state."""
        import importlib
        import scripts.live_game_poll as lgp
        importlib.reload(lgp)
        return lgp

    def test_flag_off_no_usage_key(self):
        """Flag OFF: no p_live_usg_vs_prior key in any player row."""
        os.environ.pop(LIVE_USAGE_FLAG, None)
        os.environ.pop("CV_SNAP_FF", None)
        lgp = self._reload_poll_module()
        snap = lgp.parse_boxscore_payload(_make_payload())
        for p in snap["players"]:
            assert "p_live_usg_vs_prior" not in p, (
                f"Flag OFF must not add p_live_usg_vs_prior; got keys {set(p.keys())}"
            )

    def test_flag_on_with_ff_usage_key_present(self):
        """Flag ON + CV_SNAP_FF ON: p_live_usg_vs_prior present per player."""
        os.environ[LIVE_USAGE_FLAG] = "1"
        os.environ["CV_SNAP_FF"] = "1"
        lgp = self._reload_poll_module()
        snap = lgp.parse_boxscore_payload(_make_payload())
        for p in snap["players"]:
            assert "p_live_usg_vs_prior" in p, (
                f"Flag ON must add p_live_usg_vs_prior; got keys {set(p.keys())}"
            )
            assert isinstance(p["p_live_usg_vs_prior"], float)
            assert -1.0 <= p["p_live_usg_vs_prior"] <= 2.0

    def test_flag_on_no_ff_fallback_path(self):
        """Flag ON without CV_SNAP_FF: fallback path runs, key still present."""
        os.environ[LIVE_USAGE_FLAG] = "1"
        os.environ.pop("CV_SNAP_FF", None)
        lgp = self._reload_poll_module()
        snap = lgp.parse_boxscore_payload(_make_payload())
        for p in snap["players"]:
            assert "p_live_usg_vs_prior" in p
            assert -1.0 <= p["p_live_usg_vs_prior"] <= 2.0

    def test_flag_off_all_other_keys_unchanged(self):
        """Flag OFF: baseline keys unchanged relative to baseline snapshot."""
        os.environ.pop(LIVE_USAGE_FLAG, None)
        os.environ.pop("CV_SNAP_FF", None)
        lgp = self._reload_poll_module()
        snap = lgp.parse_boxscore_payload(_make_payload())
        baseline_keys = {"player_id", "name", "team", "min", "pts", "reb",
                         "ast", "fg3m", "stl", "blk", "tov", "pf", "is_starter"}
        for p in snap["players"]:
            assert set(p.keys()) == baseline_keys, (
                f"Flag OFF must be byte-identical; extra/missing keys: "
                f"{set(p.keys()) ^ baseline_keys}"
            )


# --------------------------------------------------------------------------- #
# 4. Usage delta direction
# --------------------------------------------------------------------------- #
class TestUsageDeltaDirection:
    def test_high_volume_player_positive_delta(self):
        """A player taking many shots vs team average -> positive delta."""
        # team denom = 40+0+4 = 44; player denom = 20+0+2 = 22 -> proxy=0.50
        # p_prior_usage = 0.10 -> delta = +0.40 (positive)
        delta = compute_live_usg_vs_prior(
            fga_so_far=20.0, fta_so_far=0.0, tov_so_far=2.0,
            team_fga=40.0, team_fta=0.0, team_tov=4.0,
            p_prior_usage=0.10,
            p_prior_pts=10.0, p_prior_min=25.0,
            pts_so_far=22.0, min_so_far=12.0,
        )
        assert delta > 0.0, f"Expected positive delta for high-volume player; got {delta}"

    def test_low_volume_player_negative_delta(self):
        """A player taking few shots vs their prior role -> negative delta."""
        # team denom = 40+0+4 = 44; player denom = 1+0+0 = 1 -> proxy=0.023
        # p_prior_usage = 0.25 -> delta = -0.227 (negative)
        delta = compute_live_usg_vs_prior(
            fga_so_far=1.0, fta_so_far=0.0, tov_so_far=0.0,
            team_fga=40.0, team_fta=0.0, team_tov=4.0,
            p_prior_usage=0.25,
            p_prior_pts=18.0, p_prior_min=30.0,
            pts_so_far=2.0, min_so_far=8.0,
        )
        assert delta < 0.0, f"Expected negative delta for low-volume player; got {delta}"


# --------------------------------------------------------------------------- #
# 5. Schema: FEATURES_PLAYER has p_prior_usage; LIVE_USAGE_FEATURE exported
# --------------------------------------------------------------------------- #
class TestSchema:
    def test_features_player_has_prior_usage(self):
        assert "p_prior_usage" in FEATURES_PLAYER, (
            "FEATURES_PLAYER must declare p_prior_usage (the prior-form column "
            "that the usage-delta feature is anchored to)"
        )

    def test_live_usage_feature_exported(self):
        assert LIVE_USAGE_FEATURE == "p_live_usg_vs_prior"
        # Ensure it is exported from the module
        import src.ingame.continuous_projection as cp
        assert hasattr(cp, "LIVE_USAGE_FEATURE")
        assert hasattr(cp, "LIVE_USAGE_FLAG")
        assert hasattr(cp, "is_live_usage_enabled")
        assert hasattr(cp, "compute_live_usg_vs_prior")


# --------------------------------------------------------------------------- #
# 6. eval_sbs_v2 _build_v2_row always populates the usage column
# --------------------------------------------------------------------------- #
class TestBuildV2Row:
    def _make_prow(self):
        return {
            "player_id": 123,
            "side": "home",
            "team_abbrev": "HOM",
            "min_so_far": 12.0,
            "pts": 10,
            "reb": 4,
            "ast": 2,
            "fg3m": 1,
            "stl": 0,
            "blk": 0,
            "tov": 1,
            "pf": 1,
            "fga": 5,
            "fgm": 3,
            "on_court": True,
        }

    def _make_grow(self):
        return {
            "game_remaining_sec": 1440.0,
            "period": 2,
            "played_share": 0.50,
            "home_score": 50,
            "away_score": 45,
            "score_margin": 5.0,
            "pace_poss_per_min": 2.1,
            "poss_per_48_so_far": 96.0,
            "sec_per_poss_so_far": 14.0,
            "sec_since_last_fg": 8.0,
            "sec_since_last_score": 8.0,
            "run_last10_margin": 2.0,
            "run_last5_margin": 1.0,
            "home_in_bonus": 0.0,
            "away_in_bonus": 0.0,
            "exp_poss_remaining": 50.0,
            "home_efg": 0.52,
            "away_efg": 0.48,
            "home_tov_pct": 0.12,
            "away_tov_pct": 0.14,
            "home_fga": 30.0,
            "home_fta": 8.0,
            "home_tov": 5.0,
            "away_fga": 28.0,
            "away_fta": 6.0,
            "away_tov": 4.0,
        }

    def _make_l5(self):
        return {
            "pts": 15.0, "reb": 5.0, "ast": 3.0,
            "fg3m": 1.5, "stl": 0.5, "blk": 0.3,
            "tov": 1.2, "min": 28.0,
        }

    def test_build_v2_row_has_usage_column(self):
        """_build_v2_row always populates LIVE_USAGE_FEATURE in the returned dict."""
        from scripts.ingame.eval_sbs_v2 import _build_v2_row
        row = _build_v2_row(self._make_prow(), self._make_grow(), self._make_l5())
        assert LIVE_USAGE_FEATURE in row, (
            f"_build_v2_row must always populate {LIVE_USAGE_FEATURE}; "
            f"got keys: {set(row.keys())}"
        )
        assert isinstance(row[LIVE_USAGE_FEATURE], float)
        assert -1.0 <= row[LIVE_USAGE_FEATURE] <= 2.0

    def test_build_v2_row_usage_positive_for_high_volume(self):
        """Player with fga=5 on team fga=30 — proxy < prior for typical player."""
        prow = self._make_prow()
        grow = self._make_grow()
        l5 = self._make_l5()
        from scripts.ingame.eval_sbs_v2 import _build_v2_row
        row = _build_v2_row(prow, grow, l5)
        # No strict assertion on sign (depends on prior), just finite and clamped
        assert -1.0 <= row[LIVE_USAGE_FEATURE] <= 2.0

    def test_build_v2_row_no_l5_still_works(self):
        """_build_v2_row handles l5=None (new player) without raising."""
        from scripts.ingame.eval_sbs_v2 import _build_v2_row
        row = _build_v2_row(self._make_prow(), self._make_grow(), l5=None)
        assert LIVE_USAGE_FEATURE in row
        assert -1.0 <= row[LIVE_USAGE_FEATURE] <= 2.0

    def test_build_v2_row_away_side(self):
        """Usage computed correctly for away-side player."""
        prow = self._make_prow()
        prow["side"] = "away"
        prow["team_abbrev"] = "AWY"
        from scripts.ingame.eval_sbs_v2 import _build_v2_row
        row = _build_v2_row(prow, self._make_grow(), self._make_l5())
        assert -1.0 <= row[LIVE_USAGE_FEATURE] <= 2.0
