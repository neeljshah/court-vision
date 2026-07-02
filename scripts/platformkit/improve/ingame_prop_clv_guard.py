"""scripts.platformkit.improve.ingame_prop_clv_guard -- SUPPRESS-ONLY CLV guard for
the in-game player-prop channel (paper_ingame_prop).

MEASURED (2026-06-27, n=402 captured-close in-game prop bets, archived clv_ledger):
    * mean CLV = -31.0% (95% CI excludes 0) -- we systematically take ~31% WORSE than
      the eventual close on this channel.
    * CLV is ANTI-correlated with the model's claimed edge (corr -0.083; the higher-edge
      half is MORE negative, -34.7%).  When the in-game model sees the most "value", we
      get the WORST price vs close -> the channel is structurally adversely-selected.
    * Therefore tightening the edge/vig gate selects for the WORST bets, not the best.
      The only CLV-positive action is to STOP placing this channel.

This gate is SUPPRESS-ONLY: it can ONLY block an in-game prop placement, never add one.
It is the honest ANTI-edge move (stop a measured bleed), NOT an edge claim and NOT a
real-money flag.  Paper / units only.

DEFAULT ON (CV_INGAME_PROP_CLV_GUARD != "0"); set CV_INGAME_PROP_CLV_GUARD=0 to restore
the prior broad-capture behavior.  Re-enable per a future cross-corpus finding that a
sub-slice of the channel is CLV-neutral-or-better; until then, suppress.

The proof lives in scripts/platformkit/clv/clv_scoreboard.py (the channel table) and the
archived ledger under data/frontend/_ledger_archive/.  No src/kernel/api imports; ASCII.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

ENV = "CV_INGAME_PROP_CLV_GUARD"
_OFF = ("0", "off", "false", "no", "")


def is_enabled() -> bool:
    """True when the suppress guard is active (default ON)."""
    return str(os.environ.get(ENV, "1")).strip().lower() not in _OFF


def clv_guard(
    extra: Optional[Callable[[Dict[str, Any]], bool]] = None,
) -> Optional[Callable[[Dict[str, Any]], bool]]:
    """Compose the in-game-prop placement gate.

    When the guard is ON (default): returns a gate that SUPPRESSES every in-game prop
    placement (the channel is measured CLV-adverse) -- and still respects ``extra`` (so
    a stricter optional gate can never be loosened).  When OFF: returns ``extra``
    unchanged (the prior behavior: the optional calib gate, or None = place as before).
    """
    if not is_enabled():
        return extra

    def _gate(row: Dict[str, Any]) -> bool:
        # honor any stricter upstream gate first (compose, never loosen)
        if extra is not None and not extra(row):
            return False
        return False   # measured CLV-adverse channel -> suppress (paper units only)

    return _gate
