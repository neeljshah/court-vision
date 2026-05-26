"""backfill_linescores_2025_26.py — R26_S2 linescores backfill.

Fills in missing 2025-26 game-result linescores in
``data/nba/linescores_all.json`` so that the m2_family retraining loop and
related WinProb/OT probes have a real 2025-26 holdout to score against.

Per R24_Q3 diagnostic, only 3 of 1230 scheduled 2025-26 games had linescore
records at the time this probe was written.

Source: NBA stats endpoint ``BoxScoreSummaryV2`` — dataset index 5 is
``LineScore`` with one row per team per game (TEAM_ID, TEAM_ABBREVIATION,
PTS_QTR1..PTS_QTR4, PTS_OT1..PTS_OT10 if applicable, PTS).
Existing rows in linescores_all.json carry ONLY q1..q4 + h1 + h1_total +
home_team_id, so we match that schema exactly and stash the OT regulation
overflow under ``had_ot`` / ``home_pts_ot`` / ``away_pts_ot`` for future
consumers (existing readers ignore unknown keys).

Atomic write: each batch of `_BATCH_SAVE_EVERY` successful fetches is flushed
to disk under a `.tmp` sidecar then renamed onto the canonical path, so a
crash mid-run never leaves the file half-written. The original file is
backed up once at startup to `<path>.bak_R26_S2`.

Wallclock budget: hard cap via `--max-minutes` so the orchestrating agent
can ship PARTIAL when the NBA API stalls or rate-limits.

Run:
    python scripts/backfill_linescores_2025_26.py --max-minutes 15
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Worktrees keep data/ shared with the root checkout but the canonical
# linescores_all.json lives at the repository root. Resolve both so the
# script runs identically from worktrees and from root.
def _resolve_root() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "nba")) else PROJECT_DIR


ROOT_DIR = _resolve_root()
DATA_NBA = os.path.join(ROOT_DIR, "data", "nba")
LS_PATH = os.path.join(DATA_NBA, "linescores_all.json")
BAK_PATH = LS_PATH + ".bak_R26_S2"

# Pull this season's schedule from whichever worktree carries it (the agent's
# worktree copy is canonical for this run).
SG_CANDIDATES = [
    os.path.join(PROJECT_DIR, "data", "nba", "season_games_2025-26.json"),
    os.path.join(DATA_NBA, "season_games_2025-26.json"),
]

_SLEEP_S = 0.6
_BATCH_SAVE_EVERY = 25


def _patch_nba_api_headers() -> None:
    """stats.nba.com rejects default urllib3 user-agents — patch them in."""
    try:
        from src.data import nba_api_headers_patch  # noqa: F401
    except Exception as exc:  # pragma: no cover - best-effort
        print(f"  [warn] header patch import failed: {exc}", flush=True)


def _load_schedule() -> List[dict]:
    for p in SG_CANDIDATES:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            return d.get("rows", d) if isinstance(d, dict) else d
    raise FileNotFoundError(
        "season_games_2025-26.json not found in worktree or root data/nba"
    )


def _load_linescores() -> Dict[str, dict]:
    if not os.path.exists(LS_PATH):
        return {}
    with open(LS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _atomic_write(payload: Dict[str, dict]) -> None:
    tmp = LS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp, LS_PATH)


def _fetch_one(game_id: str) -> Optional[dict]:
    """Returns the linescore dict for one game, or None on failure / not-found.

    Schema matches the existing 2025-26 'pbp' source rows:
        home_q1..q4, away_q1..q4, home_h1, away_h1, h1_total, home_team_id,
        source='boxscoresummaryv2'
    Adds OT carryover fields (had_ot, home_pts_ot, away_pts_ot) which are
    ignored by all existing readers (which select fixed keys) but preserve
    full-game truth for future consumers.
    """
    from nba_api.stats.endpoints.boxscoresummaryv2 import BoxScoreSummaryV2

    bs = BoxScoreSummaryV2(game_id=game_id, timeout=30)
    frames = bs.get_data_frames()
    if len(frames) < 6:
        return None
    ls_df = frames[5]  # LineScore
    if ls_df.empty or len(ls_df) < 2:
        return None
    gh = frames[0]  # GameSummary — has HOME_TEAM_ID / VISITOR_TEAM_ID
    if gh.empty:
        return None
    home_team_id = int(gh.iloc[0]["HOME_TEAM_ID"])
    # Identify which LineScore row is home vs visitor via TEAM_ID.
    home_row = ls_df[ls_df["TEAM_ID"].astype(int) == home_team_id]
    away_row = ls_df[ls_df["TEAM_ID"].astype(int) != home_team_id]
    if home_row.empty or away_row.empty:
        return None
    h = home_row.iloc[0]
    a = away_row.iloc[0]

    def _q(row, col: str) -> int:
        v = row.get(col)
        try:
            return int(v) if v is not None and v == v else 0  # NaN guard
        except (TypeError, ValueError):
            return 0

    home_q = [_q(h, f"PTS_QTR{i}") for i in range(1, 5)]
    away_q = [_q(a, f"PTS_QTR{i}") for i in range(1, 5)]
    # OT carryover (kept for future consumers; existing readers ignore)
    home_ot = sum(_q(h, f"PTS_OT{i}") for i in range(1, 11))
    away_ot = sum(_q(a, f"PTS_OT{i}") for i in range(1, 11))
    home_h1 = home_q[0] + home_q[1]
    away_h1 = away_q[0] + away_q[1]
    return {
        "home_q1": home_q[0], "home_q2": home_q[1],
        "home_q3": home_q[2], "home_q4": home_q[3],
        "away_q1": away_q[0], "away_q2": away_q[1],
        "away_q3": away_q[2], "away_q4": away_q[3],
        "home_h1": home_h1,
        "away_h1": away_h1,
        "h1_total": home_h1 + away_h1,
        "home_team_id": home_team_id,
        "had_ot": int((home_ot + away_ot) > 0),
        "home_pts_ot": home_ot,
        "away_pts_ot": away_ot,
        "source": "boxscoresummaryv2",
    }


def _missing_completed(schedule: List[dict], existing: Dict[str, dict],
                        cutoff_date: str) -> List[str]:
    """Game ids for completed-but-missing 2025-26 games, sorted by date asc."""
    by_date: List[Tuple[str, str]] = []
    for r in schedule:
        gid = str(r.get("game_id", ""))
        if not gid or gid in existing:
            continue
        gd = r.get("game_date", "")
        if not gd or gd > cutoff_date:
            continue
        by_date.append((gd, gid))
    by_date.sort()
    return [gid for _, gid in by_date]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=15.0,
                    help="Hard wallclock cap before stopping and shipping partial.")
    ap.add_argument("--cutoff-date", type=str, default="2026-05-25",
                    help="Only fetch games on or before this date (YYYY-MM-DD).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Optional cap on number of API calls (0 = no cap).")
    args = ap.parse_args()

    _patch_nba_api_headers()
    schedule = _load_schedule()
    existing = _load_linescores()
    print(f"linescores_all.json: {len(existing)} rows loaded from {LS_PATH}",
          flush=True)

    missing = _missing_completed(schedule, existing, args.cutoff_date)
    print(f"Missing completed 2025-26 games (<= {args.cutoff_date}): "
          f"{len(missing)}", flush=True)
    if args.limit:
        missing = missing[: args.limit]
        print(f"Capping to {len(missing)} (--limit)", flush=True)

    if not os.path.exists(BAK_PATH):
        shutil.copy2(LS_PATH, BAK_PATH)
        print(f"Backup written: {BAK_PATH}", flush=True)

    payload = dict(existing)
    deadline = time.time() + args.max_minutes * 60.0
    n_added = 0
    n_errors = 0
    n_not_found = 0
    t0 = time.time()

    for i, gid in enumerate(missing):
        if time.time() > deadline:
            print(f"  [wallclock] {args.max_minutes:.1f}min cap reached at "
                  f"{i}/{len(missing)} — flushing and exiting partial",
                  flush=True)
            break
        try:
            row = _fetch_one(gid)
        except Exception as exc:
            n_errors += 1
            msg = str(exc)[:80]
            if i < 3 or i % 100 == 0:
                print(f"  [err {i}] {gid}: {msg}", flush=True)
            time.sleep(_SLEEP_S)
            continue
        if row is None:
            n_not_found += 1
            time.sleep(_SLEEP_S)
            continue
        payload[gid] = row
        n_added += 1
        if n_added % _BATCH_SAVE_EVERY == 0:
            _atomic_write(payload)
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(missing)}] added={n_added} errors={n_errors} "
                  f"not_found={n_not_found} elapsed={elapsed/60.0:.1f}min",
                  flush=True)
        time.sleep(_SLEEP_S)

    _atomic_write(payload)
    elapsed_min = (time.time() - t0) / 60.0
    print()
    print(f"DONE — added={n_added} errors={n_errors} not_found={n_not_found} "
          f"runtime={elapsed_min:.1f}min", flush=True)
    print(f"linescores_all.json now has {len(payload)} rows", flush=True)
    # Summary by season for the orchestrator's probe to pick up.
    from collections import Counter
    by_season = Counter()
    for k in payload.keys():
        try:
            yy = int(k[3:5])
            by_season[f"20{yy:02d}-{(yy+1)%100:02d}"] += 1
        except Exception:
            by_season["unk"] += 1
    for s, n in sorted(by_season.items()):
        print(f"  {s}: {n}", flush=True)


if __name__ == "__main__":
    main()
