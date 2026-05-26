"""backfill_lineups_2025_26.py — R31_X6 backfill of 2025-26 5-man lineup data.

Background
----------
The drift detector (R27_T3) flags `home_top_lineup_net_rtg` and
`away_top_lineup_net_rtg` as MAJOR drift because only 2 of 30 teams (LAL, GSW)
had 2025-26 lineup files cached locally; the other 28 teams returned the
default 0.0 from `_get_top_lineup_net_rtg`.

This script fetches the missing lineup data via NBA Stats
`leaguedashlineups` (Advanced / Per100Possessions / 5-man) and writes one
JSON file per team under `data/nba/lineups/lineup_splits_<TEAM>_2025-26.json`.

Two strategies:

1. **bulk** (default, fastest, single API call): pull all teams in one
   `leaguedashlineups` request, split by team_abbreviation, write one file
   per team. Falls back to per-team if bulk fails (timeouts, missing
   col, ...).
2. **per_team**: iterate the 30 NBA teams; for each missing team issue a
   `team_id_nullable=<tid>` request, write the file. Rate-limited at 0.7s
   between calls.

Resilient to 429/403 with exponential backoff.

Idempotency: files that already exist are skipped (unless --force).

After backfilling, run `scripts/feature_drift_detector.py` to confirm
`top_lineup_net_rtg` drops out of the major-drift list. (Note: that
requires `season_games_2025-26.json` to be regenerated through
backfill_pregame_features_2025_26.py or the drift detector will still
see 0.0s in the cached column — see `--patch-season-games` flag.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

_LINEUPS_DIR = PROJECT_DIR / "data" / "nba" / "lineups"
_SEASON_GAMES_PATH = PROJECT_DIR / "data" / "nba" / "season_games_2025-26.json"

_ALL_TEAMS = [
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
]

_API_DELAY_S = 0.7  # rate-limit between per-team calls
_BACKOFF_INITIAL_S = 5.0
_BACKOFF_FACTOR = 2.0
_BACKOFF_MAX_RETRIES = 4

SEASON = "2025-26"


def _ensure_dir() -> None:
    _LINEUPS_DIR.mkdir(parents=True, exist_ok=True)


def _team_file(team: str, season: str = SEASON) -> Path:
    return _LINEUPS_DIR / f"lineup_splits_{team}_{season}.json"


def existing_teams(season: str = SEASON) -> List[str]:
    """Return list of team abbreviations with a 2025-26 lineup file."""
    _ensure_dir()
    found = []
    for t in _ALL_TEAMS:
        if _team_file(t, season).exists():
            found.append(t)
    return found


def missing_teams(season: str = SEASON) -> List[str]:
    have = set(existing_teams(season))
    return [t for t in _ALL_TEAMS if t not in have]


# --------------------------------------------------------------------------- #
# Row normalization                                                            #
# --------------------------------------------------------------------------- #
def _normalize_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a leaguedashlineups row into the schema get_top_lineups expects.

    The expected reader (`src.data.lineup_data.get_top_lineups`) looks at
    `lineup` (list[str]), `minutes` (float), and `net_rating` (float).
    """
    group_name = raw.get("GROUP_NAME", "") or raw.get("group_name", "")
    players = [p.strip() for p in str(group_name).split(" - ") if p.strip()]
    return {
        "lineup":      players,
        "minutes":     float(raw.get("MIN", raw.get("min", 0)) or 0),
        "net_rating":  float(raw.get("NET_RATING", raw.get("net_rating", 0)) or 0),
        "off_rating":  float(raw.get("OFF_RATING", raw.get("off_rating", 0)) or 0),
        "def_rating":  float(raw.get("DEF_RATING", raw.get("def_rating", 0)) or 0),
        "pace":        float(raw.get("PACE", raw.get("pace", 0)) or 0),
        "efg_pct":     float(raw.get("EFG_PCT", raw.get("efg_pct", 0)) or 0),
        "tov_pct":     float(raw.get("TM_TOV_PCT", raw.get("tm_tov_pct", 0)) or 0),
        "oreb_pct":    float(raw.get("OREB_PCT", raw.get("oreb_pct", 0)) or 0),
        "ft_rate":     float(raw.get("FTA_RATE", raw.get("fta_rate", 0)) or 0),
        "plus_minus":  float(raw.get("PLUS_MINUS", raw.get("plus_minus", 0)) or 0),
    }


def write_team_lineups_atomic(team: str, lineups: List[Dict[str, Any]],
                              season: str = SEASON) -> Path:
    """Sort by net_rating desc and write to disk atomically."""
    _ensure_dir()
    out = _team_file(team, season)
    sorted_lineups = sorted(lineups, key=lambda r: r.get("net_rating", 0),
                            reverse=True)
    tmp = out.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(sorted_lineups, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, out)
    return out


