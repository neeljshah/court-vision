"""backfill_2025_26_gamelogs.py — backfill per-player gamelogs for the
CURRENT season in the exact filename + schema that
`scripts/build_prediction_cache.py` (R16_E3) expects.

The R16_E3 prediction-cache builder reads
    data/nba/gamelog_<player_id>_<season>.json
with UPPERCASE keys (PTS / REB / AST / MIN / GAME_DATE / MATCHUP / FG3M / STL /
BLK / TOV).  Only 5 players had that exact file for 2025-26 prior to this
backfill, so the live prediction cache had to fall back to 2024-25 form.

This script:
  1. Builds the active-player union:
       - all 30 NBA teams' current rosters (CommonTeamRoster, season=2025-26),
         including SAS and OKC (tonight's slate)
       - every player_id with a `gamelog_full_*_2025-26.json` (the existing
         lowercase-schema scrape — these ARE the prop_pergame model space)
       - every player_id with a `gamelog_full_*_2024-25.json` (still-active
         carryover that may not have re-scraped yet for 2025-26)
  2. For each player_id in that union, fetches PlayerGameLog for the current
     season — Regular Season AND Playoffs — merges, writes the merged list
     to `data/nba/gamelog_<pid>_2025-26.json` with UPPERCASE keys.
  3. Rate-limits 0.6s between calls, backs off to 1.5s on 429.
  4. Probes results to data/cache/probe_R17_J8_gamelog_backfill_results.json.

Reusable: pass `--season 2026-27` next year and it just works.

Usage:
    python scripts/backfill_2025_26_gamelogs.py
    python scripts/backfill_2025_26_gamelogs.py --season 2025-26 --limit 50
    python scripts/backfill_2025_26_gamelogs.py --skip-existing-nonempty
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
os.makedirs(_NBA_DIR, exist_ok=True)
os.makedirs(_CACHE_DIR, exist_ok=True)

# Fields the R16_E3 reader inspects (uppercase)
_KEEP_UPPER = [
    "GAME_ID", "GAME_DATE", "MATCHUP", "WL", "MIN",
    "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT",
    "FTM", "FTA", "FT_PCT", "OREB", "DREB", "REB",
    "AST", "STL", "BLK", "TOV", "PF", "PTS", "PLUS_MINUS",
    "PLAYER_ID", "SEASON_ID",
]

_DEFAULT_SLEEP = 0.6
_BACKOFF_SLEEP = 1.5


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


def _row_to_upper(row: dict) -> dict:
    """Normalise a PlayerGameLog row to uppercase keys + MIN as float."""
    out = {}
    for k, v in row.items():
        uk = k.upper()
        out[uk] = v
    if "MIN" in out:
        out["MIN"] = _parse_min(out["MIN"])
    return out


def _team_ids() -> List[int]:
    from nba_api.stats.static import teams as _teams
    return [int(t["id"]) for t in _teams.get_teams()]


def _fetch_team_roster_pids(team_id: int, season: str) -> List[int]:
    from nba_api.stats.endpoints import commonteamroster
    df = commonteamroster.CommonTeamRoster(
        team_id=team_id, season=season, timeout=60
    ).get_data_frames()[0]
    pids = []
    for _, row in df.iterrows():
        try:
            pids.append(int(row.get("PLAYER_ID")))
        except (TypeError, ValueError):
            continue
    return pids


def _existing_modelspace_pids() -> Set[int]:
    """player_ids present in any historical gamelog_full_*_<season>.json — they
    are the prop_pergame model space (model was trained on rows from these
    files)."""
    pids: Set[int] = set()
    if not os.path.isdir(_NBA_DIR):
        return pids
    for f in os.listdir(_NBA_DIR):
        if not f.startswith("gamelog_full_"):
            continue
        if not f.endswith(".json"):
            continue
        try:
            mid = f[len("gamelog_full_"): -len(".json")]
            pid_str = mid.rsplit("_", 1)[0]
            pids.add(int(pid_str))
        except (ValueError, IndexError):
            continue
    return pids


def _build_active_pid_universe(season: str) -> Tuple[Set[int], Dict[str, List[int]]]:
    """Build the union (active rosters + prop_pergame model space)."""
    team_ids = _team_ids()
    print(f"[universe] fetching {len(team_ids)} team rosters for {season}...", flush=True)
    roster_pids: Set[int] = set()
    roster_per_team: Dict[str, List[int]] = {}
    from nba_api.stats.static import teams as _teams
    id_to_abbr = {int(t["id"]): t["abbreviation"] for t in _teams.get_teams()}
    for tid in team_ids:
        abbr = id_to_abbr[tid]
        time.sleep(_DEFAULT_SLEEP)
        try:
            pids = _fetch_team_roster_pids(tid, season)
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                print(f"  [429] roster {abbr} — backing off 1.5s", flush=True)
                time.sleep(_BACKOFF_SLEEP)
                try:
                    pids = _fetch_team_roster_pids(tid, season)
                except Exception as e2:
                    print(f"  [SKIP] roster {abbr}: {e2}", flush=True)
                    continue
            else:
                print(f"  [SKIP] roster {abbr}: {e}", flush=True)
                continue
        roster_per_team[abbr] = pids
        roster_pids.update(pids)
        print(f"  {abbr}: {len(pids)} players", flush=True)

    model_pids = _existing_modelspace_pids()
    union = roster_pids | model_pids
    print(
        f"[universe] active-roster={len(roster_pids)}  "
        f"prop_pergame_modelspace={len(model_pids)}  "
        f"union={len(union)}",
        flush=True,
    )
    return union, roster_per_team


def _fetch_player_gamelog(pid: int, season: str, season_type: str) -> List[dict]:
    """One PlayerGameLog call. Returns raw rows (lowercase or capitalised
    columns from nba_api, we normalise outside)."""
    from nba_api.stats.endpoints import playergamelog
    df = playergamelog.PlayerGameLog(
        player_id=pid,
        season=season,
        season_type_all_star=season_type,
        timeout=60,
    ).get_data_frames()[0]
    return df.to_dict(orient="records")


def _fetch_full_player_season(pid: int, season: str) -> List[dict]:
    """Regular + Playoffs merged, uppercase keys, sorted by GAME_DATE asc."""
    rows: List[dict] = []
    for stype in ("Regular Season", "Playoffs"):
        time.sleep(_DEFAULT_SLEEP)
        try:
            chunk = _fetch_player_gamelog(pid, season, stype)
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                time.sleep(_BACKOFF_SLEEP)
                try:
                    chunk = _fetch_player_gamelog(pid, season, stype)
                except Exception as e2:
                    print(f"    [SKIP] pid={pid} {stype}: {e2}", flush=True)
                    continue
            else:
                # Playoffs missing for early-season is fine; only warn for RS.
                if stype == "Regular Season":
                    print(f"    [WARN] pid={pid} {stype}: {e}", flush=True)
                continue
        for r in chunk:
            rows.append(_row_to_upper(r))
    # Sort by GAME_DATE if parseable; nba_api returns date strings like
    # "APR 12, 2026" / "2026-04-12" — both parse with a small loop.
    def _key(r):
        d = r.get("GAME_DATE")
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(d).strip(), fmt)
            except (ValueError, TypeError):
                continue
        return datetime.min
    rows.sort(key=_key)
    return rows


def _validate_player(pid: int, label: str, season: str) -> Dict[str, float]:
    """Spot-check: load the written file, compute L5/L10 PTS/REB/AST means."""
    path = os.path.join(_NBA_DIR, f"gamelog_{pid}_{season}.json")
    if not os.path.exists(path):
        return {"label": label, "pid": pid, "status": "missing_file"}
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        return {"label": label, "pid": pid, "status": f"unreadable:{e}"}
    if not isinstance(rows, list) or not rows:
        return {"label": label, "pid": pid, "status": "empty", "n_games": 0}
    # rows are sorted ascending — take last 10 as most-recent
    last10 = rows[-10:]
    last5 = rows[-5:]
    def _mean(lst, k):
        vals = [float(r.get(k, 0) or 0) for r in lst]
        return round(sum(vals) / max(1, len(vals)), 2)
    return {
        "label": label,
        "pid": pid,
        "status": "ok",
        "n_games": len(rows),
        "latest_game_date": rows[-1].get("GAME_DATE"),
        "latest_matchup": rows[-1].get("MATCHUP"),
        "L5_pts": _mean(last5, "PTS"),
        "L5_reb": _mean(last5, "REB"),
        "L5_ast": _mean(last5, "AST"),
        "L10_pts": _mean(last10, "PTS"),
        "L10_reb": _mean(last10, "REB"),
        "L10_ast": _mean(last10, "AST"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None,
                    help="Season string, e.g. 2025-26. Defaults to current.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limit number of players (smoke test).")
    ap.add_argument("--skip-existing-nonempty", action="store_true",
                    help="Skip players whose target file already has >= 1 row.")
    ap.add_argument("--probe-out", default=os.path.join(
        _CACHE_DIR, "probe_R17_J8_gamelog_backfill_results.json"))
    args = ap.parse_args()

    season = args.season or _detect_current_season()
    print(f"[backfill] target season = {season}", flush=True)

    union, roster_per_team = _build_active_pid_universe(season)
    pid_list = sorted(union)
    if args.limit is not None:
        pid_list = pid_list[: args.limit]
        print(f"[backfill] limit applied: {len(pid_list)} players", flush=True)

    t0 = time.time()
    n_done = 0
    n_nonempty = 0
    n_zero = 0
    n_skipped = 0
    n_errors = 0

    for i, pid in enumerate(pid_list, start=1):
        out_path = os.path.join(_NBA_DIR, f"gamelog_{pid}_{season}.json")
        if args.skip_existing_nonempty and os.path.exists(out_path):
            try:
                existing = json.load(open(out_path, encoding="utf-8"))
                if isinstance(existing, list) and existing:
                    n_skipped += 1
                    continue
            except Exception:
                pass

        try:
            rows = _fetch_full_player_season(pid, season)
        except Exception as e:
            print(f"  [ERR] pid={pid}: {e}", flush=True)
            n_errors += 1
            continue

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(rows, f)
        except Exception as e:
            print(f"  [WRITE_ERR] pid={pid}: {e}", flush=True)
            n_errors += 1
            continue

        n_done += 1
        if rows:
            n_nonempty += 1
        else:
            n_zero += 1

        if i % 25 == 0:
            elapsed = time.time() - t0
            rate = i / max(1e-6, elapsed)
            eta = (len(pid_list) - i) / max(1e-6, rate)
            print(
                f"  [{i}/{len(pid_list)}] done={n_done} nonempty={n_nonempty} "
                f"zero={n_zero} skipped={n_skipped} err={n_errors} "
                f"rate={rate:.2f}/s eta={eta:.0f}s",
                flush=True,
            )

    elapsed = time.time() - t0
    print(
        f"[backfill] DONE in {elapsed:.1f}s — "
        f"done={n_done} nonempty={n_nonempty} zero={n_zero} "
        f"skipped={n_skipped} err={n_errors}",
        flush=True,
    )

    # Spot-check sample validation
    sample_pids = {
        "Shai Gilgeous-Alexander": 1628983,
        "Victor Wembanyama": 1641705,
        "Keldon Johnson": 1629640,
    }
    sample_validation = [
        _validate_player(pid, name, season) for name, pid in sample_pids.items()
    ]
    for s in sample_validation:
        print(f"  [validate] {s}", flush=True)

    probe = {
        "probe": "R17_J8_gamelog_backfill",
        "ran_at": datetime.utcnow().isoformat() + "Z",
        "season": season,
        "n_players_universe": len(union),
        "n_players_attempted": len(pid_list),
        "n_players_backfilled": n_done,
        "n_gamelogs_with_data": n_nonempty,
        "n_zero_games": n_zero,
        "n_skipped_existing": n_skipped,
        "n_errors": n_errors,
        "elapsed_seconds": round(elapsed, 1),
        "rosters_per_team": {k: len(v) for k, v in roster_per_team.items()},
        "sample_validation": sample_validation,
        "prediction_cache_regenerated": False,  # filled by orchestrator step
    }
    with open(args.probe_out, "w", encoding="utf-8") as f:
        json.dump(probe, f, indent=2, default=str)
    print(f"[backfill] probe -> {args.probe_out}", flush=True)


if __name__ == "__main__":
    main()
