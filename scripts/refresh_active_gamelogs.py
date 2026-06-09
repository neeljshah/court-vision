"""refresh_active_gamelogs.py — nightly gamelog refresh for tomorrow's slate.

Generalization of refresh_okc_sas_gamelogs.py from "21 OKC+SAS players" to
"all rostered players on any team playing tomorrow."

Pipeline:
  1. Read tomorrow's scheduled games from data/nba/season_games_<season>.json
     — rows with scheduled=True and game_date == tomorrow.
  2. For each unique team playing tomorrow, fetch the current-season roster
     via CommonTeamRoster.
  3. For each rostered player, pull PlayerGameLog (RS + Playoffs), merge,
     dedupe by GAME_ID, and write BOTH schema variants:
       - data/nba/gamelog_<pid>_<season>.json       (UPPERCASE keys, ASC)
       - data/nba/gamelog_full_<pid>_<season>.json  (lowercase keys, DESC)
  4. Backup previous file mtime; skip refresh if file was written <2h ago
     and --force not passed (rate-limit protection on retries).

Reuses logic from refresh_okc_sas_gamelogs.py — DRY.

Usage:
    python scripts/refresh_active_gamelogs.py
    python scripts/refresh_active_gamelogs.py --date 2026-05-27
    python scripts/refresh_active_gamelogs.py --season 2025-26 --dry-run
    python scripts/refresh_active_gamelogs.py --force        # ignore mtime guard
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, date as _date
from typing import Dict, List, Set

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

try:
    import src.data.nba_api_headers_patch  # noqa: F401
except Exception as _e:
    print(f"[warn] no headers patch: {_e}", flush=True)

_NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_BACKUP_DIR = os.path.join(PROJECT_DIR, "data", "backups", "gamelogs")
_SLEEP = 0.6
_BACKOFF = 5.0
_FRESH_HOURS = 2.0  # skip refresh if file written within this window


def _detect_current_season() -> str:
    now = datetime.now()
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _parse_min(m) -> float:
    try:
        if isinstance(m, str) and ":" in m:
            p = m.split(":")
            return round(float(p[0]) + float(p[1]) / 60.0, 2)
        return round(float(m), 2)
    except (ValueError, TypeError):
        return 0.0


def _date_key(d) -> datetime:
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(d).strip(), fmt)
        except (ValueError, TypeError):
            continue
    return datetime.min


def _load_season_games(season: str) -> List[dict]:
    path = os.path.join(_NBA_DIR, f"season_games_{season}.json")
    if not os.path.exists(path):
        print(f"[error] season_games file missing: {path}", flush=True)
        return []
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload["rows"] if isinstance(payload, dict) else payload


def _teams_playing_on(rows: List[dict], target_date: str) -> Set[str]:
    teams: Set[str] = set()
    for r in rows:
        if str(r.get("game_date")) != target_date:
            continue
        # Treat as scheduled if scheduled is True OR if date is in the future.
        sched = r.get("scheduled")
        if sched is False:
            continue
        h = (r.get("home_team") or "").strip()
        a = (r.get("away_team") or "").strip()
        if h:
            teams.add(h)
        if a:
            teams.add(a)
    return teams


def _team_abbr_to_id() -> Dict[str, int]:
    from nba_api.stats.static import teams as _teams
    return {t["abbreviation"]: int(t["id"]) for t in _teams.get_teams()}


def _fetch_roster_pids(team_id: int, season: str) -> List[int]:
    from nba_api.stats.endpoints import commonteamroster
    try:
        time.sleep(_SLEEP)
        df = commonteamroster.CommonTeamRoster(
            team_id=team_id, season=season, timeout=60,
        ).get_data_frames()[0]
    except Exception as e:
        err = str(e)
        if "429" in err or "rate" in err.lower():
            print(f"  [429] roster team_id={team_id} — backing off {_BACKOFF}s",
                  flush=True)
            time.sleep(_BACKOFF)
            df = commonteamroster.CommonTeamRoster(
                team_id=team_id, season=season, timeout=60,
            ).get_data_frames()[0]
        else:
            print(f"  [warn] roster team_id={team_id}: {e}", flush=True)
            return []
    pids: List[int] = []
    for _, row in df.iterrows():
        try:
            pids.append(int(row.get("PLAYER_ID")))
        except (TypeError, ValueError):
            continue
    return pids


def _fetch_gamelog(pid: int, season: str, stype: str) -> List[dict]:
    from nba_api.stats.endpoints import playergamelog
    try:
        df = playergamelog.PlayerGameLog(
            player_id=pid, season=season,
            season_type_all_star=stype, timeout=60,
        ).get_data_frames()[0]
        return df.to_dict(orient="records")
    except Exception as e:
        err = str(e)
        if "429" in err or "rate" in err.lower():
            print(f"    [429] pid={pid} {stype} — backing off {_BACKOFF}s",
                  flush=True)
            time.sleep(_BACKOFF)
            try:
                df = playergamelog.PlayerGameLog(
                    player_id=pid, season=season,
                    season_type_all_star=stype, timeout=60,
                ).get_data_frames()[0]
                return df.to_dict(orient="records")
            except Exception as e2:
                print(f"    [SKIP] pid={pid} {stype}: {e2}", flush=True)
                return []
        else:
            if stype == "Regular Season":
                print(f"    [WARN] pid={pid} {stype}: {e}", flush=True)
            return []


def _normalise_rows(raw: List[dict]) -> List[dict]:
    out = []
    for r in raw:
        upper = {k.upper(): v for k, v in r.items()}
        if "MIN" in upper:
            upper["MIN"] = _parse_min(upper["MIN"])
        out.append(upper)
    return out


def _backup(path: str) -> None:
    if not os.path.exists(path):
        return
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    base = os.path.basename(path)
    dst = os.path.join(_BACKUP_DIR, f"{base}.{stamp}.bak")
    try:
        shutil.copy2(path, dst)
    except OSError as e:
        print(f"    [warn] backup failed for {path}: {e}", flush=True)


def _write_both_schemas(pid: int, season: str, rows: List[dict]) -> int:
    asc = sorted(rows, key=lambda r: _date_key(r.get("GAME_DATE")))
    upper_path = os.path.join(_NBA_DIR, f"gamelog_{pid}_{season}.json")
    full_path = os.path.join(_NBA_DIR, f"gamelog_full_{pid}_{season}.json")
    _backup(upper_path)
    _backup(full_path)
    with open(upper_path, "w", encoding="utf-8") as f:
        json.dump(asc, f)
    desc = list(reversed(asc))
    lower_desc = [{k.lower(): v for k, v in r.items()} for r in desc]
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(lower_desc, f)
    return len(asc)


def _is_fresh(pid: int, season: str) -> bool:
    """Skip players whose UPPERCASE file is younger than _FRESH_HOURS."""
    path = os.path.join(_NBA_DIR, f"gamelog_{pid}_{season}.json")
    if not os.path.exists(path):
        return False
    age_hr = (time.time() - os.path.getmtime(path)) / 3600.0
    return age_hr < _FRESH_HOURS


def refresh_player(pid: int, season: str) -> int:
    all_rows: List[dict] = []
    for stype in ("Regular Season", "Playoffs"):
        time.sleep(_SLEEP)
        chunk = _fetch_gamelog(pid, season, stype)
        chunk = _normalise_rows(chunk)
        all_rows.extend(chunk)
    seen = set()
    deduped = []
    for r in all_rows:
        gid = r.get("GAME_ID")
        if gid in seen:
            continue
        seen.add(gid)
        deduped.append(r)
    return _write_both_schemas(pid, season, deduped)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None,
                    help="Season override (default: current)")
    ap.add_argument("--date", default=None,
                    help="Target date YYYY-MM-DD (default: tomorrow local)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't fetch — just print teams + roster counts")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch even if file is fresh (<2h old)")
    args = ap.parse_args()

    season = args.season or _detect_current_season()
    target_date = args.date or (_date.today() + timedelta(days=1)).isoformat()
    print(f"[refresh] season={season}  target_date={target_date}", flush=True)

    rows = _load_season_games(season)
    if not rows:
        print(f"[error] no season_games rows for {season}", flush=True)
        return 1

    teams = _teams_playing_on(rows, target_date)
    print(f"[refresh] teams playing on {target_date}: "
          f"{sorted(teams) or '(none)'}", flush=True)
    if not teams:
        print(f"[refresh] no games scheduled for {target_date}; "
              f"nothing to do.", flush=True)
        return 0

    abbr_to_id = _team_abbr_to_id()
    rosters: Dict[str, List[int]] = {}
    for abbr in sorted(teams):
        tid = abbr_to_id.get(abbr)
        if tid is None:
            print(f"  [warn] unknown team abbr: {abbr}", flush=True)
            continue
        pids = _fetch_roster_pids(tid, season)
        rosters[abbr] = pids
        print(f"  [roster] {abbr}: {len(pids)} players", flush=True)

    all_pids: Set[int] = set()
    for pids in rosters.values():
        all_pids.update(pids)
    print(f"[refresh] unique players to refresh: {len(all_pids)}", flush=True)

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
    print(f"[refresh] DONE in {elapsed:.1f}s  ok={n_ok}  "
          f"skipped_fresh={n_skip_fresh}  err={n_err}", flush=True)

    out = {
        "refreshed_at": datetime.utcnow().isoformat() + "Z",
        "season": season,
        "target_date": target_date,
        "teams": sorted(teams),
        "n_unique_players": len(all_pids),
        "n_ok": n_ok,
        "n_skipped_fresh": n_skip_fresh,
        "n_err": n_err,
        "per_player_rows": per_player,
    }
    out_dir = os.path.join(PROJECT_DIR, "data", "cache")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d")
    out_path = os.path.join(out_dir, f"refresh_active_gamelogs_{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"[refresh] report -> {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
