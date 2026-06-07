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
_LS_CONTEXT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "linescore_context.parquet")

log = logging.getLogger(__name__)


# ── Iter-19: linescore blowout/pace context ───────────────────────────────────

_LS_CONTEXT_DF = None  # loaded once on first call


def _load_linescore_df():
    """Load data/cache/linescore_context.parquet into module-level cache."""
    global _LS_CONTEXT_DF
    if _LS_CONTEXT_DF is None:
        try:
            import pandas as pd
            if os.path.exists(_LS_CONTEXT_PATH):
                _LS_CONTEXT_DF = pd.read_parquet(_LS_CONTEXT_PATH)
            else:
                _LS_CONTEXT_DF = None
        except Exception:
            _LS_CONTEXT_DF = None
    return _LS_CONTEXT_DF


_LS_FEATURE_KEYS = (
    "ls_blowout_pct_l5",
    "ls_avg_total_l5",
    "ls_avg_q1_pts_l5",
    "ls_avg_q4_pts_l5",
    "ls_garbage_time_pct_l5",
    "ls_opp_avg_total_allowed_l5",
    "ls_opp_q1_pts_allowed_l5",
)
_LS_DEFAULTS = {k: float("nan") for k in _LS_FEATURE_KEYS}


def _linescore_for_team(team: str, date: str) -> dict:
    """Return ls_* features for (team_abbreviation, game_date ISO).

    Returns NaN defaults when the parquet is absent or the key is missing.
    Args:
        team: 3-letter NBA tricode (e.g. 'LAL').
        date: ISO date string 'YYYY-MM-DD'.
    Returns:
        dict with 7 ls_* keys (float or NaN).
    """
    df = _load_linescore_df()
    if df is None:
        return dict(_LS_DEFAULTS)
    try:
        mask = (df["team_abbreviation"] == team) & (df["game_date"] == date)
        rows = df[mask]
        if rows.empty:
            return dict(_LS_DEFAULTS)
        r = rows.iloc[0]
        return {k: float(r[k]) if k in r.index else float("nan") for k in _LS_FEATURE_KEYS}
    except Exception:
        return dict(_LS_DEFAULTS)


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


def _gamelog_chrono_key(g: dict):
    """Parse 'Mon DD, YYYY' (or ISO) game_date to a sortable datetime; unparseable last."""
    from datetime import datetime
    gd = (g.get("game_date") or "").strip()
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(gd[:12] if fmt.startswith("%b") else gd[:10], fmt)
        except Exception:
            continue
    return datetime.min


def _gamelogs_for_player(player_id: int, season: str) -> list[dict]:
    """Load individual gamelog file for player."""
    path = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
    data = _load(path)
    if not isinstance(data, list):
        return []
    # CV_GAMELOG_CHRONO_SORT (sweep TRACKING_CV, default OFF = byte-identical legacy).
    # game_date is 'Mon DD, YYYY' (e.g. 'Apr 13, 2025'); the legacy LEXICOGRAPHIC sort
    # orders months alphabetically (Apr<Aug<Dec<Feb<Jan<...<Oct<Sep), scrambling the
    # Oct->Apr NBA season so the L5/L10/L20 tail + last-game read the WRONG games (the
    # lexicographic tail = Oct/Sep = season START, not the recent games). ON sorts truly
    # chronologically. Gated because downstream prop_model_stack / prediction_orchestrator
    # features (and any model/calibrator trained through this assembler) may be coupled to
    # the legacy order -> A/B slate ROI/MAE before flipping default ON. (Note: the b2b block
    # at ~line 912 also mis-parses this date via strptime(..,'%Y-%m-%d') -> days_rest NaN;
    # that path is separately swallowed and unaffected by this flag.)
    if os.environ.get("CV_GAMELOG_CHRONO_SORT", "0") == "1":
        try:
            return sorted(data, key=_gamelog_chrono_key)
        except Exception:
            return data
    try:
        return sorted(data, key=lambda g: g.get("game_date", ""))
    except Exception:
        return data


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

