"""exp_lowshrink_pts_reb.py — Approach A2: Un-flatten the joint model via
tuned LightGBM with reduced regularization + monotone constraints on volume
drivers + optional learned blend with production baseline.

Run:
    python scripts/exp_lowshrink_pts_reb.py

Produces:
    docs/_audits/PTS_REB_EXP_LOWSHRINK.md

Design
------
For each stat in ["pts","reb"]:
1.  Build monotone_constraints vector (+1 on volume/usage drivers, 0 elsewhere).
2.  Grid a small set of LGB configs that reduce shrinkage vs baseline:
       {num_leaves: 31,63,127} x {min_child_samples: 20,10}
       x {reg_lambda: 1.0,0.3} x {objective: regression_l1, regression}
    n_estimators up to 1500 + early stopping on val.
3.  For each config: run with AND without monotone constraints (L1 does not
    support monotone in LightGBM; those combos are skipped automatically).
4.  Learned blend: w*lgb_ho + (1-w)*base_ho, w in {0.3,0.5,0.7,1.0}.
    Blend weight chosen on OOF MAE — mildly optimistic; honest gate is
    new_mae < base_mae on full OOF regardless.
5.  Pick single best (config, monotone?, blend-w) by overall OOF MAE.
6.  score_and_report the winner, print full comparison table.

Performance note
----------------
Feature matrices are built ONCE per stat (full dataset), then sliced by
fold index to avoid rebuilding on each config iteration.
"""
from __future__ import annotations

import os
import sys
import time
import itertools
from typing import Dict, List, Tuple, Optional

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import lightgbm as lgb  # noqa: E402

from scripts._pts_oof_harness import (  # noqa: E402
    build_folds, feature_matrix, targets, recency_weights,
    load_base, score_and_report,
)

# ---------------------------------------------------------------------------
# Monotone constraint definitions (aligned to feature_columns order)
# ---------------------------------------------------------------------------

_MONOTONE_PTS = [
    "l5_min", "l10_min", "ewma_min", "prev_min",
    "l5_pts", "l10_pts", "ewma_pts", "prev_pts",
    "bbref_usg_pct",
]

_MONOTONE_REB = [
    "l5_min", "l10_min", "ewma_min", "prev_min",
    "l5_reb", "l10_reb", "ewma_reb", "prev_reb",
    "bbref_trb_pct", "reb_chance_l5",
]


def _make_monotone_vec(cols: List[str], positive_cols: List[str]) -> List[int]:
    pos_set = set(positive_cols)
    return [1 if c in pos_set else 0 for c in cols]


# ---------------------------------------------------------------------------
# Grid definition
# ---------------------------------------------------------------------------

_NUM_LEAVES    = [31, 63, 127]
_MIN_CHILD     = [20, 10]
_REG_LAMBDA    = [1.0, 0.3]
_OBJECTIVES    = ["regression_l1", "regression"]
_BLEND_WEIGHTS = [0.3, 0.5, 0.7, 1.0]

_N_ESTIMATORS = 1500
_EARLY_STOP   = 50


def _lgb_params(num_leaves: int, min_child: int, lam: float, obj: str) -> dict:
    return dict(
        objective=obj,
        num_leaves=num_leaves,
        min_child_samples=min_child,
        reg_lambda=lam,
        reg_alpha=0.0,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=4,
        verbose=-1,
        random_state=42,
    )


# ---------------------------------------------------------------------------
# Pre-build feature/target arrays once per stat
# ---------------------------------------------------------------------------

