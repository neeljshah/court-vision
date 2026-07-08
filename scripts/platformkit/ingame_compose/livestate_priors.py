"""livestate_priors -- SEASON-TO-DATE (strictly-prior) tables that v2 in-game
features condition on. Every table here answers "what did we know about this
player/league BEFORE today's game date", never anything from today or later.

Three tables, all keyed off date so the as-of cut is a single `< target_date`
filter (same discipline as compose.team_form, reused not reinvented):

  player_net48_asof(game_id, player_id)  -- minute-weighted lineup net rating
      over that PLAYER's own strictly-prior stints (data/cache/team_system/
      lineups/stints_2025_26.parquet, exploded lineup_key -> one row/player).
      Reuses team_form._asof_net_per48 verbatim (it only needs a "team" key
      column, so a player_id column is passed under that name).
  top3_fga_by_team(team, date) -> list[int]  -- the team's 3 highest
      cumulative-FGA players as of strictly-prior games (data/domains/
      basketball_nba/player_boxscores.parquet). An absent/injured star still
      ranks top-3 (roster history, not tonight's box score) so his 0 minutes
      tonight correctly shows up as an absence.
  league_shot_rates_asof(date) -> (p2, p3, pft)  -- league-wide make rate by
      shot type over all STRICTLY-PRIOR games (any team) -- the "zone-average"
      fallback: this PBP feed's `area` field is always empty (no shot location),
      so the finest granularity actually available is shot TYPE, not zone.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pandas as pd

from scripts.platformkit.compose.team_form import _asof_net_per48

_REPO = Path(__file__).resolve().parents[3]
_STINTS = _REPO / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_BOX = _REPO / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_GAMES = _REPO / "data" / "domains" / "basketball_nba" / "games.parquet"


def build_player_net48_asof(stints: pd.DataFrame | None = None,
                            games: pd.DataFrame | None = None) -> pd.Series:
    """Series indexed by (game_id, player_id) -> strictly-prior net-per-48.

    Each stint's team-level (pts_for, pts_against, elapsed_s) is attributed to
    every player in its lineup_key (standard lineup net-rating convention: all
    5 players share the stint's plus-minus). Summed to one row per
    (game_id, player_id), then _asof_net_per48 does the cumulative-minus-
    current, strictly-prior-by-date reduction -- identical machinery to the
    team-level version in team_form.py, just keyed on player instead of team."""
    st = stints if stints is not None else pd.read_parquet(_STINTS)
    gm = games if games is not None else pd.read_parquet(_GAMES)
    gm = gm[["game_id", "date"]].copy()
    gm["date"] = pd.to_datetime(gm["date"])

    rows = st[["game_id", "lineup_key", "pts_for", "pts_against", "elapsed_s"]]
    exploded = rows.assign(
        player_id=rows["lineup_key"].str.split(",")
    ).explode("player_id")
    exploded = exploded[exploded["player_id"] != ""]
    exploded["player_id"] = exploded["player_id"].astype(int)  # int everywhere (matches boxscores)
    per_game = exploded.groupby(["game_id", "player_id"], as_index=False).agg(
        pf=("pts_for", "sum"), pa=("pts_against", "sum"), sec=("elapsed_s", "sum"))
    long = per_game.merge(gm, on="game_id", how="inner").rename(
        columns={"player_id": "team"})  # _asof_net_per48 groups by "team"
    net = _asof_net_per48(long)
    net.index = net.index.set_names(["game_id", "player_id"])
    return net


def build_top3_fga_table(box: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per (team, player_id, date) row with `cum_fga` = TOTAL fga through that
    game inclusive (a running total, not strictly-prior -- strictly-prior is
    applied at lookup time in top3_fga_by_team via the `date < target` filter,
    which is what actually enforces the as-of boundary)."""
    b = box if box is not None else pd.read_parquet(_BOX)
    b = b[["team", "player_id", "date", "fga"]].copy()
    b["date"] = pd.to_datetime(b["date"])
    b = b.sort_values(["team", "player_id", "date"])
    b["cum_fga"] = b.groupby(["team", "player_id"])["fga"].cumsum()
    return b


def top3_fga_by_team(table: pd.DataFrame, team: str, target_date) -> List[int]:
    """Team's 3 highest cumulative-FGA players as of strictly-prior games.

    Empty list if the team has no prior game in `table` (first game of a
    season for that franchise's row -- genuinely no history, not imputed)."""
    prior = table[(table["team"] == team) & (table["date"] < target_date)]
    if prior.empty:
        return []
    last = prior.sort_values("date").groupby("player_id").tail(1)
    top = last.nlargest(3, "cum_fga")["player_id"]
    return [int(p) for p in top]


def build_league_shot_rate_table(box: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per distinct date with cumulative-THROUGH-that-date league
    totals for (fg2m, fg2a, fg3m, fg3a, ftm, fta) -- daily granularity because
    that is the table's key; strictly-prior lookup (date < target) happens in
    league_shot_rates_asof."""
    b = box if box is not None else pd.read_parquet(_BOX)
    b = b.copy()
    b["date"] = pd.to_datetime(b["date"])
    b["fg2m"] = b["fgm"] - b["fg3m"]
    b["fg2a"] = b["fga"] - b["fg3a"]
    daily = b.groupby("date")[["fg2m", "fg2a", "fg3m", "fg3a", "ftm", "fta"]].sum()
    daily = daily.sort_index().cumsum().reset_index()
    return daily


def league_shot_rates_asof(table: pd.DataFrame, target_date) -> Tuple[float, float, float]:
    """(p2, p3, pft) make-rate as of strictly-prior games. Falls back to 0.5/
    0.35/0.75 (rough league norms) only when there is zero prior history
    (first date in the table) so an early-season game still scores."""
    prior = table[table["date"] < target_date]
    if prior.empty:
        return 0.5, 0.35, 0.75
    r = prior.iloc[-1]
    p2 = float(r["fg2m"] / r["fg2a"]) if r["fg2a"] > 0 else 0.5
    p3 = float(r["fg3m"] / r["fg3a"]) if r["fg3a"] > 0 else 0.35
    pft = float(r["ftm"] / r["fta"]) if r["fta"] > 0 else 0.75
    return p2, p3, pft


if __name__ == "__main__":  # pragma: no cover - smoke
    net = build_player_net48_asof()
    print(f"player_net48_asof: {len(net)} rows, non-null={net.notna().sum()}")
    top3_tab = build_top3_fga_table()
    rates_tab = build_league_shot_rate_table()
    print("top3 OKC as of 2026-01-01:",
          top3_fga_by_team(top3_tab, "OKC", pd.Timestamp("2026-01-01")))
    print("league rates as of 2026-01-01:",
          league_shot_rates_asof(rates_tab, pd.Timestamp("2026-01-01")))