def _defender_matchup_for_player(game_id: Optional[str], player_id: int) -> dict:
    """Return 7 dmatch_* features from the defender matchup parquet, or all-NaN dict."""
    nan = float("nan")
    defaults: dict = {
        "dmatch_fg_pct_l10": nan,
        "dmatch_partial_poss_share": nan,
        "dmatch_switches_per_poss": nan,
        "dmatch_primary_def_height_in": nan,
        "dmatch_height_advantage_in": nan,
        "dmatch_help_blocks_per_game": nan,
        "dmatch_3p_pct_l10": nan,
    }
    if not game_id:
        return defaults
    try:
        from src.data.defender_matchup_loader import get_defender_matchup_row
        row = get_defender_matchup_row(game_id, player_id)
        if row is None:
            return defaults
        return {
            "dmatch_fg_pct_l10":          _safe_float(row.get("matchup_fg_pct_l10")),
            "dmatch_partial_poss_share":   _safe_float(row.get("matchup_partial_poss_share")),
            "dmatch_switches_per_poss":    _safe_float(row.get("switches_per_poss")),
            "dmatch_primary_def_height_in": _safe_float(row.get("primary_def_height_in")),
            "dmatch_height_advantage_in":  _safe_float(row.get("height_advantage_in")),
            "dmatch_help_blocks_per_game": _safe_float(row.get("help_blocks_per_game")),
            "dmatch_3p_pct_l10":           _safe_float(row.get("matchup_3p_pct_l10")),
        }
    except Exception as exc:
        log.debug("defender_matchup unavailable for game=%s player=%d: %s", game_id, player_id, exc)
        return defaults


def _safe_float(val) -> float:
    """Convert val to float, returning NaN on failure."""
    if val is None:
        return float("nan")
    try:
        f = float(val)
        return f
    except (TypeError, ValueError):
        return float("nan")


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

_BBREF_EXTRA_KEYS_FA = ("orb_pct", "drb_pct", "trb_pct", "bpm", "ws")
_BBREF_EXTENDED_PARQUET_FA = os.path.join(PROJECT_DIR, "data", "cache", "bbref_advanced_extended.parquet")
_BBREF_EXT_CACHE_FA: Optional[object] = None  # pandas DataFrame, lazy-loaded

# ── Iter-5: hustle + on_off parquet loaders (module-level cached) ─────────────

_HUSTLE_PARQUET_FA = os.path.join(PROJECT_DIR, "data", "cache", "hustle_features.parquet")
_HUSTLE_DF_FA: Optional[object] = None  # pandas DataFrame indexed by (player_id, season) or False

_ONOFF_PARQUET_FA = os.path.join(PROJECT_DIR, "data", "cache", "on_off_features.parquet")
_ONOFF_DF_FA: Optional[object] = None  # pandas DataFrame or False

_HUSTLE_FEAT_COLS = (
    "hustle_deflections", "hustle_contested_shots", "hustle_screen_assists",
    "hustle_box_outs", "hustle_loose_balls", "hustle_charges_drawn",
)
_ONOFF_COL_MAP_FA = {
    "on_off_net_rating_diff": "onoff_net_rating_diff",
    "on_off_impact_z":        "onoff_impact_z",
    "on_off_min_weight":      "onoff_min_weight",
}


def _load_hustle_df() -> Optional[object]:
    """Lazy-load hustle_features.parquet indexed by (player_id, season). Returns None on failure."""
    global _HUSTLE_DF_FA
    if _HUSTLE_DF_FA is None:
        try:
            import pandas as pd
            if os.path.isfile(_HUSTLE_PARQUET_FA):
                df = pd.read_parquet(
                    _HUSTLE_PARQUET_FA,
                    columns=["player_id", "season"] + list(_HUSTLE_FEAT_COLS),
                )
                _HUSTLE_DF_FA = df.set_index(["player_id", "season"])
            else:
                _HUSTLE_DF_FA = False
        except Exception as exc:
            log.debug("hustle_features.parquet load failed: %s", exc)
            _HUSTLE_DF_FA = False
    return _HUSTLE_DF_FA if _HUSTLE_DF_FA is not False else None


def _load_on_off_df() -> Optional[object]:
    """Lazy-load on_off_features.parquet. Returns None on failure."""
    global _ONOFF_DF_FA
    if _ONOFF_DF_FA is None:
        try:
            import pandas as pd
            if os.path.isfile(_ONOFF_PARQUET_FA):
                _ONOFF_DF_FA = pd.read_parquet(
                    _ONOFF_PARQUET_FA,
                    columns=["player_id", "season"] + list(_ONOFF_COL_MAP_FA.keys()),
                )
            else:
                _ONOFF_DF_FA = False
        except Exception as exc:
            log.debug("on_off_features.parquet load failed: %s", exc)
            _ONOFF_DF_FA = False
    return _ONOFF_DF_FA if _ONOFF_DF_FA is not False else None


