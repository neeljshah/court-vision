"""ast_edge_decomposition.py — is the AST +7% a real model edge or an UNDER-bias artifact?

The entire bettable pregame book now rests on AST (docs/VS_VEGAS_ASSESSMENT.md §7).
That stat is flagged "period-unstable", and the same session proved the headline
+18.38% was a market-follow artifact. Before sizing real money on AST, decompose the
edge into skill vs. directional tilt. Decisive tests, all on the real benashkar closes
at ACTUAL posted odds (settle() already prices real odds):

  1. Direction split: is the edge in OVER bets, UNDER bets, or both?
  2. Baselines: always-OVER / always-UNDER on the SAME AST slate (model direction ignored).
  3. Anti-model: flip every model call. A skilled model must LOSE when flipped.
  4. Line bias: mean(actual - line) — are AST lines just set low so blind-UNDER wins?
  5. Player concentration: ROI with the top-K most-bet players removed (overfit check).
  6. Bootstrap 95% CI on ROI (resample bets w/ replacement) — is it distinguishable from 0?
  7. Temporal: early vs late half sanity.

No production model touched. Read-only on data/cache + data/lines archives.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
from scripts.run_gate1_full_analysis import (  # noqa: E402
    load_benashkar_bets, attach_actuals_and_l10, attach_oof, settle, _payout)

RNG = np.random.default_rng(20260601)


def ast_bets():
    raw = attach_oof(attach_actuals_and_l10(load_benashkar_bets(mainline_only=True)))
    bets = [b for b in raw if b["stat"] == "ast"]
    return sorted(bets, key=lambda b: b["gdate"])


def roi_of(settled):
    """settled: list of (won, payout). ROI = sum(payout)/(n*100)*100."""
    n = len(settled)
    if not n:
        return 0, 0.0, 0.0
    pnl = sum(p for _, p in settled)
    w = sum(int(won) for won, _ in settled)
    return n, w / n * 100.0, pnl / (n * 100.0) * 100.0


def settle_model(b):
    """Model's own call (pred vs line) at real odds. Returns (won, payout) or None."""
    r = settle(b, b["pred_oof"])
    if r is None:
        return None
    _, won, pay = r
    return won, pay


def settle_forced(b, force_over):
    """Bet a forced direction at that side's real odds. Returns (won, payout) or None."""
    line, actual = b["line"], b["actual"]
    if abs(actual - line) < 1e-9:
        return None  # push
    won = (force_over and actual > line) or (not force_over and actual < line)
    odds = b["over_odds"] if force_over else b["under_odds"]
    return won, _payout(odds, won)


