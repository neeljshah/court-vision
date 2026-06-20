"""scripts.platformkit.progress.ci_state -- the durable_state builder for the cadence.

Step (B) of the W4 CONTINUOUS-IMPROVEMENT cadence. Reconstructs the per-sport
`durable_state` dict shaped EXACTLY for `schedule_policy.SchedulePolicy.decide(...)`
from the existing READ-ONLY artifacts:

  * improve_ledger.jsonl   -- last recorded verdict per sport (was the last batch
                              INSUFFICIENT/NO_CANDIDATE -> there may be settled work)
  * improvement_backlog.json -- top UNTESTED_DATA item per sport (a pending data
                              point owed a verdict -> settled_pending)
  * data/cache/ingame/*.parquet mtimes -- corpus age per sport (stale -> refresh)

The output keys are a STRICT SUBSET of what `SchedulePolicy._task_for_sport`
consumes: {settled_pending:int, ingame_pending:int, corpus_age_days:float}.

NON-NEGOTIABLE RAILS: MEASUREMENT-ONLY -- reads only; never writes data/registry/,
never flips a flag, never creates the PIPELINE_ENABLED sentinel, never edits
MEMORY.md. Pure given injected paths/clock; a missing input degrades to the
conservative "no work" (all-zero), NEVER raises. NO $ field anywhere; units/
probability only; vs_close UNPROVEN. stdlib-only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Any, Dict, List, Optional, Sequence

_REPO = pathlib.Path(__file__).resolve().parents[3]  # .../nba-ai-system
_IMPROVE_LEDGER = _REPO / "data" / "frontend" / "improve_ledger.jsonl"
_BACKLOG = _REPO / ".planning" / "product" / "meta" / "improvement_backlog.json"
_CORPORA_DIR = _REPO / "data" / "cache" / "ingame"

# Tracked sports (mirrors progress_ledger + schedule_policy defaults).
_SPORTS = ("nba", "mlb", "soccer", "tennis")

# Backlog categories that count as an UNTESTED ingested data-point still owed a
# verdict -> settled_pending. Mirrors progress_ledger._UNTESTED_CATEGORIES.
_UNTESTED_CATEGORIES = ("UNTESTED_DATA", "TIER3_ACQUISITION", "SURFACE_VALIDATED_PRIOR")

# A recorded verdict meaning "the last batch produced no shippable candidate yet,
# so more settled games may unlock one" -> settled_pending stays open.
_PENDING_VERDICTS = ("INSUFFICIENT_DATA", "NO_CANDIDATE", "REPLICATION_PENDING")

# Corpus older than this (days) is STALE -> refresh_corpora. Matches the policy's
# default stale_corpus_days.
STALE_CORPUS_DAYS = 7.0


def _norm_sport(s: Optional[str]) -> Optional[str]:
    if not isinstance(s, str):
        return None
    t = s.strip().lower()
    if t in ("basketball_nba", "nba"):
        return "nba"
    if t in ("soccer_intl", "soccer"):
        return "soccer"
    if t in _SPORTS:
        return t
    return None


def _read_json(path: pathlib.Path) -> Optional[Any]:
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding="ascii", errors="replace")
        return json.loads(raw) if raw.strip() else None
    except Exception:  # noqa: BLE001 -- pure offline read; never raises
        return None


def _read_jsonl(path: pathlib.Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        if not path.exists():
            return out
        for line in path.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(obj, dict):
                out.append(obj)
    except Exception:  # noqa: BLE001
        return out
    return out


def _last_verdict_per_sport(rows: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Map sport -> the LAST recorded verdict (later rows win)."""
    out: Dict[str, str] = {}
    for r in rows:
        sp = _norm_sport(r.get("sport"))
        v = r.get("verdict")
        if sp is not None and isinstance(v, str) and v.strip():
            out[sp] = v.strip().upper()
    return out


def _untested_per_sport(backlog: Optional[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {s: 0 for s in _SPORTS}
    cands = backlog.get("candidates") if isinstance(backlog, dict) else None
    if not isinstance(cands, list):
        return out
    for c in cands:
        if not isinstance(c, dict):
            continue
        if str(c.get("category", "")).upper() not in _UNTESTED_CATEGORIES:
            continue
        sp = _norm_sport(c.get("sport"))
        if sp is not None:
            out[sp] = out.get(sp, 0) + 1
    return out


def _corpus_age_days(sport: str, corpora_dir: pathlib.Path,
                     now_ts: float) -> float:
    """Age (days) of the FRESHEST parquet for `sport`. No file -> 0.0 (no work)."""
    try:
        if not corpora_dir.exists():
            return 0.0
        freshest = -1.0
        for p in corpora_dir.glob("%s*.parquet" % sport):
            try:
                mt = p.stat().st_mtime
            except Exception:  # noqa: BLE001
                continue
            if mt > freshest:
                freshest = mt
        if freshest < 0:
            return 0.0
        return max(0.0, (now_ts - freshest) / 86400.0)
    except Exception:  # noqa: BLE001 -- never raises; conservative no-work
        return 0.0


def build_durable_state(
    now: Optional[float] = None,
    *,
    ledger_path: Optional[pathlib.Path] = None,
    backlog_path: Optional[pathlib.Path] = None,
    corpora_dir: Optional[pathlib.Path] = None,
    sports: Sequence[str] = _SPORTS,
) -> Dict[str, Dict[str, Any]]:
    """Build the per-sport durable_state for schedule_policy.decide. NEVER raises.

    Per sport returns the EXACT keys SchedulePolicy._task_for_sport consumes:
      settled_pending : >0 iff there is an untested backlog item for the sport OR
                        the last recorded verdict was a pending (insufficient) one.
      ingame_pending  : 0 by default (re-gate candidates are surfaced by ci_regate;
                        kept as a 0 placeholder so the shape parity-asserts).
      corpus_age_days : freshest corpus age in days (>= STALE_CORPUS_DAYS -> refresh).

    Missing inputs degrade to all-zero ("no work"), never an exception.
    """
    now_ts = float(now) if now is not None else _dt.datetime.utcnow().timestamp()
    lp = ledger_path or _IMPROVE_LEDGER
    bp = backlog_path or _BACKLOG
    cd = corpora_dir or _CORPORA_DIR

    last_verdict = _last_verdict_per_sport(_read_jsonl(lp))
    untested = _untested_per_sport(_read_json(bp))

    state: Dict[str, Dict[str, Any]] = {}
    for sp in sports:
        n_untested = int(untested.get(sp, 0))
        pending_verdict = last_verdict.get(sp, "") in _PENDING_VERDICTS
        settled_pending = n_untested + (1 if pending_verdict else 0)
        state[sp] = {
            "settled_pending": int(settled_pending),
            "ingame_pending": 0,
            "corpus_age_days": _corpus_age_days(sp, cd, now_ts),
        }
    return state


__all__ = ["build_durable_state", "STALE_CORPUS_DAYS"]