def _hustle_for_player_parquet(player_id: int, season: str) -> dict:
    """Return dict with 6 hustle_ keys for (player_id, season) from parquet. NaN on miss."""
    nan = float("nan")
    defaults = {k: nan for k in _HUSTLE_FEAT_COLS}
    df = _load_hustle_df()
    if df is None:
        return defaults
    try:
        import pandas as pd
        row = df.loc[(int(player_id), str(season))]
        result = {}
        for k in _HUSTLE_FEAT_COLS:
            v = row[k] if hasattr(row, "__getitem__") else getattr(row, k, nan)
            result[k] = float(v) if pd.notna(v) else nan
        return result
    except (KeyError, IndexError):
        return defaults
    except Exception as exc:
        log.debug("_hustle_for_player_parquet pid=%d season=%s: %s", player_id, season, exc)
        return defaults


def _on_off_for_player_parquet(player_id: int, season: str) -> dict:
    """Return dict with 3 onoff_ keys for (player_id, season) from parquet. NaN on miss."""
    nan = float("nan")
    defaults = {v: nan for v in _ONOFF_COL_MAP_FA.values()}
    df = _load_on_off_df()
    if df is None:
        return defaults
    try:
        import pandas as pd
        mask = (df["player_id"] == int(player_id)) & (df["season"] == str(season))
        rows = df[mask]
        if rows.empty:
            return defaults
        r = rows.iloc[0]
        result = {}
        for parquet_col, feat_key in _ONOFF_COL_MAP_FA.items():
            v = r.get(parquet_col)
            result[feat_key] = float(v) if pd.notna(v) else nan
        return result
    except Exception as exc:
        log.debug("_on_off_for_player_parquet pid=%d season=%s: %s", player_id, season, exc)
        return defaults


def _load_bbref_ext_df():
    """Lazy-load bbref_advanced_extended.parquet once; returns DataFrame or None."""
    global _BBREF_EXT_CACHE_FA
    if _BBREF_EXT_CACHE_FA is None:
        try:
            import pandas as pd  # noqa: PLC0415
            if os.path.isfile(_BBREF_EXTENDED_PARQUET_FA):
                _BBREF_EXT_CACHE_FA = pd.read_parquet(
                    _BBREF_EXTENDED_PARQUET_FA,
                    columns=["player_name", "season"] + list(_BBREF_EXTRA_KEYS_FA),
                )
            else:
                _BBREF_EXT_CACHE_FA = False  # sentinel: file absent
        except Exception as exc:
            log.debug("bbref_extended parquet load failed: %s", exc)
            _BBREF_EXT_CACHE_FA = False
    return _BBREF_EXT_CACHE_FA if _BBREF_EXT_CACHE_FA is not False else None


def _bbref_for_player(player_id: int, player_name: str, season: str) -> dict:
    # BBRef uses names not IDs — match by name
    path = os.path.join(_EXT_CACHE, f"bbref_advanced_{season}.json")
    data = _load(path)
    base: dict = {}
    if isinstance(data, list) and player_name:
        base = _find_by_name(data, player_name) or {}
    # Merge extra keys from parquet (wave-2a extension).
    ext_df = _load_bbref_ext_df()
    if ext_df is not None and player_name:
        try:
            import pandas as pd  # noqa: PLC0415
            mask = (ext_df["player_name"] == player_name) & (ext_df["season"] == season)
            rows = ext_df[mask]
            if not rows.empty:
                r = rows.iloc[0]
                for k in _BBREF_EXTRA_KEYS_FA:
                    v = r[k]
                    base[k] = float(v) if pd.notna(v) else 0.0
        except Exception as exc:
            log.debug("bbref_ext merge failed player=%s season=%s: %s", player_name, season, exc)
    return base


# ── Contracts ──────────────────────────────────────────────────────────────────

_CONTRACT_EXT_DF: Optional[object] = None  # pandas DataFrame, loaded once

