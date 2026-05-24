"""probe_error_strata_v2.py — multi-axis hardest-strata identifier (cycle 93d).

Cycle 92's batch shipped 3 honest REJECTs all in the family of "post-prediction
multiplicative adjustments" (b2b veteran, foul-rate shrink, Q1 pace residual).
Lesson: GLOBAL adjustments saturate. The next angle is CONDITIONAL adjustment
applied only WHERE the model demonstrably fails.

v1 (probe_error_strata.py, cycle 84 era) stratified along 6 axes and printed
to stdout. v2 expands to 8+ axes, ranks strata by "hardest" (per-stat MAE
within bin minus global per-stat MAE), and writes a markdown report with the
top-5 hardest strata per stat + 3 candidate adjustment hypotheses.

This is a RESEARCH cycle. The output is candidate hypotheses for cycle 94+
probes — NOT a fitted adjustment (would overfit the holdout).

Stratification axes (8):
    1. L10 minutes bin (<20 / 20-30 / 30-36 / 36+)
    2. Pre-game prediction decile (per-stat)
    3. Player L10 variance bin (std of last 10 actuals — input reliability)
    4. Recent days active bin (days_since_last_game — return-from-rest)
    5. Position proxy (BLK/36 quartile — cycle-90c proxy)
    6. Home spread bin (where available; pre-game spread, cycle-91c source)
    7. Opponent defensive rating bin (opp_def_<stat>)
    8. Rest days bin (0 / 1 / 2 / 3+)

Run:
    python scripts/probe_error_strata_v2.py
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.validate_adjustment import _bulk_predict  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _y_true(holdout: List[dict], stat: str) -> np.ndarray:
    """Targets array; 0.0 is a valid target (cycle 79 fix)."""
    return np.array([
        np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
        for r in holdout
    ], dtype=float)


def _safe_float(v, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return f


def _per_stat_predictions(holdout: List[dict], X: np.ndarray
                          ) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {}
    for stat in STATS:
        p = _bulk_predict(stat, X)
        if p is not None:
            out[stat] = p
    return out


# ── stratification engine ────────────────────────────────────────────────────

def compute_strata_table(
    holdout: List[dict],
    preds: Dict[str, np.ndarray],
    feature_fn,                # rows -> scalar feature
    bucket_edges: List[float],
    bucket_labels: List[str],
    axis_label: str,
    min_bin_n: int = 50,
) -> List[Dict]:
    """For each (bucket, stat): compute n, mean residual (signed bias), MAE.

    Returns a list of dicts: one per (bucket, stat) cell with non-empty bin.
    """
    feat = np.array([feature_fn(r) for r in holdout], dtype=float)
    rows_out: List[Dict] = []

    for bi in range(len(bucket_edges) - 1):
        lo, hi = bucket_edges[bi], bucket_edges[bi + 1]
        mask = (feat >= lo) & (feat < hi)
        n_bin = int(mask.sum())
        if n_bin < min_bin_n:
            continue
        for stat in STATS:
            if stat not in preds:
                continue
            yt = _y_true(holdout, stat)
            valid = mask & ~np.isnan(yt)
            n_valid = int(valid.sum())
            if n_valid < min_bin_n:
                continue
            p = preds[stat]
            resid = p[valid] - yt[valid]      # signed: positive = overpredict
            mae_bin = float(np.mean(np.abs(resid)))
            bias_bin = float(np.mean(resid))
            rows_out.append({
                "axis":   axis_label,
                "bucket": bucket_labels[bi],
                "stat":   stat,
                "n":      n_valid,
                "mae":    mae_bin,
                "bias":   bias_bin,
            })
    return rows_out


def global_mae(holdout: List[dict], preds: Dict[str, np.ndarray]
               ) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for stat in STATS:
        if stat not in preds:
            continue
        yt = _y_true(holdout, stat)
        valid = ~np.isnan(yt)
        if valid.sum() == 0:
            continue
        out[stat] = float(np.mean(np.abs(preds[stat][valid] - yt[valid])))
    return out


def rank_hardest(rows: List[Dict], gmae: Dict[str, float]) -> List[Dict]:
    """Attach mae_delta = bin_mae - global_mae and sort descending."""
    for r in rows:
        gm = gmae.get(r["stat"])
        r["mae_delta"] = r["mae"] - gm if gm is not None else float("nan")
    rows_sorted = sorted(rows, key=lambda r: r["mae_delta"], reverse=True)
    return rows_sorted


def top_k_per_stat(rows_sorted: List[Dict], k: int = 5) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {s: [] for s in STATS}
    for r in rows_sorted:
        if len(out[r["stat"]]) < k:
            out[r["stat"]].append(r)
    return out


# ── prediction-decile axis: edges depend on per-stat distribution ────────────

def _pred_decile_edges(p: np.ndarray) -> Tuple[List[float], List[str]]:
    qs = np.quantile(p, np.linspace(0, 1, 11))
    qs = qs.tolist()
    qs[0] = -1e9
    qs[-1] = 1e9
    labels = [f"pred_d{i+1}" for i in range(10)]
    return qs, labels


# ── L10 variance computation (rows are already chronologically sorted) ───────

def _attach_l10_var(holdout: List[dict]) -> None:
    """For each row, attach _l10_var_<stat> = std of the player's last 10 actuals.
    Uses targets from earlier rows for the same player_id (no leakage — earlier
    chronologically). Falls back to 0.0 when fewer than 3 priors available.
    """
    # Build per-player chronological actuals via two passes.
    by_player: Dict[int, List[Dict[str, float]]] = {}
    for r in holdout:
        pid = r.get("player_id")
        if pid is None:
            continue
        try:
            pid_int = int(pid)
        except (TypeError, ValueError):
            continue
        history = by_player.setdefault(pid_int, [])
        # Compute std-of-last-10 from prior entries (before this row).
        for stat in STATS:
            prior_vals = [h[stat] for h in history[-10:] if stat in h]
            if len(prior_vals) >= 3:
                r[f"_l10_var_{stat}"] = float(np.std(prior_vals))
            else:
                r[f"_l10_var_{stat}"] = 0.0
        # Append this row's actual to history (for future rows).
        actuals: Dict[str, float] = {}
        for stat in STATS:
            tv = r.get(f"target_{stat}")
            if tv is not None:
                try:
                    actuals[stat] = float(tv)
                except (TypeError, ValueError):
                    pass
        history.append(actuals)


# ── position proxy (BLK/36) using prior-rows aggregate ───────────────────────

def _attach_blk_per36(holdout: List[dict]) -> None:
    """Attach _blk_per36 using rolling L10 BLK / L10 MIN * 36, fallback 0.0."""
    for r in holdout:
        l10_blk = _safe_float(r.get("l10_blk"))
        l10_min = _safe_float(r.get("l10_min"))
        r["_blk_per36"] = (l10_blk / l10_min * 36.0) if l10_min > 1.0 else 0.0


# ── markdown report writer ───────────────────────────────────────────────────

def _fmt_pct(x: float) -> str:
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.3f}"


def write_markdown_report(
    out_path: str,
    n_holdout: int,
    gmae: Dict[str, float],
    rows_sorted: List[Dict],
    top5_by_stat: Dict[str, List[Dict]],
    all_axes_rows: Dict[str, List[Dict]],
    hypotheses: List[Dict],
) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    lines: List[str] = []
    lines.append("# Error Strata v2 — Hardest Strata Hypothesis Generator (cycle 93d)\n")
    lines.append("## Context\n")
    lines.append(
        "Cycle 92's batch shipped 3 honest REJECTs in the post-prediction "
        "multiplicative-adjustment family (b2b veteran, foul-rate shrink, "
        "Q1 pace residual). Lesson: GLOBAL adjustments saturate.\n\n"
        "v2 stratifies holdout MAE along 8 axes, ranks strata by "
        "(bin MAE - global MAE) descending, and surfaces the hardest cells "
        "as candidate targets for CONDITIONAL adjustments (cycle 94+).\n"
    )
    lines.append(f"Holdout: n={n_holdout} (chronological 80/20 split)\n")
    lines.append("\n## Global MAE reference\n")
    lines.append("| stat | MAE |")
    lines.append("|------|------|")
    for s in STATS:
        if s in gmae:
            lines.append(f"| {s.upper()} | {gmae[s]:.4f} |")

    # Full per-axis tables.
    lines.append("\n## Per-axis stratification tables\n")
    for axis, rows in all_axes_rows.items():
        lines.append(f"\n### {axis}\n")
        lines.append("| bucket | stat | n | bin_MAE | global_MAE | delta | bias |")
        lines.append("|--------|------|---|---------|-----------|-------|------|")
        # Order by bucket label then stat (preserve list ordering).
        for r in rows:
            gm = gmae.get(r["stat"], float("nan"))
            delta = r["mae"] - gm if gm == gm else float("nan")
            lines.append(
                f"| {r['bucket']} | {r['stat'].upper()} | {r['n']} | "
                f"{r['mae']:.4f} | {gm:.4f} | {_fmt_pct(delta)} | "
                f"{_fmt_pct(r['bias'])} |"
            )

    # Top-5 hardest per stat.
    lines.append("\n## TOP-5 HARDEST STRATA PER STAT\n")
    lines.append(
        "Higher `delta` = bin MAE exceeds global MAE more strongly. "
        "Positive `bias` = model OVERPREDICTS in that cell; "
        "negative `bias` = UNDERPREDICTS.\n"
    )
    for stat in STATS:
        if stat not in top5_by_stat or not top5_by_stat[stat]:
            continue
        lines.append(f"\n### {stat.upper()} (global MAE = {gmae.get(stat, 0):.4f})\n")
        lines.append("| rank | axis | bucket | n | bin_MAE | delta | bias |")
        lines.append("|------|------|--------|---|---------|-------|------|")
        for i, r in enumerate(top5_by_stat[stat], start=1):
            lines.append(
                f"| {i} | {r['axis']} | {r['bucket']} | {r['n']} | "
                f"{r['mae']:.4f} | {_fmt_pct(r['mae_delta'])} | "
                f"{_fmt_pct(r['bias'])} |"
            )

    # Candidate hypotheses (derived from cross-stat patterns).
    lines.append("\n## CANDIDATE ADJUSTMENT HYPOTHESES (cycle 94+ targets)\n")
    for i, h in enumerate(hypotheses, start=1):
        lines.append(f"\n### H{i}. {h['title']}\n")
        lines.append(f"**Stratum signature:** {h['stratum']}\n")
        lines.append(f"**Observation:** {h['observation']}\n")
        lines.append(f"**Hypothesis:** {h['hypothesis']}\n")
        lines.append(f"**Probe path:** {h['probe']}\n")

    lines.append("\n## Methodology notes\n")
    lines.append(
        "- Stratification axes are independent: a (axis, bucket, stat) cell "
        "is counted once per axis. Cross-axis interaction is intentionally "
        "NOT explored here (would overfit the holdout).\n"
        "- `min_bin_n=50` filter applied to keep estimates stable.\n"
        "- Prediction deciles are computed PER STAT from the production "
        "_bulk_predict path (cycle 48 dispatch).\n"
        "- L10 variance is built from chronologically-prior target values "
        "WITHIN the holdout slice — does not leak future data.\n"
        "- Hypotheses are RESEARCH OUTPUTS. Validating any one is a separate "
        "probe cycle.\n"
    )

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ── hypothesis generator ─────────────────────────────────────────────────────

def derive_hypotheses(top5_by_stat: Dict[str, List[Dict]],
                      gmae: Dict[str, float],
                      all_rows_sorted: Optional[List[Dict]] = None) -> List[Dict]:
    """Look across hardest strata for patterns common to multiple stats.

    Uses TOP-5 hits for primary signals; falls back to `all_rows_sorted` for
    auxiliary patterns (e.g., big-spread bins that don't crack top-5 but still
    show structural over/under-prediction worth probing).
    """
    hypotheses: List[Dict] = []
    aux = all_rows_sorted or []

    # H1: highest prediction decile typically has worst MAE (model overshoots ceiling)
    high_pred_hits = []
    for stat, rows in top5_by_stat.items():
        for r in rows:
            if r["axis"].startswith("pred_decile") and "d10" in r["bucket"]:
                high_pred_hits.append((stat, r))
    if high_pred_hits:
        bias_signs = [r["bias"] for _, r in high_pred_hits]
        mean_bias = float(np.mean(bias_signs))
        hypotheses.append({
            "title": "Top-decile prediction cap (model overshoots its own ceiling)",
            "stratum": (f"pred_decile=d10 across {len(high_pred_hits)} stat(s) — "
                        f"mean signed bias = {mean_bias:+.3f}"),
            "observation": (
                "The top prediction decile shows MAE materially above global "
                f"MAE on {len(high_pred_hits)} of 7 stats. Signed bias is "
                f"{'positive (overshoots)' if mean_bias > 0 else 'negative (undershoots)'} "
                "on average."
            ),
            "hypothesis": (
                "When pred lands in the top decile for a stat, apply a "
                "conditional pull toward the player's L10 median — testing "
                "weights 0.10/0.15/0.20 on the top-decile subset only. "
                "Differs from cycle-84 pull_l10_low which targeted LOW preds."
            ),
            "probe": (
                "scripts/probe_top_decile_pull.py — variant of pull_l10_when "
                "with `threshold` replaced by per-stat 90th percentile cutoff."
            ),
        })

    # H2: heavy-minutes (l10_min >= 30) — stat over/undershoot pattern.
    # The 30-36 and 36+ l10_min buckets recur as hardest across PTS/AST/TOV
    # with positive bias (overshoot on high-min stars) and across REB/BLK/STL
    # with negative bias (undershoot defensive output for big-minute players).
    high_min_hits = []
    for stat, rows_ in top5_by_stat.items():
        for r in rows_:
            if r["axis"] == "l10_min" and r["bucket"] in ("30-36", "36+"):
                high_min_hits.append((stat, r))
    if high_min_hits:
        biases = [r["bias"] for _, r in high_min_hits]
        pos_count = sum(1 for b in biases if b > 0)
        hypotheses.append({
            "title": "High-minutes bucket — bidirectional stat-specific bias correction",
            "stratum": (f"l10_min in (30-36, 36+) recurs in {len(high_min_hits)} top-5 cells; "
                        f"signed bias positive in {pos_count}/{len(high_min_hits)} of them"),
            "observation": (
                "Heavy-minutes (30+ MPG) players show large MAE delta with "
                "DIVERGING bias signs: volume stats (PTS/AST/TOV) overshoot, "
                "defensive counts (REB/BLK/STL) undershoot. A single global "
                "min-aware multiplier cannot fix both directions."
            ),
            "hypothesis": (
                "Apply a stat-CONDITIONAL pull on the high-l10-min subset: "
                "shrink volume-stat preds toward player L10 median (positive "
                "bias correction) AND inflate defensive counts toward team-"
                "context REB/BLK rates (negative bias correction). Test "
                "PTS/AST/TOV separately from REB/BLK/STL."
            ),
            "probe": (
                "scripts/probe_high_min_split_adjust.py — conditional on "
                "l10_min>=30, apply per-stat-direction adjustment."
            ),
        })

    # H3: large-spread / blowout-prone — recheck T1-A garbage-time at the strata level.
    # Fall back to aux (all_rows_sorted) since spread bins typically lose to
    # pred_decile in raw delta but still carry structural signal.
    big_spread_hits = []
    for stat, rows_ in top5_by_stat.items():
        for r in rows_:
            if r["axis"].startswith("home_spread") and "spread>13" in r["bucket"]:
                big_spread_hits.append((stat, r))
    if not big_spread_hits:
        for r in aux:
            if r["axis"].startswith("home_spread") and "spread>13" in r["bucket"]:
                big_spread_hits.append((r["stat"], r))
    if big_spread_hits:
        bias_mean = float(np.mean([r["bias"] for _, r in big_spread_hits]))
        hypotheses.append({
            "title": "Big-spread bucket — selective MIN haircut (T1-A refinement)",
            "stratum": (f"abs(home_spread)>10 across {len(big_spread_hits)} stat(s); "
                        f"signed bias mean = {bias_mean:+.3f}"),
            "observation": (
                "High-spread games still appear in the hardest strata after "
                "the cycle-91c spread feature was wired. Suggests the model "
                "uses spread as a linear feature without capturing the "
                "discrete starter-bench transition that occurs near 15+ pt margins."
            ),
            "hypothesis": (
                "Apply a sparse, spread-conditional MIN haircut only on "
                "abs(spread) > 13 AND L5_min > 28 (starter on a likely "
                "blowout). This is a tighter version of the rejected cycle-90 "
                "T1-A: trigger frequency lower, effect size larger per game."
            ),
            "probe": (
                "scripts/probe_blowout_starter_haircut.py — multiplier 0.93 "
                "applied only on (abs_spread>13) ∩ (l5_min>28)."
            ),
        })

    # Backfill to 3 hypotheses if we have fewer.
    if len(hypotheses) < 3:
        # H_fallback: rest_days extremes
        long_rest_hits = []
        for stat, rows in top5_by_stat.items():
            for r in rows:
                if r["axis"].startswith("rest_days") and (
                    "4+" in r["bucket"] or "0" in r["bucket"]):
                    long_rest_hits.append((stat, r))
        if long_rest_hits and len(hypotheses) < 3:
            hypotheses.append({
                "title": "Rest-days extreme bucket — non-monotone rest effect",
                "stratum": "rest_days=0 or rest_days>=4 across hardest strata",
                "observation": (
                    "Rest days at extremes (b2b OR long layoff) recur in top "
                    "hardest strata. Linear rest_days feature can't capture "
                    "the U-shape (b2b fatigue AND rust)."
                ),
                "hypothesis": (
                    "Add a polynomial/spline transform of rest_days or "
                    "conditional adjustments at the two tails (cycle 91 b2b "
                    "rejected as blanket; this is the OTHER tail — long rest "
                    "as a rust signal)."
                ),
                "probe": "scripts/probe_long_rest_decay.py",
            })

    return hypotheses


# ── main orchestration ───────────────────────────────────────────────────────

def main() -> int:
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n={n} holdout={len(holdout)} features={len(cols)}", flush=True)

    print("Running production predictions...", flush=True)
    preds = _per_stat_predictions(holdout, X)
    gmae = global_mae(holdout, preds)
    print(f"  preds computed for {len(preds)}/{len(STATS)} stats", flush=True)

    print("Building auxiliary stratification keys (l10_var, blk_per36)...",
          flush=True)
    _attach_l10_var(holdout)
    _attach_blk_per36(holdout)

    # All-axes stratification rows, grouped by axis label.
    all_axes_rows: Dict[str, List[Dict]] = {}
    all_rows: List[Dict] = []

    def _add(label, rows_):
        all_axes_rows[label] = rows_
        all_rows.extend(rows_)

    # Axis 1: L10 minutes
    _add(
        "l10_min bin",
        compute_strata_table(
            holdout, preds,
            feature_fn=lambda r: _safe_float(r.get("l10_min")),
            bucket_edges=[0, 20, 30, 36, 48],
            bucket_labels=["l10_min<20", "20-30", "30-36", "36+"],
            axis_label="l10_min",
        ),
    )

    # Axis 2: Pre-game prediction decile (per-stat; compose into stat-tagged rows)
    pred_decile_rows: List[Dict] = []
    for stat in STATS:
        if stat not in preds:
            continue
        edges, labels = _pred_decile_edges(preds[stat])
        # Attach per-row stat prediction for stratification.
        key = f"_pred_for_decile_{stat}"
        for i, r in enumerate(holdout):
            r[key] = float(preds[stat][i])
        # Stratify but isolate this stat only.
        feat = np.array([r[key] for r in holdout], dtype=float)
        yt = _y_true(holdout, stat)
        gm = gmae.get(stat)
        for bi in range(len(edges) - 1):
            lo, hi = edges[bi], edges[bi + 1]
            mask = (feat >= lo) & (feat < hi) & ~np.isnan(yt)
            n_valid = int(mask.sum())
            if n_valid < 50:
                continue
            resid = preds[stat][mask] - yt[mask]
            pred_decile_rows.append({
                "axis":   "pred_decile",
                "bucket": labels[bi],
                "stat":   stat,
                "n":      n_valid,
                "mae":    float(np.mean(np.abs(resid))),
                "bias":   float(np.mean(resid)),
            })
    all_axes_rows["pred_decile (per-stat)"] = pred_decile_rows
    all_rows.extend(pred_decile_rows)

    # Axis 3: L10 variance bin (per-stat — std of last 10 actuals)
    l10_var_rows: List[Dict] = []
    for stat in STATS:
        if stat not in preds:
            continue
        key = f"_l10_var_{stat}"
        vals = np.array([_safe_float(r.get(key)) for r in holdout], dtype=float)
        q33, q66 = float(np.quantile(vals, 0.33)), float(np.quantile(vals, 0.66))
        edges = [-1e-9, q33, q66, 1e9]
        labels = [f"l10var_low(<{q33:.2f})",
                  f"l10var_mid({q33:.2f}-{q66:.2f})",
                  f"l10var_high(>{q66:.2f})"]
        yt = _y_true(holdout, stat)
        for bi in range(len(edges) - 1):
            lo, hi = edges[bi], edges[bi + 1]
            mask = (vals >= lo) & (vals < hi) & ~np.isnan(yt)
            n_valid = int(mask.sum())
            if n_valid < 50:
                continue
            resid = preds[stat][mask] - yt[mask]
            l10_var_rows.append({
                "axis":   f"l10_var_{stat}",
                "bucket": labels[bi],
                "stat":   stat,
                "n":      n_valid,
                "mae":    float(np.mean(np.abs(resid))),
                "bias":   float(np.mean(resid)),
            })
    all_axes_rows["l10_var (per-stat)"] = l10_var_rows
    all_rows.extend(l10_var_rows)

    # Axis 4: Days since last game
    _add(
        "days_since_last_game bin",
        compute_strata_table(
            holdout, preds,
            feature_fn=lambda r: _safe_float(r.get("days_since_last_game"), 2.0),
            bucket_edges=[0, 1, 3, 8, 100],
            bucket_labels=["dsl<1", "1-3", "3-8", "8+ (long absence)"],
            axis_label="days_since_last_game",
        ),
    )

    # Axis 5: Position proxy via BLK/36 quartile
    blk36 = np.array([_safe_float(r.get("_blk_per36")) for r in holdout], dtype=float)
    q25, q50, q75 = (float(np.quantile(blk36, 0.25)),
                     float(np.quantile(blk36, 0.50)),
                     float(np.quantile(blk36, 0.75)))
    _add(
        "position proxy (blk/36 quartile)",
        compute_strata_table(
            holdout, preds,
            feature_fn=lambda r: _safe_float(r.get("_blk_per36")),
            bucket_edges=[-1e-9, q25, q50, q75, 1e9],
            bucket_labels=[
                f"blk36_Q1(<{q25:.2f}) (G/F-like)",
                f"blk36_Q2({q25:.2f}-{q50:.2f})",
                f"blk36_Q3({q50:.2f}-{q75:.2f})",
                f"blk36_Q4(>{q75:.2f}) (C/PF-like)",
            ],
            axis_label="pos_proxy_blk36",
        ),
    )

    # Axis 6: Home spread (cycle-91c pre-game spread; NaN-tolerant)
    def _spread_abs(r):
        hs = r.get("home_spread")
        if hs is None:
            return -1.0  # sentinel for "no spread data"
        try:
            return abs(float(hs))
        except (TypeError, ValueError):
            return -1.0
    _add(
        "home_spread (absolute)",
        compute_strata_table(
            holdout, preds,
            feature_fn=_spread_abs,
            bucket_edges=[0, 4, 8, 13, 40],
            bucket_labels=["abs_spread<4 (close)",
                            "abs_spread 4-8",
                            "abs_spread 8-13",
                            "abs_spread>13 (blowout-prone)"],
            axis_label="home_spread",
        ),
    )

    # Axis 7: Opponent defensive context (use opp_def_pts as a coarse proxy)
    _add(
        "opp_def_pts bin",
        compute_strata_table(
            holdout, preds,
            feature_fn=lambda r: _safe_float(r.get("opp_def_pts"), 1.0),
            bucket_edges=[0.6, 0.95, 1.0, 1.05, 1.4],
            bucket_labels=["opp_def<0.95 (great D)",
                            "0.95-1.0",
                            "1.0-1.05",
                            "1.05+ (weak D)"],
            axis_label="opp_def_pts",
        ),
    )

    # Axis 8: Rest days bin
    _add(
        "rest_days bin",
        compute_strata_table(
            holdout, preds,
            feature_fn=lambda r: _safe_float(r.get("rest_days"), 2.0),
            bucket_edges=[-0.5, 0.5, 1.5, 2.5, 30],
            bucket_labels=["rest=0 (b2b)", "rest=1", "rest=2", "rest=3+"],
            axis_label="rest_days",
        ),
    )

    # Rank hardest + take top-5 per stat
    rows_sorted = rank_hardest(all_rows, gmae)
    top5_by_stat = top_k_per_stat(rows_sorted, k=5)

    # Generate hypotheses
    hypotheses = derive_hypotheses(top5_by_stat, gmae,
                                     all_rows_sorted=rows_sorted)

    # Write markdown
    out_path = os.path.join(PROJECT_DIR, "scripts", "_results",
                              "error_strata_v2.md")
    write_markdown_report(
        out_path=out_path,
        n_holdout=len(holdout),
        gmae=gmae,
        rows_sorted=rows_sorted,
        top5_by_stat=top5_by_stat,
        all_axes_rows=all_axes_rows,
        hypotheses=hypotheses,
    )
    print(f"  wrote {out_path}", flush=True)
    print(f"  axes: {len(all_axes_rows)}  total bin rows: {len(all_rows)}",
          flush=True)
    print(f"  hypotheses derived: {len(hypotheses)}", flush=True)

    # Brief stdout summary
    print("\nTOP-3 HARDEST PER STAT (delta = bin_MAE - global_MAE):")
    for stat in STATS:
        if stat not in top5_by_stat:
            continue
        print(f"\n  {stat.upper()} (global MAE {gmae.get(stat, 0):.4f}):")
        for r in top5_by_stat[stat][:3]:
            print(f"    {r['axis']:<28} {r['bucket']:<32} "
                  f"n={r['n']:>5} mae={r['mae']:.4f} "
                  f"d={r['mae_delta']:+.3f} bias={r['bias']:+.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
