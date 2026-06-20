"""scripts.platformkit.improve.clv_candidate -- the CLV-vs-close candidate gate FAMILY.

A SECOND candidate family for the autonomous loop (alongside
recalibrator.build_candidate) whose objective is BEATING THE TRUE CLOSE on the
held-out OUTCOME -- not shrinking toward it. It proposes a gate-consumable
candidate ONLY when the settled window genuinely beats the close, routed through
clv_corpus.build_close_corpus (which is itself the model-BEATS-close-on-outcome
gate, never a "closer to the close" reward). A pure shrink-toward-close window
yields NOTHING here, by construction, because build_close_corpus returns None for
it.

The keystone deepened (honest expectation): a CLV-objective recalibration holds
vs_close at "UNPROVEN" (the honest match) FAR more often than it flips toward a
replicated beat. THAT honest null is the success -- markets are efficient pregame.

INERT BY CONSTRUCTION:
  * The VERY FIRST guarded check is the human-only PIPELINE_ENABLED sentinel
    (pipeline_flag.pipeline_enabled). Absent -> propose_clv_candidate returns None
    (NO_CANDIDATE), byte-identical to today. The loop NEVER creates the sentinel.
  * build_close_corpus is ALSO sentinel-guarded (defense in depth): even if this
    module's guard were bypassed, the corpus path stays inert with the sentinel
    absent.

HONESTY INVARIANTS:
  * vs_close NEVER advances past "UNPROVEN" here -- a real upgrade is a separate,
    human-gated decision after gate-ship + >=2 corpora + DM p<0.05. This family
    only PROPOSES; it never ships, never stamps, never writes a registry/flag.
  * min_corpora>=2: the proposed candidate carries the same min_corpora discipline
    the ratchet enforces; the close corpus is exactly the legitimate 2nd corpus.
  * CLV is the SECOND-CORPUS / do-no-harm yardstick here, NEVER a maximization
    objective (that is the +18.38% artifact failure mode). The objective routed in
    is model-BEATS-close-on-OUTCOME; a candidate that merely copies the close is
    rejected upstream by build_close_corpus.
  * Reuses build_close_corpus + candidate_families.assert_no_dollar VERBATIM; no
    new CLV / devig / Brier math. UNITS/probability only -- NO $/roi/pnl key.
  * NEVER raises: any internal failure returns None (NO_CANDIDATE).

Build invariants: additive; <=300 LOC; ASCII; reuse, never reimplement.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from scripts.platformkit.improve.candidate_families import (
    NOTE_CALIBRATION,
    VS_CLOSE,
    assert_no_dollar,
    candidate_id as _candidate_id,
)
from scripts.platformkit.improve.clv_corpus import build_close_corpus, CLV_CORPUS_ID
from scripts.platformkit.improve.pipeline_flag import pipeline_enabled

logger = logging.getLogger("clv_candidate")

# This family's stable name (distinct from recalibrator's recal family).
FAMILY_CLV_VS_CLOSE = "clv_vs_close"

# The minimum corpora the proposed candidate demands -- the close corpus is the
# legitimate 2nd corpus; below 2 the ratchet stays at REPLICATION_PENDING.
_MIN_CORPORA = 2

# Significance bar consistent with R9 (small-N CLV variance read as edge). The
# corpus builder applies its own clustered-DM alpha; this is restated for the
# proposal's own significance flag.
_MIN_BEAT_ALPHA = 0.05


def _candidate_dict(sport: str, target: str, corpus: Dict[str, Any]
                    ) -> Dict[str, Any]:
    """Package a gate-consumable CLV-vs-close candidate from a beats-close corpus.

    Mirrors the recalibrator candidate shape the ratchet consumes (fold_results,
    corpora, min_corpora, vs_close, oos_improves, note) but its corpora list is
    seeded with the settled-CLV close corpus (the SECOND, independent corpus).
    vs_close STAYS "UNPROVEN" -- this family proposes, it never upgrades.
    """
    fold = corpus.get("folds", [{}])[0]
    delta = float(fold.get("delta", 0.0))
    signature = "clv_vs_close=beats_true_close_outcome"
    cid = _candidate_id(FAMILY_CLV_VS_CLOSE, str(sport), str(target), signature)
    candidate: Dict[str, Any] = {
        "candidate_id": cid,
        "family": FAMILY_CLV_VS_CLOSE,
        "sport": str(sport),
        "target": str(target),
        "kind": "prob",
        # the primary fold mirrors the close-corpus outcome delta (>0 = beats close)
        "fold_results": [
            {"delta": delta, "metric": "brier", "fold_id": "clv_vs_close"}
        ],
        # the settled-CLV close corpus IS the second independent corpus.
        "corpora": [corpus],
        "primary_corpus_id": CLV_CORPUS_ID,
        "min_corpora": _MIN_CORPORA,
        "oos_improves": delta > 0.0,
        "significant": bool(corpus.get("significant", False)),
        "dm_p": corpus.get("dm_p"),
        "n_clusters": int(corpus.get("n_clusters", 0)),
        "payload": {
            "family": FAMILY_CLV_VS_CLOSE,
            "objective": "beat-the-true-close-on-held-out-outcome",
            "note": NOTE_CALIBRATION,
        },
        "note": NOTE_CALIBRATION,
        # NEVER upgraded here -- a real flip is a separate human-gated decision.
        "vs_close": VS_CLOSE,
        "units": "probability",
        "status": "PROPOSED",
    }
    return candidate


def propose_clv_candidate(name: str,
                          settled: Sequence[Dict[str, Any]],
                          *, sport: str = "nba",
                          target: str = "win_prob",
                          alpha: float = _MIN_BEAT_ALPHA,
                          require_enabled: bool = True
                          ) -> Optional[Dict[str, Any]]:
    """Propose a CLV-vs-close candidate, or None (NO_CANDIDATE). NEVER raises.

    Ordering (the inert-by-construction discipline):
      1. KILL-SWITCH: with the PIPELINE_ENABLED sentinel absent (require_enabled),
         return None unconditionally -- byte-identical NO_CANDIDATE baseline.
      2. Route the settled window through build_close_corpus (the model-BEATS-close
         -on-outcome gate). It returns None for a shrink-toward-close / all-proxy /
         thin window, so a SHRINK candidate yields NOTHING here.
      3. Only a genuine all-positive beats-close corpus is packaged into a
         candidate (vs_close stays UNPROVEN, min_corpora>=2). The corpus's honesty
         text passes assert_no_dollar before it is returned.

    require_enabled mirrors build_close_corpus so tests can exercise the
    beats-close routing without the live sentinel; production callers leave it True.
    """
    try:
        # 1) kill-switch: inert when the human sentinel is absent.
        if require_enabled and not pipeline_enabled():
            return None
        if not settled:
            return None

        # 2) route through the model-BEATS-close gate. A shrink-toward-close window
        #    (model == close, outcome-Brier flat) returns None here -> no candidate.
        corpus = build_close_corpus(settled, alpha=alpha,
                                    require_enabled=require_enabled)
        if corpus is None:
            return None
        # defensive: a non-positive corpus is not a beat -> no candidate.
        if not corpus.get("all_positive", False):
            return None

        # 3) honesty choke on the corpus's text fields, then package.
        assert_no_dollar(str(corpus.get("note", "")))
        assert_no_dollar(str(corpus.get("vs_close", VS_CLOSE)))
        candidate = _candidate_dict(sport, target, corpus)
        # final honesty pass on every text field of the proposed candidate.
        for key in ("family", "sport", "target", "note", "vs_close"):
            assert_no_dollar(str(candidate.get(key, "")))
        return candidate
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> NO_CANDIDATE.
        logger.debug("propose_clv_candidate(%s) failed -> NO_CANDIDATE: %s",
                     name, exc)
        return None


__all__ = ["propose_clv_candidate", "FAMILY_CLV_VS_CLOSE"]
