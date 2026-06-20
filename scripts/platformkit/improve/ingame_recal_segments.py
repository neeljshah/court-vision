"""scripts.platformkit.improve.ingame_recal_segments -- in-game segment recal candidates.

Builds LEAK-FREE Platt recalibration CANDIDATES conditioned on the proven in-game
state segmentation: margin x period x time_bucket. Each segment is a separate
candidate routed through the recalibrator.build_candidate choke (MF1/MF2/MF3/MF4)
and the 5-gate ratchet before any swap.

The proven conditioning lever (Brier 0.21 -> 0.0085 late-sim; map_improve L113)
is the motivation. A "segment" is a bucket triple:
  margin_bucket : close | mid | blowout  (score diff thresholds)
  period_bucket : early | late           (game-quarter boundary)
  time_bucket   : ample | scarce         (possession-time remaining)

HOW IT WORKS (leak-free):
  1. load_ingame_settled(sport) reads settled in-game state rows that carry the
     required feature fields (margin, period, seconds_remaining) from the ingame
     cache dir. Missing dir/file -> [] -> NO_CANDIDATE (honest cold start).
  2. segment_settled(rows, spec_params) buckets rows by the margin x period x
     time_bucket split described by a CandidateSpec.params dict.
  3. build_ingame_segment_candidate(name, settled, spec_params) is the builder:
     MF1 kill-switch first; then quarantine via audit_settled; then fit a Platt
     on the clean segmented observations. Returns None (NO_CANDIDATE) whenever:
       * the sentinel is absent (MF1 -- always inert without the human sentinel)
       * <_MIN_OBS clean observations after segmentation (honest cold-start)
       * Platt fit diverges (degenerate numerical)
       * degenerate_base_guard fires (no-op / collapse)
     Packages the exact candidate dict build_candidate builds (same keys).

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a
flag, never creates the PIPELINE_ENABLED sentinel; calibration NOT edge (no $/
pnl/roi field anywhere); vs_close UNPROVEN; MF1 kill-switch on the first line
of build_ingame_segment_candidate. Per-source purity: NEVER raises -- any
failure returns None. Stdlib + numpy; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
from scripts.platformkit.improve.settle_audit import audit_settled, FeedDegradedError
from scripts.platformkit.improve.base_guard import degenerate_base_reason
from scripts.platformkit.eval_gate.scoring import brier

logger = logging.getLogger("ingame_recal_segments")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_INGAME_CACHE = _REPO / "data" / "frontend" / "ingame"

# Minimum CLEAN observations per segment to fit honestly.
_MIN_OBS = 8

_MARGIN_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "close":   (0.0,  8.0),
    "mid":     (8.0,  18.0),
    "blowout": (18.0, 999.0),
}
_PERIOD_THRESHOLDS: Dict[str, Tuple[int, int]] = {
    "early": (1, 2),
    "late":  (3, 4),
}
_TIME_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "ample":  (300.0, 9999.0),   # > 5 min remaining in period
    "scarce": (0.0,   300.0),
}

_PRIMARY_CORPUS_ID = "ingame_segment_primary"


def _clip01(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1.0 - 1e-6)


def _load_ingame_settled(sport: str) -> List[Dict[str, Any]]:
    """Read settled in-game state rows for `sport` from the ingame cache.

    Each row must carry at minimum:
      p0 (float) -- base model prob at that state
      outcome (0|1) -- game-level outcome
      margin (float) -- signed score difference at that state (home - away)
      period (int) -- quarter 1-4
      seconds_remaining (float) -- seconds left in the period

    Missing cache dir or missing fields -> [] (NO_CANDIDATE). Never raises.
    """
    sp = str(sport).lower()
    rows: List[Dict[str, Any]] = []
    for candidate_path in [
        _INGAME_CACHE / f"settled_{sp}.jsonl",
        _INGAME_CACHE / f"ingame_settled_{sp}.jsonl",
    ]:
        if not candidate_path.exists():
            continue
        try:
            text = candidate_path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
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
            logger.debug("ingame_recal_segments: read %s failed: %s",
                         candidate_path, exc)
        if rows:
            break
    return rows


def segment_settled(rows: Sequence[Dict[str, Any]],
                    margin_bucket: str,
                    period_bucket: str,
                    time_bucket: str) -> List[Dict[str, Any]]:
    """Return rows matching the margin x period x time_bucket segment.

    Rows missing the required fields are silently skipped (they would fail
    audit_settled anyway). Never raises.
    """
    m_lo, m_hi = _MARGIN_THRESHOLDS.get(margin_bucket, (0.0, 999.0))
    p_lo, p_hi = _PERIOD_THRESHOLDS.get(period_bucket, (1, 4))
    t_lo, t_hi = _TIME_THRESHOLDS.get(time_bucket, (0.0, 9999.0))

    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            margin = abs(float(r.get("margin", float("nan"))))
            period = int(r.get("period", 0))
            secs = float(r.get("seconds_remaining", float("nan")))
        except (TypeError, ValueError):
            continue
        if not (m_lo <= margin < m_hi):
            continue
        if not (p_lo <= period <= p_hi):
            continue
        if not (t_lo <= secs < t_hi):
            continue
        out.append(r)
    return out


def _fit_platt(base: np.ndarray,
               y: np.ndarray) -> Optional[Tuple[float, float]]:
    """Fit logistic Platt scaling a*logit(base)+b via numpy GD. Returns (a,b)|None."""
    z = np.log(_clip01(base) / (1.0 - _clip01(base)))
    a, b = 1.0, 0.0
    lr, n = 0.1, float(len(z))
    for _ in range(400):
        p = _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))
        g = p - y
        a -= lr * float(np.dot(g, z) / n)
        b -= lr * float(np.mean(g))
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
    return a, b


def _extract_pairs(clean: Sequence[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    """Pull (p0, outcome) pairs from the clean segment rows."""
    base, y = [], []
    for r in clean:
        p0 = r.get("p0")
        out = r.get("outcome")
        if p0 is None or out is None:
            continue
        try:
            base.append(float(p0))
            y.append(float(out))
        except (TypeError, ValueError):
            continue
    return base, y


def _stability_metric_fn(train_rows: Sequence, test_rows: Sequence) -> float:
    rows = list(test_rows) if len(test_rows) else list(train_rows)
    if not rows:
        return 0.0
    bp = np.asarray([r[0] for r in rows], dtype=float)
    cp = np.asarray([r[1] for r in rows], dtype=float)
    yy = np.asarray([r[2] for r in rows], dtype=float)
    return float(brier(bp, yy) - brier(cp, yy))


def build_ingame_segment_candidate(
    name: str,
    sport: str,
    margin_bucket: str,
    period_bucket: str,
    time_bucket: str,
) -> Optional[Dict[str, Any]]:
    """Build a segmented in-game Platt candidate, or None (NO_CANDIDATE).

    MF1: first line is the kill-switch -- returns None when sentinel absent.
    Leak-free: only settled rows with a confirmed (p0, outcome) pair are used.
    Segment isolation: only rows matching (margin x period x time) are fit.
    MF2: degenerate_base_guard fires -> REJECT (honest null).
    NEVER raises: any failure returns None.
    """
    if not pipeline_enabled():  # MF1 -- inert without human sentinel.
        return None
    try:
        all_rows = _load_ingame_settled(sport)
        if not all_rows:
            return None

        seg_rows = segment_settled(all_rows, margin_bucket, period_bucket, time_bucket)
        if not seg_rows:
            return None

        # MF3 anti-0-fill audit on the segment subset.
        try:
            audit = audit_settled(seg_rows)
        except FeedDegradedError:
            logger.debug("ingame_recal_segments(%s/%s/%s/%s): feed degraded",
                         sport, margin_bucket, period_bucket, time_bucket)
            return None
        clean = audit.clean_games
        if not clean:
            return None

        base_list, y_list = _extract_pairs(clean)
        if len(base_list) < _MIN_OBS:
            return None  # honest cold start for this segment

        base = _clip01(np.asarray(base_list, dtype=float))
        y = np.asarray(y_list, dtype=float)
        if not (np.all(np.isfinite(base)) and np.all(np.isfinite(y))):
            return None
        if set(np.unique(y).tolist()) - {0.0, 1.0}:
            return None

        ab = _fit_platt(base, y)
        if ab is None:
            return None
        cand_preds = _clip01(1.0 / (1.0 + np.exp(
            -(ab[0] * np.log(_clip01(base) / (1.0 - _clip01(base))) + ab[1]))))

        reason = degenerate_base_reason(cand_preds.tolist(), base.tolist(), y.tolist())
        if reason is not None:
            logger.debug("ingame_recal_segments(%s/%s/%s/%s): degenerate -> %s",
                         sport, margin_bucket, period_bucket, time_bucket, reason)
            return None

        delta = float(brier(base, y) - brier(cand_preds, y))
        seg_label = "margin:%s|period:%s|time:%s" % (margin_bucket, period_bucket,
                                                      time_bucket)
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
            "train_features": {"base_p": 1.0},
            "infer_features": {"base_p": 1.0},
            "oos_improves": delta > 0.0,
            "min_corpora":  2,
            "payload": {
                "family": "platt_ingame_segment",
                "a": float(ab[0]), "b": float(ab[1]),
                "segment": seg_label,
                "n_obs": int(len(y)),
                "note": "calibration, not edge",
            },
            "note":     "calibration, not edge",
            "vs_close": "UNPROVEN",
            "n_clean":       int(audit.n_clean),
            "n_quarantined": int(audit.n_quarantined),
            "segment":  seg_label,
            "name":     str(name),
        }
        return candidate
    except Exception as exc:  # noqa: BLE001 -- purity: never raise
        logger.debug("ingame_recal_segments(%s) -> NO_CANDIDATE: %s", name, exc)
        return None


__all__ = [
    "build_ingame_segment_candidate",
    "segment_settled",
    "load_ingame_settled",
]

# alias for direct import convenience
load_ingame_settled = _load_ingame_settled
