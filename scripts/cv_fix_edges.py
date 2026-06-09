"""
cv_fix_edges.py — compare model projections to the live market (the-odds-api) and surface edges.
Treats the market as the benchmark: reports the game-line disagreement (model vs no-vig market)
and player-prop edges, flagged by whether they agree with or fight the market's team lean.
"""
import json, math, sys
from collections import defaultdict
from statistics import median, NormalDist

CV = "data/cache/cv_fix"
PRED = json.load(open(f"{CV}/predict_g7.json"))
PROPS = json.load(open(f"{CV}/g7_props.json"))
GAME = json.load(open(f"{CV}/g7_game_odds.json")) if len(sys.argv) > 1 else None
N = NormalDist()


def am_to_prob(a):
    return (-a) / (-a + 100) if a < 0 else 100 / (a + 100)

def am_payout(a):  # profit per $1 stake
    return (100 / -a) if a < 0 else (a / 100)

def key(full):
    parts = full.split()
    return (parts[0][0].lower(), parts[-1].lower())

# my projections keyed by (first-initial, lastname)
mine = {}
for nm, r in PRED["players"].items():
    mine[key(nm.replace(".", "").replace("Jale", "Jalen").replace("Jayl", "Jaylin"))] = (nm, r)

import os
SD_INFLATE = float(os.environ.get("SD_INFLATE", "1.7"))  # de-overconfidence: 6-game variance
# underestimates true game-to-game spread; market prices season+minutes+gamescript variance.

def my_dist(stat_pc):
    mean = stat_pc["mean"]
    sd = max(1.0, (stat_pc["p90"] - stat_pc["p10"]) / 2.563) * SD_INFLATE
    return mean, sd

STAT = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast"}

# collect market lines per (player, market): consensus line + best price each side
book_lines = defaultdict(lambda: {"over": [], "under": [], "pts": []})
for bk in PROPS.get("bookmakers", []):
    for m in bk["markets"]:
        st = STAT.get(m["key"])
        if not st:
            continue
        for o in m["outcomes"]:
            pl = o["description"]; side = o["name"].lower()
            book_lines[(pl, m["key"])][side].append((o["point"], o["price"]))
            book_lines[(pl, m["key"])]["pts"].append(o["point"])

edges = []
for (pl, mk), bl in book_lines.items():
    if not bl["over"] or not bl["under"]:
        continue
    line = median(bl["pts"])
    best_over = max(p for pt, p in bl["over"] if abs(pt - line) < 1e-6) if any(abs(pt-line)<1e-6 for pt,_ in bl["over"]) else max(p for _, p in bl["over"])
    best_under = max(p for pt, p in bl["under"] if abs(pt - line) < 1e-6) if any(abs(pt-line)<1e-6 for pt,_ in bl["under"]) else max(p for _, p in bl["under"])
    # no-vig market prob (avg of books)
    io = sum(am_to_prob(p) for _, p in bl["over"]) / len(bl["over"])
    iu = sum(am_to_prob(p) for _, p in bl["under"]) / len(bl["under"])
    novig_over = io / (io + iu)
    k = key(pl); st = STAT[mk]
    if k not in mine:
        continue
    nm, r = mine[k]
    mean, sd = my_dist(r[st])
    p_over = 1 - N.cdf((line + 0.5 - mean) / sd)   # discrete continuity correction
    # pick the +EV side
    ev_over = p_over * am_payout(best_over) - (1 - p_over)
    ev_under = (1 - p_over) * am_payout(best_under) - p_over
    if ev_over >= ev_under:
        side, price, ev, p_model, p_mkt = "OVER", best_over, ev_over, p_over, novig_over
    else:
        side, price, ev, p_model, p_mkt = "UNDER", best_under, ev_under, 1 - p_over, 1 - novig_over
    edges.append(dict(player=nm, market=st, line=line, side=side, price=price,
                      proj=mean, p_model=round(p_model, 3), p_mkt=round(p_mkt, 3),
                      edge=round(p_model - p_mkt, 3), ev=round(ev, 3)))

edges.sort(key=lambda e: -e["ev"])
print("="*92)
print("GAME 7 — MODEL vs MARKET (model is series-only, no season prior — read with that caveat)")
print("="*92)
if GAME:
    print(f"GAME LINE: market {GAME['mkt']}  |  model: SAS {PRED['win_prob']['SAS']}% / OKC {PRED['win_prob']['OKC']}%")
print(f"\n{'Player':24s} {'Mkt':4s} {'Line':>5s} {'Side':5s} {'Price':>5s} {'proj':>5s} "
      f"{'P(mdl)':>6s} {'P(mkt)':>6s} {'edge':>6s} {'EV':>6s}")
for e in edges:
    if e["ev"] <= 0.02:
        continue
    print(f"{e['player']:24s} {e['market']:4s} {e['line']:5.1f} {e['side']:5s} {e['price']:>5d} "
          f"{e['proj']:5.1f} {e['p_model']:6.2f} {e['p_mkt']:6.2f} {e['edge']:+6.2f} {e['ev']:+6.2f}")
print(f"\n[{sum(1 for e in edges if e['ev']>0.02)} props with model EV>2%]  "
      f"(positive EV vs market = model thinks it's mispriced; trust scales with model calibration)")
json.dump(edges, open(f"{CV}/g7_edges.json", "w"), indent=2)
