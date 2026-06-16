"""Pure scoring for the track-record ledger (blueprint X3 / mcp-and-ledger PART B).

Proper-score core (no I/O): Brier, ECE (10 equal-WIDTH bins, stated), Murphy decomposition,
and the cluster-robust Diebold-Mariano vs the devigged close (reused verbatim from the
verified eval_gate/dm_test.py, clustered by game_id). compute_calibration() reports
Brier/ECE/resolution and -- only with enough power -- a DM test vs the close.

edge_claimed is ALWAYS False. A DM p >= 0.05 (or too few rows) is an HONEST REJECT
("market efficient"), surfaced as such, never buried. We score calibration, never $.
"""
from __future__ import annotations
import pathlib
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional

import numpy as np
import pandas as pd

# reuse the VERIFIED clustered DM reference from the eval_gate package
_EVAL_GATE = pathlib.Path(__file__).resolve().parents[1] / "eval_gate"
if str(_EVAL_GATE) not in sys.path:
    sys.path.insert(0, str(_EVAL_GATE))
from dm_test import diebold_mariano  # noqa: E402

# minimum graded n before any number is reported / a close-beat is even considered
_MIN_REPORT = 50
_MIN_BEAT = 200


def brier(p: np.ndarray, y: np.ndarray) -> float:
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error with 10 equal-WIDTH bins (stated; diagnostic only)."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.digitize(p, edges[1:-1])
    e = 0.0
    n = len(p)
    for b in range(n_bins):
        m = idx == b
        if m.any():
            e += (m.sum() / n) * abs(y[m].mean() - p[m].mean())
    return float(e)


def murphy(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> Dict[str, float]:
    """Brier = Reliability - Resolution + Uncertainty (10 equal-width bins)."""
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    n = len(p)
    ybar = float(y.mean()) if n else 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.digitize(p, edges[1:-1])
    reliability = resolution = 0.0
    for b in range(n_bins):
        m = idx == b
        nk = int(m.sum())
        if nk:
            pk = float(p[m].mean())
            ok = float(y[m].mean())
            reliability += nk * (pk - ok) ** 2
            resolution += nk * (ok - ybar) ** 2
    reliability = reliability / n if n else 0.0
    resolution = resolution / n if n else 0.0
    uncertainty = ybar * (1.0 - ybar)
    return {"reliability": float(reliability), "resolution": float(resolution),
            "uncertainty": float(uncertainty)}


def dm_vs_close(p_model: np.ndarray, p_close: np.ndarray, y: np.ndarray,
                cluster_ids) -> dict:
    """Clustered DM on per-row Brier loss. d = loss_close - loss_model (>0 => model better)."""
    p_model = np.asarray(p_model, float)
    p_close = np.asarray(p_close, float)
    y = np.asarray(y, float)
    loss_model = (p_model - y) ** 2
    loss_close = (p_close - y) ** 2
    res = diebold_mariano(loss_close - loss_model, list(cluster_ids))
    return {"dm_stat": res.dm_stat, "p_value": res.p_value, "mean_diff": res.mean_diff,
            "ci95": list(res.ci95), "n": res.n, "n_clusters": res.n_clusters}


def _parse_ts(s):
    try:
        return datetime.fromisoformat(str(s))
    except Exception:
        return None


def compute_calibration(df: pd.DataFrame, sport: str, market: str,
                        window_days: Optional[int] = None,
                        now_iso: Optional[str] = None) -> dict:
    """Brier/ECE/Murphy (+ DM vs close when powered) for one (sport, market) slice.

    Returns edge_claimed:False always. A DM p>=0.05 OR n<_MIN_BEAT => honest REJECT
    flagged in `verdict`, never a buried "beat". Pure: reads a DataFrame, no I/O.
    """
    out = {"sport": sport, "market": market, "n": 0, "edge_claimed": False,
           "verdict": "insufficient_data"}
    if df is None or df.empty:
        return out
    sub = df[(df["sport"] == sport) & (df["market"] == market) & df["outcome"].notna()].copy()
    if window_days is not None and len(sub):
        now = _parse_ts(now_iso) if now_iso else datetime.utcnow()
        cutoff = now - timedelta(days=window_days)
        sub = sub[sub["pred_ts"].map(lambda s: (_parse_ts(s) or now) >= cutoff)]
    n = len(sub)
    out["n"] = int(n)
    if n < _MIN_REPORT:
        return out
    p = sub["calibrated_prob"].to_numpy(float)
    y = sub["outcome"].to_numpy(float)
    out.update({"brier": brier(p, y), "ece": ece(p, y), **murphy(p, y),
                "verdict": "reported"})
    mkt = sub[sub["devig_close_prob"].notna()]
    if len(mkt) >= _MIN_REPORT:
        out["market_brier"] = brier(mkt["devig_close_prob"].to_numpy(float),
                                    mkt["outcome"].to_numpy(float))
        cids = mkt["game_id"].fillna(mkt.index.to_series().astype(str))
        dm = dm_vs_close(mkt["calibrated_prob"].to_numpy(float),
                         mkt["devig_close_prob"].to_numpy(float),
                         mkt["outcome"].to_numpy(float), cids)
        out["vs_close"] = dm
        beats = (len(mkt) >= _MIN_BEAT and dm["p_value"] < 0.05
                 and out["brier"] < out["market_brier"])
        # honest framing: "beat" needs power AND significance AND lower Brier; else REJECT
        out["verdict"] = "matches_close" if not beats else "beats_close_oos_pending"
    return out