def _load_contract_ext_df():
    global _CONTRACT_EXT_DF
    if _CONTRACT_EXT_DF is not None:
        return _CONTRACT_EXT_DF
    parquet_path = os.path.join(PROJECT_DIR, "data", "cache", "contract_features_extended.parquet")
    if not os.path.exists(parquet_path):
        return None
    try:
        import pandas as pd
        _CONTRACT_EXT_DF = pd.read_parquet(parquet_path)
    except Exception as exc:
        log.debug("contract_features_extended.parquet unreadable: %s", exc)
        _CONTRACT_EXT_DF = None
    return _CONTRACT_EXT_DF


def _contract_for_player(player_id: int, player_name: str) -> dict:
    path = os.path.join(_EXT_CACHE, "contracts_2024-25.json")
    data = _load(path)
    base: dict = {}
    if isinstance(data, list) and player_name:
        row = _find_by_name(data, player_name)
        base = row or {}

    # Extended parquet columns
    ext: dict = {
        "contract_years_remaining":    float("nan"),
        "contract_expiring_flag":      float("nan"),
        "contract_player_option_final": float("nan"),
        "contract_team_option_final":   float("nan"),
    }
    df = _load_contract_ext_df()
    if df is not None:
        mask = None
        if player_id:
            try:
                mask = df["player_id"] == int(player_id)
            except Exception:
                pass
        if mask is None or not mask.any():
            # fallback: name match
            try:
                nm = _norm(player_name)
                mask = df["player_name"].apply(lambda x: _norm(str(x))) == nm
            except Exception:
                mask = None
        if mask is not None and mask.any():
            r = df[mask].iloc[0]
            def _get(col: str) -> float:
                try:
                    v = r[col]
                    return float(v) if v is not None else float("nan")
                except Exception:
                    return float("nan")
            ext["contract_years_remaining"]    = _get("years_remaining")
            ext["contract_expiring_flag"]      = _get("expiring_flag")
            ext["contract_player_option_final"] = _get("player_option_final_year")
            ext["contract_team_option_final"]   = _get("team_option_final_year")

    return {**base, **ext}


# ── Iter-3: officials rolling (A) ────────────────────────────────────────────

_OFFICIALS_ROLLING_DF: Optional[object] = None
_OFFICIALS_ROLLING_PATH = os.path.join(PROJECT_DIR, "data", "cache", "officials_rolling.parquet")

def _load_officials_rolling_df():
    global _OFFICIALS_ROLLING_DF
    if _OFFICIALS_ROLLING_DF is not None:
        return _OFFICIALS_ROLLING_DF
    if not os.path.exists(_OFFICIALS_ROLLING_PATH):
        _OFFICIALS_ROLLING_DF = False
        return None
    try:
        import pandas as pd
        _OFFICIALS_ROLLING_DF = pd.read_parquet(_OFFICIALS_ROLLING_PATH)
        _OFFICIALS_ROLLING_DF["game_id"] = _OFFICIALS_ROLLING_DF["game_id"].astype(str)
    except Exception as exc:
        log.debug("officials_rolling.parquet unreadable: %s", exc)
        _OFFICIALS_ROLLING_DF = False
    return _OFFICIALS_ROLLING_DF if _OFFICIALS_ROLLING_DF is not False else None


def _officials_for_team(game_id: Optional[str], team_abbrev: Optional[str]) -> dict:
    nan = float("nan")
    defaults = {
        "ref_l5_fouls": nan, "ref_l5_fta": nan,
        "ref_fouls_z": nan, "ref_fta_z": nan, "ref_home_advantage": nan,
    }
    if not game_id or not team_abbrev:
        return defaults
    try:
        df = _load_officials_rolling_df()
        if df is None:
            return defaults
        mask = (df["game_id"] == str(game_id)) & (df["team_abbreviation"] == str(team_abbrev))
        rows = df[mask]
        if rows.empty:
            return defaults
        r = rows.iloc[0]
        import pandas as pd
        def _sf(col: str) -> float:
            v = r.get(col)
            return float(v) if v is not None and pd.notna(v) else nan
        return {
            "ref_l5_fouls":       _sf("l5_ref_crew_fouls_per_g"),
            "ref_l5_fta":         _sf("l5_ref_crew_fta_per_g"),
            "ref_fouls_z":        _sf("ref_crew_fouls_z"),
            "ref_fta_z":          _sf("ref_crew_fta_z"),
            "ref_home_advantage": _sf("home_win_pct_advantage"),
        }
    except Exception as exc:
        log.debug("_officials_for_team error: %s", exc)
        return defaults


# ── Iter-3: foul features (B) ─────────────────────────────────────────────────

