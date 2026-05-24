"""fetch_defender_matchup.py — per-game per-defender matchup scraper.

Pulls **per-game** defender matchup data from `boxscorematchupsv3` (primary)
and `boxscoredefensivev2` (per-defender summary). Both endpoints are CURRENT-
SEASON per-game — the granularity gap the model is missing.

Why this endpoint:
-----------------
The model currently uses:
- `matchupsrollup`        → season aggregate (who-guards-whom over a year)
- `leaguedashptdefend`    → season aggregate (FG% allowed by zone)
- `player_tracking.parquet` (dormant) → PRIOR-season tracking, regressed on
  walk-forward because year-over-year role changes are too noisy.

`boxscorematchupsv3` is per-(offensive_player × defensive_player × game),
giving matchup minutes, partial possessions, points allowed, FG%/3PT%
allowed, and HELP defense. Aggregated to a rolling defender_strength feature
(e.g., last-15-game opp FG% when this defender is primary), it produces a
matchup-specific number for LeBron vs a top wing defender vs a sieve —
exactly the signal aggregate `opp_def_pts` cannot express.

Output schema (defender summary parquet/json):
----------------------------------------------
    game_id, game_date, season, def_player_id, def_player_name,
    def_team_tricode, matchup_minutes_total, partial_possessions,
    points_allowed, fg_made_allowed, fg_attempted_allowed,
    fg_pct_allowed, fg3_made_allowed, fg3_attempted_allowed,
    fg3_pct_allowed, switches_on, blocks_matchup, help_blocks,
    matchups_count  (distinct offensive players guarded)

Output schema (raw matchups parquet/json):
------------------------------------------
    game_id, off_player_id, def_player_id, off_player_name,
    def_player_name, def_team_tricode, matchup_minutes,
    partial_possessions, player_points, matchup_fg_made,
    matchup_fg_attempted, matchup_fg_pct, matchup_3pm,
    matchup_3pa, matchup_3p_pct, help_blocks, switches_on

Cache layout:
    data/defender_matchups/raw_<game_id>.json   (perpetual, per-game)
    data/defender_matchups_<season>.parquet     (rolled up)
    data/defender_matchups_<season>.json        (defender summary, JSON)

Polite rate limit: 0.7s between API calls (matches `src/data/nba_stats.py`).

CLI:
    python scripts/fetch_defender_matchup.py --season 2024-25 --limit 5
    python scripts/fetch_defender_matchup.py --game-id 0022400710
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Apply nba_api headers patch (required — bare nba_api times out)
try:  # pragma: no cover - executed at import
    from src.data import nba_api_headers_patch  # noqa: F401
except Exception:
    pass

# ─── paths / TTLs ───────────────────────────────────────────────────────────
_RAW_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "defender_matchups")
_TTL_PERM = None         # per-game data is historical — perpetual
_TTL_24H = 24 * 3600     # season-level rollup refresh

# Polite rate limit between nba_api calls
_RATE_LIMIT_SECS = 0.7


def _ensure_cache_dir() -> None:
    os.makedirs(_RAW_CACHE_DIR, exist_ok=True)


def _safe(s: Any) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(s))


def _is_fresh(path: str, ttl: Optional[float]) -> bool:
    if not os.path.exists(path):
        return False
    if ttl is None:
        return True
    return (time.time() - os.path.getmtime(path)) < ttl


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str)


def _rate_limit(secs: float = _RATE_LIMIT_SECS) -> None:
    time.sleep(secs)


# ─── core fetch ─────────────────────────────────────────────────────────────

def fetch_game_matchups(
    game_id: str,
    *,
    timeout: int = 20,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch per-(off × def) matchup records for one game.

    Returns a list of matchup dicts (one per offensive×defensive player pair).
    Cached perpetually to `data/defender_matchups/raw_<game_id>.json`.

    Returns [] on any error (network, parse, missing endpoint).
    """
    _ensure_cache_dir()
    cache_path = os.path.join(_RAW_CACHE_DIR, f"raw_{_safe(game_id)}.json")
    if not force and _is_fresh(cache_path, _TTL_PERM):
        try:
            return _load_json(cache_path)
        except Exception:
            pass  # fall through to refetch

    try:
        from nba_api.stats.endpoints import boxscorematchupsv3
    except ImportError:
        print("[defender_matchup] nba_api not installed")
        return []

    _rate_limit()
    try:
        resp = boxscorematchupsv3.BoxScoreMatchupsV3(
            game_id=str(game_id), timeout=timeout,
        )
        df = resp.get_data_frames()[0]
    except Exception as exc:
        print(f"[defender_matchup] BoxScoreMatchupsV3 error for {game_id}: {exc}")
        return []

    if df is None or df.empty:
        _save_json(cache_path, [])
        return []

    records = _parse_matchups_frame(df)
    _save_json(cache_path, records)
    return records


