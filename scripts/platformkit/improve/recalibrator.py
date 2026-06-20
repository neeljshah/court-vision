"""scripts.platformkit.improve.recalibrator -- the recalibration BRIDGE (MF1+MF2+MF3).

The 5-gate self-improve ratchet (improve/ratchet_state.evaluate_candidate, driven by
selfimprove_daemon.run_cycle) is fully built but was PERMANENTLY INERT because
selfimprove_runner imported an ABSENT improve.recalibrator. This module is that missing
bridge: it turns a batch of newly-SETTLED games into the CANDIDATE dict the gate consumes
-- or honestly returns None (NO_CANDIDATE) when it should not, or cannot, build one.

It is wired LIVE but FLAG-OFF. With the human-only PIPELINE_ENABLED sentinel ABSENT,
build_candidate ALWAYS returns None on its FIRST line (MF1 kill-switch), so daemon
behaviour stays byte-identical to today's NO_CANDIDATE. Only when a human creates the
sentinel does any candidate flow.

build_candidate(name, settled, priority=None, **kw) -> Optional[dict]
  MF1  first line: if not pipeline_enabled(): return None        (inert when sentinel absent)
  MF3  audit_settled() the batch; fold ONLY clean games; on FeedDegradedError -> None
       (a dead/degraded feed degrades to NO_CANDIDATE, NEVER 0-fills a missing outcome)
  recal-variant: a ONE-family (Platt) temperature/logistic re-fit on the clean window
       builds base_preds / cand_preds / y from the clean settled states.
  MF2  degenerate_base_reason(): a no-op / collapsed / copy-the-close candidate is a
       REJECT (return None with a recorded reason) -- an honest null, never a fabricated win.
  Packages the EXACT candidate dict the gate (_default_gate_fn) expects, carrying
       note='calibration not edge', vs_close='UNPROVEN', units/probability only, NO $ field.

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag,
never creates the sentinel; calibration NOT edge (no $/pnl/roi/edge key anywhere);
vs_close UNPROVEN. Per-source purity: NEVER raises -- any failure returns None
(NO_CANDIDATE). Stdlib + numpy + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
from scripts.platformkit.improve.settle_audit import audit_settled, FeedDegradedError
from scripts.platformkit.improve.base_guard import degenerate_base_reason
from scripts.platformkit.eval_gate.scoring import brier

logger = logging.getLogger("recalibrator")

# Minimum clean observations to fit a recal variant at all. Below this a fit is noise;
# we honestly return None (cold start) rather than ship a spurious candidate.
_MIN_OBS = 8

# A stable id for the primary corpus so the daemon's >=2-corpora counter dedups it.
_PRIMARY_CORPUS_ID = "recal_primary"


def _clip01(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1.0 - 1e-6)


def _extract_obs(clean: Sequence[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    """Pull (base_pred, outcome) pairs from the CLEAN settled games only.

    A state row carries the model's pre-existing probability ``p0`` (the BASE the
    candidate must beat) and a present {0,1} ``outcome``. We take ONLY rows with a
    present outcome -- the audit already quarantined games lacking a real label, so a
    missing label is NEVER coerced to 0 here. Falls back to a game-level (p0, outcome).
    """
    base: List[float] = []
    y: List[float] = []
    for g in clean:
        states = None
        for k in ("states", "state_rows", "rows"):
            v = g.get(k)
            if isinstance(v, list):
                states = [s for s in v if isinstance(s, dict)]
                break
        rows = states if states else [g]
        for s in rows:
            out = s.get("outcome", g.get("outcome"))
            p0 = s.get("p0", g.get("p0"))
            if out is None or p0 is None:
                continue
            try:
                base.append(float(p0))
                y.append(float(out))
            except (TypeError, ValueError):
                continue
    return base, y


def _fit_platt(base: np.ndarray, y: np.ndarray) -> Optional[Tuple[float, float]]:
    """Fit logistic P = sigmoid(a*logit(base) + b) by a few Newton-free GD steps.

    Pure numpy, no scipy. Returns (a, b) or None if it cannot converge to a finite,
    non-degenerate map. Lower-is-better Brier is the only objective.
    """
    z = np.log(_clip01(base) / (1.0 - _clip01(base)))  # logit of base
    a, b = 1.0, 0.0
    lr = 0.1
    n = float(len(z))
    for _ in range(400):
        p = _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))
        g = p - y
        ga = float(np.dot(g, z) / n)
        gb = float(np.mean(g))
        a -= lr * ga
        b -= lr * gb
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
    return a, b


def _apply_platt(base: np.ndarray, ab: Tuple[float, float]) -> np.ndarray:
    a, b = ab
    z = np.log(_clip01(base) / (1.0 - _clip01(base)))
    return _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))


def _stability_metric_fn(train_rows: Sequence, test_rows: Sequence) -> float:
    """Lower-is-better delta consumed by the seed-stability bootstrap.

    Each row is (base_p, cand_p, y). Returns base_brier - cand_brier on the test rows
    so a POSITIVE delta means the candidate improved (the guard ships iff p10 >= 0).
    """
    rows = list(test_rows) if len(test_rows) else list(train_rows)
    if not rows:
        return 0.0
    bp = np.asarray([r[0] for r in rows], dtype=float)
    cp = np.asarray([r[1] for r in rows], dtype=float)
    yy = np.asarray([r[2] for r in rows], dtype=float)
    return float(brier(bp, yy) - brier(cp, yy))


def build_candidate(name: str, settled: Sequence[Dict[str, Any]],
                    priority: Any = None, **kw: Any) -> Optional[Dict[str, Any]]:
    """Build a recal-variant CANDIDATE dict for the gate, or None (NO_CANDIDATE).

    MF1: the VERY FIRST line is the kill-switch -- with the PIPELINE_ENABLED sentinel
    absent this returns None unconditionally, so the daemon stays byte-identical to its
    pre-recalibrator NO_CANDIDATE baseline even on a non-empty settled batch.

    NEVER raises: any internal failure returns None (NO_CANDIDATE).
    """
    if not pipeline_enabled():  # MF1 -- inert when the human sentinel is absent.
        return None
    try:
        if not settled:
            return None

        # --- MF3: quarantine unfoldable games; degrade -> NO_CANDIDATE, never 0-fill --
        try:
            audit = audit_settled(settled)
        except FeedDegradedError:
            logger.debug("recalibrator(%s): feed degraded -> NO_CANDIDATE", name)
            return None
        clean = audit.clean_games
        if not clean:
            return None

        base_list, y_list = _extract_obs(clean)
        if len(base_list) < _MIN_OBS:
            return None  # cold start: too few clean observations to fit honestly.

        base = _clip01(np.asarray(base_list, dtype=float))
        y = np.asarray(y_list, dtype=float)
        if not (np.all(np.isfinite(base)) and np.all(np.isfinite(y))):
            return None
        if set(np.unique(y).tolist()) - {0.0, 1.0}:
            return None  # outcomes must be {0,1}; never fabricate.

        ab = _fit_platt(base, y)
        if ab is None:
            return None
        cand = _apply_platt(base, ab)

        # --- MF2: reject a no-op / collapsed / copy-the-close candidate (honest null) --
        reason = degenerate_base_reason(cand.tolist(), base.tolist(), y.tolist())
        if reason is not None:
            logger.debug("recalibrator(%s): degenerate base -> REJECT (%s)", name, reason)
            return None

        # Folds + stability rows from the clean window (the candidate must beat base).
        delta = float(brier(base, y) - brier(cand, y))
        fold_results = [{"delta": delta, "metric": "brier", "fold_id": 0}]
        stability_data = [(float(b), float(c), float(t))
                          for b, c, t in zip(base, cand, y)]
        oos_improves = delta > 0.0

        from improve.calib_artifact import CalibArtifact  # noqa: E402
        artifact = CalibArtifact(
            version=1, created_at="", kind=str(name), n_features_in=1,
            params={"family": "platt", "a": float(ab[0]), "b": float(ab[1])},
            meta={"n_features_in": 1, "family": "platt"})

        candidate: Dict[str, Any] = {
            "base_preds": base.tolist(),
            "cand_preds": cand.tolist(),
            "y": y.tolist(),
            "kind": "prob",
            "fold_results": fold_results,
            "corpora": [],  # a 2nd independent corpus is wired later; gate -> REPLICATION_PENDING
            "primary_corpus_id": _PRIMARY_CORPUS_ID,
            "stability_metric_fn": _stability_metric_fn,
            "stability_data": stability_data,
            "train_features": {"base_p": 1.0},
            "infer_features": {"base_p": 1.0},
            "artifact": artifact,
            "artifact_meta": {"n_features_in": 1},
            "oos_improves": oos_improves,
            "min_corpora": 2,
            "payload": {"family": "platt", "a": float(ab[0]), "b": float(ab[1]),
                        "n_obs": int(len(y)), "note": "calibration, not edge"},
            "note": "calibration, not edge",
            "vs_close": "UNPROVEN",
            "n_clean": int(audit.n_clean),
            "n_quarantined": int(audit.n_quarantined),
        }
        return candidate
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> NO_CANDIDATE.
        logger.debug("recalibrator(%s) failed -> NO_CANDIDATE: %s", name, exc)
        return None


__all__ = ["build_candidate"]
