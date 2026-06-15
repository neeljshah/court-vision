"""tests/platform/test_asof_box_extra — hermetic unit tests for asof_box_extra.

Invariants tested:
  (a) First game of each team-season has NaN as-of values (no prior).
  (b) Each as-of value equals mean of strictly-PRIOR games only (no same-game leak).
  (c) NO-FUTURE-LEAK: changing a FUTURE game's box stats does NOT change a past
      game's as-of value — the critical structural leak guard.
  (d) Diff columns are home-minus-away (NaN when either side is NaN).
  (e) Two independent team pairs do not contaminate each other's as-of history.
"""
from __future__ import annotations

import math
import pandas as pd
import pytest

_STAT_COLS = ("dreb", "fg3m", "stl", "blk")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player_row(
    game_id: str,
    date: str,
    team: str,
    opp: str,
    is_home: int,
    dreb: float = 0.0,
    fg3m: float = 0.0,
    stl: float = 0.0,
    blk: float = 0.0,
) -> dict:
    return {
        "game_id": game_id, "date": date, "team": team, "opp": opp,
        "is_home": is_home, "dreb": dreb, "fg3m": fg3m, "stl": stl, "blk": blk,
    }


def _run(rows: list) -> pd.DataFrame:
    """Build from an in-memory player-row list using the pure internal helpers only.

    Bypasses file I/O entirely: calls _aggregate_team_games -> _walk_forward_team ->
    _pivot_to_games directly, which are the same functions build_asof_box_extra uses.
    This makes the tests hermetic (no temp file, no disk) while still exercising the
    FULL computation path — identical to what the builder produces.
    """
    from domains.basketball_nba.asof_box_extra import (
        _aggregate_team_games,
        _walk_forward_team,
        _pivot_to_games,
    )
    df = pd.DataFrame(rows)
    tg = _aggregate_team_games(df)
    tg = _walk_forward_team(tg)
    return _pivot_to_games(tg).sort_values("game_id").reset_index(drop=True)


def _4game_rows() -> list:
    """Standard 2-team, 4-game corpus (HOM vs AWY; same pair each game)."""
    return [
        # Game 1
        _make_player_row("G1", "2024-04-01", "HOM", "AWY", 1, dreb=8, fg3m=3, stl=2, blk=1),
        _make_player_row("G1", "2024-04-01", "AWY", "HOM", 0, dreb=6, fg3m=2, stl=1, blk=0),
        # Game 2
        _make_player_row("G2", "2024-04-03", "HOM", "AWY", 1, dreb=10, fg3m=4, stl=3, blk=2),
        _make_player_row("G2", "2024-04-03", "AWY", "HOM", 0, dreb=7,  fg3m=3, stl=2, blk=1),
        # Game 3
        _make_player_row("G3", "2024-04-05", "HOM", "AWY", 1, dreb=9,  fg3m=5, stl=1, blk=3),
        _make_player_row("G3", "2024-04-05", "AWY", "HOM", 0, dreb=5,  fg3m=1, stl=0, blk=2),
        # Game 4
        _make_player_row("G4", "2024-04-07", "HOM", "AWY", 1, dreb=12, fg3m=6, stl=4, blk=2),
        _make_player_row("G4", "2024-04-07", "AWY", "HOM", 0, dreb=8,  fg3m=4, stl=3, blk=1),
    ]


# ---------------------------------------------------------------------------
# (a) First game of each team-season has NaN
# ---------------------------------------------------------------------------

class TestFirstGameIsNaN:
    def test_g1_home_all_stats_nan(self):
        out = _run(_4game_rows())
        g1 = out[out["game_id"] == "G1"].iloc[0]
        for s in _STAT_COLS:
            assert math.isnan(g1[f"home_{s}_pg_asof"]), (
                f"G1 home_{s}_pg_asof must be NaN (zero prior games)")

    def test_g1_away_all_stats_nan(self):
        out = _run(_4game_rows())
        g1 = out[out["game_id"] == "G1"].iloc[0]
        for s in _STAT_COLS:
            assert math.isnan(g1[f"away_{s}_pg_asof"]), (
                f"G1 away_{s}_pg_asof must be NaN (zero prior games)")

    def test_g1_home_n_prior_is_zero(self):
        out = _run(_4game_rows())
        assert out[out["game_id"] == "G1"].iloc[0]["home_n_prior"] == 0

    def test_g1_diff_is_nan_when_sides_are_nan(self):
        out = _run(_4game_rows())
        g1 = out[out["game_id"] == "G1"].iloc[0]
        for s in _STAT_COLS:
            assert math.isnan(g1[f"{s}_diff_asof"]), (
                f"G1 {s}_diff_asof must be NaN when both sides NaN")