def _parse_matchups_frame(df) -> List[Dict[str, Any]]:
    """Convert a BoxScoreMatchupsV3 frame into our normalized schema."""
    out: List[Dict[str, Any]] = []

    # Map camelCase API columns → snake_case schema. Be defensive: some
    # column names vary slightly across nba_api versions.
    col_map = {
        "gameId":                            "game_id",
        "teamTricode":                       "def_team_tricode",
        "personIdOff":                       "off_player_id",
        "firstNameOff":                      "_off_first",
        "familyNameOff":                     "_off_last",
        "personIdDef":                       "def_player_id",
        "firstNameDef":                      "_def_first",
        "familyNameDef":                     "_def_last",
        "matchupMinutes":                    "matchup_minutes",
        "partialPossessions":                "partial_possessions",
        "switchesOn":                        "switches_on",
        "playerPoints":                      "player_points",
        "matchupAssists":                    "matchup_assists",
        "matchupTurnovers":                  "matchup_turnovers",
        "matchupBlocks":                     "matchup_blocks",
        "matchupFieldGoalsMade":             "matchup_fg_made",
        "matchupFieldGoalsAttempted":        "matchup_fg_attempted",
        "matchupFieldGoalsPercentage":       "matchup_fg_pct",
        "matchupThreePointersMade":          "matchup_3pm",
        "matchupThreePointersAttempted":     "matchup_3pa",
        "matchupThreePointersPercentage":    "matchup_3p_pct",
        "helpBlocks":                        "help_blocks",
        "matchupFreeThrowsMade":             "matchup_ftm",
        "matchupFreeThrowsAttempted":        "matchup_fta",
        "shootingFouls":                     "shooting_fouls",
    }

    cols = [c for c in col_map if c in df.columns]
    sub = df[cols].rename(columns={c: col_map[c] for c in cols})

    for rec in sub.to_dict("records"):
        # Stitch first+last name
        rec["off_player_name"] = " ".join(
            part for part in (rec.pop("_off_first", ""), rec.pop("_off_last", "")) if part
        ).strip()
        rec["def_player_name"] = " ".join(
            part for part in (rec.pop("_def_first", ""), rec.pop("_def_last", "")) if part
        ).strip()

        # Convert matchup_minutes 'M:SS' → float minutes for downstream math
        rec["matchup_minutes_float"] = _parse_clock(rec.get("matchup_minutes", ""))
        out.append(rec)
    return out


def _parse_clock(s: Any) -> float:
    """Convert NBA 'M:SS' time string to float minutes. Returns 0.0 on failure."""
    if s is None:
        return 0.0
    text = str(s).strip()
    if not text or text in {"None", "nan"}:
        return 0.0
    if ":" in text:
        try:
            mins, secs = text.split(":")
            return round(float(mins) + float(secs) / 60.0, 4)
        except Exception:
            return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


# ─── defender summary aggregation ───────────────────────────────────────────

