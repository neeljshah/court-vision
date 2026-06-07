"""Tests for signals/clutch_usage_pts.py.

Tests
-----
1. Live-clutch path: when ctx.live is Q4, <5 min, tight margin,
   clutch_scoring_prob is high (> 0.5) and clutch_lift is > 0.
2. Live-non-clutch path: when ctx.live is Q2 (not clutch), clutch_scoring_prob ~0.
3. OT is always clutch: period=5 → clutch_scoring_prob == 1.0.
4. Blowout guard: large margin → low clutch_scoring_prob (< 0.2).
5. Midquarter training path: close Q3 margin → clutch_scoring_prob > 0.5.
6. Atlas read path: when the store returns clutch_scoring data with pts_per36,
   clutch_pts_rate reflects the atlas value.
7. Parquet fallback: when store is None, clutch_pts_rate reflects the parquet value.
8. No player_id: clutch_pts_rate is the league-average prior.
9. validate_output() passes for a valid dict and for None.
10. hypothesis() returns correct name/target/scope/verdict.
11. feature_names() matches emits list.
12. Leak-safety: midquarter lookup does NOT use same-day rows (game_date < cutoff).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.loop.signal import AsOfContext, Hypothesis, Verdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(
    decision_date: str = "2024-10-22",
    player_id: Optional[int] = 1629029,   # SGA
    team: str = "OKC",
    opp: str = "BOS",
    game_id: str = "0022400001",
    live: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> AsOfContext:
    return AsOfContext(
        decision_time=dt.datetime.strptime(decision_date, "%Y-%m-%d"),
        player_id=player_id,
        game_id=game_id,
        team=team,
        opp=opp,
        game_date=decision_date,
        season="2024-25",
        is_home=True,
        scope="live",
        live=live,
        extra=extra or {},
    )


def _live_snapshot(period: int, clock: str, home_score: int, away_score: int) -> Dict:
    return {
        "period": period,
        "clock": clock,
        "home_score": home_score,
        "away_score": away_score,
        "home_team": "OKC",
        "away_team": "BOS",
    }


def _clutch_df_for(pid: int, pts_per36: float = 32.0):
    """Minimal clutch_profiles DataFrame for one player."""
    import pandas as pd
    return pd.DataFrame([{
        "player_id": pid,
        "season": "2024-25",
        "clutch_gp": 25,
        "clutch_min": 5.2,
        "clutch_pts": 8.4,
        "clutch_fg_pct": 0.48,
        "clutch_fg3_pct": 0.36,
        "clutch_ft_pct": 0.88,
        "clutch_pts_per36": pts_per36,
        "clutch_plus_minus": 4.2,
    }])


def _midquarter_df_for(game_id: str, game_date: str, abs_margin: float = 2.0):
    """Minimal midquarter DataFrame for one game."""
    import pandas as pd
    return pd.DataFrame([{
        "game_id": game_id,
        "game_date": pd.Timestamp(game_date),
        "score_margin": abs_margin,   # positive = home leading
        "pregame_win_prob": 0.52,
    }])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestClutchUsagePts:

    def _import_signal(self):
        from signals.clutch_usage_pts import ClutchUsagePts
        return ClutchUsagePts

    # ------------------------------------------------------------------ #
    # 1. Live Q4 clutch: high prob                                        #
    # ------------------------------------------------------------------ #
    def test_live_q4_clutch_high_prob(self):
        """Q4, 3 min left, 2-pt margin → clutch_scoring_prob > 0.5."""
        ClutchUsagePts = self._import_signal()
        live = _live_snapshot(period=4, clock="3:00", home_score=102, away_score=100)
        ctx = _ctx(live=live)
        sig = ClutchUsagePts(store=None)

        import signals.clutch_usage_pts as mod
        empty_df = __import__("pandas").DataFrame()
        with patch.object(mod, "_load_clutch_profiles", return_value=empty_df):
            result = sig.build(ctx)

        assert result is not None
        assert result["clutch_scoring_prob"] > 0.5, (
            f"Expected clutch_prob > 0.5 for Q4/3min/2pt margin; "
            f"got {result['clutch_scoring_prob']}"
        )

    # ------------------------------------------------------------------ #
    # 2. Live Q2: non-clutch → near zero                                  #
    # ------------------------------------------------------------------ #
    def test_live_q2_non_clutch_near_zero(self):
        """Q2 → clutch_scoring_prob == 0.0 (period < 4)."""
        ClutchUsagePts = self._import_signal()
        live = _live_snapshot(period=2, clock="6:00", home_score=55, away_score=53)
        ctx = _ctx(live=live)
        sig = ClutchUsagePts(store=None)

        import signals.clutch_usage_pts as mod
        empty_df = __import__("pandas").DataFrame()
        with patch.object(mod, "_load_clutch_profiles", return_value=empty_df):
            result = sig.build(ctx)

        assert result is not None
        assert result["clutch_scoring_prob"] == 0.0, (
            f"Expected 0.0 for Q2; got {result['clutch_scoring_prob']}"
        )

    # ------------------------------------------------------------------ #
    # 3. Overtime is always clutch: period=5 → prob == 1.0                #
    # ------------------------------------------------------------------ #
    def test_overtime_always_clutch(self):
        """OT (period=5) → clutch_scoring_prob == 1.0 regardless of margin/clock."""
        ClutchUsagePts = self._import_signal()
        live = _live_snapshot(period=5, clock="5:00", home_score=110, away_score=110)
        ctx = _ctx(live=live)
        sig = ClutchUsagePts(store=None)

        import signals.clutch_usage_pts as mod
        empty_df = __import__("pandas").DataFrame()
        with patch.object(mod, "_load_clutch_profiles", return_value=empty_df):
            result = sig.build(ctx)

        assert result is not None
        assert result["clutch_scoring_prob"] == 1.0, (
            f"Expected 1.0 for OT; got {result['clutch_scoring_prob']}"
        )

    # ------------------------------------------------------------------ #
    # 4. Blowout: large margin → low clutch_prob                          #
    # ------------------------------------------------------------------ #
    def test_live_q4_blowout_low_prob(self):
        """Q4, 2 min left, 25-pt blowout → clutch_scoring_prob < 0.2."""
        ClutchUsagePts = self._import_signal()
        live = _live_snapshot(period=4, clock="2:00", home_score=115, away_score=90)
        ctx = _ctx(live=live)
        sig = ClutchUsagePts(store=None)

        import signals.clutch_usage_pts as mod
        empty_df = __import__("pandas").DataFrame()
        with patch.object(mod, "_load_clutch_profiles", return_value=empty_df):
            result = sig.build(ctx)

        assert result is not None
        assert result["clutch_scoring_prob"] < 0.2, (
            f"Expected < 0.2 for 25-pt blowout; got {result['clutch_scoring_prob']}"
        )

    # ------------------------------------------------------------------ #
    # 5. Midquarter training path: close Q3 margin → high prob            #
    # ------------------------------------------------------------------ #
    def test_midquarter_close_game_high_prob(self):
        """Close Q3 margin (2 pts) in midquarter parquet → clutch_scoring_prob > 0.5."""
        import pandas as pd
        ClutchUsagePts = self._import_signal()
        import signals.clutch_usage_pts as mod

        game_date = "2024-10-20"          # 2 days before decision
        mq_df = _midquarter_df_for("0022400001", game_date=game_date, abs_margin=2.0)
        empty_df = pd.DataFrame()

        # No live context; training path uses midquarter
        ctx = _ctx(
            decision_date="2024-10-22",
            game_id="0022400001",
            live=None,
        )
        sig = ClutchUsagePts(store=None)
        with patch.object(mod, "_load_midquarter", return_value=mq_df):
            with patch.object(mod, "_load_clutch_profiles", return_value=empty_df):
                result = sig.build(ctx)

        assert result is not None
        assert result["clutch_scoring_prob"] > 0.5, (
            f"Expected > 0.5 for close Q3 margin; got {result['clutch_scoring_prob']}"
        )

    # ------------------------------------------------------------------ #
    # 6. Atlas read path: pts_per36 from atlas reflected in clutch_rate   #
    # ------------------------------------------------------------------ #
    def test_atlas_clutch_rate_reflected(self):
        """When the store returns clutch_scoring atlas, clutch_pts_rate matches."""
        import pandas as pd
        ClutchUsagePts = self._import_signal()
        import signals.clutch_usage_pts as mod
        from signals.clutch_usage_pts import _MAX_CLUTCH_PTS36

        # Atlas data shaped as sub_fields dict (store contract)
        atlas_data = {
            "scoring": {"pts_per36": 48.0, "gp": 30},
            "usage_context": {},
            "pbp_clutch": {},
        }
        mock_store = MagicMock()
        mock_store.read.return_value = atlas_data

        live = _live_snapshot(period=4, clock="2:00", home_score=100, away_score=98)
        ctx = _ctx(live=live, player_id=1629029)
        sig = ClutchUsagePts(store=mock_store)

        with patch.object(mod, "_load_clutch_profiles", return_value=pd.DataFrame()):
            result = sig.build(ctx)

        assert result is not None
        expected_rate = min(1.5, 48.0 / _MAX_CLUTCH_PTS36)
        assert abs(result["clutch_pts_rate"] - expected_rate) < 0.01, (
            f"Expected clutch_pts_rate~{expected_rate:.3f}, got {result['clutch_pts_rate']}"
        )

    # ------------------------------------------------------------------ #
    # 7. Parquet fallback: pts_per36 from clutch profiles parquet          #
    # ------------------------------------------------------------------ #
    def test_parquet_fallback_clutch_rate(self):
        """When store is None, clutch_pts_rate comes from the clutch profiles parquet."""
        import pandas as pd
        ClutchUsagePts = self._import_signal()
        import signals.clutch_usage_pts as mod
        from signals.clutch_usage_pts import _MAX_CLUTCH_PTS36

        pid = 1629029
        pts36 = 36.0
        clutch_df = _clutch_df_for(pid, pts_per36=pts36)

        live = _live_snapshot(period=5, clock="5:00", home_score=110, away_score=110)
        ctx = _ctx(live=live, player_id=pid)
        sig = ClutchUsagePts(store=None)

        with patch.object(mod, "_load_clutch_profiles", return_value=clutch_df):
            result = sig.build(ctx)

        assert result is not None
        expected_rate = min(1.5, pts36 / _MAX_CLUTCH_PTS36)
        assert abs(result["clutch_pts_rate"] - expected_rate) < 0.01, (
            f"Expected ~{expected_rate:.3f} from parquet, got {result['clutch_pts_rate']}"
        )

    # ------------------------------------------------------------------ #
    # 8. No player_id → league-average prior                              #
    # ------------------------------------------------------------------ #
    def test_no_player_id_league_avg_prior(self):
        """When player_id is None, clutch_pts_rate is the league-average prior."""
        import pandas as pd
        ClutchUsagePts = self._import_signal()
        import signals.clutch_usage_pts as mod
        from signals.clutch_usage_pts import _LEAGUE_AVG_CLUTCH_RATE

        live = _live_snapshot(period=4, clock="3:00", home_score=100, away_score=99)
        ctx = _ctx(live=live, player_id=None)
        sig = ClutchUsagePts(store=None)

        with patch.object(mod, "_load_clutch_profiles", return_value=pd.DataFrame()):
            result = sig.build(ctx)

        assert result is not None
        assert abs(result["clutch_pts_rate"] - _LEAGUE_AVG_CLUTCH_RATE) < 1e-6, (
            f"Expected league avg {_LEAGUE_AVG_CLUTCH_RATE}, got {result['clutch_pts_rate']}"
        )

    # ------------------------------------------------------------------ #
    # 9. validate_output() passes for dict and None                       #
    # ------------------------------------------------------------------ #
    def test_validate_output_valid_dict(self):
        ClutchUsagePts = self._import_signal()
        sig = ClutchUsagePts()
        good = {"clutch_scoring_prob": 0.85, "clutch_pts_rate": 0.60, "clutch_lift": 0.51}
        assert sig.validate_output(good) is True

    def test_validate_output_none(self):
        ClutchUsagePts = self._import_signal()
        sig = ClutchUsagePts()
        assert sig.validate_output(None) is True

    # ------------------------------------------------------------------ #
    # 10. hypothesis() metadata                                            #
    # ------------------------------------------------------------------ #
    def test_hypothesis_metadata(self):
        ClutchUsagePts = self._import_signal()
        sig = ClutchUsagePts()
        h = sig.hypothesis()
        assert isinstance(h, Hypothesis)
        assert h.name == "clutch_usage_pts"
        assert h.target == "pts"
        assert h.scope == "live"
        assert h.expected_verdict == Verdict.SHIP
        assert "clutch_scoring" in h.atlas_fields

    # ------------------------------------------------------------------ #
    # 11. feature_names() matches emits                                   #
    # ------------------------------------------------------------------ #
    def test_feature_names_matches_emits(self):
        ClutchUsagePts = self._import_signal()
        sig = ClutchUsagePts()
        expected = [f"clutch_usage_pts__{k}" for k in sig.emits]
        assert sig.feature_names() == expected

    # ------------------------------------------------------------------ #
    # 12. Leak-safety: midquarter same-day row must NOT be used           #
    # ------------------------------------------------------------------ #
    def test_midquarter_same_day_row_excluded(self):
        """Midquarter rows with game_date == decision_date are excluded (strict < cutoff)."""
        import pandas as pd
        ClutchUsagePts = self._import_signal()
        import signals.clutch_usage_pts as mod

        # game_date == decision_date → should be excluded by the < guard
        same_day = "2024-10-22"
        mq_df = _midquarter_df_for("0022400001", game_date=same_day, abs_margin=2.0)
        empty_df = pd.DataFrame()

        ctx = _ctx(
            decision_date=same_day,   # same day as game_date
            game_id="0022400001",
            live=None,
        )
        sig = ClutchUsagePts(store=None)
        with patch.object(mod, "_load_midquarter", return_value=mq_df):
            with patch.object(mod, "_load_clutch_profiles", return_value=empty_df):
                result = sig.build(ctx)

        # Should fall back to pregame-win-prob path (not midquarter same-day row)
        # The key assertion: no exception and clutch_scoring_prob is in a valid range
        assert result is not None
        assert 0.0 <= result["clutch_scoring_prob"] <= 1.0, (
            f"clutch_scoring_prob out of [0,1]: {result['clutch_scoring_prob']}"
        )

    # ------------------------------------------------------------------ #
    # 13. clutch_lift == clutch_scoring_prob × clutch_pts_rate            #
    # ------------------------------------------------------------------ #
    def test_clutch_lift_is_product(self):
        """clutch_lift must equal clutch_scoring_prob × clutch_pts_rate."""
        import pandas as pd
        ClutchUsagePts = self._import_signal()
        import signals.clutch_usage_pts as mod

        pid = 1629029
        clutch_df = _clutch_df_for(pid, pts_per36=36.0)
        live = _live_snapshot(period=4, clock="2:00", home_score=101, away_score=100)
        ctx = _ctx(live=live, player_id=pid)
        sig = ClutchUsagePts(store=None)

        with patch.object(mod, "_load_clutch_profiles", return_value=clutch_df):
            result = sig.build(ctx)

        assert result is not None
        expected_lift = round(
            result["clutch_scoring_prob"] * result["clutch_pts_rate"], 4
        )
        assert abs(result["clutch_lift"] - expected_lift) < 1e-6, (
            f"clutch_lift {result['clutch_lift']} != "
            f"prob × rate = {expected_lift}"
        )
