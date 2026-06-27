"""scripts.platformkit.bestbets.calibration_gate -- bet only where calibration is PROVEN.

The smarter-selection layer: an efficient market punishes a high-volume model-view prop
flood (the pregame prop channel bleeds), so concentrate stake on the (sport, stat) families
the system has ALREADY proven it calibrates better on -- the replicated SHIP verdicts from
the leak-free prop-calibration backtest (data/frontend/prop_history_meta.json).

A family qualifies only when its `replicated_verdict == "SHIP_REPLICATED"` (multiple
independent leak-free folds beat held-out Brier, planted-null did NOT leak). A single-fold
lift, a HOLD, an INSUFFICIENT_DATA, or a REJECT (planted-null fired) does NOT qualify --
those are honestly NOT proven, so we do not stake them pregame.

HONEST FRAMING: "proven calibration" means better-calibrated probabilities across folds,
NOT a market edge or any $ profit. This gate reduces exposure to the model-overconfidence
artifact; CLV remains the judge. UNITS only; no $.

Fail-open on a transient meta read error (return permissive) so a missing file never silently
zeroes the slate; when the meta IS present, the gate is enforced.

RAILS: build only under scripts/platformkit/; ASCII; <=300 LOC; public fns NEVER raise.
Per-file test: scripts/platformkit/bestbets/test_calibration_gate.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_META = _REPO / "data" / "frontend" / "prop_history_meta.json"

# prop_history_meta stat token -> the canonical prop_stat name(s) it gates. Explicit (not a
# substring match) so "runs" never accidentally allows "Home Runs". Tokens are the backtest's
# lowercased stat keys; values are the prop board's canonical stat strings.
_META_TO_CANON: Dict[str, Set[str]] = {
    "hits": {"Hits"},
    "runs": {"Runs"},
    "rbi": {"RBIs"},
    "totalbases": {"Total Bases"},
    "homeruns": {"Home Runs"},
    "walks": {"Walks"},
    "stolenbases": {"Stolen Bases"},
    "strikeouts": {"Pitcher Strikeouts"},
    "batterstrikeouts": {"Batter Strikeouts"},
    # soccer (once it accumulates enough leak-free folds to replicate)
    "goals": {"Goals"},
    "assists": {"Assists"},
    "cards": {"Cards"},
}
_PROVEN_VERDICT = "SHIP_REPLICATED"


def proven_families(*, meta_path: Optional[Path] = None
                    ) -> Optional[Dict[str, Set[str]]]:
    """{sport: {canonical_stat, ...}} of replicated-SHIP families, or None when the meta is
    unreadable (caller then fails open). Excludes the pooled 'all' group (not a single stat)
    and any non-SHIP_REPLICATED verdict. Never raises."""
    p = Path(meta_path) if meta_path is not None else _DEFAULT_META
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("calibration_gate: meta read failed %s: %s", p, exc)
        return None
    out: Dict[str, Set[str]] = {}
    for g in (meta.get("groups") or []):
        if str(g.get("replicated_verdict")) != _PROVEN_VERDICT:
            continue
        stat = str(g.get("stat") or "").strip().lower()
        if not stat or stat == "all":
            continue  # pooled model, not a single stakeable stat
        canon = _META_TO_CANON.get(stat)
        if not canon:
            continue
        sport = str(g.get("sport") or "").strip().lower()
        out.setdefault(sport, set()).update(canon)
    return out


def is_calibration_proven(sport: str, stat: str,
                          *, proven: Optional[Dict[str, Set[str]]] = None,
                          meta_path: Optional[Path] = None) -> bool:
    """True when (sport, stat) is a replicated-SHIP family -- safe to stake pregame.

    Fails OPEN (True) when the meta is unreadable so a transient miss never zeroes the slate;
    enforced strictly when the meta is present. *proven* injectable for batch/tests."""
    fam = proven if proven is not None else proven_families(meta_path=meta_path)
    if fam is None:
        return True  # meta unreadable -> do not block (tier/cap discipline still applies)
    allow = fam.get(str(sport).lower())
    if not allow:
        return False  # sport present in the proof world but nothing replicated -> don't stake
    return str(stat or "").strip() in allow


__all__ = ["proven_families", "is_calibration_proven"]
