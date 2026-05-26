"""backfill_linescores_played_games.py — R28_U1 played-games linescore backfill.

Fixes the R26_S2 data blockage: most 2025-26 linescore records in
``data/nba/linescores_all.json`` are BoxScoreSummaryV2 stubs with q1..q4 == 0
because that endpoint returns NULL periods for many regular-season games.
Only 29 of 1006 stored 2025-26 records have real per-quarter scores; 2024-25
only has 376 of 1225 games entirely (849 missing).

This backfill switches to the **CDN static boxscore JSON**
(``https://cdn.nba.com/static/json/liveData/boxscore/boxscore_<gid>.json``)
which returns authoritative per-period scores for every played NBA game
(verified against regular and double-OT games). The response is a single
JSON object per game with ``game.homeTeam.periods`` and
``game.awayTeam.periods`` lists, each item ``{period, periodType, score}``.

Schema matches the legacy ``home_q1..q4 / away_q1..q4 / home_h1 / away_h1 /
h1_total / home_team_id`` fields consumed by m2_family training and the OT
probe. New fields ``had_ot``, ``home_pts_ot``, ``away_pts_ot``, ``source``
follow the R26_S2 convention.

Behavior:
  - Walks both 2024-25 and 2025-26 schedules.
  - For each game, fetches ONLY if existing row is missing OR sum of
    q1..q4 across home+away == 0 (stub). Real rows are never re-fetched.
  - Rate-limit 0.6s between requests. Hard wallclock cap via
    ``--max-minutes`` (default 30).
  - Atomic write per batch (tmp + rename) and one-shot backup to
    ``.bak_R28_U1`` on entry.
  - Handles 403 (game not yet played / never released) gracefully — skips.

Run:
    python scripts/backfill_linescores_played_games.py --max-minutes 30
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from typing import Dict, List, Optional, Tuple

import requests

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def _resolve_root() -> str:
    """Return the canonical repo root (linescores live in a single shared file)."""
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "nba")) else PROJECT_DIR


ROOT_DIR = _resolve_root()
DATA_NBA = os.path.join(ROOT_DIR, "data", "nba")
LS_PATH = os.path.join(DATA_NBA, "linescores_all.json")
BAK_PATH = LS_PATH + ".bak_R28_U1"

# Schedule files — prefer worktree-local copy if present, fall back to root.
SG_CANDIDATES_TMPL = [
    os.path.join(PROJECT_DIR, "data", "nba", "season_games_{season}.json"),
    os.path.join(DATA_NBA, "season_games_{season}.json"),
]

_SEASONS = ("2024-25", "2025-26")
_SLEEP_S = 0.6
_BATCH_SAVE_EVERY = 25
_CDN_TMPL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{gid}.json"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Accept-Language": "en-US,en;q=0.9",
}


def _load_schedule(season: str) -> List[dict]:
    """Load season_games_<season>.json rows from whichever path exists."""
    for tmpl in SG_CANDIDATES_TMPL:
        p = tmpl.format(season=season)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            return d.get("rows", d) if isinstance(d, dict) else d
    raise FileNotFoundError(
        f"season_games_{season}.json not found in worktree or root data/nba"
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


def _is_stub(row: Optional[dict]) -> bool:
    """A row is a stub if missing OR sum of all q1..q4 (home+away) == 0."""
    if not isinstance(row, dict):
        return True
    q_sum = 0
    for side in ("home", "away"):
        for i in range(1, 5):
            try:
                q_sum += int(row.get(f"{side}_q{i}", 0) or 0)
            except (TypeError, ValueError):
                pass
    return q_sum == 0


def fetch_one(game_id: str, session: Optional[requests.Session] = None,
              timeout: int = 30) -> Optional[dict]:
    """Fetch the CDN boxscore JSON for one game; parse into legacy linescore row.

    Returns None on 403 / 404 / non-JSON / unplayed / malformed response.
    """
    url = _CDN_TMPL.format(gid=game_id)
    sess = session or requests
    try:
        r = sess.get(url, headers=_HEADERS, timeout=timeout)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except Exception:
        return None
    g = data.get("game") or {}
    home = g.get("homeTeam") or {}
    away = g.get("awayTeam") or {}
    home_periods = home.get("periods") or []
    away_periods = away.get("periods") or []
    if len(home_periods) < 4 or len(away_periods) < 4:
        # Game not played yet or malformed response.
        return None

    def _period_score(periods: list, period_num: int) -> int:
        for p in periods:
            try:
                if int(p.get("period", 0)) == period_num:
                    return int(p.get("score", 0) or 0)
            except (TypeError, ValueError):
                continue
        return 0

    home_q = [_period_score(home_periods, i) for i in range(1, 5)]
    away_q = [_period_score(away_periods, i) for i in range(1, 5)]
    # OT carryover: any period > 4 (regulation in NBA is 4 quarters of 12min).
    home_ot = sum(
        int(p.get("score", 0) or 0)
        for p in home_periods
        if (lambda v: isinstance(v, int) and v > 4)(
            int(p.get("period", 0)) if str(p.get("period", "")).isdigit() else 0
        )
    )
    away_ot = sum(
        int(p.get("score", 0) or 0)
        for p in away_periods
        if (lambda v: isinstance(v, int) and v > 4)(
            int(p.get("period", 0)) if str(p.get("period", "")).isdigit() else 0
        )
    )
    home_h1 = home_q[0] + home_q[1]
    away_h1 = away_q[0] + away_q[1]
    try:
        home_team_id = int(home.get("teamId", 0) or 0) or None
    except (TypeError, ValueError):
        home_team_id = None

    # Plausibility guard: per-team regulation total must be > 0 to avoid storing
    # a hollow record. (A real NBA quarter is never 0/0/0/0 for both sides.)
    if sum(home_q) == 0 and sum(away_q) == 0:
        return None

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
        "source": "cdn_boxscore",
    }


def _targets(schedule: List[dict], existing: Dict[str, dict],
             cutoff_date: str) -> List[str]:
    """Game ids that need fetching: missing OR existing row is a stub.

    Sorted by game_date ascending so a partial run still covers earliest
    holdout dates first (better than randomly leaving gaps).
    """
    pending: List[Tuple[str, str]] = []
    for r in schedule:
        gid = str(r.get("game_id", "") or "")
        if not gid:
            continue
        gd = str(r.get("game_date", "") or "")
        if not gd or gd > cutoff_date:
            continue
        if not _is_stub(existing.get(gid)):
            continue
        pending.append((gd, gid))
    pending.sort()
    return [gid for _, gid in pending]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=30.0,
                    help="Hard wallclock cap before flushing and exiting.")
    ap.add_argument("--cutoff-date", type=str, default="2026-05-25",
                    help="Only fetch games on/before this date (YYYY-MM-DD).")
    ap.add_argument("--limit", type=int, default=0,
                    help="Optional cap on number of API calls (0 = no cap).")
    ap.add_argument("--seasons", type=str, default=",".join(_SEASONS),
                    help="Comma-separated seasons to process.")
    args = ap.parse_args()

    seasons = [s.strip() for s in args.seasons.split(",") if s.strip()]
    existing = _load_linescores()
    print(f"linescores_all.json: {len(existing)} rows loaded from {LS_PATH}",
          flush=True)

    # Build target list prioritizing the data blockage that triggered R28_U1:
    # 1) 2025-26 STUB replacements (the original R27_T1 blockage)
    # 2) 2025-26 brand-new missing rows
    # 3) Other seasons (2024-25 etc) — newly missing rows
    # Within each priority band, date-ascending.
    priority_replace: List[Tuple[str, str]] = []  # 2025-26 stubs
    priority_new_2025: List[Tuple[str, str]] = []  # 2025-26 brand new
    other_new: List[Tuple[str, str]] = []  # 2024-25 etc

    for season in seasons:
        try:
            sched = _load_schedule(season)
        except FileNotFoundError as exc:
            print(f"  [warn] {exc} — skipping {season}", flush=True)
            continue
        gids = set(_targets(sched, existing, args.cutoff_date))
        print(f"  {season}: {len(gids)} games need fetch "
              f"(missing or stub, <= {args.cutoff_date})", flush=True)
        for r in sched:
            gid = str(r.get("game_id", "") or "")
            if gid not in gids:
                continue
            gd = str(r.get("game_date", "") or "")
            is_present = gid in existing
            if season == "2025-26" and is_present:
                priority_replace.append((gd, gid))
            elif season == "2025-26":
                priority_new_2025.append((gd, gid))
            else:
                other_new.append((gd, gid))
    priority_replace.sort()
    priority_new_2025.sort()
    other_new.sort()
    ordered = (
        [gid for _, gid in priority_replace]
        + [gid for _, gid in priority_new_2025]
        + [gid for _, gid in other_new]
    )
    print(f"  priority: replace_2025_26_stubs={len(priority_replace)} "
          f"new_2025_26={len(priority_new_2025)} "
          f"other_new={len(other_new)}", flush=True)
    if args.limit:
        ordered = ordered[: args.limit]
        print(f"Capping to {len(ordered)} (--limit)", flush=True)
    print(f"TOTAL targets: {len(ordered)}", flush=True)

    if not os.path.exists(BAK_PATH):
        shutil.copy2(LS_PATH, BAK_PATH)
        print(f"Backup written: {BAK_PATH}", flush=True)

    payload = dict(existing)
    deadline = time.time() + args.max_minutes * 60.0
    n_replaced = 0    # was a stub, now real
    n_new = 0         # didn't exist before
    n_errors = 0
    n_not_found = 0
    t0 = time.time()
    session = requests.Session()

    for i, gid in enumerate(ordered):
        if time.time() > deadline:
            print(f"  [wallclock] {args.max_minutes:.1f}min cap reached at "
                  f"{i}/{len(ordered)} — flushing partial",
                  flush=True)
            break
        was_present = gid in payload
        try:
            row = fetch_one(gid, session=session)
        except Exception as exc:
            n_errors += 1
            if i < 3 or i % 100 == 0:
                print(f"  [err {i}] {gid}: {str(exc)[:80]}", flush=True)
            time.sleep(_SLEEP_S)
            continue
        if row is None:
            n_not_found += 1
            time.sleep(_SLEEP_S)
            continue
        payload[gid] = row
        if was_present:
            n_replaced += 1
        else:
            n_new += 1
        if (n_replaced + n_new) % _BATCH_SAVE_EVERY == 0:
            _atomic_write(payload)
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(ordered)}] replaced={n_replaced} new={n_new} "
                  f"errors={n_errors} not_found={n_not_found} "
                  f"elapsed={elapsed/60.0:.1f}min", flush=True)
        time.sleep(_SLEEP_S)

    _atomic_write(payload)
    elapsed_min = (time.time() - t0) / 60.0
    print()
    print(f"DONE — replaced={n_replaced} new={n_new} errors={n_errors} "
          f"not_found={n_not_found} runtime={elapsed_min:.1f}min", flush=True)
    print(f"linescores_all.json now has {len(payload)} rows", flush=True)


if __name__ == "__main__":
    main()
