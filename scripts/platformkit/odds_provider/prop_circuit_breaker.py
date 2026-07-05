"""scripts.platformkit.odds_provider.prop_circuit_breaker -- provider circuit breaker.

THE GAP (m13 root cause, LANE m13-circuit): the 240s score-cycle timeout wrapper
(props_score_timeout.py) works and exposed the TRUE root cause underneath it --
dead providers called inline in the score path (prizepicks 403 walled, betmgm 400
broken) burn wall-clock on most cycles even though prop_edge._gather already bounds
the whole fetch under one PROP_FETCH_DEADLINE_S (default 30s) deadline. A provider
that is CONSISTENTLY dead should not even be dispatched -- it wastes a thread-pool
slot and, cumulatively across sports/cycles, budget that reliable providers need.

WHAT THIS DOES: a file-backed (JSON, atomic tmp+os.replace) circuit breaker keyed by
provider name. record_result() tracks consecutive failures; after
FAILURE_THRESHOLD (3) consecutive failures the circuit OPENS and the provider is
skipped for COOLDOWN_SEC (~6h), after which it is re-tried (half-open: one real
attempt decides). A single success at any point CLOSES the circuit and resets the
streak -- a provider that recovers is never punished longer than the cooldown.

HONESTY (binding): filter_providers() NEVER silently drops a skipped provider --
every skip is returned in the `skipped` list with reason + since, so callers can
record it as SKIPPED_CIRCUIT in the snapshot/board metadata. State persists across
cycles AND process restarts (disk-backed, not in-memory) so a restart cannot reset
a known-dead provider back to hot-path. Never raises; a corrupt/missing state file
degrades to "no provider has ever failed" (fail open, never fail closed on our own
bug).

Stdlib-only. ASCII-only. <=300 LOC.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_prop_circuit_breaker.py -q
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_STATE_PATH = _REPO / "data" / "cache" / "odds_circuit_breaker" / "prop_circuit_breaker.json"

# ---------------------------------------------------------------------------
# Per-path threading locks (mirrors clv_ledger_guarded_append._path_lock):
# serialise the read-modify-write critical section in record_result/is_open's
# half-open transition so two threads acting on the SAME state file cannot
# both read stale state and clobber each other's update (lost-ping race under
# true concurrency). Keyed on the resolved absolute path string so different
# state files get independent locks.
# ---------------------------------------------------------------------------
_LOCK_REGISTRY: Dict[str, threading.Lock] = {}
_REGISTRY_LOCK = threading.Lock()


def _path_lock(path: Path) -> threading.Lock:
    """Return (creating if needed) the threading.Lock for *path*."""
    key = str(path.resolve())
    with _REGISTRY_LOCK:
        if key not in _LOCK_REGISTRY:
            _LOCK_REGISTRY[key] = threading.Lock()
        return _LOCK_REGISTRY[key]

# Consecutive failures before a provider's circuit OPENS (skipped).
FAILURE_THRESHOLD = 3
# How long an OPEN circuit skips the provider before a half-open retry.
DEFAULT_COOLDOWN_SEC = 6.0 * 3600.0  # 6h

SKIPPED_REASON_TAG = "SKIPPED_CIRCUIT"


def _state_file(state_path: Optional[Path]) -> Path:
    return Path(state_path) if state_path is not None else DEFAULT_STATE_PATH


def _load_state(state_path: Optional[Path] = None) -> Dict[str, Any]:
    """Best-effort read of the circuit-breaker state file. Never raises; missing
    or corrupt file -> {} (equivalent to "no provider has ever failed" -- fail
    OPEN, never fail closed on our own bug)."""
    path = _state_file(state_path)
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001 -- corrupt state must never sink a fetch
        logger.debug("prop_circuit_breaker state read failed for %s: %s", path, exc)
        return {}


def _save_state(state: Dict[str, Any], state_path: Optional[Path] = None) -> None:
    """Atomic (tmp + os.replace) write of the circuit-breaker state. Never raises."""
    path = _state_file(state_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(state, ensure_ascii=True, indent=2, sort_keys=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
    except Exception as exc:  # noqa: BLE001 -- write must never sink a fetch
        logger.debug("prop_circuit_breaker state write failed for %s: %s", path, exc)


def record_result(
        provider: str, ok: bool, *,
        reason: str = "",
        state_path: Optional[Path] = None,
        now: Callable[[], float] = time.time,
        failure_threshold: int = FAILURE_THRESHOLD,
) -> Dict[str, Any]:
    """Record one fetch outcome for *provider*; returns the provider's updated
    entry. A success CLOSES the circuit (resets consecutive_failures to 0,
    clears opened_since). A failure increments consecutive_failures; hitting
    *failure_threshold* OPENS the circuit (sets opened_since = now if not
    already open). Never raises."""
    path = _state_file(state_path)
    lock = _path_lock(path)
    with lock:
        state = _load_state(path)
        ts = float(now())
        entry = state.get(provider)
        if not isinstance(entry, dict):
            entry = {"consecutive_failures": 0, "opened_since": None,
                      "last_reason": "", "last_result_at": ts}
        if ok:
            entry["consecutive_failures"] = 0
            entry["opened_since"] = None
            entry["last_reason"] = ""
        else:
            entry["consecutive_failures"] = int(entry.get("consecutive_failures", 0)) + 1
            entry["last_reason"] = str(reason or "")
            if entry["consecutive_failures"] >= failure_threshold and entry.get("opened_since") is None:
                entry["opened_since"] = ts
        entry["last_result_at"] = ts
        state[provider] = entry
        _save_state(state, path)
        return dict(entry)


def is_open(
        provider: str, *,
        state_path: Optional[Path] = None,
        now: Callable[[], float] = time.time,
        cooldown_sec: float = DEFAULT_COOLDOWN_SEC,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """True (open, i.e. SKIP) iff *provider*'s circuit is open AND still within
    *cooldown_sec* of opened_since. Past cooldown -> half-open (returns False,
    None) so the NEXT real attempt decides (a fresh failure re-opens it via
    record_result; a success closes it). Never raises -> (False, None) on any
    corrupt state (fail open).

    HALF-OPEN TRANSITION (fix, was a bug): once cooldown has elapsed we PERSIST
    the half-open transition by clearing opened_since (and zeroing
    consecutive_failures) on disk. Without this, a failed half-open retry would
    bump consecutive_failures past threshold while opened_since still held the
    ORIGINAL open timestamp -- record_result's "opened_since is None" guard
    would never fire, so opened_since never refreshed and every subsequent
    is_open call measured age against the stale original timestamp (always
    >= cooldown -> permanently half-open, retried every cycle forever instead
    of getting a fresh cooldown). Clearing state here means the very next
    record_result failure re-opens with a brand-new timestamp, as documented."""
    path = _state_file(state_path)
    lock = _path_lock(path)
    with lock:
        state = _load_state(path)
        entry = state.get(provider)
        if not isinstance(entry, dict):
            return False, None
        opened_since = entry.get("opened_since")
        if opened_since is None:
            return False, None
        try:
            since = float(opened_since)
        except (TypeError, ValueError):
            return False, None
        age = float(now()) - since
        if age >= cooldown_sec:
            # Cooldown elapsed -> half-open. Persist the transition so a subsequent
            # failure can re-open with a FRESH opened_since (see docstring).
            entry["opened_since"] = None
            entry["consecutive_failures"] = 0
            state[provider] = entry
            _save_state(state, path)
            return False, None
        return True, dict(entry)


def filter_providers(
        providers: List[Any], *,
        state_path: Optional[Path] = None,
        now: Callable[[], float] = time.time,
        cooldown_sec: float = DEFAULT_COOLDOWN_SEC,
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """Split *providers* into (kept, skipped) per the circuit-breaker state.
    *kept* preserves input order and is the list to actually dispatch. *skipped*
    is a list of honest metadata dicts (one per skipped provider): {provider,
    reason: SKIPPED_CIRCUIT, since (epoch), last_reason, consecutive_failures}
    -- NEVER silently dropped; callers record this in the board/snapshot
    metadata. A provider whose circuit is not open (or that has never been
    seen) is always kept. Never raises -> (list(providers), [])."""
    try:
        kept: List[Any] = []
        skipped: List[Dict[str, Any]] = []
        for p in (providers or []):
            name = str(getattr(p, "name", getattr(p, "__class__", type(p)).__name__))
            open_now, entry = is_open(name, state_path=state_path, now=now,
                                      cooldown_sec=cooldown_sec)
            if open_now:
                skipped.append({
                    "provider": name,
                    "reason": SKIPPED_REASON_TAG,
                    "since": (entry or {}).get("opened_since"),
                    "last_reason": (entry or {}).get("last_reason", ""),
                    "consecutive_failures": (entry or {}).get("consecutive_failures", 0),
                })
            else:
                kept.append(p)
        return kept, skipped
    except Exception as exc:  # noqa: BLE001 -- filtering must never sink the fetch
        logger.debug("prop_circuit_breaker filter_providers failed: %s", exc)
        return list(providers or []), []


__all__ = [
    "DEFAULT_STATE_PATH", "FAILURE_THRESHOLD", "DEFAULT_COOLDOWN_SEC",
    "SKIPPED_REASON_TAG", "record_result", "is_open", "filter_providers",
]