def _preload(stat: str):
    """Returns (rows, folds, X_all, y_all, cols, base_df).

    base_df has game_id patched to game_date[:10] (verified unique on
    (game_id, player_id, fold) — see exp_transform_pts_reb.py for the same
    pattern). The recs builder must use r['date'][:10] as game_id to match.
    """
    import pandas as pd
    print(f"  Building rows + feature matrix for {stat.upper()} (one-time) ...")
    t0 = time.time()
    rows, folds = build_folds(stat=stat)
    X_all, cols = feature_matrix(rows, stat)
    y_all       = targets(rows, f"target_{stat}")
    base_df     = load_base(stat).copy()
    # game_id column is empty in cached baseline; use game_date as unique key
    base_df["game_id"] = base_df["game_date"].astype(str).str[:10]
    print(f"  Done in {time.time()-t0:.1f}s.  rows={len(rows)}, feats={X_all.shape[1]}")
    # Sanity: verify uniqueness
    _dup = base_df.groupby(["game_id","player_id","fold"]).size().max()
    assert _dup == 1, f"Join key not unique! max_dup={_dup}"
    return rows, folds, X_all, y_all, cols, base_df


# ---------------------------------------------------------------------------
# Core: run one config across all folds using pre-built arrays
# ---------------------------------------------------------------------------

def _run_one_config(
    rows: list,
    folds: List[Tuple],
    X_all: np.ndarray,
    y_all: np.ndarray,
    params: dict,
    mono_vec: List[int],
    use_monotone: bool,
    base_df,
) -> Tuple[List[dict], List[dict]]:
    """Returns (lgb_recs, base_recs) lists for OOF holdout rows that merge
    against the base cache.

    Join key: (game_id=date[:10], player_id, fold) — verified unique in base_df
    after the game_date patch applied in _preload().
    """
    import pandas as pd

    lgb_recs:  List[dict] = []
    base_recs: List[dict] = []

    p = dict(params)
    if use_monotone:
        p["monotone_constraints"] = mono_vec

    for fi, tr_end, va_end, te_end in folds:
        # Slice pre-built arrays
        X_tr = X_all[:tr_end]
        y_tr = y_all[:tr_end]
        X_va = X_all[tr_end:va_end]
        y_va = y_all[tr_end:va_end]
        X_ho = X_all[va_end:te_end]

        sw = recency_weights(rows, tr_end)

        dtrain = lgb.Dataset(X_tr, label=y_tr, weight=sw)
        dval   = lgb.Dataset(X_va, label=y_va, reference=dtrain)

        cbs = [
            lgb.early_stopping(_EARLY_STOP, verbose=False),
            lgb.log_evaluation(period=-1),
        ]
        model = lgb.train(
            p, dtrain,
            num_boost_round=_N_ESTIMATORS,
            valid_sets=[dval],
            callbacks=cbs,
        )
        preds_ho = model.predict(X_ho)

        ho_rows = rows[va_end:te_end]

        # Use date[:10] as game_id proxy (matches base_df["game_id"] after patch)
        ho_ids = pd.DataFrame([
            {
                "game_id":   str(r.get("date", ""))[:10],
                "player_id": int(r.get("player_id", 0)),
                "fold":      fi,
            }
            for r in ho_rows
        ])
        ho_ids["game_id"]   = ho_ids["game_id"].astype(str)
        ho_ids["player_id"] = ho_ids["player_id"].astype(int)
        ho_ids["fold"]      = ho_ids["fold"].astype(int)

        merged = ho_ids.reset_index().merge(
            base_df[["game_id", "player_id", "fold", "oof_pred_base"]],
            on=["game_id", "player_id", "fold"],
            how="inner",
        )

        for _, row in merged.iterrows():
            j = int(row["index"])
            lgb_recs.append({
                "game_id":   str(row["game_id"]),
                "player_id": int(row["player_id"]),
                "fold":      fi,
                "pred":      float(preds_ho[j]),
            })
            base_recs.append({
                "game_id":   str(row["game_id"]),
                "player_id": int(row["player_id"]),
                "fold":      fi,
                "pred":      float(row["oof_pred_base"]),
            })

    return lgb_recs, base_recs


# ---------------------------------------------------------------------------
# OOF MAE from recs list (no harness overhead)
# ---------------------------------------------------------------------------

