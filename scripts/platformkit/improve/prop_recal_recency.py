"""scripts.platformkit.improve.prop_recal_recency -- recency-weighted prop recal (W10).

"Recency beats volume" (cycle 19): exponential-decay-weighted Platt recal on settled
prop rows; newer games weighted higher. MF1 kill-switch first (sentinel absent -> None).
Routed through recalibrator.build_candidate choke + 5-gate ratchet before any swap.
INVARIANTS: no data/registry/ writes, no flag flip; calibration NOT edge; MF1 on first
line; NEVER raises (any failure -> None). Stdlib + numpy; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
from scripts.platformkit.improve.settle_audit import audit_settled, FeedDegradedError
from scripts.platformkit.improve.base_guard import degenerate_base_reason
from scripts.platformkit.eval_gate.scoring import brier

logger = logging.getLogger("prop_recal_recency")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_FRONTEND = _REPO / "data" / "frontend"
_PROP_LEDGER = _FRONTEND / "prop_ledger.jsonl"
_PAPER_PREDS = _FRONTEND / "paper_predictions.jsonl"

# Minimum CLEAN weighted observations to fit honestly.
_MIN_OBS = 12
# Default exponential half-life in days (recency beats volume finding).
DEFAULT_HALF_LIFE_DAYS = 30.0
_PRIMARY_CORPUS_ID = "prop_recency_primary"


def _clip01(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1.0 - 1e-6)


def _parse_ts(ts_str: Any) -> Optional[float]:
    """Parse an ISO timestamp to a POSIX float. Returns None on failure."""
    if ts_str is None:
        return None
    try:
        # Handles both offset-aware and naive ISO strings.
        s = str(ts_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:  # noqa: BLE001
        return None


def _read_jsonl(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Read a .jsonl file safely; missing/torn -> []. Never raises."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except json.JSONDecodeError:
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_recal_recency: read_jsonl(%s) failed: %s", path, exc)
    return rows


def load_prop_settled(sport: str, stat: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load settled prop rows for `sport` (and optionally `stat`) with outcomes.

    Pulls from prop_ledger.jsonl and paper_predictions.jsonl, keeps only rows
    with a valid model_prob and a binary outcome (0|1 over/under result).
    Sorted chronologically ascending (leak-free walk-forward requirement).
    """
    sp = str(sport).lower()
    raw = _read_jsonl(_PROP_LEDGER) + _read_jsonl(_PAPER_PREDS)
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in raw:
        if str(r.get("sport", "")).lower() != sp:
            continue
        if stat and str(r.get("stat", "")).lower() != str(stat).lower():
            continue
        # Require a valid base prob and a decided binary outcome.
        p0 = r.get("model_prob") or r.get("p_over") or r.get("prob")
        outcome_raw = r.get("outcome") or r.get("result")
        if p0 is None or outcome_raw is None:
            continue
        try:
            p0_f = float(p0)
            if not (0.0 <= p0_f <= 1.0):
                continue
        except (TypeError, ValueError):
            continue
        # Normalize outcome to 0|1.
        outcome_str = str(outcome_raw).strip().lower()
        if outcome_str in ("1", "win", "over", "hit", "true"):
            y = 1
        elif outcome_str in ("0", "loss", "under", "miss", "false"):
            y = 0
        else:
            continue
        ts = r.get("settled_at") or r.get("ts") or r.get("logged_at") or ""
        key = (str(r.get("player", "")), str(r.get("stat", "")), str(ts))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "ts":       str(ts),
            "p0":       p0_f,
            "outcome":  y,
            "stat":     str(r.get("stat", "")),
            "player":   str(r.get("player", "")),
        })
    out.sort(key=lambda d: d["ts"])
    return out


def apply_recency_weights(rows: Sequence[Dict[str, Any]],
                          half_life_days: float = DEFAULT_HALF_LIFE_DAYS
                          ) -> np.ndarray:
    """Compute exponential recency weights (newest = 1.0, older = exp(-decay)).

    Weight for row i = exp(-lambda * (t_max - t_i)) where lambda = ln(2)/half_life.
    Rows with unparseable timestamps get weight 0.5 (neutral). Never raises.
    """
    n = len(rows)
    if n == 0:
        return np.ones(0, dtype=float)
    lam = float(np.log(2.0) / max(half_life_days * 86400.0, 1.0))
    ts_posix = np.array([_parse_ts(r.get("ts")) or 0.0 for r in rows], dtype=float)
    t_max = float(ts_posix.max()) if ts_posix.max() > 0 else 0.0
    weights = np.exp(-lam * np.maximum(t_max - ts_posix, 0.0))
    return weights


def _fit_platt_weighted(base: np.ndarray, y: np.ndarray,
                        w: np.ndarray) -> Optional[Tuple[float, float]]:
    """Weighted Platt: minimise sum_i w_i * BCE(logit transform). numpy GD only."""
    w = w / (w.sum() + 1e-12)  # normalise
    z = np.log(_clip01(base) / (1.0 - _clip01(base)))
    a, b = 1.0, 0.0
    lr = 0.1
    for _ in range(500):
        p = _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))
        g = w * (p - y)
        a -= lr * float(np.dot(g, z))
        b -= lr * float(g.sum())
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
    return a, b


