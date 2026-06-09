"""eval_atlas_by_section.py -- SELECTIVE atlas ablation, grouped by section.

The bulk ablation (``scripts/loop/eval_atlas_lift.py``) bulk-adds ALL ~49 atlas
features at once and showed the prod prop model is at its feature ceiling: bulk
HELPS only FG3M and HURTS PTS/REB. This script answers the finer question -- WHICH
individual atlas SECTIONS (the ``atlas_<section>__`` feature groups) genuinely reduce
error for WHICH stat -- so the loop can wire in only the sections that pay their way
rather than the whole undifferentiated blob.

Method (identical honest gate to eval_atlas_lift, just per-section):
  * Load the prop dataset once and join ALL atlas features once (the join is the
    expensive part). Group the materialised numeric ``atlas_*`` columns by their
    ``atlas_<section>__`` prefix.
  * For each (stat, section) run the SAME expanding-window walk-forward used by the
    canonical harness (folds at ``(i+1)/(n_splits+1)``, 0.4 val carve, train-median
    impute, exp recency-decay weights) twice on identical row slices: FULL base vs
    base + ONLY that section's columns. Record the per-fold and mean holdout MAE delta
    (``base+section`` minus ``base``); NEGATIVE = that section reduces error.
  * The base model is the FULL production feature matrix, so every section is judged as
    a marginal addition exactly like the gate -- never in isolation.

This is strictly additive: a NEW file under ``scripts/loop/`` that imports the
existing ``eval_atlas_lift`` harness + ``src.loop.atlas_features``. It does not modify
``api/``, the prod model, or any data dir.

Run:
    set NBA_OFFLINE=1
    python scripts/loop/eval_atlas_by_section.py --device auto
    python scripts/loop/eval_atlas_by_section.py --splits 3 \
        --stats pts,reb,ast,fg3m --top-sections 15
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Reuse the canonical bulk harness wholesale: device resolution, the leak-safe atlas
# join, the float matrix builder, train-median imputation, expanding-window fold
# bounds, recency-decay weights, and the GPU XGB fit/predict are all shared so the
# per-section ablation is byte-for-byte the same model as the bulk null.
import scripts.loop.eval_atlas_lift as bulk

STATS_DEFAULT = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _section_of(col: str) -> Optional[str]:
    """Extract the ``<section>`` from an ``atlas_<section>__<leaf>`` column name."""
    if not col.startswith("atlas_"):
        return None
    rest = col[len("atlas_"):]
    idx = rest.find("__")
    if idx <= 0:
        return None
    return rest[:idx]


def _group_by_section(atlas_cols: List[str]) -> Dict[str, List[str]]:
    """Group materialised atlas columns by their section prefix (ordered)."""
    groups: Dict[str, List[str]] = {}
    for c in atlas_cols:
        sec = _section_of(c)
        if sec is None:
            continue
        groups.setdefault(sec, []).append(c)
    return groups


def _coverage(rows: List[dict], cols: List[str]) -> float:
    """Fraction of rows that have at least one non-null value across ``cols``."""
    if not cols:
        return 0.0
    hit = 0
    for r in rows:
        for c in cols:
            v = r.get(c)
            if v is not None and not (isinstance(v, float) and v != v):
                hit += 1
                break
    return hit / max(1, len(rows))


def eval_by_section(
    stats: List[str],
    n_splits: int = 3,
    top_sections: Optional[int] = None,
    only_sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run the base-vs-base+section ablation for every (stat, section) pair.

    Args:
        stats:         stats to evaluate (subset of the 7 props).
        n_splits:      walk-forward folds (canonical expanding window).
        top_sections:  if set, restrict to the N highest-coverage sections (a fast
                       representative subset for a long full sweep).
        only_sections: explicit section allowlist (overrides ``top_sections``).

    Returns:
        Summary dict with per-(stat, section) MAE deltas + the bulk-null per-stat delta
        recomputed on the identical folds for an apples-to-apples comparison.
    """
    from src.prediction.prop_pergame import build_pergame_dataset

    print("[by_section] loading prop dataset (build_pergame_dataset)...", flush=True)
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"[by_section] rows={n}, base features={len(base_cols)}", flush=True)

    join_fn, names_fn = bulk._load_atlas_join()
    atlas_cols = bulk._atlas_columns(rows, join_fn, names_fn)
    groups = _group_by_section(atlas_cols)
    print(f"[by_section] joined {len(atlas_cols)} atlas cols across "
          f"{len(groups)} sections", flush=True)

    # rank sections by row-coverage (proxy for "highest-coverage sections")
    cov = {sec: _coverage(rows, cols) for sec, cols in groups.items()}
    ranked = sorted(groups.keys(), key=lambda s: (-cov[s], s))
    if only_sections:
        sel = [s for s in ranked if s in set(only_sections)]
    elif top_sections is not None:
        sel = ranked[:top_sections]
    else:
        sel = ranked
    print(f"[by_section] evaluating {len(sel)} sections: {sel}", flush=True)

    # Precompute base matrix + per-section matrices once.
    X_base = bulk._matrix(rows, list(base_cols))
    sec_mats: Dict[str, np.ndarray] = {
        sec: bulk._matrix(rows, groups[sec]) for sec in sel}
    bounds = bulk._fold_bounds(n, n_splits)

    # Cache base predictions per (stat, fold) so we only fit base once per stat-fold,
    # not once per section. The augmented model is refit per section (columns differ).
    results: Dict[str, Dict[str, Any]] = {}
    bulk_null: Dict[str, Any] = {}
    X_aug_all = bulk._matrix(rows, list(base_cols) + atlas_cols)  # bulk null matrix

    for stat in stats:
        y = np.array([r.get(f"target_{stat}", np.nan) for r in rows], dtype=float)
        # base + bulk-null per fold (computed once per stat)
        fold_meta: List[Tuple[int, int, int, np.ndarray, np.ndarray]] = []
        base_maes: List[float] = []
        bulk_maes: List[float] = []
        for fi, (tr_end, va_end, te_end) in enumerate(bounds):
            if tr_end < bulk._MIN_TRAIN_ROWS or (te_end - va_end) < bulk._MIN_HOLDOUT_ROWS:
                continue
            ho = slice(va_end, te_end)
            if not (~np.isnan(y[:tr_end])).any() or not (~np.isnan(y[ho])).any():
                continue
            sw = bulk._sample_weights(rows, tr_end)
            yb_tr, yb_ho = y[:tr_end], y[ho]
            b_tr, b_ho = bulk._impute(X_base[:tr_end], X_base[ho])
            pb = bulk._fit_predict(b_tr, yb_tr, b_ho, sw)
            mae_b = float(np.mean(np.abs(pb - yb_ho)))
            base_maes.append(mae_b)
            # bulk null on identical slice
            ab_tr, ab_ho = bulk._impute(X_aug_all[:tr_end], X_aug_all[ho])
            pbk = bulk._fit_predict(ab_tr, yb_tr, ab_ho, sw)
            bulk_maes.append(float(np.mean(np.abs(pbk - yb_ho))))
            fold_meta.append((tr_end, va_end, te_end, sw, yb_ho))
            # stash base mae aligned to this fold for per-section delta
            fold_meta[-1] = (tr_end, va_end, te_end, sw, yb_ho, mae_b)  # type: ignore

        if not fold_meta:
            results[stat] = {}
            bulk_null[stat] = {"evaluated": False}
            continue
        bulk_delta = float(np.mean(np.array(bulk_maes) - np.array(base_maes)))
        bulk_null[stat] = {
            "evaluated": True,
            "base_mae_mean": float(np.mean(base_maes)),
            "bulk_mae_mean": float(np.mean(bulk_maes)),
            "delta_mae_mean": bulk_delta,
            "n_folds": len(base_maes),
        }
        print(f"[by_section] {stat.upper()} bulk-null delta={bulk_delta:+.4f} "
              f"(base={np.mean(base_maes):.4f})", flush=True)

        # per-section
        sec_out: Dict[str, Any] = {}
        for sec in sel:
            Xs = sec_mats[sec]
            deltas: List[float] = []
            for meta in fold_meta:
                tr_end, va_end, te_end, sw, yb_ho, mae_b = meta  # type: ignore
                ho = slice(va_end, te_end)
                # base + ONLY this section's columns, identical slice
                aug_tr = np.hstack([X_base[:tr_end], Xs[:tr_end]])
                aug_ho = np.hstack([X_base[ho], Xs[ho]])
                a_tr, a_ho = bulk._impute(aug_tr, aug_ho)
                pa = bulk._fit_predict(a_tr, y[:tr_end], a_ho, sw)
                mae_a = float(np.mean(np.abs(pa - yb_ho)))
                deltas.append(mae_a - mae_b)
            n_neg = sum(1 for d in deltas if d < 0)
            sec_out[sec] = {
                "n_cols": len(groups[sec]),
                "coverage": round(cov[sec], 4),
                "delta_mae_mean": float(np.mean(deltas)),
                "deltas": [round(d, 5) for d in deltas],
                "neg_folds": n_neg,
                "n_folds": len(deltas),
                "all_improve": bool(n_neg == len(deltas)),
                "beats_bulk": bool(float(np.mean(deltas)) < bulk_delta),
            }
            print(f"    {stat.upper():4s} {sec:26s} delta={np.mean(deltas):+.4f} "
                  f"({n_neg}/{len(deltas)} neg, cov={cov[sec]:.2f})", flush=True)
        results[stat] = sec_out

    return {
        "run_timestamp": datetime.now().isoformat(),
        "device": bulk._XGB_DEVICE,
        "n_rows": n,
        "n_base_features": len(base_cols),
        "n_atlas_features": len(atlas_cols),
        "n_sections_total": len(groups),
        "n_sections_evaluated": len(sel),
        "sections_evaluated": sel,
        "section_coverage": {s: round(cov[s], 4) for s in sel},
        "n_splits": n_splits,
        "bulk_null": bulk_null,
        "per_stat_section": results,
    }