# --------------------------------------------------------------------------- #
# Top-N filtering                                                              #
# --------------------------------------------------------------------------- #
def top_n_by_minutes(lineups: List[Dict[str, Any]], n: int = 10,
                      min_minutes: float = 5.0) -> List[Dict[str, Any]]:
    """Keep only the top-N lineups by minutes played (with >= min_minutes)."""
    filt = [r for r in lineups if r.get("minutes", 0) >= min_minutes]
    filt.sort(key=lambda r: r.get("minutes", 0), reverse=True)
    return filt[:n]


# --------------------------------------------------------------------------- #
# Bulk fetch path                                                              #
# --------------------------------------------------------------------------- #
def fetch_bulk(season: str = SEASON,
               min_minutes: float = 5.0,
               top_n: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    """Single leaguedashlineups call for entire league; split by team."""
    try:
        from src.data import nba_api_headers_patch  # noqa: F401
    except Exception:
        pass
    try:
        from nba_api.stats.endpoints import leaguedashlineups
    except ImportError as exc:
        raise RuntimeError(f"nba_api not installed: {exc}")

    resp = leaguedashlineups.LeagueDashLineups(
        season=season,
        season_type_all_star="Regular Season",
        group_quantity=5,
        measure_type_detailed_defense="Advanced",
        per_mode_detailed="Per100Possessions",
        timeout=60,
    )
    df = resp.get_data_frames()[0]

    by_team: Dict[str, List[Dict[str, Any]]] = {}
    for _, row in df.iterrows():
        d = row.to_dict()
        team_abbrev = str(d.get("TEAM_ABBREVIATION", "")).upper()
        if not team_abbrev:
            continue
        mins = float(d.get("MIN", 0) or 0)
        if mins < min_minutes:
            continue
        by_team.setdefault(team_abbrev, []).append(_normalize_row(d))

    # Filter top-N per team
    return {t: top_n_by_minutes(rows, n=top_n, min_minutes=min_minutes)
            for t, rows in by_team.items()}


# --------------------------------------------------------------------------- #
# Per-team fetch path                                                          #
# --------------------------------------------------------------------------- #
def _team_id(abbrev: str) -> Optional[int]:
    try:
        from nba_api.stats.static import teams as nba_teams_static
        matches = [t for t in nba_teams_static.get_teams()
                   if t["abbreviation"] == abbrev]
        return matches[0]["id"] if matches else None
    except ImportError:
        return None


def fetch_one_team(team: str, season: str = SEASON,
                    min_minutes: float = 5.0,
                    top_n: int = 10) -> Optional[List[Dict[str, Any]]]:
    try:
        from src.data import nba_api_headers_patch  # noqa: F401
    except Exception:
        pass
    try:
        from nba_api.stats.endpoints import leaguedashlineups
    except ImportError:
        return None

    tid = _team_id(team)
    if tid is None:
        return None

    delay = _BACKOFF_INITIAL_S
    last_err: Optional[Exception] = None
    for attempt in range(_BACKOFF_MAX_RETRIES):
        try:
            resp = leaguedashlineups.LeagueDashLineups(
                season=season,
                season_type_all_star="Regular Season",
                team_id_nullable=tid,
                group_quantity=5,
                measure_type_detailed_defense="Advanced",
                per_mode_detailed="Per100Possessions",
                timeout=60,
            )
            df = resp.get_data_frames()[0]
            rows: List[Dict[str, Any]] = []
            for _, row in df.iterrows():
                d = row.to_dict()
                mins = float(d.get("MIN", 0) or 0)
                if mins < min_minutes:
                    continue
                rows.append(_normalize_row(d))
            return top_n_by_minutes(rows, n=top_n, min_minutes=min_minutes)
        except Exception as exc:
            last_err = exc
            msg = str(exc).lower()
            if "429" in msg or "403" in msg or "timeout" in msg or "ssl" in msg:
                time.sleep(delay)
                delay *= _BACKOFF_FACTOR
                continue
            # Unknown error — propagate
            raise
    print(f"  [warn] fetch_one_team({team}) exhausted retries: {last_err}",
          flush=True)
    return None


# --------------------------------------------------------------------------- #
# Main runner                                                                  #
# --------------------------------------------------------------------------- #
def run_backfill(season: str = SEASON,
                  force: bool = False,
                  prefer_bulk: bool = True,
                  min_minutes: float = 5.0,
                  top_n: int = 10) -> Dict[str, Any]:
    """Backfill missing teams. Returns summary dict."""
    _ensure_dir()
    before = existing_teams(season)
    targets = _ALL_TEAMS if force else missing_teams(season)
    print(f"[backfill] {len(before)} teams already cached, {len(targets)} targets")

    n_added = 0
    n_total_lineups = 0
    api_errors: List[str] = []

    if prefer_bulk and targets:
        try:
            print("[backfill] attempting bulk leaguedashlineups...", flush=True)
            by_team = fetch_bulk(season=season, min_minutes=min_minutes,
                                  top_n=top_n)
            for team in targets:
                rows = by_team.get(team, [])
                if not rows:
                    api_errors.append(f"{team}:empty_bulk_response")
                    continue
                write_team_lineups_atomic(team, rows, season)
                n_added += 1
                n_total_lineups += len(rows)
            print(f"[backfill] bulk wrote {n_added} teams "
                  f"({n_total_lineups} total lineups)",
                  flush=True)
            return {
                "strategy":         "bulk",
                "n_teams_before":   len(before),
                "n_teams_after":    len(existing_teams(season)),
                "n_teams_added":    n_added,
                "n_total_lineups":  n_total_lineups,
                "api_errors":       api_errors,
            }
        except Exception as exc:
            print(f"[backfill] bulk failed ({exc}); falling back to per-team",
                  flush=True)
            api_errors.append(f"bulk:{exc!r}")

    # Per-team fallback
    for team in targets:
        try:
            rows = fetch_one_team(team, season=season,
                                   min_minutes=min_minutes, top_n=top_n)
            if rows is None:
                api_errors.append(f"{team}:none_returned")
                continue
            if not rows:
                api_errors.append(f"{team}:empty")
                continue
            write_team_lineups_atomic(team, rows, season)
            n_added += 1
            n_total_lineups += len(rows)
            print(f"  [{team}] wrote {len(rows)} lineups", flush=True)
        except Exception as exc:
            api_errors.append(f"{team}:{exc!r}")
            print(f"  [{team}] ERROR {exc!r}", flush=True)
        time.sleep(_API_DELAY_S)

    return {
        "strategy":         "per_team",
        "n_teams_before":   len(before),
        "n_teams_after":    len(existing_teams(season)),
        "n_teams_added":    n_added,
        "n_total_lineups":  n_total_lineups,
        "api_errors":       api_errors,
    }


# --------------------------------------------------------------------------- #
# Optional: patch season_games_2025-26.json in-place                           #
# --------------------------------------------------------------------------- #
def patch_season_games(season: str = SEASON,
                        path: Optional[Path] = None) -> Dict[str, Any]:
    """Overwrite home_top_lineup_net_rtg / away_top_lineup_net_rtg with
    freshly-computed values from the newly-cached lineup files.

    Idempotent (re-reading lineup files gives the same answer).
    """
    p = path or _SEASON_GAMES_PATH
    if not p.exists():
        return {"patched": False, "reason": f"missing {p}"}

    # Build {team: top_net_rating} lookup
    top_by_team: Dict[str, float] = {}
    for t in _ALL_TEAMS:
        fp = _team_file(t, season)
        if not fp.exists():
            top_by_team[t] = 0.0
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                rows = json.load(fh)
        except Exception:
            top_by_team[t] = 0.0
            continue
        # The existing convention (lineup_data.get_top_lineups) requires
        # >= 30 min played, then ranks by net_rating. Mirror that:
        elig = [r for r in rows if float(r.get("minutes", 0) or 0) >= 30.0]
        if not elig:
            top_by_team[t] = 0.0
            continue
        elig.sort(key=lambda r: float(r.get("net_rating", 0) or 0),
                  reverse=True)
        top_by_team[t] = float(elig[0].get("net_rating", 0) or 0)

    with open(p, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    n_patched = 0
    for r in rows:
        ht = r.get("home_team")
        at = r.get("away_team")
        new_h = top_by_team.get(ht, 0.0)
        new_a = top_by_team.get(at, 0.0)
        if r.get("home_top_lineup_net_rtg") != new_h:
            r["home_top_lineup_net_rtg"] = new_h
            n_patched += 1
        if r.get("away_top_lineup_net_rtg") != new_a:
            r["away_top_lineup_net_rtg"] = new_a
            n_patched += 1

    # Drop marker so future probes know this ran
    if isinstance(payload, dict):
        payload.setdefault("R31_X6_lineup_backfill", {})
        payload["R31_X6_lineup_backfill"]["n_teams_with_data"] = sum(
            1 for v in top_by_team.values() if v != 0.0
        )

    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, p)
    return {
        "patched": True,
        "n_field_updates": n_patched,
        "n_teams_with_real_data": sum(1 for v in top_by_team.values()
                                       if v != 0.0),
    }


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Refetch even if file exists.")
    ap.add_argument("--per-team", action="store_true",
                    help="Skip the bulk path and fetch one team at a time.")
    ap.add_argument("--season", default=SEASON)
    ap.add_argument("--min-minutes", type=float, default=5.0)
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--patch-season-games", action="store_true",
                    help="After backfill, regenerate top_lineup_net_rtg in "
                         "season_games_2025-26.json.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print plan without API calls or writes.")
    args = ap.parse_args()

    if args.dry_run:
        missing = missing_teams(args.season)
        existing = existing_teams(args.season)
        print(f"DRY-RUN: existing={existing} ({len(existing)}), "
              f"missing={missing} ({len(missing)}), "
              f"would call leaguedashlineups for {args.season}")
        return 0

    summary = run_backfill(
        season=args.season,
        force=args.force,
        prefer_bulk=not args.per_team,
        min_minutes=args.min_minutes,
        top_n=args.top_n,
    )

    if args.patch_season_games:
        patch_res = patch_season_games(season=args.season)
        summary["season_games_patch"] = patch_res
        print(f"[patch] {patch_res}", flush=True)

    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
