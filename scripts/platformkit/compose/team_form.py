"""team_form -- per team, per game DATE, leak-free (as-of) composed NBA features.

The leak-risk heart of the compose lane. EVERY feature for a game is computed
STRICTLY from that team's games with date < the game's date -- no season-end
value ever conditions a game inside the same season.

As-of discipline, one line per feature:
  off_xpts_ps  : mean shot-quality xPts / shot over the team's STRICTLY-PRIOR
                 games (shot_xpts_2025_26, game-level); weight = n_shots.
  concession_ps: mean OPPONENT xPts / shot the team's defense faced over its
                 STRICTLY-PRIOR games (same game-level source, self-joined).
  net_per48    : minute-weighted stint net rating ((pts_for-pts_against)/sec*2880)
                 over STRICTLY-PRIOR games (stints_2025_26) -- availability-weighted
                 synergy proxy: it uses the lineups that ACTUALLY played.
  rest_diff    : rest_days_home - rest_days_away from games.parquet -- schedule is
                 known pregame, so it is as-of by definition (no aggregation).

Honest skip list (season-END aggregates -- would leak within 2025-26, no prior
season file exists so relevance_gate's prior-season trick is unavailable):
  concession_2025_26.parquet (30 team rows), lineup_spacing / gravity_proxy /
  on_off / lineup_synergy (per-team/lineup season aggregates, no date column).
  We rebuild concession + synergy AS-OF from the game-level sources above instead.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
_GAMES = _REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
_XPTS = _REPO / "data" / "cache" / "team_system" / "composition" / "shot_xpts_2025_26.parquet"
_STINTS = _REPO / "data" / "cache" / "team_system" / "lineups" / "stints_2025_26.parquet"
_SEC_PER_48 = 2880.0


def team_id_to_abbr() -> Dict[int, str]:
    """team_id -> abbreviation from nba_api static data (offline, no network)."""
    from nba_api.stats.static import teams as _t  # noqa: PLC0415
    return {int(t["id"]): t["abbreviation"] for t in _t.get_teams()}


def prior_rows(events: pd.DataFrame, target_date, date_col: str = "date") -> pd.DataFrame:
    """The ONLY window a feature may see: rows STRICTLY before target_date.

    Any caller that hands in the current/future game's date gets those rows
    excluded here -- the as-of guarantee is enforced in this one function so a
    feature literally cannot be built from date >= game date (see leak test)."""
    return events[events[date_col] < target_date]


def _asof_weighted_mean(long: pd.DataFrame, val: str, wt: str) -> pd.Series:
    """Strictly-prior weighted mean per (game_id, team), vectorized.

    long has one row per (game_id, team, date, val, wt). A team plays at most
    once per date, so cumulative-minus-current over date-sorted rows == the
    aggregate of STRICTLY-earlier games. Index: (game_id, team)."""
    d = long.sort_values(["team", "date"]).copy()
    vw = d[val] * d[wt]
    cum_vw = vw.groupby(d["team"]).cumsum()
    cum_w = d[wt].groupby(d["team"]).cumsum()
    prior_vw = cum_vw - vw
    prior_w = cum_w - d[wt]
    out = np.where(prior_w > 0, prior_vw / prior_w.replace(0, np.nan), np.nan)
    return pd.Series(out, index=pd.MultiIndex.from_arrays([d["game_id"], d["team"]]))


def _asof_net_per48(long: pd.DataFrame) -> pd.Series:
    """Strictly-prior minute-weighted net rating per (game_id, team).

    Ratio-of-sums (not mean-of-ratios): accumulate pts_for/against/seconds
    separately over prior games, then form net/48. Index: (game_id, team)."""
    d = long.sort_values(["team", "date"]).copy()
    for c in ("pf", "pa", "sec"):
        d["cum_" + c] = d[c].groupby(d["team"]).cumsum() - d[c]
    net = (d["cum_pf"] - d["cum_pa"]) / d["cum_sec"].replace(0, np.nan) * _SEC_PER_48
    return pd.Series(net.to_numpy(),
                     index=pd.MultiIndex.from_arrays([d["game_id"], d["team"]]))


def _xpts_long(games: pd.DataFrame, abbr: Dict[int, str]) -> pd.DataFrame:
    """One row per (game_id, team) with off value + concession value, dated."""
    x = pd.read_parquet(_XPTS)[["game_id", "team_id", "xpts", "n_shots"]].copy()
    x["team"] = x["team_id"].map(abbr)
    gm = games[["game_id", "date", "home_team", "away_team"]]
    x = x.merge(gm, on="game_id", how="inner")
    x = x[x["team"].notna()].copy()
    x["opp"] = np.where(x["team"] == x["home_team"], x["away_team"], x["home_team"])
    x["off_val"] = x["xpts"] / x["n_shots"].replace(0, np.nan)
    # concession = the OPPONENT's off value in the same game (opp offense vs my D)
    opp = x[["game_id", "team", "off_val", "n_shots"]].rename(
        columns={"team": "opp", "off_val": "conc_val", "n_shots": "opp_shots"})
    x = x.merge(opp, on=["game_id", "opp"], how="left")
    return x[["game_id", "team", "date", "off_val", "n_shots", "conc_val", "opp_shots"]]


def _stint_long(games: pd.DataFrame, abbr: Dict[int, str]) -> pd.DataFrame:
    """One row per (game_id, team) with pts_for/against/seconds, dated."""
    s = pd.read_parquet(_STINTS)[["game_id", "team_id", "pts_for", "pts_against",
                                  "elapsed_s"]].copy()
    s["team"] = s["team_id"].map(abbr)
    s = s[s["team"].notna()]
    agg = s.groupby(["game_id", "team"], as_index=False).agg(
        pf=("pts_for", "sum"), pa=("pts_against", "sum"), sec=("elapsed_s", "sum"))
    return agg.merge(games[["game_id", "date"]], on="game_id", how="inner")


def build_team_form(season: str = "2025-26",
                    games_path: Optional[Path] = None) -> pd.DataFrame:
    """Per-game home/away AS-OF raw features for `season`, date-ordered.

    Returns one row per game with: game_id, date, home_team, away_team, home_win,
    off_home/off_away, conc_home/conc_away, net_home/net_away, rest_diff.
    Raw (un-standardized); challenger.py standardizes on the train prefix only.
    """
    games = pd.read_parquet(games_path or _GAMES)
    games["date"] = pd.to_datetime(games["date"])
    abbr = team_id_to_abbr()

    xl = _xpts_long(games, abbr)
    off = _asof_weighted_mean(
        xl.rename(columns={"off_val": "v", "n_shots": "w"}), "v", "w")
    conc = _asof_weighted_mean(
        xl.dropna(subset=["conc_val"]).rename(columns={"conc_val": "v", "opp_shots": "w"}),
        "v", "w")
    net = _asof_net_per48(_stint_long(games, abbr))

    ev = games[games["season"].astype(str) == season].copy()
    ev = ev.sort_values(["date", "game_id"]).reset_index(drop=True)

    def look(series: pd.Series, gid: str, team: str) -> float:
        return float(series.get((gid, team), np.nan))

    def num(x) -> float:  # NaN-safe (schedule gaps -> 0 rest diff, not NaN)
        return 0.0 if pd.isna(x) else float(x)

    rows = []
    for r in ev.itertuples(index=False):
        gid, h, a = r.game_id, r.home_team, r.away_team
        rows.append({
            "game_id": gid, "date": r.date, "home_team": h, "away_team": a,
            "home_win": float(r.home_win),
            "off_home": look(off, gid, h), "off_away": look(off, gid, a),
            "conc_home": look(conc, gid, h), "conc_away": look(conc, gid, a),
            "net_home": look(net, gid, h), "net_away": look(net, gid, a),
            "rest_diff": num(getattr(r, "rest_days_home", 0.0))
            - num(getattr(r, "rest_days_away", 0.0)),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":  # pragma: no cover - smoke
    tf = build_team_form()
    print(f"team_form: {len(tf)} games; non-null off_home={tf['off_home'].notna().sum()}")
    print(tf[["date", "home_team", "away_team", "off_home", "conc_home",
              "net_home", "rest_diff"]].tail(3).to_string(index=False))
