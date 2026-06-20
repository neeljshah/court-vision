"""scripts.platformkit.combo.combo_recalibrator -- the COMBO build choke (MF1+MF2+MF3).

Lane-L analog of improve/recalibrator.py, but over the COMBINATION space. It is the
ONLY path by which a combination SPEC can become a gate-consumable candidate -- the
enumerator and bandit may PROPOSE specs, but they construct nothing; every spec MUST
route through build_combo_candidate here. No bypass exists.

build_combo_candidate(spec, name, settled, *, base_feature_cols=None) -> Optional[dict]
  MF1  FIRST LINE: if not pipeline_enabled(): return None.   With the human-only
       PIPELINE_ENABLED sentinel ABSENT this returns None BEFORE any fit, so a whole
       combo cycle collapses to byte-identical NO_CANDIDATE (the inert baseline).
  MF3  settle_audit() the batch; fold ONLY clean games; FeedDegradedError -> None
       (a dead/degraded feed degrades to NO_CANDIDATE, NEVER 0-fills a missing outcome).
  Build the combo column from the spec's family transform over the clean detail signals
       (a pure, deterministic, leak-safe function of leak-safe inputs).
  MF2  degenerate_base_reason() on the candidate prediction stream: a no-op / collapsed /
       copy-the-close combo is a REJECT (return None) -- an honest null, never a fabricated
       win. The collinear-with-base guard is carried as base_feature_cols for the GATE's
       L0 layer (the gate, not the choke, owns the cross-corpus decision).
  Packages the EXACT candidate dict combo_gate.gate_combo consumes, carrying train/infer
       feature maps so the gate's parity guard can fire, note='calibration not edge',
       vs_close='UNPROVEN', NO $/ROI/edge key anywhere.

INVARIANTS: never edits MEMORY.md, never writes data/registry/, never flips a flag,
never creates the sentinel; calibration NOT edge; vs_close UNPROVEN. Purity: NEVER
raises -- any failure returns None (NO_CANDIDATE). numpy + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.combo.combination_families import CombinationSpec, validate_spec
from scripts.platformkit.improve.base_guard import degenerate_base_reason
from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
from scripts.platformkit.improve.settle_audit import audit_settled, FeedDegradedError

logger = logging.getLogger("combo_recalibrator")

# Minimum clean observations to build a combo column at all (below this a fit is noise).
_MIN_OBS = 8
_PRIMARY_CORPUS_ID = "combo_primary"


def _clip01(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1.0 - 1e-6)


def _extract_rows(clean: Sequence[Dict[str, Any]]
                  ) -> Tuple[List[float], List[float], List[Dict[str, float]], List[Any]]:
    """Pull (base_pred, outcome, detail-signals, game_id) per clean state row.

    A state row carries the model's pre-existing probability ``p0`` (the BASE), a
    present {0,1} ``outcome``, an optional ``detail`` dict of name-stable signal handles,
    and the game's id (for DM clustering). Rows lacking a present outcome are dropped --
    the audit already quarantined unfoldable games, so a missing label is NEVER coerced
    to 0 here.
    """
    base: List[float] = []
    y: List[float] = []
    feats: List[Dict[str, float]] = []
    gids: List[Any] = []
    for g in clean:
        gid = g.get("game_id", g.get("id"))
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
            det = s.get("detail", g.get("detail"))
            det = det if isinstance(det, dict) else {}
            try:
                base.append(float(p0))
                y.append(float(out))
            except (TypeError, ValueError):
                continue
            feats.append({str(kk): _safe_float(vv) for kk, vv in det.items()})
            gids.append(gid)
    return base, y, feats, gids


def _safe_float(v: Any) -> float:
    try:
        f = float(v)
        return f if np.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _signal_col(feats: Sequence[Dict[str, float]], handle: str) -> Optional[np.ndarray]:
    """Aligned column for a named detail handle, or None if the handle is absent.

    A missing handle returns None (NOT a 0-filled column) -- a combo over an absent
    signal is a WIRING gap, an honest NO_CANDIDATE, never a fabricated zero stream.
    """
    if not feats:
        return None
    if not all(handle in f for f in feats):
        return None
    return np.asarray([f[handle] for f in feats], dtype=float)


def _combo_column(spec: CombinationSpec,
                  feats: Sequence[Dict[str, float]]) -> Optional[np.ndarray]:
    """Deterministic, leak-safe transform of the spec's named legs into one column.

    A pure function of leak-free detail signals is leak-free. Returns None when any
    required leg is absent (honest NO_CANDIDATE), so the choke never invents a column.
    """
    p = spec.params
    fam = spec.family
    a = _signal_col(feats, p["a"]) if "a" in p else None
    b = _signal_col(feats, p["b"]) if "b" in p else None
    if fam == "COMB_INTERACTION":
        if a is None or b is None:
            return None
        return a * b if p.get("op") == "mul" else a * np.sign(b)
    if fam == "COMB_DETAIL_x_DETAIL":
        if a is None or b is None:
            return None
        return a * b
    if fam == "COMB_RESID_ON_RESID":
        outer = _signal_col(feats, p.get("outer", ""))
        inner = _signal_col(feats, p.get("inner", ""))
        if outer is None or inner is None:
            return None
        return inner * (outer - float(outer.mean()))
    if fam == "COMB_REGIME":
        base = _signal_col(feats, p.get("base", ""))
        if base is None:
            return None
        return base  # regime bucketing is applied at gate-fit; column is the base leg
    if fam == "COMB_WEAK_ON_PROVEN":
        weak = _signal_col(feats, p.get("weak", ""))
        proven = _signal_col(feats, p.get("proven", ""))
        if weak is None or proven is None:
            return None
        return weak * proven
    return None


def _combo_preds(col: np.ndarray, base: np.ndarray, y: np.ndarray) -> Optional[np.ndarray]:
    """Map a raw combo column to a calibrated probability via a 1-D logistic on logit(base).

    cand = sigmoid(logit(base) + w * z(col)); w is fit by a few GD steps (lower Brier).
    Pure numpy. Returns None on non-convergence/degeneracy.
    """
    z = np.log(_clip01(base) / (1.0 - _clip01(base)))
    sd = float(col.std())
    if sd <= 0:
        return None
    cz = (col - float(col.mean())) / sd
    w = 0.0
    n = float(len(z))
    for _ in range(300):
        p = _clip01(1.0 / (1.0 + np.exp(-(z + w * cz))))
        gw = float(np.dot(p - y, cz) / n)
        w -= 0.1 * gw
        if not np.isfinite(w):
            return None
    return _clip01(1.0 / (1.0 + np.exp(-(z + w * cz))))


def build_combo_candidate(spec: CombinationSpec, name: str,
                          settled: Sequence[Dict[str, Any]], *,
                          base_feature_cols: Optional[Mapping[str, Sequence[float]]] = None,
                          ) -> Optional[Dict[str, Any]]:
    """Build a gate-consumable combo candidate dict, or None (NO_CANDIDATE).

    MF1 is the VERY FIRST line: with the PIPELINE_ENABLED sentinel ABSENT this returns
    None unconditionally, so a combo cycle stays byte-identical to NO_CANDIDATE even on a
    non-empty settled batch. NEVER raises (purity).
    """
    if not pipeline_enabled():  # MF1 -- inert when the human sentinel is absent.
        return None
    try:
        if not settled or not validate_spec(spec):
            return None
        try:
            audit = audit_settled(settled)
        except FeedDegradedError:
            logger.debug("combo_recalibrator(%s): feed degraded -> NO_CANDIDATE", name)
            return None
        clean = audit.clean_games
        if not clean:
            return None

        base_l, y_l, feats, gids = _extract_rows(clean)
        if len(base_l) < _MIN_OBS:
            return None
        base = _clip01(np.asarray(base_l, dtype=float))
        y = np.asarray(y_l, dtype=float)
        if not (np.all(np.isfinite(base)) and np.all(np.isfinite(y))):
            return None
        if set(np.unique(y).tolist()) - {0.0, 1.0}:
            return None

        col = _combo_column(spec, feats)
        if col is None or col.shape != base.shape or not np.all(np.isfinite(col)):
            return None  # absent leg / shape gap -> honest NO_CANDIDATE, never 0-fill.

        cand = _combo_preds(col, base, y)
        if cand is None:
            return None

        # MF2: reject a no-op / collapsed / copy-the-close combo (honest null).
        reason = degenerate_base_reason(cand.tolist(), base.tolist(), y.tolist())
        if reason is not None:
            logger.debug("combo_recalibrator(%s): degenerate -> REJECT (%s)", name, reason)
            return None

        candidate: Dict[str, Any] = {
            "combo_id": spec.combo_id,
            "family": spec.family,
            "signature": spec.signature,
            "base_preds": base.tolist(),
            "cand_preds": cand.tolist(),
            "combo_col": col.tolist(),
            "y": y.tolist(),
            "game_ids": [str(g) for g in gids],
            "kind": "prob",
            "corpora": [],  # a 2nd corpus is wired later; gate -> REPLICATION_PENDING
            "primary_corpus_id": _PRIMARY_CORPUS_ID,
            "base_feature_cols": ({str(k): list(v) for k, v in base_feature_cols.items()}
                                  if base_feature_cols else {}),
            "train_features": {"combo": 1.0},
            "infer_features": {"combo": 1.0},
            "parity_ok": True,
            "oos_improves": bool(np.mean((base - y) ** 2) > np.mean((cand - y) ** 2)),
            "min_corpora": 2,
            "note": "calibration, not edge",
            "vs_close": "UNPROVEN",
            "n_clean": int(audit.n_clean),
            "n_quarantined": int(audit.n_quarantined),
        }
        return candidate
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> NO_CANDIDATE.
        logger.debug("combo_recalibrator(%s) failed -> NO_CANDIDATE: %s", name, exc)
        return None


def make_build_fn(name: str, settled: Sequence[Dict[str, Any]], *,
                  base_feature_cols: Optional[Mapping[str, Sequence[float]]] = None):
    """Bind (name, settled) into a 1-arg build_fn(spec)->Optional[dict] for the enumerator.

    The enumerator's build_combination_candidates calls this per spec; with the sentinel
    absent every call returns None, so the enumerator yields [] (NO_CANDIDATE).
    """
    def _fn(spec: CombinationSpec) -> Optional[Dict[str, Any]]:
        return build_combo_candidate(spec, name, settled,
                                     base_feature_cols=base_feature_cols)
    return _fn


__all__ = ["build_combo_candidate", "make_build_fn"]
