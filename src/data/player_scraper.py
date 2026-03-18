"""
player_scraper.py — Comprehensive NBA player metric scraper with self-improving loop.

Fetches every available metric tier for all players from the NBA Stats API:
  Tier 1 (batch, all players):
    Base    — pts, reb, ast, stl, blk, tov, fgm/fga, fg3m/fg3a, ftm/fta, oreb, dreb, pf, min, gp
    Advanced — usg_pct, ts_pct, off_rtg, def_rtg, net_rtg, pie, ast_pct, reb_pct, stl_pct, blk_pct, tov_pct, efg_pct
    Scoring  — pct_pts_paint, pct_pts_mid_range, pct_pts_3pt, pct_pts_ft, pct_fga_2pt, pct_fga_3pt
    Misc     — pts_off_tov, pts_2nd_chance, pts_fb, pts_paint, blk_a, fouls_drawn

  Tier 2 (per-player, high-value targets):
    GameLog  — full game-by-game: pts/reb/ast/stl/blk/tov/fgm/fga/fg3m/fg3a/ftm/fta/oreb/dreb/pf/plus_minus
    Splits   — last 5/10/15/20 game averages (rolling form)

Self-improvement loop:
  - Reads coverage report from data/nba/scraper_coverage.json
  - Detects missing/stale metric tiers per player
  - Fills gaps in priority order: Advanced > Scoring > Misc > GameLog > Splits
  - Writes updated coverage + delta to vault improvement log

Public API
----------
    fetch_all_player_stats(season)                    -> dict  # all players, all tiers
    fetch_player_gamelog_full(player_id, season)      -> list  # full per-game rows
    fetch_player_splits(player_id, season)            -> dict  # last-N splits
    run_improvement_loop(season, max_players, delay)  -> dict  # coverage delta report
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE    = os.path.join(PROJECT_DIR, "data", "nba")

# Apply the same session patch used by nba_stats.py (proper headers + retry)
try:
    from src.data.nba_stats import _configure_nba_session
    _configure_nba_session()
except Exception:
    pass
_COVERAGE_FILE = os.path.join(_NBA_CACHE, "scraper_coverage.json")
_VAULT_LOG    = os.path.join(PROJECT_DIR, "vault", "Improvements", "Tracker Improvements Log.md")

# TTL in hours per tier (how long before re-fetch)
_TTL = {
    "base":     24,
    "advanced": 24,
    "scoring":  24,
    "misc":     24,
    "gamelog":  6,    # gamelogs change after each game
    "splits":   12,
}

# Priority order for gap-filling (highest impact first)
_TIER_PRIORITY = ["advanced", "scoring", "misc", "base", "gamelog", "splits"]

# Columns to extract per measure_type from LeagueDashPlayerStats
_BATCH_TIERS = {
    "base": {
        "measure_type": "Base",
        "per_mode": "PerGame",
        "cols": {
            "GP": "gp", "W": "wins", "L": "losses", "W_PCT": "win_pct",
            "MIN": "min", "FGM": "fgm", "FGA": "fga", "FG_PCT": "fg_pct",
            "FG3M": "fg3m", "FG3A": "fg3a", "FG3_PCT": "fg3_pct",
            "FTM": "ftm", "FTA": "fta", "FT_PCT": "ft_pct",
            "OREB": "oreb", "DREB": "dreb", "REB": "reb",
            "AST": "ast", "TOV": "tov", "STL": "stl", "BLK": "blk",
            "PF": "pf", "PTS": "pts", "PLUS_MINUS": "plus_minus",
        },
    },
    "advanced": {
        "measure_type": "Advanced",
        "per_mode": "PerGame",
        "cols": {
            "OFF_RATING": "off_rtg", "DEF_RATING": "def_rtg", "NET_RATING": "net_rtg",
            "AST_PCT": "ast_pct", "AST_TO": "ast_to_ratio",
            "AST_RATIO": "ast_ratio", "OREB_PCT": "oreb_pct", "DREB_PCT": "dreb_pct",
            "REB_PCT": "reb_pct", "TM_TOV_PCT": "tov_pct",
            "EFG_PCT": "efg_pct", "TS_PCT": "ts_pct",
            "USG_PCT": "usg_pct", "PACE": "pace", "PIE": "pie",
            "POSS": "possessions",
        },
    },
    "scoring": {
        "measure_type": "Scoring",
        "per_mode": "PerGame",
        "cols": {
            "PCT_FGA_2PT": "pct_fga_2pt", "PCT_FGA_3PT": "pct_fga_3pt",
            "PCT_PTS_2PT": "pct_pts_2pt", "PCT_PTS_2PT_MR": "pct_pts_mid_range",
            "PCT_PTS_3PT": "pct_pts_3pt", "PCT_PTS_FB": "pct_pts_fast_break",
            "PCT_PTS_FT": "pct_pts_ft", "PCT_PTS_OFF_TOV": "pct_pts_off_tov",
            "PCT_PTS_PAINT": "pct_pts_paint",
            "PCT_AST_2PM": "pct_ast_2pt", "PCT_UAST_2PM": "pct_unast_2pt",
            "PCT_AST_3PM": "pct_ast_3pt", "PCT_UAST_3PM": "pct_unast_3pt",
        },
    },
    "misc": {
        "measure_type": "Misc",
        "per_mode": "PerGame",
        "cols": {
            "PTS_OFF_TOV": "pts_off_tov", "PTS_2ND_CHANCE": "pts_2nd_chance",
            "PTS_FB": "pts_fast_break", "PTS_PAINT": "pts_paint",
            "OPP_PTS_OFF_TOV": "opp_pts_off_tov", "OPP_PTS_2ND_CHANCE": "opp_pts_2nd_chance",
            "OPP_PTS_FB": "opp_pts_fast_break", "OPP_PTS_PAINT": "opp_pts_paint",
            "BLK": "blk", "BLKA": "blk_against",
        },
    },
}

# All gamelog columns available from PlayerGameLog endpoint
_GAMELOG_COLS = [
    "SEASON_ID", "Game_ID", "GAME_DATE", "MATCHUP", "WL",
    "MIN", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT",
    "FTM", "FTA", "FT_PCT", "OREB", "DREB", "REB",
    "AST", "STL", "BLK", "TOV", "PF", "PTS", "PLUS_MINUS",
]


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1: Batch pulls (all players at once)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_player_stats(season: str = "2024-25", force: bool = False) -> dict:
    """
    Fetch all batch metric tiers for every player in the league.

    Returns merged dict keyed by normalized player name:
    {
        "lebron james": {
            "player_id": 2544, "team": "LAL",
            "pts": 25.2, "usg_pct": 0.31, "ts_pct": 0.63,
            "pct_pts_paint": 0.41, ...
        }
    }

    Caches per tier to data/nba/player_{tier}_{season}.json with TTL.
    """
    import unicodedata

    def _norm(s: str) -> str:
        return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()

    merged: dict = {}

    for tier_name, tier_cfg in _BATCH_TIERS.items():
        cache_path = os.path.join(_NBA_CACHE, f"player_{tier_name}_{season}.json")
        cache_age_h = (
            (time.time() - os.path.getmtime(cache_path)) / 3600
            if os.path.exists(cache_path) else 999
        )
        if not force and cache_age_h < _TTL[tier_name]:
            with open(cache_path) as f:
                tier_data = json.load(f)
            print(f"  [scraper] {tier_name} cache hit ({cache_age_h:.1f}h old, TTL={_TTL[tier_name]}h)")
        else:
            tier_data = _fetch_batch_tier(tier_name, tier_cfg, season)
            if tier_data:
                os.makedirs(_NBA_CACHE, exist_ok=True)
                with open(cache_path, "w") as f:
                    json.dump(tier_data, f)
                print(f"  [scraper] {tier_name} fetched — {len(tier_data)} players")

        # Merge into combined dict
        for name, stats in tier_data.items():
            nk = _norm(name)
            if nk not in merged:
                merged[nk] = {}
            merged[nk].update(stats)

    # Write combined cache
    combined_path = os.path.join(_NBA_CACHE, f"player_full_{season}.json")
    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(combined_path, "w") as f:
        json.dump(merged, f)

    return merged


def _bootstrap_from_legacy(season: str) -> dict:
    """
    Migrate old player_avgs_{season}.json (12-col format from player_props.py)
    into the new base tier schema so we don't need an API call for 'base'.

    Returns {player_name: {player_id, team, gp, min, pts, reb, ast, ...}}
    or {} if legacy file not found.
    """
    legacy_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    if not os.path.exists(legacy_path):
        return {}
    with open(legacy_path) as f:
        legacy = json.load(f)
    # Legacy keys are already normalised lowercase names → values match base col schema
    result = {}
    for name, data in legacy.items():
        result[name] = {
            "player_id": data.get("player_id", 0),
            "team":      data.get("team", ""),
            "gp":        data.get("gp", 0),
            "min":       round(float(data.get("min", 0)), 2),
            "pts":       round(float(data.get("pts", 0)), 2),
            "reb":       round(float(data.get("reb", 0)), 2),
            "ast":       round(float(data.get("ast", 0)), 2),
            "tov":       round(float(data.get("tov", 0)), 2),
            "fg_pct":    round(float(data.get("fg_pct", 0)), 4),
            "fg3_pct":   round(float(data.get("fg3_pct", 0)), 4),
            "ft_pct":    round(float(data.get("ft_pct", 0)), 4),
            "fta":       round(float(data.get("fta", 0)), 2),
        }
    print(f"  [scraper] base bootstrapped from legacy cache — {len(result)} players")
    return result


def _fetch_batch_tier(tier_name: str, tier_cfg: dict, season: str) -> dict:
    """Fetch one measure_type batch from LeagueDashPlayerStats. Returns {name: {cols}}."""
    # For 'base' tier: try migrating legacy player_avgs cache first (avoids API call)
    if tier_name == "base":
        legacy = _bootstrap_from_legacy(season)
        if legacy:
            return legacy

    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
    except ImportError:
        raise RuntimeError("nba_api not installed")

    time.sleep(1.2)
    try:
        resp = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            measure_type_detailed_defense=tier_cfg["measure_type"],
            per_mode_detailed=tier_cfg["per_mode"],
            timeout=90,
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"  [scraper] {tier_name} API error: {e}")
        return {}

    col_map = tier_cfg["cols"]
    result = {}
    for _, row in df.iterrows():
        name = str(row.get("PLAYER_NAME", "")).strip()
        if not name:
            continue
        stats = {
            "player_id": int(row.get("PLAYER_ID", 0)),
            "team":      str(row.get("TEAM_ABBREVIATION", "")),
        }
        for src_col, dst_col in col_map.items():
            raw = row.get(src_col)
            if raw is not None:
                try:
                    stats[dst_col] = round(float(raw), 4)
                except (ValueError, TypeError):
                    stats[dst_col] = raw
        result[name] = stats
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2: Per-player — full gamelog
# ─────────────────────────────────────────────────────────────────────────────

def fetch_player_gamelog_full(
    player_id: int,
    season: str = "2024-25",
    force: bool = False,
) -> list:
    """
    Fetch full game-by-game log for a player with ALL available columns.

    Returns list of dicts sorted by GAME_DATE descending (most recent first).
    Each row has: game_id, game_date, matchup, wl, min, fgm, fga, fg_pct,
    fg3m, fg3a, fg3_pct, ftm, fta, ft_pct, oreb, dreb, reb, ast, stl, blk,
    tov, pf, pts, plus_minus.

    Cached to data/nba/gamelog_full_{player_id}_{season}.json with 6h TTL.
    """
    cache_path = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
    cache_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _TTL["gamelog"] * 3600
    )
    if not force and cache_fresh:
        with open(cache_path) as f:
            return json.load(f)

    try:
        from nba_api.stats.endpoints import playergamelog
    except ImportError:
        raise RuntimeError("nba_api not installed")

    time.sleep(0.6)
    try:
        df = playergamelog.PlayerGameLog(
            player_id=player_id, season=season, timeout=60
        ).get_data_frames()[0]
    except Exception as e:
        print(f"  [scraper] gamelog fetch failed for player {player_id}: {e}")
        return []

    def _parse_min(m) -> float:
        try:
            if isinstance(m, str) and ":" in m:
                p = m.split(":")
                return round(float(p[0]) + float(p[1]) / 60, 2)
            return round(float(m), 2)
        except (ValueError, TypeError):
            return 0.0

    def _parse_date(d: str) -> datetime:
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(str(d).strip(), fmt)
            except ValueError:
                continue
        return datetime.min

    rows = []
    for _, r in df.iterrows():
        row = {
            "game_id":    str(r.get("Game_ID", "")),
            "game_date":  str(r.get("GAME_DATE", "")),
            "matchup":    str(r.get("MATCHUP", "")),
            "wl":         str(r.get("WL", "")),
            "min":        _parse_min(r.get("MIN")),
            "fgm":        int(r.get("FGM", 0) or 0),
            "fga":        int(r.get("FGA", 0) or 0),
            "fg_pct":     round(float(r.get("FG_PCT", 0) or 0), 3),
            "fg3m":       int(r.get("FG3M", 0) or 0),
            "fg3a":       int(r.get("FG3A", 0) or 0),
            "fg3_pct":    round(float(r.get("FG3_PCT", 0) or 0), 3),
            "ftm":        int(r.get("FTM", 0) or 0),
            "fta":        int(r.get("FTA", 0) or 0),
            "ft_pct":     round(float(r.get("FT_PCT", 0) or 0), 3),
            "oreb":       int(r.get("OREB", 0) or 0),
            "dreb":       int(r.get("DREB", 0) or 0),
            "reb":        int(r.get("REB", 0) or 0),
            "ast":        int(r.get("AST", 0) or 0),
            "stl":        int(r.get("STL", 0) or 0),
            "blk":        int(r.get("BLK", 0) or 0),
            "tov":        int(r.get("TOV", 0) or 0),
            "pf":         int(r.get("PF", 0) or 0),
            "pts":        int(r.get("PTS", 0) or 0),
            "plus_minus": int(r.get("PLUS_MINUS", 0) or 0),
        }
        rows.append(row)

    rows.sort(key=lambda r: _parse_date(r["game_date"]), reverse=True)

    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(rows, f)

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2: Per-player — rolling splits (last 5/10/15/20)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_player_splits(
    player_id: int,
    season: str = "2024-25",
    force: bool = False,
) -> dict:
    """
    Fetch last-5/10/15/20 game rolling averages from PlayerDashboardByLastNGames.

    Returns:
    {
        "last5":  {"pts": X, "reb": X, "ast": X, "min": X, ...},
        "last10": {...},
        "last15": {...},
        "last20": {...},
    }
    Cached to data/nba/splits_{player_id}_{season}.json.
    """
    cache_path = os.path.join(_NBA_CACHE, f"splits_{player_id}_{season}.json")
    cache_fresh = (
        os.path.exists(cache_path)
        and (time.time() - os.path.getmtime(cache_path)) < _TTL["splits"] * 3600
    )
    if not force and cache_fresh:
        with open(cache_path) as f:
            return json.load(f)

    try:
        from nba_api.stats.endpoints import playerdashboardbylastngames
    except ImportError:
        raise RuntimeError("nba_api not installed")

    time.sleep(0.8)
    try:
        resp = playerdashboardbylastngames.PlayerDashboardByLastNGames(
            player_id=player_id, season=season, per_mode_detailed="PerGame", timeout=60
        )
        data = resp.get_normalized_dict()
    except Exception as e:
        print(f"  [scraper] splits fetch failed for player {player_id}: {e}")
        return {}

    _SPLIT_COLS = [
        "GP", "W", "L", "MIN", "FGM", "FGA", "FG_PCT",
        "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT",
        "OREB", "DREB", "REB", "AST", "TOV", "STL", "BLK",
        "PF", "PTS", "PLUS_MINUS",
    ]

    splits = {}
    key_map = {
        "Last5PlayerDashboard":  "last5",
        "Last10PlayerDashboard": "last10",
        "Last15PlayerDashboard": "last15",
        "Last20PlayerDashboard": "last20",
    }
    for api_key, out_key in key_map.items():
        rows = data.get(api_key, [])
        if not rows:
            continue
        row = rows[0]  # single summary row
        splits[out_key] = {
            col.lower(): (round(float(row[col]), 4) if row.get(col) is not None else None)
            for col in _SPLIT_COLS if col in row
        }

    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(splits, f)

    return splits


# ─────────────────────────────────────────────────────────────────────────────
# Coverage tracking
# ─────────────────────────────────────────────────────────────────────────────

def _load_coverage() -> dict:
    if os.path.exists(_COVERAGE_FILE):
        with open(_COVERAGE_FILE) as f:
            return json.load(f)
    return {}


def _save_coverage(cov: dict) -> None:
    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(_COVERAGE_FILE, "w") as f:
        json.dump(cov, f, indent=2)


def _coverage_score(player_data: dict) -> float:
    """0.0–1.0 based on how many metric groups are present for a player."""
    all_keys = set()
    for tier_cfg in _BATCH_TIERS.values():
        all_keys.update(tier_cfg["cols"].values())
    # Also count gamelog and splits presence
    total_groups = len(_BATCH_TIERS) + 2  # +gamelog +splits
    present = sum(1 for k in tier_cfg["cols"].values() if k in player_data
                  for tier_cfg in _BATCH_TIERS.values())
    # Normalise
    filled_tiers = sum(
        1 for tier_name, tier_cfg in _BATCH_TIERS.items()
        if any(v in player_data for v in tier_cfg["cols"].values())
    )
    has_gamelog = "gamelog_rows" in player_data
    has_splits  = "splits_last10_pts" in player_data
    return round((filled_tiers + has_gamelog + has_splits) / total_groups, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Self-improving loop
# ─────────────────────────────────────────────────────────────────────────────

def run_improvement_loop(
    season: str = "2024-25",
    max_players: int = 50,
    delay: float = 0.8,
    dry_run: bool = False,
) -> dict:
    """
    Self-improving data collection loop.

    1. Loads existing coverage report
    2. Fetches all batch tiers (stale ones only)
    3. For the top-N players by minutes, fetches Tier 2 (gamelog + splits) if missing/stale
    4. Updates coverage report
    5. Logs delta to vault improvement log

    Returns coverage delta: {"players_updated": N, "new_metrics_added": N, "coverage_pct": X}
    """
    print(f"\n[scraper] Starting improvement loop — season={season}, max_players={max_players}")
    t0 = time.time()

    # ── Step 1: Batch tier pull ──
    if not dry_run:
        merged = fetch_all_player_stats(season)
    else:
        merged = {}
        combined = os.path.join(_NBA_CACHE, f"player_full_{season}.json")
        if os.path.exists(combined):
            with open(combined) as f:
                merged = json.load(f)

    print(f"  [scraper] {len(merged)} players in merged batch data")

    # ── Step 2: Load old coverage + bulk-update batch tier coverage for all players ──
    old_coverage = _load_coverage()
    new_coverage = dict(old_coverage)

    # Update coverage for all players in merged (batch tiers already fetched above)
    for name, data in merged.items():
        player_id = data.get("player_id")
        if not player_id:
            continue
        prev = old_coverage.get(str(player_id), {})
        # Carry forward gamelog/splits info from existing coverage or cache files
        gamelog_cache = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
        if prev.get("has_gamelog") or (os.path.exists(gamelog_cache) and os.path.getsize(gamelog_cache) > 2):
            data.setdefault("gamelog_rows", 1)
        if prev.get("has_splits") or prev.get("splits_last10_pts") is not None:
            data.setdefault("splits_last10_pts", prev.get("splits_last10_pts", 0))
        score = _coverage_score(data)
        new_coverage[str(player_id)] = {
            "name":         name,
            "team":         data.get("team", ""),
            "min":          data.get("min", 0),
            "score":        score,
            "has_base":     any(v in data for v in _BATCH_TIERS["base"]["cols"].values()),
            "has_advanced": any(v in data for v in _BATCH_TIERS["advanced"]["cols"].values()),
            "has_scoring":  any(v in data for v in _BATCH_TIERS["scoring"]["cols"].values()),
            "has_misc":     any(v in data for v in _BATCH_TIERS["misc"]["cols"].values()),
            "has_gamelog":  "gamelog_rows" in data,
            "has_splits":   "splits_last10_pts" in data,
            "has_shotchart": prev.get("has_shotchart", False),
            "updated":      datetime.now().isoformat()[:16],
        }

    # ── Step 3: Tier 2 — pick top players by minutes, fill gamelog + splits ──
    # Sort by minutes descending to prioritise starters
    sorted_players = sorted(
        [(name, data) for name, data in merged.items() if data.get("min", 0) > 10],
        key=lambda x: x[1].get("min", 0),
        reverse=True,
    )[:max_players]

    players_updated = 0
    new_metrics = 0

    for name, data in sorted_players:
        player_id = data.get("player_id")
        if not player_id:
            continue

        prev_score = old_coverage.get(str(player_id), {}).get("score", 0.0)

        # Gamelog
        gamelog_cache = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
        gamelog_stale = (
            not os.path.exists(gamelog_cache)
            or (time.time() - os.path.getmtime(gamelog_cache)) > _TTL["gamelog"] * 3600
        )
        if gamelog_stale and not dry_run:
            rows = fetch_player_gamelog_full(player_id, season)
            if rows:
                data["gamelog_rows"] = len(rows)
                new_metrics += len([c for c in _GAMELOG_COLS if c.lower() in rows[0]])
                time.sleep(delay)

        # Splits
        splits_cache = os.path.join(_NBA_CACHE, f"splits_{player_id}_{season}.json")
        splits_stale = (
            not os.path.exists(splits_cache)
            or (time.time() - os.path.getmtime(splits_cache)) > _TTL["splits"] * 3600
        )
        if splits_stale and not dry_run:
            splits = fetch_player_splits(player_id, season)
            if splits.get("last10"):
                for k, v in splits["last10"].items():
                    data[f"splits_last10_{k}"] = v
                new_metrics += len(splits["last10"])
                time.sleep(delay)

        prev_entry = old_coverage.get(str(player_id), {})
        score = _coverage_score(data)
        new_coverage[str(player_id)] = {
            "name":         name,
            "team":         data.get("team", ""),
            "min":          data.get("min", 0),
            "score":        score,
            "has_base":     any(v in data for v in _BATCH_TIERS["base"]["cols"].values()),
            "has_advanced": any(v in data for v in _BATCH_TIERS["advanced"]["cols"].values()),
            "has_scoring":  any(v in data for v in _BATCH_TIERS["scoring"]["cols"].values()),
            "has_misc":     any(v in data for v in _BATCH_TIERS["misc"]["cols"].values()),
            "has_gamelog":  "gamelog_rows" in data,
            "has_splits":   "splits_last10_pts" in data,
            "has_shotchart": prev_entry.get("has_shotchart", False),
            "updated":      datetime.now().isoformat()[:16],
        }
        if score > prev_score:
            players_updated += 1

    _save_coverage(new_coverage)

    # ── Step 4: Compute summary ──
    scores = [v["score"] for v in new_coverage.values()]
    avg_coverage = round(sum(scores) / len(scores), 3) if scores else 0.0
    elapsed = round(time.time() - t0, 1)

    report = {
        "timestamp":        datetime.now().isoformat()[:16],
        "season":           season,
        "players_total":    len(merged),
        "players_updated":  players_updated,
        "new_metrics_added": new_metrics,
        "coverage_pct":     avg_coverage,
        "elapsed_secs":     elapsed,
    }

    # ── Step 5: Log to vault ──
    _log_improvement(report)

    print(f"  [scraper] Done. {players_updated} players updated, "
          f"coverage={avg_coverage:.1%}, {elapsed}s")
    return report


def _log_improvement(report: dict) -> None:
    """Append a scraper run entry to the vault improvement log."""
    if not os.path.exists(_VAULT_LOG):
        return
    entry = (
        f"\n### {report['timestamp']} — Player Scraper Loop\n"
        f"- Season: {report['season']}\n"
        f"- Players in league: {report['players_total']}\n"
        f"- Players updated (coverage improved): {report['players_updated']}\n"
        f"- New metric columns added: {report['new_metrics_added']}\n"
        f"- Avg coverage score: {report['coverage_pct']:.1%}\n"
        f"- Elapsed: {report['elapsed_secs']}s\n"
    )
    with open(_VAULT_LOG, "a", encoding="utf-8") as f:
        f.write(entry)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: get fully merged player profile
# ─────────────────────────────────────────────────────────────────────────────

def get_player_profile(
    player_name: str,
    season: str = "2024-25",
    include_gamelog: bool = True,
    include_splits: bool = True,
) -> dict:
    """
    Return the full metric profile for a single player.

    Merges batch stats + gamelog summary + splits into one dict.
    Fetches live if not cached.

    Args:
        player_name: Display name (e.g. "LeBron James")
        season: e.g. "2024-25"
        include_gamelog: Whether to include per-game rows
        include_splits: Whether to include last-N splits

    Returns:
        Flat dict with all available metrics. Empty dict if player not found.
    """
    import unicodedata

    def _norm(s: str) -> str:
        return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()

    combined_path = os.path.join(_NBA_CACHE, f"player_full_{season}.json")
    if os.path.exists(combined_path):
        with open(combined_path) as f:
            merged = json.load(f)
    else:
        merged = fetch_all_player_stats(season)

    key = _norm(player_name)
    profile = dict(merged.get(key, {}))
    if not profile:
        return {}

    player_id = profile.get("player_id")
    if not player_id:
        return profile

    if include_gamelog:
        rows = fetch_player_gamelog_full(player_id, season)
        profile["gamelog"] = rows
        profile["gamelog_games"] = len(rows)
        if rows:
            last5 = rows[:5]
            profile["l5_pts"]  = round(sum(r["pts"]  for r in last5) / len(last5), 1)
            profile["l5_reb"]  = round(sum(r["reb"]  for r in last5) / len(last5), 1)
            profile["l5_ast"]  = round(sum(r["ast"]  for r in last5) / len(last5), 1)
            profile["l5_stl"]  = round(sum(r["stl"]  for r in last5) / len(last5), 1)
            profile["l5_blk"]  = round(sum(r["blk"]  for r in last5) / len(last5), 1)
            profile["l5_tov"]  = round(sum(r["tov"]  for r in last5) / len(last5), 1)
            profile["l5_min"]  = round(sum(r["min"]  for r in last5) / len(last5), 1)
            profile["l5_ts_pct"] = _compute_ts(last5)

    if include_splits:
        splits = fetch_player_splits(player_id, season)
        profile["splits"] = splits

    return profile


def _compute_ts(games: list) -> float:
    """True shooting % across a list of game dicts."""
    pts = sum(g.get("pts", 0) for g in games)
    fga = sum(g.get("fga", 0) for g in games)
    fta = sum(g.get("fta", 0) for g in games)
    denom = 2 * (fga + 0.44 * fta)
    return round(pts / denom, 3) if denom > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NBA player scraper")
    parser.add_argument("--loop",       action="store_true", help="Run improvement loop")
    parser.add_argument("--player",     type=str,            help="Get full profile for a player")
    parser.add_argument("--season",     default="2024-25",   help="Season (e.g. 2024-25)")
    parser.add_argument("--max",        type=int, default=50, help="Max players for Tier 2 in loop")
    parser.add_argument("--dry-run",    action="store_true", help="Skip API calls, show coverage only")
    parser.add_argument("--force",      action="store_true", help="Ignore cache, re-fetch everything")
    args = parser.parse_args()

    if args.loop:
        report = run_improvement_loop(
            season=args.season,
            max_players=args.max,
            dry_run=args.dry_run,
        )
        print(json.dumps(report, indent=2))

    elif args.player:
        profile = get_player_profile(args.player, season=args.season)
        if not profile:
            print(f"Player '{args.player}' not found in {args.season} data")
        else:
            # Print compact summary
            gamelog = profile.pop("gamelog", [])
            print(json.dumps(profile, indent=2))
            if gamelog:
                print(f"\nLast 5 games:")
                for g in gamelog[:5]:
                    print(f"  {g['game_date']}  {g['matchup']:<22}  "
                          f"{g['pts']:>3}pts  {g['reb']:>2}reb  {g['ast']:>2}ast  "
                          f"{g['stl']:>2}stl  {g['blk']:>2}blk  {g['tov']:>2}tov  "
                          f"{g['min']:>5.1f}min  {g['wl']}")

    else:
        parser.print_help()
