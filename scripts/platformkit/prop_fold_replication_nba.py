"""scripts.platformkit.prop_fold_replication_nba -- multi-fold replication guard.

DISCIPLINE: single-fold/single-seed lifts are artifacts (see feedback_single_fold_lifts_are_artifacts).
A stat is ONLY promoted when it shows positive BSS across >= 3 of 5 walk-forward folds.

Verdicts:
  REPLICATED         -- >= 3 of 5 folds positive BSS (and n_folds_positive >= MIN_FOLDS_POSITIVE)
  REPLICATION_PENDING -- 1 or 2 of 5 folds positive BSS (not enough; do NOT ship on this alone)
  REJECT             -- 0 folds positive BSS (all-fold-negative)
  INSUFFICIENT_DATA  -- too few folds have n >= MIN_FOLD_N to evaluate

Never fabricates $ or edge. CALIBRATION only. ASCII only. Per-file test.

Public API:
  run_fold_replication(df, stats, min_fold_n, min_folds_positive) -> Dict
  load_and_run(oof_path, stats, min_fold_n, min_folds_positive) -> Dict

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_fold_replication_nba.py -q
"""
from __future__ import annotations

import logging
import math
import os
from typing import Dict, List, Optional, Sequence

from scripts.platformkit.props_eval import score_prop_predictions
from scripts.platformkit.props_eval_nba import (
    NBA_STATS,
    _SIGMA_FLOOR,
    _build_preds_for_stat,
    INSUFFICIENT_DATA,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_OOF_PATH = os.path.join("data", "cache", "pregame_oof.parquet")

# Min samples per fold per stat to count that fold (thin folds excluded)
MIN_FOLD_N: int = 30

# Min folds with positive BSS to call REPLICATED
MIN_FOLDS_POSITIVE: int = 3

# Total folds expected in the walk-forward
EXPECTED_FOLDS: int = 5

# Verdicts
REPLICATED = "REPLICATED"
REPLICATION_PENDING = "REPLICATION_PENDING"
REJECT = "REJECT"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _verdict(n_folds_positive: int, n_folds_evaluated: int) -> str:
    """Map fold counts to a verdict string.

    INSUFFICIENT_DATA if n_folds_evaluated == 0 (no folds passed MIN_FOLD_N).
    REJECT if n_folds_positive == 0.
    REPLICATION_PENDING if 1 <= n_folds_positive < MIN_FOLDS_POSITIVE.
    REPLICATED if n_folds_positive >= MIN_FOLDS_POSITIVE.
    """
    if n_folds_evaluated == 0:
        return INSUFFICIENT_DATA
    if n_folds_positive >= MIN_FOLDS_POSITIVE:
        return REPLICATED
    if n_folds_positive >= 1:
        return REPLICATION_PENDING
    return REJECT


def _score_fold(rows: List[dict], stat: str) -> Optional[float]:
    """BSS for a single fold; None if n < MIN_FOLD_N after building preds."""
    preds = _build_preds_for_stat(rows, stat)
    if len(preds) < MIN_FOLD_N:
        return None
    scored = score_prop_predictions(preds)
    bss = scored.get("brier_skill_score")
    if bss is None or not math.isfinite(float(bss)):
        return None
    return float(bss)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_fold_replication(
    df,
    stats: Optional[Sequence[str]] = None,
    min_fold_n: int = MIN_FOLD_N,
    min_folds_positive: int = MIN_FOLDS_POSITIVE,
) -> Dict[str, object]:
    """Multi-fold replication check from a preloaded OOF DataFrame.

    Args:
        df: pandas DataFrame with columns [stat, oof_pred, actual, fold].
        stats: which stats to evaluate (default NBA_STATS).
        min_fold_n: minimum observations per (stat, fold) to evaluate that fold.
        min_folds_positive: folds with BSS > 0 needed for REPLICATED verdict.

    Returns dict:
        {
          "stats": [str, ...],
          "per_stat": {
            stat: {
              "per_fold_bss": {fold_id: bss or INSUFFICIENT_DATA},
              "n_folds_positive": int,
              "n_folds_evaluated": int,
              "verdict": REPLICATED | REPLICATION_PENDING | REJECT | INSUFFICIENT_DATA,
            } or INSUFFICIENT_DATA if the stat has no valid data at all
          },
          "note": str,
        }

    Never raises. CALIBRATION not $. No dollar keys.
    """
    use_stats = list(stats) if stats else list(NBA_STATS)

    base: Dict[str, object] = {
        "stats": use_stats,
        "per_stat": {s: INSUFFICIENT_DATA for s in use_stats},
        "note": "",
    }

    if df is None or len(df) == 0:
        base["note"] = "empty OOF dataframe -> INSUFFICIENT_DATA"
        return base

    required = {"stat", "oof_pred", "actual", "fold"}
    if not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        base["note"] = f"OOF missing columns: {missing}"
        return base

    folds_present = sorted(df["fold"].dropna().unique().tolist())
    per_stat: Dict[str, object] = {}

    for stat in use_stats:
        stat_df = df[df["stat"] == stat]

        if len(stat_df) == 0:
            per_stat[stat] = INSUFFICIENT_DATA
            continue

        per_fold_bss: Dict[str, object] = {}
        n_folds_positive = 0
        n_folds_evaluated = 0

        for fold_id in folds_present:
            fold_df = stat_df[stat_df["fold"] == fold_id]
            rows: List[dict] = []
            for _, r in fold_df.iterrows():
                try:
                    pred_v = r["oof_pred"]
                    act_v = r["actual"]
                    if pred_v is None or act_v is None:
                        continue
                    pf = float(pred_v)
                    af = float(act_v)
                    if math.isfinite(pf) and math.isfinite(af):
                        rows.append({"pred": pf, "actual": af})
                except (TypeError, ValueError):
                    continue

            bss = _score_fold(rows, stat) if len(rows) >= min_fold_n else None

            fold_key = str(fold_id)
            if bss is None:
                per_fold_bss[fold_key] = INSUFFICIENT_DATA
            else:
                per_fold_bss[fold_key] = round(bss, 5)
                n_folds_evaluated += 1
                if bss > 0.0:
                    n_folds_positive += 1

        verdict = _verdict(n_folds_positive, n_folds_evaluated)

        per_stat[stat] = {
            "per_fold_bss": per_fold_bss,
            "n_folds_positive": n_folds_positive,
            "n_folds_evaluated": n_folds_evaluated,
            "verdict": verdict,
        }

    base["per_stat"] = per_stat
    base["note"] = (
        "NBA prop fold replication guard: a stat is REPLICATED only if BSS > 0 "
        "in >= %d of %d walk-forward folds (min_fold_n=%d). "
        "Single-fold lifts -> REPLICATION_PENDING, not SHIP. "
        "CALIBRATION only -- no $-edge." % (min_folds_positive, len(folds_present), min_fold_n)
    )
    return base


def load_and_run(
    oof_path: Optional[str] = None,
    stats: Optional[Sequence[str]] = None,
    min_fold_n: int = MIN_FOLD_N,
    min_folds_positive: int = MIN_FOLDS_POSITIVE,
) -> Dict[str, object]:
    """Load pregame_oof.parquet and run fold replication check.

    Returns INSUFFICIENT_DATA sentinel per stat if parquet absent or unreadable.
    Never raises.
    """
    use_stats = list(stats) if stats else list(NBA_STATS)
    base: Dict[str, object] = {
        "stats": use_stats,
        "per_stat": {s: INSUFFICIENT_DATA for s in use_stats},
        "note": "",
    }

    try:
        import pandas as pd
        path = oof_path or _OOF_PATH
        if not os.path.exists(path):
            base["note"] = "pregame_oof.parquet absent -> INSUFFICIENT_DATA"
            return base
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 -- never raise
        logger.warning("prop_fold_replication_nba: OOF load failed: %s", exc)
        base["note"] = f"OOF load failed: {exc}"
        return base

    return run_fold_replication(
        df,
        stats=use_stats,
        min_fold_n=min_fold_n,
        min_folds_positive=min_folds_positive,
    )