def summarize_defender(
    matchups: Iterable[Dict[str, Any]],
    *,
    game_id: str,
    season: str = "",
    game_date: str = "",
) -> List[Dict[str, Any]]:
    """Aggregate raw matchups by defender within one game.

    Produces one row per defensive player containing total matchup minutes,
    points allowed, FG%/3PT% allowed, switches, blocks, and matchups_count
    (distinct offensive players guarded). This is the "defender_strength"
    per-game signal the prop model can later consume.
    """
    by_def: Dict[Any, Dict[str, Any]] = {}
    for m in matchups:
        pid_raw = m.get("def_player_id")
        # Skip None, NaN (pandas converts None → NaN), or non-numeric IDs.
        try:
            if pid_raw is None or pid_raw != pid_raw:  # NaN check
                continue
            pid = int(pid_raw)
        except (TypeError, ValueError):
            continue
        agg = by_def.setdefault(pid, {
            "game_id":              game_id,
            "game_date":            game_date,
            "season":               season,
            "def_player_id":        pid,
            "def_player_name":      m.get("def_player_name", ""),
            "def_team_tricode":     m.get("def_team_tricode", ""),
            "matchup_minutes_total": 0.0,
            "partial_possessions":  0.0,
            "points_allowed":       0,
            "fg_made_allowed":      0,
            "fg_attempted_allowed": 0,
            "fg3_made_allowed":     0,
            "fg3_attempted_allowed": 0,
            "switches_on":          0,
            "blocks_matchup":       0,
            "help_blocks":          0,
            "matchups_count":       0,
        })
        agg["matchup_minutes_total"] += _flt(m.get("matchup_minutes_float", 0))
        agg["partial_possessions"]   += _flt(m.get("partial_possessions", 0))
        agg["points_allowed"]        += _int(m.get("player_points", 0))
        agg["fg_made_allowed"]       += _int(m.get("matchup_fg_made", 0))
        agg["fg_attempted_allowed"]  += _int(m.get("matchup_fg_attempted", 0))
        agg["fg3_made_allowed"]      += _int(m.get("matchup_3pm", 0))
        agg["fg3_attempted_allowed"] += _int(m.get("matchup_3pa", 0))
        agg["switches_on"]           += _int(m.get("switches_on", 0))
        agg["blocks_matchup"]        += _int(m.get("matchup_blocks", 0))
        agg["help_blocks"]           += _int(m.get("help_blocks", 0))
        agg["matchups_count"]        += 1

    # Compute derived percentages
    for agg in by_def.values():
        fga = agg["fg_attempted_allowed"]
        fg3a = agg["fg3_attempted_allowed"]
        agg["fg_pct_allowed"]  = round(agg["fg_made_allowed"] / fga, 4) if fga else 0.0
        agg["fg3_pct_allowed"] = round(agg["fg3_made_allowed"] / fg3a, 4) if fg3a else 0.0
        agg["matchup_minutes_total"] = round(agg["matchup_minutes_total"], 3)
        agg["partial_possessions"]   = round(agg["partial_possessions"], 2)

    return sorted(
        by_def.values(),
        key=lambda r: r["matchup_minutes_total"], reverse=True,
    )


