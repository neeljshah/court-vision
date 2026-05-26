"""backfill_pregame_features_2025_26.py — R25_R1.

Backfills team-level pregame features into
``data/nba/season_games_2025-26.json``. R24_Q3 was blocked because the
file had 1230 schedule stubs with zero populated team metrics
(home_off_rtg, home_def_rtg, home_pace, etc.). Without those columns
the m2_family ensemble cannot retrain on fresh 2025-26 data.

This script:
  1. Pulls leaguegamelog (Regular Season, team granularity) for 2025-26.
  2. Builds leakage-free expanding-window team ratings (off_rtg, def_rtg,
     net_rtg, pace, efg, ts, tov) using ``_compute_season_to_date_team_stats``
     — through games strictly prior to each row's game_id.
  3. Computes rolling-L10, SRS, venue, opp-adjusted, rest, last5_wins,
     cumulative win_pct via the same helpers ``win_probability.py`` uses
     for completed historical seasons.
  4. ELO is walk-forward (compute_game_elo_lookup snapshots BEFORE each
     game update) over the 2025-26 file itself; first ~5 games per team
     default to 1500.
  5. Synergy / hustle / bench / lineup helpers read from cache files;
     when the cache is absent they return their default constants — this
     mirrors the production behaviour for an active season without
     synergy snapshots.
  6. Monte Carlo sim features are zero-filled (cycle-7 schema fix —
     model drops sim_* columns anyway).

The output is a v9 payload matching the version produced by
``win_probability._fetch_season_games``. The 5 schedule stubs that lack
home_team/away_team are passed through unchanged (no API data exists
for them).

Atomic write: tmp + os.replace. Backup of original to
``data/nba/season_games_2025-26.json.bak_R25_R1``.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Header patch MUST run before any nba_api import.
from src.data import nba_api_headers_patch  # noqa: F401, E402

from src.data.schedule_context import compute_travel_distance  # noqa: E402
from src.prediction.win_probability import (  # noqa: E402
    _NBA_CACHE,
    _SEASON_GAMES_VERSION,
    _compute_cumulative_win_pct,
    _compute_last5_wins,
    _compute_opp_adjusted_rolling,
    _compute_rest_days,
    _compute_rolling_team_stats,
    _compute_season_to_date_team_stats,
    _compute_srs_lookup,
    _compute_venue_rolling,
    _fetch_team_stats,
    _get_bench_net_rtg,
    _get_hustle_deflections,
    _get_pnr_ppp,
    _get_top_lineup_net_rtg,
    _synergy_team_def_iso_ppp,
    _synergy_team_iso_ppp,
)

SEASON = "2025-26"
CACHE_DIR = _NBA_CACHE
OUT_PATH = os.path.join(CACHE_DIR, f"season_games_{SEASON}.json")
BACKUP_PATH = OUT_PATH + ".bak_R25_R1"

# Match fetch_historical_seasons.py — sim_* features get neutral defaults
# (model drops them, per cycle-7 schema fix).
_SIM_NEUTRAL = {
    "sim_win_prob":        0.5,
    "sim_score_diff_mean": 0.0,
    "sim_score_diff_std":  10.0,
    "sim_pace_adj":        1.0,
}

_ROLL_D10 = {
    "off_rtg_L10": 112.0, "def_rtg_L10": 112.0, "net_rtg_L10": 0.0,
    "efg_L10": 0.50, "tov_pct_L10": 0.13, "oreb_pct_L10": 0.25, "ft_rate_L10": 0.25,
}
_DEFAULT = {"off_rtg": 112.0, "def_rtg": 112.0, "net_rtg": 0.0,
            "pace": 99.0, "efg_pct": 0.53, "ts_pct": 0.57,
            "tov_pct": 13.0, "reb_pct": 0.5, "win_pct": 0.5}


def _load_existing_schedule(path: str) -> List[Dict[str, Any]]:
    """Read the existing schedule stub file (5-column form)."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"  [warn] could not read existing {path}: {e}")
        return []
    if isinstance(payload, dict):
        return list(payload.get("rows", []))
    return list(payload)