_FOUL_FEATURES_DF: Optional[object] = None
_FOUL_FEATURES_PATH = os.path.join(PROJECT_DIR, "data", "cache", "foul_features.parquet")

def _load_foul_features_df():
    global _FOUL_FEATURES_DF
    if _FOUL_FEATURES_DF is not None:
        return _FOUL_FEATURES_DF
    if not os.path.exists(_FOUL_FEATURES_PATH):
        _FOUL_FEATURES_DF = False
        return None
    try:
        import pandas as pd
        _FOUL_FEATURES_DF = pd.read_parquet(_FOUL_FEATURES_PATH)
        _FOUL_FEATURES_DF["game_id"] = _FOUL_FEATURES_DF["game_id"].astype(str)
        _FOUL_FEATURES_DF["game_date"] = _FOUL_FEATURES_DF["game_date"].astype(str).str[:10]
    except Exception as exc:
        log.debug("foul_features.parquet unreadable: %s", exc)
        _FOUL_FEATURES_DF = False
    return _FOUL_FEATURES_DF if _FOUL_FEATURES_DF is not False else None


def _fouls_for_player(player_id: int, game_id: Optional[str], game_date: Optional[str]) -> dict:
    nan = float("nan")
    defaults = {
        "foul_pf36_l5": nan, "foul_pf36_l10": nan,
        "foul_trouble_l10": nan, "foul_last_pf": nan, "foul_min_l5": nan,
    }
    try:
        df = _load_foul_features_df()
        if df is None:
            return defaults
        import pandas as pd
        rows = None
        if game_id:
            mask = (df["player_id"] == int(player_id)) & (df["game_id"] == str(game_id))
            rows = df[mask]
        if (rows is None or rows.empty) and game_date:
            gd = str(game_date)[:10]
            mask2 = (df["player_id"] == int(player_id)) & (df["game_date"] == gd)
            rows = df[mask2]
        if rows is None or rows.empty:
            return defaults
        r = rows.iloc[0]
        def _sf(col: str) -> float:
            v = r.get(col)
            return float(v) if v is not None and pd.notna(v) else nan
        return {
            "foul_pf36_l5":     _sf("pf_per_36_l5"),
            "foul_pf36_l10":    _sf("pf_per_36_l10"),
            "foul_trouble_l10": _sf("foul_trouble_rate_l10"),
            "foul_last_pf":     _sf("last_game_pf"),
            "foul_min_l5":      _sf("min_l5"),
        }
    except Exception as exc:
        log.debug("_fouls_for_player error: %s", exc)
        return defaults


# ── Iter-3: DNP team features (C) ────────────────────────────────────────────

_DNP_TEAM_DF: Optional[object] = None
_DNP_TEAM_PATH = os.path.join(PROJECT_DIR, "data", "cache", "dnp_features_team.parquet")

def _load_dnp_team_df():
    global _DNP_TEAM_DF
    if _DNP_TEAM_DF is not None:
        return _DNP_TEAM_DF
    if not os.path.exists(_DNP_TEAM_PATH):
        _DNP_TEAM_DF = False
        return None
    try:
        import pandas as pd
        _DNP_TEAM_DF = pd.read_parquet(_DNP_TEAM_PATH)
        _DNP_TEAM_DF["game_id"] = _DNP_TEAM_DF["game_id"].astype(str)
    except Exception as exc:
        log.debug("dnp_features_team.parquet unreadable: %s", exc)
        _DNP_TEAM_DF = False
    return _DNP_TEAM_DF if _DNP_TEAM_DF is not False else None


def _dnp_team_for_game(game_id: Optional[str], team_abbrev: Optional[str]) -> dict:
    nan = float("nan")
    defaults = {
        "dnp_in_game": nan, "dnp_l5_avg": nan,
        "dnp_l10_avg": nan, "dnp_prior_game": nan,
    }
    if not game_id or not team_abbrev:
        return defaults
    try:
        df = _load_dnp_team_df()
        if df is None:
            return defaults
        import pandas as pd
        mask = (df["game_id"] == str(game_id)) & (df["team_abbreviation"] == str(team_abbrev))
        rows = df[mask]
        if rows.empty:
            return defaults
        r = rows.iloc[0]
        def _sf(col: str) -> float:
            v = r.get(col)
            return float(v) if v is not None and pd.notna(v) else nan
        return {
            "dnp_in_game":    _sf("dnp_count_in_game"),
            "dnp_l5_avg":     _sf("dnp_count_l5_avg"),
            "dnp_l10_avg":    _sf("dnp_count_l10_avg"),
            "dnp_prior_game": _sf("prior_game_dnp_count"),
        }
    except Exception as exc:
        log.debug("_dnp_team_for_game error: %s", exc)
        return defaults


