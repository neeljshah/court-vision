"""
data_loader.py — Unified data loading layer for the NBA AI system.

Provides three high-level loaders that abstract over PostgreSQL (primary)
and CSV fallback (for environments without a live DB):

    load_tracking_data(game_id)              -> pd.DataFrame
    load_player_features(player_id, season)  -> dict
    load_game_context(game_id)               -> dict

Usage:
    from src.pipeline.data_loader import load_tracking_data
    df = load_tracking_data("0022401001")
"""

from __future__ import annotations

import json
import os
from typing import Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA_DIR   = os.path.join(PROJECT_DIR, "data")
_NBA_CACHE  = os.path.join(_DATA_DIR, "nba")

# CSV fallback paths (used when PostgreSQL is unavailable)
_TRACKING_CSV  = os.path.join(_DATA_DIR, "tracking_data.csv")
_SCHEDULE_JSON = os.path.join(_NBA_CACHE, "schedule_context.json")


# ── load_tracking_data ────────────────────────────────────────────────────────

def load_tracking_data(game_id: str, db_url: Optional[str] = None) -> pd.DataFrame:
    """
    Load per-frame tracking data for a game.

    Primary source: PostgreSQL ``tracking_data`` table.
    Fallback: ``data/tracking_data.csv`` (filtered by game_id if present).

    Args:
        game_id: NBA game ID string (e.g. '0022401001').
        db_url:  Optional PostgreSQL connection URL; if None reads DATABASE_URL env var.

    Returns:
        DataFrame with columns: frame, player_id, team_id, x_position, y_position,
        speed, acceleration, ball_possession, event, jersey_number, player_name,
        timestamp (and any extras in the source).
        Empty DataFrame if no data found.
    """
    df = _try_pg_tracking(game_id, db_url)
    if df is not None:
        return df

    return _csv_tracking_fallback(game_id)


def _try_pg_tracking(game_id: str, db_url: Optional[str]) -> Optional[pd.DataFrame]:
    """Attempt to load tracking rows from PostgreSQL. Returns None on any failure."""
    url = db_url or os.environ.get("DATABASE_URL")
    if not url:
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tracking_data WHERE game_id = %s ORDER BY frame",
                (game_id,),
            )
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        conn.close()
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows, columns=cols)
    except Exception:
        return None


def _csv_tracking_fallback(game_id: str) -> pd.DataFrame:
    """Load from tracking_data.csv, filtering by game_id."""
    if not os.path.exists(_TRACKING_CSV):
        return pd.DataFrame()
    df = pd.read_csv(_TRACKING_CSV)
    if "game_id" in df.columns:
        # Coerce to string for comparison regardless of how pandas inferred the type
        mask = df["game_id"].astype(str) == str(game_id)
        return df[mask].reset_index(drop=True)
    return df.reset_index(drop=True)


# ── load_player_features ──────────────────────────────────────────────────────

