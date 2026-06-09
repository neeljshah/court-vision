"""
mc_to_predictions_cache.py — wire the Game-7 possession Monte Carlo to the
CourtVision betting page.

What it does (idempotent, re-runnable nightly):
  1. Runs the possession Monte Carlo via src.simulation.game_simulator.GameSimulator,
     reusing run_possession_sim_game7_v3.py's CALIBRATED recipe:
        - per-player blended seed (0.5*season + 0.5*playoff-series) that pins
          means to the season/playoff seed  (build_blended_seed / _load_player_seed patch)
        - v3 usage-aware empirical assist attribution (assist_rates.json)
        - per-player pts calibration factor (seed_pts / raw_sim_mean) so the
          displayed pts distribution is anchored to the seed mean, not the raw
          (slightly low) possession-sim mean.
  2. Writes data/cache/predictions_cache_<date>.parquet in the PAGE schema
        (long: player_id, player_name, team, is_home, stat, q10, q50, q90, sigma)
     so api/courtvision_router._build_box_score picks it up.
  3. Writes data/cache/cv_fix/mc_distributions_<date>.json per the CONTRACT:
        {player_name_lower: {stat: {mean, sigma, p10, p50, p90}}}
     Engine computes P(over line) = 1 - Phi((line-mean)/sigma).

Usage:
    python scripts/mc_to_predictions_cache.py [DATE] [GID]
        DATE default 2026-05-30,  GID default 0042500317 (Game 7 OKC vs SAS)

Teams / home-away / rosters resolve from data/cache/games_lookup.json by GID;
if the GID isn't present (or has no rosters), we fall back to the hard-coded
v3 Game-7 lineups so tonight always works.

Every external read/sim step is wrapped with a graceful fallback so a single
bad input never crashes the nightly job (production betting code).
"""
from __future__ import annotations
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Defaults (tonight) ────────────────────────────────────────────────────────
DEFAULT_DATE = "2026-05-30"
DEFAULT_GID = "0042500317"          # WCF Game 7, SAS @ OKC, OKC home
N_SIMS = 10_000
BOX_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
CALIB_FACTOR = 1.1702               # v2/v3 team-pts calibration (used as a fallback)


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(name).lower()).strip()


# ── Reuse run_possession_sim_game7_v3.py wholesale via importlib ──────────────
# Importing the v3 module patches _sim_module._load_player_seed with the
# calibrated blended seed and runs the sim at import time, exposing `result`,
# `build_blended_seed`, the v3 assist recompute, lineups and display map.
def _load_v3():
    """Import the v3 runner module (executes the calibrated sim once).

    Returns the module on success, or None on any failure (caller falls back
    to a self-contained sim path)."""
    try:
        spec = importlib.util.spec_from_file_location(
            "_g7v3_runner", ROOT / "scripts" / "run_possession_sim_game7_v3.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[warn] could not import v3 runner ({exc}); using standalone sim")
        return None


# ── Roster / team resolution ──────────────────────────────────────────────────
def resolve_matchup(date: str, gid: str, v3):
    """Return (home_abbr, away_abbr, home_lineup, away_lineup, display_map).

    Prefers games_lookup.json for team abbreviations; rosters come from the v3
    module (Game-7 lineups) which is what we have calibrated seeds for. For an
    arbitrary future GID with no v3 lineups, we still emit what we can."""
    home_abbr, away_abbr = "HOME", "AWAY"
    try:
        gl = json.load(open(ROOT / "data" / "cache" / "games_lookup.json"))
        ent = gl.get(gid) or {}
        home_abbr = (ent.get("home_abbr") or home_abbr).upper()
        away_abbr = (ent.get("away_abbr") or away_abbr).upper()
    except Exception as exc:
        print(f"[warn] games_lookup read failed ({exc}); using v3 defaults OKC/SAS")
        home_abbr, away_abbr = "OKC", "SAS"

    if v3 is not None:
        return (home_abbr, away_abbr,
                list(v3.OKC_LINEUP), list(v3.SAS_LINEUP), dict(v3.PLAYER_DISPLAY))
    return home_abbr, away_abbr, [], [], {}


