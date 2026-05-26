"""probe_R28_U1_played_games.py — verifies the R28_U1 played-games linescore backfill.

Reports per-season counts of rows before/after, stub counts before/after, the
number of stubs replaced with real per-quarter data, the count of brand-new
rows added, and cross-references against ``season_games_<season>.json``
completion to flag any remaining gaps.

Read-only — does NOT call the NBA API. Just diffs the current
``data/nba/linescores_all.json`` against the ``.bak_R28_U1`` sidecar the
backfill wrote on entry. Persists output to
``data/cache/probe_R28_U1_results.json`` (worktree-local so concurrent
agents don't clobber each other).

Ship gates:
  - SHIP: stubs_replaced_total >= 100 AND no schema regression
  - PARTIAL: 1 <= stubs_replaced_total < 100 (API rate-limited)
  - REJECT: stubs_replaced_total == 0 OR older-season counts drifted
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
BAK_PATH = LS_PATH + ".bak_R28_U1"
RESULTS_PATH = os.path.join(WORKTREE_DIR, "data", "cache",
                            "probe_R28_U1_results.json")

# Schedule files — prefer worktree-local then root.
SG_TMPL = [
    os.path.join(WORKTREE_DIR, "data", "nba", "season_games_{season}.json"),
    os.path.join(ROOT_DIR, "data", "nba", "season_games_{season}.json"),
]

_LEGACY_KEYS = {
    "home_q1", "home_q2", "home_q3", "home_q4",
    "away_q1", "away_q2", "away_q3", "away_q4",
    "home_h1", "away_h1", "h1_total", "home_team_id",
}

_TARGET_SEASONS = ("2024-25", "2025-26")


def _season_prefix(gid: str) -> str:
    try:
        yy = int(gid[3:5])
        return f"20{yy:02d}-{(yy + 1) % 100:02d}"
    except Exception:
        return "unk"


def _is_stub(row) -> bool:
    if not isinstance(row, dict):
        return True
    s = 0
    for side in ("home", "away"):
        for i in range(1, 5):
            try:
                s += int(row.get(f"{side}_q{i}", 0) or 0)
            except (TypeError, ValueError):
                pass
    return s == 0


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d if isinstance(d, dict) else {}


def _load_schedule(season: str) -> list:
    for tmpl in SG_TMPL:
        p = tmpl.format(season=season)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            return d.get("rows", d) if isinstance(d, dict) else d
    return []


def _season_breakdown(payload: dict, season: str):
    rows = {k: v for k, v in payload.items()
            if _season_prefix(k) == season}
    stubs = sum(1 for v in rows.values() if _is_stub(v))
    real = len(rows) - stubs
    return len(rows), stubs, real


def main() -> None:
    after = _load(LS_PATH)
    before = _load(BAK_PATH)

    c_after = Counter(_season_prefix(k) for k in after.keys())
    c_before = Counter(_season_prefix(k) for k in before.keys())

    # Per-season breakdown (stub vs real, before vs after).
    per_season = {}
    stubs_replaced_total = 0
    new_rows_total = 0
    for season in _TARGET_SEASONS:
        rows_b, stubs_b, real_b = _season_breakdown(before, season)
        rows_a, stubs_a, real_a = _season_breakdown(after, season)
        stubs_replaced = max(0, stubs_b - stubs_a)
        new_rows = max(0, rows_a - rows_b)
        # Cross-ref against schedule.
        sched = _load_schedule(season)
        completed = sum(1 for r in sched
                        if str(r.get("game_date", "")) <= "2026-05-25")
        gids_in_ls = set(k for k in after if _season_prefix(k) == season)
        sched_gids = set(str(r.get("game_id", "")) for r in sched if r.get("game_id"))
        missing_vs_schedule = len(sched_gids - gids_in_ls)
        per_season[season] = {
            "rows_before": rows_b,
            "rows_after": rows_a,
            "stubs_before": stubs_b,
            "stubs_after": stubs_a,
            "real_before": real_b,
            "real_after": real_a,
            "stubs_replaced": stubs_replaced,
            "new_rows_added": new_rows,
            "schedule_completed_games": completed,
            "schedule_total_games": len(sched),
            "missing_vs_schedule": missing_vs_schedule,
        }
        stubs_replaced_total += stubs_replaced
        new_rows_total += new_rows

    # Schema check: every 2024-25/2025-26 row carries legacy keys.
    rows_recent = {k: v for k, v in after.items()
                   if _season_prefix(k) in _TARGET_SEASONS}
    bad_schema = sum(
        1 for v in rows_recent.values()
        if not isinstance(v, dict) or not _LEGACY_KEYS.issubset(v.keys())
    )

    # OT coverage across recent seasons.
    ot_count = sum(
        1 for v in rows_recent.values()
        if isinstance(v, dict) and int(v.get("had_ot", 0) or 0) == 1
    )

    # Older-season parity (pre-2024-25 must be untouched).
    older_drift = {}
    for season, n in c_before.items():
        if season in _TARGET_SEASONS:
            continue
        if c_after.get(season, 0) != n:
            older_drift[season] = {
                "before": n, "after": c_after.get(season, 0),
            }

    if stubs_replaced_total == 0 and new_rows_total == 0:
        decision = "REJECT"
        reason = "zero stubs replaced and zero new rows added"
    elif older_drift:
        decision = "REJECT"
        reason = f"older-season counts drifted: {older_drift}"
    elif stubs_replaced_total >= 100 and bad_schema == 0:
        decision = "SHIP"
        reason = (f"replaced {stubs_replaced_total} stubs + added "
                  f"{new_rows_total} new rows, schema clean, {ot_count} OT")
    else:
        decision = "PARTIAL"
        reason = (f"replaced {stubs_replaced_total} stubs (< 100 ship gate) "
                  f"+ added {new_rows_total} new rows; bad_schema={bad_schema}")

    payload = {
        "probe": "R28_U1_played_games_backfill",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "ls_path": LS_PATH,
        "bak_path": BAK_PATH,
        "rows_before_total": len(before),
        "rows_after_total": len(after),
        "stubs_replaced_total": stubs_replaced_total,
        "new_rows_added_total": new_rows_total,
        "per_season": per_season,
        "by_season_after": dict(sorted(c_after.items())),
        "by_season_before": dict(sorted(c_before.items())),
        "ot_games_recent": ot_count,
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
