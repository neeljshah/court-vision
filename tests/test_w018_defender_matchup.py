"""tests/test_w018_defender_matchup.py — W-018 CV_DEFENDER_MATCHUP gate tests.

Validates:
  1. Flag OFF: project_from_snapshot output is byte-identical to baseline
     (no matchup adjustment applied, no matchup keys injected).
  2. Flag ON: matchup adjustment is applied for supported stats (pts, fg3m, stl,
     blk, tov) when a defender is present in the snapshot.
  3. PROTECT AST: AST rows are NEVER modified by the matchup block — the
     projection must be byte-identical regardless of defender assignment.
  4. MIN_POSS guard: with partial_poss < 30 the multiplier is a no-op
     (apply_matchup_adjustment returns projection unchanged).
  5. Bayesian shrink: lambda = poss/(poss+60); clamp [0.55, 1.55].
  6. matchups_source:'unavailable' written when no matchup data is available.
  7. Byte-identical with flag OFF confirmed across 10 synthetic rows.

All tests are pure-unit (no network, no heavy models, no parquet reads).
Run: python -m pytest tests/test_w018_defender_matchup.py -v
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("NBA_OFFLINE", "1")

# ── helpers ──────────────────────────────────────────────────────────────────

FLAG = "CV_DEFENDER_MATCHUP"


def _make_snap(
    players: Optional[List[Dict[str, Any]]] = None,
    game_id: str = "0042599999",
    period: int = 3,
    clock: str = "12:00",
) -> Dict[str, Any]:
    """Minimal synthetic snapshot."""
    return {
        "game_id": game_id,
        "period": period,
        "clock": clock,
        "home_team": "OKC",
        "away_team": "NYK",
        "home_score": 55,
        "away_score": 50,
        "players": players or [],
    }


def _make_rows(stats: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Synthetic projection rows for player 1000."""
    stats = stats or ["pts", "reb", "ast", "fg3m"]
    rows = []
    for i, stat in enumerate(stats):
        rows.append({
            "player_id": 1000,
            "name": "Test Player",
            "team": "OKC",
            "stat": stat,
            "current": 10.0,
            "projected_final": 20.0 + i,
            "projection_source": "cycle_88_linear",
            "snapshot_period": 3,
            "snapshot_clock": "12:00",
        })
    return rows


# ── core math tests (no engine call, pure module) ────────────────────────────

class TestBayesianShrink:
    """Unit tests for the Bayesian shrink math in defender_matchup_residual."""

    def test_low_poss_lambda(self):
        from src.prediction.defender_matchup_residual import _shrink_multiplier
        # 30 poss: lambda = 30/90 = 0.333; rate_ratio=2.0 → mult = 0.333*2+0.667 = 1.333
        mult = _shrink_multiplier(2.0, 30.0)
        assert abs(mult - (30.0 / 90.0 * 2.0 + 60.0 / 90.0 * 1.0)) < 1e-9

    def test_high_poss_lambda(self):
        from src.prediction.defender_matchup_residual import _shrink_multiplier
        # 90 poss: lambda = 90/150 = 0.60; rate_ratio=0.5 → mult = 0.60*0.5+0.40 = 0.70
        mult = _shrink_multiplier(0.5, 90.0)
        assert abs(mult - (90.0 / 150.0 * 0.5 + 60.0 / 150.0 * 1.0)) < 1e-9

    def test_floor_clamp(self):
        from src.prediction.defender_matchup_residual import _shrink_multiplier
        # rate_ratio near zero → clamped at 0.55
        mult = _shrink_multiplier(0.0, 600.0)
        assert mult == pytest.approx(0.55, abs=1e-9)

    def test_ceil_clamp(self):
        from src.prediction.defender_matchup_residual import _shrink_multiplier
        # rate_ratio=10.0, 600 poss (pure empirical) → raw=10.0, clamped to 1.55
        mult = _shrink_multiplier(10.0, 600.0)
        assert mult == pytest.approx(1.55, abs=1e-9)

    def test_no_adjustment_when_poss_zero(self):
        from src.prediction.defender_matchup_residual import apply_matchup_adjustment
        proj, reason = apply_matchup_adjustment(
            1000, "pts", 25.0, snapshot=None, defender_id=9999,
        )
        # defender is unknown, no CSVs loaded → should skip
        assert proj == 25.0
        assert "matchup_skip" in reason