# ── Iter-3: advanced stats splits (D) ────────────────────────────────────────

_ADV_SPLITS_DF: Optional[object] = None
_ADV_SPLITS_PATH = os.path.join(PROJECT_DIR, "data", "cache", "adv_stats_splits.parquet")

def _load_adv_splits_df():
    global _ADV_SPLITS_DF
    if _ADV_SPLITS_DF is not None:
        return _ADV_SPLITS_DF
    if not os.path.exists(_ADV_SPLITS_PATH):
        _ADV_SPLITS_DF = False
        return None
    try:
        import pandas as pd
        _ADV_SPLITS_DF = pd.read_parquet(_ADV_SPLITS_PATH)
        _ADV_SPLITS_DF["game_id"] = _ADV_SPLITS_DF["game_id"].astype(str)
        _ADV_SPLITS_DF["game_date"] = _ADV_SPLITS_DF["game_date"].astype(str).str[:10]
    except Exception as exc:
        log.debug("adv_stats_splits.parquet unreadable: %s", exc)
        _ADV_SPLITS_DF = False
    return _ADV_SPLITS_DF if _ADV_SPLITS_DF is not False else None


def _adv_splits_for_player(player_id: int, game_id: Optional[str], game_date: Optional[str] = None) -> dict:
    nan = float("nan")
    defaults = {
        "adv_usage_std": nan, "adv_ts_std": nan, "adv_efg_std": nan,
        "adv_usage_vs_opp_l3": nan, "adv_ts_vs_opp_l3": nan, "adv_usage_z": nan,
    }
    try:
        df = _load_adv_splits_df()
        if df is None:
            return defaults
        import pandas as pd
        rows = None
        if game_id:
            mask = (df["player_id"] == int(player_id)) & (df["game_id"] == str(game_id))
            rows = df[mask]
        if (rows is None or rows.empty) and game_date:
            gd = str(game_date)[:10]
            mask2 = (df["player_id"] == int(player_id)) & (df["game_date"] == gd)
            rows = df[mask2]
        if rows is None or rows.empty:
            return defaults
        r = rows.iloc[0]
        def _sf(col: str) -> float:
            v = r.get(col)
            return float(v) if v is not None and pd.notna(v) else nan
        return {
            "adv_usage_std":        _sf("adv_usage_season_to_date"),
            "adv_ts_std":           _sf("adv_ts_season_to_date"),
            "adv_efg_std":          _sf("adv_efg_season_to_date"),
            "adv_usage_vs_opp_l3":  _sf("adv_usage_vs_opp_l3"),
            "adv_ts_vs_opp_l3":     _sf("adv_ts_vs_opp_l3"),
            "adv_usage_z":          _sf("adv_usage_z_in_season"),
        }
    except Exception as exc:
        log.debug("_adv_splits_for_player error: %s", exc)
        return defaults


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


# ── Player profile ────────────────────────────────────────────────────────────

