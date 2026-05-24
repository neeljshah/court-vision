"""probe_outlier_uplift.py — Cycle 98c (loop 5) outlier-uplift probe.

Targets the heteroskedasticity bias surfaced by cycle 96e: q50 quantile-head
stats (BLK, FG3M, STL, TOV, REB) bias is driven by right-tail OUTLIER games
not by median shift. Per-position scaling (cycles 97b/c) was rejected
because the bias isn't uniform — only OUTLIER rows are systematically
under-predicted.

This probe builds a per-row OUTLIER PRIOR (probability the player exceeds
their L20 q90 in this game) using ONLY prior-game data (no leak), then
applies a multiplicative uplift to rows where outlier_prior crosses a
threshold. The framework is reusable — if it fails for BLK/FG3M, we keep
the L20-distribution lookup for future probes.

Outlier-prior definition (no leak):
  - For each holdout row, look up the player's L20 distribution from games
    STRICTLY PRIOR to the row's date.
  - outlier_prior = 0.10 base (top decile by definition) + recent-form bump:
      if l5_<stat> > L20 q75: prior += 0.10  (recent hot streak)
      if l5_<stat> > L20 q90: prior += 0.05  (already at outlier territory)
  - Capped at 0.30.

Uplift rule:
  - When outlier_prior > prob_threshold (default 0.15): pred *= (1 + uplift_factor).
  - Else: pred unchanged.

Ship gate (BOTH required):
  - single-split MAE strictly DOWN on >= 2 of (BLK, FG3M).
  - WF 4/4 positive on the same stats.

NO-OP test: uplift_factor=0.0 must produce EXACTLY 0.0 MAE delta on all 7 stats.

Run:
    python scripts/probe_outlier_uplift.py
    python scripts/probe_outlier_uplift.py --skip-wf
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import warnings
from typing import Callable, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _BOX_COL, _MIN_PLAYED, _NBA_CACHE,
    _num, _parse_date,
    build_pergame_dataset, feature_columns,
)
from scripts.validate_adjustment import (  # noqa: E402
    _bulk_predict, validate, print_report,
)


_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
os.makedirs(_RESULTS_DIR, exist_ok=True)

# Stats this probe targets — q50 heads where cycle 96e identified
# right-tail-driven bias. PTS (sqrt+Huber) and AST (multitask MLP) approximate
# the mean correctly and don't get uplift.
_UPLIFT_STATS = ("blk", "fg3m")

# L20 distribution window — number of prior PLAYED games to define
# the per-player outlier baseline.
_L20_WINDOW = 20


# ── per-(player_id, date_iso, stat) L20 distribution lookup ───────────────────

def build_l20_lookup(gamelog_dir: Optional[str] = None) -> Dict[Tuple[int, str], Dict[str, Dict[str, float]]]:
    """Build (player_id, date_iso) -> {stat: {q75, q90, n}}.

    The distribution is the player's last _L20_WINDOW PLAYED games STRICTLY
    BEFORE date_iso. Rows with fewer than 5 prior games get None (caller
    must default outlier_prior to 0.10 — graceful no-history fallback).

    Mirrors the build_pergame_dataset prior_played iteration to guarantee
    we hit the same set of (pid, date) keys as the holdout rows.
    """
    gamelog_dir = gamelog_dir or _NBA_CACHE
    lookup: Dict[Tuple[int, str], Dict[str, Dict[str, float]]] = {}

    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list):
            continue

        try:
            basename = os.path.basename(path)
            pid = int(basename.split("_")[1])
        except Exception:
            continue

        # Same chronological sort and played-filter as build_pergame_dataset.
        dated = [(d, g) for g in games
                 if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])

        prior_played: List[dict] = []
        for gdate, game in dated:
            played = _num(game.get("MIN")) >= _MIN_PLAYED
            if played and len(prior_played) >= 1:
                # Compute L20-window distribution from the last 20 prior games.
                window = prior_played[-_L20_WINDOW:]
                key = (pid, gdate.isoformat())
                per_stat: Dict[str, Dict[str, float]] = {}
                for stat in _UPLIFT_STATS:
                    col = _BOX_COL[stat]
                    vals = [_num(g.get(col)) for g in window]
                    vals = [v for v in vals if v is not None]
                    if len(vals) >= 5:
                        per_stat[stat] = {
                            "q75": float(np.quantile(vals, 0.75)),
                            "q90": float(np.quantile(vals, 0.90)),
                            "n":   float(len(vals)),
                        }
                if per_stat:
                    lookup[key] = per_stat
            if played:
                prior_played.append(game)

    return lookup


# ── outlier-prior compute (uses ONLY pre-game info) ──────────────────────────

def compute_outlier_prior(
    row: dict,
    stat: str,
    l20: Dict[Tuple[int, str], Dict[str, Dict[str, float]]],
) -> float:
    """P(player's stat is in their L20 top-decile this game).

    Base 0.10 (definition of top-decile). Bumps:
      + 0.10 when l5_<stat> > L20 q75 (recent hot streak)
      + 0.05 when l5_<stat> > L20 q90 (already at outlier territory)
    Capped at 0.30. Graceful 0.10 fallback when no L20 history.
    """
    pid = row.get("player_id")
    date_iso = row.get("date")
    if pid is None or date_iso is None:
        return 0.10
    key = (int(pid), str(date_iso))
    dist = l20.get(key)
    if dist is None or stat not in dist:
        return 0.10  # no history — graceful default to base rate

    q75 = dist[stat]["q75"]
    q90 = dist[stat]["q90"]
    l5 = row.get(f"l5_{stat}")
    if l5 is None:
        return 0.10
    try:
        l5f = float(l5)
    except (TypeError, ValueError):
        return 0.10

    prior = 0.10
    if l5f > q75:
        prior += 0.10
    if l5f > q90:
        prior += 0.05
    return min(prior, 0.30)


# ── adjustment factory ───────────────────────────────────────────────────────

def make_outlier_uplift(
    uplift_factor: float = 0.05,
    prob_threshold: float = 0.15,
    l20_lookup: Optional[Dict[Tuple[int, str], Dict[str, Dict[str, float]]]] = None,
    target_stats: Tuple[str, ...] = _UPLIFT_STATS,
) -> Callable[[np.ndarray, List[dict], str], np.ndarray]:
    """Multiply pred by (1 + uplift_factor) when outlier_prior > prob_threshold.

    Strictly targets ``target_stats`` (default BLK, FG3M). All other stats and
    rows below threshold are exact no-ops.
    """
    l20 = l20_lookup or {}

    def fn(pred: np.ndarray, rows: List[dict], stat: str) -> np.ndarray:
        out = pred.copy()
        if stat not in target_stats:
            return out
        if uplift_factor == 0.0:
            # Fast-path so the no-op test sees identical floats.
            return out
        scale = 1.0 + uplift_factor
        for i, r in enumerate(rows):
            prior = compute_outlier_prior(r, stat, l20)
            if prior > prob_threshold:
                out[i] = pred[i] * scale
        return np.clip(out, 0.0, None)

    return fn


# ── WF helper ────────────────────────────────────────────────────────────────

def walk_forward_post_adjust(
    fn,
    holdout: List[dict],
    X: np.ndarray,
    n_folds: int = 4,
    stats: Tuple[str, ...] = _UPLIFT_STATS,
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


# ── no-op assertion ──────────────────────────────────────────────────────────

def assert_noop_reproduction(
    holdout: List[dict],
    X: np.ndarray,
    l20: Dict[Tuple[int, str], Dict[str, Dict[str, float]]],
) -> None:
    """uplift_factor=0.0 must produce EXACTLY 0.0 MAE delta on ALL 7 stats."""
    fn = make_outlier_uplift(uplift_factor=0.0, prob_threshold=0.15,
                              l20_lookup=l20)
    results = validate(fn, holdout, X)
    for stat in STATS:
        delta = results.get(stat, {}).get("delta_mae", 0.0)
        if abs(delta) > 1e-12:
            raise AssertionError(
                f"NO-OP REPRODUCTION FAILED on stat={stat}: uplift=0.0 "
                f"produced delta_mae={delta:+.10f}; must be exactly 0.0. "
                f"Probe halted before sweep."
            )
    print(f"  no-op reproduction OK: uplift=0.0 -> 0 MAE delta across all 7 stats")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-wf", action="store_true")
    args = ap.parse_args()

    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)
    cols = feature_columns()

    holdout = rows[int(n_total * 0.80):]
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n_total={n_total}  holdout={len(holdout)}  features={len(cols)}",
          flush=True)

    print("Building L20 lookup from gamelogs...", flush=True)
    l20 = build_l20_lookup()
    print(f"  L20 lookup keys: {len(l20)}", flush=True)

    # Player_id coverage audit (post-cycle-98c additive)
    n_with_pid = sum(1 for r in holdout if r.get("player_id") is not None)
    print(f"  holdout rows with player_id: {n_with_pid}/{len(holdout)} "
          f"({100*n_with_pid/max(1,len(holdout)):.1f}%)", flush=True)

    # Outlier-prior distribution per stat on holdout
    print("\nOutlier-prior distribution on holdout:")
    prior_stats: Dict[str, Dict[str, float]] = {}
    for stat in _UPLIFT_STATS:
        priors = [compute_outlier_prior(r, stat, l20) for r in holdout]
        priors_arr = np.array(priors, dtype=float)
        prior_stats[stat] = {
            "mean":   float(np.mean(priors_arr)),
            "median": float(np.median(priors_arr)),
            "frac_above_0.15": float(np.mean(priors_arr > 0.15)),
            "frac_above_0.20": float(np.mean(priors_arr > 0.20)),
            "max":    float(np.max(priors_arr)),
        }
        s = prior_stats[stat]
        print(f"  {stat:<5}: mean={s['mean']:.3f} median={s['median']:.3f} "
              f"frac>0.15={s['frac_above_0.15']:.3f} "
              f"frac>0.20={s['frac_above_0.20']:.3f} max={s['max']:.3f}")

    # NO-OP test
    print("\n" + "=" * 78)
    print("NO-OP REPRODUCTION (uplift_factor=0.0)")
    print("=" * 78)
    assert_noop_reproduction(holdout, X, l20)

    # Sweep
    factors = [0.02, 0.03, 0.05, 0.07, 0.10]
    threshold = 0.15
    print("\n" + "=" * 78)
    print(f"SINGLE-SPLIT SWEEP (uplift in [0.02..0.10], threshold={threshold})")
    print("=" * 78)

    sweep_rows = []
    for uf in factors:
        fn = make_outlier_uplift(uplift_factor=uf, prob_threshold=threshold,
                                   l20_lookup=l20)
        results = validate(fn, holdout, X)
        label = f"outlier_uplift factor={uf:.2f}"
        print_report(label, results)
        per_stat_d = {s: results.get(s, {}).get("delta_mae", 0.0)
                      for s in STATS}
        # Safety: stats NOT in _UPLIFT_STATS should be unchanged
        other_max_abs = max(
            abs(per_stat_d[s] or 0.0) for s in STATS
            if s not in _UPLIFT_STATS
        )
        sweep_rows.append({
            "factor": uf,
            "results": results,
            "deltas": per_stat_d,
            "other_max_abs": other_max_abs,
        })

    # Best-per-stat selection (most negative delta within sweep)
    best_per_stat: Dict[str, dict] = {}
    for stat in _UPLIFT_STATS:
        best = min(sweep_rows, key=lambda d: d["deltas"][stat])
        best_per_stat[stat] = {
            "factor": best["factor"],
            "delta":  best["deltas"][stat],
            "other_max_abs": best["other_max_abs"],
        }
    print("\n" + "=" * 78)
    print("BEST FACTOR PER STAT")
    print("=" * 78)
    for stat, b in best_per_stat.items():
        print(f"  {stat:<5} best_factor={b['factor']:.2f}  "
              f"delta={b['delta']:+.4f}  other_max_abs={b['other_max_abs']:.2e}")

    # WF on best per stat
    wf_results: Dict[str, List[float]] = {}
    if not args.skip_wf:
        print("\n" + "=" * 78)
        print("WALK-FORWARD 4-FOLD on best variant per stat")
        print("=" * 78)
        for stat, b in best_per_stat.items():
            fn = make_outlier_uplift(uplift_factor=b["factor"],
                                       prob_threshold=threshold,
                                       l20_lookup=l20)
            wf = walk_forward_post_adjust(fn, holdout, X, n_folds=4,
                                            stats=(stat,))
            deltas = wf.get(stat, [])
            wf_results[stat] = deltas
            mean = float(np.mean(deltas)) if deltas else float("nan")
            n_neg = sum(1 for d in deltas if d < -0.0001)
            row_str = f"  {stat:<5}  "
            for d in deltas:
                row_str += f"{d:+9.4f} "
            row_str += f"  mean={mean:+.4f}  folds<0={n_neg}/4"
            print(row_str)

    # Ship gate
    print("\n" + "=" * 78)
    print("SHIP GATE (workday spec)")
    print("=" * 78)
    ss_pass_stats = [s for s, b in best_per_stat.items() if b["delta"] < -0.0001]
    ss_pass = len(ss_pass_stats) >= 2  # require >=2 of (BLK, FG3M)
    other_max = max(b["other_max_abs"] for b in best_per_stat.values())

    wf_pass = True
    wf_pass_stats: List[str] = []
    if not args.skip_wf:
        for stat, b in best_per_stat.items():
            deltas = wf_results.get(stat, [])
            n_neg = sum(1 for d in deltas if d < -0.0001)
            if n_neg == 4:
                wf_pass_stats.append(stat)
        # WF needs the SAME stats that passed single-split to be 4/4 positive
        wf_pass = all(s in wf_pass_stats for s in ss_pass_stats) and ss_pass

    print(f"  SS pass stats (delta < 0): {ss_pass_stats}  "
          f"need >=2 -> pass={ss_pass}")
    print(f"  Other-stat max abs drift: {other_max:.2e}")
    if not args.skip_wf:
        print(f"  WF 4/4 pass stats: {wf_pass_stats}  "
              f"covers SS-pass set? {all(s in wf_pass_stats for s in ss_pass_stats)}")
    final = ss_pass and wf_pass and (other_max < 1e-12)
    print(f"  VERDICT: {'SHIP' if final else 'REJECT'}")

    # Markdown report
    out_path = os.path.join(_RESULTS_DIR, "outlier_uplift_v1.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Cycle 98c (loop 5) — outlier-uplift probe (BLK, FG3M)\n\n")
        f.write("## Why this cycle\n")
        f.write("Cycles 97b/c rejected flat per-position scales because the q50-head "
                "bias was driven by right-tail OUTLIER games, not median shift. "
                "This probe targets that heteroskedasticity: build a per-row "
                "outlier_prior (P(player exceeds L20 q90)) using ONLY prior-game "
                "data, then apply a small uplift ONLY on rows where the model "
                "expects elevated outlier risk.\n\n")

        f.write("## Outlier-prior distribution on holdout\n\n")
        f.write("| stat | mean | median | frac>0.15 | frac>0.20 | max |\n")
        f.write("|------|------|--------|-----------|-----------|-----|\n")
        for stat, s in prior_stats.items():
            f.write(f"| {stat} | {s['mean']:.3f} | {s['median']:.3f} | "
                    f"{s['frac_above_0.15']:.3f} | {s['frac_above_0.20']:.3f} | "
                    f"{s['max']:.3f} |\n")

        f.write("\n## No-op reproduction (cycle 97a discipline)\n")
        f.write("- uplift_factor=0.0 produced ZERO MAE delta on all 7 stats "
                "(asserted before sweep).\n")

        f.write("\n## Factor sweep (single-split)\n\n")
        f.write("| factor | BLK Δ | FG3M Δ | other-stat max abs Δ |\n")
        f.write("|--------|-------|--------|----------------------|\n")
        for s in sweep_rows:
            f.write(f"| {s['factor']:.2f} | {s['deltas']['blk']:+.4f} | "
                    f"{s['deltas']['fg3m']:+.4f} | {s['other_max_abs']:.2e} |\n")

        f.write("\n## Best per stat\n\n")
        f.write("| stat | best_factor | SS Δ | other_max_abs |\n")
        f.write("|------|-------------|------|---------------|\n")
        for stat, b in best_per_stat.items():
            f.write(f"| {stat} | {b['factor']:.2f} | {b['delta']:+.4f} | "
                    f"{b['other_max_abs']:.2e} |\n")

        if not args.skip_wf:
            f.write("\n## Walk-forward 4-fold (best factor per stat)\n\n")
            f.write("| stat | fold1 | fold2 | fold3 | fold4 | mean | folds<0 |\n")
            f.write("|------|-------|-------|-------|-------|------|---------|\n")
            for stat in _UPLIFT_STATS:
                deltas = wf_results.get(stat, [])
                if not deltas:
                    continue
                mean = float(np.mean(deltas))
                n_neg = sum(1 for d in deltas if d < -0.0001)
                row_md = f"| {stat} |"
                for d in deltas:
                    row_md += f" {d:+.4f} |"
                row_md += f" {mean:+.4f} | {n_neg}/4 |\n"
                f.write(row_md)

        f.write("\n## Ship gate\n\n")
        f.write(f"- single-split: >=2 of (BLK, FG3M) strictly DOWN -> **{ss_pass}**\n")
        f.write(f"- WF 4/4 positive on SS-pass stats -> **{wf_pass}**\n")
        f.write(f"- other-stat drift < 1e-12 -> **{other_max < 1e-12}** "
                f"({other_max:.2e})\n")
        f.write(f"\n**VERDICT: {'SHIP' if final else 'REJECT'}**\n")
        if not final:
            f.write("\n**Rejection rationale:**\n")
            if not ss_pass:
                f.write(f"- single-split: only {len(ss_pass_stats)}/2 "
                        f"target stats passed (BLK/FG3M)\n")
            if not args.skip_wf and not wf_pass and ss_pass:
                f.write(f"- WF: SS-pass stats {ss_pass_stats} not all 4/4 "
                        f"positive (WF-pass: {wf_pass_stats})\n")
            if other_max >= 1e-12:
                f.write(f"- non-target stat drift {other_max:.2e} "
                        f"(probe touched wrong stats)\n")

    print(f"\nReport written: {out_path}")
    print(f"\n__SS_PASS__={ss_pass}")
    if not args.skip_wf:
        print(f"__WF_PASS__={wf_pass}")
    print(f"__FINAL__={'SHIP' if final else 'REJECT'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
