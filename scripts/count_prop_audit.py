"""
count_prop_audit.py — re-price EVERY count-stat prop (reb/blk/stl/ast) with proper
over-dispersed count distributions anchored to real WCF series averages.

Motivation: caught the board pricing Wemby BLK UNDER 3.5 at 96% when his series blk avg is
3.0 (honest ~69%). The prop stack's count-stat variance is systematically too tight. This
audits the whole count board, flags where |board_p - honest_p| > 0.10, and emits corrected
probabilities + EV so the bet card uses honest numbers.
"""
import json, csv, math
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "intel_game7"
SERIES = ROOT / "data" / "cache" / "intel_2026-05-26" / "wcf_player_series_avg_6g.csv"

# series per-game means by player_name -> {reb, ast, stl, blk}
series = {}
with open(SERIES, newline="") as f:
    for r in csv.DictReader(f):
        series[r["player_name"].strip().lower()] = {
            "reb": float(r["reb_pg"]), "ast": float(r["ast_pg"]),
            "stl": float(r["stl_pg"]), "blk": float(r["blk_pg"]), "min": float(r["min_pg"])}

# dispersion (var/mean) priors by stat — count stats are over-dispersed game-to-game
DISP = {"reb": 1.35, "ast": 1.45, "stl": 1.20, "blk": 1.55}
# modest regression toward the line/role for G7 (series is small sample)
REG = 0.93

def nb_under(mean, line, disp):
    """P(X <= floor(line)) for NegBinom(mean, var=disp*mean); Poisson if disp<=1."""
    mean = max(mean, 0.05)
    var = disp * mean
    k = int(math.floor(line))
    if var <= mean * 1.001:
        return float(stats.poisson(mean).cdf(k))
    p = mean / var; r = mean * p / (1 - p)
    return float(stats.nbinom(r, p).cdf(k))

def american_to_b(o):
    o = float(o)
    return o/100.0 if o > 0 else 100.0/abs(o)

def name_key(n):
    return n.strip().lower().replace("’", "'")

rows, flags = [], []
with open(CACHE / "prop_ev_best.csv", newline="") as f:
    for r in csv.DictReader(f):
        stat = r["stat"]
        if stat not in DISP or r["book"] == "fanatics":
            continue
        nm = name_key(r["player"])
        s = series.get(nm)
        if not s:
            continue
        line = float(r["line"]); side = r["side"]; odds = float(r["odds"]); board_p = float(r["p_win"])
        mean = s[stat] * REG
        p_under = nb_under(mean, line, DISP[stat])
        honest_p = p_under if side == "UNDER" else (1 - p_under)
        b = american_to_b(odds)
        ev = honest_p * b - (1 - honest_p)
        delta = honest_p - board_p
        rec = {"player": r["player"], "stat": stat, "side": side, "line": line,
               "series_avg": round(s[stat], 2), "model_mean": round(mean, 2),
               "board_p": round(board_p, 3), "honest_p": round(honest_p, 3),
               "delta": round(delta, 3), "odds": int(odds), "honest_ev": round(ev, 3), "book": r["book"]}
        rows.append(rec)
        if abs(delta) > 0.10:
            flags.append(rec)

# sort flags by absolute board overconfidence
flags.sort(key=lambda x: abs(x["delta"]), reverse=True)
# honest positive-EV count plays
plays = sorted([x for x in rows if x["honest_ev"] >= 0.04 and 0.55 <= x["honest_p"] <= 0.95],
               key=lambda x: x["honest_ev"], reverse=True)

out = {"n_count_props": len(rows), "n_flagged_miscalibrated": len(flags),
       "flagged_board_overconfidence": flags[:20], "honest_count_plays": plays[:15],
       "method": "NegBinom anchored to WCF 6g series avg, var=disp*mean (reb1.35/ast1.45/stl1.20/blk1.55), 0.93 regression.",
       "notes": ["Flags = |board_p - honest_p| > 0.10. Positive delta => board UNDER-rated the side; negative => board OVER-confident.",
                 "Honest plays filtered EV>=4%, 0.55<=p<=0.95 (drop board's >0.95 fantasies)."]}
(CACHE / "count_prop_audit.json").write_text(json.dumps(out, indent=2))

print(f"=== COUNT-PROP AUDIT ===  {len(rows)} props, {len(flags)} miscalibrated (>10pp)")
print("\nMOST MISCALIBRATED (board_p -> honest_p):")
print(f"{'BET':40s} {'avg':>4s} {'board':>5s} {'honest':>6s} {'Δ':>6s}")
for x in flags[:14]:
    nm = f"{x['player']} {x['stat'].upper()} {x['side']} {x['line']}"
    print(f"{nm:40s} {x['series_avg']:>4} {x['board_p']:>5.2f} {x['honest_p']:>6.2f} {x['delta']:>+6.2f}")
print("\nHONEST +EV COUNT PLAYS:")
for x in plays[:10]:
    nm = f"{x['player']} {x['stat'].upper()} {x['side']} {x['line']}"
    print(f"  {nm:40s} p={x['honest_p']:.2f} EV={x['honest_ev']*100:+.0f}% ({x['odds']:+d} {x['book']})")
print("\nWROTE", CACHE / "count_prop_audit.json")