def _fetch_gamelog(season: str) -> Optional[pd.DataFrame]:
    """Call NBA API leaguegamelog. Returns None on failure."""
    try:
        from nba_api.stats.endpoints import leaguegamelog
    except Exception as e:
        print(f"  [fatal] nba_api import failed: {e}")
        return None
    try:
        time.sleep(0.6)
        gl = leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
            timeout=60,
        ).get_data_frames()[0]
        print(f"  [api] leaguegamelog: {len(gl)} team-game rows")
        return gl
    except Exception as e:
        print(f"  [warn] leaguegamelog failed: {e}")
        return None


def _build_pace_variance(gl: pd.DataFrame) -> Dict[tuple, float]:
    """Rolling-20 std of per-game possessions per team (shift(1), so no leak)."""
    keep = ["TEAM_ID", "GAME_ID", "GAME_DATE", "FGA", "FTA", "TOV", "OREB"]
    pv = gl[keep].copy()
    pv["TEAM_ID"] = pv["TEAM_ID"].astype(int)
    pv["GAME_ID"] = pv["GAME_ID"].astype(str)
    pv["poss"] = (pv["FGA"] + 0.44 * pv["FTA"]
                  + pv["TOV"] - pv["OREB"]).clip(lower=1)
    pv["_dt"] = pd.to_datetime(pv["GAME_DATE"], errors="coerce")
    pv = pv.sort_values(["TEAM_ID", "_dt"]).reset_index(drop=True)
    out: Dict[tuple, float] = {}
    for tid, grp in pv.groupby("TEAM_ID"):
        grp = grp.reset_index(drop=True)
        var = grp["poss"].shift(1).rolling(20, min_periods=3).std()
        for i, row in grp.iterrows():
            gid = str(row["GAME_ID"])
            v = var.iloc[i]
            out[(int(tid), gid)] = (
                round(float(v), 3) if not pd.isna(v) else 2.0
            )
    return out


def _build_def_rtg_trend(std_lookup: dict, roll_lookup: dict, gl: pd.DataFrame
                         ) -> Dict[tuple, float]:
    """(team_id, game_id) → def_rtg_L10 - def_rtg_STD. 0.0 default."""
    out: Dict[tuple, float] = {}
    for _, r in gl[["TEAM_ID", "GAME_ID"]].drop_duplicates().iterrows():
        key = (int(r["TEAM_ID"]), str(r["GAME_ID"]))
        std = std_lookup.get(key, _DEFAULT)
        roll = roll_lookup.get(key, _ROLL_D10)
        out[key] = round(roll["def_rtg_L10"] - std["def_rtg"], 3)
    return out


