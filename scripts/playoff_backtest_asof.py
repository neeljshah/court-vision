"""
playoff_backtest_asof.py - Clean as-of backtest for WCF G1-G6.

For G1-G4: reads actual box scores from gamelog JSON files.
For G5-G6: uses hardcoded actuals from update_series_6game.py.

For each game, predictions use ONLY games strictly before that game's date
(written to a temp dir) to eliminate look-ahead leakage.

Outputs per-stat playoff MAE compared to claimed holdout MAE.
"""
from __future__ import annotations
import warnings, os, sys, json, tempfile, shutil
warnings.filterwarnings("ignore")
os.environ["NBA_INJURY_WIRE_DISABLE"] = "1"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import src.data.nba_api_headers_patch  # noqa: F401
from datetime import datetime
from src.prediction.prop_pergame import (
    predict_player_pergame, STATS, _parse_date, _MIN_PLAYED
)

SEASON = "2025-26"
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# WCF game definitions: (game_id, date_str, game_num, home_team, away_team)
WCF_GAMES_G1_G4 = [
    ("0042500311", "May 18, 2026", 1, "OKC", "SAS"),
    ("0042500312", "May 20, 2026", 2, "OKC", "SAS"),
    ("0042500313", "May 22, 2026", 3, "SAS", "OKC"),
    ("0042500314", "May 24, 2026", 4, "SAS", "OKC"),
]

# G5 and G6 actuals from update_series_6game.py
# order in tuple: min, pts, reb, ast, stl, blk, tov, fg3m
G5_ACTUALS_BY_PID = {
    1628983: (37, 32, 2, 9, 2, 1, 6, 2),    # SGA
    1631096: (30, 16, 11, 1, 1, 1, 3, 0),   # Holmgren
    1628392: (31, 12, 15, 4, 0, 1, 3, 0),   # Hartenstein
    1627936: (28, 22, 2, 6, 3, 0, 2, 4),    # Caruso
    1642272: (33, 20, 3, 0, 0, 0, 2, 3),    # McCain
    1629652: (18, 7, 4, 0, 0, 0, 0, 1),     # Dort
    1629026: (31, 7, 4, 5, 2, 2, 0, 1),     # KenrichWilliams
    1641705: (38, 20, 6, 1, 2, 3, 2, 0),    # Wemby
    1628368: (33, 9, 4, 8, 3, 0, 1, 0),     # Fox
    1642264: (33, 24, 5, 6, 3, 0, 3, 3),    # Castle
    1630170: (36, 6, 4, 4, 3, 0, 1, 2),     # Vassell
    1629640: (20, 15, 4, 2, 0, 0, 2, 1),    # KeldonJohnson
    1630577: (30, 22, 8, 1, 3, 0, 2, 4),    # Champagnie
}

G6_ACTUALS_BY_PID = {
    1628983: (28, 15, 1, 4, 0, 0, 2, 0),    # SGA
    1631096: (24, 10, 11, 1, 1, 2, 0, 0),   # Holmgren
    1628392: (16, 10, 5, 3, 0, 0, 0, 0),    # Hartenstein
    1627936: (21, 7, 0, 0, 1, 0, 0, 1),     # Caruso
    1642272: (27, 13, 2, 6, 2, 0, 2, 2),    # McCain
    1629652: (23, 5, 1, 0, 1, 1, 1, 1),     # Dort
    1629026: (15, 7, 6, 2, 0, 0, 1, 1),     # KenrichWilliams
    1641705: (28, 28, 10, 2, 2, 3, 3, 4),   # Wemby
    1628368: (26, 5, 5, 7, 0, 0, 0, 0),     # Fox
    1642264: (32, 17, 5, 9, 1, 0, 1, 0),    # Castle
    1630170: (26, 12, 1, 2, 1, 2, 1, 4),    # Vassell
    1642844: (22, 18, 6, 4, 0, 0, 1, 2),    # Harper
    1629640: (18, 9, 3, 0, 1, 0, 1, 1),     # KeldonJohnson
    1630577: (25, 10, 6, 2, 1, 2, 1, 2),    # Champagnie
}

