"""probe_pace_q1_proxy.py — Cycle 92f (loop 5) T1-D probe.

Tier-1 in-game-gap research (scripts/_results/in_game_gaps_v1.md lines 37-42):
once Q1 has elapsed, the OBSERVED Q1 pace is a stronger predictor of
full-game pace than the pre-game two-team-pace average. A residual
between observed-Q1-pace and the pre-game pace prior should scale all
volume stats (PTS / REB / AST / TOV) roughly linearly with pace.

This probe builds the SCAFFOLD on the 50-game cycle-91a subset and
auto-scales when cycle 92c's daemon adds more games. The use case
is mid-game (post-Q1) prediction, so we test: "if we had known Q1 actual
pace, how much better could we have predicted full-game volume stats?"
That is OK to test on the existing holdout — we're measuring the value
of a hypothetical live signal, not using future info for pre-game
prediction.

Design (mirrors probe_garbage_time_haircut.py pattern):
1. Build (game_id, team_abbrev) -> team Q1 possessions from
   data/cache/quarter_box/<gid>_q1.json team rows. Possessions formula:
   FGA + 0.44*FTA - OREB + TOV. Q1 pace = possessions * (48/Q1_min).
2. Build (game_id) -> pre-game expected Q1 pace from season_games_*.json
   home_pace + away_pace average / 4 (Q1 share of game).
3. Build (player_id, date) -> (game_id, team_abbrev) lookup from
   quarter_box files. (Gamelog cache has MATCHUP but no game_id.)
4. Attach team_abbrev + game_id to each pergame holdout row by
   (player_id_from_gamelog_filename, date).
5. Compute observed Q1 pace residual z-score per row.
6. Sweep k in {0.05, 0.10, 0.15, 0.20}. Adjust pred *= (1 + k * z).
   Only volume stats (PTS / REB / AST / TOV) get the scaling.
7. Single-split MAE delta + optional walk-forward 4-fold.
8. Relaxed ship gate (per cycle spec): <100 rows -> REJECT data sparse;
   else 0.003 aggregate PTS+REB+AST improvement + 3/4 WF folds.

Run:
    python scripts/probe_pace_q1_proxy.py
    python scripts/probe_pace_q1_proxy.py --skip-wf
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import warnings
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _MIN_PLAYED, _num, _parse_date,
    build_pergame_dataset, feature_columns,
)
from scripts.validate_adjustment import (  # noqa: E402
    _bulk_predict, validate, print_report,
)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_QUARTER_BOX_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

# Volume stats most pace-sensitive (per cycle 89f T1-D research). FG3M / STL
# / BLK aren't scaled — possession-rate stats with much weaker pace
# coupling, and per cycle 89f post-prediction-adjust avoid list.
_VOLUME_STATS = {"pts", "reb", "ast", "tov"}


# ── data loading ─────────────────────────────────────────────────────────────

def _norm_date(s: str) -> str:
    return str(s or "")[:10]


def _parse_min_str(s) -> float:
    """Parse a minutes string like '60:00' or '12:34' or numeric to float minutes."""
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s:
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60.0
        except (ValueError, IndexError):
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def build_quarter_data() -> Tuple[
    Dict[Tuple[str, str], dict],        # (gid, team_abbr) -> Q1 team stats
    Dict[Tuple[int, str], Tuple[str, str]],  # (pid, date) -> (gid, team_abbr)
    Dict[str, str],                     # gid -> date
]:
    """Walk data/cache/quarter_box/<gid>_q1.json files. For each game-team
    pair, compute Q1 possessions and team-min. Also build a
    (player_id, date) -> (game_id, team_abbrev) lookup.

    Possessions = FGA + 0.44*FTA - OREB + TOV (standard formula).
    Pace = possessions * (48 / min_played).  Q1 min_played is ~60 (5 players
    x 12 min) but we read the team `min` field to get exact.
    """
    team_q1: Dict[Tuple[str, str], dict] = {}
    pid_date_to_game: Dict[Tuple[int, str], Tuple[str, str]] = {}
    gid_to_date: Dict[str, str] = {}

    # First, build gid -> date from season_games_*.json (also used for pace
    # prior later).
    for fname in os.listdir(_NBA_CACHE):
        if not fname.startswith("season_games_") or not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_NBA_CACHE, fname), encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        for g in rows or []:
            gid = str(g.get("game_id") or "").zfill(10)
            gdate = _norm_date(g.get("game_date"))
            if gid and gdate:
                gid_to_date[gid] = gdate

    if not os.path.isdir(_QUARTER_BOX_DIR):
        return team_q1, pid_date_to_game, gid_to_date

    for fname in sorted(os.listdir(_QUARTER_BOX_DIR)):
        if not fname.endswith("_q1.json"):
            continue
        path = os.path.join(_QUARTER_BOX_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        gid = str(data.get("game_id") or fname.split("_")[0]).zfill(10)
        gdate = gid_to_date.get(gid)
        # Q1 team stats
        for trow in data.get("teams") or []:
            team_abbr = str(trow.get("team_abbreviation") or "").strip()
            if not team_abbr:
                continue
            fga = float(trow.get("fga") or 0)
            fta = float(trow.get("fta") or 0)
            oreb = float(trow.get("oreb") or 0)
            to = float(trow.get("to") or 0)
            tmin_player = _parse_min_str(trow.get("min"))  # sum of player-min
            poss = fga + 0.44 * fta - oreb + to
            # NBA pace = possessions per 48 CLOCK minutes per team. Team's
            # `min` field is sum of player-min (5 players * clock-min). So
            # clock-min = tmin_player / 5. For a normal Q1: 60 player-min
            # = 12 clock-min, pace = poss * 48/12 = poss * 4.
            clock_min = tmin_player / 5.0
            pace = (poss * 48.0 / clock_min) if clock_min > 0 else float("nan")
            team_q1[(gid, team_abbr)] = {
                "fga": fga, "fta": fta, "oreb": oreb, "to": to,
                "tmin_player": tmin_player, "clock_min": clock_min,
                "poss": poss, "pace": pace,
            }
        # (player_id, date) -> (gid, team_abbr) from Q1 player rows
        if gdate:
            for prow in data.get("players") or []:
                try:
                    pid = int(prow.get("player_id"))
                except (TypeError, ValueError):
                    continue
                team_abbr = str(prow.get("team_abbreviation") or "").strip()
                if not team_abbr:
                    continue
                pid_date_to_game[(pid, gdate)] = (gid, team_abbr)

    return team_q1, pid_date_to_game, gid_to_date


def build_pace_prior() -> Dict[str, Tuple[float, float, str, str]]:
    """gid -> (home_pace, away_pace, home_team, away_team) from season_games.

    Average of home_pace and away_pace is the standard pre-game pace prior
    (rotogrinders convention). We divide by 4 later to get Q1-share.
    """
    out: Dict[str, Tuple[float, float, str, str]] = {}
    for fname in os.listdir(_NBA_CACHE):
        if not fname.startswith("season_games_") or not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(_NBA_CACHE, fname), encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        for g in rows or []:
            gid = str(g.get("game_id") or "").zfill(10)
            hp = g.get("home_pace")
            ap = g.get("away_pace")
            ht = str(g.get("home_team") or "").strip()
            at = str(g.get("away_team") or "").strip()
            if gid and hp is not None and ap is not None and ht and at:
                try:
                    out[gid] = (float(hp), float(ap), ht, at)
                except (TypeError, ValueError):
                    continue
    return out


# ── attach (game_id, team, q1_pace_residual) to holdout rows ─────────────────

def build_rows_with_q1(min_prior: int = 0) -> Tuple[List[dict], List[str]]:
    """Identical to build_pergame_dataset but attaches _player_id +
    _team_abbrev (from gamelog MATCHUP, by position). The player_id comes
    from the gamelog filename via parallel walk in the same order as
    build_pergame_dataset's glob iteration.
    """
    rows, fc = build_pergame_dataset(min_prior=min_prior)
    print(f"  built {len(rows)} canonical rows; attaching player_id + team_abbrev...",
          flush=True)

    parallel: List[Tuple[str, str, int, int]] = []  # (date_iso, team_abbrev, is_home, pid)
    for path in glob.glob(os.path.join(_NBA_CACHE, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= min_prior:
            continue
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            file_pid = int(parts[1])
        except Exception:
            file_pid = 0
        dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])
        prior_count = 0
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            if played and prior_count >= min_prior:
                matchup = str(game.get("MATCHUP", ""))
                is_home = 1 if " vs. " in matchup else 0
                team_abbrev = matchup.split()[0] if matchup.split() else ""
                parallel.append((gdate.isoformat(), team_abbrev, is_home, file_pid))
            if played:
                prior_count += 1

    if len(parallel) != len(rows):
        print(f"  WARN: parallel walk gave {len(parallel)} entries vs {len(rows)} rows.",
              flush=True)

    n_match = min(len(parallel), len(rows))
    n_ok = 0
    for i in range(n_match):
        if parallel[i][0] == rows[i].get("date") and \
           int(parallel[i][2]) == int(rows[i].get("is_home", 0) or 0):
            rows[i]["_team_abbrev"] = parallel[i][1]
            rows[i]["_player_id"] = parallel[i][3]
            n_ok += 1
        else:
            rows[i]["_team_abbrev"] = ""
            rows[i]["_player_id"] = 0
    for i in range(n_match, len(rows)):
        rows[i]["_team_abbrev"] = ""
        rows[i]["_player_id"] = 0
    print(f"  attached: {n_ok}/{len(rows)} ({100*n_ok/max(1,len(rows)):.1f}%)",
          flush=True)
    return rows, fc


def attach_q1_residual(
    rows: List[dict],
    team_q1: Dict[Tuple[str, str], dict],
    pace_prior: Dict[str, Tuple[float, float, str, str]],
    pid_date_to_game: Dict[Tuple[int, str], Tuple[str, str]],
) -> None:
    """Mutates rows in-place. For each row whose (pid, date) maps to a
    (gid, team_abbrev) with both Q1 pace and pre-game pace prior known,
    set row["_q1_pace_residual"] = observed_q1_pace - expected_q1_pace.

    expected_q1_pace = (home_pace + away_pace) / 2  (Q1 pace is calibrated
    to full-game pace by the *48/tmin factor in team_q1, so we compare
    apples-to-apples on a "possessions per 48 min" basis).
    """
    for r in rows:
        r["_q1_pace_residual"] = None
        r["_q1_pace_obs"] = None
        r["_q1_pace_exp"] = None
        r["_game_id"] = None
    n_attached = 0
    for r in rows:
        pid = r.get("_player_id", 0) or 0
        date = _norm_date(r.get("date", ""))
        if not pid or not date:
            continue
        game_lookup = pid_date_to_game.get((pid, date))
        if game_lookup is None:
            continue
        gid, team_abbr = game_lookup
        r["_game_id"] = gid
        # Override _team_abbrev with the quarter-box-derived one (more reliable)
        if not r.get("_team_abbrev"):
            r["_team_abbrev"] = team_abbr
        q1 = team_q1.get((gid, team_abbr))
        prior = pace_prior.get(gid)
        if q1 is None or prior is None:
            continue
        obs = q1.get("pace")
        if obs is None or (isinstance(obs, float) and math.isnan(obs)):
            continue
        home_pace, away_pace, ht, at = prior
        exp = (float(home_pace) + float(away_pace)) / 2.0
        r["_q1_pace_obs"] = obs
        r["_q1_pace_exp"] = exp
        r["_q1_pace_residual"] = obs - exp
        n_attached += 1
    return n_attached


# ── adjustment factory ───────────────────────────────────────────────────────

def make_q1_pace_adjust(slope_k: float, residual_std: float):
    """Adjust pred for volume stats by (1 + k * z) where z is the z-score
    of the row's Q1 pace residual (normalised by the holdout residual std).

    Skipped for non-volume stats (FG3M / STL / BLK) — see _VOLUME_STATS.
    """
    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        if stat not in _VOLUME_STATS:
            return pred.copy()
        out = pred.copy()
        if residual_std <= 0:
            return out
        for i, r in enumerate(rows):
            resid = r.get("_q1_pace_residual")
            if resid is None:
                continue
            z = float(resid) / residual_std
            out[i] = pred[i] * (1.0 + slope_k * z)
        return np.clip(out, 0.0, None)
    return fn


# ── walk-forward ─────────────────────────────────────────────────────────────

def walk_forward_post_adjust(fn, holdout, X, n_folds=4,
                             stats=("pts", "reb", "ast")):
    n = len(holdout)
    fold_size = n // n_folds
    per_stat: Dict[str, List[float]] = {s: [] for s in stats}
    for fold_i in range(n_folds):
        lo = fold_i * fold_size
        hi = n if fold_i == n_folds - 1 else (fold_i + 1) * fold_size
        sub_rows = holdout[lo:hi]
        sub_X = X[lo:hi]
        for stat in stats:
            y_true = np.array([
                np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
                for r in sub_rows
            ], dtype=float)
            mask = ~np.isnan(y_true)
            pred = _bulk_predict(stat, sub_X)
            if pred is None:
                per_stat[stat].append(float("nan"))
                continue
            adj = fn(pred, sub_rows, stat)
            bm = float(np.mean(np.abs(pred[mask] - y_true[mask])))
            am = float(np.mean(np.abs(adj[mask] - y_true[mask])))
            per_stat[stat].append(am - bm)
    return per_stat


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-wf", action="store_true")
    args = ap.parse_args()

    print("Loading pergame dataset + attaching pid/team...", flush=True)
    rows, _fc = build_rows_with_q1(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)
    cols = feature_columns()
    print(f"  n_total={n_total} features={len(cols)}\n", flush=True)

    print("Building Q1 team data + pace prior from quarter_box + season_games...",
          flush=True)
    team_q1, pid_date_to_game, gid_to_date = build_quarter_data()
    pace_prior = build_pace_prior()
    print(f"  team_q1 entries: {len(team_q1)}  (games covered: {len(team_q1)//2})",
          flush=True)
    print(f"  pid_date_to_game entries: {len(pid_date_to_game)}", flush=True)
    print(f"  pace_prior entries: {len(pace_prior)}\n", flush=True)

    if pid_date_to_game:
        q_dates = sorted({d for (_p, d) in pid_date_to_game.keys()})
        print(f"  Q1 data date range: {q_dates[0]} -> {q_dates[-1]}  "
              f"({len(q_dates)} dates)\n", flush=True)

    # Restrict holdout to dates where Q1 data exists. Without this, the
    # canonical 80/20 split lands entirely in 2025-26 with zero overlap.
    q1_dates = {d for (_p, d) in pid_date_to_game.keys()}
    if q1_dates:
        max_q1 = max(q1_dates)
        min_q1 = min(q1_dates)
        covered_rows = [r for r in rows
                        if min_q1 <= _norm_date(r["date"]) <= max_q1]
    else:
        covered_rows = []
        max_q1 = min_q1 = ""
    print(f"  rows within Q1-coverage window: {len(covered_rows)}/{n_total}\n",
          flush=True)

    if not covered_rows:
        print("  NO ROWS in Q1 coverage window — REJECT data sparse.\n")
        _write_report(0, 0, [], None, [], {}, [], None, "REJECT data sparse",
                      "no rows in coverage window", min_q1, max_q1, len(team_q1)//2)
        return 0

    # 80/20 within the coverage window
    n = len(covered_rows)
    holdout_all = covered_rows[int(n * 0.80):] if n >= 5 else covered_rows
    print(f"  using {len(holdout_all)} holdout rows from window "
          f"({min_q1} -> {max_q1})\n", flush=True)

    # Attach residual
    n_with_q1 = attach_q1_residual(holdout_all, team_q1, pace_prior, pid_date_to_game)
    print(f"  holdout rows with Q1 residual attached: {n_with_q1}/{len(holdout_all)}",
          flush=True)

    # Compute residual distribution
    resids = np.array([r["_q1_pace_residual"] for r in holdout_all
                       if r.get("_q1_pace_residual") is not None], dtype=float)
    if len(resids) == 0:
        residual_std = 1.0
        resid_stats = {"n": 0, "mean": 0.0, "std": 0.0,
                       "p10": 0.0, "p50": 0.0, "p90": 0.0,
                       "min": 0.0, "max": 0.0}
    else:
        residual_std = float(np.std(resids))
        resid_stats = {
            "n": len(resids),
            "mean": float(np.mean(resids)),
            "std": residual_std,
            "p10": float(np.percentile(resids, 10)),
            "p50": float(np.percentile(resids, 50)),
            "p90": float(np.percentile(resids, 90)),
            "min": float(np.min(resids)),
            "max": float(np.max(resids)),
        }
    print(f"  Q1 pace residual: n={resid_stats['n']} mean={resid_stats['mean']:+.3f} "
          f"std={resid_stats['std']:.3f}", flush=True)
    print(f"  pct: p10={resid_stats['p10']:+.2f} p50={resid_stats['p50']:+.2f} "
          f"p90={resid_stats['p90']:+.2f}  range=[{resid_stats['min']:+.2f}, "
          f"{resid_stats['max']:+.2f}]\n", flush=True)

    # SHIP GATE — relaxed for sparse data
    if n_with_q1 < 100:
        print("=" * 78)
        print("SHIP GATE: REJECT — data sparse (<100 holdout rows with Q1 data)")
        print("  Re-run after cycle 92c daemon completes more games.")
        print("=" * 78)
        _write_report(
            n_with_q1, len(holdout_all), [], None,
            [], {}, [], resid_stats,
            "REJECT data sparse",
            f"n_with_q1={n_with_q1} < 100; re-run after cycle 92c daemon completes",
            min_q1, max_q1, len(team_q1)//2,
        )
        return 0

    # Otherwise build feature matrix and sweep
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout_all], dtype=float)

    print("=" * 78)
    print("SINGLE-SPLIT SWEEP — k in {0.05, 0.10, 0.15, 0.20}")
    print("=" * 78)

    k_grid = [0.05, 0.10, 0.15, 0.20]
    results_per_k: List[Dict] = []
    for k in k_grid:
        fn = make_q1_pace_adjust(slope_k=k, residual_std=residual_std)
        results = validate(fn, holdout_all, X)
        name = f"Q1 pace residual adjust k={k:.2f}"
        print_report(name, results)
        target_delta_sum = sum(
            (results.get(s, {}).get("delta_mae") or 0.0)
            for s in ("pts", "reb", "ast")
        )
        n_improved = sum(
            1 for s in STATS
            if (results.get(s, {}).get("delta_mae") or 0.0) < -0.001
        )
        results_per_k.append({
            "k": k, "results": results,
            "target_delta_sum": target_delta_sum,
            "n_improved": n_improved,
        })

    best = min(results_per_k, key=lambda d: d["target_delta_sum"])
    best_k = best["k"]
    print()
    print("=" * 78)
    print(f"BEST SINGLE-SPLIT k: {best_k:.2f}  "
          f"PTS+REB+AST agg delta: {best['target_delta_sum']:+.4f}  "
          f"n_improved: {best['n_improved']}/7")
    print("=" * 78)

    # WF gate (only if SS shows >= 0.003 improvement)
    wf_results: Dict[str, List[float]] = {}
    wf_pass = False
    if not args.skip_wf and best["target_delta_sum"] <= -0.003:
        print()
        print("=" * 78)
        print(f"WALK-FORWARD 4-FOLD (k={best_k:.2f})")
        print("=" * 78)
        best_fn = make_q1_pace_adjust(slope_k=best_k, residual_std=residual_std)
        wf_results = walk_forward_post_adjust(best_fn, holdout_all, X, n_folds=4,
                                              stats=["pts", "reb", "ast"])
        wf_per_stat_pass: Dict[str, bool] = {}
        print(f"  {'stat':<5} {'fold1':>9} {'fold2':>9} {'fold3':>9} {'fold4':>9}  "
              f"{'mean':>9} {'folds<0':>8}")
        for s in ("pts", "reb", "ast"):
            deltas = wf_results.get(s, [])
            mean = np.mean(deltas) if deltas else float("nan")
            n_neg = sum(1 for d in deltas if d < -0.0001)
            wf_per_stat_pass[s] = (n_neg >= 3)
            row = f"  {s:<5} "
            for d in deltas:
                row += f"{d:+9.4f} "
            row += f" {mean:+9.4f} {n_neg}/{len(deltas):>3d}"
            print(row)
        # Pass: 3/4 folds on PTS (the dominant volume stat); REB/AST informational.
        wf_pass = wf_per_stat_pass.get("pts", False)
    elif not args.skip_wf:
        print(f"\nSKIPPING WF — SS aggregate {best['target_delta_sum']:+.4f} "
              f"does not meet relaxed 0.003 bar.\n")

    # Final verdict
    print()
    print("=" * 78)
    print("SHIP GATE")
    print("=" * 78)
    ss_pass = best["target_delta_sum"] <= -0.003
    final = ss_pass and (args.skip_wf or wf_pass)
    if final:
        verdict = "SHIP"
    elif not ss_pass:
        verdict = "REJECT signal"
    else:
        verdict = "REJECT WF"
    print(f"  SS bar (>= 0.003 PTS+REB+AST agg improvement): pass={ss_pass}")
    if not args.skip_wf and ss_pass:
        print(f"  WF bar (PTS 3/4 folds): pass={wf_pass}")
    print(f"  VERDICT: {verdict}")

    _write_report(
        n_with_q1, len(holdout_all), k_grid, best_k,
        results_per_k, wf_results, [], resid_stats,
        verdict, "" if final else "see SS / WF metrics above",
        min_q1, max_q1, len(team_q1)//2,
    )
    return 0


def _write_report(
    n_with_q1: int,
    n_holdout: int,
    k_grid: List[float],
    best_k: Optional[float],
    results_per_k: List[dict],
    wf_results: Dict[str, List[float]],
    _extra: List,
    resid_stats: Optional[dict],
    verdict: str,
    note: str,
    min_date: str,
    max_date: str,
    n_games_q1: int,
) -> None:
    out_path = os.path.join(_RESULTS_DIR, "pace_q1_proxy_v1.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Cycle 92f (loop 5) -- T1-D Q1 pace residual probe (scaffold)\n\n")
        f.write("## Setup\n")
        f.write(f"- Q1 data source: data/player_quarter_stats.parquet "
                f"(cycle 91a; {n_games_q1} games covered, "
                f"{min_date} -> {max_date}).\n")
        f.write(f"- Holdout window restricted to Q1-coverage dates. "
                f"holdout n={n_holdout}, rows with Q1 pace residual "
                f"attached: {n_with_q1}.\n")
        f.write("- Possessions formula: FGA + 0.44*FTA - OREB + TOV "
                "(team-level Q1 box).\n")
        f.write("- Pace = poss * 48 / team_min; expected pre-game pace = "
                "(home_pace + away_pace) / 2 from season_games.\n")
        f.write("- Use-case: mid-game prediction (post-Q1). Probe measures "
                "value of a hypothetical live Q1-pace signal.\n\n")

        if resid_stats:
            f.write("## Residual distribution\n")
            f.write(f"- n: {resid_stats['n']}\n")
            f.write(f"- mean: {resid_stats['mean']:+.3f}, "
                    f"std: {resid_stats['std']:.3f}\n")
            f.write(f"- pct: p10={resid_stats['p10']:+.2f}, "
                    f"p50={resid_stats['p50']:+.2f}, "
                    f"p90={resid_stats['p90']:+.2f}\n")
            f.write(f"- range: [{resid_stats['min']:+.2f}, "
                    f"{resid_stats['max']:+.2f}]\n\n")

        if results_per_k:
            f.write("## k-sweep (single split)\n\n")
            f.write("| k | n_improved | PTS delta | REB delta | AST delta | TOV delta | PTS+REB+AST agg |\n")
            f.write("|---|------------|-----------|-----------|-----------|-----------|-----------------|\n")
            for entry in results_per_k:
                r = entry["results"]
                pd_ = (r.get("pts", {}).get("delta_mae") or 0.0)
                rd_ = (r.get("reb", {}).get("delta_mae") or 0.0)
                ad_ = (r.get("ast", {}).get("delta_mae") or 0.0)
                td_ = (r.get("tov", {}).get("delta_mae") or 0.0)
                f.write(f"| {entry['k']:.2f} | {entry['n_improved']}/7 "
                        f"| {pd_:+.4f} | {rd_:+.4f} | {ad_:+.4f} | {td_:+.4f} "
                        f"| {entry['target_delta_sum']:+.4f} |\n")
            f.write("\n")

        if best_k is not None and wf_results:
            f.write(f"## Walk-forward 4-fold (k={best_k:.2f})\n\n")
            f.write("| stat | fold1 | fold2 | fold3 | fold4 | mean | folds<0 |\n")
            f.write("|------|-------|-------|-------|-------|------|---------|\n")
            for s in ("pts", "reb", "ast"):
                deltas = wf_results.get(s, [])
                mean = np.mean(deltas) if deltas else float("nan")
                n_neg = sum(1 for d in deltas if d < -0.0001)
                f.write(f"| {s} ")
                for d in deltas:
                    f.write(f"| {d:+.4f} ")
                f.write(f"| {mean:+.4f} | {n_neg}/4 |\n")
            f.write("\n")

        f.write("## Verdict\n\n")
        f.write(f"**{verdict}**\n\n")
        if note:
            f.write(f"Note: {note}\n\n")
        f.write("## Auto-scale\n")
        f.write("Probe is gated on data/cache/quarter_box/<gid>_q1.json and "
                "data/player_quarter_stats.parquet. Re-running after cycle 92c "
                "daemon adds more games will automatically widen the holdout "
                "and re-sweep without code changes.\n")
    print(f"\nReport written: {out_path}")


if __name__ == "__main__":
    sys.exit(main())