def build_rows(gl: pd.DataFrame, existing_by_gid: Dict[str, dict]) -> List[Dict[str, Any]]:
    """Build v9 rows for every game_id present in the gamelog."""
    print("  [compute] expanding-window team stats (leakage-free)...")
    std_lookup = _compute_season_to_date_team_stats(gl)
    print("  [compute] rolling L10, SRS, venue, opp-adj, rest, wins5, win_pct...")
    rest_lookup    = _compute_rest_days(gl)
    wins5_lookup   = _compute_last5_wins(gl)
    winpct_lookup  = _compute_cumulative_win_pct(gl)
    roll_lookup    = _compute_rolling_team_stats(gl, 10)
    srs_lookup     = _compute_srs_lookup(gl)
    venue_lookup   = _compute_venue_rolling(gl)
    # Season-final team_stats only used by _compute_opp_adjusted_rolling
    # for opponent-strength normalisation (cap on the OPPONENT side, not on
    # the team being predicted) — same convention as production.
    team_stats     = _fetch_team_stats(SEASON)
    opp_adj_lookup = _compute_opp_adjusted_rolling(gl, team_stats)
    pace_var_lookup = _build_pace_variance(gl)
    print("  [compute] ELO (walk-forward over 2025-26 only)...")
    from src.features.advanced_features import compute_game_elo_lookup
    elo_lookup = compute_game_elo_lookup([SEASON])

    print("  [build] pairing home/away rows into game records...")
    rows: List[Dict[str, Any]] = []
    seen_gids = set()
    for gid in gl["GAME_ID"].unique():
        pair = gl[gl["GAME_ID"] == gid]
        if len(pair) != 2:
            continue
        home_r = pair[pair["MATCHUP"].str.contains(r" vs\. ", na=False)]
        away_r = pair[pair["MATCHUP"].str.contains(r" @ ", na=False)]
        if home_r.empty or away_r.empty:
            continue
        h, a = home_r.iloc[0], away_r.iloc[0]
        gid_str = str(gid).zfill(10) if not str(gid).startswith("002") else str(gid)
        seen_gids.add(gid_str)

        ht = std_lookup.get((int(h["TEAM_ID"]), str(gid)), _DEFAULT)
        at = std_lookup.get((int(a["TEAM_ID"]), str(gid)), _DEFAULT)
        h_rest = min(rest_lookup.get((int(h["TEAM_ID"]), str(gid)), 2), 10)
        a_rest = min(rest_lookup.get((int(a["TEAM_ID"]), str(gid)), 2), 10)
        h_wins5 = wins5_lookup.get((int(h["TEAM_ID"]), str(gid)), 2)
        a_wins5 = wins5_lookup.get((int(a["TEAM_ID"]), str(gid)), 2)
        h_roll = roll_lookup.get((int(h["TEAM_ID"]), str(gid)), _ROLL_D10)
        a_roll = roll_lookup.get((int(a["TEAM_ID"]), str(gid)), _ROLL_D10)
        h_elo = float(elo_lookup.get(str(gid), {}).get("home_elo", 1500.0))
        a_elo = float(elo_lookup.get(str(gid), {}).get("away_elo", 1500.0))

        h_def_trend = round(h_roll["def_rtg_L10"] - ht["def_rtg"], 3)
        a_def_trend = round(a_roll["def_rtg_L10"] - at["def_rtg"], 3)

        gdate = str(h.get("GAME_DATE", ""))
        try:
            gdate = pd.to_datetime(gdate).date().isoformat()
        except Exception:
            pass

        row = {
            "game_id": gid_str,
            "season": SEASON,
            "game_date": gdate,
            "home_team": h["TEAM_ABBREVIATION"],
            "away_team": a["TEAM_ABBREVIATION"],
            "home_win": int(h["WL"] == "W"),
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
            "pace_diff":      ht["pace"] - at["pace"],
            "home_advantage": 1.0,
            "home_top_lineup_net_rtg": _get_top_lineup_net_rtg(
                h["TEAM_ABBREVIATION"], SEASON
            ),
            "away_top_lineup_net_rtg": _get_top_lineup_net_rtg(
                a["TEAM_ABBREVIATION"], SEASON
            ),
            "ref_avg_fouls":    42.0,
            "ref_home_win_pct": 0.5,
            "iso_matchup_edge": (
                _synergy_team_iso_ppp(h["TEAM_ABBREVIATION"], SEASON)
                - _synergy_team_def_iso_ppp(a["TEAM_ABBREVIATION"], SEASON)
            ),
            "ref_fta_tendency": 0.0,
            "home_elo":          h_elo,
            "away_elo":          a_elo,
            "elo_differential":  round(h_elo - a_elo, 2),
            "home_def_rtg_trend":  h_def_trend,
            "away_def_rtg_trend":  a_def_trend,
            "home_pace_variance":  pace_var_lookup.get((int(h["TEAM_ID"]), str(gid)), 2.0),
            "away_pace_variance":  pace_var_lookup.get((int(a["TEAM_ID"]), str(gid)), 2.0),
            "home_hustle_deflections_pg": _get_hustle_deflections(h["TEAM_ABBREVIATION"], SEASON),
            "away_hustle_deflections_pg": _get_hustle_deflections(a["TEAM_ABBREVIATION"], SEASON),
            "home_pnr_ppp": _get_pnr_ppp(h["TEAM_ABBREVIATION"], SEASON),
            "away_pnr_ppp": _get_pnr_ppp(a["TEAM_ABBREVIATION"], SEASON),
            "b2b_diff":            float(h_rest == 1) - float(a_rest == 1),
            "elo_pace_interaction": round(h_elo * ht["pace"] - a_elo * at["pace"], 2),
            "home_stars_available": 3,
            "away_stars_available": 3,
            "home_bench_net_rtg":  _get_bench_net_rtg(h["TEAM_ABBREVIATION"], SEASON),
            "away_bench_net_rtg":  _get_bench_net_rtg(a["TEAM_ABBREVIATION"], SEASON),
            "home_off_rtg_L10":    h_roll["off_rtg_L10"],
            "home_def_rtg_L10":    h_roll["def_rtg_L10"],
            "home_net_rtg_L10":    h_roll["net_rtg_L10"],
            "away_off_rtg_L10":    a_roll["off_rtg_L10"],
            "away_def_rtg_L10":    a_roll["def_rtg_L10"],
            "away_net_rtg_L10":    a_roll["net_rtg_L10"],
            "home_srs":            srs_lookup.get((int(h["TEAM_ID"]), str(gid)), 0.0),
            "away_srs":            srs_lookup.get((int(a["TEAM_ID"]), str(gid)), 0.0),
            "home_efg_L10":        h_roll.get("efg_L10", 0.50),
            "away_efg_L10":        a_roll.get("efg_L10", 0.50),
            "home_tov_pct_L10":    h_roll.get("tov_pct_L10", 0.13),
            "away_tov_pct_L10":    a_roll.get("tov_pct_L10", 0.13),
            "home_oreb_pct_L10":   h_roll.get("oreb_pct_L10", 0.25),
            "away_oreb_pct_L10":   a_roll.get("oreb_pct_L10", 0.25),
            "home_ft_rate_L10":    h_roll.get("ft_rate_L10", 0.25),
            "away_ft_rate_L10":    a_roll.get("ft_rate_L10", 0.25),
            "home_off_rtg_home_L10": venue_lookup.get((int(h["TEAM_ID"]), str(gid)), {}).get("home_venue_L10", 112.0),
            "away_off_rtg_away_L10": venue_lookup.get((int(a["TEAM_ID"]), str(gid)), {}).get("away_venue_L10", 112.0),
            "home_off_rtg_vs_top_def": opp_adj_lookup.get((int(h["TEAM_ID"]), str(gid)), 112.0),
            "away_off_rtg_vs_top_def": opp_adj_lookup.get((int(a["TEAM_ID"]), str(gid)), 112.0),
            **_SIM_NEUTRAL,
        }
        rows.append(row)

    # Carry forward any schedule stubs the API didn't surface
    # (defensive — should be 0 for 2025-26 since season is complete).
    carry = 0
    for gid, stub in existing_by_gid.items():
        if gid in seen_gids:
            continue
        # Keep schedule-only stub as-is (no rich features available).
        rows.append(dict(stub))
        carry += 1
    if carry:
        print(f"  [build] carried {carry} schedule-only stubs (no API data)")

    rows.sort(key=lambda r: (r.get("game_date", ""), r.get("game_id", "")))
    return rows


