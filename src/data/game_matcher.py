"""
game_matcher.py — Match a clip label to a real NBA game and fetch its stats.

Given a clip label like "gsw_lakers_2025" or "bos_mia_playoffs", this module:
  1. Parses team abbreviations from the label
  2. Searches NBA API for games between those two teams in the right season
  3. Returns box score (players, FGA, minutes) and shot totals for validation

All data is cached under data/nba/ to avoid repeat API calls.

Public API
----------
    match_clip_to_game(label)           -> GameMatch  (namedtuple)
    fetch_game_box_score(game_id)       -> dict
    get_comparison_stats(label)         -> dict  (all stats for loop scoring)
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE  = os.path.join(PROJECT_DIR, "data", "nba")

# ── Team abbreviation aliases ─────────────────────────────────────────────────
# Maps shorthand used in clip labels → official NBA abbreviations
_LABEL_TO_ABBREV: dict[str, str] = {
    "gsw":    "GSW",
    "warriors": "GSW",
    "lakers": "LAL",
    "lal":    "LAL",
    "bos":    "BOS",
    "celtics": "BOS",
    "mia":    "MIA",
    "heat":   "MIA",
    "mil":    "MIL",
    "bucks":  "MIL",
    "chi":    "CHI",
    "bulls":  "CHI",
    "phi":    "PHI",
    "76ers":  "PHI",
    "tor":    "TOR",
    "raptors": "TOR",
    "den":    "DEN",
    "nuggets": "DEN",
    "phx":    "PHX",
    "suns":   "PHX",
    "okc":    "OKC",
    "thunder": "OKC",
    "dal":    "DAL",
    "mavericks": "DAL",
    "sas":    "SAS",
    "spurs":  "SAS",
    "bkn":    "BKN",
    "nets":   "BKN",
    "mem":    "MEM",
    "grizzlies": "MEM",
    "nop":    "NOP",
    "pelicans": "NOP",
    "sac":    "SAC",
    "kings":  "SAC",
    "por":    "POR",
    "trailblazers": "POR",
    "atl":    "ATL",
    "hawks":  "ATL",
    "ind":    "IND",
    "pacers": "IND",
    "cavs":   "CLE",
    "cavaliers": "CLE",
    "cle":    "CLE",
}

# ── Label → season mapping ────────────────────────────────────────────────────
def _label_to_season(label: str) -> tuple[str, str]:
    """Return (season_str, season_type) from a clip label."""
    label_lower = label.lower()
    if "playoffs" in label_lower or "finals" in label_lower:
        if "2016" in label_lower:
            return "2015-16", "Playoffs"
        if "2024" in label_lower:
            return "2023-24", "Playoffs"
        return "2023-24", "Playoffs"
    if "2025" in label_lower:
        return "2024-25", "Regular Season"
    if "2024" in label_lower:
        return "2023-24", "Regular Season"
    return "2024-25", "Regular Season"


def _parse_teams(label: str) -> tuple[Optional[str], Optional[str]]:
    """Extract (team1_abbrev, team2_abbrev) from a clip label string."""
    parts = label.lower().replace("-", "_").split("_")
    found = []
    for part in parts:
        abbrev = _LABEL_TO_ABBREV.get(part)
        if abbrev and abbrev not in found:
            found.append(abbrev)
        if len(found) == 2:
            break
    t1 = found[0] if len(found) >= 1 else None
    t2 = found[1] if len(found) >= 2 else None
    return t1, t2


def _rate_limit():
    time.sleep(0.7)


def _load(path: str):
    with open(path) as f:
        return json.load(f)


def _save(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ── Game search ───────────────────────────────────────────────────────────────

def find_game_id(
    team1_abbrev: str,
    team2_abbrev: str,
    season: str = "2024-25",
    season_type: str = "Regular Season",
) -> Optional[str]:
    """
    Find the most recent game ID between two teams in a season.

    Args:
        team1_abbrev: Home team abbreviation (e.g. "GSW")
        team2_abbrev: Away team abbreviation (e.g. "LAL")
        season:       e.g. "2024-25"
        season_type:  "Regular Season" | "Playoffs"

    Returns:
        Game ID string or None if not found.
    """
    cache_key = f"matchup_{team1_abbrev}_{team2_abbrev}_{season}_{season_type[:3]}"
    cache_path = os.path.join(_NBA_CACHE, f"{cache_key}.json")
    if os.path.exists(cache_path):
        data = _load(cache_path)
        return data.get("game_id")

    try:
        from nba_api.stats.static import teams as nba_teams
        from nba_api.stats.endpoints import teamgamelog

        all_teams = nba_teams.get_teams()

        def _get_team_id(abbrev: str) -> Optional[int]:
            t = next((x for x in all_teams if x["abbreviation"] == abbrev), None)
            return t["id"] if t else None

        tid1 = _get_team_id(team1_abbrev)
        if tid1 is None:
            return None

        _rate_limit()
        log = teamgamelog.TeamGameLog(
            team_id=tid1,
            season=season,
            season_type_all_star=season_type,
        )
        df = log.get_data_frames()[0]
        if df.empty:
            return None

        # Filter to games vs team2
        opp_col = "MATCHUP"
        if opp_col in df.columns:
            mask = df[opp_col].str.contains(team2_abbrev, case=False, na=False)
            filtered = df[mask]
            if not filtered.empty:
                game_id = filtered.iloc[0]["Game_ID"]
                _save(cache_path, {"game_id": game_id, "teams": [team1_abbrev, team2_abbrev]})
                return game_id

        # Fallback: just return the most recent game
        game_id = df.iloc[0]["Game_ID"]
        _save(cache_path, {"game_id": game_id, "teams": [team1_abbrev, team2_abbrev]})
        return game_id

    except Exception as e:
        print(f"[game_matcher] find_game_id failed: {e}")
        return None


# ── Box score ─────────────────────────────────────────────────────────────────

def fetch_game_box_score(game_id: str) -> dict:
    """
    Fetch box score summary for a game.

    Returns:
        {
            "game_id": str,
            "home_team": str,
            "away_team": str,
            "home_score": int,
            "away_score": int,
            "total_fga": int,        # both teams combined
            "home_fga": int,
            "away_fga": int,
            "total_players": int,    # players with >0 minutes
            "players": [
                {
                    "name": str,
                    "team_abbreviation": str,
                    "min": float,
                    "fga": int,
                    "fgm": int,
                    "pts": int,
                }
            ]
        }
    """
    cache_path = os.path.join(_NBA_CACHE, f"boxscore_{game_id}.json")
    if os.path.exists(cache_path):
        return _load(cache_path)

    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2

        _rate_limit()
        box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        frames = box.get_data_frames()
        players_df = frames[0]   # player stats
        teams_df   = frames[1]   # team totals

        result: dict = {"game_id": game_id, "players": []}

        if not teams_df.empty:
            home = teams_df[teams_df["TEAM_ID"] == teams_df["TEAM_ID"].iloc[0]].iloc[0]
            away = teams_df.iloc[1] if len(teams_df) > 1 else home
            result["home_team"]  = str(teams_df.iloc[0].get("TEAM_ABBREVIATION", ""))
            result["away_team"]  = str(teams_df.iloc[1].get("TEAM_ABBREVIATION", "")) if len(teams_df) > 1 else ""
            result["home_score"] = int(teams_df.iloc[0].get("PTS", 0) or 0)
            result["away_score"] = int(teams_df.iloc[1].get("PTS", 0) or 0) if len(teams_df) > 1 else 0
            result["home_fga"]   = int(teams_df.iloc[0].get("FGA", 0) or 0)
            result["away_fga"]   = int(teams_df.iloc[1].get("FGA", 0) or 0) if len(teams_df) > 1 else 0
            result["total_fga"]  = result["home_fga"] + result["away_fga"]

        if not players_df.empty:
            active = players_df[players_df["MIN"].notna() & (players_df["MIN"] != "0:00")]
            result["total_players"] = len(active)
            for _, row in active.iterrows():
                min_str = str(row.get("MIN", "0") or "0")
                try:
                    mins = float(min_str.split(":")[0]) + float(min_str.split(":")[1]) / 60 if ":" in min_str else float(min_str)
                except Exception:
                    mins = 0.0
                result["players"].append({
                    "name":              str(row.get("PLAYER_NAME", "")),
                    "team_abbreviation": str(row.get("TEAM_ABBREVIATION", "")),
                    "min":               round(mins, 1),
                    "fga":               int(row.get("FGA", 0) or 0),
                    "fgm":               int(row.get("FGM", 0) or 0),
                    "pts":               int(row.get("PTS", 0) or 0),
                })

        _save(cache_path, result)
        return result

    except Exception as e:
        print(f"[game_matcher] fetch_game_box_score failed for {game_id}: {e}")
        return {"game_id": game_id, "error": str(e), "players": []}


# ── Shot count ────────────────────────────────────────────────────────────────

def fetch_game_shot_count(game_id: str) -> dict:
    """
    Fetch total shot attempts and made shots for a game (both teams).

    Returns:
        {
            "total_fga": int,
            "total_fgm": int,
            "fg_pct": float,
            "shots_per_minute": float,   # FGA / 48
            "three_pa": int,
        }
    """
    cache_path = os.path.join(_NBA_CACHE, f"shots_count_{game_id}.json")
    if os.path.exists(cache_path):
        return _load(cache_path)

    try:
        from nba_api.stats.endpoints import shotchartdetail

        _rate_limit()
        sc = shotchartdetail.ShotChartDetail(
            team_id=0,
            player_id=0,
            game_id_nullable=game_id,
            context_measure_simple="FGA",
        )
        df = sc.get_data_frames()[0]

        total_fga = len(df)
        total_fgm = int(df["SHOT_MADE_FLAG"].sum()) if "SHOT_MADE_FLAG" in df.columns else 0
        three_pa  = int((df["SHOT_TYPE"] == "3PT Field Goal").sum()) if "SHOT_TYPE" in df.columns else 0

        result = {
            "total_fga":       total_fga,
            "total_fgm":       total_fgm,
            "fg_pct":          round(total_fgm / max(1, total_fga), 3),
            "shots_per_minute": round(total_fga / 48.0, 2),
            "three_pa":        three_pa,
        }
        _save(cache_path, result)
        return result

    except Exception as e:
        print(f"[game_matcher] fetch_game_shot_count failed for {game_id}: {e}")
        return {}


# ── Main public API ───────────────────────────────────────────────────────────

def get_comparison_stats(label: str) -> dict:
    """
    Given a clip label, return all real NBA stats for tracker validation.

    This is the main entry point for autonomous_loop.py.

    Returns:
        {
            "clip_label":       str,
            "game_id":          str or None,
            "team1":            str,
            "team2":            str,
            "season":           str,
            "season_type":      str,
            "total_fga":        int,      # from box score
            "total_players":    int,      # players with playing time
            "shots_per_minute": float,    # real game FGA/48
            "home_score":       int,
            "away_score":       int,
            "data_source":      "nba_api" | "league_average",
        }
    """
    cache_path = os.path.join(_NBA_CACHE, f"comparison_{label.replace(' ', '_')[:60]}.json")
    if os.path.exists(cache_path):
        cached = _load(cache_path)
        # Refresh if older than 7 days
        import time as _time
        mtime = os.path.getmtime(cache_path)
        if _time.time() - mtime < 7 * 86400:
            return cached

    team1, team2 = _parse_teams(label)
    season, season_type = _label_to_season(label)

    result: dict = {
        "clip_label":       label,
        "game_id":          None,
        "team1":            team1 or "UNK",
        "team2":            team2 or "UNK",
        "season":           season,
        "season_type":      season_type,
        # Fallback to NBA averages
        "total_fga":        177,         # ~88.5 FGA/team × 2
        "total_players":    10,
        "shots_per_minute": 1.84,
        "home_score":       0,
        "away_score":       0,
        "data_source":      "league_average",
    }

    if team1 is None:
        print(f"[game_matcher] Could not parse teams from label: {label}")
        return result

    game_id = find_game_id(team1, team2 or "", season, season_type) if team2 else None

    if game_id:
        result["game_id"] = game_id
        box = fetch_game_box_score(game_id)
        if "error" not in box and box.get("total_fga", 0) > 0:
            result["total_fga"]       = box.get("total_fga", result["total_fga"])
            result["total_players"]   = box.get("total_players", result["total_players"])
            result["home_score"]      = box.get("home_score", 0)
            result["away_score"]      = box.get("away_score", 0)
            result["shots_per_minute"] = round(result["total_fga"] / 48.0, 2)
            result["data_source"]     = "nba_api"
            print(f"[game_matcher] {label} → game {game_id}: {result['total_fga']} FGA, {result['total_players']} players")
        else:
            # Try shot chart count as fallback
            shot_data = fetch_game_shot_count(game_id)
            if shot_data.get("total_fga", 0) > 0:
                result["total_fga"]        = shot_data["total_fga"]
                result["shots_per_minute"] = shot_data.get("shots_per_minute", result["shots_per_minute"])
                result["data_source"]      = "nba_api"

    _save(cache_path, result)
    return result
