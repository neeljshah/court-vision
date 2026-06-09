"""refresh_playoff_team_gamelogs.py — refresh gamelogs for ALL 2026 playoff
teams (so the system is current on day 1, not just for OKC/SAS).

Identifies 2026 playoff teams from data/nba/season_games_2025-26.json (rows
whose game_id starts with '0042' — NBA's playoffs prefix) and, for each team
NOT already refreshed (OKC + SAS were handled by refresh_okc_sas_gamelogs.py),
pulls the CommonTeamRoster and refreshes each rostered player's gamelog
(Regular Season + Playoffs) via the same helpers that
refresh_active_gamelogs.py already exposes.

Reuses _team_abbr_to_id, _fetch_roster_pids, refresh_player, _is_fresh from
the existing module. The <2h freshness guard auto-skips OKC/SAS players.

Usage:
    python scripts/refresh_playoff_team_gamelogs.py
    python scripts/refresh_playoff_team_gamelogs.py --dry-run
    python scripts/refresh_playoff_team_gamelogs.py --force

Pace: 0.6s between API calls (same as refresh_active_gamelogs).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Set

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Reuse all the logic from refresh_active_gamelogs
from scripts.refresh_active_gamelogs import (  # noqa: E402
    _NBA_DIR,
    _detect_current_season,
    _team_abbr_to_id,
    _fetch_roster_pids,
    refresh_player,
    _is_fresh,
)

_SKIP_TEAMS = {"OKC", "SAS"}  # already refreshed via refresh_okc_sas_gamelogs.py


def _load_playoff_teams(season: str) -> Set[str]:
    """Return set of team abbrs that played in 2026 playoffs."""
    path = os.path.join(_NBA_DIR, f"season_games_{season}.json")
    if not os.path.exists(path):
        print(f"[error] season_games file missing: {path}", flush=True)
        return set()
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload["rows"] if isinstance(payload, dict) else payload
    teams: Set[str] = set()
    for r in rows:
        gid = str(r.get("game_id") or "")
        # NBA playoffs: game_id prefix '0042'
        if not gid.startswith("0042"):
            continue
        h = (r.get("home_team") or "").strip()
        a = (r.get("away_team") or "").strip()
        if h:
            teams.add(h)
        if a:
            teams.add(a)
    return teams


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None,
                    help="Season override (default: current)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't fetch — just print teams + roster counts")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch even if file is fresh (<2h old)")
    args = ap.parse_args()

    season = args.season or _detect_current_season()
    print(f"[playoff-refresh] season={season}", flush=True)

    all_playoff = _load_playoff_teams(season)
    print(f"[playoff-refresh] all 2026 playoff teams ({len(all_playoff)}): "
          f"{sorted(all_playoff)}", flush=True)

    targets = sorted(all_playoff - _SKIP_TEAMS)
    print(f"[playoff-refresh] target teams (excluding {sorted(_SKIP_TEAMS)}): "
          f"{len(targets)}", flush=True)
    print(f"[playoff-refresh] {targets}", flush=True)

    if not targets:
        print("[playoff-refresh] nothing to do.", flush=True)
        return 0

    abbr_to_id = _team_abbr_to_id()
    rosters: Dict[str, List[int]] = {}
    for abbr in targets:
        tid = abbr_to_id.get(abbr)
        if tid is None:
            print(f"  [warn] unknown team abbr: {abbr}", flush=True)
            continue
        pids = _fetch_roster_pids(tid, season)
        # Top-10 only per the task spec
        rosters[abbr] = pids[:10]
        print(f"  [roster] {abbr}: {len(pids)} on roster -> using top "
              f"{len(rosters[abbr])}", flush=True)

    all_pids: Set[int] = set()
    for pids in rosters.values():
        all_pids.update(pids)
    print(f"[playoff-refresh] unique players to refresh: {len(all_pids)}",
          flush=True)

    if args.dry_run:
        print("[dry-run] would refresh gamelogs — exiting.", flush=True)
        return 0

    t0 = time.time()
    n_ok = 0
    n_skip_fresh = 0
    n_err = 0
    per_player: Dict[int, int] = {}
    for pid in sorted(all_pids):
        if not args.force and _is_fresh(pid, season):
            n_skip_fresh += 1
            continue
        try:
            n = refresh_player(pid, season)
            per_player[pid] = n
            n_ok += 1
            print(f"  [{pid}] {n} rows", flush=True)
        except Exception as e:
            n_err += 1
            print(f"  [{pid}] ERR: {e}", flush=True)

    elapsed = time.time() - t0
    print(f"[playoff-refresh] DONE in {elapsed:.1f}s  ok={n_ok}  "
          f"skipped_fresh={n_skip_fresh}  err={n_err}", flush=True)

    out = {
        "refreshed_at": datetime.utcnow().isoformat() + "Z",
        "season": season,
        "elapsed_sec": round(elapsed, 1),
        "all_playoff_teams": sorted(all_playoff),
        "target_teams": targets,
        "skipped_teams": sorted(_SKIP_TEAMS),
        "rosters_top10": {k: v for k, v in rosters.items()},
        "n_unique_players": len(all_pids),
        "n_ok": n_ok,
        "n_skipped_fresh": n_skip_fresh,
        "n_err": n_err,
        "per_player_rows": per_player,
    }
    out_dir = os.path.join(PROJECT_DIR, "data", "cache")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d")
    out_path = os.path.join(out_dir,
                            f"refresh_playoff_team_gamelogs_{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"[playoff-refresh] report -> {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