# ── Distribution helpers ──────────────────────────────────────────────────────
def _dist(arr: np.ndarray) -> dict:
    """Quantiles + sigma for one stat array."""
    a = np.asarray(arr, dtype=float)
    mean = float(np.mean(a))
    sigma = float(np.std(a))
    return {
        "mean": round(mean, 4),
        "sigma": round(sigma, 4),
        "p10": round(float(np.percentile(a, 10)), 4),
        "p50": round(float(np.median(a)), 4),
        "p90": round(float(np.percentile(a, 90)), 4),
    }


def _per_player_pts_calib(pid: str, raw_mean: float, v3) -> float:
    """seed_pts / raw_sim_pts_mean — anchors displayed pts to the calibrated
    seed mean (matches v3's ppcf). Falls back to CALIB_FACTOR."""
    if v3 is None or raw_mean < 0.5:
        return CALIB_FACTOR
    try:
        seed_pts = float(v3.build_blended_seed(pid)["pts"])
        if seed_pts <= 0:
            return CALIB_FACTOR
        return seed_pts / raw_mean
    except Exception:
        return CALIB_FACTOR


def build_player_distributions(result, lineup, display_map, v3):
    """{pid: {"name":..., stats:{stat: {mean,sigma,p10,p50,p90}}}} with the
    per-player pts calibration applied to the pts channel only (the seed already
    pins reb/ast/etc. means via the blended seed + v3 assist model)."""
    out = {}
    for pid in lineup:
        ps = result.player_stats.get(pid, {})
        if not ps:
            continue
        # pts calibration factor for this player
        raw_pts = ps.get("pts")
        f = 1.0
        if raw_pts is not None and len(raw_pts):
            f = _per_player_pts_calib(pid, float(np.mean(raw_pts)), v3)
        stats = {}
        for stat in BOX_STATS:
            arr = ps.get(stat)
            if arr is None or len(arr) == 0:
                continue
            a = np.asarray(arr, dtype=float)
            if stat == "pts":
                a = a * f
            stats[stat] = _dist(a)
        out[pid] = {"name": display_map.get(pid, pid), "stats": stats, "pts_calib": round(f, 4)}
    return out


# ── Writers ───────────────────────────────────────────────────────────────────
def write_predictions_cache(date, home_abbr, away_abbr, home_dists, away_dists):
    """Long-format parquet in the page schema consumed by _build_box_score."""
    now = datetime.now(timezone.utc).isoformat()
    rows = []

    def add(dists, team, is_home):
        for pid, info in dists.items():
            for stat, d in info["stats"].items():
                try:
                    pid_int = int(pid)
                except Exception:
                    pid_int = 0
                rows.append({
                    "player_id": pid_int,
                    "player_name": info["name"],
                    "team": team,
                    "is_home": bool(is_home),
                    "stat": stat,
                    "q10": d["p10"],
                    "q50": d["p50"],
                    "q90": d["p90"],
                    "sigma": d["sigma"],
                    "computed_at": now,
                })

    add(home_dists, home_abbr, True)
    add(away_dists, away_abbr, False)

    df = pd.DataFrame(rows, columns=[
        "player_id", "player_name", "team", "is_home", "stat",
        "q10", "q50", "q90", "sigma", "computed_at",
    ])
    out = ROOT / "data" / "cache" / f"predictions_cache_{date}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out, df


def write_mc_distributions(date, home_dists, away_dists):
    """CONTRACT artifact: {player_name_lower: {stat: {mean,sigma,p10,p50,p90}}}."""
    payload = {}
    for dists in (home_dists, away_dists):
        for pid, info in dists.items():
            key = _norm_name(info["name"])
            if not key:
                continue
            payload[key] = {
                stat: {
                    "mean": d["mean"], "sigma": d["sigma"],
                    "p10": d["p10"], "p50": d["p50"], "p90": d["p90"],
                }
                for stat, d in info["stats"].items()
            }
    out = ROOT / "data" / "cache" / "cv_fix" / f"mc_distributions_{date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(payload, open(out, "w"), indent=2)
    return out, payload


