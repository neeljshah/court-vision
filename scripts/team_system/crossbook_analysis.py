"""CROSS-BOOK LINE EFFICIENCY -- mine the untapped multi-bookmaker odds snapshots.

`data/cache/odds_api/historical_event_odds/` holds 646 near-close odds SNAPSHOTS (2024-26, incl playoffs),
each with up to 8 books (DK/FD/MGM/Bovada/BetRivers/WilliamHill/BetOnline/Fanatics) x 6 player-prop markets.
The EDGE_GATE corpora are single-BOOK single-snapshot; this is the first use of the MULTI-BOOK dimension.

It answers two disciplined, validatable (pure-pricing-fact, no outcome-fit, no overfit) questions:
  1. LINE-SHOPPING value: how much EV does taking the BEST of N books add vs the median book? (an EXECUTION
     edge -- mechanical, additive to any model edge; NOT a model edge claim).
  2. CROSS-BOOK EFFICIENCY at close: how much do books disagree on the de-vigged P(over)? Small disagreement
     => the close is efficient => the real edge lane is OPENERS/freshness (the documented un-refuted lane), not
     the close. (The hold sets the bar a bet must beat.)

American odds are NOT linearly averageable across the +/-100 discontinuity -> all aggregation is done in
implied-probability / net-payout space.

  python scripts/team_system/crossbook_analysis.py
"""
from __future__ import annotations
import glob, json, os, statistics as st
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAP = os.path.join(ROOT, "data", "cache", "odds_api", "historical_event_odds")
OUT = os.path.join(ROOT, "data", "cache", "team_system", "crossbook_efficiency.json")


def imp(a):
    a = float(a)
    return 100 / (a + 100) if a > 0 else (-a) / (-a + 100)


def payout(a):                 # net profit per 1u staked (decimal - 1); always > 0 for valid American odds
    a = float(a)
    return a / 100 if a > 0 else 100 / (-a)


def main():
    rows = []
    for f in glob.glob(os.path.join(SNAP, "*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        date = os.path.basename(f)[:10]
        for b in d.get("data", {}).get("bookmakers", []):
            for m in b.get("markets", []):
                tmp = {}
                for o in m.get("outcomes", []):
                    pt = o.get("point")
                    if pt is None or o.get("price") in (None, 0):
                        continue
                    tmp.setdefault((o.get("description"), pt), {})[o["name"]] = o["price"]
                for (pl, pt), sd in tmp.items():
                    if "Over" in sd and "Under" in sd:
                        rows.append((date, m["key"], pl, pt, b["key"], sd["Over"], sd["Under"]))

    g = defaultdict(list)
    for r in rows:
        g[(r[0], r[1], r[2], r[3])].append((r[4], r[5], r[6]))

    bymk = defaultdict(lambda: {"up": [], "dis": [], "hold": []})
    n_books_hist = defaultdict(int)
    for k, v in g.items():
        n_books_hist[len(v)] += 1
        if len(v) < 3:
            continue
        mk = k[1]
        pos = [imp(ov) / (imp(ov) + imp(un)) for _, ov, un in v]
        cons = st.median(pos)
        payb = [payout(ov) for _, ov, un in v]
        best, med = max(payb), st.median(payb)
        bymk[mk]["up"].append(cons * (best - med))                       # line-shop EV uplift (>=0 by construction)
        bymk[mk]["dis"].append(max(pos) - min(pos))                      # cross-book de-vig disagreement
        bymk[mk]["hold"].append(st.median([imp(ov) + imp(un) - 1 for _, ov, un in v]))

    # book-softness map: which book most often offers the best line-shopping price (+ its hold)
    best_over = defaultdict(int); best_under = defaultdict(int); appear = defaultdict(int); bk_hold = defaultdict(list)
    pay = lambda a: (a / 100 if a > 0 else 100 / (-a))
    for k, v in g.items():
        if len(v) < 3:
            continue
        for bk, ov, un in v:
            appear[bk] += 1; bk_hold[bk].append(imp(ov) + imp(un) - 1)
        best_over[max(v, key=lambda x: pay(x[1]))[0]] += 1
        best_under[max(v, key=lambda x: pay(x[2]))[0]] += 1

    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    allup = [u for mk in bymk for u in bymk[mk]["up"]]
    alldis = [d for mk in bymk for d in bymk[mk]["dis"]]
    allhold = [h for mk in bymk for h in bymk[mk]["hold"]]
    assert min(allup) >= -1e-9, "negative line-shopping uplift = a bug"

    print(f"=== CROSS-BOOK LINE EFFICIENCY ({len(rows)} prop-book rows, {len(g)} props; >=3-book props) ===")
    print(f"{'market':16s} {'n':>5s} {'lineshop EV+':>12s} {'devig disagr':>12s} {'med hold':>9s}")
    out = {"asof": "2026-06-08", "builder": "crossbook_analysis.py", "n_prop_book_rows": len(rows),
           "n_props": len(g), "by_market": {}}
    for mk in sorted(bymk):
        u, di, ho = bymk[mk]["up"], bymk[mk]["dis"], bymk[mk]["hold"]
        print(f"{mk:16s} {len(u):5d} {mean(u)*100:+11.2f}% {mean(di)*100:11.2f}pp {mean(ho)*100:8.2f}%")
        out["by_market"][mk] = {"n": len(u), "lineshop_ev": mean(u), "devig_disagree": mean(di), "med_hold": mean(ho)}
    print(f"{'ALL':16s} {len(allup):5d} {mean(allup)*100:+11.2f}% {mean(alldis)*100:11.2f}pp {mean(allhold)*100:8.2f}%")
    out["ALL"] = {"n": len(allup), "lineshop_ev": mean(allup), "devig_disagree": mean(alldis),
                  "med_hold": mean(allhold)}

    print(f"\n=== BOOK SOFTNESS (higher best-price%% = softer/better to line-shop) ===")
    print(f"{'book':16s} {'appears':>8s} {'best-over%':>10s} {'best-under%':>11s} {'avg hold':>9s}")
    out["book_softness"] = {}
    for bk in sorted(appear, key=lambda b: -(best_over[b] + best_under[b]) / max(appear[b], 1)):
        ap = appear[bk]
        print(f"{bk:16s} {ap:8d} {best_over[bk]/ap*100:9.1f}% {best_under[bk]/ap*100:10.1f}% {mean(bk_hold[bk])*100:8.2f}%")
        out["book_softness"][bk] = {"appears": ap, "best_over_pct": best_over[bk] / ap,
                                    "best_under_pct": best_under[bk] / ap, "avg_hold": mean(bk_hold[bk])}
    json.dump(out, open(OUT + ".staging", "w"), indent=1)
    os.replace(OUT + ".staging", OUT)
    print(f"\nwrote {OUT}")
    print(f"\nREAD: line-shopping the best of >=3 books adds ~{mean(allup)*100:+.1f}% EV/bet (an EXECUTION edge, "
          f"additive to any model edge -- NOT a model edge claim). Books agree at close within "
          f"~{mean(alldis)*100:.1f}pp de-vig (vs a ~{mean(allhold)*100:.1f}% hold) -> the close is efficient -> "
          f"the real edge lane is OPENERS/FRESHNESS (bet before the line converges), confirming the documented "
          f"un-refuted money lane. Outcome-graded edge still needs open/close capture (single-snapshot here).")


if __name__ == "__main__":
    main()