def _player_profile_for_player(player_id: int, date: Optional[str]) -> dict:
    try:
        from src.data.player_profile_loader import get_player_profile
        return get_player_profile(player_id, as_of_date=date) or {}
    except Exception as exc:
        log.debug("player_profile_loader unavailable: %s", exc)
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

    # ── 3. Hustle stats (parquet, iter-5) ────────────────────────────────────
    hustle_pq = _hustle_for_player_parquet(player_id, season)
    feats.update(hustle_pq)
    # Legacy JSON-based keys for backward-compat inference paths.
    hustle = _hustle_for_player(player_id, season)
    if hustle:
        feats["hustle_contested_shots"]     = float(hustle.get("contested_shots", 0) or 0)
        feats["hustle_charges"]             = float(hustle.get("charges_drawn", 0) or 0)
    else:
        missing.append("hustle_stats")

    # ── 4. On/Off splits (parquet, iter-5) ───────────────────────────────────
    onoff_pq = _on_off_for_player_parquet(player_id, season)
    feats.update(onoff_pq)
    # Legacy JSON-based keys for backward-compat inference paths.
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
        # Wave-2a: 5 new columns from bbref_advanced_extended.parquet
        feats["bbref_orb_pct"]  = float(bb.get("orb_pct", 0) or 0)
        feats["bbref_drb_pct"]  = float(bb.get("drb_pct", 0) or 0)
        feats["bbref_trb_pct"]  = float(bb.get("trb_pct", 0) or 0)
        feats["bbref_ws"]       = float(bb.get("ws", 0) or 0)
    else:
        missing.append("bbref")
        for _k in ("bbref_orb_pct", "bbref_drb_pct", "bbref_trb_pct", "bbref_ws"):
            feats[_k] = 0.0

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

    # ── 14. Defender matchup features (dmatch_*) ─────────────────────────────
    dmatch = _defender_matchup_for_player(game_id, player_id)
    feats.update(dmatch)

    # ── 15. Player profile (prof_*) ───────────────────────────────────────────
    prof = _player_profile_for_player(player_id, date)
    if prof:
        _nan = float("nan")
        def _fi(key: str) -> float:
            v = prof.get(key)
            return float(v) if v is not None else _nan
        def _ii(key: str) -> int:
            v = prof.get(key)
            return int(v) if v is not None else 0
        feats["prof_height_in"]       = _fi("height_in")
        feats["prof_weight_lb"]       = _fi("weight_lb")
        feats["prof_draft_year"]      = _fi("draft_year")
        feats["prof_draft_number"]    = _fi("draft_number")
        feats["prof_undrafted_flag"]  = _ii("undrafted_flag")
        feats["prof_intl_flag"]       = _ii("intl_flag")
        feats["prof_college_d1_flag"] = _fi("college_d1_flag")
        feats["prof_greatest_75_flag"] = _ii("greatest_75_flag")
        feats["prof_age_days"]         = _fi("age_precise_days_as_of")
        feats["prof_years_in_league"]  = _fi("years_in_league_as_of")
        feats["prof_rookie_flag"]      = _ii("rookie_flag_as_of")
        feats["prof_season_exp"]       = _fi("season_exp")
    else:
        missing.append("player_profile")

    # ── 16. Iter-3 officials rolling (A) ─────────────────────────────────────
    try:
        off_feats = _officials_for_team(game_id, team_abbrev)
        feats.update(off_feats)
    except Exception as exc:
        log.debug("officials_for_team failed: %s", exc)
        feats.update({"ref_l5_fouls": float("nan"), "ref_l5_fta": float("nan"),
                      "ref_fouls_z": float("nan"), "ref_fta_z": float("nan"),
                      "ref_home_advantage": float("nan")})

    # ── 17. Iter-3 foul features (B) ─────────────────────────────────────────
    try:
        foul_feats = _fouls_for_player(player_id, game_id, date)
        feats.update(foul_feats)
    except Exception as exc:
        log.debug("fouls_for_player failed: %s", exc)
        feats.update({"foul_pf36_l5": float("nan"), "foul_pf36_l10": float("nan"),
                      "foul_trouble_l10": float("nan"), "foul_last_pf": float("nan"),
                      "foul_min_l5": float("nan")})

    # ── 18. Iter-3 DNP team features (C) ─────────────────────────────────────
    try:
        dnp_feats = _dnp_team_for_game(game_id, team_abbrev)
        feats.update(dnp_feats)
    except Exception as exc:
        log.debug("dnp_team_for_game failed: %s", exc)
        feats.update({"dnp_in_game": float("nan"), "dnp_l5_avg": float("nan"),
                      "dnp_l10_avg": float("nan"), "dnp_prior_game": float("nan")})

    # ── 19. Iter-3 advanced stats splits (D) ─────────────────────────────────
    try:
        adv_feats = _adv_splits_for_player(player_id, game_id, date)
        feats.update(adv_feats)
    except Exception as exc:
        log.debug("adv_splits_for_player failed: %s", exc)
        feats.update({"adv_usage_std": float("nan"), "adv_ts_std": float("nan"),
                      "adv_efg_std": float("nan"), "adv_usage_vs_opp_l3": float("nan"),
                      "adv_ts_vs_opp_l3": float("nan"), "adv_usage_z": float("nan")})

    # ── Log missing sources (debug) ───────────────────────────────────────────
    if missing:
        log.debug("player_id=%d missing sources: %s", player_id, missing)

    feats["_missing_sources"] = missing
    return feats
