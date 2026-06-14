"""tests/platform/test_asof_espn_box — hermetic unit tests for asof_espn_box.

Invariants: (1) first-game NaN, (2) prior-count monotonicity, (3) arithmetic
correctness (mean of strictly-prior games), (4) NO-FUTURE-LEAK (appending
a future game leaves earlier rows byte-identical), (5) diff = home - away,
(6) two-team independence, (7) output schema present.
"""
from __future__ import annotations

import math
import pandas as pd
import pytest

from domains.mlb.asof_espn_box import build_asof_espn_box

_STAT_COLS = ["bat_runs", "bat_hits", "bat_homeRuns"]


def _make_box_df(rows: list[dict]) -> pd.DataFrame:
    defaults: dict = {
        "home_abbr": "HOM", "away_abbr": "AWY",
        "home_score": 3.0, "away_score": 2.0,
    }
    for s in _STAT_COLS:
        defaults[f"home_{s}"] = 0.0
        defaults[f"away_{s}"] = 0.0
    return pd.DataFrame([{**defaults, **r} for r in rows])


def _run(df: pd.DataFrame) -> pd.DataFrame:
    result, _ = build_asof_espn_box(src=df, out_path="/dev/null")
    return result.sort_values("event_id").reset_index(drop=True)


def _4game() -> pd.DataFrame:
    return _make_box_df([
        {"event_id": "G1", "date": "2024-04-01",
         "home_bat_runs": 5.0, "away_bat_runs": 3.0,
         "home_bat_hits": 10.0, "away_bat_hits": 7.0},
        {"event_id": "G2", "date": "2024-04-03",
         "home_bat_runs": 7.0, "away_bat_runs": 2.0,
         "home_bat_hits": 11.0, "away_bat_hits": 6.0},
        {"event_id": "G3", "date": "2024-04-05",
         "home_bat_runs": 4.0, "away_bat_runs": 6.0,
         "home_bat_hits": 8.0, "away_bat_hits": 9.0},
        {"event_id": "G4", "date": "2024-04-07",
         "home_bat_runs": 9.0, "away_bat_runs": 1.0,
         "home_bat_hits": 14.0, "away_bat_hits": 5.0},
    ])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestOutputSchema:
    def test_required_columns_present(self):
        df = _run(_4game())
        for col in ("event_id", "home_n_prior", "away_n_prior",
                    "home_bat_runs_asof", "away_bat_runs_asof", "diff_bat_runs_asof"):
            assert col in df.columns, f"missing column {col!r}"

    def test_one_row_per_game_no_dupes(self):
        df = _run(_4game())
        assert len(df) == 4
        assert df["event_id"].nunique() == 4


# ---------------------------------------------------------------------------
# Snapshot-before-update (no-future-leak structurally)
# ---------------------------------------------------------------------------

class TestSnapshotBeforeUpdate:
    def test_first_game_both_sides_nan(self):
        out = _run(_4game())
        g1 = out[out["event_id"] == "G1"].iloc[0]
        assert math.isnan(g1["home_bat_runs_asof"]), "G1 home must be NaN (0 prior)"
        assert math.isnan(g1["away_bat_runs_asof"]), "G1 away must be NaN (0 prior)"

    def test_prior_counts_are_strictly_prior(self):
        out = _run(_4game())
        assert out["home_n_prior"].tolist() == [0, 1, 2, 3], (
            "home_n_prior must count STRICTLY-prior games; snapshot-before-update violated"
        )
        assert out["away_n_prior"].tolist() == [0, 1, 2, 3]

    def test_game2_asof_equals_game1_realized(self):
        out = _run(_4game())
        g2 = out[out["event_id"] == "G2"].iloc[0]
        assert g2["home_bat_runs_asof"] == pytest.approx(5.0, abs=1e-9)
        assert g2["away_bat_runs_asof"] == pytest.approx(3.0, abs=1e-9)

    def test_game3_asof_is_mean_of_g1_g2(self):
        out = _run(_4game())
        g3 = out[out["event_id"] == "G3"].iloc[0]
        assert g3["home_bat_runs_asof"] == pytest.approx(6.0, abs=1e-9)

    def test_game4_asof_is_mean_of_g1_g2_g3(self):
        out = _run(_4game())
        g4 = out[out["event_id"] == "G4"].iloc[0]
        assert g4["home_bat_runs_asof"] == pytest.approx((5 + 7 + 4) / 3, abs=1e-9)


# ---------------------------------------------------------------------------
# Diff columns
# ---------------------------------------------------------------------------

class TestDiffColumns:
    def test_diff_equals_home_minus_away_all_rows(self):
        out = _run(_4game())
        for _, row in out.iterrows():
            h = row["home_bat_runs_asof"]
            a = row["away_bat_runs_asof"]
            d = row["diff_bat_runs_asof"]
            if math.isnan(h) or math.isnan(a):
                assert math.isnan(d), f"diff must be NaN when either side is NaN ({row['event_id']})"
            else:
                assert d == pytest.approx(h - a, abs=1e-9), f"diff wrong at {row['event_id']}"