# ---------------------------------------------------------------------------
# (b) Each as-of value equals mean of strictly-PRIOR games only
# ---------------------------------------------------------------------------

class TestPriorOnlyMean:
    def test_g2_home_dreb_equals_g1_realized(self):
        out = _run(_4game_rows())
        g2 = out[out["game_id"] == "G2"].iloc[0]
        # HOM's prior: only G1 => dreb=8
        assert g2["home_dreb_pg_asof"] == pytest.approx(8.0, abs=1e-9)

    def test_g3_home_dreb_is_mean_of_g1_g2(self):
        out = _run(_4game_rows())
        g3 = out[out["game_id"] == "G3"].iloc[0]
        # HOM prior: G1=8, G2=10 => mean=9.0
        assert g3["home_dreb_pg_asof"] == pytest.approx(9.0, abs=1e-9)

    def test_g4_home_fg3m_is_mean_of_g1_g2_g3(self):
        out = _run(_4game_rows())
        g4 = out[out["game_id"] == "G4"].iloc[0]
        # HOM prior: G1=3, G2=4, G3=5 => mean=4.0
        assert g4["home_fg3m_pg_asof"] == pytest.approx(4.0, abs=1e-9)

    def test_g4_away_stl_is_mean_of_g1_g2_g3(self):
        out = _run(_4game_rows())
        g4 = out[out["game_id"] == "G4"].iloc[0]
        # AWY prior: G1=1, G2=2, G3=0 => mean=1.0
        assert g4["away_stl_pg_asof"] == pytest.approx(1.0, abs=1e-9)

    def test_n_prior_strictly_counts_prior_games(self):
        out = _run(_4game_rows())
        assert out["home_n_prior"].tolist() == [0, 1, 2, 3], (
            "home_n_prior must count strictly-prior games (snapshot-before-update)")


# ---------------------------------------------------------------------------
# (c) NO-FUTURE-LEAK — CRITICAL structural guard
# ---------------------------------------------------------------------------

class TestNoFutureLeak:
    """Changing a FUTURE game must NOT alter any PAST game's as-of value."""

    def _rows3(self) -> list:
        return [
            _make_player_row("G1", "2024-04-01", "HOM", "AWY", 1, dreb=8,  fg3m=3),
            _make_player_row("G1", "2024-04-01", "AWY", "HOM", 0, dreb=6,  fg3m=2),
            _make_player_row("G2", "2024-04-03", "HOM", "AWY", 1, dreb=10, fg3m=4),
            _make_player_row("G2", "2024-04-03", "AWY", "HOM", 0, dreb=7,  fg3m=3),
            _make_player_row("G3", "2024-04-05", "HOM", "AWY", 1, dreb=9,  fg3m=5),
            _make_player_row("G3", "2024-04-05", "AWY", "HOM", 0, dreb=5,  fg3m=1),
        ]

    def _rows4_extreme(self) -> list:
        """Same 3 games + a 4th with extreme values (999/888) to detect leakage."""
        r3 = self._rows3()
        r3 += [
            _make_player_row("G4", "2024-04-07", "HOM", "AWY", 1, dreb=999, fg3m=999),
            _make_player_row("G4", "2024-04-07", "AWY", "HOM", 0, dreb=888, fg3m=888),
        ]
        return r3

    def test_appending_future_game_leaves_g1_unchanged(self):
        out3 = _run(self._rows3())
        out4 = _run(self._rows4_extreme())
        for col in ("home_dreb_pg_asof", "away_dreb_pg_asof",
                    "home_fg3m_pg_asof", "away_fg3m_pg_asof"):
            v3 = out3[out3["game_id"] == "G1"].iloc[0][col]
            v4 = out4[out4["game_id"] == "G1"].iloc[0][col]
            # Both must be NaN (G1 has no prior) or equal
            if math.isnan(v3):
                assert math.isnan(v4), (
                    f"NO-FUTURE-LEAK VIOLATION G1/{col}: 3g={v3!r} 4g={v4!r}")
            else:
                assert v3 == pytest.approx(v4, abs=1e-12), (
                    f"NO-FUTURE-LEAK VIOLATION G1/{col}: 3g={v3} != 4g={v4}")

    def test_appending_future_game_leaves_g2_g3_unchanged(self):
        out3 = _run(self._rows3())
        out4 = _run(self._rows4_extreme())
        for gid in ("G2", "G3"):
            for col in ("home_dreb_pg_asof", "away_fg3m_pg_asof"):
                v3 = out3[out3["game_id"] == gid].iloc[0][col]
                v4 = out4[out4["game_id"] == gid].iloc[0][col]
                if math.isnan(v3):
                    assert math.isnan(v4), (
                        f"NO-FUTURE-LEAK VIOLATION {gid}/{col}: 3g={v3!r} 4g={v4!r}")
                else:
                    assert v3 == pytest.approx(v4, abs=1e-12), (
                        f"NO-FUTURE-LEAK VIOLATION {gid}/{col}: 3g={v3} != 4g={v4}. "
                        "Future G4 (dreb=999) must NOT contaminate prior as-of values.")

    def test_n_prior_unchanged_by_future_game(self):
        out3 = _run(self._rows3())
        out4 = _run(self._rows4_extreme())
        for gid in ("G1", "G2", "G3"):
            n3 = out3[out3["game_id"] == gid].iloc[0]["home_n_prior"]
            n4 = out4[out4["game_id"] == gid].iloc[0]["home_n_prior"]
            assert n3 == n4, (
                f"NO-FUTURE-LEAK VIOLATION n_prior at {gid}: 3g={n3} != 4g={n4}")