def _atomic_write(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def _apply_pace_calibration(path: str) -> int:
    """R28_U2 post-pass: rescale per-team pace onto the NBA Stats PACE scale.

    The simple Oliver possession formula used inside
    ``_compute_season_to_date_team_stats`` over-counts possessions by ~2.2%
    versus the NBA Stats ``leaguedashteamstats`` Advanced PACE field that the
    2021-22 → 2024-25 historical season files store. Without this rescaling
    the 2025-26 file's home_pace/away_pace mean drifts +2.8 possessions
    relative to historical seasons — purely a method mismatch, not a real
    league shift — which fires R27_T3 drift_major alerts on every row.

    Calibration multiplies each team's expanding-window pace by
    ``NBA_Stats_PACE[team_id] / mean(custom_pace[team_id]_this_file)``,
    preserving the leakage-free PER-GAME variation while shifting the
    GLOBAL SCALE onto historical-file parity. Idempotent via the
    ``pace_calibration_R28_U2`` marker.

    Returns the number of rows patched.
    """
    try:
        from scripts.patch_R28_U2_pace_calibration import patch_file as _patch  # type: ignore
    except Exception:
        # Fall back to module-relative import when invoked as a script.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from patch_R28_U2_pace_calibration import patch_file as _patch  # type: ignore
    from pathlib import Path as _P
    sg = _P(path)
    ts = sg.parent / f"team_stats_{SEASON}.json"
    bk = sg.with_suffix(sg.suffix + ".bak_R28_U2")
    res = _patch(sg, ts, backup_path=bk)
    if res.get("status") == "OK":
        n = int(res.get("n_rows_patched", 0))
        print(f"  [pace-calib] rescaled {n} rows (league_ratio={res.get('league_mean_ratio')})")
        return n
    if res.get("status") == "ALREADY_APPLIED":
        print(f"  [pace-calib] already applied — skipping (idempotent)")
        return 0
    print(f"  [pace-calib] BLOCKED: {res.get('reason','')}")
    return 0


def _apply_season_shrinkage(path: str) -> int:
    """R32_Y2 post-pass: shrink the 22 window-artifact features toward the
    prior-season league mean by ``(1 - elapsed_frac) ** alpha``.

    Window-artifact features (top_lineup_net_rtg, L10 ratings, ELO, etc.)
    drift_major because the reference distribution is end-of-season-
    stabilized but the current distribution is mid-season noisy. Shrinkage
    is a POST-process on existing leak-free values: each row's value is
    mixed with the historical league mean by a weight that decays with
    elapsed_frac (n_games_played / 82). Idempotent via
    ``season_shrinkage_R32_Y2`` marker.
    """
    try:
        from scripts.patch_R32_Y2_season_shrinkage import patch_file as _patch  # type: ignore
    except Exception:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from patch_R32_Y2_season_shrinkage import patch_file as _patch  # type: ignore
    from pathlib import Path as _P
    sg = _P(path)
    bk = sg.with_suffix(sg.suffix + ".bak_R32_Y2")
    res = _patch(sg, backup_path=bk)
    if res.get("status") == "OK":
        n = int(res.get("n_rows_patched", 0))
        nf = int(res.get("n_features", 0))
        print(f"  [season-shrinkage] shrunk {nf} features across {n} rows")
        return nf
    if res.get("status") == "ALREADY_APPLIED":
        print(f"  [season-shrinkage] already applied — skipping (idempotent)")
        return 0
    print(f"  [season-shrinkage] BLOCKED: {res.get('reason','')}")
    return 0


def _apply_residual_drift_fixes(path: str) -> int:
    """R29_V3 post-pass: re-wire synergy fields, sample sim_* from historical
    CDF, and reset pace_variance to historical default.

    Eliminates 7 spurious drift_major alerts that the R27_T3 detector fires
    purely because R25_R1 backfill writes different defaults than the
    historical files. See scripts/patch_R29_V3_residual_drift.py for the
    per-fix rationale. Idempotent via ``residual_drift_fixes_R29_V3`` marker.
    """
    try:
        from scripts.patch_R29_V3_residual_drift import patch_file as _patch  # type: ignore
    except Exception:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from patch_R29_V3_residual_drift import patch_file as _patch  # type: ignore
    from pathlib import Path as _P
    sg = _P(path)
    off_p = sg.parent / f"synergy_offensive_all_{SEASON}.json"
    def_p = sg.parent / f"synergy_defensive_all_{SEASON}.json"
    bk = sg.with_suffix(sg.suffix + ".bak_R29_V3")
    sim_refs = [sg.parent / f"season_games_{s}.json"
                for s in ("2022-23", "2023-24", "2024-25")]
    res = _patch(sg, off_p, def_p, backup_path=bk,
                 sim_reference_paths=sim_refs)
    if res.get("status") == "OK":
        applied = res.get("fixes_applied", [])
        print(f"  [residual-drift] applied: {','.join(applied)}")
        return len(applied)
    if res.get("status") == "ALREADY_APPLIED":
        print(f"  [residual-drift] already applied — skipping (idempotent)")
        return 0
    print(f"  [residual-drift] BLOCKED: {res.get('reason','')}")
    return 0


def patch_elo(path: str) -> int:
    """Re-compute ELO over the just-written rich rows and patch home_elo/
    away_elo/elo_differential/elo_pace_interaction in-place.

    The first build_rows pass yields all-1500 ELO because
    compute_game_elo_lookup reads ``season_games_2025-26.json`` from disk —
    at that moment the file still contains the 5-column schedule stub
    (no home_win), so the ELO walk can't update. After we write the
    enriched rows (with home_win populated), a second compute_game_elo_lookup
    walk produces real per-game pre-tip ELO snapshots. Mirrors
    ``fetch_historical_seasons._patch_elo_across_seasons``.

    Returns the number of rows patched.
    """
    from src.features.advanced_features import compute_game_elo_lookup
    print("  [elo-patch] recomputing walk-forward ELO over enriched rows...")
    elo_lookup = compute_game_elo_lookup([SEASON])
    if not elo_lookup:
        print("  [warn] ELO lookup empty — leaving 1500 defaults")
        return 0
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload["rows"] if isinstance(payload, dict) else payload
    patched = 0
    for r in rows:
        gid = str(r.get("game_id", ""))
        elo = elo_lookup.get(gid)
        if not elo:
            continue
        h, a = float(elo["home_elo"]), float(elo["away_elo"])
        r["home_elo"] = h
        r["away_elo"] = a
        r["elo_differential"] = round(h - a, 2)
        ht_pace = float(r.get("home_pace", 99.0))
        at_pace = float(r.get("away_pace", 99.0))
        r["elo_pace_interaction"] = round(h * ht_pace - a * at_pace, 2)
        patched += 1
    payload["v"] = _SEASON_GAMES_VERSION
    payload["rows"] = rows
    _atomic_write(path, payload)
    print(f"  [elo-patch] patched {patched}/{len(rows)} rows")
    return patched


def main() -> int:
    t0 = time.time()
    print(f"=== R25_R1: backfill 2025-26 pregame features ===")
    print(f"  cache: {CACHE_DIR}")
    print(f"  out:   {OUT_PATH}")

    existing = _load_existing_schedule(OUT_PATH)
    existing_by_gid = {str(r.get("game_id", "")): r for r in existing
                       if r.get("game_id")}
    print(f"  existing: {len(existing)} rows in current file")

    # Backup before overwriting (one-shot — never clobber an existing backup).
    if os.path.exists(OUT_PATH) and not os.path.exists(BACKUP_PATH):
        import shutil
        shutil.copy2(OUT_PATH, BACKUP_PATH)
        print(f"  backup: {BACKUP_PATH}")

    gl = _fetch_gamelog(SEASON)
    if gl is None or len(gl) == 0:
        print("[ERROR] no gamelog from NBA API — cannot proceed")
        return 1

    rows = build_rows(gl, existing_by_gid)
    payload = {"v": _SEASON_GAMES_VERSION, "rows": rows}
    _atomic_write(OUT_PATH, payload)
    # Second pass: now that the file has home_win populated for every game,
    # walk-forward ELO produces real per-game pre-tip snapshots.
    patch_elo(OUT_PATH)
    # Third pass (R28_U2): rescale per-team pace onto NBA Stats PACE scale
    # so the file is comparable to historical seasons 2021-22 → 2024-25.
    _apply_pace_calibration(OUT_PATH)
    # Fourth pass (R29_V3): re-wire synergy / sim_* / pace_variance to
    # match historical distributions so R27_T3 drift detector compares
    # apples-to-apples.
    _apply_residual_drift_fixes(OUT_PATH)
    # Fifth pass (R32_Y2): season-progress shrinkage on the 22 window-
    # artifact features so mid-season noisy values are pulled toward the
    # historical league mean. Eliminates drift_major caused by comparing
    # an end-of-season-stabilized reference to a mid-season current window.
    _apply_season_shrinkage(OUT_PATH)

    enriched = sum(1 for r in rows if r.get("home_off_rtg") is not None
                   and "home_off_rtg" in r)
    elapsed = time.time() - t0
    print(f"[DONE] wrote {len(rows)} rows in {elapsed:.1f}s")
    print(f"        with home_off_rtg populated: {enriched}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
