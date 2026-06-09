"""SIGNAL EDGE -- the missing half of the lab: does a signal convert to MONEY vs real lines?

`signal_lab.py` grades ACCURACY (held-out rmse/logloss lift). But accuracy != edge -- the marginal point
predictions are at the market-efficient ceiling, so an accuracy win usually does NOT become ROI (proven the
hard way: CV_LOWSHRINK_BLEND lowered REB MAE yet HURT ROI; vac signals netted ~null; calibration KILLS the
AST edge). This module grades the other axis -- ROI/hit vs REAL book lines + vig -- with the same surgical
discipline: bootstrap CI, multiple INDEPENDENT corpora must agree, and the playoff regime is reported
SEPARATELY (it is where the model loses; pooling it with the regular season would launder the truth).

Substrate = the cross-time prop OOF corpora with real odds (`data/cache/pit/crosstime_oof_*_oddsapi.parquet`):
each row = (date, pid, stat, line, over_odds, under_odds, actual, pred, + rest/b2b/home/l10_min/std_min).

THE EDGE GATES (a bet-selection signal is EDGE only if all hold):
  1. PROFITABLE   the selected bets' ROI bootstrap-CI lower bound > 0 (genuinely beats the vig, not noise).
  2. REPLICATES   positive in >=2 INDEPENDENT regular-season corpora (one season/stat can fluke).
  3. LIFTS        the filtered ROI beats the unfiltered baseline (the signal CONCENTRATES edge).
  4. MATERIAL n   >= MIN_BETS selected (so the CI means something).
Playoffs: graded + printed, NEVER counted toward the verdict (small-n, negative regime = the Finals reality).

  python scripts/team_system/signal_edge.py --baseline      # the honest ROI map per stat x regime
  python scripts/team_system/signal_edge.py --screen        # screen bet-selection filters for concentrated edge
"""
from __future__ import annotations
import glob, os, sys
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIT = os.path.join(ROOT, "data", "cache", "pit")
REG = os.path.join(ROOT, "data", "registry", "signal_edge_registry.parquet")
MIN_BETS = 40            # below this the ROI CI is meaningless
DEFAULT_THRESH = 1.0     # only bet when |pred - line| >= this (the model claims real value)


def _profit(odds):
    """American odds -> net profit per 1u on a win."""
    odds = np.asarray(odds, float)
    return np.where(odds > 0, odds / 100.0, 100.0 / np.abs(odds))


def _returns(df, thresh, pred="pred", mask=None):
    """Per-bet net returns (1u stake) for the value-bet policy on rows passing the optional mask."""
    d = df.dropna(subset=["line", "over_odds", "under_odds", "actual", pred]).copy()
    if mask is not None:
        d = d[mask.loc[d.index]] if hasattr(mask, "loc") else d[mask]
    edge = d[pred] - d.line
    bet = d[np.abs(edge) >= thresh]
    if not len(bet):
        return np.array([]), np.array([], bool)
    side_over = (bet[pred] > bet.line).values
    win = np.where(side_over, bet.actual.values > bet.line.values, bet.actual.values < bet.line.values)
    push = bet.actual.values == bet.line.values
    od = np.where(side_over, bet.over_odds.values, bet.under_odds.values).astype(float)
    ret = np.where(push, 0.0, np.where(win, _profit(od), -1.0))
    return ret, push


def _boot_ci(ret, nboot=2000, seed=0):
    """95% bootstrap CI on mean ROI (%)."""
    if len(ret) < 5:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = [ret[rng.integers(0, len(ret), len(ret))].mean() for _ in range(nboot)]
    return (float(np.percentile(means, 2.5) * 100), float(np.percentile(means, 97.5) * 100))


def grade(df, thresh=DEFAULT_THRESH, pred="pred", mask=None):
    ret, push = _returns(df, thresh, pred, mask)
    if not len(ret):
        return dict(n=0, hit=0.0, roi=0.0, ci_lo=float("nan"), ci_hi=float("nan"))
    live = ~push
    lo, hi = _boot_ci(ret)
    return dict(n=int(len(ret)), hit=float(np.mean((ret > 0)[live]) * 100 if live.sum() else 0),
                roi=float(ret.mean() * 100), ci_lo=lo, ci_hi=hi)


