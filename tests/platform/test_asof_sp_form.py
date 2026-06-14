"""tests/platform/test_asof_sp_form.py

Unit tests for domains.mlb.asof_sp_form.

Key invariants verified:
  1. Snapshot-before-update (no-future-leak): a pitcher's first-game feature is NaN
     because zero prior starts exist; subsequent games use only prior data.
  2. EW update order: the EW mean reflects the correct alpha-weighted sequence.
  3. Handedness parsing from '-R' / '-L' suffix.
  4. First-6-innings isolation: only the first 6 innings are summed; 'x' skipped.
  5. MIN_PRIOR_STARTS gate: NaN emitted when prior starts < threshold.
  6. sp_first6_diff_ew sign convention: positive → home edge (away SP worse).
  7. NO-LEAK assertion: feature at game N uses zero information from game N's result.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest

from domains.mlb.asof_sp_form import (
    _parse_hand,
    _parse_first6,
    _EWState,
    build_sp_form_features,
    EW_ALPHA,
    MIN_PRIOR_STARTS,
    MAX_FIRST6_INNINGS,
)

# ---------------------------------------------------------------------------
# Helpers — build a minimal pitchers / games synthetic DataFrame
# ---------------------------------------------------------------------------

def _make_pitchers(rows: list[dict]) -> pd.DataFrame:
    """Build a synthetic pitchers DataFrame from a list of dicts."""
    defaults = {
        "home_sp_present": True,
        "away_sp_present": True,
        "home_innings": "0,0,0,0,0,0,0,0,x",
        "away_innings": "0,0,0,0,0,0,0,0,0",
        "home_team": "HOM",
        "away_team": "AWY",
    }
    records = []
    for r in rows:
        rec = {**defaults, **r}
        records.append(rec)
    return pd.DataFrame(records)


def _make_games(rows: list[dict]) -> pd.DataFrame:
    """Build a synthetic games DataFrame with required columns."""
    defaults = {"home_runs": 3, "away_runs": 2, "target_home_win": 1,
                "season": 2010, "game_seq": 1, "home_league": "AL",
                "home_team": "HOM", "away_team": "AWY"}
    records = []
    for r in rows:
        rec = {**defaults, **r}
        records.append(rec)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# _parse_hand
# ---------------------------------------------------------------------------

class TestParseHand:
    def test_right_handed(self):
        assert _parse_hand("JBECKETT-R") == "R"

    def test_left_handed(self):
        assert _parse_hand("CSABATHIA-L") == "L"

    def test_no_suffix(self):
        assert _parse_hand("NOLAN") == ""

    def test_none(self):
        assert _parse_hand(None) == ""

    def test_nan_float(self):
        assert _parse_hand(float("nan")) == ""

    def test_ambiguous_r_in_name(self):
        """A name ending in '-R' only at the suffix, not embedded '-R' mid-name."""
        assert _parse_hand("NRANGER-R") == "R"


# ---------------------------------------------------------------------------
# _parse_first6
# ---------------------------------------------------------------------------

class TestParseFirst6:
    def test_normal_9_innings(self):
        # sum of first 6: 0+1+2+1+0+3 = 7
        result = _parse_first6("0,1,2,1,0,3,0,1,x")
        assert result == pytest.approx(7.0)

    def test_skips_x(self):
        # '1,2,3,4,5,x,6' → first 6 numeric tokens: 1+2+3+4+5+6=21
        result = _parse_first6("1,2,3,4,5,x,6")
        assert result == pytest.approx(1 + 2 + 3 + 4 + 5 + 6)

    def test_fewer_than_6_innings(self):
        # Rain-shortened: only 4 numeric entries — sum them
        result = _parse_first6("2,1,0,3,x")
        assert result == pytest.approx(6.0)

    def test_none_input(self):
        assert _parse_first6(None) is None

    def test_nan_input(self):
        assert _parse_first6(float("nan")) is None

    def test_only_x(self):
        assert _parse_first6("x,x,x") is None

    def test_exactly_6_innings(self):
        result = _parse_first6("1,1,1,1,1,1")
        assert result == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# _EWState
# ---------------------------------------------------------------------------

class TestEWState:
    def test_empty_snapshot(self):
        st = _EWState()
        v, n = st.snapshot()
        assert math.isnan(v)
        assert n == 0

    def test_below_min_prior_starts_is_nan(self):
        st = _EWState()
        for _ in range(MIN_PRIOR_STARTS - 1):
            st.update(2.0)
        v, n = st.snapshot()
        assert math.isnan(v)
        assert n == MIN_PRIOR_STARTS - 1

    def test_at_min_prior_starts_not_nan(self):
        st = _EWState()
        for _ in range(MIN_PRIOR_STARTS):
            st.update(2.0)
        v, n = st.snapshot()
        assert not math.isnan(v)
        assert n == MIN_PRIOR_STARTS

    def test_ew_recency_weights_most_recent(self):
        """Most recent observation should have the largest weight in the EW mean."""
        st = _EWState()
        # Feed 3.0 then 0.0: EW mean should be closer to 0.0 than 3.0
        for _ in range(MIN_PRIOR_STARTS):
            st.update(3.0)
        # Now feed a very different value
        st.update(0.0)
        v, _ = st.snapshot()
        # With alpha=0.35, one 0.0 update pushes it below 3.0
        assert v < 3.0

    def test_ew_formula(self):
        """Verify the exact EW update formula with known values."""
        alpha = EW_ALPHA
        st = _EWState()
        st.update(4.0)  # ew = 4.0, n=1
        st.update(2.0)  # ew = (1-a)*4 + a*2
        expected = (1.0 - alpha) * 4.0 + alpha * 2.0
        st.update(1.0)  # further update
        expected2 = (1.0 - alpha) * expected + alpha * 1.0
        # At n=3 (== MIN_PRIOR_STARTS), snapshot should give expected2
        v, n = st.snapshot()
        assert n == 3
        if MIN_PRIOR_STARTS <= 3:
            assert v == pytest.approx(expected2, rel=1e-9)


# ---------------------------------------------------------------------------
# build_sp_form_features — integration tests
# ---------------------------------------------------------------------------

class TestBuildSpFormFeatures:
    """Integration tests using synthetic DataFrames (no file I/O)."""

    def _make_4game_corpus(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """4 games: same pitchers (APITCHER-R vs BPITCHER-L) across all games.

        Game sequence:
          G1: home=APITCHER-R, away=BPITCHER-L
              home_innings="1,0,2,0,1,0,3,0,x"  away_innings="0,0,0,1,0,0,0,1,0"
          G2: same pitchers
          G3: same pitchers
          G4: same pitchers — by now both have >= 3 prior starts
        """
        pitchers = _make_pitchers([
            {"event_id": "EV1", "date": "2010-04-04", "season": 2010,
             "home_sp_name": "APITCHER-R", "away_sp_name": "BPITCHER-L",
             "home_innings": "1,0,2,0,1,0,3,0,x", "away_innings": "0,0,0,1,0,0,0,1,0"},
            {"event_id": "EV2", "date": "2010-04-06", "season": 2010,
             "home_sp_name": "APITCHER-R", "away_sp_name": "BPITCHER-L",
             "home_innings": "0,0,1,0,0,0,1,0,x", "away_innings": "2,0,0,0,2,0,0,0,0"},
            {"event_id": "EV3", "date": "2010-04-08", "season": 2010,
             "home_sp_name": "APITCHER-R", "away_sp_name": "BPITCHER-L",
             "home_innings": "0,1,0,1,0,1,0,1,x", "away_innings": "1,1,1,1,1,1,0,0,0"},
            {"event_id": "EV4", "date": "2010-04-10", "season": 2010,
             "home_sp_name": "APITCHER-R", "away_sp_name": "BPITCHER-L",
             "home_innings": "3,0,0,3,0,0,3,0,x", "away_innings": "0,0,0,0,0,0,0,0,0"},
        ])
        games = _make_games([
            {"event_id": "EV1", "date": "2010-04-04", "season": 2010,
             "home_runs": 8, "away_runs": 2, "target_home_win": 1},
            {"event_id": "EV2", "date": "2010-04-06", "season": 2010,
             "home_runs": 2, "away_runs": 4, "target_home_win": 0},
            {"event_id": "EV3", "date": "2010-04-08", "season": 2010,
             "home_runs": 4, "away_runs": 6, "target_home_win": 0},
            {"event_id": "EV4", "date": "2010-04-10", "season": 2010,
             "home_runs": 6, "away_runs": 0, "target_home_win": 1},
        ])
        return pitchers, games

    def test_output_columns(self):
        pit, gm = self._make_4game_corpus()
        out = build_sp_form_features(pitchers=pit, games=gm)
        from domains.mlb.asof_sp_form import OUT_COLS
        for col in OUT_COLS:
            assert col in out.columns, f"missing column {col!r}"

    def test_one_row_per_game(self):
        pit, gm = self._make_4game_corpus()
        out = build_sp_form_features(pitchers=pit, games=gm)
        assert len(out) == 4

    def test_first_game_nan_due_to_zero_prior_starts(self):
        """Game 1: zero prior starts → NaN feature (no-future-leak assertion)."""
        pit, gm = self._make_4game_corpus()
        out = build_sp_form_features(pitchers=pit, games=gm)
        row0 = out[out["event_id"] == "EV1"].iloc[0]
        assert math.isnan(row0["home_sp_first6_ew"]), "G1 home_sp should be NaN (0 prior starts)"
        assert math.isnan(row0["away_sp_first6_ew"]), "G1 away_sp should be NaN (0 prior starts)"
        assert math.isnan(row0["sp_first6_diff_ew"]), "G1 diff should be NaN"

    def test_no_future_leak_assertion(self):
        """CRITICAL: for game N, the feature must NOT incorporate game N's innings result.

        We verify by checking that prior_starts at G1=0, G2=1, G3=2, G4=3,
        meaning each game only counted the strictly-prior starts.
        """
        pit, gm = self._make_4game_corpus()
        out = build_sp_form_features(pitchers=pit, games=gm)
        out = out.sort_values("event_id").reset_index(drop=True)
        # home SP starts prior: 0, 1, 2, 3 (strictly prior to each game)
        expected_prior = [0, 1, 2, 3]
        actual_prior = out["home_sp_starts_prior"].tolist()
        assert actual_prior == expected_prior, (
            f"No-future-leak VIOLATION: expected prior counts {expected_prior}, "
            f"got {actual_prior}. G_N must NOT see G_N's result."
        )

    def test_min_prior_starts_gate(self):
        """NaN until MIN_PRIOR_STARTS starts; then non-NaN."""
        pit, gm = self._make_4game_corpus()
        out = build_sp_form_features(pitchers=pit, games=gm)
        out = out.sort_values("event_id").reset_index(drop=True)
        for idx in range(MIN_PRIOR_STARTS):
            row = out.iloc[idx]
            assert math.isnan(row["home_sp_first6_ew"]), (
                f"Row {idx}: expected NaN (only {idx} prior starts, threshold={MIN_PRIOR_STARTS})"
            )
        # Row at MIN_PRIOR_STARTS index should be non-NaN (if within our 4-game corpus)
        if MIN_PRIOR_STARTS < len(out):
            row = out.iloc[MIN_PRIOR_STARTS]
            assert not math.isnan(row["home_sp_first6_ew"]), (
                f"Row {MIN_PRIOR_STARTS}: expected non-NaN (has {MIN_PRIOR_STARTS} prior starts)"
            )

    def test_handedness_parsed(self):
        pit, gm = self._make_4game_corpus()
        out = build_sp_form_features(pitchers=pit, games=gm)
        assert (out["home_sp_hand"] == "R").all()
        assert (out["away_sp_hand"] == "L").all()

    def test_diff_sign_convention(self):
        """sp_first6_diff_ew = away_sp_first6_ew - home_sp_first6_ew.
        If away SP has HIGHER EW RA, diff > 0 → home edge."""
        pit, gm = self._make_4game_corpus()
        out = build_sp_form_features(pitchers=pit, games=gm)
        for _, row in out.iterrows():
            if not math.isnan(row["home_sp_first6_ew"]) and not math.isnan(row["away_sp_first6_ew"]):
                expected_diff = row["away_sp_first6_ew"] - row["home_sp_first6_ew"]
                assert row["sp_first6_diff_ew"] == pytest.approx(expected_diff, abs=1e-9), (
                    f"event {row['event_id']}: diff sign convention violated"
                )

    def test_absent_sp_yields_nan(self):
        """When home_sp_present=False the feature must be NaN (not zero)."""
        pit = _make_pitchers([
            {"event_id": "EA1", "date": "2010-04-04", "season": 2010,
             "home_sp_name": "APITCHER-R", "away_sp_name": "BPITCHER-L",
             "home_sp_present": False, "away_sp_present": True,
             "home_innings": "0,0,0,0,0,0,0,0,x", "away_innings": "0,0,0,0,0,0,0,0,0"},
        ])
        gm = _make_games([
            {"event_id": "EA1", "date": "2010-04-04", "season": 2010},
        ])
        out = build_sp_form_features(pitchers=pit, games=gm)
        row = out.iloc[0]
        assert math.isnan(row["home_sp_first6_ew"]), "absent SP should yield NaN feature"

    def test_duplicate_event_id_not_present(self):
        """Each event_id appears exactly once in output."""
        pit, gm = self._make_4game_corpus()
        out = build_sp_form_features(pitchers=pit, games=gm)
        assert out["event_id"].nunique() == len(out), "duplicate event_ids in output"

    def test_ew_updates_use_first6_only(self):
        """Innings 7+ must NOT affect the EW mean. We construct a corpus where innings
        7-9 are huge but innings 1-6 are small, then verify the feature stays low."""
        # Three games (to reach MIN_PRIOR_STARTS) with tiny first-6 and large 7-9
        tiny_first6 = "0,0,0,0,0,0,9,9,9"  # first 6 = 0; innings 7-9 = 27
        pit = _make_pitchers([
            {"event_id": "TB1", "date": "2010-04-04", "season": 2010,
             "home_sp_name": "TPITCHER-R", "away_sp_name": "OTHER-R",
             "away_innings": tiny_first6, "home_innings": tiny_first6},
            {"event_id": "TB2", "date": "2010-04-06", "season": 2010,
             "home_sp_name": "TPITCHER-R", "away_sp_name": "XOTHER-R",
             "away_innings": tiny_first6, "home_innings": tiny_first6},
            {"event_id": "TB3", "date": "2010-04-08", "season": 2010,
             "home_sp_name": "TPITCHER-R", "away_sp_name": "YOTHER-R",
             "away_innings": tiny_first6, "home_innings": tiny_first6},
            {"event_id": "TB4", "date": "2010-04-10", "season": 2010,
             "home_sp_name": "TPITCHER-R", "away_sp_name": "ZOTHER-R",
             "away_innings": tiny_first6, "home_innings": tiny_first6},
        ])
        gm = _make_games([
            {"event_id": "TB1", "date": "2010-04-04", "season": 2010},
            {"event_id": "TB2", "date": "2010-04-06", "season": 2010},
            {"event_id": "TB3", "date": "2010-04-08", "season": 2010},
            {"event_id": "TB4", "date": "2010-04-10", "season": 2010},
        ])
        out = build_sp_form_features(pitchers=pit, games=gm)
        # Game 4 has 3 prior starts; first-6 sum was 0 each time → EW should be 0
        row4 = out[out["event_id"] == "TB4"].iloc[0]
        assert not math.isnan(row4["home_sp_first6_ew"])
        assert row4["home_sp_first6_ew"] == pytest.approx(0.0, abs=1e-9), (
            "innings 7-9 contaminated the EW feature (should use first-6 only)"
        )
