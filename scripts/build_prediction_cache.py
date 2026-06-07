"""build_prediction_cache.py — precompute RAW q10/q50/q90 for every active
player at game-day start so live ranking serves predictions in <100ms.

R16_E3. The slow path (`scripts/predict_player.py`) re-builds the feature row
+ runs 7-stat × 4-model inference per call (~10-30s/player). For live ranking
across the slate we need O(milliseconds) — so this script writes a parquet
that the serving helper (`scripts/serve_prediction.py`) memory-maps.

Output schema (`data/cache/predictions_cache_<isodate>.parquet`):

    player_id   int64
    player_name str
    team        str
    stat        str        # one of STATS (pts, reb, ast, fg3m, stl, blk, tov)
    q10         float64    # RAW — BEFORE injury_availability dampener
    q50         float64    # RAW
    q90         float64    # RAW
    sigma       float64    # (q90 - q10) / 2.563 — Gaussian σ proxy
    computed_at str        # iso8601 UTC timestamp

Active-player set:
    1. Iterate ALL gamelog files in data/nba/gamelog_<pid>_<season>.json
       — every player with a cached season log is a candidate.
    2. Skip players whose latest game is >14 days old (off-team / inactive).
    3. Skip players the model can't predict (missing features / no history).

The injury_availability dampener is INTENTIONALLY NOT applied here — it
is applied at serve time (`get_prediction(..., apply_injury=True)`) so the
cache stays valid across multiple injury-snapshot refreshes per day.

Usage:
    python scripts/build_prediction_cache.py
    python scripts/build_prediction_cache.py --season 2025-26 --max 200
    python scripts/build_prediction_cache.py --opp BOS --rest 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, date as _date, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Bypass live ESPN scraping during the bulk build — we cache RAW predictions
# and apply the dampener at serve time.
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_prediction_row, predict_pergame, _MIN_PLAYED, _num,
    _parse_date,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    predict_pergame_quantiles,
)


_NBA_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")


def _detect_current_season() -> str:
    """NBA season string for today's date — same rule as predict_player.py."""
    now = datetime.now()
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _normalize_gamelog_in_place(games: list) -> None:
    """Some gamelog cache files use lowercase keys (game_date / min / matchup);
    the predict path requires uppercase (GAME_DATE / MIN / MATCHUP / PTS / ...).
    This patches each row in place so build_prediction_row accepts it.

    Non-destructive: if the row already has uppercase keys we leave them
    alone. Lowercase variants are copied to their uppercase equivalents.
    """
    upper_keys = {
        "GAME_DATE", "MIN", "MATCHUP", "PTS", "REB", "AST",
        "FG3M", "STL", "BLK", "TOV", "FGM", "FGA", "FG_PCT",
        "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT", "OREB", "DREB",
        "PF", "PLUS_MINUS", "WL", "GAME_ID", "PLAYER_ID",
    }
    for row in games:
        if not isinstance(row, dict):
            continue
        for k in list(row.keys()):
            uk = k.upper()
            if uk != k and uk in upper_keys and uk not in row:
                row[uk] = row[k]


def _iter_active_players(
    season: str,
    *,
    max_age_days: int = 500,
    limit: Optional[int] = None,
) -> List[Tuple[int, str, datetime]]:
    """Return [(player_id, team_abbrev_from_latest_matchup, latest_date), ...].

    Players whose latest game is >max_age_days old are dropped — keeps the
    cache tight (no inactive/off-team players blowing up the parquet).
    """
    out: List[Tuple[int, str, datetime]] = []
    if not os.path.isdir(_NBA_CACHE_DIR):
        return out
    today = datetime.now()
    suffix = f"_{season}.json"
    for fname in sorted(os.listdir(_NBA_CACHE_DIR)):
        if not fname.startswith("gamelog_") or not fname.endswith(suffix):
            continue
        try:
            pid = int(fname[len("gamelog_"): -len(suffix)])
        except ValueError:
            continue
        path = os.path.join(_NBA_CACHE_DIR, fname)
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or not games:
            continue
        # Handle the lowercase-key variant of the gamelog cache.
        _normalize_gamelog_in_place(games)
        dated = [
            (d, g) for g in games
            if (d := _parse_date(g.get("GAME_DATE"))) is not None
            and _num(g.get("MIN")) >= _MIN_PLAYED
        ]
        if not dated:
            continue
        dated.sort(key=lambda x: x[0])
        latest_date, latest_game = dated[-1]
        if (today - latest_date).days > max_age_days:
            continue
        # Parse team_abbrev from MATCHUP ("TEAM @ OPP" or "TEAM vs. OPP")
        matchup = str(latest_game.get("MATCHUP", "")).strip()
        team = matchup.split()[0] if matchup else ""
        # Rewrite the normalised gamelog back to disk so build_prediction_row
        # — which re-reads the file directly — sees the uppercase keys.
        try:
            json.dump(games, open(path, "w", encoding="utf-8"))
        except Exception:
            pass
        out.append((pid, team, latest_date))
        if limit and len(out) >= limit:
            break
    return out


def _resolve_player_name(player_id: int) -> str:
    """Look up name via nba_api.stats.static. Cached lookup; safe on miss."""
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
        rec = players.find_player_by_id(int(player_id))
        if rec:
            return rec.get("full_name", "") or ""
    except Exception:
        pass
    return ""


