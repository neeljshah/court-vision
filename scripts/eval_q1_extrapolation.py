"""scripts/eval_q1_extrapolation.py -- INT-70 F1 Q1-Extrapolation Validation.

Walk-forward retro over 4-fold chronological GroupKFold. Compares three predictors:
  1. Pregame baseline  -- L20 rolling mean per stat
  2. Q1-no-CV          -- LGB-q50 head, priors + Q1 actuals only (no CV block)
  3. Q1+CV             -- LGB-q50 head, priors + Q1 actuals + 5 CV cumulatives

Ship gates (both must hold on >= 3/4 folds per stat):
  Gate A: MAE(Q1+CV) <= 0.90 * MAE(pregame)   -- >= 10% lift over pregame
  Gate B: MAE(Q1+CV) <= 0.95 * MAE(Q1-no-CV)  -- CV adds >= 5% on top of Q1 actuals

Mandatory null control:
  Shuffle CV cumulatives across game_id (5 seeds). Retrain. Compute Gate B delta.
  REJECT CV block if |real_delta - null_delta| < 0.5 * stddev(null deltas across seeds).

EARLY STOP: if cv_used rows < 200, prints message and exits 0 cleanly.

Usage:
    python scripts/eval_q1_extrapolation.py
    python scripts/eval_q1_extrapolation.py --max-games 200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
VAULT_DIR = ROOT / "vault" / "Intelligence"
NULL_CONTROL_OUT = VAULT_DIR / "INT-70_null_control.json"
EARLY_STOP_THRESHOLD = 200

LGB_PARAMS_Q50 = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 80,
    "objective": "quantile",
    "alpha": 0.5,
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}

FEATURE_BASE = [
    "pts_q1", "reb_q1", "ast_q1", "fg3m_q1", "stl_q1", "blk_q1", "tov_q1", "pf_q1",
    "min_q1", "pos_C", "pos_F", "pos_G", "cv_n_games_cv",
]

FEATURE_CV = [
    "paint_dwell_so_far_q1", "touches_so_far_q1", "contested_so_far_q1",
    "avg_def_dist_so_far_q1", "shots_per_poss_so_far_q1",
]


# ---------------------------------------------------------------------------
# Data loading (re-uses build_q1_extrapolation_signals.py logic)
# ---------------------------------------------------------------------------

def load_or_build_rows(max_games: Optional[int] = None) -> list:
    """Load from signals parquet if fresh, else rebuild via build script."""
    signals_path = ROOT / "data" / "intelligence" / "q1_extrapolation_signals.parquet"
    if signals_path.exists():
        import pandas as pd
        df = pd.read_parquet(str(signals_path))
        if len(df) > 0:
            return df.to_dict("records")

    # Rebuild
    import importlib, importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_q1", ROOT / "scripts" / "build_q1_extrapolation_signals.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _, _, _, rows = mod.build_training_rows(max_games)
    return rows


# ---------------------------------------------------------------------------
# Pregame baseline (L20 rolling mean)
# ---------------------------------------------------------------------------

def _build_pregame_lookup(rows: list) -> Dict[Tuple[int, str, str], float]:
    """Build {(player_id, game_id, stat): l20_mean} pregame baseline.

    Uses per-player game history from gamelog JSONs (same as train_period_heads.py).
    Falls back to global mean if no history available.
    """
    import glob, json as _json
    from collections import defaultdict

    logs: Dict[int, List[Tuple[str, Dict[str, float]]]] = defaultdict(list)
    for fp in glob.glob(str(ROOT / "data" / "nba" / "gamelog_*.json")):
        try:
            pid = int(Path(fp).stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        try:
            games = _json.loads(Path(fp).read_text(encoding="utf-8")) or []
        except Exception:
            continue
        for r in games:
            try:
                from datetime import datetime
                d = datetime.strptime(str(r.get("GAME_DATE")), "%b %d, %Y").date().isoformat()
                m = float(r.get("MIN") or 0)
            except (TypeError, ValueError):
                continue
            if m < 1.0:
                continue
            stats = {s: float(r.get(s.upper()) or 0) for s in STATS}
            stats["min"] = m
            logs[pid].append((d, stats))

    for pid in logs:
        logs[pid].sort(key=lambda x: x[0])

    # Global fallback
    global_means: Dict[str, float] = {}
    for stat in STATS:
        vals = [r[f"{stat}_full"] for r in rows if r.get(f"{stat}_full") is not None]
        global_means[stat] = float(sum(vals) / len(vals)) if vals else 0.0

    # Build lookup: for each (pid, gid), L20 prior games
    lookup: Dict[Tuple[int, str, str], float] = {}
    # Deduplicate by (pid, gid)
    seen_pid_gid: Dict[Tuple[int, str], str] = {}
    for r in rows:
        pid = r["player_id"]
        gid = r["game_id"]
        seen_pid_gid[(pid, gid)] = gid

    for (pid, gid), _ in seen_pid_gid.items():
        log = logs.get(int(pid), [])
        for stat in STATS:
            prior = [s[stat] for (d, s) in log][-20:]
            if prior:
                lookup[(pid, gid, stat)] = float(sum(prior) / len(prior))
            else:
                lookup[(pid, gid, stat)] = global_means.get(stat, 0.0)

    return lookup


# ---------------------------------------------------------------------------
# Training helper
# ---------------------------------------------------------------------------

def _train_fold(
    train_rows: list,
    stat: str,
    with_cv: bool,
) -> Optional[object]:
    import numpy as np
    import lightgbm as lgb

    feats = FEATURE_BASE + (FEATURE_CV if with_cv else [])
    X = np.array([[r.get(k, 0.0) for k in feats] for r in train_rows], dtype=np.float32)
    y = np.array([r.get(f"{stat}_full", 0.0) for r in train_rows], dtype=np.float32)
    if len(X) < LGB_PARAMS_Q50["min_child_samples"]:
        return None
    model = lgb.LGBMRegressor(**LGB_PARAMS_Q50)
    model.fit(X, y, feature_name=feats)
    return model


def _predict_fold(model, val_rows: list, with_cv: bool) -> list:
    import numpy as np
    feats = FEATURE_BASE + (FEATURE_CV if with_cv else [])
    X = np.array([[r.get(k, 0.0) for k in feats] for r in val_rows], dtype=np.float32)
    return model.predict(X).tolist()


# ---------------------------------------------------------------------------
# Walk-forward evaluation
# ---------------------------------------------------------------------------

def walk_forward_eval(
    rows: list,
    pregame_lookup: Dict,
) -> Dict[str, List[Dict]]:
    """4-fold chronological GroupKFold.

    Returns {stat: [fold_dict, ...]} where fold_dict has:
      mae_pregame, mae_q1_no_cv, mae_q1_cv, n_val
    """
    import numpy as np

    unique_games = list(dict.fromkeys(r["game_id"] for r in rows))
    n_games = len(unique_games)
    fold_size = max(1, n_games // 4)

    results: Dict[str, List[Dict]] = {s: [] for s in STATS}

    for fi in range(4):
        lo = fi * fold_size
        hi = n_games if fi == 3 else (fi + 1) * fold_size
        val_games = set(unique_games[lo:hi])
        train_games = set(unique_games[:lo] + unique_games[hi:])

        train_rows = [r for r in rows if r["game_id"] in train_games and not r.get("cv_q1_proxy", False)]
        val_rows = [r for r in rows if r["game_id"] in val_games and not r.get("cv_q1_proxy", False)]

        if not val_rows:
            print(f"  [fold {fi+1}] no val rows, skip")
            continue

        print(f"  [fold {fi+1}] train={len(train_rows)} val={len(val_rows)}")

        for stat in STATS:
            y_true = np.array([r.get(f"{stat}_full", 0.0) for r in val_rows])

            # Pregame baseline
            y_pregame = np.array([
                pregame_lookup.get((r["player_id"], r["game_id"], stat),
                                   float(np.mean(y_true))) for r in val_rows
            ])
            mae_pregame = float(np.mean(np.abs(y_pregame - y_true)))

            # Q1-no-CV
            mae_q1_no_cv = float("nan")
            m_no_cv = _train_fold(train_rows, stat, with_cv=False)
            if m_no_cv is not None:
                preds_no_cv = np.array(_predict_fold(m_no_cv, val_rows, with_cv=False))
                mae_q1_no_cv = float(np.mean(np.abs(preds_no_cv - y_true)))

            # Q1+CV (only on cv_used rows in val set)
            val_cv = [r for r in val_rows if r.get("cv_used", False) and not r.get("cv_q1_proxy", False)]
            mae_q1_cv = float("nan")
            if val_cv:
                train_cv = [r for r in train_rows if r.get("cv_used", False)]
                m_cv = _train_fold(train_cv if train_cv else train_rows, stat, with_cv=True)
                if m_cv is not None:
                    y_cv_true = np.array([r.get(f"{stat}_full", 0.0) for r in val_cv])
                    preds_cv = np.array(_predict_fold(m_cv, val_cv, with_cv=True))
                    mae_q1_cv = float(np.mean(np.abs(preds_cv - y_cv_true)))
                    # Recompute mae_pregame + mae_q1_no_cv on same cv subset for fair gate comparison
                    y_pg_cv = np.array([
                        pregame_lookup.get((r["player_id"], r["game_id"], stat),
                                          float(np.mean(y_cv_true))) for r in val_cv
                    ])
                    mae_pregame = float(np.mean(np.abs(y_pg_cv - y_cv_true)))
                    if m_no_cv is not None:
                        preds_no_cv_subset = np.array(_predict_fold(m_no_cv, val_cv, with_cv=False))
                        mae_q1_no_cv = float(np.mean(np.abs(preds_no_cv_subset - y_cv_true)))

            print(f"    [{stat}] pregame={mae_pregame:.4f} q1_no_cv={mae_q1_no_cv:.4f} q1_cv={mae_q1_cv:.4f}")
            results[stat].append({
                "fold": fi + 1,
                "n_val": len(val_cv) if val_cv else len(val_rows),
                "mae_pregame": round(mae_pregame, 5),
                "mae_q1_no_cv": round(mae_q1_no_cv, 5),
                "mae_q1_cv": round(mae_q1_cv, 5),
                "gate_a": mae_q1_cv <= 0.90 * mae_pregame if not any(
                    v != v for v in [mae_q1_cv, mae_pregame]) else False,
                "gate_b": mae_q1_cv <= 0.95 * mae_q1_no_cv if not any(
                    v != v for v in [mae_q1_cv, mae_q1_no_cv]) else False,
            })

    return results


# ---------------------------------------------------------------------------
# Null control
# ---------------------------------------------------------------------------

def null_control(
    rows: list,
    n_seeds: int = 5,
) -> Dict[str, Dict]:
    """Shuffle CV cumulatives across game_id (5 seeds). Measure Gate B delta."""
    import numpy as np
    import lightgbm as lgb

    unique_games = list(dict.fromkeys(r["game_id"] for r in rows))
    n_games = len(unique_games)
    fold_size = max(1, n_games // 4)

    null_results: Dict[str, Dict] = {}

    for stat in STATS:
        null_deltas_per_seed = []

        for seed in range(n_seeds):
            rng = np.random.RandomState(seed)
            # Permute CV cumulatives across game_id
            game_ids = [r["game_id"] for r in rows]
            shuffled_idx = rng.permutation(len(rows))

            permuted_rows = []
            for i, r in enumerate(rows):
                r2 = dict(r)
                src = rows[shuffled_idx[i]]
                for k in FEATURE_CV:
                    r2[k] = src.get(k, 0.0)
                permuted_rows.append(r2)

            # 4-fold WF MAE delta (Q1+CV vs Q1-no-CV) on permuted data
            fold_deltas = []
            for fi in range(4):
                lo = fi * fold_size
                hi = n_games if fi == 3 else (fi + 1) * fold_size
                val_games = set(unique_games[lo:hi])
                train_games = set(unique_games[:lo] + unique_games[hi:])

                tr = [r for r in permuted_rows
                      if r["game_id"] in train_games and not r.get("cv_q1_proxy", False)]
                va = [r for r in permuted_rows
                      if r["game_id"] in val_games and not r.get("cv_q1_proxy", False)]
                if not va:
                    continue

                y_true = np.array([r.get(f"{stat}_full", 0.0) for r in va])

                m_no_cv = _train_fold(tr, stat, with_cv=False)
                m_cv = _train_fold(tr, stat, with_cv=True)
                if m_no_cv is None or m_cv is None:
                    continue

                p_no_cv = np.array(_predict_fold(m_no_cv, va, with_cv=False))
                p_cv = np.array(_predict_fold(m_cv, va, with_cv=True))

                mae_no_cv = float(np.mean(np.abs(p_no_cv - y_true)))
                mae_cv = float(np.mean(np.abs(p_cv - y_true)))
                fold_deltas.append(mae_cv - mae_no_cv)

            if fold_deltas:
                null_deltas_per_seed.append(float(np.mean(fold_deltas)))

        null_mean = float(np.mean(null_deltas_per_seed)) if null_deltas_per_seed else 0.0
        null_std = float(np.std(null_deltas_per_seed)) if len(null_deltas_per_seed) > 1 else 0.0
        null_results[stat] = {
            "null_delta_mean": round(null_mean, 5),
            "null_delta_std": round(null_std, 5),
            "null_deltas_per_seed": [round(x, 5) for x in null_deltas_per_seed],
        }

    return null_results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="INT-70 Q1-Extrapolation walk-forward eval.")
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--skip-null-control", action="store_true",
                    help="Skip null control (faster iteration)")
    args = ap.parse_args()

    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== INT-70 eval: loading rows ===")
    rows = load_or_build_rows(args.max_games)

    # Filter non-proxy rows for evaluation
    eval_rows = [r for r in rows if not r.get("cv_q1_proxy", False)]
    n_cv_used = sum(1 for r in eval_rows if r.get("cv_used", False))
    print(f"  Total rows: {len(rows)}")
    print(f"  Non-proxy rows: {len(eval_rows)}")
    print(f"  cv_used (non-proxy): {n_cv_used}")
    print(f"  N games: {len(set(r['game_id'] for r in eval_rows))}")

    if n_cv_used < EARLY_STOP_THRESHOLD:
        print(f"\nEARLY STOP: cv_used rows {n_cv_used} < {EARLY_STOP_THRESHOLD}.")
        print("Run build_q1_extrapolation_signals.py first and check INT-70_EARLY_STOP_LOW_COVERAGE.md")
        return 0

    print("\n=== Building pregame lookup ===")
    pregame_lookup = _build_pregame_lookup(eval_rows)
    print(f"  Lookup entries: {len(pregame_lookup)}")

    print("\n=== Walk-forward evaluation (4-fold) ===")
    wf_results = walk_forward_eval(eval_rows, pregame_lookup)

    # Compute per-stat ship verdict
    import numpy as np
    ship_verdicts: Dict[str, Dict] = {}
    for stat in STATS:
        folds = wf_results[stat]
        gate_a_wins = sum(1 for f in folds if f.get("gate_a", False))
        gate_b_wins = sum(1 for f in folds if f.get("gate_b", False))
        ship = gate_a_wins >= 3 and gate_b_wins >= 3
        ship_verdicts[stat] = {
            "gate_a_wins": gate_a_wins,
            "gate_b_wins": gate_b_wins,
            "ship": ship,
            "folds": folds,
        }
        status = "SHIP" if ship else "REJECT"
        print(f"  [{stat}] Gate A: {gate_a_wins}/4  Gate B: {gate_b_wins}/4  -> {status}")

    # Null control
    null_results = {}
    if not args.skip_null_control and len(eval_rows) >= EARLY_STOP_THRESHOLD:
        print("\n=== Null control (5 seeds) ===")
        null_results = null_control(eval_rows)

        # Check rejection condition per stat
        for stat in STATS:
            nr = null_results.get(stat, {})
            # Real delta = mean MAE(q1_cv) - mean MAE(q1_no_cv) across folds
            real_deltas = [
                f["mae_q1_cv"] - f["mae_q1_no_cv"]
                for f in wf_results[stat]
                if not any(v != v for v in [f["mae_q1_cv"], f["mae_q1_no_cv"]])
            ]
            real_delta = float(np.mean(real_deltas)) if real_deltas else 0.0
            null_mean = nr.get("null_delta_mean", 0.0)
            null_std = nr.get("null_delta_std", 0.0)
            null_reject = abs(real_delta - null_mean) < 0.5 * null_std
            nr["real_delta"] = round(real_delta, 5)
            nr["null_reject"] = null_reject
            if null_reject and ship_verdicts[stat]["ship"]:
                ship_verdicts[stat]["ship"] = False
                ship_verdicts[stat]["null_control_override"] = True
                print(f"  [{stat}] NULL CONTROL OVERRIDE — real_delta={real_delta:.4f} "
                      f"null_mean={null_mean:.4f} null_std={null_std:.4f} -> REJECT")
            else:
                print(f"  [{stat}] null ok: real={real_delta:.4f} null={null_mean:.4f}±{null_std:.4f}")

        null_control_out_data = {
            "note": "INT-70 null control: CV cumulatives permuted across game_id",
            "n_seeds": 5,
            "per_stat": null_results,
        }
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        NULL_CONTROL_OUT.write_text(
            json.dumps(null_control_out_data, indent=2), encoding="utf-8"
        )
        print(f"  Null control saved: {NULL_CONTROL_OUT}")

    # Write vault doc
    doc_path = VAULT_DIR / "INT-70_Q1_Extrapolation_Extension.md"
    shipped = [s for s in STATS if ship_verdicts[s]["ship"]]
    rejected = [s for s in STATS if not ship_verdicts[s]["ship"]]

    fold_table_lines = [
        "| stat | fold | n_val | pregame_MAE | q1_noCV_MAE | q1+CV_MAE | Gate A | Gate B |",
        "|------|------|-------|-------------|-------------|-----------|--------|--------|",
    ]
    for stat in STATS:
        for f in wf_results[stat]:
            gate_a = "PASS" if f.get("gate_a") else "fail"
            gate_b = "PASS" if f.get("gate_b") else "fail"
            fold_table_lines.append(
                f"| {stat} | {f['fold']} | {f['n_val']} | {f['mae_pregame']:.4f} | "
                f"{f['mae_q1_no_cv']:.4f} | {f['mae_q1_cv']:.4f} | {gate_a} | {gate_b} |"
            )

    null_lines = []
    if null_results:
        null_lines = [
            "",
            "## Null control",
            "",
            "| stat | real_delta | null_mean | null_std | reject? |",
            "|------|-----------|-----------|----------|---------|",
        ]
        for stat in STATS:
            nr = null_results.get(stat, {})
            null_lines.append(
                f"| {stat} | {nr.get('real_delta', 0):.4f} | "
                f"{nr.get('null_delta_mean', 0):.4f} | "
                f"{nr.get('null_delta_std', 0):.4f} | "
                f"{'YES — REJECT' if nr.get('null_reject') else 'no'} |"
            )

    newline = "\n"
    verdict_status = "PARTIAL SHIP" if shipped else "REJECT ALL"
    shipped_str = ", ".join(shipped) if shipped else "none"
    rejected_str = ", ".join(rejected) if rejected else "none"
    n_eval_games = len(set(r["game_id"] for r in eval_rows))
    n_eval_players = len(set(r["player_id"] for r in eval_rows))

    verdict_rows = []
    for s in STATS:
        ga = ship_verdicts[s]["gate_a_wins"]
        gb = ship_verdicts[s]["gate_b_wins"]
        verd = "SHIP" if ship_verdicts[s]["ship"] else "REJECT"
        verdict_rows.append(f"| {s} | {ga}/4 | {gb}/4 | {verd} |")
    verdict_table = newline.join(verdict_rows)

    fold_table = newline.join(fold_table_lines)
    null_section = newline.join(null_lines)

    doc = (
        f"# INT-70 Q1 Extrapolation Extension (F1)\n\n"
        f"**Date:** 2026-05-29\n"
        f"**Status:** {verdict_status}\n"
        f"**Shipped stats:** {shipped_str}\n"
        f"**Rejected stats:** {rejected_str}\n\n"
        f"## Coverage\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Non-proxy eval rows | {len(eval_rows)} |\n"
        f"| cv_used rows | {n_cv_used} |\n"
        f"| N games | {n_eval_games} |\n"
        f"| N players | {n_eval_players} |\n\n"
        f"## Walk-forward results (4-fold GroupKFold by game_id, chronological)\n\n"
        f"{fold_table}\n\n"
        f"## Per-stat verdict\n\n"
        f"| stat | Gate A (>=3/4) | Gate B (>=3/4) | Verdict |\n"
        f"|------|---------------|---------------|----------|\n"
        f"{verdict_table}\n"
        f"{null_section}\n\n"
        f"## Files\n\n"
        f"- `data/intelligence/q1_extrapolation_signals.parquet` — training dataset\n"
        f"- `data/models/q1_extrap_heads/<stat>_q50.lgb` — shipped heads ({shipped_str})\n"
        f"- `vault/Intelligence/INT-70_null_control.json` — null control results\n\n"
        f"## Notes\n\n"
        f"Gate A: MAE(Q1+CV) <= 0.90 * MAE(pregame) — 10% lift over pregame baseline\n"
        f"Gate B: MAE(Q1+CV) <= 0.95 * MAE(Q1-no-CV) — CV adds 5% on top of Q1 actuals\n"
        f"Null control: permute CV cumulatives across game_id (5 seeds), reject if real delta indistinguishable from null\n"
    )
    doc_path.write_text(doc, encoding="utf-8")
    print(f"\n  Vault doc: {doc_path}")

    print(f"\nFinal verdict: {len(shipped)}/7 stats SHIP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
