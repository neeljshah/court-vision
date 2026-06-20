"""predict_service.edge_completion_gate -- post-filter: no bet on a completed game.

BE-B-edge-completion-gate (QA iter 11 P1).
BE-R3-2 (QA iter 231/279): closes the per-game edges/bestbets leak.

On suppression enforces: freshness='stale', decision='no_bet',
stake_units+tier REMOVED, skip_reason='game_final'.

Detection arms (first match wins):
  0. game_state=='post' in payload (PredictionRecord 1.2.0 field).
  1. Explicit finals list via postgame_suppress.
  2. state_map entry (completed/state).
  3. Timeout: commence_time + max_duration_h in the past.
No signal / future -> payload unchanged (conservative).

Public API: apply_game_gate | apply_games_gate | gate_decide_payload.
HONESTY: no $ field; stale-never-green; real-money stays DENY.
INVARIANTS: predict_service/ only; <=300 LOC; ASCII only; no $; no src/kernel/api.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MAX_DURATION_H: float = 5.0

_REASON_FINALS = "game_complete_finals_list"
_REASON_STATE_MAP = "game_complete_state_map"
_REASON_TIMEOUT = "game_complete_timeout"
_REASON_GAME_STATE = "game_complete_game_state_field"

# State values recognised as "game is over" in any completion signal or payload.
_COMPLETED_STATES = frozenset({
    "post", "final", "STATUS_FINAL", "STATUS_FULL_TIME",
    "STATUS_FINAL_PEN", "STATUS_FINAL_OVERTIME",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rec_is_complete(rec: Dict[str, Any]) -> bool:
    if bool(rec.get("completed")):
        return True
    state = str(rec.get("state") or "").strip()
    return state.lower() in {"post", "final"} or state in _COMPLETED_STATES


def _parse_utc(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return None
    return None


def _game_state_is_post(payload: Dict[str, Any]) -> bool:
    """Return True when the payload carries game_state='post' (PredictionRecord 1.2.0).

    This is arm 0: the most authoritative signal -- the producer already resolved
    live-state + tipoff-heuristic into a canonical 'pre'|'live'|'post' label.
    """
    gs = payload.get("game_state")
    if gs is None:
        return False
    return str(gs).strip().lower() in {"post", "final"}


def _detect_completion(
    game_id: str,
    *,
    payload: Optional[Dict[str, Any]],
    finals: Optional[List[Dict[str, Any]]],
    state_map: Optional[Dict[str, Dict[str, Any]]],
    commence_time: Optional[str],
    now: datetime,
    max_duration_h: float,
) -> Optional[str]:
    """Return a completion reason string or None. Delegates to postgame_suppress.

    Detection order (first match wins):
      0. game_state=='post' field in payload (PredictionRecord 1.2.0, most direct).
      1. Explicit finals list (delegates to postgame_suppress).
      2. state_map entry with completed/state.
      3. Timeout: commence_time + max_duration_h in the past.
    """
    # Arm 0: game_state field in the payload (fastest, no I/O).
    if payload and _game_state_is_post(payload):
        return _REASON_GAME_STATE

    # Prefer postgame_suppress (single truth source for arms 1-3).
    try:
        from scripts.platformkit.ingame.postgame_suppress import suppress_verdict  # noqa
        v = suppress_verdict(
            game_id, finals=finals, state_map=state_map,
            commence_time=commence_time, now=now,
            max_game_duration_h=max_duration_h,
        )
        return str(v.get("reason", "game_complete")) if v.get("suppress_bet") else None
    except Exception:  # noqa: BLE001
        pass

    gid = str(game_id)

    # Arm 1: explicit finals list
    if finals:
        for rec in finals:
            if not isinstance(rec, dict):
                continue
            if str(rec.get("game_id") or "") != gid:
                continue
            if _rec_is_complete(rec):
                return _REASON_FINALS

    # Arm 2: state_map
    if state_map:
        entry = state_map.get(gid) or state_map.get(str(gid))
        if isinstance(entry, dict) and _rec_is_complete(entry):
            return _REASON_STATE_MAP

    # Arm 3: timeout arm
    ct_str = commence_time
    if ct_str is None and state_map:
        entry = (state_map.get(gid) or state_map.get(str(gid))) or {}
        if isinstance(entry, dict):
            ct_str = entry.get("commence_time")
    if ct_str is not None:
        commence_dt = _parse_utc(ct_str)
        if commence_dt is not None and now >= commence_dt + timedelta(hours=max_duration_h):
            return _REASON_TIMEOUT

    return None


def _force_stale_freshness(payload: Dict[str, Any]) -> None:
    """Mutate freshness block in-place to stale.  Never raises."""
    f = payload.get("freshness")
    if isinstance(f, dict):
        f["status"] = "stale"
        f["ok"] = False
        f["fresh"] = False
        f["stale"] = True
        if not f.get("reason"):
            f["reason"] = "game_complete"
    else:
        payload["freshness"] = {
            "status": "stale", "ok": False,
            "fresh": False, "stale": True,
            "reason": "game_complete",
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_game_gate(
    payload: Dict[str, Any],
    *,
    game_id: Optional[str] = None,
    finals: Optional[List[Dict[str, Any]]] = None,
    state_map: Optional[Dict[str, Dict[str, Any]]] = None,
    commence_time: Optional[str] = None,
    now: Optional[datetime] = None,
    max_duration_h: float = DEFAULT_MAX_DURATION_H,
) -> Dict[str, Any]:
    """Apply the completion gate to ONE per-game payload dict.

    Returns a deep copy of payload with:
      - freshness.status='stale', decision='no_bet', stake_units/tier removed
        when game is post/Final or past commence+max_duration.
      - Unchanged (deep copy) when completion is unknown or future.
    Never raises; degrades to a deep copy on internal error.
    game_id falls back to payload.get('game_id').
    commence_time falls back to payload.get('tipoff') / payload.get('commence_time').
    game_state='post' in payload is checked first (arm 0, PredictionRecord 1.2.0).
    """
    if not isinstance(payload, dict):
        return {}
    try:
        if now is None:
            now = datetime.now(tz=timezone.utc)
        gid = str(game_id or payload.get("game_id") or "")
        if not gid:
            return copy.deepcopy(payload)
        ct = commence_time
        if ct is None:
            raw_ct = payload.get("tipoff") or payload.get("commence_time")
            ct = str(raw_ct) if raw_ct is not None else None
        reason = _detect_completion(
            gid, payload=payload, finals=finals, state_map=state_map,
            commence_time=ct, now=now, max_duration_h=max_duration_h,
        )
        out = copy.deepcopy(payload)
        if reason is None:
            return out
        _force_stale_freshness(out)
        out["decision"] = "no_bet"
        out.pop("stake_units", None)
        out.pop("tier", None)          # no tier on a settled game
        out["suppressed"] = True
        out["suppress_reason"] = reason
        out.setdefault("skip_reason", "game_final")
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("edge_completion_gate.apply_game_gate error: %s", exc)
        return copy.deepcopy(payload)


def apply_games_gate(
    games: List[Dict[str, Any]],
    *,
    finals: Optional[List[Dict[str, Any]]] = None,
    state_map: Optional[Dict[str, Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
    max_duration_h: float = DEFAULT_MAX_DURATION_H,
) -> List[Dict[str, Any]]:
    """Apply apply_game_gate to a list of per-game payloads. Never raises."""
    if not games:
        return []
    result = []
    for g in games:
        if not isinstance(g, dict):
            result.append(g)
            continue
        gid = str(g.get("game_id") or "") or None
        raw_ct = g.get("tipoff") or g.get("commence_time")
        ct_str = str(raw_ct) if raw_ct is not None else None
        result.append(apply_game_gate(
            g, game_id=gid, finals=finals, state_map=state_map,
            commence_time=ct_str, now=now, max_duration_h=max_duration_h,
        ))
    return result


def gate_decide_payload(
    payload: Dict[str, Any],
    *,
    game_id: Optional[str] = None,
    finals: Optional[List[Dict[str, Any]]] = None,
    state_map: Optional[Dict[str, Dict[str, Any]]] = None,
    commence_time: Optional[str] = None,
    now: Optional[datetime] = None,
    max_duration_h: float = DEFAULT_MAX_DURATION_H,
) -> Dict[str, Any]:
    """Preferred entry point for the per-game edges + bestbets path.

    Thin alias for apply_game_gate that documents the per-game usage contract.
    On suppression: decision='no_bet', skip_reason='game_final', stake_units+tier
    removed, freshness='stale'. Live/pre game -> unchanged deep copy.
    See apply_game_gate for full arm documentation.
    """
    return apply_game_gate(
        payload,
        game_id=game_id,
        finals=finals,
        state_map=state_map,
        commence_time=commence_time,
        now=now,
        max_duration_h=max_duration_h,
    )


__all__ = [
    "apply_game_gate",
    "apply_games_gate",
    "gate_decide_payload",
    "DEFAULT_MAX_DURATION_H",
]
