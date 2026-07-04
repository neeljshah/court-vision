"""scripts.platformkit.autonomy.post_restart_readiness_checks -- RESTART-READINESS
LANE 3 additive extension to the post-`boot.ps1` verifier: 6 activations waves
15/17/18/20 shipped that need the pending m2/supervisor bounce to run under NEW code:

  (k) grade-writer frac-clamp (mlb_live_model._FRAC_CEIL, wave-15): fresh mlb grade
      row at/past bottom-9th still has non-null model_prob. PENDING without a live
      mlb game at/past bottom-9th (only state exercising the old saturation bug).
  (l) Kalshi 429 pacing counters (kalshi_pacing.py, wave-17): capture heartbeat
      (data/cache/ingame_grade/_capture_heartbeat.json) carries n_requests_total/
      n_429_total. PENDING if heartbeat predates restart (old code never wrote
      these -- pre-restart absence is honest baseline, not a defect).
  (m) enrichment persistence into grade rows (wave-18): fresh grade row (any
      capture sport) carries >=1 additive enrichment key via the `extra=` merge.
      PENDING without a live game/fresh row.
  (n) sidecar retention (sidecar_retention.py, m37, wave-18): DEFAULT_POLICY is
      well-formed and dry-run plan_dir succeeds for every policy (read-only PLAN,
      never enforce -- must never move a file). No PENDING branch -- pure
      code-shape check, independent of restart/live-game state.
  (o) supervisor beat-thread + 300s watchdog + boot_initiator stamp (wave-17/18):
      supervisor_status.json carries non-null boot_initiator (proves NEW code
      ran; OLD supervisor never wrote this) AND updated_at fresher than the 300s
      watchdog threshold. PENDING if the status doc predates the restart.
  (p) npb/kbo live-state bridge (npb_kbo_live_state.py, wave-20): bridge module
      imports + its dispatch table covers both sports (pure code-shape check --
      no network call; schedule existence is not this verifier's job).

Mirrors post_restart_capture_checks.py / post_restart_enrichment_checks.py's pattern
EXACTLY (same PASS/FAIL/PENDING vocabulary, same injectable-everything discipline).
Read-only: no flag flip, no data/registry/ write, no PID touched, no file moved.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_post_restart_readiness_checks.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.autonomy.post_restart_checks import FAIL, PASS, PENDING, read_json, row

_REPO = Path(__file__).resolve().parents[3]
_INGAME_GRADE = _REPO / "data" / "cache" / "ingame_grade"
_CAPTURE_HEARTBEAT = _INGAME_GRADE / "_capture_heartbeat.json"
_OPS = _REPO / "data" / "frontend" / "ops"

# The additive enrichment keys inplay_capture_loop._enrichment_fields() always emits
# (mirrors post_restart_enrichment_checks.ENRICHMENT_KEYS; duplicated here as a plain
# tuple so this module has no import-time dependency on that sibling's internals).
_ENRICHMENT_KEYS = (
    "xg_home", "xg_away", "xg_asof_min", "spread_bp", "book_thinness",
    "stale_quote", "espn_wp", "espn_event_id",
)

# 300s watchdog threshold (wave-18 supervisor fix: heartbeat_reaper's new threshold).
_WATCHDOG_THRESHOLD_SEC = 300.0


def _newest_grade_row(sport: str) -> Any:
    """Last JSON line of the freshest grade file for *sport*, or None. Never raises."""
    sport_dir = _INGAME_GRADE / sport
    try:
        if not sport_dir.is_dir():
            return None
        files = sorted(sport_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime,
                       reverse=True)
        if not files:
            return None
        last_line = None
        with files[0].open("r", encoding="ascii", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last_line = line
        if last_line is None:
            return None
        parsed = json.loads(last_line)
        return parsed if isinstance(parsed, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _mtime_of(sport: str) -> Optional[float]:
    sport_dir = _INGAME_GRADE / sport
    try:
        if not sport_dir.is_dir():
            return None
        files = list(sport_dir.glob("*.jsonl"))
        if not files:
            return None
        return max(f.stat().st_mtime for f in files)
    except Exception:  # noqa: BLE001
        return None


def check_grade_writer_clamp(now: float, *, live_game_fn: Callable[[str], bool],
                             fresh_sec: float = 1800.0) -> Dict[str, Any]:
    """(k) a fresh mlb grade row at/past the bottom of the 9th still has a
    non-null model_prob (the old bug returned None forever from there on)."""
    name = "grade_writer_frac_clamp_mlb"
    try:
        live = bool(live_game_fn("mlb"))
    except Exception as exc:  # noqa: BLE001
        return row(name, PENDING, "live-game lookup raised %s" % type(exc).__name__)
    if not live:
        return row(name, PENDING, "no live mlb game right now")
    mtime = _mtime_of("mlb")
    if mtime is None:
        return row(name, PENDING, "live game but no readable grade row yet")
    if now - mtime > fresh_sec:
        return row(name, PENDING, "newest grade row %.0fs old (>%.0fs) -- stale"
                   % (now - mtime, fresh_sec))
    parsed = _newest_grade_row("mlb")
    if parsed is None:
        return row(name, PENDING, "live game but no readable grade row yet")
    summary = str(parsed.get("state_summary") or "")
    inning = None
    for token in summary.replace(",", " ").split():
        if token.startswith("inning="):
            try:
                inning = int(token.split("=", 1)[1])
            except ValueError:
                inning = None
            break
    if inning is None or inning < 9:
        return row(name, PENDING,
                   "no bottom-9th-or-later tick yet this game (inning=%s) -- the "
                   "clamp's saturation branch is not exercised before inning 9"
                   % inning)
    if parsed.get("model_prob") is not None:
        return row(name, PASS,
                   "inning=%d tick carries model_prob=%r (clamp fix live -- old bug "
                   "would have returned None from here on)" % (inning, parsed.get("model_prob")))
    return row(name, FAIL,
               "inning=%d tick has model_prob=None (frac-clamp regression -- the "
               "wave-14/15 bug is back)" % inning)


def check_kalshi_pacing_counters(restart_ts: float) -> Dict[str, Any]:
    """(l) the capture heartbeat carries the n_requests_total/n_429_total pacing
    counters (wave-17 fix). PENDING (not FAIL) if the heartbeat predates the
    restart -- old code never wrote these keys, so pre-restart absence is
    honestly expected, not a defect."""
    name = "kalshi_pacing_counters"
    doc = read_json(_CAPTURE_HEARTBEAT)
    if doc is None:
        return row(name, PENDING, "capture heartbeat missing/unreadable "
                   "(data/cache/ingame_grade/_capture_heartbeat.json)")
    try:
        mtime = _CAPTURE_HEARTBEAT.stat().st_mtime
    except Exception:  # noqa: BLE001
        mtime = None
    has_both = "n_requests_total" in doc and "n_429_total" in doc
    if has_both:
        return row(name, PASS,
                   "capture heartbeat carries n_requests_total=%r n_429_total=%r"
                   % (doc.get("n_requests_total"), doc.get("n_429_total")))
    if mtime is not None and mtime < restart_ts:
        return row(name, PENDING,
                   "capture heartbeat predates restart (old pre-fix code -- counters "
                   "honestly absent until the next tick under the new code)")
    return row(name, FAIL,
               "capture heartbeat is POST-restart but missing n_requests_total/"
               "n_429_total (pacing fix did not activate)")


def check_enrichment_persistence(now: float, *, live_game_fn: Callable[[str], bool],
                                 sports: Optional[List[str]] = None,
                                 fresh_sec: float = 1800.0) -> Dict[str, Any]:
    """(m) a fresh grade row for ANY live capture sport carries at least one
    additive enrichment key (proves the extra= merge path landed in a real
    row, not just the capture-loop's own in-memory dict)."""
    name = "enrichment_persisted_in_grade_rows"
    check_sports = sports if sports is not None else [
        "mlb", "wnba", "soccer_intl", "tennis", "npb", "kbo", "nba", "soccer"]
    any_live = False
    for sport in check_sports:
        try:
            live = bool(live_game_fn(sport))
        except Exception:  # noqa: BLE001
            live = False
        if not live:
            continue
        any_live = True
        mtime = _mtime_of(sport)
        if mtime is None or now - mtime > fresh_sec:
            continue
        parsed = _newest_grade_row(sport)
        if not isinstance(parsed, dict):
            continue
        present = [k for k in _ENRICHMENT_KEYS if k in parsed]
        if present:
            return row(name, PASS,
                       "%s fresh grade row carries enrichment keys: %s"
                       % (sport, present))
    if not any_live:
        return row(name, PENDING, "no live game right now (any capture sport)")
    return row(name, PENDING,
               "live game(s) but no fresh grade row yet carried an enrichment key "
               "(honest PENDING -- could also mean this game predates the persistence "
               "wire; not conclusive enough to FAIL on absence alone)")


def check_sidecar_retention() -> Dict[str, Any]:
    """(n) sidecar_retention.DEFAULT_POLICY is well-formed and every policy's
    plan_dir (read-only; never enforces) computes without raising. No PENDING
    branch -- this is a pure code-shape check, independent of any live-game or
    restart-timing state."""
    name = "sidecar_retention_plan"
    try:
        from scripts.platformkit.ingame.sidecar_retention import DEFAULT_POLICY, plan_dir
    except Exception as exc:  # noqa: BLE001
        return row(name, FAIL, "import raised %s" % type(exc).__name__)
    if not DEFAULT_POLICY:
        return row(name, FAIL, "DEFAULT_POLICY is empty")
    errors: List[str] = []
    n_ok = 0
    for policy in DEFAULT_POLICY:
        try:
            plan = plan_dir(policy)
            if not isinstance(plan, dict):
                errors.append("%s: plan_dir returned non-dict" % policy.dir)
                continue
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            errors.append("%s: plan_dir raised %s" % (policy.dir, type(exc).__name__))
    if errors:
        return row(name, FAIL, "plan_dir failed for %d/%d policies: %s"
                   % (len(errors), len(DEFAULT_POLICY), errors[:3]))
    return row(name, PASS,
               "%d/%d sidecar policies plan cleanly (dry-run only, nothing moved)"
               % (n_ok, len(DEFAULT_POLICY)))


def check_supervisor_beat_thread(now: float, restart_ts_val: float) -> Dict[str, Any]:
    """(o) boot_initiator stamped (proves the NEW supervisor code path ran) +
    updated_at fresher than the 300s watchdog threshold. PENDING if the status
    doc itself predates the restart (a stale pre-restart artifact -- the OLD
    supervisor never stamped boot_initiator at all, so its honest absence there
    is expected, not a defect)."""
    name = "supervisor_beat_thread"
    doc = read_json(_OPS / "supervisor_status.json")
    if doc is None:
        return row(name, PENDING, "supervisor_status.json missing/unreadable")
    try:
        mtime = (_OPS / "supervisor_status.json").stat().st_mtime
    except Exception:  # noqa: BLE001
        mtime = None
    if mtime is not None and mtime < restart_ts_val:
        return row(name, PENDING,
                   "supervisor_status.json predates the restart (pre-fix code never "
                   "stamped boot_initiator -- honest gap, not a FAIL)")
    initiator = doc.get("boot_initiator")
    updated_at = doc.get("updated_at")
    if initiator is None:
        return row(name, FAIL,
                   "post-restart supervisor_status.json missing boot_initiator "
                   "(beat-thread fix did not activate)")
    if not isinstance(updated_at, (int, float)):
        return row(name, FAIL, "updated_at missing/unparseable in supervisor_status.json")
    age = now - float(updated_at)
    if age > _WATCHDOG_THRESHOLD_SEC:
        return row(name, FAIL,
                   "boot_initiator=%r stamped, but updated_at is %.0fs stale "
                   "(> %.0fs watchdog threshold -- beat thread may have died)"
                   % (initiator, age, _WATCHDOG_THRESHOLD_SEC))
    return row(name, PASS,
               "boot_initiator=%r stamped, updated_at %.0fs old (<= %.0fs watchdog "
               "threshold)" % (initiator, age, _WATCHDOG_THRESHOLD_SEC))


def check_npb_kbo_live_state_bridge() -> Dict[str, Any]:
    """(p) npb_kbo_live_state's dispatch table covers both sports (pure
    code-shape check; no network call -- schedule existence is not this
    verifier's job)."""
    name = "npb_kbo_live_state_bridge"
    try:
        from scripts.platformkit.ingame.npb_kbo_live_state import _DISPATCH
        from scripts.platformkit.ingame.ingame_live_state import _NON_ESPN_SPORTS
    except Exception as exc:  # noqa: BLE001
        return row(name, FAIL, "import raised %s" % type(exc).__name__)
    missing_dispatch = sorted(s for s in ("npb", "kbo") if s not in _DISPATCH)
    missing_bridge = sorted(s for s in ("npb", "kbo") if s not in _NON_ESPN_SPORTS)
    if missing_dispatch or missing_bridge:
        return row(name, FAIL,
                   "bridge incomplete: missing_dispatch=%s missing_non_espn_sports=%s"
                   % (missing_dispatch, missing_bridge))
    return row(name, PASS,
               "npb+kbo both in npb_kbo_live_state._DISPATCH and "
               "ingame_live_state._NON_ESPN_SPORTS (grading unblocked, activates at "
               "daemon restart per wave-20)")


__all__ = [
    "check_grade_writer_clamp", "check_kalshi_pacing_counters",
    "check_enrichment_persistence", "check_sidecar_retention",
    "check_supervisor_beat_thread", "check_npb_kbo_live_state_bridge",
]