# ---------------------------------------------------------------------------
# (d) Diff columns are home-minus-away
# ---------------------------------------------------------------------------

class TestDiffColumns:
    def test_diff_equals_home_minus_away_all_rows(self):
        out = _run(_4game_rows())
        for _, row in out.iterrows():
            for s in _STAT_COLS:
                h = row[f"home_{s}_pg_asof"]
                a = row[f"away_{s}_pg_asof"]
                d = row[f"{s}_diff_asof"]
                if math.isnan(h) or math.isnan(a):
                    assert math.isnan(d), (
                        f"{s}_diff_asof must be NaN when either side is NaN "
                        f"(game {row['game_id']})")
                else:
                    assert d == pytest.approx(h - a, abs=1e-9), (
                        f"{s}_diff_asof mismatch at game {row['game_id']}")


# ---------------------------------------------------------------------------
# (e) Two independent team pairs do not contaminate each other
# ---------------------------------------------------------------------------

class TestTwoTeamPairIndependence:
    def _two_pair_rows(self) -> list:
        return [
            _make_player_row("G1", "2024-04-01", "HOM", "AWY", 1, dreb=8),
            _make_player_row("G1", "2024-04-01", "AWY", "HOM", 0, dreb=6),
            _make_player_row("G2", "2024-04-03", "HOM", "AWY", 1, dreb=10),
            _make_player_row("G2", "2024-04-03", "AWY", "HOM", 0, dreb=7),
            # Different pair (ALT vs OTH)
            _make_player_row("G3", "2024-04-05", "ALT", "OTH", 1, dreb=5),
            _make_player_row("G3", "2024-04-05", "OTH", "ALT", 0, dreb=3),
            _make_player_row("G4", "2024-04-07", "ALT", "OTH", 1, dreb=4),
            _make_player_row("G4", "2024-04-07", "OTH", "ALT", 0, dreb=9),
        ]

    def test_new_pair_first_game_is_nan(self):
        out = _run(self._two_pair_rows())
        g3 = out[out["game_id"] == "G3"].iloc[0]
        assert math.isnan(g3["home_dreb_pg_asof"]), "ALT first game must be NaN"
        assert math.isnan(g3["away_dreb_pg_asof"]), "OTH first game must be NaN"

    def test_new_pair_second_game_uses_own_history_only(self):
        out = _run(self._two_pair_rows())
        g4 = out[out["game_id"] == "G4"].iloc[0]
        # ALT's only prior is G3 => dreb=5 (NOT contaminated by HOM/AWY)
        assert g4["home_dreb_pg_asof"] == pytest.approx(5.0, abs=1e-9), (
            "ALT G4 asof must equal ALT's G3 result only — not HOM/AWY history")
