"""generate_predictions_20260529.py — Offline predictions for OKC@SAS 2026-05-29.

Bypasses the NBA Scoreboard API (which returns no data for future dates)
and directly calls predict_player_pergame for the known OKC@SAS roster.

Produces:
  data/predictions/2026-05-29.csv        — raw CSV (date, game_id, player_id, ...)
  data/cache/predictions_cache_2026-05-29.parquet — overlay parquet (player_name, stat, q10, q50, q90, sigma)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import warnings
warnings.filterwarnings("ignore", message="X does not have valid feature names")

import src.data.nba_api_headers_patch  # noqa: F401

from src.prediction.prop_pergame import STATS, predict_player_pergame, _MIN_PLAYED, _num

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_PRED_DIR  = os.path.join(PROJECT_DIR, "data", "predictions")
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")

# ── Known OKC@SAS game for 2026-05-29 ────────────────────────────────────────
# Game is WCF (series). SAS is home, OKC is away.
DATE_STR = "2026-05-29"
SEASON   = "2025-26"
GAME_ID  = "0042400315"   # canonical NBA game_id from 2026-05-26 series entry

# Rosters: (player_id, player_name, team_abbrev, is_home)
ROSTER = [
    # OKC (away)
    (1628983, "Shai Gilgeous-Alexander", "OKC", False),
    (1631096, "Chet Holmgren",           "OKC", False),
    (1630198, "Isaiah Joe",              "OKC", False),
    (1630598, "Aaron Wiggins",           "OKC", False),
    (1628392, "Isaiah Hartenstein",      "OKC", False),
    (1641717, "Cason Wallace",           "OKC", False),
    (1629652, "Luguentz Dort",           "OKC", False),
    (1627936, "Alex Caruso",             "OKC", False),
    (1629026, "Kenrich Williams",        "OKC", False),
    (1631114, "Jalen Williams",           "OKC", False),
    (1631119, "Jaylin Williams",         "OKC", False),
    (1642362, "Payton Sandfort",         "OKC", False),
    (1642272, "Jared McCain",            "OKC", False),
    # SAS (home)
    (1641705, "Victor Wembanyama",       "SAS", True),
    (1628368, "De'Aaron Fox",            "SAS", True),
    (1642264, "Stephon Castle",          "SAS", True),
    (1630170, "Devin Vassell",           "SAS", True),
    (1642844, "Dylan Harper",            "SAS", True),
    (1629640, "Keldon Johnson",          "SAS", True),
    (1628436, "Luke Kornet",             "SAS", True),
    (203084,  "Harrison Barnes",         "SAS", True),
    (1630577, "Julian Champagnie",       "SAS", True),
    (1631127, "Harrison Ingram",         "SAS", True),
    (202687,  "Bismack Biyombo",         "SAS", True),
]

# Sigma priors from STAT_SIGMA in courtvision_router.py (MAE * 1.253)
_STAT_SIGMA = {
    "pts": 5.79, "reb": 2.38, "ast": 1.70,
    "fg3m": 1.12, "stl": 0.90, "blk": 0.55, "tov": 1.12,
}


def _normal_quantile(mean: float, sigma: float, p: float) -> float:
    """Approximate normal quantile via erfinv-free formula (fast enough here)."""
    import math
    # Use scipy if available, else Beasley-Springer-Moro approximation
    try:
        from scipy.stats import norm
        return float(norm.ppf(p, loc=mean, scale=sigma))
    except ImportError:
        # Simple approximation good to ±0.01 for p in [0.1, 0.9]
        if p <= 0:
            return 0.0
        if p >= 1:
            return mean + 4 * sigma
        # Rational approximation
        if p < 0.5:
            t = (-2 * math.log(p)) ** 0.5
        else:
            t = (-2 * math.log(1 - p)) ** 0.5
        c = (2.515517 + 0.802853 * t + 0.010328 * t * t)
        d = (1.0 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t)
        z = t - c / d
        if p < 0.5:
            z = -z
        return max(0.0, mean + z * sigma)


def main():
    import csv
    import pandas as pd

    os.makedirs(_PRED_DIR, exist_ok=True)
    os.makedirs(_CACHE_DIR, exist_ok=True)

    csv_path = os.path.join(_PRED_DIR, f"{DATE_STR}.csv")
    parquet_path = os.path.join(_CACHE_DIR, f"predictions_cache_{DATE_STR}.parquet")

    print(f"\nGenerating predictions for OKC @ SAS  date={DATE_STR}  season={SEASON}")
    print(f"Players: {len(ROSTER)}")

    csv_rows = []
    parquet_rows = []
    computed_at = datetime.now(timezone.utc).isoformat()
    n_ok = 0
    n_fail = 0

    for pid, name, team, is_home in ROSTER:
        opp = "SAS" if team == "OKC" else "OKC"
        venue = "home" if is_home else "away"
        try:
            preds = predict_player_pergame(
                pid, opp, SEASON,
                is_home=is_home, rest_days=2.0,
                gamelog_dir=_NBA_CACHE, model_dir=_MODEL_DIR,
            )
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}")
            n_fail += 1
            continue

        if not preds:
            print(f"  [SKIP] {name}: no predictions returned")
            n_fail += 1
            continue

        n_ok += 1
        print(f"  {name:<30} PTS={preds.get('pts', '?'):>5}  REB={preds.get('reb', '?'):>4}  "
              f"AST={preds.get('ast', '?'):>4}  FG3M={preds.get('fg3m', '?'):>3}  "
              f"STL={preds.get('stl', '?'):>3}  BLK={preds.get('blk', '?'):>3}  "
              f"TOV={preds.get('tov', '?'):>4}")

        for stat in STATS:
            v = preds.get(stat)
            if v is None:
                continue
            q50 = float(v)
            sigma = _STAT_SIGMA.get(stat, 2.0)
            q10 = max(0.0, _normal_quantile(q50, sigma, 0.10))
            q90 = max(0.0, _normal_quantile(q50, sigma, 0.90))

            csv_rows.append({
                "date": DATE_STR, "game_id": GAME_ID,
                "player_id": pid, "player": name,
                "team": team, "opp": opp, "venue": venue,
                "stat": stat, "pred": f"{q50:.4f}",
                "lineup_status": "", "lineup_class": "", "play_pct": "", "injury_status": "",
            })
            parquet_rows.append({
                "player_id": pid, "player_name": name, "team": team,
                "stat": stat, "q10": q10, "q50": q50, "q90": q90, "sigma": sigma,
                "computed_at": computed_at,
            })

    # Write CSV
    if csv_rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "date", "game_id", "player_id", "player", "team", "opp", "venue",
                "stat", "pred", "lineup_status", "lineup_class", "play_pct", "injury_status",
            ])
            w.writeheader()
            w.writerows(csv_rows)
        print(f"\n  Wrote {len(csv_rows)} rows → {csv_path}")
    else:
        print("\n  [ERROR] No prediction rows generated!")
        return 1

    # Write parquet
    if parquet_rows:
        df = pd.DataFrame(parquet_rows)
        df.to_parquet(parquet_path, index=False)
        print(f"  Wrote {len(parquet_rows)} rows → {parquet_path}")
    else:
        print("  [ERROR] No parquet rows generated!")
        return 1

    print(f"\n  Summary: {n_ok} players predicted, {n_fail} failed")
    print(f"  Sanity check — SGA PTS: {next((r['pred'] for r in csv_rows if r['player']=='Shai Gilgeous-Alexander' and r['stat']=='pts'), 'not found')}")
    print(f"  Sanity check — Wembanyama PTS: {next((r['pred'] for r in csv_rows if r['player']=='Victor Wembanyama' and r['stat']=='pts'), 'not found')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