# Column order in G5/G6 tuples: min, pts, reb, ast, stl, blk, tov, fg3m
G5G6_ORDER = ["min", "pts", "reb", "ast", "stl", "blk", "tov", "fg3m"]

PLAYERS = [
    (1628983, "SGA", "OKC"),
    (1631096, "Holmgren", "OKC"),
    (1628392, "Hartenstein", "OKC"),
    (1627936, "Caruso", "OKC"),
    (1642272, "McCain", "OKC"),
    (1641717, "C.Wallace", "OKC"),
    (1629652, "Dort", "OKC"),
    (1631119, "JaylinWilliams", "OKC"),
    (1629026, "KenrichWilliams", "OKC"),
    (1641705, "Wemby", "SAS"),
    (1628368, "Fox", "SAS"),
    (1642264, "Castle", "SAS"),
    (1630170, "Vassell", "SAS"),
    (1642844, "Harper", "SAS"),
    (1629640, "KeldonJohnson", "SAS"),
    (1630577, "Champagnie", "SAS"),
]

# Claimed MAEs from verify_production_mae.py / PREDICTIONS_QUICKSTART
CLAIMED_MAE = {"pts": 4.62, "reb": 1.90, "ast": 1.36, "fg3m": 0.89, "stl": 0.72, "blk": 0.44, "tov": 0.89}

MIN_MINUTES = 10.0  # skip DNPs/garbage time


def get_actual_from_gamelog(pid, game_id):
    """Read actual stats for a player in a specific game_id from their gamelog."""
    path = os.path.join(_NBA_CACHE, f"gamelog_{pid}_{SEASON}.json")
    if not os.path.exists(path):
        return None
    try:
        games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    for g in games:
        if g.get("GAME_ID") == game_id:
            return {
                "min": float(g.get("MIN", 0) or 0),
                "pts": float(g.get("PTS", 0) or 0),
                "reb": float(g.get("REB", 0) or 0),
                "ast": float(g.get("AST", 0) or 0),
                "stl": float(g.get("STL", 0) or 0),
                "blk": float(g.get("BLK", 0) or 0),
                "tov": float(g.get("TOV", 0) or 0),
                "fg3m": float(g.get("FG3M", 0) or 0),
            }
    return None


def predict_asof(pid, team, opp, is_home, cutoff_date, rest_days=2.0):
    """Build a clean prediction using only games STRICTLY before cutoff_date."""
    path = os.path.join(_NBA_CACHE, f"gamelog_{pid}_{SEASON}.json")
    if not os.path.exists(path):
        return None
    try:
        all_games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None

    # Filter to games before cutoff
    prior = [g for g in all_games
             if (d := _parse_date(g.get("GAME_DATE"))) is not None and d < cutoff_date]

    prior_played = [g for g in prior if float(g.get("MIN", 0) or 0) >= _MIN_PLAYED]
    if len(prior_played) < 3:
        return None

    # Write temp gamelog
    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_path = os.path.join(tmp_dir, f"gamelog_{pid}_{SEASON}.json")
        json.dump(prior, open(tmp_path, "w", encoding="utf-8"))
        preds = predict_player_pergame(
            pid, opp, SEASON,
            is_home=is_home,
            rest_days=rest_days,
            gamelog_dir=tmp_dir,
            model_dir=_MODEL_DIR,
        )
    except Exception as e:
        print(f"    [predict_asof ERROR pid={pid}]: {e}")
        preds = None
    finally:
        shutil.rmtree(tmp_dir)
    return preds


