"""
feature_assembler.py — Single-call feature aggregator for all data sources.

assemble_features(game_id, player_id, date) → flat dict of every available feature.
Missing features are logged as warnings and returned as NaN — never raises.

Public API
----------
    assemble_features(game_id, player_id, date, season) -> dict
    get_player_id_map(season)                           -> dict  {name: player_id}
"""

from __future__ import annotations

import glob
import json
import logging
import math
import os
import sys
import time
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_EXT_CACHE = os.path.join(PROJECT_DIR, "data", "external")
_MODEL_DIR  = os.path.join(PROJECT_DIR, "data", "models")

log = logging.getLogger(__name__)


# ── Name normalisation ────────────────────────────────────────────────────────

import unicodedata

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


# ── JSON cache helpers ────────────────────────────────────────────────────────

_JSON_CACHE: dict[str, object] = {}

def _load(path: str) -> object:
    if path not in _JSON_CACHE:
        try:
            with open(path) as f:
                _JSON_CACHE[path] = json.load(f)
        except Exception:
            _JSON_CACHE[path] = None
    return _JSON_CACHE[path]


def _find_by_player_id(data_list: list, player_id: int) -> Optional[dict]:
    """Search list for dict with player_id field matching."""
    for row in data_list:
        if isinstance(row, dict) and str(row.get("player_id", "")) == str(player_id):
            return row
    return None


def _find_by_name(data_list: list, player_name: str) -> Optional[dict]:
    """Search list for dict whose player_name field normalises to target."""
    target = _norm(player_name)
    for row in data_list:
        if isinstance(row, dict):
            for key in ("player_name", "PLAYER_NAME", "name"):
                val = row.get(key, "")
                if val and _norm(str(val)) == target:
                    return row
    return None


# ── Gamelog helpers ───────────────────────────────────────────────────────────

def _parse_min(val) -> float:
    if val is None:
        return float("nan")
    s = str(val).strip()
    if s in ("", "None", "null"):
        return float("nan")
    if s in ("0", "0:00"):
        return 0.0
    if ":" in s:
        parts = s.split(":")
        try:
            return float(parts[0]) + float(parts[1]) / 60
        except Exception:
            return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def _gamelog_rolling(logs: list[dict], n: int, field: str) -> float:
    """Rolling average of `field` over last n games (min played > 0)."""
    played = [g for g in logs if _parse_min(g.get("min", 0)) > 0][-n:]
    if not played:
        return float("nan")
    vals = [float(g.get(field, 0) or 0) for g in played]
    return float(np.mean(vals))


def _gamelogs_for_player(player_id: int, season: str) -> list[dict]:
    """Load individual gamelog file for player."""
    path = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
    data = _load(path)
    if isinstance(data, list):
        # Sort by game_date ascending
        try:
            return sorted(data, key=lambda g: g.get("game_date", ""))
        except Exception:
            return data
    return []


# ── Shot dashboard ─────────────────────────────────────────────────────────────

def _shot_dashboard_for_player(player_id: int, season: str) -> dict:
    path = os.path.join(_NBA_CACHE, f"shot_dashboard_{player_id}_{season}.json")
    data = _load(path)
    if isinstance(data, dict):
        return data
    return {}


# ── Hustle stats ───────────────────────────────────────────────────────────────

def _hustle_for_player(player_id: int, season: str) -> dict:
    path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
    data = _load(path)
    if isinstance(data, list):
        row = _find_by_player_id(data, player_id)
        return row or {}
    return {}


# ── On/Off splits ──────────────────────────────────────────────────────────────

def _on_off_for_player(player_id: int, season: str) -> dict:
    path = os.path.join(_NBA_CACHE, f"on_off_{season}.json")
    data = _load(path)
    if isinstance(data, list):
        row = _find_by_player_id(data, player_id)
        return row or {}
    return {}


# ── Defender zone ──────────────────────────────────────────────────────────────

def _defender_zone_for_player(player_id: int, season: str) -> dict:
    path = os.path.join(_NBA_CACHE, f"defender_zone_{season}.json")
    data = _load(path)
    if isinstance(data, list):
        row = _find_by_player_id(data, player_id)
        return row or {}
    return {}


# ── Matchups ───────────────────────────────────────────────────────────────────

def _matchup_for_player(player_id: int, season: str) -> list[dict]:
    path = os.path.join(_NBA_CACHE, f"matchups_{season}.json")
    data = _load(path)
    if isinstance(data, list):
        return [r for r in data if str(r.get("off_player_id", "")) == str(player_id)
                or str(r.get("def_player_id", "")) == str(player_id)]
    return []


# ── Synergy ────────────────────────────────────────────────────────────────────

_SYNERGY_CACHE: Optional[list] = None