def _flt(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _int(v: Any) -> int:
    try:
        return int(float(v)) if v is not None else 0
    except (TypeError, ValueError):
        return 0


# ─── bulk season fetch ──────────────────────────────────────────────────────

def fetch_season_matchups(
    season: str = "2024-25",
    *,
    limit: Optional[int] = None,
    delay: float = _RATE_LIMIT_SECS,
    force: bool = False,
) -> Dict[str, Any]:
    """Pull matchups for every regular-season game in `season`.

    Writes:
        data/defender_matchups/raw_<game_id>.json    (per game)
        data/defender_matchups_<season>.parquet      (per defender × game)
        data/defender_matchups_<season>.json         (per defender × game)

    Returns a summary dict {n_games, n_defender_rows, parquet_path, json_path}.
    """
    out_summary_path_pq   = os.path.join(PROJECT_DIR, "data",
                                         f"defender_matchups_{_safe(season)}.parquet")
    out_summary_path_json = os.path.join(PROJECT_DIR, "data",
                                         f"defender_matchups_{_safe(season)}.json")

    # Pull season schedule via nba_api leaguegamelog
    try:
        from nba_api.stats.endpoints import leaguegamelog
    except ImportError:
        print("[defender_matchup] nba_api not installed")
        return {"n_games": 0, "n_defender_rows": 0,
                "parquet_path": None, "json_path": None}

    _rate_limit(delay)
    try:
        log = leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
            timeout=20,
        )
        df = log.get_data_frames()[0]
    except Exception as exc:
        print(f"[defender_matchup] leaguegamelog error: {exc}")
        return {"n_games": 0, "n_defender_rows": 0,
                "parquet_path": None, "json_path": None}

    game_ids = sorted({str(g).zfill(10) for g in df["GAME_ID"].tolist()})
    if limit is not None:
        game_ids = game_ids[:limit]

    # date lookup
    date_lookup = {str(g).zfill(10): str(d)
                   for g, d in zip(df["GAME_ID"], df["GAME_DATE"])}

    all_rows: List[Dict[str, Any]] = []
    for i, gid in enumerate(game_ids, 1):
        raw = fetch_game_matchups(gid, force=force)
        if not raw:
            continue
        summary = summarize_defender(
            raw, game_id=gid, season=season,
            game_date=date_lookup.get(gid, ""),
        )
        all_rows.extend(summary)
        if i % 25 == 0:
            print(f"[defender_matchup] {i}/{len(game_ids)} games processed "
                  f"({len(all_rows)} defender rows so far)")
        time.sleep(delay)

    # Persist
    _save_json(out_summary_path_json, all_rows)

    try:
        import pandas as pd
        if all_rows:
            pd.DataFrame(all_rows).to_parquet(out_summary_path_pq, index=False)
    except Exception as exc:
        print(f"[defender_matchup] parquet write skipped: {exc}")
        out_summary_path_pq = None  # type: ignore[assignment]

    print(f"\n[defender_matchup] DONE: {len(game_ids)} games "
          f"→ {len(all_rows)} defender rows")
    if out_summary_path_pq:
        print(f"   parquet: {out_summary_path_pq}")
    print(f"   json   : {out_summary_path_json}")

    return {
        "n_games":          len(game_ids),
        "n_defender_rows":  len(all_rows),
        "parquet_path":     out_summary_path_pq,
        "json_path":        out_summary_path_json,
    }


# ─── CLI ────────────────────────────────────────────────────────────────────

def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", default="2024-25",
                    help="NBA season, e.g. 2024-25 (used for bulk fetch).")
    ap.add_argument("--game-id", default=None,
                    help="If set, fetch a single game and print summary "
                         "(skips season pull).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap the number of games for a partial bulk pull.")
    ap.add_argument("--force", action="store_true",
                    help="Re-fetch even if cache exists.")
    args = ap.parse_args()

    if args.game_id:
        raw = fetch_game_matchups(args.game_id, force=args.force)
        summary = summarize_defender(raw, game_id=args.game_id,
                                     season=args.season)
        print(f"\nGame {args.game_id}: {len(raw)} raw matchups, "
              f"{len(summary)} defenders")
        for row in summary[:10]:
            name = (row.get("def_player_name") or "").encode(
                sys.stdout.encoding or "utf-8", errors="replace"
            ).decode(sys.stdout.encoding or "utf-8", errors="replace")
            print(f"  {name:<22} "
                  f"min={row['matchup_minutes_total']:5.1f}  "
                  f"pts_allowed={row['points_allowed']:3d}  "
                  f"fg%={row['fg_pct_allowed']:.3f}  "
                  f"matchups={row['matchups_count']}")
        return

    fetch_season_matchups(args.season, limit=args.limit, force=args.force)


if __name__ == "__main__":
    _cli()