def main():
    all_results = []

    # --- G1-G4: actual data from gamelogs ---
    print("\n=== WCF G1-G4 AS-OF PREDICTIONS ===")
    for game_id, date_str, game_num, home_team, away_team in WCF_GAMES_G1_G4:
        cutoff = datetime.strptime(date_str, "%b %d, %Y")
        print(f"\n--- G{game_num} {date_str}  {away_team} @ {home_team} ---")
        for pid, pname, team in PLAYERS:
            actual = get_actual_from_gamelog(pid, game_id)
            if actual is None or actual["min"] < MIN_MINUTES:
                continue
            opp = "SAS" if team == "OKC" else "OKC"
            is_home = (team == home_team)
            preds = predict_asof(pid, team, opp, is_home, cutoff)
            if preds is None:
                print(f"  {pname}: no prediction")
                continue
            row = {"game": game_num, "player": pname, "pid": pid, "min": actual["min"]}
            print(f"  {pname:<18} min={actual['min']:.0f} | ", end="")
            for stat in STATS:
                p = preds[stat]
                a = actual.get(stat, 0.0)
                err = abs(p - a)
                row[stat + "_pred"] = p
                row[stat + "_actual"] = a
                row[stat + "_err"] = err
                all_results.append({"game": game_num, "player": pname, "stat": stat,
                                     "pred": p, "actual": a, "err": err})
            print(f"PTS pred={preds['pts']:.1f} act={actual['pts']:.0f} | "
                  f"REB pred={preds['reb']:.1f} act={actual['reb']:.0f} | "
                  f"AST pred={preds['ast']:.1f} act={actual['ast']:.0f}")

    # --- G5 and G6: actuals from hardcoded dicts; predict as-of May 26 / May 28 ---
    G5_DATE = datetime(2026, 5, 26)
    G6_DATE = datetime(2026, 5, 28)

    for game_num, cutoff, actuals_dict, home_team, away_team in [
        (5, G5_DATE, G5_ACTUALS_BY_PID, "OKC", "SAS"),   # OKC 127-114
        (6, G6_DATE, G6_ACTUALS_BY_PID, "SAS", "OKC"),   # SAS 118-91
    ]:
        print(f"\n--- G{game_num} {cutoff.strftime('%b %d, %Y')}  {away_team} @ {home_team} ---")
        for pid, pname, team in PLAYERS:
            if pid not in actuals_dict:
                continue
            actual_tup = actuals_dict[pid]
            if actual_tup[0] is None:  # Harper not in G5
                continue
            actual = dict(zip(G5G6_ORDER, actual_tup))
            if actual["min"] < MIN_MINUTES:
                continue
            opp = "SAS" if team == "OKC" else "OKC"
            is_home = (team == home_team)
            preds = predict_asof(pid, team, opp, is_home, cutoff)
            if preds is None:
                print(f"  {pname}: no prediction")
                continue
            print(f"  {pname:<18} min={actual['min']:.0f} | ", end="")
            for stat in STATS:
                p = preds[stat]
                a = float(actual.get(stat, 0.0))
                err = abs(p - a)
                all_results.append({"game": game_num, "player": pname, "stat": stat,
                                     "pred": p, "actual": a, "err": err})
            print(f"PTS pred={preds['pts']:.1f} act={actual['pts']:.0f} | "
                  f"REB pred={preds['reb']:.1f} act={actual['reb']:.0f} | "
                  f"AST pred={preds['ast']:.1f} act={actual['ast']:.0f}")

    # --- Summary ---
    print("\n\n=== PLAYOFF BACKTEST SUMMARY (AS-OF, 6 GAMES) ===")
    print(f"{'Stat':<6} {'Playoff MAE':>12} {'Claimed MAE':>12} {'Gap':>8} {'N':>5}")
    print("-" * 50)

    stat_rows = []
    for stat in STATS:
        sr = [r for r in all_results if r["stat"] == stat]
        if not sr:
            continue
        mae = sum(r["err"] for r in sr) / len(sr)
        claim = CLAIMED_MAE[stat]
        gap = mae - claim
        stat_rows.append((stat, mae, claim, gap, len(sr)))
        sign = "+" if gap >= 0 else ""
        print(f"{stat.upper():<6} {mae:>12.4f} {claim:>12.2f} {sign+f'{gap:.4f}':>8} {len(sr):>5}")

    # Bias analysis
    print("\n--- PTS Bias Analysis ---")
    pts_res = [r for r in all_results if r["stat"] == "pts"]
    if pts_res:
        bias = sum(r["pred"] - r["actual"] for r in pts_res) / len(pts_res)
        print(f"  Mean bias (pred - actual): {bias:+.2f} (positive = over-predict)")

    return stat_rows, all_results


if __name__ == "__main__":
    stat_rows, all_results = main()
