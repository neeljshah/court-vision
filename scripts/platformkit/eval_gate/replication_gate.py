"""scripts.platformkit.eval_gate.replication_gate -- make the replication floor a GATE.

`combo/fwer_budget.min_corpora_eff` computes the replication floor that rises with K,
but the modules that WRITE the literal verdict "AHEAD" never consulted it, so a
single-window AHEAD was downgraded only by memo (VERIFIER_CONTRACT Q5). This module
turns that convention into a pure function a call site can apply additively.

Rules (deliberately narrow -- B2 non-additive-schema guard):
  * ONLY an AHEAD verdict can be downgraded, and only to the literal "SINGLE-WINDOW".
  * Every other verdict (BEHIND, MATCH, NULL, INSUFFICIENT, REJECT, ...) is returned
    BYTE-IDENTICAL. A replication floor is not a quality judgement on a non-AHEAD.
  * `n_corpora` counts disjoint `corpus_unit`s, not rows: tennis ATP vs WTA, soccer
    D1/E0/E1/F1/I1/SP1, MLB's two eras, NBA's two seasons. Replication needs no new data.

`min_corpora_eff` itself is a SHARED MODULE and is imported READ-ONLY; no constant,
threshold or bar in it is touched here.

Calibration language only: no dollar, ROI, profit or edge wording. A SINGLE-WINDOW
label is an honest downgrade, i.e. a success, not a failure.
ASCII; stdlib + the read-only shared import.
Per-file test: python -m pytest scripts/platformkit/eval_gate/test_replication_gate.py -q
"""
from __future__ import annotations

from typing import Any, Dict

from scripts.platformkit.combo.fwer_budget import min_corpora_eff

# The one label this module may introduce. Never replaces a stored verdict in place --
# call sites write it BESIDE the original (see hedge_trial_runner.verdict_of_replicated).
SINGLE_WINDOW = "SINGLE-WINDOW"


def _is_ahead(verdict: str) -> bool:
    """True for the literal "AHEAD" or any "<prefix>_AHEAD" (e.g. "e4_AHEAD")."""
    v = str(verdict)
    return v == "AHEAD" or v.endswith("_AHEAD")


def replication_verdict(verdict: str, n_corpora: int, k: int) -> str:
    """Downgrade an AHEAD that did not replicate; pass everything else through unchanged.

    floor = min_corpora_eff(max(1, n_corpora), k)   # >= 2 always, capped at 4
    Downgrade iff the verdict is AHEAD-shaped AND n_corpora < floor.
    """
    if not _is_ahead(verdict):
        return str(verdict)
    floor = min_corpora_eff(max(1, int(n_corpora)), int(k))
    return SINGLE_WINDOW if int(n_corpora) < floor else str(verdict)


def replication_fields(verdict: str, n_corpora: int, k: int) -> Dict[str, Any]:
    """The four keys an artifact embeds so the downgrade is auditable, never implicit."""
    return {
        "verdict_replicated": replication_verdict(verdict, n_corpora, k),
        "min_corpora_eff": int(min_corpora_eff(max(1, int(n_corpora)), int(k))),
        "n_corpora": int(n_corpora),
        "k_cumulative": int(k),
    }


__all__ = ["SINGLE_WINDOW", "replication_verdict", "replication_fields"]
