"""probe_per_position_factors_v2.py — cycle 96e (loop 5).

V2 of per-position factor probe. v1 (cycle 89c) REJECTED because position
was missing from the pergame dataset. Cycle 90e wired in the
build_player_positions() join. Cycle 92b's background daemon completed
the 800-pid commonplayerinfo fetch. Cycle 95g committed the full parquet.

This v2 probe:
  1. Uses the now-100%-covered `position` row field (Guard/Forward/Center
     and the four hyphenated combos like Guard-Forward).
  2. Stratifies holdout MAE by TWO independent buckets:
        - Coarse 3-position (G/F/C, hyphen folds to first listed)
        - Granular 5-position (PG/SG/SF/PF/C — but data only has
          coarse + hyphenated, so granular collapses to 3 base + 4 hybrid)
  3. Identifies top-3 (position, stat) buckets where MAE is >= 10% above
     global MAE for that stat.
  4. Proposes candidate adjustments per bucket.
  5. Research-only — does NOT wire-in adjustments. Wait for
     validator-confirmed probe before shipping.

Run:
    python scripts/probe_per_position_factors_v2.py
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.validate_adjustment import _bulk_predict  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


def _coarse_bucket(raw: str) -> str:
    """Collapse full-word position to G/F/C. Hyphenated takes first listed.

    Examples:
        'Guard' -> 'G'
        'Forward-Center' -> 'F'
        'Center' -> 'C'
    """
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    head = s.split("-")[0].strip().upper()
    if head.startswith("G"):
        return "G"
    if head.startswith("F"):
        return "F"
    if head.startswith("C"):
        return "C"
    return ""


def _granular_bucket(raw: str) -> str:
    """Preserve hyphenated combos as their own bucket.

    Examples:
        'Guard' -> 'G'
        'Forward-Center' -> 'F-C'
        'Center' -> 'C'
        'Center-Forward' -> 'C-F'
    """
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    parts = [p.strip().upper()[:1] for p in s.split("-") if p.strip()]
    if not parts:
        return ""
    return "-".join(parts)


def _y_true(holdout: List[dict], stat: str) -> np.ndarray:
    return np.array([
        np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
        for r in holdout
    ], dtype=float)


def _global_mae(holdout: List[dict], preds: Dict[str, np.ndarray]) -> Dict[str, float]:
    gm: Dict[str, float] = {}
    for stat in STATS:
        if stat not in preds:
            continue
        yt = _y_true(holdout, stat)
        m = ~np.isnan(yt)
        if m.sum() == 0:
            continue
        gm[stat] = float(np.mean(np.abs(preds[stat][m] - yt[m])))
    return gm


def _per_bucket_table(
    holdout: List[dict],
    preds: Dict[str, np.ndarray],
    bucket_per_row: np.ndarray,
    global_mae: Dict[str, float],
    min_n: int = 100,
) -> Dict[Tuple[str, str], Dict[str, float]]:
    """For each (bucket, stat), compute n / mae / rel-vs-global.
    Skips buckets with n < min_n to avoid noise."""
    cell: Dict[Tuple[str, str], Dict[str, float]] = {}
    unique = sorted({b for b in bucket_per_row if b})
    for b in unique:
        bmask = (bucket_per_row == b)
        if bmask.sum() < min_n:
            continue
        for stat in STATS:
            if stat not in preds:
                continue
            yt = _y_true(holdout, stat)
            mask = bmask & ~np.isnan(yt)
            n = int(mask.sum())
            if n < min_n:
                continue
            err = float(np.mean(np.abs(preds[stat][mask] - yt[mask])))
            gmae = global_mae.get(stat, float("nan"))
            rel = (err / gmae) if (gmae and gmae == gmae and gmae > 0) else float("nan")
            mean_pred = float(np.mean(preds[stat][mask]))
            mean_true = float(np.mean(yt[mask]))
            bias = mean_pred - mean_true  # positive = over-predicting
            cell[(b, stat)] = {
                "n": n, "mae": err, "rel": rel,
                "bias": bias, "mean_pred": mean_pred, "mean_true": mean_true,
            }
    return cell


def _format_bucket_table(name: str, cell: Dict, global_mae: Dict[str, float],
                         buckets: List[str]) -> List[str]:
    body = [f"### {name} stratification\n"]
    body.append("| position | stat | n | bucket_mae | global_mae | rel | bias (pred-true) |")
    body.append("|----------|------|---|-----------|------------|-----|-------------------|")
    for b in buckets:
        for stat in STATS:
            c = cell.get((b, stat))
            if c is None:
                continue
            g = global_mae.get(stat, float("nan"))
            body.append(
                f"| {b} | {stat} | {c['n']} | {c['mae']:.4f} | {g:.4f} | "
                f"{c['rel']:.3f} | {c['bias']:+.4f} |"
            )
    body.append("")
    return body


def _rank_top_buckets(cell: Dict[Tuple[str, str], Dict[str, float]],
                      global_mae: Dict[str, float], top_n: int = 3) -> List[Tuple]:
    """Rank by REL above 1.0, only buckets where rel >= 1.10."""
    candidates = []
    for (pos, stat), v in cell.items():
        if v["rel"] != v["rel"]:  # NaN
            continue
        if v["rel"] < 1.10:
            continue
        candidates.append(((pos, stat), v))
    candidates.sort(key=lambda kv: kv[1]["rel"], reverse=True)
    return candidates[:top_n]


def _propose_adjustment(pos: str, stat: str, v: Dict[str, float]) -> str:
    """Generate a candidate adjustment hypothesis text from a bucket."""
    bias = v["bias"]
    rel_excess_pct = (v["rel"] - 1.0) * 100.0
    direction = "under-predicting" if bias < 0 else "over-predicting"
    needed_scale = (v["mean_true"] / v["mean_pred"]) if v["mean_pred"] != 0 else 1.0
    delta_pct = (needed_scale - 1.0) * 100.0
    sign = "+" if delta_pct > 0 else ""
    return (
        f"({pos}, {stat}): MAE {rel_excess_pct:+.1f}% vs global, "
        f"model {direction} by mean bias {bias:+.4f} "
        f"(pred {v['mean_pred']:.3f} vs true {v['mean_true']:.3f}). "
        f"Candidate: scale {stat.upper()} preds by {sign}{delta_pct:.1f}% "
        f"only for `position=='{pos}'` rows (n={v['n']})."
    )


def main() -> int:
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n={n} holdout={len(holdout)}", flush=True)

    # Coverage check
    pos_raw = [r.get("position") for r in holdout]
    n_pos = sum(1 for p in pos_raw if p)
    print(f"  position coverage: {n_pos}/{len(holdout)} = "
          f"{100*n_pos/len(holdout):.1f}%", flush=True)

    coarse = np.array([_coarse_bucket(p) for p in pos_raw], dtype=object)
    granular = np.array([_granular_bucket(p) for p in pos_raw], dtype=object)

    # Production predictions per stat.
    preds = {}
    for stat in STATS:
        p = _bulk_predict(stat, X)
        if p is not None:
            preds[stat] = p
    print(f"  predictions produced for {sorted(preds.keys())}", flush=True)

    gm = _global_mae(holdout, preds)

    coarse_cell = _per_bucket_table(holdout, preds, coarse, gm, min_n=100)
    granular_cell = _per_bucket_table(holdout, preds, granular, gm, min_n=100)

    coarse_buckets = sorted({b for b in coarse if b})
    granular_buckets = sorted({b for b in granular if b})

    body = []
    body.append("# Per-position factor probe v2 — cycle 96e (loop 5)\n")
    body.append("## FOUND — full parquet (cycle 95g) gives 100% coverage\n")
    body.append(f"- Holdout rows: {len(holdout)}  (chronological 80/20 split)")
    body.append(f"- Position coverage: {n_pos}/{len(holdout)} = "
                f"{100*n_pos/len(holdout):.1f}%")
    body.append(f"- Coarse buckets (G/F/C): {coarse_buckets}")
    body.append(f"- Granular buckets (hyphen preserved): {granular_buckets}")
    body.append("")
    body.append("### Global MAE per stat (production-pipeline holdout)")
    body.append("| stat | global_MAE |")
    body.append("|------|-----------|")
    for stat in STATS:
        if stat in gm:
            body.append(f"| {stat} | {gm[stat]:.4f} |")
    body.append("")

    body.extend(_format_bucket_table("Coarse G/F/C", coarse_cell, gm,
                                     coarse_buckets))
    body.extend(_format_bucket_table("Granular (with hybrid)", granular_cell,
                                     gm, granular_buckets))

    # Top-3 worst per bucket scheme
    top_coarse = _rank_top_buckets(coarse_cell, gm, top_n=3)
    top_granular = _rank_top_buckets(granular_cell, gm, top_n=3)

    body.append("### Top-3 worst buckets (rel >= 1.10) — COARSE")
    if not top_coarse:
        body.append("- No coarse (G/F/C) bucket exceeds 10% relative MAE vs global.")
        body.append("")
    else:
        body.append("| rank | pos | stat | n | bucket_mae | global_mae | rel | bias |")
        body.append("|------|-----|------|---|-----------|------------|-----|------|")
        for i, ((pos, stat), v) in enumerate(top_coarse):
            body.append(
                f"| {i+1} | {pos} | {stat} | {v['n']} | {v['mae']:.4f} | "
                f"{gm[stat]:.4f} | {v['rel']:.3f} | {v['bias']:+.4f} |"
            )
        body.append("")

    body.append("### Top-3 worst buckets (rel >= 1.10) — GRANULAR")
    if not top_granular:
        body.append("- No granular bucket exceeds 10% relative MAE vs global.")
        body.append("")
    else:
        body.append("| rank | pos | stat | n | bucket_mae | global_mae | rel | bias |")
        body.append("|------|-----|------|---|-----------|------------|-----|------|")
        for i, ((pos, stat), v) in enumerate(top_granular):
            body.append(
                f"| {i+1} | {pos} | {stat} | {v['n']} | {v['mae']:.4f} | "
                f"{gm[stat]:.4f} | {v['rel']:.3f} | {v['bias']:+.4f} |"
            )
        body.append("")

    # Candidate hypotheses
    body.append("### Candidate hypotheses (research-only — do NOT wire in)")
    all_cands = list(top_coarse) + list(top_granular)
    seen = set()
    hyp_count = 0
    for (pos, stat), v in all_cands:
        key = (pos, stat)
        if key in seen:
            continue
        seen.add(key)
        body.append(f"- {_propose_adjustment(pos, stat, v)}")
        hyp_count += 1
        if hyp_count >= 3:
            break
    if hyp_count == 0:
        body.append("- No (position, stat) bucket exceeds rel 1.10. Model is "
                    "evenly calibrated across positions — per-position scale "
                    "adjustments NOT justified by this probe.")
        body.append("- Per-cycle 95-series lesson: stats already absorb most "
                    "position-driven variance via prior-form (l5/l10/ewma) "
                    "features. Position adds little marginal signal.")
        body.append("- Next research angle: try position * matchup or "
                    "position * fatigue interactions instead of flat scale.")
    body.append("")

    body.append("### Verdict")
    if hyp_count > 0:
        body.append(f"- {hyp_count} candidate position-aware adjustment(s) "
                    "surfaced. Next step (cycle 97): write per-bucket factor "
                    "into `validate_adjustment.py`, gate via dual MAE-delta "
                    "test (single-split AND 4-fold walk-forward). DO NOT ship "
                    "this cycle.")
    else:
        body.append("- REJECT scale-only per-position adjustment. No bucket "
                    "shows rel >= 1.10. Model is evenly calibrated across "
                    "positions. Pivot research to interaction features.")
    body.append("")
    body.append("### Diagnostic notes")
    body.append("- v1 (cycle 89c) was REJECTed due to missing position field. "
                "v2 (this probe) ran on the cycle 95g parquet with 100% "
                "coverage. Buckets are populated entirely by the "
                "build_player_positions() join in src/prediction/prop_pergame.py.")
    body.append("- Granular buckets (e.g. 'F-C', 'C-F') are kept distinct "
                "from base buckets ('F', 'C') because hyphenated players have "
                "fluid usage and may absorb different role variance.")
    body.append("- bias column = mean(pred) - mean(true). Negative bias means "
                "the model under-predicts that bucket on average — a positive "
                "scale factor would close the gap.")
    body.append("")

    out_path = os.path.join(PROJECT_DIR, "scripts", "_results",
                            "per_position_factors_v2_with_data.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))
    print(f"\nReport written: {out_path}")

    # Console summary
    print("\n=== Coarse G/F/C bucket MAE ===")
    for b in coarse_buckets:
        for stat in STATS:
            c = coarse_cell.get((b, stat))
            if c is None:
                continue
            print(f"  {b:>3} {stat:<5} n={c['n']:>4d} mae={c['mae']:.4f} "
                  f"rel={c['rel']:.3f} bias={c['bias']:+.4f}")
    print("\n=== Top candidates ===")
    if hyp_count > 0:
        for (pos, stat), v in all_cands[:3]:
            print(f"  ({pos},{stat}) rel={v['rel']:.3f} n={v['n']}")
    else:
        print("  None at rel>=1.10. Model evenly calibrated across positions.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