# ── Prop check vs posted lines ────────────────────────────────────────────────
def _phi(x):
    from math import erf, sqrt
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def load_lines(date):
    """Read tonight's player-prop lines (prefer FD, fall back to DK)."""
    for book in ("fd", "dk"):
        p = ROOT / "data" / "lines" / f"{date}_{book}.csv"
        if p.exists():
            try:
                # on_bad_lines='skip': line CSVs occasionally contain an
                # unquoted comma in a player name ("Jaxson Hayes, Jr." etc.)
                # which would otherwise abort the whole read.
                df = pd.read_csv(p, on_bad_lines="skip")
                df["_name"] = df["player_name"].map(_norm_name)
                # Line CSVs accumulate multiple captures per (player, stat);
                # keep the latest capture so the report isn't dominated by dups.
                if "captured_at" in df.columns:
                    df = df.sort_values("captured_at").drop_duplicates(
                        subset=["_name", "stat"], keep="last")
                return book, df
            except Exception:
                continue
    return None, None


def p_over_from_dist(d, line):
    """1 - Phi((line-mean)/sigma)."""
    sigma = max(float(d.get("sigma", 0.0)), 1e-6)
    return 1.0 - _phi((float(line) - float(d["mean"])) / sigma)


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DATE
    gid = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_GID
    print(f"=== mc_to_predictions_cache  date={date}  gid={gid} ===")

    v3 = _load_v3()
    if v3 is None:
        print("[fatal] v3 runner unavailable; cannot produce calibrated sim. Aborting.")
        return 1

    result = v3.result  # already simulated at import (calibrated seeds + v3 assists)
    home_abbr, away_abbr, home_lineup, away_lineup, display_map = resolve_matchup(date, gid, v3)
    print(f"matchup: {away_abbr} @ {home_abbr}  (home={home_abbr})")

    home_dists = build_player_distributions(result, home_lineup, display_map, v3)
    away_dists = build_player_distributions(result, away_lineup, display_map, v3)

    pq_path, df = write_predictions_cache(date, home_abbr, away_abbr, home_dists, away_dists)
    json_path, payload = write_mc_distributions(date, home_dists, away_dists)

    print(f"\nWROTE parquet: {pq_path}  ({len(df)} rows, "
          f"{df['player_id'].nunique()} players)")
    print(f"WROTE json:    {json_path}  ({len(payload)} players)")

    # ── Report key players ────────────────────────────────────────────────────
    KEY = {
        "shai gilgeousalexander": "SGA",
        "victor wembanyama": "Wemby",
        "chet holmgren": "Holmgren",
        "deaaron fox": "Fox",
        "stephon castle": "Castle",
    }
    all_dists = {**home_dists, **away_dists}
    by_name = {_norm_name(i["name"]): i for i in all_dists.values()}
    print("\n=== KEY PLAYER pts / reb / ast distributions (mean [p10,p50,p90]) ===")
    for nkey, short in KEY.items():
        info = by_name.get(nkey)
        if not info:
            print(f"  {short:10s}  (not in lineup)")
            continue
        parts = []
        for stat in ("pts", "reb", "ast"):
            d = info["stats"].get(stat)
            if d:
                parts.append(f"{stat} {d['mean']:.1f} [{d['p10']:.1f},{d['p50']:.1f},{d['p90']:.1f}]")
        print(f"  {short:10s}  " + "  ".join(parts))

    # ── Prop p_over vs posted lines ───────────────────────────────────────────
    book, lines = load_lines(date)
    if lines is not None:
        print(f"\n=== sample prop p_over vs posted lines (book={book}) ===")
        shown = 0
        for nkey, short in KEY.items():
            info = by_name.get(nkey)
            if not info:
                continue
            sub = lines[lines["_name"] == nkey]
            for _, lr in sub.iterrows():
                stat = str(lr["stat"]).lower()
                d = info["stats"].get(stat)
                if d is None:
                    continue
                line = float(lr["line"])
                po = p_over_from_dist(d, line)
                print(f"  {short:10s} {stat:4s} line {line:5.1f}  "
                      f"mean {d['mean']:5.1f}  p_over {po:.3f}  "
                      f"(over {lr.get('over_price','')}/under {lr.get('under_price','')})")
                shown += 1
                if shown >= 18:
                    break
            if shown >= 18:
                break
    else:
        print(f"\n[info] no lines CSV found for {date}; skipped prop p_over report")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