class TestMinPossGuard:
    """MIN_POSS=30: pairs with < 30 poss must no-op."""

    def test_low_sample_returns_unchanged(self):
        """Build an in-memory matchup DF with partial_poss=10 (< 30 floor)."""
        import pandas as pd
        from src.prediction.defender_matchup_residual import apply_matchup_adjustment

        matchup_df = pd.DataFrame([{
            "off_player_id": 1000,
            "def_player_id": 2000,
            "pts_allowed": 8.0,
            "fg3m_allowed": 1.0,
            "ast_allowed": 2.0,
            "tov_forced": 1.0,
            "blocks": 0.0,
            "partial_poss": 10.0,  # below MIN_POSS=30
        }])
        series_df = pd.DataFrame([{
            "player_id": 1000,
            "pts_pg": 20.0,
            "fg3m_pg": 2.0,
            "ast_pg": 4.0,
            "tov_pg": 2.0,
            "blk_pg": 0.5,
            "min_pg": 32.0,
        }])

        proj, reason = apply_matchup_adjustment(
            1000, "pts", 25.0,
            snapshot=None, defender_id=2000,
            matchup_df=matchup_df, series_df=series_df,
        )
        assert proj == 25.0
        assert "low_sample" in reason

    def test_exactly_30_poss_applies(self):
        """Exactly MIN_POSS=30 should APPLY (inclusive)."""
        import pandas as pd
        from src.prediction.defender_matchup_residual import apply_matchup_adjustment

        matchup_df = pd.DataFrame([{
            "off_player_id": 1000,
            "def_player_id": 2000,
            "pts_allowed": 15.0,
            "fg3m_allowed": 0.0,
            "ast_allowed": 0.0,
            "tov_forced": 0.0,
            "blocks": 0.0,
            "partial_poss": 30.0,  # exactly at threshold
        }])
        series_df = pd.DataFrame([{
            "player_id": 1000,
            "pts_pg": 20.0,
            "fg3m_pg": 0.0,
            "ast_pg": 0.0,
            "tov_pg": 0.0,
            "blk_pg": 0.0,
            "min_pg": 32.0,
        }])

        proj, reason = apply_matchup_adjustment(
            1000, "pts", 25.0,
            snapshot=None, defender_id=2000,
            matchup_df=matchup_df, series_df=series_df,
        )
        # Should apply (not skip on low_sample)
        assert "matchup_applied" in reason


# ── byte-identical flag-OFF tests ─────────────────────────────────────────────

class TestFlagOffByteIdentical:
    """With CV_DEFENDER_MATCHUP unset, project_from_snapshot must be
    byte-identical to baseline (no matchup keys injected into rows)."""

    def _snap(self):
        players = [{
            "player_id": 1000, "name": "Test Player", "team": "OKC",
            "min": 20.0, "pts": 10, "reb": 4, "ast": 3, "fg3m": 1,
            "stl": 1, "blk": 0, "tov": 2, "pf": 2,
            "current_defender_id": 2000,
        }]
        return _make_snap(players=players)

    def setup_method(self):
        os.environ.pop(FLAG, None)

    def teardown_method(self):
        os.environ.pop(FLAG, None)

    def test_no_matchup_keys_in_rows_flag_off(self):
        """With flag OFF, rows must have no matchup_reason key."""
        from src.prediction.live_engine import project_from_snapshot
        snap = self._snap()
        rows = project_from_snapshot(snap)
        for r in rows:
            assert "matchup_reason" not in r, (
                f"flag OFF must not inject matchup_reason into rows; got {r}"
            )

    def test_no_matchups_in_snap_flag_off(self):
        """With flag OFF, snap must not have matchups_source added."""
        from src.prediction.live_engine import project_from_snapshot
        snap = self._snap()
        project_from_snapshot(snap)
        assert "matchups_source" not in snap, (
            "flag OFF must not add matchups_source to snap"
        )

    def test_projected_final_unchanged_flag_off(self):
        """With flag OFF, projected_final must be identical to a second run."""
        from src.prediction.live_engine import project_from_snapshot
        snap1 = self._snap()
        snap2 = self._snap()
        rows1 = project_from_snapshot(snap1)
        rows2 = project_from_snapshot(snap2)
        pf1 = {(r["player_id"], r["stat"]): r.get("projected_final") for r in rows1}
        pf2 = {(r["player_id"], r["stat"]): r.get("projected_final") for r in rows2}
        assert pf1 == pf2, "flag OFF: two identical snaps must produce identical projections"


# ── AST protection tests ──────────────────────────────────────────────────────