def load_player_features(
    player_id: int,
    season: str = "2024-25",
    db_url: Optional[str] = None,
) -> dict:
    """
    Load all features for a player: base stats, advanced stats, splits, injury status.

    Sources (merged in priority order):
      1. ``data/nba/players_{season}.json``  — base + advanced stats
      2. ``data/nba/gamelogs_{season}.json`` — gamelog + rolling averages
      3. ``data/nba/injury_report.json``     — current injury status

    Args:
        player_id: NBA player ID integer.
        season:    NBA season string (e.g. '2024-25').
        db_url:    Reserved for future PostgreSQL expansion; currently unused.

    Returns:
        Merged dict with keys:
          player_id, player_name, season,
          pts, reb, ast, min, fg_pct, fg3_pct, ft_pct  (base stats)
          usg_pct, ts_pct, off_rtg, def_rtg, net_rtg, pie  (advanced)
          l5_pts, l5_reb, l5_ast  (last-5 rolling, if available)
          injury_status  (str: Out / Questionable / etc.)
        Returns {"player_id": player_id, "found": False} if no data found.
    """
    features: dict = {"player_id": player_id, "season": season, "found": False}

    # 1. Base + advanced stats
    player_cache = os.path.join(_NBA_CACHE, f"players_{season}.json")
    if os.path.exists(player_cache):
        try:
            with open(player_cache, encoding="utf-8") as f:
                all_players = json.load(f)
            pid_str = str(player_id)
            if pid_str in all_players:
                features.update(all_players[pid_str])
                features["found"] = True
        except Exception:
            pass

    # 2. Gamelog rolling averages
    gamelog_cache = os.path.join(_NBA_CACHE, f"gamelogs_{season}.json")
    if os.path.exists(gamelog_cache):
        try:
            with open(gamelog_cache, encoding="utf-8") as f:
                gamelogs = json.load(f)
            pid_str = str(player_id)
            if pid_str in gamelogs:
                gl = gamelogs[pid_str]
                # Compute simple last-5 averages if raw game list present
                games = gl.get("games", [])
                if len(games) >= 1:
                    last5 = games[-5:]
                    for stat in ("pts", "reb", "ast"):
                        vals = [g.get(stat, 0) for g in last5 if stat in g]
                        if vals:
                            features[f"l5_{stat}"] = round(sum(vals) / len(vals), 2)
                features["found"] = True
        except Exception:
            pass

    # 3. Injury status
    injury_cache = os.path.join(_NBA_CACHE, "injury_report.json")
    features["injury_status"] = "Available"
    if os.path.exists(injury_cache):
        try:
            with open(injury_cache, encoding="utf-8") as f:
                report = json.load(f)
            player_name = features.get("player_name", "")
            if player_name:
                import unicodedata

                def _norm(s: str) -> str:
                    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()

                query = _norm(player_name)
                for inj in report.get("injuries", []):
                    if _norm(inj.get("player_name", "")) == query:
                        features["injury_status"] = inj.get("status", "Available")
                        break
        except Exception:
            pass

    return features


# ── load_game_context ─────────────────────────────────────────────────────────

def load_game_context(game_id: str, season: str = "2024-25") -> dict:
    """
    Load game-level context: teams, date, referees, rest, back-to-back.

    Sources:
      1. ``data/nba/schedule_context.json``   — rest/travel/B2B info
      2. ``data/nba/boxscores.json``           — refs if available

    Args:
        game_id: NBA game ID string (e.g. '0022401001').
        season:  NBA season string.

    Returns:
        {
          "game_id":    str,
          "home_team":  str,   # abbreviation
          "away_team":  str,
          "date":       str,   # ISO date or ""
          "refs":       list,  # list of referee names (empty if unknown)
          "home_rest":  int,   # days since last game (0 if unknown)
          "away_rest":  int,
          "home_b2b":   bool,
          "away_b2b":   bool,
          "found":      bool,
        }
    """
    ctx: dict = {
        "game_id":   game_id,
        "home_team": "",
        "away_team": "",
        "date":      "",
        "refs":      [],
        "home_rest": 0,
        "away_rest": 0,
        "home_b2b":  False,
        "away_b2b":  False,
        "found":     False,
    }

    # 1. Schedule context
    if os.path.exists(_SCHEDULE_JSON):
        try:
            with open(_SCHEDULE_JSON, encoding="utf-8") as f:
                sched = json.load(f)
            game_sched = sched.get(game_id, {})
            if game_sched:
                ctx.update({
                    "home_team": game_sched.get("home_team", ""),
                    "away_team": game_sched.get("away_team", ""),
                    "date":      game_sched.get("game_date", ""),
                    "home_rest": int(game_sched.get("home_rest_days", 0)),
                    "away_rest": int(game_sched.get("away_rest_days", 0)),
                    "home_b2b":  bool(game_sched.get("home_b2b", False)),
                    "away_b2b":  bool(game_sched.get("away_b2b", False)),
                })
                ctx["found"] = True
        except Exception:
            pass

    # 2. Boxscores for refs
    boxscores_path = os.path.join(_NBA_CACHE, "boxscores.json")
    if os.path.exists(boxscores_path):
        try:
            with open(boxscores_path, encoding="utf-8") as f:
                boxes = json.load(f)
            game_box = boxes.get(game_id, {})
            if game_box:
                ctx["refs"] = game_box.get("officials", [])
                if not ctx.get("home_team"):
                    ctx["home_team"] = game_box.get("home_team", "")
                if not ctx.get("away_team"):
                    ctx["away_team"] = game_box.get("away_team", "")
                ctx["found"] = True
        except Exception:
            pass

    return ctx