# ---------------------------------------------------------------------------
# Two-team independence
# ---------------------------------------------------------------------------

class TestTwoTeamIndependence:
    def _two_pair_corpus(self) -> pd.DataFrame:
        return _make_box_df([
            {"event_id": "G1", "date": "2024-04-01",
             "home_abbr": "HOM", "away_abbr": "AWY",
             "home_bat_runs": 5.0, "away_bat_runs": 3.0},
            {"event_id": "G2", "date": "2024-04-03",
             "home_abbr": "HOM", "away_abbr": "AWY",
             "home_bat_runs": 7.0, "away_bat_runs": 2.0},
            {"event_id": "G3", "date": "2024-04-05",
             "home_abbr": "ALT", "away_abbr": "OTH",
             "home_bat_runs": 4.0, "away_bat_runs": 6.0},
            {"event_id": "G4", "date": "2024-04-07",
             "home_abbr": "ALT", "away_abbr": "OTH",
             "home_bat_runs": 9.0, "away_bat_runs": 1.0},
        ])

    def test_new_team_first_appearance_is_nan(self):
        out = _run(self._two_pair_corpus())
        g3 = out[out["event_id"] == "G3"].iloc[0]
        assert math.isnan(g3["home_bat_runs_asof"]), "ALT first game must be NaN"
        assert math.isnan(g3["away_bat_runs_asof"]), "OTH first game must be NaN"

    def test_new_team_second_game_uses_only_own_history(self):
        out = _run(self._two_pair_corpus())
        g4 = out[out["event_id"] == "G4"].iloc[0]
        assert g4["home_bat_runs_asof"] == pytest.approx(4.0, abs=1e-9), (
            "ALT G4 asof must equal ALT's G3 result (4.0) — not contaminated by HOM/AWY"
        )


# ---------------------------------------------------------------------------
# NO-FUTURE-LEAK (structural assertion)
# ---------------------------------------------------------------------------

class TestNoFutureLeak:
    def _corpus3(self) -> pd.DataFrame:
        return _make_box_df([
            {"event_id": "G1", "date": "2024-04-01",
             "home_bat_runs": 5.0, "away_bat_runs": 3.0},
            {"event_id": "G2", "date": "2024-04-03",
             "home_bat_runs": 7.0, "away_bat_runs": 2.0},
            {"event_id": "G3", "date": "2024-04-05",
             "home_bat_runs": 4.0, "away_bat_runs": 6.0},
        ])

    def _corpus4(self) -> pd.DataFrame:
        df3 = self._corpus3()
        extra = _make_box_df([
            {"event_id": "G4", "date": "2024-04-07",
             "home_bat_runs": 999.0, "away_bat_runs": 888.0},
        ])
        return pd.concat([df3, extra], ignore_index=True)

    def test_appending_future_game_leaves_prior_asof_unchanged(self):
        out3 = _run(self._corpus3())
        out4 = _run(self._corpus4())
        col = "home_bat_runs_asof"
        for eid in ("G1", "G2", "G3"):
            v3 = out3[out3["event_id"] == eid].iloc[0][col]
            v4 = out4[out4["event_id"] == eid].iloc[0][col]
            if math.isnan(v3):
                assert math.isnan(v4), (
                    f"NO-FUTURE-LEAK VIOLATION at {eid}: "
                    f"3-game={v3!r} vs 4-game={v4!r}"
                )
            else:
                assert v3 == pytest.approx(v4, abs=1e-12), (
                    f"NO-FUTURE-LEAK VIOLATION at {eid}: "
                    f"3-game={v3} != 4-game={v4}. "
                    "Future game G4 (bat_runs=999) changed an earlier as-of feature."
                )

    def test_n_prior_unchanged_by_future_game(self):
        out3 = _run(self._corpus3())
        out4 = _run(self._corpus4())
        for eid in ("G1", "G2", "G3"):
            n3 = out3[out3["event_id"] == eid].iloc[0]["home_n_prior"]
            n4 = out4[out4["event_id"] == eid].iloc[0]["home_n_prior"]
            assert n3 == n4, (
                f"NO-FUTURE-LEAK VIOLATION (n_prior) at {eid}: 3g={n3} != 4g={n4}"
            )


# ---------------------------------------------------------------------------
# Validation — bad inputs raise
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_event_id_raises(self):
        df = _make_box_df([{"event_id": "X1", "date": "2024-01-01"}]).drop(columns=["event_id"])
        with pytest.raises(KeyError):
            build_asof_espn_box(src=df, out_path="/dev/null")

    def test_missing_home_abbr_raises(self):
        df = _make_box_df([{"event_id": "X1", "date": "2024-01-01"}]).drop(columns=["home_abbr"])
        with pytest.raises(KeyError):
            build_asof_espn_box(src=df, out_path="/dev/null")

    def test_no_stat_columns_raises_value_error(self):
        df = pd.DataFrame({
            "event_id": ["X1"], "date": ["2024-01-01"],
            "home_abbr": ["HOM"], "away_abbr": ["AWY"],
        })
        with pytest.raises(ValueError, match="No ASOF_FEATURES"):
            build_asof_espn_box(src=df, out_path="/dev/null")
