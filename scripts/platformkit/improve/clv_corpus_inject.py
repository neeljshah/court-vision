"""scripts.platformkit.improve.clv_corpus_inject -- the sentinel-guarded BRIDGE that
hands the settled-CLV close corpus (clv_corpus.build_close_corpus) to the 5-gate
ratchet, replacing the empty ``corpora: []`` that wedges the loop at
REPLICATION_PENDING. Inc2's wiring half.

It is the do-no-harm bridge, NOT a ship objective:
  * INERT when the human-only PIPELINE_ENABLED sentinel is ABSENT -- inject_corpus
    returns the candidate UNCHANGED (byte-identical, still ``corpora: []`` -> the
    daemon's downstream verdict stays NO_CANDIDATE / REPLICATION_PENDING).
  * It does NOT itself decide a ship and it does NOT self-stamp a vs_close upgrade
    (P2). vs_close stays "UNPROVEN" on every path here. An upgrade record is emitted
    ONLY by maybe_vs_close_upgrade() and ONLY after ALL of: the gate already
    SHIPPED (gate_ship is True) AND n_rep >= 2 independent corpora AND the close
    corpus's clustered DM p < 0.05. clv_corpus_inject NEVER stamps the upgrade onto
    the candidate or any registry/flag itself -- it returns an honest verdict the
    human-gated wire-in may record. Missing any condition -> None (no upgrade).

Reuses build_close_corpus VERBATIM (no CLV/DM/Brier re-implementation). Never
flips a flag, never creates the sentinel, never writes data/registry/ or
MEMORY.md, never claims a $ edge. NO $/roi/pnl field. NEVER raises; any failure
leaves the candidate UNCHANGED. stdlib + repo-internal; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from scripts.platformkit.improve.clv_corpus import build_close_corpus, CLV_CORPUS_ID
from scripts.platformkit.improve.pipeline_flag import pipeline_enabled

logger = logging.getLogger("clv_corpus_inject")

# vs_close NEVER advances to anything but UNPROVEN through this bridge.
_UNPROVEN = "UNPROVEN"

# An upgrade requires at least this many independent corpora (the primary recal
# corpus + the settled-CLV close corpus). Matches the ratchet's min_corpora.
_MIN_REP = 2

# The clustered-DM significance bar for a vs_close upgrade (P2). Same alpha the
# corpus builder uses; restated here because the upgrade is a SEPARATE decision.
_DM_ALPHA = 0.05


def inject_corpus(candidate: Optional[Dict[str, Any]],
                  settled: Sequence[Dict[str, Any]],
                  *, alpha: float = _DM_ALPHA,
                  require_enabled: bool = True) -> Optional[Dict[str, Any]]:
    """Return ``candidate`` with the settled-CLV close corpus appended, or UNCHANGED.

    INERT (sentinel absent): returns the candidate object unchanged so the daemon's
    behaviour is byte-identical to its ``corpora: []`` baseline (NO_CANDIDATE /
    REPLICATION_PENDING). When the sentinel IS present and the settled window yields
    a genuine model-beats-close corpus (build_close_corpus is not None), that single
    corpus is appended to candidate['corpora'] so multifold can satisfy
    min_corpora>=2. When build_close_corpus returns None (shrink-toward-close /
    all-proxy / too few clusters), the candidate is returned UNCHANGED -- no phantom
    corpus is fabricated. vs_close STAYS UNPROVEN here regardless (P2). NEVER raises.
    """
    if candidate is None:
        return None
    try:
        if require_enabled and not pipeline_enabled():
            return candidate  # inert: byte-identical, corpora unchanged

        corpus = build_close_corpus(settled, alpha=alpha,
                                    require_enabled=require_enabled)
        if corpus is None:
            return candidate  # honest: no model-beats-close corpus -> unchanged

        # Append (do not replace) so the recal primary corpus + any others remain.
        existing = list(candidate.get("corpora") or [])
        if not any(isinstance(c, dict) and c.get("corpus_id") == CLV_CORPUS_ID
                   for c in existing):
            existing.append(corpus)
        out = dict(candidate)
        out["corpora"] = existing
        # P2: never self-stamp an upgrade. vs_close stays UNPROVEN on this path.
        out["vs_close"] = _UNPROVEN
        out["clv_corpus_injected"] = True
        return out
    except Exception as exc:  # noqa: BLE001 -- purity: leave candidate UNCHANGED
        logger.debug("inject_corpus failed -> candidate unchanged: %s", exc)
        return candidate


def maybe_vs_close_upgrade(*, gate_ship: bool,
                           n_rep: int,
                           close_corpus: Optional[Dict[str, Any]],
                           ) -> Optional[Dict[str, Any]]:
    """Emit a vs_close UPGRADE verdict ONLY when ALL P2 conditions hold, else None.

    The upgrade from the default vs_close=UNPROVEN to a PROVEN reading is the rare
    honest exception, and it is NEVER self-stamped by this loop. This function
    returns an upgrade RECORD (for a human-gated wire-in to record) only when:
        gate_ship is True                         (the ratchet already SHIPPED) AND
        n_rep >= 2                                (>=2 independent corpora) AND
        the close corpus's clustered DM p < 0.05  (significant model-beats-close).
    ANY missing condition -> None (no upgrade; vs_close stays UNPROVEN). This
    function applies NOTHING; it only describes the verdict.
    """
    try:
        if not bool(gate_ship):
            return None
        if int(n_rep) < _MIN_REP:
            return None
        if not isinstance(close_corpus, dict):
            return None
        # The close corpus must itself be a significant model-beats-close win.
        dm_p = close_corpus.get("dm_p")
        if dm_p is None or float(dm_p) >= _DM_ALPHA:
            return None
        if close_corpus.get("all_positive") is not True:
            return None
        return {
            "vs_close": "PROVEN",   # the verdict ONLY -- never written back here
            "reason": "gate_ship AND n_rep>=2 AND clustered DM p<0.05",
            "n_rep": int(n_rep),
            "dm_p": float(dm_p),
            "corpus_id": str(close_corpus.get("corpus_id", CLV_CORPUS_ID)),
            "note": "verdict only; not self-stamped; human-gated to record",
            "units": "probability",
        }
    except Exception as exc:  # noqa: BLE001 -- purity: no upgrade on any failure
        logger.debug("maybe_vs_close_upgrade failed -> None: %s", exc)
        return None


__all__ = ["inject_corpus", "maybe_vs_close_upgrade", "CLV_CORPUS_ID"]
