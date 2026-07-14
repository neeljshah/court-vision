"""scripts.platformkit.claims.condition_tagger -- tag as-of state against OPEN cards.

PURE function: tag(state, scope) -> {card_id: bool}, one bool per OPEN card whose
condition.scope matches *scope*. Evaluates card_registry's pre-registered
condition.trigger (already field-allowlisted at registration time) against ONLY the
as-of fields present in *state*.

LEAK-FREE / FAIL-CLOSED: a card whose trigger references any field NOT present in
*state* is tagged False, never evaluated, never an error -- so truncating future
fields out of *state* can only turn a True into a False, never fabricate a True.
Same *state* always yields the same tags (no randomness, no I/O beyond the
read-only card registry load).

TAG ONLY -- this module makes zero betting/pricing decisions and writes nothing.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/claims/test_condition_tagger.py -q
"""
from __future__ import annotations

import re
from typing import Any, Dict

from scripts.platformkit.claims import card_registry as _reg

_FIELD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PY_KEYWORDS = {"and", "or", "not", "in", "is", "True", "False", "None", "abs"}
_SAFE_GLOBALS = {"__builtins__": {}, "abs": abs, "True": True, "False": False, "None": None}


def _trigger_fields(trigger: str) -> set:
    return {t for t in _FIELD_RE.findall(trigger) if t not in _PY_KEYWORDS}


def tag(state: Dict[str, Any], scope: str) -> Dict[str, bool]:
    """Tag *state* (as-of fields only) against every OPEN card in *scope*.

    Missing field -> False (card not fired), never an error. Non-matching scope
    is simply excluded from the result.
    """
    out: Dict[str, bool] = {}
    if not isinstance(state, dict):
        state = {}
    for card in _reg.get_open():
        cond = card.get("condition") or {}
        if cond.get("scope") != scope:
            continue
        card_id = card.get("card_id")
        if not card_id:
            continue
        trigger = cond.get("trigger", "")
        fields = _trigger_fields(trigger)
        if not fields or not fields.issubset(state.keys()):
            out[card_id] = False
            continue
        try:
            out[card_id] = bool(eval(trigger, _SAFE_GLOBALS, dict(state)))  # noqa: S307 -- allowlisted fields only, no builtins
        except Exception:  # noqa: BLE001 -- any eval hiccup -> not fired, never raise
            out[card_id] = False
    return out


__all__ = ["tag"]