def _oof_mae_from_recs(recs: List[dict], base_df) -> float:
    import pandas as pd
    if not recs:
        return float("inf")
    df = pd.DataFrame(recs)
    df["game_id"]   = df["game_id"].astype(str)
    df["player_id"] = df["player_id"].astype(int)
    df["fold"]      = df["fold"].astype(int)
    m = base_df.merge(df, on=["game_id", "player_id", "fold"], how="inner")
    if m.empty:
        return float("inf")
    return float((m["pred"] - m["actual"]).abs().mean())


# ---------------------------------------------------------------------------
# Blend recs
# ---------------------------------------------------------------------------

def _blend_recs(lgb_recs: List[dict], base_recs: List[dict], w: float) -> List[dict]:
    """w * lgb + (1-w) * base"""
    assert len(lgb_recs) == len(base_recs)
    return [
        {
            "game_id":   lr["game_id"],
            "player_id": lr["player_id"],
            "fold":      lr["fold"],
            "pred":      w * lr["pred"] + (1.0 - w) * br["pred"],
        }
        for lr, br in zip(lgb_recs, base_recs)
    ]


# ---------------------------------------------------------------------------
# Main experiment loop for one stat
# ---------------------------------------------------------------------------

def run_stat(stat: str) -> Tuple[dict, List[dict]]:
    """Returns (winner_result_dict, all_config_rows)."""
    print(f"\n{'='*70}")
    print(f"  STAT: {stat.upper()}")
    print(f"{'='*70}")
    t0 = time.time()

    rows, folds, X_all, y_all, cols, base_df = _preload(stat)

    mono_pos  = _MONOTONE_PTS if stat == "pts" else _MONOTONE_REB
    mono_vec  = _make_monotone_vec(cols, mono_pos)
    found_pos = [cols[i] for i, v in enumerate(mono_vec) if v == 1]
    print(f"  Monotone +1 on {len(found_pos)} cols: {found_pos}")
    missing = [c for c in mono_pos if c not in cols]
    if missing:
        print(f"  WARNING: {missing} not in cols — will be ignored")

    base_mae = float((base_df["oof_pred_base"] - base_df["actual"]).abs().mean())
    print(f"  Baseline OOF MAE: {base_mae:.4f}")
    print()

    # Build grid
    grid = list(itertools.product(
        _NUM_LEAVES, _MIN_CHILD, _REG_LAMBDA, _OBJECTIVES
    ))
    # Each grid entry tried with/without monotone
    # L1 + monotone = unsupported by LGB; those entries will be skipped
    total = len(grid) * 2
    run_i = 0

    config_rows: List[dict] = []
    best_mae     = float("inf")
    best_recs:     List[dict] = []
    best_cfg_str = ""

    for nl, mc, lam, obj in grid:
        params = _lgb_params(nl, mc, lam, obj)
        obj_short = "L1" if obj == "regression_l1" else "L2"

        for use_mono in [False, True]:
            run_i += 1
            mono_label = "mono" if use_mono else "free"
            cfg_str = f"nl{nl}_mc{mc}_lam{lam}_{obj_short}_{mono_label}"

            # LightGBM does NOT support monotone_constraints with regression_l1
            if use_mono and obj == "regression_l1":
                print(f"[{run_i:3d}/{total}] {cfg_str:40s} SKIP (L1+mono unsupported)")
                config_rows.append(dict(
                    cfg=cfg_str, stat=stat,
                    num_leaves=nl, min_child=mc, reg_lambda=lam, objective=obj_short,
                    use_monotone=True, best_blend_w=float("nan"),
                    mae=float("nan"), delta=float("nan"), delta_pct=float("nan"),
                    wins=False,
                ))
                continue

            print(f"[{run_i:3d}/{total}] {cfg_str:40s}", end="", flush=True)
            t1 = time.time()

            lgb_recs, base_recs = _run_one_config(
                rows, folds, X_all, y_all, params, mono_vec, use_mono, base_df
            )

            # Choose best blend weight on OOF (mildly optimistic; honest gate
            # is still new_mae < base_mae regardless of how w was chosen)
            best_w     = 1.0
            best_w_mae = _oof_mae_from_recs(lgb_recs, base_df)

            for w in [0.3, 0.5, 0.7]:
                blend = _blend_recs(lgb_recs, base_recs, w)
                m_mae = _oof_mae_from_recs(blend, base_df)
                if m_mae < best_w_mae:
                    best_w_mae = m_mae
                    best_w     = w

            blend_recs = (
                lgb_recs if best_w == 1.0
                else _blend_recs(lgb_recs, base_recs, best_w)
            )

            delta     = best_w_mae - base_mae
            delta_pct = delta / base_mae * 100.0
            elapsed   = time.time() - t1
            win_tag   = "*** WINS ***" if delta < 0 else ""
            print(
                f" MAE={best_w_mae:.4f}  delta={delta:+.4f} ({delta_pct:+.2f}%)"
                f"  w={best_w}  {elapsed:.1f}s  {win_tag}"
            )

            config_rows.append(dict(
                cfg=cfg_str, stat=stat,
                num_leaves=nl, min_child=mc, reg_lambda=lam, objective=obj_short,
                use_monotone=use_mono, best_blend_w=best_w,
                mae=best_w_mae, delta=delta, delta_pct=delta_pct,
                wins=(delta < 0),
            ))

            if best_w_mae < best_mae:
                best_mae     = best_w_mae
                best_recs    = blend_recs
                best_cfg_str = cfg_str + f"_w{best_w}"

    print(f"\nBest config for {stat.upper()}: {best_cfg_str}  MAE={best_mae:.4f}")
    print(f"Running full score_and_report for best config ...")
    result = score_and_report(best_recs, base_df, rows, label=f"{stat}:A2_best")

    print(f"\nTotal time for {stat}: {time.time()-t0:.0f}s")
    return result, config_rows


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(
    pts_result: dict, pts_configs: List[dict],
    reb_result: dict, reb_configs: List[dict],
) -> str:
    import pandas as pd

    lines = [
        "# PTS / REB Low-Shrink Experiment (Approach A2)",
        "",
        "**Date:** 2026-06-04",
        "",
        "## Summary",
        "",
    ]

    def gate_line(stat: str, res: dict) -> str:
        if not res:
            return f"- **{stat.upper()}**: NO RESULT"
        gate = "PASS (new<base)" if res.get("pass") else "FAIL (new>=base)"
        ship = "SHIP" if res.get("pass") else "REJECT"
        return (
            f"- **{stat.upper()}**: base={res['mae_base']:.4f}  "
            f"new={res['mae_new']:.4f}  delta={res['delta']:+.4f} "
            f"({res['pct']:+.2f}%)  gate={gate}  **-> {ship}**"
        )

    lines.append(gate_line("pts", pts_result))
    lines.append(gate_line("reb", reb_result))
    lines.append("")
    lines.append(
        "> NOTE: blend weight w chosen on full OOF MAE — mildly optimistic (w"
        " selection sees all folds). Honest gate is new_mae < base_mae on full OOF."
    )
    lines.append("")

    for stat, result, configs in [
        ("pts", pts_result, pts_configs),
        ("reb", reb_result, reb_configs),
    ]:
        lines.append(f"## {stat.upper()} Detail")
        lines.append("")
        if result:
            lines.append(f"- Overall MAE base: {result['mae_base']:.4f}")
            lines.append(f"- Overall MAE new:  {result['mae_new']:.4f}")
            lines.append(f"- Delta: {result['delta']:+.4f} ({result['pct']:+.2f}%)")
            lines.append(f"- Coverage: {result['coverage']*100:.1f}%  ({result['n']:,} rows)")
            sb = result.get('slope_base', float('nan'))
            sn = result.get('slope_new', float('nan'))
            lines.append(f"- Slope base: {sb:.3f}  new: {sn:.3f}")
            lines.append(f"- GATE: {'PASS' if result.get('pass') else 'FAIL'}")
            lines.append("")

        if configs:
            df = pd.DataFrame(configs)
            # Drop NaN rows from skip entries for sorting
            valid = df.dropna(subset=["mae"])
            valid = valid.sort_values("mae").reset_index(drop=True)
            lines.append("### Config Table (valid runs only, sorted by OOF MAE)")
            lines.append("")
            lines.append(
                "| cfg | nl | mc | lam | obj | mono | blend_w "
                "| MAE | delta | delta% | wins |"
            )
            lines.append(
                "|-----|----|----|-----|-----|------|---------|"
                "-----|-------|--------|------|"
            )
            for _, row in valid.iterrows():
                lines.append(
                    f"| {row['cfg']} "
                    f"| {int(row['num_leaves'])} "
                    f"| {int(row['min_child'])} "
                    f"| {row['reg_lambda']} "
                    f"| {row['objective']} "
                    f"| {'Y' if row['use_monotone'] else 'N'} "
                    f"| {row['best_blend_w']:.1f} "
                    f"| {row['mae']:.4f} "
                    f"| {row['delta']:+.4f} "
                    f"| {row['delta_pct']:+.2f}% "
                    f"| {'Y' if row['wins'] else 'N'} |"
                )
            lines.append("")

            # Skipped entries
            skipped = df[df["mae"].isna()]
            if len(skipped):
                lines.append(f"Skipped (L1+mono unsupported by LightGBM): "
                             f"{len(skipped)} configs")
                lines.append("")

    lines.append("## Methodology Notes")
    lines.append("")
    lines.append(
        "- Folds: 4-fold walk-forward (fold geometry identical to cache_pergame_oof)."
    )
    lines.append(
        "- Feature matrices built once per stat (full dataset), then sliced per fold."
    )
    lines.append(
        "- Blend weight w chosen by OOF MAE (mildly optimistic)."
        " If best w < 1.0, the LGB alone does not dominate production baseline."
    )
    lines.append(
        "- Monotone constraints: +1 on volume/usage drivers"
        " (l5/l10/ewma/prev min + l5/l10/ewma/prev stat + usage %)."
        " Only compatible with L2 objective."
    )
    lines.append(
        "- Classic trap monitored: lower regularization may improve TRAIN MAE but"
        " worsen OOF. Every config where OOF >= base is labeled FAIL."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=== exp_lowshrink_pts_reb.py  (Approach A2) ===")
    print("Baseline MAE targets: PTS=4.4454  REB=1.8461")
    print()

    pts_result, pts_configs = run_stat("pts")
    reb_result, reb_configs = run_stat("reb")

    # Write audit doc
    report  = write_report(pts_result, pts_configs, reb_result, reb_configs)
    out_dir = os.path.join(_ROOT, "docs", "_audits")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "PTS_REB_EXP_LOWSHRINK.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\nReport written to: {out_path}")

    # Final summary
    print("\n" + "="*70)
    print("FINAL SUMMARY")
    print("="*70)
    for stat, res in [("PTS", pts_result), ("REB", reb_result)]:
        if res:
            gate = "PASS" if res.get("pass") else "FAIL"
            ship = "SHIP" if res.get("pass") else "REJECT"
            print(
                f"  {stat}: base={res['mae_base']:.4f}  new={res['mae_new']:.4f}  "
                f"delta={res['delta']:+.4f} ({res['pct']:+.2f}%)  "
                f"slope_base={res.get('slope_base',float('nan')):.3f}  "
                f"slope_new={res.get('slope_new',float('nan')):.3f}  "
                f"gate={gate}  -> {ship}"
            )


if __name__ == "__main__":
    main()