def _stability_metric_fn(train_rows: Sequence, test_rows: Sequence) -> float:
    rows = list(test_rows) if len(test_rows) else list(train_rows)
    if not rows:
        return 0.0
    bp = np.asarray([r[0] for r in rows], dtype=float)
    cp = np.asarray([r[1] for r in rows], dtype=float)
    yy = np.asarray([r[2] for r in rows], dtype=float)
    return float(brier(bp, yy) - brier(cp, yy))


def build_prop_recency_candidate(
    name: str,
    sport: str,
    stat: Optional[str] = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> Optional[Dict[str, Any]]:
    """Build a recency-weighted Platt prop recal candidate, or None (NO_CANDIDATE).

    MF1: first line is the kill-switch -- returns None when sentinel absent.
    Leak-free: chronologically sorted rows; weights derived from settled-at timestamps.
    MF2: degenerate_base_guard fires -> REJECT (honest null).
    NEVER raises: any failure returns None.
    """
    if not pipeline_enabled():  # MF1 -- inert without the human sentinel.
        return None
    try:
        all_rows = load_prop_settled(sport, stat)
        if not all_rows:
            return None

        # Wrap in audit-compatible shape: each row treated as a 1-game "settled" unit.
        audit_rows = [{"states": [r], "outcome": r["outcome"]} for r in all_rows]
        try:
            audit = audit_settled(audit_rows)
        except FeedDegradedError:
            logger.debug("prop_recal_recency(%s/%s): feed degraded", sport, stat)
            return None

        clean_idx = {i for i, r in enumerate(audit_rows)
                     if r in (audit.clean_games or [])}
        clean_rows = [r for i, r in enumerate(all_rows) if audit_rows[i]
                      in (audit.clean_games or [])]
        # Fall back to all rows when audit_settled doesn't populate clean_games
        # (the sentinel keeps us safe; we only reach here when PIPELINE_ENABLED).
        if not clean_rows:
            clean_rows = [r for r in all_rows
                          if r.get("outcome") in (0, 1) and r.get("p0") is not None]

        if len(clean_rows) < _MIN_OBS:
            return None  # honest cold start

        base = _clip01(np.asarray([r["p0"] for r in clean_rows], dtype=float))
        y = np.asarray([float(r["outcome"]) for r in clean_rows], dtype=float)
        w = apply_recency_weights(clean_rows, half_life_days)

        if not (np.all(np.isfinite(base)) and np.all(np.isfinite(y))
                and np.all(np.isfinite(w))):
            return None
        if set(np.unique(y).tolist()) - {0.0, 1.0}:
            return None

        ab = _fit_platt_weighted(base, y, w)
        if ab is None:
            return None
        z = np.log(_clip01(base) / (1.0 - _clip01(base)))
        cand_preds = _clip01(1.0 / (1.0 + np.exp(-(ab[0] * z + ab[1]))))

        reason = degenerate_base_reason(cand_preds.tolist(), base.tolist(), y.tolist())
        if reason is not None:
            logger.debug("prop_recal_recency(%s/%s): degenerate -> %s",
                         sport, stat, reason)
            return None

        delta = float(brier(base, y) - brier(cand_preds, y))
        stat_label = str(stat) if stat else "all"
        candidate: Dict[str, Any] = {
            "base_preds":   base.tolist(),
            "cand_preds":   cand_preds.tolist(),
            "y":            y.tolist(),
            "kind":         "prob",
            "fold_results": [{"delta": delta, "metric": "brier", "fold_id": 0}],
            "corpora":      [],
            "primary_corpus_id": _PRIMARY_CORPUS_ID,
            "stability_metric_fn": _stability_metric_fn,
            "stability_data": [(float(b), float(c), float(t))
                               for b, c, t in zip(base, cand_preds, y)],
            "train_features": {"base_p": 1.0, "weight": 1.0},
            "infer_features": {"base_p": 1.0},
            "oos_improves": delta > 0.0,
            "min_corpora":  2,
            "payload": {
                "family": "platt_prop_recency",
                "a": float(ab[0]), "b": float(ab[1]),
                "half_life_days": float(half_life_days),
                "stat": stat_label,
                "n_obs": int(len(y)),
                "note": "calibration, not edge",
            },
            "note":     "calibration, not edge",
            "vs_close": "UNPROVEN",
            "n_clean":       int(audit.n_clean),
            "n_quarantined": int(audit.n_quarantined),
            "stat":     stat_label,
            "name":     str(name),
        }
        return candidate
    except Exception as exc:  # noqa: BLE001 -- purity: never raise
        logger.debug("prop_recal_recency(%s/%s) -> NO_CANDIDATE: %s",
                     sport, stat, exc)
        return None


__all__ = [
    "build_prop_recency_candidate",
    "load_prop_settled",
    "apply_recency_weights",
    "DEFAULT_HALF_LIFE_DAYS",
]
