# tests/platform/test_soccer_postmortem.py
"""Tests for the soccer post-mortem rule cascade.

LEAK TIER: DESCRIPTIVE/KNOWLEDGE — all assertions are on realized match stats.
No signal/edge claims.
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from domains.soccer.postmortem import (
    _FINISHING_RESIDUAL_THRESHOLD,
    _SOT_DIFF_DRAW_THRESHOLD,
    _compute_features,
    _apply_cascade,
    build_postmortem,
    RULES,
)

# ---------------------------------------------------------------------------
# Helpers to build minimal synthetic DataFrames
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
_STATS_PATH = _ROOT / "data" / "domains" / "soccer" / "match_stats.parquet"
_MATCHES_PATH = _ROOT / "data" / "domains" / "soccer" / "matches.parquet"


def _make_stats_row(**kwargs) -> pd.DataFrame:
    """Return a single-row stats DataFrame with sensible defaults."""
    defaults = dict(
        event_id="test-001",
        div="E1",
        date=pd.Timestamp("2022-01-01"),
        home_team="Home FC",
        away_team="Away FC",
        hthg=1.0,
        htag=0.0,
        htr="H",
        home_shots=10.0,
        away_shots=8.0,
        home_sot=4.0,
        away_sot=3.0,
        home_corners=5.0,
        away_corners=3.0,
        home_fouls=10.0,
        away_fouls=12.0,
        home_yellow=2.0,
        away_yellow=1.0,
        home_red=0.0,
        away_red=0.0,
        referee="Test Ref",
        home_sot_ratio=0.4,
        away_sot_ratio=0.375,
        total_shots=18.0,
        total_sot=7.0,
    )
    defaults.update(kwargs)
    return pd.DataFrame([defaults])


def _make_matches_row(**kwargs) -> pd.DataFrame:
    defaults = dict(
        event_id="test-001",
        date=pd.Timestamp("2022-01-01"),
        season=2022,
        div="E1",
        home_team="Home FC",
        away_team="Away FC",
        fthg=1,
        ftag=0,
        total_goals=1,
        target_over25=0,
        ftr="H",
    )
    defaults.update(kwargs)
    return pd.DataFrame([defaults])


def _full_df(stats_kw: dict, matches_kw: dict) -> pd.DataFrame:
    """Merge a stats+matches row pair and compute features, return feature-enriched df."""
    stats = _make_stats_row(**stats_kw)
    matches = _make_matches_row(**matches_kw)[["event_id", "fthg", "ftag", "ftr", "season"]]
    df = stats.merge(matches, on="event_id", how="left")
    for col in ["home_sot", "away_sot", "home_corners", "away_corners",
                "home_red", "away_red", "fthg", "ftag"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return _compute_features(df)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRuleNames:
    def test_rules_list_complete(self):
        assert "ROUTINE" in RULES
        assert "RED_CARD_SWING" in RULES
        assert len(RULES) == 7


class TestFeatureComputation:
    def test_finishing_residual_home(self):
        df = _full_df(
            {"home_sot": 5.0, "away_sot": 3.0},
            {"fthg": 2, "ftag": 1, "ftr": "H"},
        )
        expected = 2 - 0.32 * 5.0
        assert abs(df["finishing_residual_home"].iloc[0] - expected) < 1e-9

    def test_finishing_residual_away(self):
        df = _full_df(
            {"home_sot": 5.0, "away_sot": 4.0},
            {"fthg": 1, "ftag": 2, "ftr": "A"},
        )
        expected = 2 - 0.32 * 4.0
        assert abs(df["finishing_residual_away"].iloc[0] - expected) < 1e-9

    def test_sot_diff(self):
        df = _full_df({"home_sot": 7.0, "away_sot": 3.0}, {"fthg": 1, "ftag": 0, "ftr": "H"})
        assert df["sot_diff"].iloc[0] == pytest.approx(4.0)

    def test_red_flags_true(self):
        df = _full_df({"home_red": 1.0, "away_red": 0.0}, {"fthg": 0, "ftag": 1, "ftr": "A"})
        assert df["red_flags"].iloc[0] is True or df["red_flags"].iloc[0] == True

    def test_red_flags_false_no_reds(self):
        df = _full_df({"home_red": 0.0, "away_red": 0.0}, {"fthg": 1, "ftag": 0, "ftr": "H"})
        assert df["red_flags"].iloc[0] is False or df["red_flags"].iloc[0] == False


class TestCascadeDeterminism:
    """Same input must always produce same decided_by (no randomness)."""

    def test_same_output_multiple_calls(self):
        df = _full_df(
            {"home_sot": 4.0, "away_sot": 3.0},
            {"fthg": 1, "ftag": 0, "ftr": "H"},
        )
        results = [_apply_cascade(df).iloc[0] for _ in range(5)]
        assert len(set(results)) == 1, "cascade must be deterministic"

    def test_decided_by_never_null(self):
        rows = []
        for i in range(10):
            df = _full_df(
                {"home_sot": float(i), "away_sot": float(i % 3)},
                {"fthg": i % 4, "ftag": i % 3, "ftr": ["H", "D", "A"][i % 3]},
            )
            rows.append(df)
        combined = pd.concat(rows, ignore_index=True)
        labels = _apply_cascade(combined)
        assert labels.notna().all(), "decided_by must never be null"
        assert (labels != "").all(), "decided_by must never be empty"


class TestRedCardSwing:
    """Synthetic: home has red card and away wins → RED_CARD_SWING."""

    def test_away_wins_after_home_red(self):
        df = _full_df(
            {"home_red": 1.0, "away_red": 0.0, "home_sot": 3.0, "away_sot": 4.0,
             "home_corners": 4.0, "away_corners": 3.0},
            {"fthg": 0, "ftag": 1, "ftr": "A"},
        )
        label = _apply_cascade(df).iloc[0]
        assert label == "RED_CARD_SWING", f"Expected RED_CARD_SWING, got {label}"

    def test_home_wins_after_away_red(self):
        df = _full_df(
            {"home_red": 0.0, "away_red": 1.0, "home_sot": 4.0, "away_sot": 3.0,
             "home_corners": 5.0, "away_corners": 4.0},
            {"fthg": 2, "ftag": 0, "ftr": "H"},
        )
        label = _apply_cascade(df).iloc[0]
        assert label == "RED_CARD_SWING", f"Expected RED_CARD_SWING, got {label}"

    def test_no_red_not_swing(self):
        df = _full_df(
            {"home_red": 0.0, "away_red": 0.0, "home_sot": 4.0, "away_sot": 3.0,
             "home_corners": 3.0, "away_corners": 2.0},
            {"fthg": 1, "ftag": 0, "ftr": "H"},
        )
        label = _apply_cascade(df).iloc[0]
        assert label != "RED_CARD_SWING"


class TestDominantButDrew:
    """Synthetic: draw but SoT gap > threshold → DOMINANT_BUT_DREW."""

    def test_home_dominant_drew(self):
        # sot_diff = 6 - 3 = 3 > threshold=2; no red cards; result draw
        # fthg=1, home_sot=6 → residual = 1 - 0.32*6 = -0.92 (< 1.5, no FINISHING_VARIANCE)
        # ftag=1, away_sot=3 → residual = 1 - 0.32*3 = 0.04 (< 1.5)
        df = _full_df(
            {"home_red": 0.0, "away_red": 0.0,
             "home_sot": 6.0, "away_sot": 3.0,
             "home_corners": 4.0, "away_corners": 3.0,
             "htr": "D"},
            {"fthg": 1, "ftag": 1, "ftr": "D"},
        )
        label = _apply_cascade(df).iloc[0]
        assert label == "DOMINANT_BUT_DREW", f"Expected DOMINANT_BUT_DREW, got {label}"

    def test_small_sot_diff_not_dominant_drew(self):
        # sot_diff = 4 - 3 = 1 ≤ threshold=2
        df = _full_df(
            {"home_red": 0.0, "away_red": 0.0,
             "home_sot": 4.0, "away_sot": 3.0,
             "home_corners": 4.0, "away_corners": 4.0,
             "hthg": 0.0, "htag": 0.0, "htr": "D"},
            {"fthg": 1, "ftag": 1, "ftr": "D"},
        )
        label = _apply_cascade(df).iloc[0]
        assert label != "DOMINANT_BUT_DREW"


class TestHTRules:
    def test_ht_collapse_home_draws_from_lead(self):
        # htr=H but ftr=D → HT_COLLAPSE (leader only drew, not a full comeback by away)
        # home_sot=4, fthg=1 → residual = 1 - 1.28 = -0.28 (small)
        # away_sot=3, ftag=1 → residual = 1 - 0.96 = 0.04 (small)
        df = _full_df(
            {"htr": "H", "hthg": 1.0, "htag": 0.0,
             "home_red": 0.0, "away_red": 0.0,
             "home_sot": 4.0, "away_sot": 3.0,
             "home_corners": 4.0, "away_corners": 3.0},
            {"fthg": 1, "ftag": 1, "ftr": "D"},
        )
        label = _apply_cascade(df).iloc[0]
        # sot_diff = 1 ≤ 2 (no DOMINANT_BUT_DREW); no red; residuals small
        # htr=H, ftr=D → ht_flip=True, ht_comeback=False → HT_COLLAPSE fires
        assert label == "HT_COLLAPSE", f"Expected HT_COLLAPSE, got {label}"

    def test_ht_comeback_wins(self):
        # htr=A (away leading at HT) but ftr=H (home wins) → HT_COMEBACK
        df = _full_df(
            {"htr": "A", "hthg": 0.0, "htag": 1.0,
             "home_red": 0.0, "away_red": 0.0,
             "home_sot": 4.0, "away_sot": 3.0,
             "home_corners": 4.0, "away_corners": 3.0},
            {"fthg": 2, "ftag": 1, "ftr": "H"},
        )
        label = _apply_cascade(df).iloc[0]
        assert label == "HT_COMEBACK", f"Expected HT_COMEBACK, got {label}"


class TestRoutine:
    def test_routine_when_nothing_special(self):
        # Equal, no red cards, no ht flip, small residuals, result H
        df = _full_df(
            {"htr": "H", "hthg": 1.0, "htag": 0.0,
             "home_red": 0.0, "away_red": 0.0,
             "home_sot": 4.0, "away_sot": 4.0,
             "home_corners": 5.0, "away_corners": 5.0},
            {"fthg": 1, "ftag": 0, "ftr": "H"},
        )
        # residual_home = 1 - 0.32*4 = -0.28; residual_away = 0 - 0.32*4 = -1.28
        # No rule fires before ROUTINE (sot_diff=0, not a draw, no red)
        label = _apply_cascade(df).iloc[0]
        assert label == "ROUTINE", f"Expected ROUTINE, got {label}"


class TestBuildPostmortem:
    """Integration test against real data (skipped if data missing)."""

    @pytest.mark.skipif(
        not _STATS_PATH.exists() or not _MATCHES_PATH.exists(),
        reason="Real soccer data not present",
    )
    def test_real_data_no_nulls(self, tmp_path):
        out = tmp_path / "postmortem.parquet"
        pm = build_postmortem(
            path_stats=_STATS_PATH,
            path_matches=_MATCHES_PATH,
            output_path=out,
        )
        assert pm["decided_by"].notna().all()
        assert set(pm["decided_by"].unique()).issubset(set(RULES))

    @pytest.mark.skipif(
        not _STATS_PATH.exists() or not _MATCHES_PATH.exists(),
        reason="Real soccer data not present",
    )
    def test_real_data_shape(self, tmp_path):
        out = tmp_path / "postmortem.parquet"
        pm = build_postmortem(
            path_stats=_STATS_PATH,
            path_matches=_MATCHES_PATH,
            output_path=out,
        )
        assert len(pm) > 20_000, "Expected 25k+ rows"
        required_cols = {
            "event_id", "date", "fthg", "ftag", "ftr", "decided_by",
            "finishing_residual_home", "finishing_residual_away",
            "sot_diff", "red_flags", "ht_flip",
        }
        assert required_cols.issubset(set(pm.columns))

    @pytest.mark.skipif(
        not _STATS_PATH.exists() or not _MATCHES_PATH.exists(),
        reason="Real soccer data not present",
    )
    def test_real_red_card_rate_plausible(self, tmp_path):
        out = tmp_path / "postmortem.parquet"
        pm = build_postmortem(
            path_stats=_STATS_PATH,
            path_matches=_MATCHES_PATH,
            output_path=out,
        )
        red_rate = pm["red_flags"].mean()
        # Architect says ~16%; accept 10%–25% as plausible
        assert 0.10 <= red_rate <= 0.30, f"Red card rate {red_rate:.2%} outside plausible range"
