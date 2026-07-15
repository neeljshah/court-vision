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


# trigger string -> (fields, compiled code). Cards are 10,000s now; re-parsing
# every trigger on every tick is the difference between ~ms and ~seconds.
_COMPILED: Dict[str, Any] = {}


def _trigger_fields(trigger: str) -> set:
    return {t for t in _FIELD_RE.findall(trigger) if t not in _PY_KEYWORDS}


def _compiled(trigger: str):
    """(fields, code) for *trigger*, cached. code is None if uncompilable."""
    hit = _COMPILED.get(trigger)
    if hit is None:
        fields = _trigger_fields(trigger)
        try:
            code = compile(trigger, "<trigger>", "eval")
        except Exception:  # noqa: BLE001 -- bad trigger -> never fires
            code = None
        hit = (fields, code)
        _COMPILED[trigger] = hit
    return hit


def eval_trigger(trigger: str, state: Dict[str, Any]) -> bool:
    """Fail-closed single-trigger evaluation against as-of *state*: missing
    field, None-valued comparison, or any eval error -> False. Shared by tag()
    (live capture) and card_grader's retro-tagging (historical as-of rows)."""
    fields, code = _compiled(trigger)
    if code is None or not fields or not fields.issubset(state.keys()):
        return False
    try:
        return bool(eval(code, _SAFE_GLOBALS, dict(state)))  # noqa: S307 -- allowlisted fields only, no builtins
    except Exception:  # noqa: BLE001 -- any eval hiccup -> not fired, never raise
        return False


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
        out[card_id] = eval_trigger(cond.get("trigger", ""), state)
    return out


__all__ = ["tag", "eval_trigger"]