def main():
    bets = ast_bets()
    print(f"AST bets (real benashkar closes, joined to OOF): n={len(bets):,}")
    mid = bets[len(bets) // 2]["gdate"]
    print(f"date span: {bets[0]['gdate'].date()} .. {bets[-1]['gdate'].date()}  "
          f"(mid={mid.date()})\n")

    # ── 1. model edge + direction split ──────────────────────────────
    model = [(b, settle_model(b)) for b in bets]
    model = [(b, s) for b, s in model if s is not None]
    overs = [s for b, s in model if b["pred_oof"] > b["line"]]
    unders = [s for b, s in model if b["pred_oof"] < b["line"]]
    n_all, win_all, roi_all = roi_of([s for _, s in model])
    n_o, win_o, roi_o = roi_of(overs)
    n_u, win_u, roi_u = roi_of(unders)
    print("── 1. MODEL EDGE BY DIRECTION (real odds) ──")
    print(f"  ALL model calls : n={n_all:,}  win={win_all:.1f}%  ROI={roi_all:+.2f}%")
    print(f"  model says OVER : n={n_o:,}  win={win_o:.1f}%  ROI={roi_o:+.2f}%   "
          f"({n_o/n_all*100:.0f}% of bets)")
    print(f"  model says UNDER: n={n_u:,}  win={win_u:.1f}%  ROI={roi_u:+.2f}%   "
          f"({n_u/n_all*100:.0f}% of bets)")
    print("  >> If edge lives ONLY in UNDER, it's a directional bias, not skill.\n")

    # ── 2. blind baselines on the SAME slate ─────────────────────────
    blind_over = [s for s in (settle_forced(b, True) for b in bets) if s is not None]
    blind_under = [s for s in (settle_forced(b, False) for b in bets) if s is not None]
    print("── 2. BLIND BASELINES (model direction ignored) ──")
    print(f"  always OVER : n={len(blind_over):,}  win={roi_of(blind_over)[1]:.1f}%  "
          f"ROI={roi_of(blind_over)[2]:+.2f}%")
    print(f"  always UNDER: n={len(blind_under):,}  win={roi_of(blind_under)[1]:.1f}%  "
          f"ROI={roi_of(blind_under)[2]:+.2f}%")
    print("  >> If always-UNDER ≈ model ROI, the model adds nothing over the tilt.\n")

    # ── 3. anti-model (flip every call) ──────────────────────────────
    anti = []
    for b in bets:
        bet_over = b["pred_oof"] > b["line"]
        s = settle_forced(b, not bet_over)  # flip
        if s is not None:
            anti.append(s)
    print("── 3. ANTI-MODEL (flip every call) ──")
    print(f"  flipped: n={len(anti):,}  win={roi_of(anti)[1]:.1f}%  ROI={roi_of(anti)[2]:+.2f}%")
    print("  >> A skilled model must LOSE when flipped (mirror of #1).\n")

    # ── 4. line bias ─────────────────────────────────────────────────
    diffs = np.array([b["actual"] - b["line"] for b in bets])
    pred_diffs = np.array([b["pred_oof"] - b["line"] for b in bets])
    print("── 4. LINE / PREDICTION BIAS ──")
    print(f"  mean(actual - line) = {diffs.mean():+.3f}  (>0 => lines set LOW, unders lose)")
    print(f"  mean(pred   - line) = {pred_diffs.mean():+.3f}  (<0 => model leans UNDER)")
    print(f"  share actual>line (over cashes): {(diffs>0).mean()*100:.1f}%   "
          f"actual<line: {(diffs<0).mean()*100:.1f}%\n")

    # ── 5. player concentration ──────────────────────────────────────
    by_pid = defaultdict(list)
    for b, s in model:
        by_pid[b["pid"]].append(s)
    pid_roi = {pid: (len(ss), roi_of(ss)[2]) for pid, ss in by_pid.items()}
    top = sorted(pid_roi.items(), key=lambda kv: -kv[1][0])[:8]
    name_of = {b["pid"]: b["player"] for b in bets}
    print("── 5. PLAYER CONCENTRATION (top by bet count) ──")
    for pid, (c, r) in top:
        print(f"  {name_of.get(pid,'?')[:22]:22s} n={c:3d}  ROI={r:+.1f}%")
    for k in (1, 3, 5, 10):
        drop = {pid for pid, _ in sorted(pid_roi.items(), key=lambda kv: -kv[1][1])[:k]}
        kept = [s for b, s in model if b["pid"] not in drop]
        print(f"  drop top-{k:2d} ROI players -> n={len(kept):,}  ROI={roi_of(kept)[2]:+.2f}%")
    print("  >> If dropping a few players kills the edge, it's overfit to them.\n")

    # ── 6. bootstrap CI ──────────────────────────────────────────────
    pays = np.array([p for _, s in model for (won, p) in [s]])
    boot = []
    for _ in range(5000):
        samp = RNG.choice(pays, size=len(pays), replace=True)
        boot.append(samp.sum() / (len(pays) * 100.0) * 100.0)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    p_le0 = (np.array(boot) <= 0).mean()
    print("── 6. BOOTSTRAP 95% CI on ROI (5000 resamples) ──")
    print(f"  ROI={roi_all:+.2f}%   95% CI=[{lo:+.2f}%, {hi:+.2f}%]   P(ROI<=0)={p_le0:.3f}")
    print("  >> CI crossing 0 / high P(ROI<=0) => not distinguishable from no edge.\n")

    # ── 7. temporal ──────────────────────────────────────────────────
    early = [s for b, s in model if b["gdate"] < mid]
    late = [s for b, s in model if b["gdate"] >= mid]
    print("── 7. TEMPORAL ──")
    print(f"  early half: n={len(early):,}  ROI={roi_of(early)[2]:+.2f}%")
    print(f"  late  half: n={len(late):,}  ROI={roi_of(late)[2]:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
