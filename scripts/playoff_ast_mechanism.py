"""playoff_ast_mechanism.py — WHY does the AST pregame edge break in the playoffs,
and does ANY playoff sub-policy survive?

Consumes the leak-free graded rows pickled by playoff_pregame_edge.py (each row carries
the production-stack pred, the real line+odds, the actual, and the full dataset feature row
incl. opp_team_pace_l5, l10_min, target_min). All grading at |odds|>=100, real posted odds.

Mechanism hypotheses tested (pre-registered):
  H-PACE   : §8d found the regular-season AST edge is pace-concentrated (high opp_pace
             +43.8%). Playoffs slow down -> the edge's fuel disappears. Test: (a) is playoff
             pace lower than regular season? (b) does the §8d pace tilt SURVIVE in playoffs
             (is high-pace playoff AST still +)?
  H-MIN    : tighter playoff rotations -> minutes more predictable -> the minutes-surprise
             the model exploits shrinks. Test: is |target_min - l10_min| smaller in playoffs?
             (a smaller surprise band means the model has less to exploit.)
  H-LINE   : star-centric usage -> higher AST lines, sharper books. Test: edge by line bucket.

Sub-policies tested for a ROBUST survivor (must clear in BOTH the 2026-oddsapi playoff sample
AND the extended_oos 2026-playoff AST sample from §8e — not a single series): high-pace AST,
UNDER-only, low-line AST, gated. Small-sample discipline: report bootstrap CI + P(ROI<=0),
do NOT declare an edge on one slice of one series.

Read-only. No flag flips.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import _payout  # noqa: E402

RNG = np.random.default_rng(20260604)


def settle(r):
    line, a, p = r["line"], r["actual"], r["pred"]
    if abs(p - line) < 1e-9 or abs(a - line) < 1e-9:
        return None
    over = p > line
    won = (over and a > line) or (not over and a < line)
    return over, won, _payout(r["over_odds"] if over else r["under_odds"], won)


def roi(rs):
    if not rs:
        return 0, 0.0, 0.0
    n = len(rs)
    return n, sum(int(w) for _, w, _ in rs) / n * 100, sum(p for _, _, p in rs) / (n * 100) * 100


def boot(rs):
    if not rs:
        return (0.0, 0.0, 1.0)
    pays = np.array([p for _, _, p in rs])
    b = [RNG.choice(pays, len(pays), replace=True).sum() / (len(pays) * 100) * 100 for _ in range(6000)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), float((np.array(b) <= 0).mean())


def grade(rows, fil=None):
    sel = [r for r in rows if (fil is None or fil(r))]
    s = [(r, settle(r)) for r in sel]
    s = [(r, x) for r, x in s if x is not None]
    allx = [x for _, x in s]
    n, win, r_ = roi(allx)
    lo, hi, p0 = boot(allx)
    return {"n": n, "win": round(win, 1), "roi": round(r_, 2),
            "ci": [round(lo, 1), round(hi, 1)], "p_le0": round(p0, 3)}


def pace_of(r):
    return float(r["row"].get("opp_team_pace_l5") or 0.0)


def minsurprise(r):
    tm = r["row"].get("target_min")
    l10 = r["row"].get("l10_min")
    if tm is None or l10 is None:
        return None
    return abs(float(tm) - float(l10))


def main():
    graded = pickle.load(open(_ROOT / "data" / "cache" / "playoff_graded.pkl", "rb"))
    out = {}

    # --- assemble the 2026 playoff AST sample (the real-odds one) ---
    po_ast = graded.get("2026_playoffs", {}).get("ast", [])
    print(f"2026-playoff AST graded rows (real odds): n={len(po_ast)}")

    # =============================================================
    # MECHANISM
    # =============================================================
    print("\n" + "=" * 64)
    print("MECHANISM — pace & minutes regime, playoff AST vs regular season")
    print("=" * 64)

    # H-PACE (a): playoff vs reg-season pace distribution.
    paces = [pace_of(r) for r in po_ast if pace_of(r) > 0]
    print(f"\n[H-PACE a] 2026-playoff AST-bet opp_pace_l5: "
          f"median={np.median(paces):.1f} mean={np.mean(paces):.1f} "
          f"p25={np.percentile(paces,25):.1f} p75={np.percentile(paces,75):.1f}  (n={len(paces)})")
    print("  >> §8d regular-season high-pace cutoff was 101.9. Fraction of playoff AST bets "
          f"above 101.9 = {np.mean([p>101.9 for p in paces])*100:.0f}%")
    out["playoff_ast_pace"] = {"median": round(float(np.median(paces)), 1),
                               "mean": round(float(np.mean(paces)), 1),
                               "frac_above_101_9": round(float(np.mean([p > 101.9 for p in paces])), 3),
                               "n": len(paces)}

    # H-PACE (b): does the pace tilt survive in playoffs? terciles by opp_pace.
    valid = [r for r in po_ast if pace_of(r) > 0]
    if len(valid) >= 12:
        ps = np.array([pace_of(r) for r in valid])
        t1, t2 = np.percentile(ps, [33.3, 66.6])
        lo_p = [r for r in valid if pace_of(r) <= t1]
        mid_p = [r for r in valid if t1 < pace_of(r) <= t2]
        hi_p = [r for r in valid if pace_of(r) > t2]
        print(f"\n[H-PACE b] playoff AST by opp_pace tercile (cuts {t1:.1f}, {t2:.1f}):")
        out["playoff_ast_by_pace"] = {}
        for lab, grp in [("low", lo_p), ("mid", mid_p), ("high", hi_p)]:
            g = grade(grp)
            out["playoff_ast_by_pace"][lab] = g
            print(f"  {lab:<5} n={g['n']:>3} win={g['win']:>5.1f}% ROI={g['roi']:>+7.2f}% "
                  f"CI[{g['ci'][0]:+.0f},{g['ci'][1]:+.0f}] P(<=0)={g['p_le0']:.2f}")
        print("  >> §8d reg-season: high-pace AST +43.8% (robust). If high-pace playoff AST is "
              "NOT clearly positive, the pace fuel is gone -> mechanism confirmed.")

    # H-MIN: minutes-surprise band, playoff AST vs the full regular-season dataset.
    ms_po = [minsurprise(r) for r in po_ast]
    ms_po = [m for m in ms_po if m is not None]
    # regular-season reference straight from the dataset rows attached
    from src.prediction.prop_pergame import build_pergame_dataset
    rows, _ = build_pergame_dataset(min_prior=0)
    reg = [r for r in rows if "2025-11" <= str(r["date"])[:7] <= "2026-03"]

    def ms_dataset(r):
        tm, l10 = r.get("target_min"), r.get("l10_min")
        if tm is None or l10 is None:
            return None
        return abs(float(tm) - float(l10))
    ms_reg = [ms_dataset(r) for r in reg]
    ms_reg = [m for m in ms_reg if m is not None]
    print(f"\n[H-MIN] |actual_min - l10_min| (minutes-surprise the model can't see):")
    print(f"  regular-season 2025-26 dataset: median={np.median(ms_reg):.2f} "
          f"mean={np.mean(ms_reg):.2f}  (n={len(ms_reg):,})")
    print(f"  2026 playoff AST bets:          median={np.median(ms_po):.2f} "
          f"mean={np.mean(ms_po):.2f}  (n={len(ms_po)})")
    print("  >> if playoff surprise is NOT smaller, the 'tighter rotations help the model' "
          "story is FALSE and the break is not a minutes-predictability story.")
    out["minutes_surprise"] = {"reg_median": round(float(np.median(ms_reg)), 2),
                               "reg_mean": round(float(np.mean(ms_reg)), 2),
                               "po_median": round(float(np.median(ms_po)), 2),
                               "po_mean": round(float(np.mean(ms_po)), 2)}

    # model vs line MAE in playoffs (is the model simply worse at predicting playoff AST?)
    mmae = np.mean([abs(r["pred"] - r["actual"]) for r in po_ast])
    lmae = np.mean([abs(r["line"] - r["actual"]) for r in po_ast])
    print(f"\n[accuracy] playoff AST model MAE={mmae:.3f} vs line MAE={lmae:.3f}  "
          f"(model {'beats' if mmae<lmae else 'TRAILS'} the line by {lmae-mmae:+.3f})")
    out["playoff_ast_mae"] = {"model": round(float(mmae), 3), "line": round(float(lmae), 3)}

    # =============================================================
    # SUB-POLICIES (robust survivor hunt)
    # =============================================================
    print("\n" + "=" * 64)
    print("SUB-POLICY survivor hunt — 2026 playoff AST (real odds)")
    print("=" * 64)
    policies = {
        "ALL": None,
        "UNDER-only": lambda r: r["pred"] < r["line"],
        "OVER-only": lambda r: r["pred"] > r["line"],
        "gated(edge>=0.75,line<=7.5)": lambda r: abs(r["pred"] - r["line"]) >= 0.75 and r["line"] <= 7.5,
        "low-line(<=4.5)": lambda r: r["line"] <= 4.5,
        "high-pace(>101.9)": lambda r: pace_of(r) > 101.9,
        "high-pace+gated": lambda r: pace_of(r) > 101.9 and abs(r["pred"] - r["line"]) >= 0.75 and r["line"] <= 7.5,
    }
    out["subpolicies_2026po"] = {}
    for name, fil in policies.items():
        g = grade(po_ast, fil)
        out["subpolicies_2026po"][name] = g
        verdict = "POSITIVE" if g["roi"] > 0 and g["p_le0"] < 0.5 else "neg/weak"
        print(f"  {name:<30} n={g['n']:>3} win={g['win']:>5.1f}% ROI={g['roi']:>+7.2f}% "
              f"CI[{g['ci'][0]:+.0f},{g['ci'][1]:+.0f}] P(<=0)={g['p_le0']:.2f}  {verdict}")

    json.dump(out, open(_ROOT / "data" / "cache" / "playoff_ast_mechanism.json", "w"), indent=2)
    print("\nwrote data/cache/playoff_ast_mechanism.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
