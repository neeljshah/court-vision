"""EXPERIMENT (pit, prediction-integration): CONFIRM-or-KILL the blowout-starter-UNDER
SELECTION filter with MORE STATISTICAL POWER via rolling-origin evaluation.

CONTEXT (sibling `PRED_EXP_blowout_minutes_2026-06-01.md`): filtering the model's own
UNDER bets to STARTERS in projected-BLOWOUT games (big as-of SRS mismatch) lifted held-out
late-half ROI to +15.6% (n=45, win 66.7%) on Family A -- but the bootstrap 90% CI included
zero (P(ROI<=0)=0.11) and the thin odds-api corpora couldn't independently confirm. The
MINUTES MECHANISM is confirmed (Q4-blowout starters -2.4 min, monotonic). Single 50/50 split
=> too little power.

THIS SCRIPT gets more power by:
  (A) ROLLING-ORIGIN over the FULL Family A corpus: K time-folds; for fold k, fit the
      blowout-risk top-quartile THRESHOLD on the model's-UNDER STARTER bets strictly BEFORE
      fold k, then apply forward to fold k. Accumulate ALL forward held-out bets (uses ~all
      ~4068 bets leak-free instead of one half). Strictly train-on-past => leak-free.
  (B) POOL Family A + Family C (cross-season odds-api 2024-25) for the same
      blowout-starter-model-UNDER subset, to maximize n and test cross-season replication.
  (C) Re-estimate ROI with a proper percentile bootstrap CI + a coherence check, per-stat.

SIGNAL (leak-free, prior-games only): exp_margin = asof_srs(team) - asof_srs(opp) + HCA*home.
  Family A: asof_srs rebuilt from realized team margins (leaguegamelog, strictly prior games;
  sibling validated corr 0.845 vs season_games as-of srs). Family C: season_games_2024-25
  as-of srs (no local realized-margin log; validated leak-free as-of quantity). blowout = |em|.
SELECTION = model-UNDER (pred < line) AND starter (as-of L10 min >= 28) AND blowout >= thr
  where thr = top-quartile of blowout among STARTER bets fit on the PAST fold(s) only.

VERDICT logic: CONFIRM if the pooled/rolling ROI CI clears 0 AND it replicates cross-season;
KILL if CI still includes 0 / doesn't replicate; INSUFFICIENT if n is still too small even
pooled (report the exact confirmed-blowout-starter-UNDER bet count).

DISCIPLINE: read-only except this file + scratch + the report md; coherence guard; drop
|odds|<100 (grader does it); reg-season corpora only; rolling-origin = strictly fit-on-past;
no git commit. Run: conda run -n basketball_ai python scripts/pit/exp_blowout_rolling.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "pit"))
import intel_grade as ig  # noqa: E402

HCA = 2.5             # home-court points (matches sibling)
STARTER_MIN = 28.0    # as-of L10 minutes threshold for starter (matches sibling)
STATS = ["pts", "reb", "ast"]
QUANTILE = 75.0       # top-quartile blowout-risk threshold (matches sibling)
N_FOLDS = 8           # rolling-origin time folds for Family A
N_BOOT = 20000        # bootstrap resamples for the CI
RNG = np.random.default_rng(20260601)
LGLOG = os.path.join(ROOT, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")


# ============================================================ SRS builders (leak-free)
def build_asof_srs_2025_26():
    """Leak-free strength-adjusted running margin per (team, as-of date) from realized
    margins (strictly prior games). Returns (asof_srs(team,date), pid_team_date)."""
    df = pd.read_parquet(LGLOG)
    df["d"] = pd.to_datetime(df["GAME_DATE"]).dt.normalize()
    tg = df.groupby(["GAME_ID", "d", "TEAM_ABBREVIATION"], as_index=False)["PTS"].sum()
    g = tg.merge(tg, on="GAME_ID", suffixes=("", "_opp"))
    g = g[g["TEAM_ABBREVIATION"] != g["TEAM_ABBREVIATION_opp"]].copy()
    g["margin"] = g["PTS"] - g["PTS_opp"]
    g = g.sort_values(["d", "GAME_ID"]).reset_index(drop=True)
    games = list(g.itertuples(index=False))

    team_hist = defaultdict(list)
    asof_mov = {}
    for r in games:
        prior = team_hist[r.TEAM_ABBREVIATION]
        asof_mov[(r.GAME_ID, r.TEAM_ABBREVIATION)] = float(np.mean(prior)) if prior else 0.0
        team_hist[r.TEAM_ABBREVIATION].append(r.margin)

    opp_hist = defaultdict(list)
    asof_sos = {}
    for r in games:
        prior = opp_hist[r.TEAM_ABBREVIATION]
        asof_sos[(r.GAME_ID, r.TEAM_ABBREVIATION)] = float(np.mean(prior)) if prior else 0.0
        opp_hist[r.TEAM_ABBREVIATION].append(asof_mov.get((r.GAME_ID, r.TEAM_ABBREVIATION_opp), 0.0))

    team_date = defaultdict(list)
    for r in games:
        srs = asof_mov[(r.GAME_ID, r.TEAM_ABBREVIATION)] + 0.5 * asof_sos[(r.GAME_ID, r.TEAM_ABBREVIATION)]
        team_date[r.TEAM_ABBREVIATION].append((r.d, srs))
    for t in team_date:
        team_date[t].sort()

    def asof_srs(team, date):
        arr = team_date.get(team)
        if not arr:
            return None
        val = None
        for dd, s in arr:
            if dd < date:        # strictly before -> leak-free
                val = s
            else:
                break
        return val

    pid_team_date = defaultdict(dict)
    for r in df.itertuples():
        pid_team_date[int(r.PLAYER_ID)][r.d] = r.TEAM_ABBREVIATION
    return asof_srs, pid_team_date


def build_season_games_srs(season):
    """as-of srs + player-team inference per game from season_games_<season>.json
    (leak-free as-of quantity; validated corr 0.845 with realized-margin SRS)."""
    rows = json.load(open(os.path.join(ROOT, "data", "nba", f"season_games_{season}.json"),
                          encoding="utf-8"))["rows"]
    team_date = defaultdict(list)
    games_by_date = defaultdict(list)
    for r in rows:
        if "home_team" not in r or "home_srs" not in r:
            continue
        d = pd.Timestamp(r["game_date"]).normalize()
        team_date[r["home_team"]].append((d, float(r["home_srs"])))
        team_date[r["away_team"]].append((d, float(r["away_srs"])))
        games_by_date[d].append((r["home_team"], r["away_team"]))
    for t in team_date:
        team_date[t].sort()

    def asof_srs(team, date):
        arr = team_date.get(team)
        if not arr:
            return None
        val = None
        for dd, s in arr:
            if dd <= date:       # season_games srs at game-date is pre-game (as-of)
                val = s
            if dd > date:
                break
        return val

    def player_team(opp, venue, date):
        for h, a in games_by_date.get(date, []):
            if h == opp:
                return a
            if a == opp:
                return h
        return None

    return asof_srs, player_team


# ============================================================ signal attachment
def attach_signal(bets, asof_srs, pid_team_date=None, player_team_fn=None):
    """Attach exp_margin/_blowout/_role to each bet. Returns count attached."""
    n = 0
    for b in bets:
        pt = None
        if pid_team_date is not None:
            pt = pid_team_date.get(b["pid"], {}).get(b["gdate"])
        if pt is None and player_team_fn is not None:
            pt = player_team_fn(b["opp"], b.get("venue", ""), b["gdate"])
        if pt is None:
            continue
        s_team = asof_srs(pt, b["gdate"])
        s_opp = asof_srs(b["opp"], b["gdate"])
        if s_team is None or s_opp is None:
            continue
        hca = HCA if b.get("is_home") == 1 else -HCA
        em = s_team - s_opp + hca
        b["_exp_margin"] = em
        b["_blowout"] = abs(em)
        b["_favored"] = 1 if em > 0 else 0
        l10 = b.get("l10_min", np.nan)
        b["_starter"] = bool(np.isfinite(l10) and l10 >= STARTER_MIN)
        n += 1
    return n


# ============================================================ ROI / settle helpers
def _settle_pnl(b):
    """PnL for the model-UNDER bet on b (pred<line forced via under_only at call site).
    Returns +payout (win) or -100 (loss) or None (push). Uses grader settle semantics."""
    res = ig.settle(b, b["pred"])
    if res is None:
        return None
    _, won, payout = res
    return payout


def roi_of(rows):
    """ROI% over a list of bets, betting model direction (pred>line). Mirrors ig.roi."""
    r = ig.roi(rows, predictor="pred")
    return r


def bootstrap_ci(pnls, n_boot=N_BOOT, lo=5.0, hi=95.0):
    """Percentile bootstrap CI on mean PnL per 100u staked -> ROI%. Each bet stakes 100u;
    ROI% = mean(pnl)/100*100 = mean(pnl). pnl already in 'per-100-stake' units (+decimal*100
    or -100), so ROI% = mean(pnls)/100*100... wait: ig pnl sums payout where win=+dec*100,
    loss=-100; ROI% = pnl/(n*100)*100 = mean(pnls)/100*100 = mean(pnls). Keep mean(pnls)/1.0
    consistent with ig.roi: roi_pct = pnl/(n*100)*100 => mean(pnls)/100*100? No.
    ig: roi_pct = pnl/(n*100)*100. pnl=sum(pnls). => roi_pct = mean(pnls)/100*100 = mean(pnls).
    So ROI% == mean(pnls). Bootstrap the mean of pnls directly."""
    pnls = np.asarray(pnls, dtype=float)
    n = len(pnls)
    if n == 0:
        return None
    idx = RNG.integers(0, n, size=(n_boot, n))
    means = pnls[idx].mean(axis=1)            # ROI% per resample
    p_le0 = float((means <= 0).mean())
    return {
        "roi": float(pnls.mean()),
        "ci90": (float(np.percentile(means, lo)), float(np.percentile(means, hi))),
        "ci95": (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))),
        "p_le0": p_le0,
        "n": n,
    }


# ============================================================ rolling-origin selection
def select_blowout_under(bets, thr):
    """The selection rule applied with a GIVEN blowout threshold thr:
    model-UNDER (pred<line) AND starter AND blowout>=thr. Returns the selected bets."""
    out = []
    for b in bets:
        if not b.get("_starter"):
            continue
        if not np.isfinite(b.get("_blowout", np.nan)):
            continue
        if b["_blowout"] < thr:
            continue
        if not (b["pred"] < b["line"]):        # model-UNDER only
            continue
        out.append(b)
    return out


def starter_blowouts(rows):
    """Blowout values among STARTER bets (the population the threshold is fit on)."""
    return np.array([b["_blowout"] for b in rows
                     if b.get("_starter") and np.isfinite(b.get("_blowout", np.nan))], dtype=float)


def rolling_origin(sig_bets, n_folds=N_FOLDS, min_train_starters=60):
    """Rolling-origin: sort by date, cut into n_folds equal-date blocks. For each fold k>=1,
    fit thr = top-quartile blowout among STARTER bets strictly before fold k, apply to fold k.
    Returns (selected_held_out_bets, per_fold_log). Strictly train-on-past => leak-free."""
    ds = sorted({b["gdate"] for b in sig_bets})
    if len(ds) < n_folds + 1:
        n_folds = max(2, len(ds) // 2)
    # equal-size date blocks
    edges = [ds[int(round(i * len(ds) / n_folds))] for i in range(n_folds)] + [ds[-1] + pd.Timedelta(days=1)]
    blocks = []
    for i in range(n_folds):
        lo, hi = edges[i], edges[i + 1]
        blocks.append([b for b in sig_bets if lo <= b["gdate"] < hi])
    selected = []
    log = []
    for k in range(1, n_folds):
        train = [b for r in blocks[:k] for b in r]
        test = blocks[k]
        bl = starter_blowouts(train)
        if len(bl) < min_train_starters:
            log.append({"fold": k, "skipped": "thin-train", "n_train_starters": int(len(bl))})
            continue
        thr = float(np.percentile(bl, QUANTILE))
        sel = select_blowout_under(test, thr)
        selected.extend(sel)
        r = roi_of(sel)
        log.append({"fold": k, "thr": thr, "n_train_starters": int(len(bl)),
                    "n_test": len(test), "n_selected": r["n"], "roi": r["roi_pct"],
                    "win": r["win_pct"]})
    return selected, log


# ============================================================ corpus loaders
def load_family_a():
    bets = ig.prepare("benashkar_2026_canonical.csv")
    asof, pid_team_date = build_asof_srs_2025_26()
    attach_signal(bets, asof, pid_team_date=pid_team_date)
    return [b for b in bets if "_blowout" in b], ig.coherence(bets)


def load_family_c():
    bets = ig.prepare("regular_season_2024_25_oddsapi.csv")
    asof, pteam = build_season_games_srs("2024-25")
    attach_signal(bets, asof, player_team_fn=pteam)
    return [b for b in bets if "_blowout" in b], ig.coherence(bets)


def load_family_b():
    bets = ig.prepare("regular_season_2025_26_oddsapi.csv")
    asof, pid_team_date = build_asof_srs_2025_26()
    attach_signal(bets, asof, pid_team_date=pid_team_date)
    return [b for b in bets if "_blowout" in b], ig.coherence(bets)


def pnls_of(rows):
    """Per-bet PnL list (model direction) for bootstrap. Drops pushes."""
    out = []
    for b in rows:
        p = _settle_pnl(b)
        if p is not None:
            out.append(p)
    return out


def fmt_ci(d):
    if d is None:
        return "n=0"
    (l90, h90) = d["ci90"]
    (l95, h95) = d["ci95"]
    return (f"ROI {d['roi']:+.2f}% n={d['n']} | 90% CI [{l90:+.1f},{h90:+.1f}] "
            f"95% CI [{l95:+.1f},{h95:+.1f}] | P(ROI<=0)={d['p_le0']:.3f}")


# ============================================================ MAIN
def main():
    print("=" * 80)
    print("BLOWOUT-STARTER-UNDER selection filter -- ROLLING-ORIGIN power test")
    print("=" * 80)

    # ---------- Family A ----------
    print("\n### FAMILY A (benashkar DK/FD/MGM 2025-26, realized-margin SRS) ###")
    A, cohA = load_family_a()
    print(f" coherence sum {cohA['sum']:+.2f}% ({'OK' if cohA['coherent'] else 'CORRUPT'}); "
          f"signal-attached n={len(A)}")
    assert cohA["coherent"], "Family A corpus corrupt -- refuse to grade"
    n_starter_A = sum(1 for b in A if b.get("_starter"))
    n_su_A = sum(1 for b in A if b.get("_starter") and b["pred"] < b["line"])
    print(f" starters={n_starter_A}  starter-UNDER={n_su_A}")

    selA, logA = rolling_origin(A, n_folds=N_FOLDS)
    print(f"\n [A.rolling-origin] {N_FOLDS} time-folds, fit-thr-on-past forward to each:")
    for e in logA:
        if "skipped" in e:
            print(f"   fold {e['fold']}: SKIP ({e['skipped']}, train-starters={e['n_train_starters']})")
        else:
            print(f"   fold {e['fold']}: thr={e['thr']:5.2f} train-starters={e['n_train_starters']:4d} "
                  f"test={e['n_test']:4d} -> selected={e['n_selected']:3d} "
                  f"ROI={e['roi']:+7.2f}% win={e['win']:5.1f}%")
    pnlA = pnls_of(selA)
    ciA = bootstrap_ci(pnlA)
    print(f"\n [A.rolling-origin POOLED] {fmt_ci(ciA)}")
    # coherence on the selected slice (blind O+U should be negative if odds sane)
    cohAsel = ig.coherence(selA)
    print(f"   selected-slice coherence: blind-O {cohAsel['over']['roi_pct']:+.1f}% + "
          f"blind-U {cohAsel['under']['roi_pct']:+.1f}% = {cohAsel['sum']:+.1f}% "
          f"({'OK' if cohAsel['coherent'] else 'CHECK'})")
    # per-stat on the rolling-origin selected slice
    print("   per-stat (rolling-origin selected):")
    for s in STATS:
        sub = [b for b in selA if b["stat"] == s]
        r = roi_of(sub)
        ci = bootstrap_ci(pnls_of(sub))
        print(f"     {s:4s} {fmt_ci(ci) if ci else 'n=0'}")

    # ---------- Family C (cross-season replication) ----------
    print("\n### FAMILY C (odds-api 2024-25, cross-season, season_games SRS) ###")
    C, cohC = load_family_c()
    print(f" coherence sum {cohC['sum']:+.2f}% ({'OK' if cohC['coherent'] else 'CORRUPT'}); "
          f"signal-attached n={len(C)}")
    if cohC["coherent"]:
        n_starter_C = sum(1 for b in C if b.get("_starter"))
        n_su_C = sum(1 for b in C if b.get("_starter") and b["pred"] < b["line"])
        print(f" starters={n_starter_C}  starter-UNDER={n_su_C}")
        # C is thin -> single global threshold fit on A's starter blowouts (cross-corpus,
        # no in-sample fit on C), AND a within-C rolling check if it has enough dates.
        thrA = float(np.percentile(starter_blowouts(A), QUANTILE))
        selC_thrA = select_blowout_under(C, thrA)
        rC = roi_of(selC_thrA)
        ciC = bootstrap_ci(pnls_of(selC_thrA))
        print(f" [C @ A-fit thr={thrA:.2f}] selected n={rC['n']} -> {fmt_ci(ciC) if ciC else 'n=0'}")
        selC_roll, logC = rolling_origin(C, n_folds=4, min_train_starters=30)
        rCr = roi_of(selC_roll)
        ciCr = bootstrap_ci(pnls_of(selC_roll))
        print(f" [C rolling-origin 4-fold] selected n={rCr['n']} -> {fmt_ci(ciCr) if ciCr else 'n=0'}")
        for e in logC:
            if "skipped" in e:
                print(f"   fold {e['fold']}: SKIP ({e['skipped']})")
            else:
                print(f"   fold {e['fold']}: thr={e['thr']:5.2f} selected={e['n_selected']} "
                      f"ROI={e['roi']:+.2f}% win={e['win']:.1f}%")
    else:
        selC_thrA = []
        print(" !! Family C corrupt, skip")

    # ---------- Family B (same-season independent book, supplementary) ----------
    print("\n### FAMILY B (odds-api 2025-26, independent book, supplementary) ###")
    B, cohB = load_family_b()
    print(f" coherence sum {cohB['sum']:+.2f}% ({'OK' if cohB['coherent'] else 'CORRUPT'}); "
          f"signal-attached n={len(B)}")
    selB = []
    if cohB["coherent"]:
        thrA = float(np.percentile(starter_blowouts(A), QUANTILE))
        selB = select_blowout_under(B, thrA)
        rB = roi_of(selB)
        ciB = bootstrap_ci(pnls_of(selB))
        print(f" [B @ A-fit thr={thrA:.2f}] selected n={rB['n']} -> {fmt_ci(ciB) if ciB else 'n=0'}")

    # ---------- POOLED A + C (max-n cross-season subset) ----------
    print("\n### POOLED  Family A (rolling-origin) + Family C (A-fit thr) ###")
    pooled = selA + (selC_thrA if cohC["coherent"] else [])
    ciP = bootstrap_ci(pnls_of(pooled))
    print(f" [A+C POOLED] {fmt_ci(ciP)}")
    print("   per-stat (pooled A+C):")
    for s in STATS:
        sub = [b for b in pooled if b["stat"] == s]
        ci = bootstrap_ci(pnls_of(sub))
        print(f"     {s:4s} {fmt_ci(ci) if ci else 'n=0'}")

    # ---------- POOLED A+B+C (all independent reg-season) ----------
    poolABC = selA + (selC_thrA if cohC["coherent"] else []) + (selB if cohB["coherent"] else [])
    ciABC = bootstrap_ci(pnls_of(poolABC))
    print(f"\n [A+B+C POOLED all reg-season] {fmt_ci(ciABC)}")

    # ---------- SUMMARY ----------
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f" Family A rolling-origin (all forward bets): {fmt_ci(ciA)}")
    print(f" Family C @ A-fit thr (cross-season):        {fmt_ci(ciC) if cohC['coherent'] and ciC else 'n=0'}")
    print(f" Pooled A+C:                                  {fmt_ci(ciP)}")
    print(f" Pooled A+B+C:                                {fmt_ci(ciABC)}")
    # verdict heuristic
    confirm_A = ciA is not None and ciA["ci90"][0] > 0
    replicate_C = (cohC["coherent"] and ciC is not None and ciC["n"] >= 30 and ciC["roi"] > 0)
    confirm_pool = ciP is not None and ciP["ci90"][0] > 0
    if confirm_A and (replicate_C or confirm_pool):
        verdict = "CONFIRM"
    elif (ciP is None) or (ciP["n"] < 60):
        verdict = "INSUFFICIENT"
    else:
        verdict = "KILL"
    print(f"\n VERDICT(auto-heuristic): {verdict}")
    print(f"   confirmed-blowout-starter-UNDER bets: A-rolling={ciA['n'] if ciA else 0}, "
          f"C={ciC['n'] if (cohC['coherent'] and ciC) else 0}, "
          f"pooledA+C={ciP['n'] if ciP else 0}")


if __name__ == "__main__":
    main()
