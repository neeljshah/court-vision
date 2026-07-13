"""clv_quarantine -- reads the mlb_wrong_settle_quarantine.json adjudication
block and returns the flagged bet_id set to exclude from CLV aggregates.

Fail-open by design: a missing file, a missing/other adjudication decision, or
malformed json returns an EMPTY set (current unfiltered behavior), never
blocks the scoreboard/reconciler. Read-only -- never touches the quarantine
file (that stays human-gated / audit-owned).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
_QUARANTINE_JSON = os.path.join(
    _REPO, "data", "frontend", "ops", "mlb_wrong_settle_quarantine.json")


def quarantined_bet_ids(path: Optional[str] = None) -> Set[str]:
    """bet_ids to EXCLUDE from aggregates, IFF the file's adjudication.decision
    is 'EXCLUDE-FROM-AGGREGATES'. No/other adjudication or malformed json ->
    empty set (fail-open to current behavior); malformed prints a warning."""
    try:
        with open(path or _QUARANTINE_JSON, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print("(quarantine file unreadable, not applied: %s)" % type(exc).__name__)
        return set()
    try:
        if data.get("adjudication", {}).get("decision") != "EXCLUDE-FROM-AGGREGATES":
            return set()
        return {str(f["bet_id"]) for f in data.get("flags", []) if f.get("bet_id")}
    except (AttributeError, TypeError) as exc:
        print("(quarantine file malformed, not applied: %s)" % type(exc).__name__)
        return set()


def split_quarantined(rows: Sequence[Dict[str, Any]],
                       quarantined: Set[str]) -> Tuple[List[Dict[str, Any]], int]:
    """(kept, n_excluded) -- rows whose bet_id is in `quarantined` are dropped
    but counted, never silently vanished."""
    if not quarantined:
        return list(rows), 0
    kept: List[Dict[str, Any]] = []
    n = 0
    for r in rows:
        if str(r.get("bet_id") or "") in quarantined:
            n += 1
        else:
            kept.append(r)
    return kept, n