def _synergy_for_player(player_id: int, season: str) -> dict:
    """Return dict of {play_type: ppp} for player from synergy data."""
    paths = glob.glob(os.path.join(_NBA_CACHE, f"synergy_*_{season}.json"))
    result: dict = {}
    for p in paths:
        data = _load(p)
        if isinstance(data, list):
            row = _find_by_player_id(data, player_id)
            if row and row.get("play_type"):
                result[row["play_type"]] = float(row.get("ppp", 0) or 0)
    return result


# ── BBRef advanced ─────────────────────────────────────────────────────────────

def _bbref_for_player(player_id: int, player_name: str, season: str) -> dict:
    # BBRef uses names not IDs — match by name
    year = season.split("-")[0]
    path = os.path.join(_EXT_CACHE, f"bbref_advanced_{season}.json")
    data = _load(path)
    if isinstance(data, list) and player_name:
        row = _find_by_name(data, player_name)
        return row or {}
    return {}


# ── Contracts ──────────────────────────────────────────────────────────────────

def _contract_for_player(player_id: int, player_name: str) -> dict:
    path = os.path.join(_EXT_CACHE, "contracts_2024-25.json")
    data = _load(path)
    if isinstance(data, list) and player_name:
        row = _find_by_name(data, player_name)
        return row or {}
    return {}


# ── Historical lines ───────────────────────────────────────────────────────────

def _historical_lines(season: str) -> list[dict]:
    path = os.path.join(_EXT_CACHE, f"historical_lines_{season}.json")
    data = _load(path)
    return data if isinstance(data, list) else []


# ── Existing model outputs ─────────────────────────────────────────────────────

def _load_model_output(model_name: str) -> dict:
    for ext in (".json", ".pkl"):
        p = os.path.join(_MODEL_DIR, f"{model_name}{ext}")
        if os.path.exists(p) and ext == ".json":
            try:
                return json.load(open(p))
            except Exception:
                pass
    return {}


# ── Schedule context ───────────────────────────────────────────────────────────

def _schedule_context(game_id: Optional[str], team_abbrev: Optional[str]) -> dict:
    if not game_id or not team_abbrev:
        return {}
    try:
        from src.data.schedule_context import get_game_context
        return get_game_context(game_id, team_abbrev) or {}
    except Exception as e:
        log.debug("schedule_context unavailable: %s", e)
        return {}


# ── Injury monitor ─────────────────────────────────────────────────────────────

def _injury_status(player_name: str) -> dict:
    try:
        from src.data.injury_monitor import InjuryMonitor
        mon = InjuryMonitor()
        return mon.get_injury_status(player_name) or {}
    except Exception as e:
        log.debug("injury_monitor unavailable: %s", e)
        return {}


# ── Current props ──────────────────────────────────────────────────────────────

def _current_props(player_name: str) -> dict:
    try:
        from src.data.props_scraper import get_player_props
        return get_player_props(player_name) or {}
    except Exception as e:
        log.debug("props_scraper unavailable: %s", e)
        return {}


# ── Player name lookup ────────────────────────────────────────────────────────

_ID_TO_NAME: dict[int, str] = {}

def get_player_id_map(season: str = "2024-25") -> dict[str, int]:
    """Return {player_name_normalised: player_id} from gamelogs."""
    path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    data = _load(path)
    result: dict[str, int] = {}
    if isinstance(data, dict):
        for name, info in data.items():
            if isinstance(info, dict):
                pid = info.get("player_id") or info.get("id")
                if pid:
                    result[_norm(name)] = int(pid)
    return result


def _resolve_player_name(player_id: int, season: str = "2024-25") -> str:
    """Best-effort reverse lookup of player_id → player_name."""
    global _ID_TO_NAME
    if player_id in _ID_TO_NAME:
        return _ID_TO_NAME[player_id]
    # Search gamelog files
    path = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
    data = _load(path)
    if isinstance(data, list) and data:
        name = data[0].get("player_name", "") or data[0].get("PLAYER_NAME", "")
        if name:
            _ID_TO_NAME[player_id] = name
            return name
    # Try hustle stats
    hustle_path = os.path.join(_NBA_CACHE, f"hustle_stats_{season}.json")
    hustle = _load(hustle_path)
    if isinstance(hustle, list):
        row = _find_by_player_id(hustle, player_id)
        if row and row.get("player_name"):
            _ID_TO_NAME[player_id] = row["player_name"]
            return row["player_name"]
    return ""


# ── Main assembler ─────────────────────────────────────────────────────────────

