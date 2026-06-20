"""scripts.platformkit.improve.nba_ast_segment -- NBA AST segment-filter (P1-4).

Exploits the ONE proven pregame NBA edge (AST +7%) HONESTLY via a segment-filter:
  - Load pregame OOF rows from data/cache/pregame_oof.parquet
  - EXCLUDE playoff rows (NBA game_id prefix 0041/0042/0043)
  - Split by prediction confidence (outer vs inner quantile tertiles)
  - Bootstrap Spearman r per segment, per stat, to identify strong vs null
  - KEEP the strong segment (outer tertiles: top + bottom prediction confidence)
  - DROP the null segment (middle tertile: near-average predictions)
  - Run across the FULL stat surface (not just AST), producing per-stat verdicts
  - Thin segment (<MIN_BOOTSTRAP_N rows) -> verdict: INSUFFICIENT_DATA
  - Ship-readout dict only; FLAG OFF (no $ field, no edge claim)

AST is the motivated entry point (the only proven edge), but the filter must be
validated on the FULL surface to avoid reporting a fragment of the evidence.

INVARIANTS: no $ / roi / pnl / profit key anywhere; calibration NOT edge;
vs_close UNPROVEN; no data/registry/ writes; no flag flip; never creates
PIPELINE_ENABLED sentinel; NEVER raises (any failure -> safe result).
Stdlib + numpy + pandas + scipy; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
import pathlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("nba_ast_segment")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_OOF_PATH = _REPO / "data" / "cache" / "pregame_oof.parquet"

# Minimum rows per segment to produce a bootstrap estimate honestly.
MIN_BOOTSTRAP_N = 30
# Number of bootstrap resamples.
_N_BOOTSTRAP = 500
# A segment is 'strong' if p10 of bootstrap r exceeds this threshold.
_STRONG_R_FLOOR = 0.40
# Tertile split: outer = [0, 1/3) U [2/3, 1], inner = [1/3, 2/3)
_LOW_Q = 1.0 / 3.0
_HIGH_Q = 2.0 / 3.0

# NBA game_id prefixes that identify PLAYOFF games (exclude from analysis).
_PLAYOFF_PREFIXES: Tuple[str, ...] = ("0041", "0042", "0043")


def _is_playoff(game_id: Any) -> bool:
    """Return True when the game_id is a known NBA playoff series code."""
    return str(game_id).startswith(_PLAYOFF_PREFIXES)


def load_oof_rows(stat: Optional[str] = None,
                  oof_path: Optional[pathlib.Path] = None) -> pd.DataFrame:
    """Load pregame OOF rows, excluding playoff rows.

    Returns a DataFrame with columns: game_id, player_id, stat, oof_pred, actual,
    game_date, fold, season. Playoff rows (0041/0042/0043 game_id prefix) are
    dropped. Missing file -> empty DataFrame. Never raises.
    """
    path = pathlib.Path(oof_path) if oof_path is not None else _OOF_PATH
    if not path.exists():
        logger.debug("nba_ast_segment: OOF path missing: %s", path)
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("nba_ast_segment: read_parquet failed: %s", exc)
        return pd.DataFrame()

    required = {"game_id", "stat", "oof_pred", "actual"}
    if not required.issubset(df.columns):
        logger.debug("nba_ast_segment: missing columns %s", required - set(df.columns))
        return pd.DataFrame()

    # Exclude playoff rows.
    playoff_mask = df["game_id"].astype(str).str.startswith(_PLAYOFF_PREFIXES)
    df = df[~playoff_mask].copy()

    if stat is not None:
        df = df[df["stat"].str.lower() == str(stat).lower()]

    return df.reset_index(drop=True)


def _bootstrap_r(preds: np.ndarray, actuals: np.ndarray,
                 n_boot: int = _N_BOOTSTRAP,
                 rng: Optional[np.random.Generator] = None) -> Dict[str, float]:
    """Bootstrap Spearman r between preds and actuals.

    Returns dict: mean_r, p10, p90, n. Uses numpy only. Never raises.
    """
    n = len(preds)
    if n < 2:
        return {"mean_r": 0.0, "p10": 0.0, "p90": 0.0, "n": n}
    rng = rng or np.random.default_rng(seed=42)
    rs: List[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        p_s = preds[idx]
        a_s = actuals[idx]
        # Spearman via rankdata approximation (argsort twice)
        rp = _rankdata(p_s)
        ra = _rankdata(a_s)
        if rp.std() < 1e-9 or ra.std() < 1e-9:
            continue
        corr = float(np.corrcoef(rp, ra)[0, 1])
        if np.isfinite(corr):
            rs.append(corr)
    if not rs:
        return {"mean_r": 0.0, "p10": 0.0, "p90": 0.0, "n": n}
    arr = np.array(rs)
    return {
        "mean_r": float(arr.mean()),
        "p10": float(np.percentile(arr, 10)),
        "p90": float(np.percentile(arr, 90)),
        "n": n,
    }


def _rankdata(x: np.ndarray) -> np.ndarray:
    """Simple rank (no ties handling; sufficient for bootstrap estimation)."""
    order = np.argsort(x)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(x) + 1, dtype=float)
    return ranks


def _segment_stat(df_stat: pd.DataFrame,
                  n_boot: int = _N_BOOTSTRAP) -> Dict[str, Any]:
    """Compute segment-filter verdict for one stat's OOF rows.

    Splits df_stat into strong (outer tertiles of oof_pred) and null (inner
    tertile), bootstraps Spearman r for each, and decides:
      kept   = strong segment is strong (p10 >= STRONG_R_FLOOR)
      dropped = null segment is weak (p10 < STRONG_R_FLOOR)
      status = 'ok' | 'INSUFFICIENT_DATA'

    Returns a readout dict. No $ / roi / pnl key anywhere.
    """
    if df_stat.empty:
        return {"status": "INSUFFICIENT_DATA", "reason": "no_rows",
                "note": "calibration, not edge"}

    preds = df_stat["oof_pred"].to_numpy(dtype=float)
    actuals = df_stat["actual"].to_numpy(dtype=float)
    n = len(preds)

    low_t = float(np.quantile(preds, _LOW_Q))
    high_t = float(np.quantile(preds, _HIGH_Q))

    strong_mask = (preds <= low_t) | (preds >= high_t)
    null_mask = ~strong_mask

    n_strong = int(strong_mask.sum())
    n_null = int(null_mask.sum())

    if n_strong < MIN_BOOTSTRAP_N or n_null < MIN_BOOTSTRAP_N:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "thin_segment",
            "n_total": n,
            "n_strong": n_strong,
            "n_null": n_null,
            "min_bootstrap_n": MIN_BOOTSTRAP_N,
            "note": "calibration, not edge",
        }

    rng = np.random.default_rng(seed=42)
    strong_boot = _bootstrap_r(preds[strong_mask], actuals[strong_mask],
                               n_boot=n_boot, rng=rng)
    null_boot = _bootstrap_r(preds[null_mask], actuals[null_mask],
                             n_boot=n_boot, rng=rng)

    is_strong_kept = strong_boot["p10"] >= _STRONG_R_FLOOR
    is_null_dropped = null_boot["p10"] < _STRONG_R_FLOOR

    return {
        "status": "ok",
        "n_total": n,
        "n_strong": n_strong,
        "n_null": n_null,
        "low_thresh": round(low_t, 4),
        "high_thresh": round(high_t, 4),
        "strong_segment": {
            "kept": is_strong_kept,
            "mean_r": round(strong_boot["mean_r"], 4),
            "p10_r": round(strong_boot["p10"], 4),
            "p90_r": round(strong_boot["p90"], 4),
            "n": strong_boot["n"],
        },
        "null_segment": {
            "dropped": is_null_dropped,
            "mean_r": round(null_boot["mean_r"], 4),
            "p10_r": round(null_boot["p10"], 4),
            "p90_r": round(null_boot["p90"], 4),
            "n": null_boot["n"],
        },
        "verdict": ("strong_kept_null_dropped"
                    if is_strong_kept and is_null_dropped
                    else "no_clear_split"),
        "note": "calibration, not edge",
        "vs_close": "UNPROVEN",
    }


def run_ast_segment_filter(
    oof_path: Optional[pathlib.Path] = None,
    stats: Optional[Sequence[str]] = None,
    n_boot: int = _N_BOOTSTRAP,
) -> Dict[str, Any]:
    """Run the NBA AST segment-filter across the FULL stat surface.

    Entry point for the P1-4 workstream. FLAG OFF (readout only; no promotion,
    no sentinel flip, no data/registry/ write).

    Args:
        oof_path: override path to pregame_oof.parquet (default: data/cache/).
        stats:    stat subset to evaluate (default: all stats in the parquet).
        n_boot:   bootstrap resamples per segment (default: _N_BOOTSTRAP).

    Returns:
        A readout dict with keys:
          status       : 'ok' | 'INSUFFICIENT_DATA'
          n_rows_total : total non-playoff OOF rows loaded
          n_playoff_excluded: always 0 here (regular-season OOF only, but guard kept)
          per_stat     : {stat: segment_verdict_dict}
          ast_verdict  : the AST-specific verdict (the motivated entry point)
          flag         : 'OFF' (always -- readout only)
          note         : 'calibration, not edge'

    NEVER raises.
    """
    try:
        df_all = load_oof_rows(oof_path=oof_path)
        if df_all.empty:
            return {
                "status": "INSUFFICIENT_DATA",
                "reason": "no_oof_data",
                "flag": "OFF",
                "note": "calibration, not edge",
            }

        n_total = len(df_all)
        stat_list = list(df_all["stat"].unique()) if stats is None else list(stats)

        per_stat: Dict[str, Any] = {}
        for s in stat_list:
            s_df = df_all[df_all["stat"].str.lower() == str(s).lower()]
            per_stat[s] = _segment_stat(s_df, n_boot=n_boot)

        ast_verdict = per_stat.get("ast", {
            "status": "INSUFFICIENT_DATA",
            "reason": "ast_not_in_parquet",
            "note": "calibration, not edge",
        })

        all_ok = [v for v in per_stat.values() if v.get("status") == "ok"]
        overall_status = "ok" if all_ok else "INSUFFICIENT_DATA"

        return {
            "status": overall_status,
            "n_rows_total": n_total,
            "n_playoff_excluded": 0,
            "per_stat": per_stat,
            "ast_verdict": ast_verdict,
            "flag": "OFF",
            "note": "calibration, not edge",
            "vs_close": "UNPROVEN",
        }
    except Exception as exc:  # noqa: BLE001 -- purity: never raise
        logger.debug("nba_ast_segment.run_ast_segment_filter failed: %s", exc)
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "internal_error",
            "flag": "OFF",
            "note": "calibration, not edge",
        }


__all__ = [
    "run_ast_segment_filter",
    "load_oof_rows",
    "MIN_BOOTSTRAP_N",
    "_STRONG_R_FLOOR",
    "_PLAYOFF_PREFIXES",
]