def corpora():
    out = []
    for f in sorted(glob.glob(os.path.join(PIT, "crosstime_oof_*_oddsapi.parquet"))):
        base = os.path.basename(f).replace("crosstime_oof_", "").replace("_oddsapi.parquet", "")
        stat = base.split("_")[0]
        regime = "playoffs" if "playoffs" in base else "regular"
        out.append(dict(name=base, path=f, stat=stat, regime=regime, df=pd.read_parquet(f)))
    return out


# --- bet-selection filters to screen: WHERE does the model's edge concentrate? ---
def _filters(df):
    sm = df.std_min
    med = sm.median()
    return {
        "all":          pd.Series(True, index=df.index),
        "home":         df.is_home == 1,
        "away":         df.is_home == 0,
        "rested(>=2)":  df.rest_days >= 2,
        "b2b":          df.is_b2b == 1,
        "stable_min":   sm <= med,                 # minutes-surprise is the dominant error -> stable = reliable
        "volatile_min": sm > med,
        "starter(>=30)": df.l10_min >= 30,
    }


def baseline(thresh=DEFAULT_THRESH):
    print(f"=== EDGE BASELINE (value-bet |pred-line|>= {thresh}, real odds+vig, 95% bootstrap CI) ===")
    print(f"{'corpus':34s} {'n':>4s} {'hit%':>6s} {'ROI%':>7s} {'CI95 (ROI)':>18s}")
    for c in corpora():
        g = grade(c["df"], thresh)
        tag = "  <- PLAYOFF (not counted)" if c["regime"] == "playoffs" else ""
        print(f"{c['name']:34s} {g['n']:4d} {g['hit']:6.1f} {g['roi']:+7.2f}  [{g['ci_lo']:+6.2f},{g['ci_hi']:+6.2f}]{tag}")


def screen(thresh=DEFAULT_THRESH, record=True):
    rows = []
    cs = corpora()
    fnames = list(_filters(cs[0]["df"]).keys())
    print(f"=== EDGE FILTER SCREEN (where does edge concentrate? value-bet thr {thresh}) ===")
    for fn in fnames:
        print(f"\n-- filter: {fn} --")
        reg_rois, reg_lo_ok = [], []
        for c in cs:
            f = _filters(c["df"])[fn]
            g = grade(c["df"], thresh, mask=f)
            base = grade(c["df"], thresh)
            lift = g["roi"] - base["roi"]
            star = " EDGE?" if (c["regime"] == "regular" and g["n"] >= MIN_BETS and g["ci_lo"] > 0 and lift > 0) else ""
            print(f"   {c['name']:34s} n={g['n']:4d} ROI {g['roi']:+6.2f} (base {base['roi']:+6.2f}, "
                  f"lift {lift:+5.2f}) CI[{g['ci_lo']:+6.2f},{g['ci_hi']:+6.2f}]{star}")
            if c["regime"] == "regular":
                reg_rois.append(g["roi"]); reg_lo_ok.append(g["n"] >= MIN_BETS and g["ci_lo"] > 0 and lift > 0)
            rows.append(dict(signal=fn, corpus=c["name"], stat=c["stat"], regime=c["regime"],
                             n=g["n"], roi=round(g["roi"], 2), ci_lo=round(g["ci_lo"], 2),
                             ci_hi=round(g["ci_hi"], 2), base_roi=round(base["roi"], 2), lift=round(lift, 2)))
        verdict = "EDGE" if sum(reg_lo_ok) >= 2 else "NO-EDGE"
        print(f"   => {verdict} (profitable+lifting+CI>0 in {sum(reg_lo_ok)} of {len(reg_lo_ok)} reg-season corpora; "
              f"need >=2; playoffs excluded)")
    if record and rows:
        os.makedirs(os.path.dirname(REG), exist_ok=True)
        pd.DataFrame(rows).to_parquet(REG, index=False)
        print(f"\nedge registry -> {REG} ({len(rows)} rows)")


if __name__ == "__main__":
    th = DEFAULT_THRESH
    if "--thresh" in sys.argv:
        th = float(sys.argv[sys.argv.index("--thresh") + 1])
    if "--screen" in sys.argv:
        screen(th)
    else:
        baseline(th)
        if "--all" in sys.argv:
            print(); screen(th)