def _ranked_winners(result: Dict[str, Any]) -> List[Tuple[str, str, float, bool, str]]:
    """Flatten to (stat, section, delta, beats_bulk, folds) sorted by delta asc."""
    rows: List[Tuple[str, str, float, bool, str]] = []
    for stat, secs in result["per_stat_section"].items():
        for sec, v in secs.items():
            rows.append((stat, sec, v["delta_mae_mean"], v["beats_bulk"],
                         f"{v['neg_folds']}/{v['n_folds']}"))
    rows.sort(key=lambda r: r[2])
    return rows


def _write_markdown(result: Dict[str, Any], md_path: str) -> None:
    """Write a ranked markdown table of (stat, section) MAE deltas."""
    lines: List[str] = []
    lines.append("# Atlas selective ablation -- per-(stat, section) MAE delta\n")
    lines.append(f"_Run {result['run_timestamp']} | device={result['device']} | "
                 f"rows={result['n_rows']} | base={result['n_base_features']} feats | "
                 f"{result['n_splits']} walk-forward folds_\n")
    lines.append("Negative delta = that atlas SECTION, added on top of the FULL "
                 "production base model, REDUCES holdout MAE. `beats_bulk` = this "
                 "single section's delta is better (more negative) than bulk-adding "
                 "all 49 atlas features at once.\n")

    lines.append("## Bulk null (all atlas features at once)\n")
    lines.append("| stat | base MAE | bulk MAE | bulk delta |")
    lines.append("|------|---------:|---------:|-----------:|")
    for stat, v in result["bulk_null"].items():
        if not v.get("evaluated"):
            lines.append(f"| {stat.upper()} | -- | -- | n/a |")
            continue
        lines.append(f"| {stat.upper()} | {v['base_mae_mean']:.4f} | "
                     f"{v['bulk_mae_mean']:.4f} | {v['delta_mae_mean']:+.4f} |")
    lines.append("")

    lines.append("## Top winners (most negative delta first)\n")
    lines.append("| rank | stat | section | delta MAE | neg folds | beats bulk? |")
    lines.append("|-----:|------|---------|----------:|:---------:|:-----------:|")
    for i, (stat, sec, d, beats, folds) in enumerate(_ranked_winners(result), 1):
        if d >= 0 and i > 30:
            break
        lines.append(f"| {i} | {stat.upper()} | {sec} | {d:+.4f} | {folds} | "
                     f"{'yes' if beats else 'no'} |")
    lines.append("")

    lines.append("## Full grid (delta MAE, negative = section helps)\n")
    stats = list(result["per_stat_section"].keys())
    secs = result["sections_evaluated"]
    lines.append("| section | cov | " + " | ".join(s.upper() for s in stats) + " |")
    lines.append("|---------|----:|" + "|".join("----:" for _ in stats) + "|")
    for sec in secs:
        cov = result["section_coverage"].get(sec, 0.0)
        cells = []
        for stat in stats:
            v = result["per_stat_section"].get(stat, {}).get(sec)
            cells.append(f"{v['delta_mae_mean']:+.4f}" if v else "--")
        lines.append(f"| {sec} | {cov:.2f} | " + " | ".join(cells) + " |")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    """Parse args, run the per-section ablation, persist JSON + markdown, print top 5."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--splits", type=int, default=3, help="walk-forward folds")
    ap.add_argument("--stats", default="pts,reb,ast,fg3m",
                    help="comma-separated stats (default: pts,reb,ast,fg3m)")
    ap.add_argument("--device", default="auto", help="XGB device: cuda/cpu/auto")
    ap.add_argument("--top-sections", type=int, default=15,
                    help="restrict to the N highest-coverage sections (default 15)")
    ap.add_argument("--only-sections", default=None,
                    help="comma-separated explicit section allowlist")
    ap.add_argument("--out", default=None, help="output JSON path")
    ap.add_argument("--md", default=None, help="output markdown path")
    args = ap.parse_args()

    bulk._XGB_DEVICE = bulk._resolve_device(args.device)
    print(f"[by_section] device={bulk._XGB_DEVICE} "
          f"NBA_OFFLINE={os.environ.get('NBA_OFFLINE')}", flush=True)

    stats = [s.strip().lower() for s in args.stats.split(",") if s.strip()]
    only = ([s.strip() for s in args.only_sections.split(",") if s.strip()]
            if args.only_sections else None)
    top = None if only else args.top_sections

    t0 = time.time()
    result = eval_by_section(stats, n_splits=args.splits,
                             top_sections=top, only_sections=only)
    result["wall_seconds"] = round(time.time() - t0, 1)

    out_path = args.out or os.path.join(
        PROJECT_DIR, ".planning", "loop", "atlas_by_section.json")
    md_path = args.md or os.path.join(
        PROJECT_DIR, ".planning", "loop", "atlas_by_section.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    _write_markdown(result, md_path)

    winners = _ranked_winners(result)
    print("\n" + "=" * 64)
    print("  TOP 5 (stat, section, delta MAE) -- negative = section helps")
    print("=" * 64)
    for stat, sec, d, beats, folds in winners[:5]:
        print(f"  {stat.upper():4s} {sec:26s} {d:+.4f}  "
              f"({folds} neg, beats_bulk={beats})")
    print("=" * 64)
    print(f"[by_section] wrote {out_path}")
    print(f"[by_section] wrote {md_path}")


if __name__ == "__main__":
    main()
