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
import os
import pathlib
import re
import uuid
from typing import Any

from scripts.platformkit.io_atomic import append_jsonl_atomic

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CARDS_PATH = _REPO_ROOT / "data" / "cache" / "claims" / "cards.jsonl"

# 2026-07-15 USER DIRECTIVE: scale to 10,000s of cards and validate as many as
# possible autonomously. The pre-registration integrity comes from the
# lock-before-peek + allowlisted-trigger invariants, NOT from a small open
# count; the grader's per-card two-half gate handles the multiple-comparison
# load (verdict rows carry family metadata for FDR accounting downstream).
MAX_OPEN = int(os.environ.get("CV_CLAIMS_MAX_OPEN", "20000") or 20000)

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
    # as-of-tick fields ACTUALLY CARRIED by the live capture rows
    # (data/cache/ingame_grade/<sport>/*.jsonl -- verified 2026-07-15). All are
    # captured before the tick's outcome is known; ids are excluded on purpose.
    "model_prob", "market_prob", "espn_wp", "spread_bp", "book_thinness",
    "stale_quote", "xg_home", "xg_away", "xg_asof_min",
    "mlb_pitcher_pitch_count", "mlb_bullpen_used",
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


# (mtime, size) -> parsed rows. With 10,000s of cards the per-tick tagger
# cannot afford a full JSONL re-parse per tag() call; the file is append-only
# so (mtime, size) is a sound freshness key. One entry, module-level.
_ROWS_CACHE: list = [None, None]  # [key, rows]


def _read_rows() -> list[dict]:
    if not CARDS_PATH.is_file():
        return []
    try:
        st = CARDS_PATH.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key is not None and _ROWS_CACHE[0] == key:
        return _ROWS_CACHE[1]
    rows = []
    for line in CARDS_PATH.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if key is not None:
        _ROWS_CACHE[0], _ROWS_CACHE[1] = key, rows
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


def _append_rows(rows: list[dict[str, Any]]) -> None:
    """ONE crash-safe append for many rows: read once, write once, replace.
    append_jsonl_atomic re-reads + rewrites the whole file PER ROW -- O(n^2)
    I/O that took 10k-card registration from seconds to an hour."""
    if not rows:
        return
    CARDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = CARDS_PATH.read_text(encoding="ascii", errors="replace") if CARDS_PATH.is_file() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    body = existing + "".join(
        json.dumps(r, ensure_ascii=True, sort_keys=True) + "\n" for r in rows)
    tmp = CARDS_PATH.with_suffix(".jsonl.tmp_bulk")
    tmp.write_text(body, encoding="ascii")
    import os as _os
    _os.replace(str(tmp), str(CARDS_PATH))


def register_bulk(cards: list[dict[str, Any]], source: str, ts: str) -> dict[str, Any]:
    """Pre-register many cards in one pass (bulk-miner path). Same validation
    as register() per card, but open-slot count is computed ONCE and rows are
    written in ONE atomic append (register()'s per-card get_open() re-read +
    append_jsonl_atomic's per-row full-file rewrite are both O(n^2) at 10k
    cards). Invalid cards are skipped and reported, never written."""
    open_now = len(get_open())
    n_open = n_queued = 0
    rejected: list[str] = []
    to_write: list[dict[str, Any]] = []
    for c in cards:
        cond = c.get("condition") or {}
        if (not str(c.get("mechanism") or "").strip()
                or c.get("expected_sign") not in VALID_SIGNS
                or cond.get("scope") not in VALID_SCOPES
                or cond.get("entity") not in VALID_ENTITIES):
            rejected.append("shape")
            continue
        ok, reason = validate_trigger(cond.get("trigger", ""))
        if not ok:
            rejected.append(reason)
            continue
        status = "OPEN" if open_now < MAX_OPEN else "QUEUED"
        row = {
            "card_id": f"card_{uuid.uuid4().hex[:10]}",
            "claim": c["claim"], "condition": cond, "mechanism": c["mechanism"],
            "expected_sign": c["expected_sign"],
            "expected_magnitude": c.get("expected_magnitude", ""),
            "family": c.get("family"), "cell": c.get("cell"),
            "source": source, "registered_ts": ts,
            "status": status, "outcomes_peeked": False,
        }
        to_write.append(row)
        if status == "OPEN":
            open_now += 1
            n_open += 1
        else:
            n_queued += 1
    _append_rows(to_write)
    return {"ok": True, "n_open": n_open, "n_queued": n_queued,
            "n_rejected": len(rejected), "reject_sample": rejected[:5]}


def bulk_update(changes_by_id: dict[str, dict[str, Any]], ts: str) -> int:
    """Apply per-card *changes* for many cards with ONE registry read (the
    bulk grader path -- update_card()'s per-call re-read is O(n^2) at 10k
    cards). Same protected-field discipline as update_card: a protected-field
    change on a peeked card REJECTS that card instead of mutating it.
    Returns rows appended."""
    latest = get_all_latest()
    rows: list[dict[str, Any]] = []
    for card_id, changes in changes_by_id.items():
        current = latest.get(card_id)
        if current is None:
            continue
        if (_PROTECTED_FIELDS & set(changes)) and current.get("outcomes_peeked", False):
            rows.append({**current, "status": "REJECTED",
                         "reason": "post-hoc modification", "updated_ts": ts})
            continue
        rows.append({**current, **changes, "updated_ts": ts})
    _append_rows(rows)
    return len(rows)


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
    "register", "register_bulk", "update_card", "bulk_update", "mark_peeked",
    "close_card", "promote_queued",
]
