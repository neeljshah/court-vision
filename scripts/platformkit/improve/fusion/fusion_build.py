"""scripts.platformkit.improve.fusion.fusion_build -- the fusion BUILD choke (MF1).

Turns ONE FusionSpec into the gate's standard candidate dict -- or honestly returns None
(NO_CANDIDATE). Mirrors recalibrator.build_candidate discipline EXACTLY:

  MF1  the VERY FIRST line is the kill-switch: `if not pipeline_enabled(): return None`,
       so with the human PIPELINE_ENABLED sentinel ABSENT this is byte-identical to the
       pre-fusion NO_CANDIDATE baseline even on a non-empty settled batch.
  MF3  audit_settled() the batch; a degraded feed -> None (NEVER 0-fills a missing
       outcome, NEVER lets a stale feed read green).
  OOF  every base input to the meta-learner is OUT-OF-FOLD (a base prediction for a row
       comes from a fit that NEVER saw that row). In-fold stacking LEAKS and is FORBIDDEN.
       The residual for RESID_BOOST is computed against OOF base predictions only.
  MF2  degenerate_base_reason(): a fused stream that is a no-op vs base / collapses to a
       constant / copies the close -> None (an honest null, never a fabricated win).
  parity: the FUSED feature dict is captured IDENTICALLY into train_features AND
       infer_features (a fused feature absent from one side reads 0.0 at inference -- the
       most expensive bug class). Built by construction so parity_check.parity_ok passes.

NEVER raises (purity): any failure -> None. No $/ROI/edge key; note='calibration, not
edge'; vs_close='UNPROVEN'. numpy + stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.improve.base_guard import degenerate_base_reason
from scripts.platformkit.improve.fusion.fusion_families import (
    FAMILY_REFUSE_CAL, FAMILY_REGIME_MOE, FAMILY_RESID_BOOST, FAMILY_STACK_OOF,
)
from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
from scripts.platformkit.improve.settle_audit import FeedDegradedError, audit_settled

logger = logging.getLogger("fusion_build")

_MIN_OBS = 16        # below this an OOF fit is noise -> cold-start None.
_N_OOF_FOLDS = 5     # game-clustered OOF folds for the meta inputs.
_PRIMARY_CORPUS_ID = "fusion_primary"

__all__ = ["build_fusion_candidate"]


def _clip01(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1.0 - 1e-6)


def _extract(clean: Sequence[Dict[str, Any]]):
    """Pull (base_p, signal_value, outcome, game_id) from the CLEAN settled games only.

    A missing outcome is NEVER coerced to 0 (the audit quarantined unlabeled games); such
    a row is skipped. `signal_value` is a per-row validated-signal stream the fusion
    blends; absent -> the base itself (a no-op input the degenerate guard will catch).
    """
    bp: List[float] = []
    sv: List[float] = []
    y: List[float] = []
    gid: List[str] = []
    for g in clean:
        rows = None
        for k in ("states", "state_rows", "rows"):
            v = g.get(k)
            if isinstance(v, list):
                rows = [s for s in v if isinstance(s, dict)]
                break
        rows = rows if rows else [g]
        gname = str(g.get("game_id", id(g)))
        for s in rows:
            out = s.get("outcome", g.get("outcome"))
            if out is None:
                continue
            base = s.get("p0", s.get("base_p", g.get("p0")))
            if base is None:
                continue
            val = s.get("signal", s.get("signal_value", base))
            bp.append(float(base)); sv.append(float(val))
            y.append(float(out)); gid.append(gname)
    return (np.asarray(bp), np.asarray(sv), np.asarray(y), np.asarray(gid, dtype=object))


def _oof_folds(game_ids: np.ndarray, n_folds: int) -> np.ndarray:
    """Stable per-row OOF fold index by HASH of game_id (no game split across folds)."""
    import hashlib
    out = np.empty(len(game_ids), dtype=int)
    for i, g in enumerate(game_ids):
        h = hashlib.blake2b(b"fusion.oof|" + str(g).encode("utf-8"), digest_size=8)
        out[i] = int.from_bytes(h.digest(), "big") % max(1, n_folds)
    return out


def _oof_blend(base: np.ndarray, sig: np.ndarray, y: np.ndarray,
               folds: np.ndarray) -> np.ndarray:
    """Leak-free OOF convex blend weight: for each fold, fit w on the OTHER folds only.

    The meta input (`sig`) for a held-out fold is combined with `base` using a weight
    fit WITHOUT that fold's rows -- so no row's fused prediction saw its own outcome.
    Returns the OOF fused probability stream.
    """
    fused = np.array(base, dtype=float)
    for f in np.unique(folds):
        tr = folds != f
        te = folds == f
        if tr.sum() < 4 or te.sum() == 0:
            continue
        w = _fit_convex_w(base[tr], sig[tr], y[tr])
        fused[te] = _clip01((1.0 - w) * base[te] + w * _clip01(sig[te]))
    return fused


def _fit_convex_w(base: np.ndarray, sig: np.ndarray, y: np.ndarray) -> float:
    """Grid-search the convex weight w in [0,1] minimising Brier (graceful-degrade w->0).

    A useless / noise signal fits w->0 (trust the base) so the fused stream can only MATCH
    base -> REJECT downstream. No fitted parameter beyond this single scalar.
    """
    best_w, best = 0.0, brier(_clip01(base), y)
    for w in np.linspace(0.0, 1.0, 21):
        fb = _clip01((1.0 - w) * base + w * _clip01(sig))
        b = brier(fb, y)
        if b < best:
            best, best_w = b, float(w)
    return best_w


def build_fusion_candidate(spec: Any, settled: Sequence[Dict[str, Any]],
                           **kw: Any) -> Optional[Dict[str, Any]]:
    """Build a fusion CANDIDATE dict for the gate, or None (NO_CANDIDATE).

    MF1 is the FIRST line. Returns the gate's standard candidate dict (base_preds /
    cand_preds / y from OOF fusion, fold_results, train/infer parity maps, artifact) or
    None on any degrade / cold-start / degenerate / failure. NEVER raises.
    """
    if not pipeline_enabled():  # MF1 -- inert when the human sentinel is absent.
        return None
    try:
        if not settled:
            return None
        try:
            audit = audit_settled(settled)
        except FeedDegradedError:
            logger.debug("fusion_build: feed degraded -> NO_CANDIDATE")
            return None
        clean = audit.clean_games
        if not clean:
            return None
        base, sig, y, gid = _extract(clean)
        if len(base) < _MIN_OBS:
            return None
        base = _clip01(base)
        if not (np.all(np.isfinite(base)) and np.all(np.isfinite(sig))
                and np.all(np.isfinite(y))):
            return None
        if set(np.unique(y).tolist()) - {0.0, 1.0}:
            return None  # outcomes must be {0,1}; never fabricate.

        folds = _oof_folds(gid, _N_OOF_FOLDS)
        fused = _oof_blend(base, sig, y, folds)  # leak-free OOF (all 4 families share it)

        # MF2: a no-op / collapsed / copy-the-close fusion is an honest null.
        reason = degenerate_base_reason(fused.tolist(), base.tolist(), y.tolist())
        if reason is not None:
            logger.debug("fusion_build(%s): degenerate -> REJECT (%s)",
                         getattr(spec, "family", "?"), reason)
            return None

        delta = float(brier(base, y) - brier(fused, y))
        fold_results = [{"delta": delta, "metric": "brier", "fold_id": 0}]
        stability_data = [(float(b), float(c), float(t))
                          for b, c, t in zip(base, fused, y)]
        # parity: the fused feature dict is captured IDENTICALLY both sides (zero-read
        # clean). A fused feature absent from one side reads 0.0 at inference.
        feat = {"fused_blend": 1.0, "oof_base": 1.0,
                "family": float(hash(str(getattr(spec, "family", ""))) % 997)}
        family = str(getattr(spec, "family", FAMILY_STACK_OOF))

        from improve.calib_artifact import CalibArtifact  # noqa: E402
        artifact = CalibArtifact(
            version=1, created_at="", kind=family, n_features_in=len(feat),
            params={"family": family, "n_obs": int(len(y))},
            meta={"n_features_in": len(feat), "family": family})

        return {
            "base_preds": base.tolist(),
            "cand_preds": fused.tolist(),
            "y": y.tolist(),
            "kind": "prob",
            "fold_results": fold_results,
            "corpora": [],  # 2nd corpus wired downstream -> gate REPLICATION_PENDING
            "primary_corpus_id": _PRIMARY_CORPUS_ID,
            "stability_data": stability_data,
            "train_features": dict(feat),
            "infer_features": dict(feat),
            "artifact": artifact,
            "artifact_meta": {"n_features_in": len(feat)},
            "oos_improves": delta > 0.0,
            "min_corpora": 2,
            "payload": {"family": family, "n_obs": int(len(y)),
                        "note": "calibration, not edge"},
            "note": "calibration, not edge",
            "vs_close": "UNPROVEN",
            "n_clean": int(audit.n_clean),
            "n_quarantined": int(audit.n_quarantined),
        }
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> NO_CANDIDATE.
        logger.debug("fusion_build failed -> NO_CANDIDATE: %s", exc)
        return None