def _predict_one_player(
    player_id: int,
    opp_team: str,
    season: str,
    *,
    is_home: bool,
    rest_days: float,
    model_dir: Optional[str] = None,
) -> Optional[Dict[str, Dict[str, float]]]:
    """Predict q10/q50/q90 for every stat. Returns {stat: {q10, q50, q90}} or None.

    Per-stat None outputs are accepted — they become NaN in the parquet so the
    server can fall back to L5 baselines. The whole-player None is only when
    feature-row construction itself fails (no gamelog / too little history).
    """
    row = build_prediction_row(
        player_id, opp_team, season,
        is_home=is_home, rest_days=rest_days, gamelog_dir=_NBA_CACHE_DIR,
    )
    if row is None:
        return None
    out: Dict[str, Dict[str, float]] = {}
    for stat in STATS:
        # q50 point estimate via the production stack
        q50_point = predict_pergame(stat, row, model_dir)
        # q10 / q90 via the quantile heads. NOTE: player_id is NOT passed so
        # the injury dampener is NOT applied — we want RAW values in cache.
        qint = predict_pergame_quantiles(stat, row, model_dir) or {}
        q10 = float(qint["q10"]) if qint.get("q10") is not None else float("nan")
        q50 = (float(q50_point) if q50_point is not None
               else (float(qint["q50"]) if qint.get("q50") is not None
                     else float("nan")))
        q90 = float(qint["q90"]) if qint.get("q90") is not None else float("nan")
        # Enforce monotonicity: q10 <= q50 <= q90.  Mirrors the clamp in
        # live_quantile_bands.bands_for() so the cache is never persisted with
        # crossed intervals (e.g. q90 < q50 on star BLK rows).
        if not np.isnan(q10) and not np.isnan(q50):
            q10 = min(q10, q50)
        if not np.isnan(q90) and not np.isnan(q50):
            q90 = max(q90, q50)
        out[stat] = {"q10": q10, "q50": q50, "q90": q90}
    return out


def build_cache(
    *,
    season: Optional[str] = None,
    opp_team: str = "OPP",
    is_home: bool = True,
    rest_days: float = 2.0,
    max_players: Optional[int] = None,
    max_age_days: int = 500,
    out_path: Optional[str] = None,
    model_dir: Optional[str] = None,
    verbose: bool = True,
) -> Tuple[str, int]:
    """Build the prediction cache parquet. Returns (out_path, n_rows)."""
    season = season or _detect_current_season()
    today_iso = _date.today().isoformat()
    if out_path is None:
        out_path = os.path.join(_CACHE_DIR, f"predictions_cache_{today_iso}.parquet")

    os.makedirs(_CACHE_DIR, exist_ok=True)
    candidates = _iter_active_players(season, max_age_days=max_age_days,
                                       limit=max_players)
    if verbose:
        print(f"[build] {len(candidates)} candidate players (season={season})")

    computed_at = datetime.now(timezone.utc).isoformat()
    rows: List[dict] = []
    t0 = time.perf_counter()
    n_predicted = 0
    n_skipped = 0
    for i, (pid, team, _latest) in enumerate(candidates):
        # NOTE: opp_team here is a placeholder ("OPP" by default). The cache
        # is matchup-AGNOSTIC — opponent-specific adjustments are applied at
        # serve time if needed, but for the live-ranker hot path we accept
        # the small accuracy loss for ~100x latency win.
        preds = _predict_one_player(
            pid, opp_team, season,
            is_home=is_home, rest_days=rest_days, model_dir=model_dir,
        )
        if preds is None:
            n_skipped += 1
            continue
        name = _resolve_player_name(pid)
        for stat, qd in preds.items():
            sigma_proxy = float("nan")
            if not (np.isnan(qd["q10"]) or np.isnan(qd["q90"])):
                # (q90 - q10) / 2 × 1.2816 → σ for Gaussian — / 2.5631
                sigma_proxy = (qd["q90"] - qd["q10"]) / 2.5631
            rows.append({
                "player_id":   int(pid),
                "player_name": name,
                "team":        team,
                "stat":        stat,
                "q10":         qd["q10"],
                "q50":         qd["q50"],
                "q90":         qd["q90"],
                "sigma":       sigma_proxy,
                "computed_at": computed_at,
            })
        n_predicted += 1
        if verbose and (i + 1) % 50 == 0:
            rate = (i + 1) / max(1e-9, time.perf_counter() - t0)
            print(f"  [{i + 1}/{len(candidates)}]  {rate:.1f} players/s")

    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=[
            "player_id", "player_name", "team", "stat",
            "q10", "q50", "q90", "sigma", "computed_at",
        ])
    df.to_parquet(out_path, index=False)
    elapsed = time.perf_counter() - t0
    if verbose:
        print(f"[build] wrote {len(df)} rows ({n_predicted} players, "
              f"{n_skipped} skipped) → {out_path}  in {elapsed:.1f}s")
    return out_path, len(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None,
                    help="Season override (default: current)")
    ap.add_argument("--opp", default="OPP",
                    help="Placeholder opponent abbrev — cache is matchup-agnostic")
    ap.add_argument("--rest", type=float, default=2.0)
    ap.add_argument("--away", action="store_true",
                    help="Build with is_home=False (default home)")
    ap.add_argument("--max", type=int, default=None,
                    help="Cap number of players (for smoke tests)")
    ap.add_argument("--max-age-days", type=int, default=500,
                    help="Drop players whose latest gamelog row is older "
                         "than this (default 400 — generous in off-season)")
    ap.add_argument("--out", default=None,
                    help="Output parquet path")
    args = ap.parse_args()
    build_cache(
        season=args.season,
        opp_team=args.opp,
        is_home=not args.away,
        rest_days=args.rest,
        max_players=args.max,
        max_age_days=args.max_age_days,
        out_path=args.out,
    )


if __name__ == "__main__":
    main()
