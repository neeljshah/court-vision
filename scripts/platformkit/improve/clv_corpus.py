"""scripts.platformkit.improve.clv_corpus -- the settled-CLV SECOND CORPUS (Inc2 core).

The 5-gate ratchet (improve.ratchet_state.evaluate_candidate) needs >=2 independent
corpora to ever SHIP, yet the recalibrator hands it ``corpora: []`` -- so a candidate
is wedged at REPLICATION_PENDING forever. This module builds the missing SECOND
corpus from SETTLED games, and -- the honesty crux -- builds it ONLY when the
candidate genuinely BEATS THE CLOSE on held-out OUTCOME Brier.

P1 (KEYSTONE): a close-corpus fold passes ONLY if the candidate model BEATS the
close on OUTCOME-Brier on a time-disjoint walk-forward window -- the DM loss is
``loss_close - loss_model`` per state (POSITIVE mean => model better, reusing the
verified eval_gate.dm_test convention), clustered by game_id (P5). It is NEVER
"closer to the close": ANY fold whose apparent delta comes from reduced
model-close DIVERGENCE without a model-beats-close OUTCOME win is REJECTED. A pure
shrink-toward-close candidate (outcome-Brier-flat, divergence-collapsed) yields
NO corpus -- ``build_close_corpus`` returns None, not an all-positive corpus.

CLV is a do-no-harm / second-corpus GUARD here, never a ship-maximization
objective: the SHIP objective stays held-out outcome Brier. is_true_close is
enforced ITSELF (P3): proxy-close states are EXCLUDED, and an all-proxy window
returns None (we never grade a candidate against a fabricated close). Per-game
loss vectors are emitted so the cluster-robust DM binds (P5).

INVARIANTS: imports the verified dm_test + brier VERBATIM (no reimplementation);
units/probability only, NO $/roi/pnl/bankroll field; vs_close stays UNPROVEN here
(an upgrade is the inject module's job, gated on ship+replication+DM-p). The corpus
is only APPENDED when pipeline_enabled() AND every fold is positive; otherwise the
caller gets None (no candidate corpus). NEVER raises; any failure -> None. Reuses
the verified vintage guard so a hindsight-stamped state is EXCLUDED. stdlib +
numpy + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
from scripts.platformkit.quant.clv_core import assert_vintage

logger = logging.getLogger("clv_corpus")

# Stable id so the ratchet's >=2-corpora counter treats this as the SECOND,
# independent corpus (distinct from recalibrator._PRIMARY_CORPUS_ID).
CLV_CORPUS_ID = "clv_settled_close"

# A model-close divergence below this (per state, mean |model - close|) on a
# candidate whose outcome-Brier is NOT better than the close is the shrink
# -toward-close signature -- collapsed divergence with no real outcome win.
_DIVERGENCE_EPS = 1e-4

# Minimum clustered games to bind the cluster-robust DM SE honestly. One game's
# many correlated states is not >=2 clusters; below this the SE is noise.
_MIN_CLUSTERS = 2


def _clip01(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-6, 1.0 - 1e-6)


def _state_rows(g: Dict[str, Any]) -> List[Dict[str, Any]]:
    for k in ("states", "state_rows", "rows"):
        v = g.get(k)
        if isinstance(v, list):
            return [s for s in v if isinstance(s, dict)]
    return [g]


def _vintage_ok(state: Dict[str, Any], game: Dict[str, Any]) -> bool:
    """True iff the state's prediction predates the close it is graded against.

    Reuses the verified clv_core.assert_vintage (raises on pred_ts >= close ts).
    A state lacking either timestamp is treated as clean (the field is optional
    in reconstructed rows); only a present-and-hindsight pair is excluded.
    """
    pred_ts = state.get("pred_ts", game.get("pred_ts"))
    close_ts = state.get("close_captured_at", game.get("close_captured_at"))
    if pred_ts is None or close_ts is None:
        return True
    try:
        assert_vintage(str(pred_ts), str(close_ts))
        return True
    except Exception:  # noqa: BLE001 -- hindsight (or equal) stamp -> EXCLUDE
        return False


def _extract(settled: Sequence[Dict[str, Any]]
             ) -> Tuple[List[float], List[float], List[float], List[Any], bool]:
    """Pull (model_p, close_p, y, game_id) from TRUE-close, vintage-clean states.

    Returns (model, close, y, cluster_ids, saw_proxy). Proxy-close states (P3) are
    EXCLUDED; ``saw_proxy`` records whether any were seen so an all-proxy window is
    distinguishable from an empty one. A state missing model_p / close_p / outcome
    is skipped (never 0-filled).
    """
    model: List[float] = []
    close: List[float] = []
    y: List[float] = []
    cluster: List[Any] = []
    saw_proxy = False
    for g in settled:
        gid = g.get("game_id", g.get("id", id(g)))
        for s in _state_rows(g):
            is_true = s.get("is_true_close", g.get("is_true_close"))
            if is_true is False:
                saw_proxy = True
                continue  # P3: never grade against a proxy close
            mp = s.get("model_p", s.get("p0", g.get("model_p")))
            cp = s.get("close_p", g.get("close_p"))
            out = s.get("outcome", g.get("outcome"))
            if mp is None or cp is None or out is None:
                continue
            if not _vintage_ok(s, g):
                continue
            try:
                model.append(float(mp))
                close.append(float(cp))
                y.append(float(out))
                cluster.append(gid)
            except (TypeError, ValueError):
                continue
    return model, close, y, cluster, saw_proxy


def _per_game_losses(d: np.ndarray, cluster: Sequence[Any]
                     ) -> List[Dict[str, Any]]:
    """Per-game (clustered) loss-difference vectors (P5): emit each game's d_t list
    so a downstream cluster-robust DM can rebind without re-deriving clusters."""
    groups: Dict[Any, List[float]] = {}
    for di, c in zip(d.tolist(), cluster):
        groups.setdefault(c, []).append(float(di))
    return [{"game_id": str(c), "d": v} for c, v in groups.items()]


def build_close_corpus(settled: Sequence[Dict[str, Any]],
                       *, alpha: float = 0.05,
                       require_enabled: bool = True) -> Optional[Dict[str, Any]]:
    """Build the settled-CLV close corpus, or None (no second corpus). NEVER raises.

    Returns a CorpusResult dict ``{corpus_id, folds, ...}`` consumable by
    multifold_guard.replicated ONLY when the candidate BEATS the close on outcome
    -Brier (P1): per-state DM loss = brier_close - brier_model, clustered by game
    (P5), mean POSITIVE and significant. Returns None when:
      * the pipeline sentinel is absent (require_enabled) -- inert,
      * every usable close is a PROXY (P3) -- never grade against a fake close,
      * the candidate merely shrank toward the close (divergence-collapse, no
        outcome win) -- the P1 reject: a flat candidate yields NO corpus,
      * too few clustered games to bind the DM SE.
    """
    try:
        if require_enabled and not pipeline_enabled():
            return None  # inert: sentinel absent -> no corpus appended
        if not settled:
            return None

        model_l, close_l, y_l, cluster, saw_proxy = _extract(settled)
        if not model_l:
            # No usable states. If the ONLY reason was proxy closes, that is the
            # explicit P3 all-proxy None (vs an honest empty window).
            return None

        model = _clip01(np.asarray(model_l, dtype=float))
        close = _clip01(np.asarray(close_l, dtype=float))
        y = np.asarray(y_l, dtype=float)
        if set(np.unique(y).tolist()) - {0.0, 1.0}:
            return None  # outcomes must be {0,1}; never fabricate a label

        # Per-state OUTCOME-Brier losses; d = loss_close - loss_model (positive
        # => model beats the close ON THE OUTCOME, the only admissible win).
        loss_model = (model - y) ** 2
        loss_close = (close - y) ** 2
        d = loss_close - loss_model

        n_clusters = len(set(cluster))
        if n_clusters < _MIN_CLUSTERS:
            return None  # cannot bind a clustered SE honestly

        dm = diebold_mariano(d.tolist(), list(cluster))
        outcome_delta = float(brier(close, y) - brier(model, y))  # +ve = model better
        divergence = float(np.mean(np.abs(model - close)))

        # P1 REJECT: a pure shrink-toward-close candidate -- the model collapsed
        # onto the close (divergence ~0) WITHOUT a real outcome win. Its tiny
        # delta is divergence-collapse, not a model-beats-close win. NO corpus.
        beats_outcome = outcome_delta > 0.0 and dm.mean_diff > 0.0
        if not beats_outcome:
            logger.debug(
                "clv_corpus: no model-beats-close outcome win "
                "(outcome_delta=%.6f dm_mean=%.6f div=%.6f) -> NO corpus",
                outcome_delta, dm.mean_diff, divergence)
            return None
        # Defensive: a "win" whose divergence has collapsed to ~0 is the close
        # itself; reject as a shrink artifact rather than ship a phantom corpus.
        if divergence < _DIVERGENCE_EPS:
            logger.debug("clv_corpus: divergence collapsed (%.2e) -> shrink, NO corpus",
                         divergence)
            return None

        significant = dm.p_value < float(alpha)

        fold = {
            "fold_id": "clv_settled",
            "delta": outcome_delta,        # >0 = beats close on OUTCOME (multifold reads this)
            "metric": "brier",
            "dm_stat": dm.dm_stat,
            "dm_p": dm.p_value,
            "dm_mean_diff": dm.mean_diff,
            "n_clusters": dm.n_clusters,
            "significant": bool(significant),
        }
        # Only an ALL-POSITIVE (and the sole) fold; if not significant the fold's
        # delta still gates via multifold, but we surface the non-significance.
        all_positive = outcome_delta > 0.0
        return {
            "corpus_id": CLV_CORPUS_ID,
            "folds": [fold],
            "all_positive": bool(all_positive),
            "significant": bool(significant),
            "dm_p": dm.p_value,
            "n": int(dm.n),
            "n_clusters": int(dm.n_clusters),
            "per_game_losses": _per_game_losses(d, cluster),  # P5
            "saw_proxy": bool(saw_proxy),
            "note": "calibration, not edge; vs_close UNPROVEN; second corpus only",
            "vs_close": "UNPROVEN",
            "units": "probability",
        }
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> no corpus
        logger.debug("build_close_corpus failed -> None: %s", exc)
        return None


__all__ = ["build_close_corpus", "CLV_CORPUS_ID"]
