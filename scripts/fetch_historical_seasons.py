"""fetch_historical_seasons.py — fast cache build for past NBA seasons.

The production `_fetch_season_games` runs a 1000-iteration Monte Carlo per
matchup inline, which makes each fresh-cache fetch take 15-30 minutes.
Since the WinProb model drops sim_* features anyway (cache predates Phase 8
columns, see cycle-7 schema fix), that compute is pure waste during a bulk
historical fetch.

This script:
  1. Patches nba_api headers (required for stats.nba.com to respond).
  2. Pulls leaguegamelog + leaguedashteamstats Advanced + Base for each
     requested season.
  3. Builds rows using the SAME row schema as the production fetcher,
     EXCEPT sim_* features are zero-filled (model drops them anyway).
  4. Writes `data/nba/season_games_<season>.json` with v8 schema (same
     version the production trainer expects).
  5. Skips seasons that already have a v8 cache present.

Run:
    python scripts/fetch_historical_seasons.py 2018-19 2019-20 2020-21 2021-22
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Header patch must run before any nba_api imports.
from src.data import nba_api_headers_patch  # noqa: F401, E402

from src.data.schedule_context import compute_travel_distance  # noqa: E402
from src.prediction.win_probability import (  # noqa: E402
    _NBA_CACHE,
    _SEASON_GAMES_VERSION,
    _synergy_team_iso_ppp,
    _synergy_team_def_iso_ppp,
    _get_pnr_ppp,
    _compute_rest_days,
    _compute_last5_wins,
    _compute_cumulative_win_pct,
    _compute_rolling_team_stats,
    _compute_srs_lookup,
    _compute_venue_rolling,
    _compute_opp_adjusted_rolling,
    _get_top_lineup_net_rtg,
    _get_hustle_deflections,
    _get_bench_net_rtg,
    _fetch_team_stats,
)

# Sim features default to neutral values when not computed. Model drops them
# anyway (cycle-7 schema fix), but we include them so the row shape matches v8.
_SIM_NEUTRAL = {
    "sim_win_prob":        0.5,
    "sim_score_diff_mean": 0.0,
    "sim_score_diff_std":  10.0,
    "sim_pace_adj":        1.0,
}


def _load_stars_available(season: str) -> dict:
    """Read stars_available_{season}.json if present.

    Returns dict mapping game_id (str) -> {team_abbreviation: int_count}.
    Empty dict if not available; row builder falls back to 3 (full strength).
    """
    path = os.path.join(_NBA_CACHE, f"stars_available_{season}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _load_ref_data(season: str):
    """Read officials + ref_stats caches if present.

    Returns (officials_per_game, ref_stats):
      officials_per_game: {game_id: [ref_name, ...]}
      ref_stats: {ref_name: {games_officiated, home_win_rate, avg_total_fouls, avg_total_fta}}
    Both empty dicts if caches not built yet — row builder falls back to
    league-average defaults.
    """
    off_path = os.path.join(_NBA_CACHE, "officials", f"officials_{season}.json")
    stats_path = os.path.join(_NBA_CACHE, "officials", f"ref_stats_{season}.json")
    officials = {}
    ref_stats = {}
    if os.path.exists(off_path):
        try:
            with open(off_path) as f:
                officials = json.load(f) or {}
        except Exception:
            pass
    if os.path.exists(stats_path):
        try:
            with open(stats_path) as f:
                ref_stats = json.load(f) or {}
        except Exception:
            pass
    return officials, ref_stats


def _crew_avg(refs: list, ref_stats: dict, field: str, default: float) -> float:
    """Mean of `field` across the refs in the crew that have stats. Falls
    back to `default` when nobody has data."""
    vals = []
    for r in refs or []:
        s = ref_stats.get(r)
        if s and field in s:
            vals.append(float(s[field]))
    if not vals:
        return default
    return round(sum(vals) / len(vals), 4)


def _fetch_one_season(season: str) -> int:
    """Fetch one season, build rows (no sim Monte Carlo), persist cache.

    Returns the number of rows written, or 0 on failure / skip.
    """
    cache_path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                payload = json.load(f)
            if isinstance(payload, dict) and payload.get("v") == _SEASON_GAMES_VERSION:
                rows = payload.get("rows", [])
                if rows:
                    print(f"  [skip] {season}: v{_SEASON_GAMES_VERSION} cache "
                          f"already present ({len(rows)} games)")
                    return 0
        except Exception:
            pass  # fall through to refetch

    print(f"  fetching leaguegamelog {season}...", flush=True)
    from nba_api.stats.endpoints import leaguegamelog
    time.sleep(0.6)
    try:
        gl = leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [ERROR] gamelog {season}: {e}")
        return 0
    print(f"  got {len(gl)} team-game rows for {season}", flush=True)

    print(f"  fetching team_stats {season}...", flush=True)
    team_stats = _fetch_team_stats(season)
    print(f"  got {len(team_stats)} team stats for {season}", flush=True)

    from src.features.advanced_features import compute_game_elo_lookup
    rest_lookup    = _compute_rest_days(gl)
    wins5_lookup   = _compute_last5_wins(gl)
    winpct_lookup  = _compute_cumulative_win_pct(gl)
    try:
        elo_lookup = compute_game_elo_lookup([season])
    except Exception as e:
        print(f"  [warn] elo_lookup for {season} failed: {e} — using 1500 defaults")
        elo_lookup = {}
    roll_lookup    = _compute_rolling_team_stats(gl, 10)
    srs_lookup     = _compute_srs_lookup(gl)
    venue_lookup   = _compute_venue_rolling(gl)
    opp_adj_lookup = _compute_opp_adjusted_rolling(gl, team_stats)

    # Pace variance: rolling-20-game std of per-game possessions per team.
    # Replaces the constant 2.0 default; gives the model real signal on
    # team-level pace volatility (high-variance teams swing more).
    _pv = gl[["TEAM_ID", "GAME_ID", "GAME_DATE",
              "FGA", "FTA", "TOV", "OREB"]].copy()
    _pv["TEAM_ID"] = _pv["TEAM_ID"].astype(int)
    _pv["GAME_ID"] = _pv["GAME_ID"].astype(str)
    _pv["poss"] = (_pv["FGA"] + 0.44 * _pv["FTA"]
                   + _pv["TOV"] - _pv["OREB"]).clip(lower=1)
    _pv["_dt"] = pd.to_datetime(_pv["GAME_DATE"], errors="coerce")
    _pv = _pv.sort_values(["TEAM_ID", "_dt"]).reset_index(drop=True)
    stars_available_lookup = _load_stars_available(season)
    officials_per_game, ref_stats = _load_ref_data(season)
    pace_var_lookup: dict = {}
    for _tid, _grp in _pv.groupby("TEAM_ID"):
        _grp = _grp.reset_index(drop=True)
        _var = _grp["poss"].shift(1).rolling(20, min_periods=3).std()
        for _i, _row in _grp.iterrows():
            _gid = str(_row["GAME_ID"])
            _v = _var.iloc[_i]
            pace_var_lookup[(int(_tid), _gid)] = (
                round(float(_v), 3) if not pd.isna(_v) else 2.0
            )
    _ROLL_D10 = {
        "off_rtg_L10": 112.0, "def_rtg_L10": 112.0, "net_rtg_L10": 0.0,
        "efg_L10": 0.50, "tov_pct_L10": 0.13, "oreb_pct_L10": 0.25, "ft_rate_L10": 0.25,
    }
    _DEFAULT = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
                "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57,
                "tov_pct": 13.0, "reb_pct": 0.5, "win_pct": 0.5}

    rows = []
    for gid in gl["GAME_ID"].unique():
        pair = gl[gl["GAME_ID"] == gid]
        if len(pair) != 2:
            continue
        home_r = pair[pair["MATCHUP"].str.contains(r" vs\. ", na=False)]
        away_r = pair[pair["MATCHUP"].str.contains(r" @ ",    na=False)]
        if home_r.empty or away_r.empty:
            continue
        h, a   = home_r.iloc[0], away_r.iloc[0]
        ht     = team_stats.get(int(h["TEAM_ID"]), _DEFAULT)
        at     = team_stats.get(int(a["TEAM_ID"]), _DEFAULT)
        h_rest  = min(rest_lookup.get((int(h["TEAM_ID"]), str(gid)), 2), 10)
        a_rest  = min(rest_lookup.get((int(a["TEAM_ID"]), str(gid)), 2), 10)
        h_wins5 = wins5_lookup.get((int(h["TEAM_ID"]), str(gid)), 2)
        a_wins5 = wins5_lookup.get((int(a["TEAM_ID"]), str(gid)), 2)
        h_roll  = roll_lookup.get((int(h["TEAM_ID"]), str(gid)), _ROLL_D10)
        a_roll  = roll_lookup.get((int(a["TEAM_ID"]), str(gid)), _ROLL_D10)
        rows.append({
            "game_id": gid, "season": season,
            "game_date": str(h.get("GAME_DATE", "")),
            "home_team": h["TEAM_ABBREVIATION"], "away_team": a["TEAM_ABBREVIATION"],
            "home_win":  int(h["WL"] == "W"),
            "home_off_rtg":        ht["off_rtg"],
            "home_def_rtg":        ht["def_rtg"],
            "home_net_rtg":        ht["net_rtg"],
            "home_pace":           ht["pace"],
            "home_efg_pct":        ht["efg_pct"],
            "home_ts_pct":         ht["ts_pct"],
            "home_tov_pct":        ht["tov_pct"],
            "home_rest_days":      float(h_rest),
            "home_back_to_back":   float(h_rest == 1),
            "home_travel_miles":   0.0,
            "home_last5_wins":     float(h_wins5),
            "home_season_win_pct": winpct_lookup.get((int(h["TEAM_ID"]), str(gid)), 0.5),
            "away_off_rtg":        at["off_rtg"],
            "away_def_rtg":        at["def_rtg"],
            "away_net_rtg":        at["net_rtg"],
            "away_pace":           at["pace"],
            "away_efg_pct":        at["efg_pct"],
            "away_ts_pct":         at["ts_pct"],
            "away_tov_pct":        at["tov_pct"],
            "away_rest_days":      float(a_rest),
            "away_back_to_back":   float(a_rest == 1),
            "away_travel_miles":   compute_travel_distance(
                a["TEAM_ABBREVIATION"], h["TEAM_ABBREVIATION"]
            ),
            "away_last5_wins":     float(a_wins5),
            "away_season_win_pct": winpct_lookup.get((int(a["TEAM_ID"]), str(gid)), 0.5),
            "net_rtg_diff":   h_roll["net_rtg_L10"] - a_roll["net_rtg_L10"],
            "pace_diff":      ht["pace"]    - at["pace"],
            "home_advantage": 1.0,
            "home_top_lineup_net_rtg": _get_top_lineup_net_rtg(h["TEAM_ABBREVIATION"], season),
            "away_top_lineup_net_rtg": _get_top_lineup_net_rtg(a["TEAM_ABBREVIATION"], season),
            # Ref crew tendencies — mean of the 3 refs' historical stats.
            # Falls back to league averages when no ref data for the crew.
            "ref_avg_fouls":    _crew_avg(officials_per_game.get(str(gid), []),
                                          ref_stats, "avg_total_fouls", 42.0),
            "ref_home_win_pct": _crew_avg(officials_per_game.get(str(gid), []),
                                          ref_stats, "home_win_rate", 0.5),
            "iso_matchup_edge": (
                _synergy_team_iso_ppp(h["TEAM_ABBREVIATION"], season)
                - _synergy_team_def_iso_ppp(a["TEAM_ABBREVIATION"], season)
            ),
            "ref_fta_tendency": _crew_avg(officials_per_game.get(str(gid), []),
                                          ref_stats, "avg_total_fta", 0.0),
            "home_elo":          elo_lookup.get(str(gid), {}).get("home_elo", 1500.0),
            "away_elo":          elo_lookup.get(str(gid), {}).get("away_elo", 1500.0),
            "elo_differential":  (
                elo_lookup.get(str(gid), {}).get("home_elo", 1500.0)
                - elo_lookup.get(str(gid), {}).get("away_elo", 1500.0)
            ),
            # Defensive form trend: recent (L10) minus season baseline.
            # Positive means defense is currently worse than season average.
            "home_def_rtg_trend":  round(h_roll["def_rtg_L10"] - ht["def_rtg"], 3),
            "away_def_rtg_trend":  round(a_roll["def_rtg_L10"] - at["def_rtg"], 3),
            "home_pace_variance":  pace_var_lookup.get((int(h["TEAM_ID"]), str(gid)), 2.0),
            "away_pace_variance":  pace_var_lookup.get((int(a["TEAM_ID"]), str(gid)), 2.0),
            "home_hustle_deflections_pg": _get_hustle_deflections(h["TEAM_ABBREVIATION"], season),
            "away_hustle_deflections_pg": _get_hustle_deflections(a["TEAM_ABBREVIATION"], season),
            "home_pnr_ppp": _get_pnr_ppp(h["TEAM_ABBREVIATION"], season),
            "away_pnr_ppp": _get_pnr_ppp(a["TEAM_ABBREVIATION"], season),
            "b2b_diff":            float(h_rest == 1) - float(a_rest == 1),
            "elo_pace_interaction": (
                elo_lookup.get(str(gid), {}).get("home_elo", 1500.0) * ht["pace"]
                - elo_lookup.get(str(gid), {}).get("away_elo", 1500.0) * at["pace"]
            ),
            # Historical injury proxy: count of top-8-by-minutes players on
            # the team who actually appeared in this specific game. Built by
            # scripts/fetch_historical_injuries.py. Falls back to 8 (full
            # strength) if no cache.
            "home_stars_available": int(stars_available_lookup.get(str(gid), {}).get(
                h["TEAM_ABBREVIATION"], 8)),
            "away_stars_available": int(stars_available_lookup.get(str(gid), {}).get(
                a["TEAM_ABBREVIATION"], 8)),
            "home_bench_net_rtg":  _get_bench_net_rtg(h["TEAM_ABBREVIATION"], season),
            "away_bench_net_rtg":  _get_bench_net_rtg(a["TEAM_ABBREVIATION"], season),
            "home_off_rtg_L10":    h_roll["off_rtg_L10"],
            "home_def_rtg_L10":    h_roll["def_rtg_L10"],
            "home_net_rtg_L10":    h_roll["net_rtg_L10"],
            "away_off_rtg_L10":    a_roll["off_rtg_L10"],
            "away_def_rtg_L10":    a_roll["def_rtg_L10"],
            "away_net_rtg_L10":    a_roll["net_rtg_L10"],
            "home_srs":            srs_lookup.get((int(h["TEAM_ID"]), str(gid)), 0.0),
            "away_srs":            srs_lookup.get((int(a["TEAM_ID"]), str(gid)), 0.0),
            "home_efg_L10":        h_roll.get("efg_L10",      0.50),
            "away_efg_L10":        a_roll.get("efg_L10",      0.50),
            "home_tov_pct_L10":    h_roll.get("tov_pct_L10",  0.13),
            "away_tov_pct_L10":    a_roll.get("tov_pct_L10",  0.13),
            "home_oreb_pct_L10":   h_roll.get("oreb_pct_L10", 0.25),
            "away_oreb_pct_L10":   a_roll.get("oreb_pct_L10", 0.25),
            "home_ft_rate_L10":    h_roll.get("ft_rate_L10",  0.25),
            "away_ft_rate_L10":    a_roll.get("ft_rate_L10",  0.25),
            "home_off_rtg_home_L10": venue_lookup.get((int(h["TEAM_ID"]), str(gid)), {}).get("home_venue_L10", 112.0),
            "away_off_rtg_away_L10": venue_lookup.get((int(a["TEAM_ID"]), str(gid)), {}).get("away_venue_L10", 112.0),
            "home_off_rtg_vs_top_def": opp_adj_lookup.get((int(h["TEAM_ID"]), str(gid)), 112.0),
            "away_off_rtg_vs_top_def": opp_adj_lookup.get((int(a["TEAM_ID"]), str(gid)), 112.0),
            # Sim features zero-filled (model drops them anyway, per cycle-7 schema fix).
            **_SIM_NEUTRAL,
        })

    with open(cache_path, "w") as f:
        json.dump({"v": _SEASON_GAMES_VERSION, "rows": rows}, f)
    print(f"  wrote {len(rows)} rows -> {cache_path}", flush=True)
    return len(rows)


def _patch_elo_across_seasons(seasons: List[str]) -> None:
    """Re-compute ELO across all seasons jointly, patch each cache file.

    The first pass of _fetch_one_season writes 1500-defaulted ELO because
    `compute_game_elo_lookup` reads `season_games_*.json` files — which
    don't exist until the first pass writes them. This second pass closes
    the chicken-and-egg loop: with all caches present, compute the true
    cross-season ELO trajectory, then patch home_elo/away_elo/
    elo_differential/elo_pace_interaction in-place per row.
    """
    from src.features.advanced_features import compute_game_elo_lookup
    print("[elo-patch] computing ELO across all seasons jointly...", flush=True)
    elo_lookup = compute_game_elo_lookup(seasons)
    print(f"  got {len(elo_lookup)} ELO snapshots", flush=True)
    if not elo_lookup:
        print("  [warn] empty ELO lookup — leaving caches with 1500 defaults")
        return

    for s in seasons:
        path = os.path.join(_NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            payload = json.load(f)
        rows = payload["rows"] if isinstance(payload, dict) else payload
        patched = 0
        for r in rows:
            gid = str(r.get("game_id", ""))
            elo = elo_lookup.get(gid)
            if not elo:
                continue
            h, a = float(elo["home_elo"]), float(elo["away_elo"])
            r["home_elo"]         = h
            r["away_elo"]         = a
            r["elo_differential"] = round(h - a, 2)
            # Keep elo_pace_interaction consistent.
            ht_pace = float(r.get("home_pace", 99.0))
            at_pace = float(r.get("away_pace", 99.0))
            r["elo_pace_interaction"] = round(h * ht_pace - a * at_pace, 2)
            patched += 1
        with open(path, "w") as f:
            json.dump({"v": _SEASON_GAMES_VERSION, "rows": rows}, f)
        print(f"  patched {patched}/{len(rows)} rows in {s}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("seasons", nargs="+",
                    help="Seasons to fetch, e.g. 2018-19 2019-20")
    args = ap.parse_args()

    print(f"Fast historical-season fetcher (no Monte Carlo)")
    print(f"Cache version v{_SEASON_GAMES_VERSION}, seasons: {args.seasons}\n")
    total = 0
    for s in args.seasons:
        print(f"=== {s} ===", flush=True)
        t0 = time.time()
        n = _fetch_one_season(s)
        elapsed = time.time() - t0
        print(f"  {s}: {n} rows in {elapsed:.1f}s\n", flush=True)
        total += n
    # Now that all season caches exist, recompute ELO jointly and patch rows.
    _patch_elo_across_seasons(args.seasons)
    print(f"DONE — {total} total rows across {len(args.seasons)} seasons")


if __name__ == "__main__":
    main()
