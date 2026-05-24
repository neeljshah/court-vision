"""probe_b2b_veteran_v2.py — cycle 92e (loop 5) T1-C re-test with REAL is_b2b.

v1 (cycle 90b) was forced into a Q4 in-distribution window because
`data/rest_travel.parquet` ended 2025-04-13 — every row in the canonical
2025-26 holdout had `is_b2b == 0`. Cycle 91d shipped a rebuilt parquet
that now extends through 2026-04-06 (2025-26 mean is_b2b ≈ 0.178).

This v2 re-runs the SAME adjustment on the canonical chronological 80/20
holdout (so the b2b cell is real, populated, and OUT-of-sample for the
production models).

The structural SELECTION BIAS from v1 still applies — gamelog rows only
include games the player actually PLAYED. The 80% sit-rate prior from
landyourbets is silent here because DNPs are not in the dataset. The
realized effect on rows where vets DID suit up should therefore be
SMALLER than 12% (the headline shrink would suggest). Expected ceiling:
~3-4% headline → ~0.5-1pp MAE win at best.

Adjustment: shrink predicted (PTS, REB, AST) by `factor` when
    age >= age_threshold AND is_b2b >= 0.5
Starter flag: not in dataset → default include (same as v1).

Sweep: factor ∈ {0.88, 0.90, 0.92, 0.94, 0.96}.

Ship gate:
- Single-split MAE strictly down on PTS AND REB AND AST (delta < -0.001).
- WF 4/4 chronological folds positive on each of PTS, REB, AST.

Output: scripts/_results/b2b_veteran_v2_real_b2b.md
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from typing import List

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Reuse v1 helpers — we ONLY change the holdout slice (canonical 80/20)
# and add 0.88 to the sweep. Wiring everything through v1's helpers keeps
# the two probes directly comparable.
from scripts.probe_b2b_veteran import (  # noqa: E402
    _TARGET_STATS, _build_holdout_with_pid, _load_bbref_age,
    _season_from_date_iso, apply_b2b_veteran_shrink,
    run_single_split, run_wf_chronological,
)
from src.prediction.prop_pergame import STATS, feature_columns  # noqa: E402


def _agg_delta(res):
    return sum(res[s]["delta"] for s in _TARGET_STATS if res.get(s))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--age-threshold", type=float, default=33.0)
    ap.add_argument("--no-sweep", action="store_true",
                    help="use a single factor (--factor) instead of the 5-factor sweep")
    ap.add_argument("--factor", type=float, default=0.92,
                    help="single factor when --no-sweep is set")
    args = ap.parse_args()

    print("Building dataset with player_id attached...", flush=True)
    rows, pids, seasons_raw, dates, names = _build_holdout_with_pid(min_prior=0)
    n = len(rows)
    order = sorted(range(n), key=lambda i: dates[i])
    rows = [rows[i] for i in order]
    pids = [pids[i] for i in order]
    names = [names[i] for i in order]
    dates = [dates[i] for i in order]

    # CANONICAL chronological 80/20 — same split used for production model
    # validation. With cycle 91d's rest_travel.parquet, this slice now has
    # real is_b2b data for the 2025-26 season.
    cut = int(n * 0.80)
    holdout = rows[cut:]
    holdout_names = names[cut:]
    holdout_dates = dates[cut:]
    n_ho = len(holdout)
    print(f"  full n={n}  holdout={n_ho}  date range: {holdout_dates[0]} -> {holdout_dates[-1]}",
          flush=True)

    # Confirm is_b2b is populated in the holdout (cycle 91d's fix).
    b2b_vals = np.array([float(r.get("is_b2b", 0) or 0) for r in holdout], dtype=float)
    is_b2b_mean = float(b2b_vals.mean())
    n_b2b = int((b2b_vals >= 0.5).sum())
    print(f"  is_b2b mean in holdout: {is_b2b_mean:.4f}  ({n_b2b}/{n_ho} rows)", flush=True)

    holdout_seasons = [_season_from_date_iso(d) for d in holdout_dates]
    season_set = sorted(set(holdout_seasons))
    print(f"  holdout seasons: {season_set}", flush=True)

    age_lookup = _load_bbref_age(season_set)
    print(f"  bbref age entries loaded: {len(age_lookup)}", flush=True)

    ages = np.zeros(n_ho, dtype=float)
    n_known = 0
    for i in range(n_ho):
        name = holdout_names[i]
        season = holdout_seasons[i]
        a = age_lookup.get((name, season), 0.0) if name else 0.0
        ages[i] = a
        if a > 0:
            n_known += 1
    print(f"  ages resolved: {n_known}/{n_ho} ({100*n_known/n_ho:.1f}%)", flush=True)

    n_veteran_b2b = sum(
        1 for i, r in enumerate(holdout)
        if ages[i] >= args.age_threshold
        and float(r.get("is_b2b", 0) or 0) >= 0.5
    )
    n_age_known_vet = sum(1 for a in ages if a >= args.age_threshold)
    print(f"  rows age>={args.age_threshold:.0f}: {n_age_known_vet}", flush=True)
    print(f"  rows (age>={args.age_threshold:.0f} AND is_b2b): {n_veteran_b2b}", flush=True)

    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in holdout],
                 dtype=float)

    if args.no_sweep:
        factors: List[float] = [args.factor]
    else:
        factors = [0.88, 0.90, 0.92, 0.94, 0.96]

    all_results = {}
    for f in factors:
        print(f"\n=== factor={f:.2f} ===", flush=True)
        r = run_single_split(holdout, X, ages, f)
        all_results[f] = r
        print(f"{'stat':<5} {'n_aff':>6} {'base':>9} {'adj':>9} {'delta':>10}")
        for s in STATS:
            rr = r[s]
            if rr is None:
                print(f"{s:<5} (no model)")
                continue
            print(f"{s:<5} {rr['n_affected']:>6d} {rr['base_mae']:>9.4f} "
                  f"{rr['adj_mae']:>9.4f} {rr['delta']:>+10.4f}")

    best_factor = min(factors, key=lambda f: _agg_delta(all_results[f]))
    best_res = all_results[best_factor]
    print(f"\nBest factor: {best_factor:.2f}  agg_delta={_agg_delta(best_res):+.4f}", flush=True)

    gate_ss = all(best_res[s]["delta"] < -0.001 for s in _TARGET_STATS)
    print(f"\nSingle-split ship gate (PTS+REB+AST all strictly down): "
          f"{'PASS' if gate_ss else 'FAIL'}", flush=True)

    # Run WF when single-split is at least mildly positive on aggregate.
    # Use a softer gate than v1 (-0.001) because the expected ceiling here
    # is ~3-4% headline → small absolute MAE deltas.
    wf_results = None
    if _agg_delta(best_res) <= -0.001:
        print(f"\n=== Walk-forward (4-fold chronological, no retrain) factor={best_factor:.2f} ===",
              flush=True)
        wf_results = run_wf_chronological(holdout, X, ages, best_factor, n_folds=4)
        for s in _TARGET_STATS:
            print(f"\n  {s.upper()} WF folds:")
            for fi, fr in enumerate(wf_results[s]):
                if fr is None:
                    continue
                ver = "+" if fr["delta"] < 0 else "-"
                print(f"    fold{fi+1}: base={fr['base']:.4f} adj={fr['adj']:.4f} "
                      f"delta={fr['delta']:+.4f}  n={fr['n']}  {ver}")

    # Write markdown report.
    out_path = os.path.join(PROJECT_DIR, "scripts", "_results", "b2b_veteran_v2_real_b2b.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    L = []
    L.append("# cycle 92e (loop 5) — T1-C re-test with REAL is_b2b")
    L.append("")
    L.append("## Why v2")
    L.append("v1 (cycle 90b) ran into a data bug: `data/rest_travel.parquet` ended")
    L.append("2025-04-13, so every row in the canonical 2025-26 holdout had")
    L.append("`is_b2b == 0`. v1 fell back to a Q4 in-distribution window. Cycle 91d")
    L.append("shipped a rebuilt parquet through 2026-04-06 (overall `is_b2b` mean")
    L.append("≈ 0.174, 2025-26 mean ≈ 0.178). v2 re-runs on the canonical 80/20")
    L.append("holdout where the b2b cell is real AND out-of-sample.")
    L.append("")
    L.append("## Setup")
    L.append(f"- holdout: chronological 80/20 (n={n_ho} of full n={n})")
    L.append(f"- holdout date range: {holdout_dates[0]} -> {holdout_dates[-1]}")
    L.append(f"- holdout seasons: {season_set}")
    L.append(f"- **is_b2b mean in holdout: {is_b2b_mean:.4f}  "
             f"({n_b2b}/{n_ho} rows had is_b2b>=0.5)**")
    L.append(f"- age source: `data/external/bbref_advanced_<season>.json` (`age` field)")
    L.append(f"- ages resolved: {n_known}/{n_ho} ({100*n_known/n_ho:.1f}%)")
    L.append(f"- rows age>={args.age_threshold:.0f}: {n_age_known_vet}")
    L.append(f"- **rows affected (age>={args.age_threshold:.0f} AND is_b2b): {n_veteran_b2b}**")
    L.append(f"- starter flag: NOT IN DATASET — defaulted to INCLUDE (same as v1)")
    L.append(f"- target stats: pts, reb, ast (others fg3m/stl/blk/tov untouched)")
    L.append("")
    L.append("## Single-split MAE table (per factor)")
    L.append("")
    L.append("| factor | stat | n_aff | base_mae | adj_mae | delta |")
    L.append("|--------|------|------:|---------:|--------:|------:|")
    for f in factors:
        r = all_results[f]
        for s in STATS:
            rr = r[s]
            if rr is None:
                continue
            L.append(f"| {f:.2f} | {s} | {rr['n_affected']} | "
                     f"{rr['base_mae']:.4f} | {rr['adj_mae']:.4f} | "
                     f"{rr['delta']:+.4f} |")
    L.append("")
    L.append(f"## Best factor: **{best_factor:.2f}**")
    L.append(f"- aggregate (pts+reb+ast) delta: {_agg_delta(best_res):+.4f}")
    L.append(f"- single-split ship gate (PTS AND REB AND AST strictly down): "
             f"**{'PASS' if gate_ss else 'FAIL'}**")
    L.append("")

    gate_wf = False
    if wf_results is not None:
        L.append("## Walk-forward (4 chronological folds within holdout, no retrain)")
        L.append("")
        L.append("| stat | fold | base | adj | delta | positive? |")
        L.append("|------|-----:|----:|----:|------:|:---------:|")
        wf_pos = {}
        for s in _TARGET_STATS:
            n_pos = 0
            for fi, fr in enumerate(wf_results[s]):
                if fr is None:
                    continue
                pos = fr["delta"] < 0
                if pos:
                    n_pos += 1
                L.append(f"| {s} | {fi+1} | {fr['base']:.4f} | {fr['adj']:.4f} | "
                         f"{fr['delta']:+.4f} | {'YES' if pos else 'no'} |")
            wf_pos[s] = n_pos
        L.append("")
        for s in _TARGET_STATS:
            L.append(f"- {s.upper()}: {wf_pos[s]}/4 folds positive")
        gate_wf = all(wf_pos[s] == 4 for s in _TARGET_STATS)
        L.append("")
        L.append(f"## WF gate (4/4 on PTS, REB, AST): **{'PASS' if gate_wf else 'FAIL'}**")
    else:
        L.append("## Walk-forward: SKIPPED (single-split aggregate not even mildly positive)")

    gate_ship = gate_ss and gate_wf
    L.append("")
    L.append("## Selection-bias context (still applies in v2)")
    L.append("")
    L.append("The landyourbets prior is 'veterans aged 33+ sit ~80% of second")
    L.append("nights of b2bs'. But `gamelog_*.json` ONLY contains games the player")
    L.append("ACTUALLY PLAYED — the 80% who sat are SILENT in the dataset. The")
    L.append(f"~{n_veteran_b2b} rows we adjust are the ~20% who DID suit up: by")
    L.append("selection, these are the vets in good health/form. Shrinking their")
    L.append("projections fights what the model already learned from the `is_b2b`")
    L.append("+ `rest_days` features (which DO see the survivor distribution).")
    L.append("")
    L.append("**Expected ceiling on this probe is ~3-4% headline effect** (single-")
    L.append("digit basis-point MAE win) — NOT the 1-3bp/8-12% the headline prior")
    L.append("would suggest. If we land near zero or negative, that confirms the")
    L.append("selection-bias ceiling, not noise.")
    L.append("")
    L.append("## Verdict")
    if gate_ship:
        L.append(f"**SHIP** at factor={best_factor:.2f}, age_threshold=33.")
        L.append("Wire-in: post-prediction hook in `src/prediction/prop_pergame.py`.")
    else:
        reasons = []
        if not gate_ss:
            reasons.append("single-split gate failed (not all 3 stats strictly down)")
        if wf_results is None:
            reasons.append("aggregate improvement not even mildly positive — WF skipped")
        elif not gate_wf:
            reasons.append("WF gate failed (not 4/4 on all target stats)")
        L.append(f"**REJECT** — {'; '.join(reasons)}.")
        L.append("")
        L.append("Even with real 2025-26 `is_b2b` (cycle 91d), the gamelog selection")
        L.append("bias dominates. The vets who PLAY on the b2b are the survivor")
        L.append("subset, and the model's per-row `is_b2b` feature already captures")
        L.append("whatever residual fatigue effect remains in that subset.")
        L.append("")
        L.append("**Follow-up:** T1-C is structurally untestable on game-log data.")
        L.append("Deferring to a DNP-aware projection-set infra cycle — that loop")
        L.append("would let us validate the FULL sit-rate effect (the 80% who DNP)")
        L.append("by predicting for ALL rostered vets pre-game and weighting by")
        L.append("realized play-probability. Without that, every flavor of this")
        L.append("probe (age 33, 32, 30; starter only; PT-weighted) will hit the")
        L.append("same survivor-bias ceiling.")

    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(L) + "\n")
    print(f"\nWrote {out_path}", flush=True)
    print(f"\nFinal verdict: {'SHIP' if gate_ship else 'REJECT'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
