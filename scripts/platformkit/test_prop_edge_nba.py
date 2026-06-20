"""Per-file unit tests for scripts.platformkit.prop_edge_nba.

Covers: name index, stat canonicalization, and edge_for_line_nba (P0-3 criteria 1-4).
Integration/board tests: test_prop_edge_nba_board.py

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_edge_nba.py -q
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit.prop_edge_nba import (
    HONEST_NOTE,
    _build_nba_name_index,
    _canon_nba_stat,
    _resolve_nba_player,
    edge_for_line_nba,
)


# ---------------------------------------------------------------------------
# Shared helpers (also imported by test_prop_edge_nba_board.py)
# ---------------------------------------------------------------------------

def make_df(players=None, n_games=15, seed=42) -> pd.DataFrame:
    """Synthetic player_boxscores shaped DataFrame."""
    rng = np.random.default_rng(seed)
    if players is None:
        players = [
            {"player_id": 1001, "player_name": "LeBron James"},
            {"player_id": 1002, "player_name": "Stephen Curry"},
        ]
    rows = []
    for i, p in enumerate(players):
        for g in range(n_games):
            rows.append({
                "game_id": f"G{i:02d}{g:03d}",
                "date": pd.Timestamp(f"2025-{(g // 10) + 1:02d}-{(g % 10) + 1:02d}"),
                "season": "2024-25",
                "team": "LAL" if i == 0 else "GSW",
                "opp": "BOS",
                "is_home": float(g % 2),
                "player_id": p["player_id"],
                "player_name": p["player_name"],
                "starter": True,
                "min": 30.0 + rng.uniform(-5, 5),
                "pts": max(0.0, float(rng.normal(25.0, 5.0))),
                "reb": max(0.0, float(rng.normal(7.0, 2.0))),
                "ast": max(0.0, float(rng.normal(8.0, 2.0))),
                "stl": max(0.0, float(rng.normal(1.2, 0.5))),
                "blk": max(0.0, float(rng.normal(0.8, 0.4))),
                "fg3m": max(0.0, float(rng.normal(2.5, 1.0))),
                "tov": max(0.0, float(rng.normal(3.0, 1.0))),
                "oreb": 0.0, "dreb": 0.0,
                "fgm": 0.0, "fga": 0.0, "fg3a": 0.0,
                "ftm": 0.0, "fta": 0.0, "pf": 0.0, "plus_minus": 0.0,
            })
    return pd.DataFrame(rows)


def make_line(
    player="LeBron James",
    stat="Points",
    line=25.5,
    payout_type="dfs_pickem",
    over_price=None,
    under_price=None,
) -> PropLine:
    return PropLine(
        sport="nba",
        event_id="E001",
        match="LAL vs BOS",
        player=player,
        team="LAL",
        stat=stat,
        line=line,
        over_price=over_price,
        under_price=under_price,
        payout_type=payout_type,
        source="test",
        as_of="2025-04-01",
    )


def noop_ev(edge: Dict[str, Any], line: PropLine, model_p_over: float,
            conf: str) -> None:
    """Stub apply_ev that sets ev_flag=ok and model_gap only (no network, no prices)."""
    edge["model_gap"] = round(abs(model_p_over - 0.5), 4)
    edge["edge_basis"] = "model_view"
    edge["ev_flag"] = "ok" if conf == "ok" else "uncalibrated_thin"


# ---------------------------------------------------------------------------
# Unit: name index + resolver
# ---------------------------------------------------------------------------

class TestNameIndex:
    def test_builds_index_from_df(self):
        df = make_df()
        idx = _build_nba_name_index(df)
        assert "lebron james" in idx
        assert idx["lebron james"] == 1001

    def test_resolves_exact_case_insensitive(self):
        idx = {"lebron james": 1001, "stephen curry": 1002}
        assert _resolve_nba_player("LeBron James", idx) == 1001
        assert _resolve_nba_player("STEPHEN CURRY", idx) == 1002

    def test_unresolved_name_returns_none(self):
        idx = {"lebron james": 1001}
        assert _resolve_nba_player("Zion Williamson", idx) is None

    def test_none_name_returns_none(self):
        idx = {"lebron james": 1001}
        assert _resolve_nba_player(None, idx) is None

    def test_empty_df_returns_empty_index(self):
        empty_df = pd.DataFrame(columns=["player_name", "player_id"])
        idx = _build_nba_name_index(empty_df)
        assert idx == {}


# ---------------------------------------------------------------------------
# Unit: stat canonicalization
# ---------------------------------------------------------------------------

class TestCanonNbaStat:
    def test_points(self):
        assert _canon_nba_stat("Points") == "pts"
        assert _canon_nba_stat("points") == "pts"

    def test_rebounds(self):
        assert _canon_nba_stat("Rebounds") == "reb"

    def test_3pt(self):
        assert _canon_nba_stat("3-PT Made") == "fg3m"
        assert _canon_nba_stat("3-pt made") == "fg3m"

    def test_combo_pra(self):
        assert _canon_nba_stat("Pts+Reb+Ast") == "pra"

    def test_unsupported_stat_returns_none(self):
        assert _canon_nba_stat("Fantasy Score") is None
        assert _canon_nba_stat("NonExistentStat") is None

    def test_none_returns_none(self):
        assert _canon_nba_stat(None) is None


# ---------------------------------------------------------------------------
# Unit: HONEST_NOTE exported
# ---------------------------------------------------------------------------

class TestHonestNote:
    def test_honest_note_is_nonempty_string(self):
        assert isinstance(HONEST_NOTE, str)
        assert len(HONEST_NOTE) > 0

    def test_honest_note_no_dollar_edge(self):
        low = HONEST_NOTE.lower()
        assert "roi" not in low
        assert "profit" not in low


# ---------------------------------------------------------------------------
# Unit: edge_for_line_nba
# ---------------------------------------------------------------------------

class TestEdgeForLineNba:
    def setup_method(self):
        self.df = make_df()
        self.index = _build_nba_name_index(self.df)
        self.as_of = "2025-06-01"

    def test_valid_line_returns_edge(self):
        line = make_line("LeBron James", "Points", 25.5)
        out = edge_for_line_nba(
            line, self.df, self.as_of, self.index, apply_ev=noop_ev)
        assert "edge" in out, f"Expected edge, got: {out}"
        e = out["edge"]
        assert "model_p_over" in e
        assert 0.0 <= e["model_p_over"] <= 1.0
        # apply_tier not called inside edge_for_line_nba; default tier is MODEL_VIEW
        assert e["tier"] == "MODEL_VIEW"

    def test_valid_line_has_no_dollar_keys(self):
        line = make_line("LeBron James", "Points", 25.5)
        out = edge_for_line_nba(
            line, self.df, self.as_of, self.index, apply_ev=noop_ev)
        assert "edge" in out
        banned = {"roi", "pnl", "profit", "edge_dollars", "dollar_return"}
        keys_lower = {k.lower() for k in out["edge"].keys()}
        for b in banned:
            assert b not in keys_lower, f"Banned key '{b}' found in edge row"

    def test_unknown_player_returns_unresolved(self):
        line = make_line("Unknown Player XYZ", "Points", 25.5)
        out = edge_for_line_nba(
            line, self.df, self.as_of, self.index, apply_ev=noop_ev)
        assert "unresolved" in out
        assert out["unresolved"]["reason"] == "player_not_found"

    def test_unsupported_stat_returns_unresolved(self):
        line = make_line("LeBron James", "Fantasy Score", 45.0)
        out = edge_for_line_nba(
            line, self.df, self.as_of, self.index, apply_ev=noop_ev)
        assert "unresolved" in out
        assert out["unresolved"]["reason"] == "stat_unsupported"

    def test_player_with_no_history_returns_unresolved(self):
        """Player in index but no games before as_of -> insufficient_history."""
        line = make_line("LeBron James", "Points", 25.5)
        out = edge_for_line_nba(
            line, self.df, "2020-01-01", self.index, apply_ev=noop_ev)
        assert "unresolved" in out
        assert out["unresolved"]["reason"] == "insufficient_history"

    def test_unresolved_row_has_required_keys(self):
        line = make_line("Ghost Player", "Points", 20.0)
        out = edge_for_line_nba(
            line, self.df, self.as_of, self.index, apply_ev=noop_ev)
        u = out["unresolved"]
        assert "player" in u
        assert "stat" in u
        assert "reason" in u

    def test_stat_aliases_resolve(self):
        """Multiple alias forms of the same stat all resolve to the engine key."""
        for alias in ["Rebounds", "rebounds", "Assists", "3-PT Made"]:
            line = make_line("LeBron James", alias, 5.0)
            out = edge_for_line_nba(
                line, self.df, self.as_of, self.index, apply_ev=noop_ev)
            assert "edge" in out, f"Expected edge for stat alias '{alias}'"

    def test_priced_line_model_gap_or_ev_fields(self):
        """DFS pickem -> edge_basis=model_view; apply_ev can set model_gap."""
        line = make_line("LeBron James", "Points", 25.5, payout_type="dfs_pickem")
        out = edge_for_line_nba(
            line, self.df, self.as_of, self.index, apply_ev=noop_ev)
        assert "edge" in out
        e = out["edge"]
        assert e["edge_basis"] == "model_view"
        assert e["model_gap"] is not None