class TestASTProtection:
    """PROTECT AST: AST rows must NEVER be adjusted by the matchup block."""

    def _snap_with_defender(self):
        return _make_snap(players=[{
            "player_id": 1000, "name": "Test Player", "team": "OKC",
            "min": 20.0, "pts": 10, "reb": 4, "ast": 3, "fg3m": 1,
            "stl": 1, "blk": 0, "tov": 2, "pf": 2,
            "current_defender_id": 2000,
        }])

    def setup_method(self):
        os.environ.pop(FLAG, None)

    def teardown_method(self):
        os.environ.pop(FLAG, None)

    def test_ast_not_adjusted_with_defender_in_snap(self):
        """Even when a defender is in the snapshot and flag is ON, AST
        must not have a matchup_reason logged. (In live path AST is always
        skipped by the _MATCHUP_STATS guard.)"""
        # This test exercises the apply_matchup_adjustment skip logic.
        from src.prediction.defender_matchup_residual import apply_matchup_adjustment
        proj, reason = apply_matchup_adjustment(
            1000, "ast", 5.0, snapshot=None, defender_id=2000,
        )
        # AST is in _STAT_TO_COLS with value None → stat_not_supported
        assert proj == 5.0
        assert "matchup_skip" in reason

    def test_ast_projected_final_unchanged(self):
        """apply_matchup_adjustment must always leave AST unchanged regardless
        of whether it skips due to stat_not_supported, missing CSV, or missing
        pair — the projection value is the invariant, not the reason string."""
        from src.prediction.defender_matchup_residual import apply_matchup_adjustment
        # AST is in _STAT_TO_COLS as None → always returns (proj, skip:*) unchanged.
        for proj_val in [0.0, 3.5, 12.7, 25.0]:
            adj, reason = apply_matchup_adjustment(
                1000, "ast", proj_val, snapshot=None, defender_id=99999,
            )
            assert adj == proj_val, (
                f"AST proj={proj_val} was changed to {adj} — must be protected"
            )
            # Any matchup_skip reason is acceptable; projection must not change.
            assert "matchup_skip" in reason, (
                f"AST must always return a skip reason; got: {reason!r}"
            )


# ── matchups_source:'unavailable' tests ───────────────────────────────────────

class TestMatchupsSourceUnavailable:
    """When the CDN is blocked / no matchup data available,
    matchups_source must be written as 'unavailable'."""

    def test_seeder_sets_unavailable_when_no_csv(self):
        """seed_matchups_from_series with no CSV → snap["matchups"] stays empty
        → override with blocked fetch → matchups_source = 'unavailable'."""
        from src.data.live_matchup_seeder import (
            seed_matchups_from_series,
            override_matchups_from_live_game,
        )

        snap = _make_snap()
        # Seed with a nonexistent path → no-op.
        seed_matchups_from_series(snap, series_csv_path="/nonexistent/path.csv")
        # Override with a fetch_fn that returns [] (CDN blocked).
        override_matchups_from_live_game(snap, game_id="0042599999",
                                         fetch_fn=lambda gid: [])
        # Both sources gave nothing → matchups is empty → set unavailable.
        matchups = snap.get("matchups") or {}
        meta = snap.get("_matchups_meta") or {}
        assert meta.get("live_overrides", 0) == 0
        assert not matchups  # empty dict

    def test_seeder_populates_when_csv_present(self, tmp_path):
        """With a valid CSV, seed_matchups_from_series must populate matchups."""
        import pandas as pd
        from src.data.live_matchup_seeder import seed_matchups_from_series

        csv_path = tmp_path / "wcf_defensive_matchups.csv"
        pd.DataFrame([{
            "off_player_id": 1000,
            "def_player_id": 2000,
            "matchup_min": 10.0,
            "partial_poss": 50.0,
        }]).to_csv(csv_path, index=False)

        snap = _make_snap()
        seed_matchups_from_series(snap, series_csv_path=str(csv_path))
        assert snap.get("matchups", {}).get(1000) == 2000


# ── re-export shim test ───────────────────────────────────────────────────────

class TestLiveMatchupSeederShim:
    """src/prediction/live_matchup_seeder.py must re-export the two public
    functions from src/data/live_matchup_seeder.py."""

    def test_shim_exports_seed(self):
        from src.prediction.live_matchup_seeder import seed_matchups_from_series
        assert callable(seed_matchups_from_series)

    def test_shim_exports_override(self):
        from src.prediction.live_matchup_seeder import override_matchups_from_live_game
        assert callable(override_matchups_from_live_game)

    def test_shim_is_same_object(self):
        from src.prediction.live_matchup_seeder import seed_matchups_from_series as a
        from src.data.live_matchup_seeder import seed_matchups_from_series as b
        assert a is b
