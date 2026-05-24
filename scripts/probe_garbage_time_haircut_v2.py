"""probe_garbage_time_haircut_v2.py — Cycle 94a (loop 5) T1-A v2.

Re-tests the cycle 90a garbage-time haircut using REAL pre-game sportsbook
spreads instead of the SRS proxy. Cycle 90a v1 was REJECTED but the
data was a confound: `season_games_*.json` SRS coverage stops at
2025-04-13, so the default 20% holdout (which lives entirely in 2025-26)
had ZERO spread data. v1 worked around this by re-splitting WITHIN the
SRS-coverage window — a synthetic 2024-25 holdout, not the canonical
production holdout.

Cycle 92a shipped `data/pregame_spreads.parquet` with full-season coverage
(1316 rows / 206 dates / 2025-10-21 → 2025-05-25). Cycle 91c wired
`home_spread` (per-player-perspective sign) onto every row dict in
build_pergame_dataset. This probe consumes it directly.

Sign convention (from prop_pergame.py:1717):
  row["home_spread"] is the spread FROM THIS PLAYER'S PERSPECTIVE —
  NEGATIVE when the player's team is favoured. ABS value = absolute
  spread = blowout signal.

Variants tested (each applied to PTS/REB/AST ONLY — fg3m/stl/blk/tov
saturated per cycle 89f / 90a):
  V1-revalidate: (6,10,14) → (0.98,0.95,0.92)   — v1's best on SRS proxy
  Gentler-wider: (8,12,16) → (0.99,0.97,0.94)
  Sharper:       (5,10,15) → (0.97,0.93,0.88)
  93d-refined:   (13,)     → (0.92,)  when ALSO l5_min > 28   (starter trigger)

Run:
    python scripts/probe_garbage_time_haircut_v2.py
    python scripts/probe_garbage_time_haircut_v2.py --skip-wf
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from typing import Callable, Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

from scripts.validate_adjustment import (  # noqa: E402
    _bulk_predict, validate, print_report,
)


_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

_VOLUME_STATS = {"pts", "reb", "ast"}


# ── adjustment factories ─────────────────────────────────────────────────────

def make_garbage_haircut_v2(
    bins: Tuple[float, ...],
    factors: Tuple[float, ...],
    require_starter_min: float = 0.0,
) -> Callable[[np.ndarray, List[dict], str], np.ndarray]:
    """Multiplicative tiered haircut on volume stats, keyed on ABS(home_spread).

    Tiered application by absolute spread:
        abs_spread <  bins[0]            -> 1.0
        bins[0] <= abs_spread < bins[1]  -> factors[0]
        ...
        abs_spread >= bins[-1]           -> factors[-1]

    require_starter_min: if > 0, ONLY rows with l5_min > this value receive
    the haircut. Encodes cycle 93d hypothesis #3 — bench/short-minute
    rotation guys aren't affected by garbage time (they get garbage time
    minutes themselves).

    Applies ONLY to pts/reb/ast — fg3m/stl/blk/tov are saturated.
    """
    assert len(bins) == len(factors), "bins and factors must be same length"

    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        if stat not in _VOLUME_STATS:
            return pred.copy()
        out = pred.copy()
        for i, r in enumerate(rows):
            hs = r.get("home_spread")
            if hs is None:
                continue
            try:
                abs_s = abs(float(hs))
            except (TypeError, ValueError):
                continue
            if abs_s < bins[0]:
                continue
            if require_starter_min > 0.0:
                try:
                    l5m = float(r.get("l5_min", 0.0) or 0.0)
                except (TypeError, ValueError):
                    l5m = 0.0
                if l5m <= require_starter_min:
                    continue
            factor = 1.0
            for thr, f in zip(bins, factors):
                if abs_s >= thr:
                    factor = f
            out[i] = pred[i] * factor
        return np.clip(out, 0.0, None)

    return fn


# ── WF helper (post-prediction adjustment — no retrain) ──────────────────────

def walk_forward_post_adjust(
    fn,
    holdout: List[dict],
    X: np.ndarray,
    n_folds: int = 4,
    stats: Tuple[str, ...] = ("pts", "reb", "ast"),
) -> Dict[str, List[float]]:
    """Per-stat per-fold MAE delta (adj - base). Negative = improvement."""
    n = len(holdout)
    fold_size = n // n_folds
    per_stat: Dict[str, List[float]] = {s: [] for s in stats}
    for fold_i in range(n_folds):
        lo = fold_i * fold_size
        hi = n if fold_i == n_folds - 1 else (fold_i + 1) * fold_size
        sub_rows = holdout[lo:hi]
        sub_X = X[lo:hi]
        for stat in stats:
            y_true = np.array([
                np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
                for r in sub_rows
            ], dtype=float)
            mask = ~np.isnan(y_true)
            pred = _bulk_predict(stat, sub_X)
            if pred is None:
                per_stat[stat].append(float("nan"))
                continue
            adj = fn(pred, sub_rows, stat)
            bm = float(np.mean(np.abs(pred[mask] - y_true[mask])))
            am = float(np.mean(np.abs(adj[mask] - y_true[mask])))
            per_stat[stat].append(am - bm)
    return per_stat


# ── main ─────────────────────────────────────────────────────────────────────

def _fmt(bins, factors):
    return ("/".join(f"{b:g}" for b in bins)) + " -> " + ("/".join(f"{f:.2f}" for f in factors))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-wf", action="store_true")
    args = ap.parse_args()

    print("Loading pergame dataset (with home_spread join)...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)
    cols = feature_columns()

    holdout = rows[int(n_total * 0.80):]
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n_total={n_total}  holdout={len(holdout)}  features={len(cols)}\n",
          flush=True)

    # Coverage audit on the holdout
    spread_vals = [r.get("home_spread") for r in holdout]
    n_with = sum(1 for v in spread_vals if v is not None)
    abs_vals = [abs(float(v)) for v in spread_vals if v is not None]
    holdout_min_date = holdout[0]["date"] if holdout else ""
    holdout_max_date = holdout[-1]["date"] if holdout else ""
    print(f"  holdout date range: {holdout_min_date} -> {holdout_max_date}",
          flush=True)
    print(f"  rows with home_spread: {n_with}/{len(holdout)} "
          f"({100*n_with/max(1,len(holdout)):.1f}%)", flush=True)
    if abs_vals:
        pct5  = sum(1 for v in abs_vals if v >= 5)  / len(abs_vals)
        pct8  = sum(1 for v in abs_vals if v >= 8)  / len(abs_vals)
        pct10 = sum(1 for v in abs_vals if v >= 10) / len(abs_vals)
        pct12 = sum(1 for v in abs_vals if v >= 12) / len(abs_vals)
        pct13 = sum(1 for v in abs_vals if v >= 13) / len(abs_vals)
        pct16 = sum(1 for v in abs_vals if v >= 16) / len(abs_vals)
        print(f"  |home_spread|  >=5 {pct5:.1%}  >=8 {pct8:.1%}  >=10 {pct10:.1%} "
              f" >=12 {pct12:.1%}  >=13 {pct13:.1%}  >=16 {pct16:.1%}\n", flush=True)
    else:
        pct5 = pct8 = pct10 = pct12 = pct13 = pct16 = 0.0

    if n_with < 1000:
        print("WARN: insufficient holdout home_spread coverage — probe is "
              "informational only.", flush=True)

    # Variants
    variants = [
        ("v1-revalidate",  (6.0, 10.0, 14.0),  (0.98, 0.95, 0.92), 0.0),
        ("gentler-wider",  (8.0, 12.0, 16.0),  (0.99, 0.97, 0.94), 0.0),
        ("sharper",        (5.0, 10.0, 15.0),  (0.97, 0.93, 0.88), 0.0),
        ("93d-refined",    (13.0,),             (0.92,),            28.0),
    ]

    print("=" * 78)
    print("SINGLE-SPLIT SWEEP")
    print("=" * 78)

    sweep_rows = []
    for name, bins, factors, req_min in variants:
        fn = make_garbage_haircut_v2(bins, factors,
                                      require_starter_min=req_min)
        results = validate(fn, holdout, X)
        label = f"{name}: {_fmt(bins, factors)}" + \
                (f" [l5_min>{req_min:g}]" if req_min > 0 else "")
        print_report(label, results)
        agg_delta = sum(
            (results.get(s, {}).get("delta_mae") or 0.0)
            for s in ("pts", "reb", "ast")
        )
        n_improved = sum(
            1 for s in STATS
            if ((results.get(s, {}).get("delta_mae") or 0.0) < -0.001)
        )
        sweep_rows.append({
            "name": name, "bins": bins, "factors": factors,
            "req_min": req_min, "results": results,
            "agg_delta": agg_delta, "n_improved": n_improved,
        })

    # Pick best by aggregate PTS+REB+AST delta
    best = min(sweep_rows, key=lambda d: d["agg_delta"])
    print()
    print("=" * 78)
    print(f"BEST: {best['name']}  ({_fmt(best['bins'], best['factors'])})"
          + (f"  l5_min>{best['req_min']:g}" if best["req_min"] > 0 else ""))
    print(f"  PTS+REB+AST aggregate delta: {best['agg_delta']:+.4f}")
    print(f"  n_improved: {best['n_improved']}/7")
    print("=" * 78)

    # WF on best variant
    wf_results: Dict[str, List[float]] = {}
    if not args.skip_wf:
        print()
        print("=" * 78)
        print(f"WALK-FORWARD 4-FOLD on best variant")
        print("=" * 78)
        best_fn = make_garbage_haircut_v2(best["bins"], best["factors"],
                                           require_starter_min=best["req_min"])
        wf_results = walk_forward_post_adjust(best_fn, holdout, X, n_folds=4)
        print(f"  {'stat':<5} {'fold1':>9} {'fold2':>9} {'fold3':>9} {'fold4':>9}  "
              f"{'mean':>9} {'folds<0':>8}")
        for s in ("pts", "reb", "ast"):
            deltas = wf_results.get(s, [])
            mean = np.mean(deltas) if deltas else float("nan")
            n_neg = sum(1 for d in deltas if d < -0.0001)
            row = f"  {s:<5} "
            for d in deltas:
                row += f"{d:+9.4f} "
            row += f" {mean:+9.4f} {n_neg}/{len(deltas):>3d}"
            print(row)

    # Ship gate (cycle 94a — relaxed per cycle 93d insight)
    print()
    print("=" * 78)
    print("SHIP GATE (cycle 94a relaxed)")
    print("=" * 78)
    pts_d = best["results"].get("pts", {}).get("delta_mae") or 0.0
    reb_d = best["results"].get("reb", {}).get("delta_mae") or 0.0
    ast_d = best["results"].get("ast", {}).get("delta_mae") or 0.0
    agg = pts_d + reb_d + ast_d
    ss_pass = (pts_d < 0) and (agg <= -0.005)
    wf_pts_pass = True
    wf_n_neg_pts = 0
    if not args.skip_wf:
        pts_deltas = wf_results.get("pts", [])
        wf_n_neg_pts = sum(1 for d in pts_deltas if d < -0.0001)
        wf_pts_pass = (wf_n_neg_pts == 4)
    print(f"  SS: PTS={pts_d:+.4f} REB={reb_d:+.4f} AST={ast_d:+.4f}  "
          f"agg={agg:+.4f}  pass={ss_pass}")
    if not args.skip_wf:
        print(f"  WF PTS: {wf_n_neg_pts}/4 folds positive  pass={wf_pts_pass}")
    final = ss_pass and wf_pts_pass
    print(f"  VERDICT: {'SHIP' if final else 'REJECT'}")

    # Markdown report
    out_path = os.path.join(_RESULTS_DIR, "garbage_time_haircut_v2.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Cycle 94a (loop 5) — T1-A garbage-time haircut v2 (REAL spreads)\n\n")
        f.write("## Why this re-runs cycle 90a\n")
        f.write("Cycle 90a v1 used a SRS proxy for the pre-game spread because no "
                "real-spread parquet existed. SRS coverage stopped 2025-04-13, so "
                "the canonical 20% holdout (entirely in 2025-26) had no signal. "
                "v1 worked around this by re-splitting WITHIN the SRS window — a "
                "synthetic 2024-25 holdout. Cycle 92a shipped "
                "`data/pregame_spreads.parquet` with full 2025-26 coverage and "
                "cycle 91c joined `home_spread` (per-player perspective) onto "
                "every row. This probe consumes the real value.\n\n")

        f.write("## Coverage on canonical holdout\n")
        f.write(f"- holdout date range: {holdout_min_date} → {holdout_max_date}\n")
        f.write(f"- rows with home_spread: {n_with}/{len(holdout)} "
                f"({100*n_with/max(1,len(holdout)):.1f}%)\n")
        if abs_vals:
            f.write(f"- |home_spread|: >=5 {pct5:.1%}, >=8 {pct8:.1%}, "
                    f">=10 {pct10:.1%}, >=12 {pct12:.1%}, >=13 {pct13:.1%}, "
                    f">=16 {pct16:.1%}\n")
        f.write("\n## Variant sweep (single-split, PTS/REB/AST only)\n\n")
        f.write("| variant | bins | factors | gate | n_imp | PTS Δ | REB Δ | AST Δ | agg Δ |\n")
        f.write("|---------|------|---------|------|-------|-------|-------|-------|-------|\n")
        for s in sweep_rows:
            pts = s["results"].get("pts", {}).get("delta_mae") or 0.0
            reb = s["results"].get("reb", {}).get("delta_mae") or 0.0
            ast = s["results"].get("ast", {}).get("delta_mae") or 0.0
            gate = f"l5_min>{s['req_min']:g}" if s["req_min"] > 0 else "—"
            f.write(f"| {s['name']} "
                    f"| {'/'.join(f'{b:g}' for b in s['bins'])} "
                    f"| {'/'.join(f'{ff:.2f}' for ff in s['factors'])} "
                    f"| {gate} | {s['n_improved']}/7 "
                    f"| {pts:+.4f} | {reb:+.4f} | {ast:+.4f} | {s['agg_delta']:+.4f} |\n")

        f.write(f"\n## Best variant detail: **{best['name']}**\n\n")
        f.write("| stat | n | baseline_mae | adjusted_mae | delta_mae | verdict |\n")
        f.write("|------|---|--------------|--------------|-----------|---------|\n")
        for s in STATS:
            r = best["results"].get(s, {})
            if not r or r.get("n") == 0:
                continue
            d = r.get("delta_mae") or 0.0
            v = "BETTER" if d < -0.001 else ("worse" if d > 0.001 else "flat")
            f.write(f"| {s} | {r.get('n')} | {r.get('baseline_mae'):.4f} "
                    f"| {r.get('adjusted_mae'):.4f} | {d:+.4f} | {v} |\n")

        if not args.skip_wf:
            f.write(f"\n## Walk-forward 4-fold (best variant)\n\n")
            f.write("| stat | fold1 | fold2 | fold3 | fold4 | mean | folds<0 |\n")
            f.write("|------|-------|-------|-------|-------|------|---------|\n")
            for s in ("pts", "reb", "ast"):
                deltas = wf_results.get(s, [])
                mean = np.mean(deltas) if deltas else float("nan")
                n_neg = sum(1 for d in deltas if d < -0.0001)
                f.write(f"| {s} ")
                for d in deltas:
                    f.write(f"| {d:+.4f} ")
                f.write(f"| {mean:+.4f} | {n_neg}/4 |\n")

        f.write("\n## v1 (SRS proxy, 2024-25 synthetic holdout) vs v2 (real spreads, 2025-26 canonical holdout)\n\n")
        f.write("| | v1 best (6/10/14 -> .98/.95/.92) | v2 best |\n")
        f.write("|---|---|---|\n")
        f.write("| holdout window | 2024-25 (synthetic re-split) | 2025-26 canonical |\n")
        f.write(f"| holdout n | 15662 | {len(holdout)} |\n")
        f.write(f"| spread source | SRS proxy | REAL pregame |\n")
        f.write(f"| PTS Δ | -0.0020 | {pts_d:+.4f} |\n")
        f.write(f"| REB Δ | +0.0017 | {reb_d:+.4f} |\n")
        f.write(f"| AST Δ | -0.0007 | {ast_d:+.4f} |\n")
        f.write(f"| agg Δ | -0.0010 | {agg:+.4f} |\n")
        f.write(f"| WF PTS folds<0 | 2/4 | {wf_n_neg_pts}/4 |\n")

        f.write("\n## Ship gate (cycle 94a relaxed)\n\n")
        f.write(f"- single-split: PTS < 0 AND agg <= -0.005 → **{ss_pass}** "
                f"(PTS={pts_d:+.4f}, agg={agg:+.4f})\n")
        if not args.skip_wf:
            f.write(f"- WF PTS 4/4 folds positive → **{wf_pts_pass}** "
                    f"({wf_n_neg_pts}/4)\n")
        f.write(f"\n**VERDICT: {'SHIP' if final else 'REJECT'}**\n")
        if not final:
            f.write("\n**Rejection rationale:**\n")
            if not ss_pass:
                f.write(f"- single-split: PTS={pts_d:+.4f} (need < 0), "
                        f"agg={agg:+.4f} (need <= -0.005)\n")
            if not args.skip_wf and not wf_pts_pass:
                f.write(f"- WF PTS only {wf_n_neg_pts}/4 folds positive\n")

    print(f"\nReport written: {out_path}")

    # Print machine-readable summary for the wrapper script
    print(f"\n__BEST_BINS__={'/'.join(f'{b:g}' for b in best['bins'])}")
    print(f"__BEST_FACTORS__={'/'.join(f'{f:.2f}' for f in best['factors'])}")
    print(f"__SS_PASS__={ss_pass}")
    if not args.skip_wf:
        print(f"__WF_PASS__={wf_pts_pass}")
    print(f"__FINAL__={'SHIP' if final else 'REJECT'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