def assemble_features(
    game_id: Optional[str],
    player_id: int,
    date: Optional[str] = None,
    season: str = "2024-25",
    team_abbrev: Optional[str] = None,
    opp_team: Optional[str] = None,
) -> dict:
    """
    Pull every available feature for a player into a single flat dict.

    Missing features are NaN — never raises.

    Args:
        game_id:     NBA game ID string (e.g. '0022400851').
        player_id:   NBA player ID integer.
        date:        ISO date string 'YYYY-MM-DD' (optional).
        season:      Season string '2024-25'.
        team_abbrev: Team abbreviation for schedule context (e.g. 'GSW').
        opp_team:    Opponent abbreviation (e.g. 'BOS').

    Returns:
        Flat dict with all available features. Unknown/missing → NaN.
    """
    feats: dict = {
        "player_id": player_id,
        "game_id": game_id or "",
        "date": date or "",
        "season": season,
    }
    missing: list[str] = []

    player_name = _resolve_player_name(player_id, season)
    feats["player_name"] = player_name

    # ── 1. Gamelogs rolling stats ─────────────────────────────────────────────
    logs = _gamelogs_for_player(player_id, season)
    if logs:
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "min",
                     "fgm", "fga", "fg_pct", "fg3a", "fg3_pct", "ftm", "fta"):
            for n in (5, 10, 20):
                key = f"{stat}_l{n}"
                feats[key] = _gamelog_rolling(logs, n, stat)

        # Latest game stats
        played = [g for g in logs if _parse_min(g.get("min", 0)) > 0]
        if played:
            last = played[-1]
            feats["last_game_min"] = _parse_min(last.get("min", 0))
            feats["last_game_pts"] = float(last.get("pts", 0) or 0)

        # B2B detection
        if date and len(played) >= 1:
            last_date = played[-1].get("game_date", "")
            try:
                from datetime import datetime
                d_today = datetime.strptime(date[:10], "%Y-%m-%d")
                d_last  = datetime.strptime(last_date[:10], "%Y-%m-%d")
                feats["days_rest"] = (d_today - d_last).days - 1
                feats["is_b2b"] = int(feats["days_rest"] == 0)
            except Exception:
                feats["days_rest"] = float("nan")
                feats["is_b2b"] = 0

        # Season totals
        feats["season_gp"] = len(played)
        feats["season_avg_min"] = _gamelog_rolling(logs, 82, "min")
        feats["season_avg_pts"] = _gamelog_rolling(logs, 82, "pts")
        feats["season_avg_reb"] = _gamelog_rolling(logs, 82, "reb")
        feats["season_avg_ast"] = _gamelog_rolling(logs, 82, "ast")
    else:
        missing.append("gamelogs")

    # ── 2. Shot dashboard ─────────────────────────────────────────────────────
    sd = _shot_dashboard_for_player(player_id, season)
    if sd:
        feats["catch_and_shoot_pct"]           = float(sd.get("catch_and_shoot_pct", 0) or 0)
        feats["pull_up_pct"]                   = float(sd.get("pull_up_pct", 0) or 0)
        feats["contested_pct"]                 = float(sd.get("contested_pct", 0) or 0)
        feats["uncontested_pct"]               = float(sd.get("uncontested_pct", 0) or 0)
        feats["avg_defender_dist_contested"]   = float(sd.get("avg_defender_dist_contested", 0) or 0)
        feats["avg_defender_dist_catch_shoot"] = float(sd.get("avg_defender_dist_catch_shoot", 0) or 0)
    else:
        missing.append("shot_dashboard")

    # ── 3. Hustle stats ───────────────────────────────────────────────────────
    hustle = _hustle_for_player(player_id, season)
    if hustle:
        feats["hustle_contested_shots"]     = float(hustle.get("contested_shots", 0) or 0)
        feats["hustle_deflections"]         = float(hustle.get("deflections", 0) or 0)
        feats["hustle_loose_balls"]         = float(hustle.get("loose_balls_recovered", 0) or 0)
        feats["hustle_charges"]             = float(hustle.get("charges_drawn", 0) or 0)
        feats["hustle_screen_assists"]      = float(hustle.get("screen_assists", 0) or 0)
        feats["hustle_box_outs"]            = float(hustle.get("box_outs", 0) or 0)
    else:
        missing.append("hustle_stats")

    # ── 4. On/Off splits ──────────────────────────────────────────────────────
    on_off = _on_off_for_player(player_id, season)
    if on_off:
        feats["on_court_plus_minus"]  = float(on_off.get("on_court_plus_minus", 0) or 0)
        feats["off_court_plus_minus"] = float(on_off.get("off_court_plus_minus", 0) or 0)
        feats["on_off_diff"]          = float(on_off.get("on_off_diff", 0) or 0)
        feats["minutes_on"]           = float(on_off.get("minutes_on", 0) or 0)
    else:
        missing.append("on_off")

    # ── 5. Defender zone ──────────────────────────────────────────────────────
    dz = _defender_zone_for_player(player_id, season)
    # Note: defender_zone data is sparse — many players only have player_name
    for key in ("fg_pct_lt6", "fg_pct_6_10", "fg_pct_10_16", "fg_pct_16_3pt", "fg_pct_3pt"):
        val = dz.get(key)
        feats[f"def_zone_{key}"] = float(val) if val is not None else float("nan")

    # ── 6. Synergy play types ─────────────────────────────────────────────────
    syn = _synergy_for_player(player_id, season)
    for play_type in ("Isolation", "PRBallHandler", "Postup", "SpotUp", "Transition",
                      "Handoff", "Cut", "OffScreen"):
        feats[f"syn_{_norm(play_type)}_ppp"] = syn.get(play_type, float("nan"))

    # ── 7. BBRef advanced ─────────────────────────────────────────────────────
    bb = _bbref_for_player(player_id, player_name, season)
    if bb:
        feats["bbref_vorp"]     = float(bb.get("vorp", 0) or 0)
        feats["bbref_bpm"]      = float(bb.get("bpm", 0) or 0)
        feats["bbref_ws48"]     = float(bb.get("ws_per_48", 0) or 0)
        feats["bbref_usg_pct"]  = float(bb.get("usg_pct", 0) or 0)
        feats["bbref_ts_pct"]   = float(bb.get("ts_pct", 0) or 0)
        feats["bbref_age"]      = float(bb.get("age", 0) or 0)
        feats["bbref_per"]      = float(bb.get("per", 0) or 0)
    else:
        missing.append("bbref")

    # ── 8. Contract info ──────────────────────────────────────────────────────
    contract = _contract_for_player(player_id, player_name)
    if contract:
        feats["contract_year_flag"]  = int(contract.get("contract_year", False) or 0)
        feats["years_remaining"]     = float(contract.get("years_remaining", 0) or 0)
        feats["cap_hit_pct"]         = float(contract.get("cap_hit_pct", 0) or 0)
    else:
        missing.append("contract")

    # ── 9. Schedule context ───────────────────────────────────────────────────
    ctx = _schedule_context(game_id, team_abbrev)
    if ctx:
        feats["sched_rest_days"]       = float(ctx.get("rest_days", 1) or 1)
        feats["sched_is_b2b"]          = int(ctx.get("is_back_to_back", 0) or 0)
        feats["sched_travel_dist"]     = float(ctx.get("travel_distance", 0) or 0)
        feats["sched_home"]            = int(ctx.get("home_game", 1) or 1)
        feats["sched_games_on_road"]   = float(ctx.get("consecutive_road_games", 0) or 0)
    else:
        # Fall back to simple b2b computed from logs
        feats.setdefault("sched_rest_days", feats.get("days_rest", float("nan")))
        feats.setdefault("sched_is_b2b", feats.get("is_b2b", 0))
        feats.setdefault("sched_travel_dist", 0.0)
        feats.setdefault("sched_home", 1)
        feats.setdefault("sched_games_on_road", 0.0)

    # ── 10. Injury status ─────────────────────────────────────────────────────
    inj = _injury_status(player_name) if player_name else {}
    if inj:
        status = inj.get("status", "Available")
        feats["injury_status"]    = status
        feats["injury_out_flag"]  = int(status in ("Out", "Doubtful"))
        feats["injury_q_flag"]    = int(status == "Questionable")
    else:
        feats["injury_status"]   = "Available"
        feats["injury_out_flag"] = 0
        feats["injury_q_flag"]   = 0

    # ── 11. Current props lines ───────────────────────────────────────────────
    props = _current_props(player_name) if player_name else {}
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk"):
        feats[f"book_line_{stat}"] = float(props.get(stat, float("nan")))

    # ── 12. Existing model outputs ────────────────────────────────────────────
    # Inject DNP prob if available
    try:
        from src.prediction.dnp_predictor import predict_dnp
        dnp = predict_dnp(str(player_id), season=season)
        feats["dnp_prob"] = float(dnp.get("dnp_prob", 0.05) if isinstance(dnp, dict) else 0.05)
    except Exception:
        feats.setdefault("dnp_prob", 0.05)

    # ── 13. Matchup context (opp team data) ───────────────────────────────────
    matchups = _matchup_for_player(player_id, season)
    if matchups:
        avg_matchup_poss = float(np.mean([float(m.get("partial_possessions", 0) or 0) for m in matchups]))
        feats["matchup_avg_poss"] = avg_matchup_poss
    else:
        feats["matchup_avg_poss"] = float("nan")

    # ── Log missing sources (debug) ───────────────────────────────────────────
    if missing:
        log.debug("player_id=%d missing sources: %s", player_id, missing)

    feats["_missing_sources"] = missing
    return feats
