"""generate_predictions_game7.py — Offline predictions for WCF Game 7 SAS @ OKC.

Series 3-3 -> Game 7 at OKC (2-2-1-1-1 -> higher seed hosts G7). OKC home, SAS away.
Mirrors generate_predictions_20260529.py but flips venue.

Writes:
  data/cache/predictions_cache_game7.parquet  (player_name, stat, q10/q50/q90, sigma)
"""
from __future__ import annotations
import os, sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
import warnings
warnings.filterwarnings("ignore", message="X does not have valid feature names")
import src.data.nba_api_headers_patch  # noqa: F401
from src.prediction.prop_pergame import STATS, predict_player_pergame

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")

DATE_STR = "2026-06-01"   # Game 7 label
SEASON = "2025-26"
GAME_ID = "0042500317"

# (player_id, name, team, is_home)  — OKC HOME for Game 7
ROSTER = [
    (1628983, "Shai Gilgeous-Alexander", "OKC", True),
    (1631096, "Chet Holmgren", "OKC", True),
    (1630198, "Isaiah Joe", "OKC", True),
    (1630598, "Aaron Wiggins", "OKC", True),
    (1628392, "Isaiah Hartenstein", "OKC", True),
    (1641717, "Cason Wallace", "OKC", True),
    (1629652, "Luguentz Dort", "OKC", True),
    (1627936, "Alex Caruso", "OKC", True),
    (1629026, "Kenrich Williams", "OKC", True),
    (1631114, "Jalen Williams", "OKC", True),
    (1631119, "Jaylin Williams", "OKC", True),
    (1642272, "Jared McCain", "OKC", True),
    (1641705, "Victor Wembanyama", "SAS", False),
    (1628368, "De'Aaron Fox", "SAS", False),
    (1642264, "Stephon Castle", "SAS", False),
    (1630170, "Devin Vassell", "SAS", False),
    (1642844, "Dylan Harper", "SAS", False),
    (1629640, "Keldon Johnson", "SAS", False),
    (1628436, "Luke Kornet", "SAS", False),
    (203084, "Harrison Barnes", "SAS", False),
    (1630577, "Julian Champagnie", "SAS", False),
    (1631127, "Harrison Ingram", "SAS", False),
    (202687, "Bismack Biyombo", "SAS", False),
]

_STAT_SIGMA = {"pts": 5.79, "reb": 2.38, "ast": 1.70, "fg3m": 1.12, "stl": 0.90, "blk": 0.55, "tov": 1.12}


def _q(mean, sigma, p):
    from scipy.stats import norm
    return max(0.0, float(norm.ppf(p, loc=mean, scale=sigma)))


def main():
    import pandas as pd
    rows = []
    computed_at = datetime.now(timezone.utc).isoformat()
    n_ok = 0
    print(f"\nGame 7  SAS @ OKC  (OKC home)  date={DATE_STR}")
    for pid, name, team, is_home in ROSTER:
        opp = "SAS" if team == "OKC" else "OKC"
        try:
            preds = predict_player_pergame(pid, opp, SEASON, is_home=is_home, rest_days=2.0,
                                           gamelog_dir=_NBA_CACHE, model_dir=_MODEL_DIR)
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}"); continue
        if not preds:
            print(f"  [SKIP] {name}"); continue
        n_ok += 1
        print(f"  {name:<28} PTS={preds.get('pts','?'):>5} REB={preds.get('reb','?'):>4} AST={preds.get('ast','?'):>4}")
        for stat in STATS:
            v = preds.get(stat)
            if v is None:
                continue
            q50 = float(v); sig = _STAT_SIGMA.get(stat, 2.0)
            rows.append({"player_id": pid, "player_name": name, "team": team, "is_home": is_home,
                         "stat": stat, "q10": _q(q50, sig, .1), "q50": q50, "q90": _q(q50, sig, .9),
                         "sigma": sig, "computed_at": computed_at})
    df = pd.DataFrame(rows)
    out = os.path.join(_CACHE_DIR, "predictions_cache_game7.parquet")
    df.to_parquet(out, index=False)
    print(f"\n  Wrote {len(df)} rows ({n_ok} players) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
