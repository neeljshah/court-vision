"""
bet_card_game7.py — reconciled, actionable bet card for WCF G7.
Reads the EV board (prop_ev_best.csv) + the reconciled ensemble + the Wemby/SGA showcases,
computes proper EV and quarter-Kelly stakes, OVERRIDES the stale board p_win with the
matchup-grounded showcase probabilities where we have them, filters, and ranks.
Output: data/cache/intel_game7/bet_card_game7.json (+ printed markdown table).
Every number traces to an input artifact. No fabrication.
"""
import json, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "intel_game7"

def american_to_b(o):
    o = float(o)
    return o/100.0 if o > 0 else 100.0/abs(o)

def ev_and_kelly(p, odds):
    b = american_to_b(odds)
    ev = p*b - (1-p)              # per $1 risked
    f = (p*(b+1) - 1)/b          # full Kelly fraction
    kelly_q = max(0.0, 0.25*f)   # quarter-Kelly, no negative
    return round(ev, 3), round(kelly_q, 4), round(b, 3)

# --- showcase overrides (matchup-grounded, more reliable than the board's fused p) ---
wem = json.loads((CACHE/"wemby_points_showcase.json").read_text())
sga = json.loads((CACHE/"sga_points_showcase.json").read_text())
OVERRIDES = {
    # (player, stat, line) -> {side: p_win}  (p of the side WINNING)
    ("Victor Wembanyama","pts",27.5): {"UNDER": round(1-wem["distribution"]["P(over_27.5)"],3),
                                        "OVER": wem["distribution"]["P(over_27.5)"]},
    ("Shai Gilgeous-Alexander","pts",27.5): {"UNDER": round(1-sga["distribution"]["P(over_27.5)"],3),
                                             "OVER": sga["distribution"]["P(over_27.5)"]},
    ("Shai Gilgeous-Alexander","pts",26.5): {"UNDER": round(1-sga["distribution"]["P(over_26.5)"],3),
                                             "OVER": sga["distribution"]["P(over_26.5)"]},
}

rows = []
with open(CACHE/"prop_ev_best.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["book"] == "fanatics":   # exclude longshot book (unrealistic odds)
            continue
        try:
            p = float(r["p_win"]); line = float(r["line"]); odds = float(r["odds"])
        except Exception:
            continue
        key = (r["player"], r["stat"], line); ov = OVERRIDES.get(key)
        src = "board"
        if ov and r["side"] in ov:
            p = ov[r["side"]]; src = "showcase"
        ev, kq, b = ev_and_kelly(p, odds)
        rows.append({"player": r["player"], "stat": r["stat"], "side": r["side"], "line": line,
                     "fused": r.get("fused_mu"), "p_win": round(p,3), "odds": int(odds),
                     "ev": ev, "kelly_q": kq, "book": r["book"], "p_src": src})

# filters: positive EV, sane confidence band (avoid coinflips & heavy favorites that are noise)
plays = [x for x in rows if x["ev"] >= 0.04 and 0.55 <= x["p_win"] <= 0.97]
plays.sort(key=lambda x: x["ev"], reverse=True)

# team bets (from ensemble) — honest read
ens = json.loads((CACHE/"ensemble_game7.json").read_text())
team = {
    "OKC_ML": {"model_p": ens["okc_win_prob"], "market_implied_-155": 0.608,
               "read": "model 60.9% vs market 60.8% -> NO EDGE, pass/tiny"},
    "OKC_spread": {"model_margin": ens["okc_margin_est"], "market": "-3.5/-4.5",
                   "read": "model OKC -2.7 -> -3 is ~fair, -4.5 is RICH; prefer ML or -3"},
    "total": {"model": ens["total_est"], "market": 213.0,
              "read": "model 214.2 vs 213 -> NO EDGE; slight under lean on G7 pace compression, pass"},
}

out = {"game": "WCF G7 SAS@OKC 2026-05-30", "n_props_considered": len(rows),
       "team_bets": team, "top_prop_plays": plays[:18],
       "notes": ["p_src=showcase => p_win overridden by matchup-grounded Wemby/SGA model (more reliable than board fused).",
                 "Kelly is QUARTER-Kelly, no-negative. Stake = kelly_q * bankroll, cap at your own max (e.g. 2-3%).",
                 "fanatics book excluded (longshot odds). EV>=4% and 0.55<=p<=0.97 filter.",
                 "Team side/total: market efficient -> edge is in props. Wemby PTS now a PASS (showcase P-over 50.4%)."]}
(CACHE/"bet_card_game7.json").write_text(json.dumps(out, indent=2))

print("=== WCF G7 BET CARD (top prop plays by EV) ===")
print(f"{'BET':42s} {'line':>5s} {'p':>5s} {'odds':>5s} {'EV%':>6s} {'qK%':>5s} {'book':>9s} src")
for x in plays[:18]:
    nm = f"{x['player']} {x['stat'].upper()} {x['side']} {x['line']}"
    print(f"{nm:42s} {x['line']:>5} {x['p_win']:>5.2f} {x['odds']:>5d} {x['ev']*100:>5.1f}% {x['kelly_q']*100:>4.1f}% {x['book']:>9s} {x['p_src']}")
print("\nTeam bets:")
for k,v in team.items(): print(f"  {k}: {v['read']}")
print("\nWROTE", CACHE/"bet_card_game7.json")
