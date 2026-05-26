"""probe_R26_S2_linescores_backfill.py — verifies the 2025-26 linescores backfill.

Reports row counts before/after, per-season distribution, OT coverage, and a
ship/partial/reject decision based on the wired ship gates from the R26_S2
brief:

  - SHIP: rows_added_2025_26 >= 50 AND no schema regression
  - PARTIAL: rows_added_2025_26 between 1 and 49 (NBA API partially blocked)
  - REJECT: rows_added_2025_26 == 0 OR pre-2025-26 row count changed

The probe is read-only — it does NOT call NBA API; it just diffs the current
``data/nba/linescores_all.json`` against the ``.bak_R26_S2`` snapshot the
backfill writes on entry. Persists results to
``data/cache/probe_R26_S2_results.json`` (worktree-local so concurrent
agents do not clobber each other).
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

PROBE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKTREE_DIR = os.path.dirname(os.path.dirname(PROBE_DIR))
sys.path.insert(0, WORKTREE_DIR)


def _resolve_root() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "nba")) else WORKTREE_DIR


ROOT_DIR = _resolve_root()
LS_PATH = os.path.join(ROOT_DIR, "data", "nba", "linescores_all.json")
BAK_PATH = LS_PATH + ".bak_R26_S2"
RESULTS_PATH = os.path.join(WORKTREE_DIR, "data", "cache", "probe_R26_S2_results.json")

_LEGACY_KEYS = {
    "home_q1", "home_q2", "home_q3", "home_q4",
    "away_q1", "away_q2", "away_q3", "away_q4",
    "home_h1", "away_h1", "h1_total", "home_team_id",
}


def _season_prefix(gid: str) -> str:
    try:
        yy = int(gid[3:5])
        return f"20{yy:02d}-{(yy + 1) % 100:02d}"
    except Exception:
        return "unk"


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d if isinstance(d, dict) else {}


def main() -> None:
    after = _load(LS_PATH)
    before = _load(BAK_PATH)

    c_after = Counter(_season_prefix(k) for k in after.keys())
    c_before = Counter(_season_prefix(k) for k in before.keys())

    added_2025_26 = c_after.get("2025-26", 0) - c_before.get("2025-26", 0)

    # Schema check: every 2025-26 row carries legacy keys.
    rows_25 = {k: v for k, v in after.items() if _season_prefix(k) == "2025-26"}
    bad_schema = sum(
        1 for v in rows_25.values()
        if not isinstance(v, dict) or not _LEGACY_KEYS.issubset(v.keys())
    )

    # OT coverage among the freshly added rows.
    ot_count = sum(
        1 for v in rows_25.values()
        if isinstance(v, dict) and int(v.get("had_ot", 0) or 0) == 1
    )

    # Older-season parity check.
    older_drift = {}
    for season, n in c_before.items():
        if season == "2025-26":
            continue
        if c_after.get(season, 0) != n:
            older_drift[season] = {
                "before": n, "after": c_after.get(season, 0)
            }

    if added_2025_26 == 0 or older_drift:
        decision = "REJECT"
        reason = ("zero 2025-26 rows added" if added_2025_26 == 0
                  else f"older-season counts drifted: {older_drift}")
    elif added_2025_26 >= 50 and bad_schema == 0:
        decision = "SHIP"
        reason = (f"added {added_2025_26} 2025-26 linescores, schema clean, "
                  f"{ot_count} OT games tagged")
    else:
        decision = "PARTIAL"
        reason = (f"added {added_2025_26} rows (< 50 ship gate) or schema "
                  f"warnings ({bad_schema})")

    payload = {
        "probe": "R26_S2_linescores_backfill",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "ls_path": LS_PATH,
        "bak_path": BAK_PATH,
        "rows_before": len(before),
        "rows_after": len(after),
        "rows_added_total": len(after) - len(before),
        "rows_added_2025_26": added_2025_26,
        "rows_2025_26_after": c_after.get("2025-26", 0),
        "rows_2025_26_before": c_before.get("2025-26", 0),
        "by_season_after": dict(sorted(c_after.items())),
        "by_season_before": dict(sorted(c_before.items())),
        "ot_games_in_2025_26": ot_count,
        "bad_schema_rows": bad_schema,
        "older_season_drift": older_drift,
        "decision": decision,
        "reason": reason,
    }

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
