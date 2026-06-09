"""exp_usage_transfer.py — PLAYER-SPECIFIC next-man-up transfer for the BENEFICIARY.

HYPOTHESIS (basketball): the leak-free pred substrate already carries AGGREGATE
vacated load (vac_min / vac_pts / n_out in calibration_frame_v2), but NOT
player-SPECIFIC transfer. When a specific high-usage teammate sits, his
touches/shots/assists flow to SPECIFIC remaining teammates per usage structure;
the magnitude for a given BENEFICIARY can exceed/differ from the team aggregate.

We build, leak-free & as-of, a beneficiary-specific "absorption" signal:
  for each (team, date):
    absent regulars  = recent-roster players (played >=1 of prev 3 team-games,
                       as-of L10 min >= 15) who did NOT appear in this team-game
    vac_pts = sum(absent.L10_pts) ; vac_ast = sum(absent.L10_ast)   (leak-free)
  for each player who PLAYED:
    share_pts = own.L10_pts / sum(L10_pts over players who played)
    share_ast = own.L10_ast / sum(L10_ast over players who played)
    absorb_pts = share_pts * vac_pts   # beneficiary-specific expected PTS inflow
    absorb_ast = share_ast * vac_ast   # beneficiary-specific expected AST inflow

`absorb_*` is PLAYER-SPECIFIC: two beneficiaries on the same team-date with the
same vac_pts get DIFFERENT absorb_pts (by usage rank). That is the thing the
aggregate vac_* the model already has cannot express.

STRICT METHOD (per PREDICTION_HARNESS_GUIDE.md):
  (1) leak-free as-of signal (L10 from prior games only).
  (2) ORTHOGONALITY PRE-SCREEN: corr(signal, actual-pred) on the joined set.
      The honest control = vac_pts / vac_ast aggregate. We require the
      PLAYER-SPECIFIC absorb_* to add residual correlation BEYOND aggregate vac_*
      (partial corr controlling for vac_*), else the model already has it -> REJECT.
  (3) if orthogonal: pred_adj = pred + beta*signal (beta from EARLY half),
      grade ROI(pred_adj) vs ROI(pred) on HELD-OUT LATE half via intel_grade.
  (4) >=2 INDEPENDENT corpora: Family A (extended_oos) + Family C (oddsapi 2024-25).
  (5) VERDICT: SHARPENS / NO-LIFT / REJECT with the numbers.

Read-only except prints; writes nothing. Run:
  conda run -n basketball_ai python scripts/pit/exp_usage_transfer.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, os.path.join(str(_ROOT), "scripts", "pit"))
import intel_grade as ig  # noqa: E402

# corpus -> the gamelog season tag whose box-logs we mine for absorption.
# (extended_oos joined set is 2025-26 reg; oddsapi 2024-25 is 2024-25 reg.)
CORPUS_SEASON = {
    "extended_oos_canonical.csv": "2025-26",
    "benashkar_2026_canonical.csv": "2025-26",
    "regular_season_2025_26_oddsapi.csv": "2025-26",
    "regular_season_2024_25_oddsapi.csv": "2024-25",
}


# ----------------------------------------------------------------------------
# Leak-free signal builder (box-appearance route; generalizes exp_teammate_out)
# ----------------------------------------------------------------------------
def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _team_of(matchup):
    if not matchup:
        return None
    if " @ " in matchup:
        return matchup.split(" @ ")[0].strip()
    if " vs. " in matchup:
        return matchup.split(" vs. ")[0].strip()
    return None


def build_absorption(season: str) -> dict:
    """Return {(pid, 'YYYY-MM-DD'): {...signal...}} for the given gamelog season.

    Leak-free: every per-player L10 stat is computed from that player's STRICTLY
    PRIOR games. vac_* uses absent regulars' prior-L10; absorb_* uses the
    beneficiary's prior-L10 usage share among players who played.
    """
    rows_by_td = defaultdict(list)  # (team,date) -> list of player records who PLAYED
    files = glob.glob(str(_ROOT / "data" / "nba" / f"gamelog_*_{season}.json"))
    for fp in files:
        try:
            pid = int(Path(fp).stem.split("_")[1])
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        recs = []
        for g in log:
            d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
            if pd.isna(d):
                continue
            recs.append((d, g))
        recs.sort(key=lambda kv: kv[0])
        mins, ptss, astss = [], [], []
        for d, g in recs:
            team = _team_of(g.get("MATCHUP"))
            # as-of L10 BEFORE this game (prior only)
            l10_min = float(np.mean(mins[-10:])) if mins else 0.0
            l10_pts = float(np.mean(ptss[-10:])) if ptss else 0.0
            l10_ast = float(np.mean(astss[-10:])) if astss else 0.0
            m = _f(g.get("MIN"))
            played = m is not None and m >= 1
            ds = d.date().isoformat()
            if team and played:
                rows_by_td[(team, ds)].append({
                    "pid": pid, "l10_min": l10_min,
                    "l10_pts": l10_pts, "l10_ast": l10_ast})
            # update history AFTER recording the as-of values
            if played:
                mins.append(m)
                ptss.append(_f(g.get("PTS")) or 0.0)
                astss.append(_f(g.get("AST")) or 0.0)

    # team -> sorted dates (chronological)
    team_dates = defaultdict(list)
    for (team, ds) in rows_by_td:
        team_dates[team].append(ds)
    for t in team_dates:
        team_dates[t] = sorted(set(team_dates[t]))

    # last-seen L10 record per (team, pid) up to a date index -> recent roster
    def recent_roster(team, idx):
        dates = team_dates[team]
        roster = {}
        for j in range(max(0, idx - 3), idx):
            for rec in rows_by_td[(team, dates[j])]:
                roster[rec["pid"]] = rec  # last-seen prior L10 carries
        return roster

    out = {}
    for (team, ds), played in rows_by_td.items():
        dates = team_dates[team]
        i = dates.index(ds)
        if i < 3:
            continue  # need 3 prior team-games for a stable roster
        played_ids = {r["pid"] for r in played}
        roster = recent_roster(team, i)

        # absent regulars -> vacated load (leak-free, prior L10)
        vac_pts = vac_ast = vac_min = 0.0
        n_out = 0
        for pid, rec in roster.items():
            if pid in played_ids:
                continue
            if rec["l10_min"] >= 15:
                vac_pts += rec["l10_pts"]
                vac_ast += rec["l10_ast"]
                vac_min += rec["l10_min"]
                n_out += 1

        # usage denominators among players who PLAYED (prior L10)
        sum_pts = sum(max(r["l10_pts"], 0.0) for r in played) or 1e-9
        sum_ast = sum(max(r["l10_ast"], 0.0) for r in played) or 1e-9

        for r in played:
            share_pts = max(r["l10_pts"], 0.0) / sum_pts
            share_ast = max(r["l10_ast"], 0.0) / sum_ast
            out[(r["pid"], ds)] = {
                "absorb_pts": share_pts * vac_pts,   # beneficiary-specific PTS inflow
                "absorb_ast": share_ast * vac_ast,   # beneficiary-specific AST inflow
                "share_pts": share_pts,
                "share_ast": share_ast,
                "vac_pts_box": vac_pts,              # box-derived aggregate (control)
                "vac_ast_box": vac_ast,
                "n_out_box": float(n_out),
                "own_l10_pts": r["l10_pts"],
                "own_l10_ast": r["l10_ast"],
            }
    return out


def attach_absorption(bets, season):
    sig = build_absorption(season)
    matched = 0
    for b in bets:
        ds = b["gdate"].date().isoformat()
        m = sig.get((b["pid"], ds))
        if m is not None:
            b.update(m)
            matched += 1
        else:
            for k in ("absorb_pts", "absorb_ast", "vac_pts_box", "vac_ast_box",
                      "n_out_box", "share_pts", "share_ast"):
                b.setdefault(k, np.nan)
    print(f"    absorption matched {matched}/{len(bets)} ({100*matched/max(len(bets),1):.0f}%)")
    return bets


# ----------------------------------------------------------------------------
# Stats helpers
# ----------------------------------------------------------------------------
def _arr(bets, key):
    return np.array([b.get(key, np.nan) for b in bets], dtype=float)


def resid_corr(bets, stat, key):
    sub = [b for b in bets if b["stat"] == stat]
    sig = _arr(sub, key)
    pred = _arr(sub, "pred")
    act = np.array([b["actual"] for b in sub], dtype=float)
    resid = act - pred
    m = np.isfinite(sig) & np.isfinite(resid)
    if m.sum() < 30 or np.std(sig[m]) < 1e-9:
        return None, int(m.sum())
    return float(np.corrcoef(sig[m], resid[m])[0, 1]), int(m.sum())


def partial_corr(bets, stat, key, control):
    """corr(signal, resid) AFTER regressing both signal and resid on `control`.
    This is the incremental-info test: does player-specific absorb_* add anything
    beyond the aggregate vac_* the model already has?"""
    sub = [b for b in bets if b["stat"] == stat]
    sig = _arr(sub, key)
    ctrl = _arr(sub, control)
    pred = _arr(sub, "pred")
    act = np.array([b["actual"] for b in sub], dtype=float)
    resid = act - pred
    m = np.isfinite(sig) & np.isfinite(ctrl) & np.isfinite(resid)
    if m.sum() < 40 or np.std(sig[m]) < 1e-9 or np.std(ctrl[m]) < 1e-9:
        return None, int(m.sum())
    s, c, r = sig[m], ctrl[m], resid[m]

    def _resid_on(y, x):
        X = np.column_stack([np.ones_like(x), x])
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        return y - X @ beta
    s_r = _resid_on(s, c)
    r_r = _resid_on(r, c)
    if np.std(s_r) < 1e-9:
        return None, int(m.sum())
    return float(np.corrcoef(s_r, r_r)[0, 1]), int(m.sum())


def fit_beta(rows, stat, key):
    sub = [b for b in rows if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, 0
    sig = np.array([b[key] for b in sub])
    resid = np.array([b["actual"] - b["pred"] for b in sub])
    if np.std(sig) < 1e-9:
        return None, len(sub)
    return float(np.cov(sig, resid)[0, 1] / np.var(sig)), len(sub)


def halves(bets):
    ds = sorted({b["gdate"] for b in bets})
    if len(ds) < 4:
        return [], []
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


# stat -> player-specific absorption signal + the aggregate control the model has
SIGNAL = {"pts": ("absorb_pts", "vac_pts"), "ast": ("absorb_ast", "vac_ast_box")}


def run_corpus(corpus, season, *, screen_only=False):
    print(f"\n{'='*74}\n CORPUS: {corpus}   (box-season {season})\n{'='*74}")
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f" coherence sum {coh['sum']:+.2f}%  ({'OK' if coh['coherent'] else 'CORRUPT'})  joined n={len(bets)}")
    if not coh["coherent"]:
        print(" !! corrupt corpus -> refuse to grade")
        return
    bets = attach_absorption(bets, season)

    results = {}
    for stat, (sig_key, ctrl_key) in SIGNAL.items():
        nstat = len([b for b in bets if b["stat"] == stat and np.isfinite(b.get(sig_key, np.nan))])
        if nstat < 50:
            print(f"\n  --- {stat.upper()}: n={nstat} too thin, skip ---")
            continue
        print(f"\n  --- {stat.upper()}  (n with signal={nstat}) ---")

        # (A) ORTHOGONALITY: raw corr of player-specific signal AND of aggregate control
        r_sig, n1 = resid_corr(bets, stat, sig_key)
        r_ctrl, _ = resid_corr(bets, stat, ctrl_key)
        r_part, npc = partial_corr(bets, stat, sig_key, ctrl_key)
        print(f"   resid corr  player-specific {sig_key:12s} r={_fmt(r_sig)}  (n={n1})")
        print(f"   resid corr  aggregate ctrl  {ctrl_key:12s} r={_fmt(r_ctrl)}")
        print(f"   PARTIAL corr {sig_key} | {ctrl_key}  r={_fmt(r_part)}  (n={npc})"
              f"  {'<-- adds info' if (r_part is not None and abs(r_part) >= 0.05) else '<-- model already has it'}")
        results[stat] = {"r_sig": r_sig, "r_ctrl": r_ctrl, "r_part": r_part}

        if screen_only:
            continue

        # (B) leak-free held-out ROI tilt
        early, late = halves(bets)
        beta, nb = fit_beta(early, stat, sig_key)
        if beta is None:
            print(f"   (beta unfittable on early half, n={nb})")
            continue
        flips = 0
        late_stat = [b for b in late if b["stat"] == stat]
        for b in late_stat:
            if np.isfinite(b.get(sig_key, np.nan)) and np.isfinite(b.get("pred", np.nan)):
                old_dir = b["pred"] > b["line"]
                b["_pred_adj"] = b["pred"] + beta * b[sig_key]
                if (b["_pred_adj"] > b["line"]) != old_dir:
                    flips += 1
        raw = ig.roi(late_stat, predictor="pred")
        adj = ig.roi([b for b in late_stat if "_pred_adj" in b], predictor="_pred_adj")
        print(f"   beta(early)={beta:+.4f} (n={nb})  |  held-out LATE half (n={raw['n']}, flips={flips})")
        print(f"     raw  pred>line ROI = {raw['roi_pct']:+.2f}%  (win {raw['win_pct']:.1f}%, n {raw['n']})")
        print(f"     adj  pred+b*sig ROI = {adj['roi_pct']:+.2f}%  (win {adj['win_pct']:.1f}%, n {adj['n']})")
        lift = adj["roi_pct"] - raw["roi_pct"]
        print(f"     LIFT = {lift:+.2f} pp  {'SHARPENS' if lift > 0.5 else ('NO-LIFT' if abs(lift) <= 0.5 else 'HURTS')}")
        results[stat]["lift"] = lift
        results[stat]["raw_roi"] = raw["roi_pct"]
        results[stat]["adj_roi"] = adj["roi_pct"]
        results[stat]["n_late"] = raw["n"]

        # (C) selection variant: keep only beneficiaries in the TOP tercile of
        # the player-specific inflow (where transfer should matter most), bet raw model
        sub = [b for b in late_stat if np.isfinite(b.get(sig_key, np.nan))]
        if len(sub) >= 30:
            hi = np.nanpercentile(_arr(sub, sig_key), 66.667)
            top = [b for b in sub if b[sig_key] > hi]
            rest = [b for b in sub if b[sig_key] <= hi]
            rt = ig.roi(top, predictor="pred")
            rr = ig.roi(rest, predictor="pred")
            print(f"   selection: TOP-absorb tercile ROI={rt['roi_pct']:+.2f}% (n{rt['n']})  "
                  f"rest ROI={rr['roi_pct']:+.2f}% (n{rr['n']})")
    return results


def _fmt(x):
    return "None" if x is None else f"{x:+.3f}"


if __name__ == "__main__":
    # Family A — the big 2025-26 reg-season joined set
    run_corpus("extended_oos_canonical.csv", "2025-26")
    # Family C — independent cross-season odds-api book (thin, directional)
    run_corpus("regular_season_2024_25_oddsapi.csv", "2024-25")
    # Family B — independent same-season odds-api book (thin, directional)
    run_corpus("regular_season_2025_26_oddsapi.csv", "2025-26")
