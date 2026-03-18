"""
ref_tracker.py — NBA referee historical tendencies (Phase 5).

Pulls referee game assignments from nba_api and builds per-referee tendency
profiles: avg fouls per game, home-win pct, and avg pace.

Cache
-----
    data/nba/ref_tendencies.json   — persisted after each scrape

Public API
----------
    scrape_ref_tendencies(season)  -> dict   (raw ref map, writes cache)
    get_ref_features(ref_names)    -> dict   (averaged features for a crew)
    get_all_refs()                 -> list   (sorted list of known ref names)
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from src.data.cache_utils import cache_is_fresh, load_json_cache, save_json_cache

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH = os.path.join(PROJECT_DIR, "data", "nba", "ref_tendencies.json")
_CACHE_TTL  = 24 * 3600   # 24 hours
_DELAY      = 0.8          # seconds between NBA API calls


# ── helpers ───────────────────────────────────────────────────────────────────

def _cache_is_fresh() -> bool:
    """Return True if the ref cache exists and is younger than TTL."""
    return cache_is_fresh(_CACHE_PATH, _CACHE_TTL)


def _load_cache() -> dict:
    """Load the ref tendencies cache from disk."""
    return load_json_cache(_CACHE_PATH)


def _save_cache(data: dict) -> None:
    """Persist ref tendencies to disk."""
    save_json_cache(_CACHE_PATH, data)


def _norm_name(name: str) -> str:
    """Normalise referee name to lowercase stripped form."""
    return name.lower().strip()


# ── scraper ───────────────────────────────────────────────────────────────────

def scrape_ref_tendencies(
    season: str = "2024-25",
    max_games: int = 200,
    force: bool = False,
) -> dict:
    """
    Pull referee assignments from nba_api and build tendency profiles.

    Iterates over game summaries for the season, collects official assignments,
    then aggregates:
        - avg_fouls_per_game  : mean (home_fouls + away_fouls) per game
        - home_win_pct        : fraction of games the home team won
        - avg_pace            : mean pace (from game pace stats endpoint)
        - games_counted       : number of games included in the profile

    Results are merged with any existing cache so profiles improve over time.

    Args:
        season:    NBA season string, e.g. "2024-25".
        max_games: Maximum number of games to process per call (for rate-limit safety).
        force:     Re-scrape even if cache is fresh.

    Returns:
        Dict mapping referee full name → tendency dict.
    """
    if not force and _cache_is_fresh():
        return _load_cache()

    # Load existing cache to merge (avoids losing data from prior seasons)
    existing: dict = {}
    if os.path.exists(_CACHE_PATH):
        try:
            existing = _load_cache()
        except Exception:
            existing = {}

    try:
        from nba_api.stats.endpoints import leaguegamelog, boxscoretraditionalv2
        from nba_api.stats.static import teams as nba_teams_module

        # Step 1: get game IDs for the season
        time.sleep(_DELAY)
        log_resp = leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="T",
        )
        dfs = log_resp.get_data_frames()
        if not dfs or len(dfs[0]) == 0:
            print(f"[ref_tracker] No game log for {season}")
            return existing

        game_ids = dfs[0]["GAME_ID"].unique().tolist()
        print(f"[ref_tracker] Found {len(game_ids)} games for {season}, processing up to {max_games}")

        # Accumulator: ref_name → {fouls: [], home_win: [], pace: []}
        acc: Dict[str, Dict[str, list]] = {}

        for gid in game_ids[:max_games]:
            try:
                time.sleep(_DELAY)
                box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=gid)
                box_dfs = box.get_data_frames()

                if len(box_dfs) < 3:
                    continue

                # df index 2 = game summary / officials in some endpoints
                # BoxScoreTraditional returns: [PlayerStats, TeamStats, ...]
                team_df = box_dfs[1]  # TeamStats
                if team_df is None or len(team_df) < 2:
                    continue

                home_row  = team_df[team_df["TEAM_ABBREVIATION"] == team_df["TEAM_ABBREVIATION"].iloc[0]]
                home_won  = False
                home_pts  = 0
                away_pts  = 0

                if "PTS" in team_df.columns and len(team_df) >= 2:
                    pts = team_df["PTS"].tolist()
                    if len(pts) >= 2:
                        home_pts, away_pts = int(pts[0] or 0), int(pts[1] or 0)
                        home_won = home_pts > away_pts

                total_fouls = 0
                if "PF" in team_df.columns:
                    total_fouls = int(team_df["PF"].sum() or 0)

                # Officials: try the Officials endpoint (index varies by nba_api version)
                officials: List[str] = []
                for sub_df in box_dfs:
                    cols = list(sub_df.columns) if hasattr(sub_df, "columns") else []
                    if "OFFICIAL_NAME" in cols or "FIRST_NAME" in cols:
                        if "OFFICIAL_NAME" in cols:
                            officials = sub_df["OFFICIAL_NAME"].dropna().tolist()
                        elif "FIRST_NAME" in cols and "LAST_NAME" in cols:
                            officials = [
                                f"{r['FIRST_NAME']} {r['LAST_NAME']}"
                                for _, r in sub_df.iterrows()
                            ]
                        break

                if not officials:
                    continue

                # Fetch game pace from BoxScoreAdvancedV2 (separate endpoint)
                game_pace: Optional[float] = None
                try:
                    from nba_api.stats.endpoints import boxscoreadvancedv2
                    time.sleep(_DELAY)
                    adv = boxscoreadvancedv2.BoxScoreAdvancedV2(game_id=gid)
                    adv_dfs = adv.get_data_frames()
                    # Index 1 = TeamStats in BoxScoreAdvancedV2; PACE column present
                    if len(adv_dfs) > 1 and "PACE" in adv_dfs[1].columns:
                        pace_vals = adv_dfs[1]["PACE"].dropna().tolist()
                        if pace_vals:
                            game_pace = float(sum(pace_vals) / len(pace_vals))
                except Exception:
                    pass  # keep game_pace as None — averaged safely below

                for ref_name in officials:
                    ref_name = str(ref_name).strip()
                    if not ref_name:
                        continue
                    if ref_name not in acc:
                        acc[ref_name] = {"fouls": [], "home_win": [], "pace": []}
                    acc[ref_name]["fouls"].append(total_fouls)
                    acc[ref_name]["home_win"].append(1 if home_won else 0)
                    if game_pace is not None:
                        acc[ref_name]["pace"].append(game_pace)

            except Exception as e:
                print(f"[ref_tracker] game {gid} failed: {e}")
                continue

        # Build profiles
        profiles: dict = dict(existing)
        for ref_name, data in acc.items():
            if not data["fouls"]:
                continue
            n = len(data["fouls"])
            profiles[ref_name] = {
                "avg_fouls_per_game": round(sum(data["fouls"]) / n, 2),
                "home_win_pct":       round(sum(data["home_win"]) / n, 3),
                "avg_pace":           round(sum(data["pace"]) / n, 1) if any(data["pace"]) else None,
                "games_counted":      n,
            }

        _save_cache(profiles)
        print(f"[ref_tracker] Saved {len(profiles)} referee profiles → {_CACHE_PATH}")
        return profiles

    except Exception as e:
        print(f"[ref_tracker] Scrape error: {e}")
        if os.path.exists(_CACHE_PATH):
            print("[ref_tracker] Returning stale cache.")
            return _load_cache()
        return {}


# ── public API ────────────────────────────────────────────────────────────────

def get_ref_features(ref_names: List[str]) -> dict:
    """
    Return averaged tendency features for a referee crew.

    Loads the cache (or scrapes if missing/stale) and averages the profiles
    of all named referees.  Unknown referees are skipped.

    Args:
        ref_names: List of referee full names (e.g. ["Scott Foster", "Tony Brothers"]).

    Returns:
        {
            "avg_fouls_per_game": float,
            "home_win_pct":       float,
            "avg_pace":           float | None,
            "refs_found":         int,
            "refs_total":         int,
        }
        All float fields are None if no matching refs found.
    """
    profiles = _get_profiles()

    found: List[dict] = []
    for name in ref_names:
        key = name.strip()
        if key in profiles:
            found.append(profiles[key])

    if not found:
        return {
            "avg_fouls_per_game": None,
            "home_win_pct":       None,
            "avg_pace":           None,
            "refs_found":         0,
            "refs_total":         len(ref_names),
        }

    fouls = [p["avg_fouls_per_game"] for p in found if p.get("avg_fouls_per_game") is not None]
    hwp   = [p["home_win_pct"]       for p in found if p.get("home_win_pct")       is not None]
    pace  = [p["avg_pace"]           for p in found if p.get("avg_pace")           is not None]

    return {
        "avg_fouls_per_game": round(sum(fouls) / len(fouls), 2) if fouls else None,
        "home_win_pct":       round(sum(hwp)   / len(hwp),   3) if hwp   else None,
        "avg_pace":           round(sum(pace)  / len(pace),  1) if pace  else None,
        "refs_found":         len(found),
        "refs_total":         len(ref_names),
    }


def get_all_refs() -> List[str]:
    """
    Return sorted list of all referee names in the cache.

    Returns:
        Sorted list of referee full-name strings.  Empty if cache not built.
    """
    profiles = _get_profiles()
    return sorted(profiles.keys())


def _get_profiles() -> dict:
    """Return cached profiles, loading from disk (no network call)."""
    if os.path.exists(_CACHE_PATH):
        try:
            return _load_cache()
        except Exception:
            pass
    return {}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NBA Referee Tendency Tracker")
    ap.add_argument("--season", default="2024-25", help="NBA season string")
    ap.add_argument("--max",    type=int, default=200, help="Max games to process")
    ap.add_argument("--force",  action="store_true",  help="Re-scrape even if cached")
    ap.add_argument("--refs",   nargs="+",             help="Look up specific ref names")
    args = ap.parse_args()

    if args.refs:
        features = get_ref_features(args.refs)
        print(json.dumps(features, indent=2))
    else:
        profiles = scrape_ref_tendencies(args.season, max_games=args.max, force=args.force)
        print(f"Profiles built: {len(profiles)}")
        for name, p in list(profiles.items())[:5]:
            print(f"  {name}: fouls={p['avg_fouls_per_game']} hw%={p['home_win_pct']}")
