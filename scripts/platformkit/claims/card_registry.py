"""scripts.platformkit.claims.card_registry -- hypothesis-card pre-registration lock.

A CARD is ONE conditional claim ("X helps WHEN condition C holds"), written
and locked BEFORE any outcome is examined. This module is the registry: it
enforces the invariants that make a card pre-registered rather than a
post-hoc rationalisation --

  * MAX_OPEN cards may be OPEN at once; extras QUEUE until a slot frees.
  * condition.trigger may reference ONLY an allow-listed as-of field (pregame
    prior or realized in-game state as-of-tick) -- never a season-final or
    post-hoc field. Unknown/forbidden fields REJECT at registration.
  * Once outcomes_peeked=true, claim/condition/mechanism/expected_sign/
    expected_magnitude can never be edited again -- an attempted edit closes
    the OLD card as REJECTED ("post-hoc modification") instead of mutating it.

Storage is one append-only JSONL (data/cache/claims/cards.jsonl): each edit
appends a NEW row for the same card_id: readers take the latest row per id.
That is what makes "no post-hoc edit" enforceable -- the old row is still on
disk, untouched, forever.

Paper-only. No $ fields. ASCII stdout. <=300 LOC.
"""
from __future__ import annotations

import json
import pathlib
import re
import uuid
from typing import Any

from scripts.platformkit.io_atomic import append_jsonl_atomic

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CARDS_PATH = _REPO_ROOT / "data" / "cache" / "claims" / "cards.jsonl"

MAX_OPEN = 10

VALID_SCOPES = {"ingame", "pregame"}
VALID_ENTITIES = {"team", "player", "lineup", "game"}
VALID_SIGNS = {"+", "-"}

# Fields condition.trigger may reference: as-of state ONLY (pregame priors /
# realized in-game state as-of-tick). Anything else -- season-final box
# scores, next-game results, full-season postgame averages -- is a leak and
# REJECTs at registration. Extend this set deliberately; do not widen it to
# a regex that would let an unreviewed field slip through.
ALLOWED_TRIGGER_FIELDS = {
    # in-game as-of-tick state
    "quarter", "clock_seconds_elapsed", "seconds_remaining_period",
    "possession_diff_asof", "score_margin_asof", "score_margin_abs_asof",
    "realized_pace_asof", "realized_margin_asof", "pace_deviation_asof",
    "margin_deviation_asof", "home_flag", "back_to_back_flag_asof",
    # pregame priors (known before tip, static team/player identity)
    "expected_pace_pregame", "expected_margin_pregame",
    "matchup_prior_margin", "matchup_prior_pace_diff",
    "pace_identity_diff", "spacing_pctile_diff", "rim_protection_pctile_diff",
    "perimeter_denial_pctile_diff", "transition_d_pctile_diff",
    "scheme_tag_overlap",
    "def_transition_pctile_home", "opp_transition_share_pctile_away",
    "spacing_pctile_home", "opp_perimeter_denial_pctile_away",
    "paint_protection_pctile_home", "opp_rim_freq_pctile_away",
    "pace_identity_home_fast", "opp_pace_control_pctile_away",
    "oreb_pctile_home", "opp_dreb_pctile_away",
    "tov_forced_pctile_home", "opp_tov_rate_pctile_away",
    "closeout_pctile_home", "opp_3pa_rate_pctile_away",
}

# Fields that can be updated after outcomes_peeked=true WITHOUT counting as
# a post-hoc modification of the claim itself (bookkeeping, not the bet).
_MUTABLE_AFTER_PEEK = {"status", "reason", "outcomes_peeked"}
_PROTECTED_FIELDS = {"claim", "condition", "mechanism", "expected_sign", "expected_magnitude"}

_PY_KEYWORDS = {"and", "or", "not", "in", "is", "True", "False", "None", "abs"}


def validate_trigger(trigger: str) -> tuple[bool, str]:
    """Extract identifiers from *trigger* and check each is allow-listed.

    Returns (ok, reason). reason names the first offending field on failure.
    """
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", trigger)
    fields = [t for t in tokens if t not in _PY_KEYWORDS]
    for f in fields:
        if f not in ALLOWED_TRIGGER_FIELDS:
            return False, f"forbidden/unknown trigger field: {f}"
    return True, "ok"


def _read_rows() -> list[dict]:
    if not CARDS_PATH.is_file():
        return []
    rows = []
    for line in CARDS_PATH.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _latest_by_id(rows: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        cid = row.get("card_id")
        if cid:
            latest[cid] = row  # later rows in file order win
    return latest


def get_all_latest() -> dict[str, dict]:
    """card_id -> latest row (append-only log collapsed to current state)."""
    return _latest_by_id(_read_rows())


def get_open() -> list[dict]:
    return [c for c in get_all_latest().values() if c.get("status") == "OPEN"]


def can_edit(card_id: str) -> bool:
    """False once outcomes_peeked=true -- claim/condition/mechanism are frozen."""
    card = get_all_latest().get(card_id)
    if card is None:
        return False
    return not card.get("outcomes_peeked", False)


def register(
    claim: str,
    condition: dict[str, Any],
    mechanism: str,
    expected_sign: str,
    expected_magnitude: str,
    source: str,
    ts: str,
) -> dict[str, Any]:
    """Pre-register one card. Validates BEFORE writing anything.

    Returns {"ok": True, "card_id": ..., "status": "OPEN"|"QUEUED"} or
    {"ok": False, "reason": ...} -- rejected registrations write NOTHING.
    """
    if not mechanism or not mechanism.strip():
        return {"ok": False, "reason": "mechanism is required"}
    if expected_sign not in VALID_SIGNS:
        return {"ok": False, "reason": f"expected_sign must be one of {VALID_SIGNS}"}
    scope = condition.get("scope")
    if scope not in VALID_SCOPES:
        return {"ok": False, "reason": f"condition.scope must be one of {VALID_SCOPES}"}
    entity = condition.get("entity")
    if entity not in VALID_ENTITIES:
        return {"ok": False, "reason": f"condition.entity must be one of {VALID_ENTITIES}"}
    trigger = condition.get("trigger", "")
    ok, reason = validate_trigger(trigger)
    if not ok:
        return {"ok": False, "reason": reason}

    status = "OPEN" if len(get_open()) < MAX_OPEN else "QUEUED"
    card_id = f"card_{uuid.uuid4().hex[:10]}"
    row = {
        "card_id": card_id,
        "claim": claim,
        "condition": condition,
        "mechanism": mechanism,
        "expected_sign": expected_sign,
        "expected_magnitude": expected_magnitude,
        "source": source,
        "registered_ts": ts,
        "status": status,
        "outcomes_peeked": False,
    }
    append_jsonl_atomic(CARDS_PATH, row)
    return {"ok": True, "card_id": card_id, "status": status}


def update_card(card_id: str, changes: dict[str, Any], ts: str) -> dict[str, Any]:
    """Apply *changes* to a card. Protected-field changes after outcomes_peeked
    auto-REJECT the old card instead of mutating it (see module docstring)."""
    current = get_all_latest().get(card_id)
    if current is None:
        return {"ok": False, "reason": "unknown card_id"}
    touches_protected = bool(_PROTECTED_FIELDS & set(changes))
    if touches_protected and not can_edit(card_id):
        rejected = {**current, "status": "REJECTED", "reason": "post-hoc modification", "updated_ts": ts}
        append_jsonl_atomic(CARDS_PATH, rejected)
        return {"ok": False, "reason": "post-hoc modification", "card_id": card_id}
    updated = {**current, **changes, "updated_ts": ts}
    append_jsonl_atomic(CARDS_PATH, updated)
    return {"ok": True, "card_id": card_id}


def mark_peeked(card_id: str, ts: str) -> dict[str, Any]:
    return update_card(card_id, {"outcomes_peeked": True}, ts)


def close_card(card_id: str, status: str, reason: str, ts: str) -> dict[str, Any]:
    return update_card(card_id, {"status": status, "reason": reason}, ts)


def promote_queued(ts: str) -> list[str]:
    """Fill any OPEN slots freed by closed cards, oldest-QUEUED-first."""
    free = MAX_OPEN - len(get_open())
    if free <= 0:
        return []
    queued = sorted(
        (c for c in get_all_latest().values() if c.get("status") == "QUEUED"),
        key=lambda c: c.get("registered_ts", ""),
    )
    promoted = []
    for card in queued[:free]:
        update_card(card["card_id"], {"status": "OPEN"}, ts)
        promoted.append(card["card_id"])
    return promoted


__all__ = [
    "CARDS_PATH", "MAX_OPEN", "ALLOWED_TRIGGER_FIELDS",
    "validate_trigger", "get_all_latest", "get_open", "can_edit",
    "register", "update_card", "mark_peeked", "close_card", "promote_queued",
]
