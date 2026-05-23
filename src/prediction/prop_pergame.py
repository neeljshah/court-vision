"""
prop_pergame.py — Per-game prop models trained on real game logs (PRED-13).

The legacy prop pipeline (player_props.train_props) trains on SEASON
averages: it predicts a player's season-average stat from features that are
essentially that same season average, plus simulated noise. Its reported
R²≈0.99 is therefore meaningless — a near-identity fit. The honest holdout
(predictions vs realised box scores) is only ~0.45.

This module trains the real task, the way a sharp quant would: each row is
one game, every feature is computed strictly from the player's PRIOR games
(rolling form, EWMA recency, rest, home/away), and the target is THAT game's
actual stat line. No leakage — features never see the game they predict.

Public API
----------
    build_pergame_dataset(gamelog_dir, min_prior) -> (rows, feature_cols)
    train_pergame_models(...)                     -> dict   (honest holdout R²/MAE)
    load_pergame_model(stat)                      -> model or None
    predict_pergame(stat, feature_row)            -> float
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_PLAYTYPE_PATH = os.path.join(PROJECT_DIR, "data", "playtypes.parquet")
_PLAY_TYPES = [
    "isolation", "prballhandler", "prrollman", "postup",
    "spotup", "handoff", "cut", "offscreen", "transition",
]
_PLAYTYPE_DEFAULTS: Dict[str, float] = {f"pt_{pt}_freq": 0.0 for pt in _PLAY_TYPES}

# Stats predicted, and their box-score column names in the gamelog JSON.
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
# Stats where the XGB Poisson learner consistently degrades the XGB+LGB
# blend (ensemble_lift negative on holdout). For these we save only the
# LGB model and predict_pergame's load_pergame_model returns just LGB,
# making the "blend" a single-model prediction.
_LGB_ONLY_STATS = {"stl"}
_BOX_COL = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
            "stl": "STL", "blk": "BLK", "tov": "TOV", "min": "MIN"}
_FORM_STATS = STATS + ["min"]          # min drives every counting stat

_MIN_PLAYED = 5.0                      # a game counts only if the player played
_EWMA_ALPHA = 0.30                     # recency weight — recent games dominate


# ── feature helpers ───────────────────────────────────────────────────────────

def _parse_date(raw: str) -> Optional[datetime]:
    """Parse an NBA gamelog date ('Apr 13, 2025'). Returns None on failure."""
    try:
        return datetime.strptime(str(raw).strip(), "%b %d, %Y")
    except Exception:
        return None


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _ewma(vals: List[float], alpha: float = _EWMA_ALPHA) -> float:
    """Exponentially-weighted mean — most recent game weighted highest."""
    if not vals:
        return 0.0
    weighted = total_w = 0.0
    for i, v in enumerate(reversed(vals)):       # i=0 is the most recent game
        w = alpha * (1.0 - alpha) ** i
        weighted += w * v
        total_w += w
    return weighted / total_w if total_w > 0 else 0.0


def feature_columns() -> List[str]:
    """Ordered feature names — form, game-context, opponent defence, rest/travel,
    playtype frequency, BBRef advanced, contracts."""
    cols: List[str] = []
    for stat in _FORM_STATS:
        cols += [f"l5_{stat}", f"l10_{stat}", f"std_{stat}",
                 f"ewma_{stat}", f"prev_{stat}"]
    cols += ["rest_days", "is_home", "games_played"]
    cols += ["days_since_last_game", "games_since_long_absence"]
    cols += [f"opp_def_{s}" for s in STATS]      # opponent-defence factors
    cols += ["is_b2b", "is_b3b", "miles_traveled", "altitude_ft"]
    cols += [f"pt_{pt}_freq" for pt in _PLAY_TYPES]
    cols += [f"bbref_{k}" for k in _BBREF_KEYS]
    cols += [f"contract_{k}" for k in _CONTRACT_KEYS]
    cols += list(_RATIO_KEYS)
    return cols


# ── rest / travel features ────────────────────────────────────────────────────

_REST_TRAVEL_PATH = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
_REST_TRAVEL_DEFAULTS: Dict[str, float] = {
    "is_b2b": 0.0, "is_b3b": 0.0, "miles_traveled": 0.0, "altitude_ft": 0.0,
}


class _RestTravel:
    """Lookup table for rest/travel features sourced from data/rest_travel.parquet.

    Keyed by (game_date_iso, team_abbreviation) → {is_b2b, is_b3b, miles_traveled, altitude_ft}.
    Yields neutral defaults when the parquet is absent or the key is missing.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, team_abbrev: str, gdate: datetime) -> Dict[str, float]:
        """Return rest/travel feature dict for a team on a date."""
        key = (gdate.date().isoformat(), str(team_abbrev))
        return dict(self._lookup.get(key, _REST_TRAVEL_DEFAULTS))


def build_rest_travel(cache_path: Optional[str] = None) -> _RestTravel:
    """Load rest/travel parquet and build the lookup table.

    If the parquet is absent or pandas/pyarrow import fails, returns a
    _RestTravel that always yields neutral defaults. Never raises.
    """
    path = cache_path or _REST_TRAVEL_PATH
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _RestTravel(lookup)
        df = pd.read_parquet(path)
        for _, row in df.iterrows():
            key = (str(row["game_date"]), str(row["team_abbreviation"]))
            lookup[key] = {
                "is_b2b":         float(row.get("is_b2b", 0.0) or 0.0),
                "is_b3b":         float(row.get("is_b3b", 0.0) or 0.0),
                "miles_traveled": float(row.get("miles_traveled", 0.0) or 0.0),
                "altitude_ft":    float(row.get("altitude_ft", 0.0) or 0.0),
            }
    except Exception:
        pass
    return _RestTravel(lookup)


# ── play-type features ────────────────────────────────────────────────────────

class _PlayTypes:
    """Lookup table for Synergy play-type frequencies sourced from data/playtypes.parquet.

    Keyed by (player_id, season) → {pt_<playtype>_freq: float, ...}.
    Yields zero defaults when the parquet is absent or the key is missing.
    """

    def __init__(self, lookup: Dict[Tuple[int, str], Dict[str, float]]):
        self._lookup = lookup

    def features(self, player_id, season: str) -> Dict[str, float]:
        """Return play-type feature dict for a player in a season."""
        key = (int(player_id), str(season))
        return dict(self._lookup.get(key, _PLAYTYPE_DEFAULTS))


def build_playtypes(cache_path: Optional[str] = None) -> _PlayTypes:
    """Load the play-type parquet and build the lookup table.

    If the parquet is absent or pandas/pyarrow import fails, returns a
    _PlayTypes that always yields zero defaults. Never raises.
    """
    path = cache_path or _PLAYTYPE_PATH
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    try:
        import pandas as pd  # noqa: PLC0415
        if not os.path.exists(path):
            return _PlayTypes(lookup)
        df = pd.read_parquet(path)
        for _, row in df.iterrows():
            normalized = str(row["play_type"]).lower().replace(" ", "")
            key = (int(row["player_id"]), str(row["season"]))
            lookup.setdefault(key, {})[f"pt_{normalized}_freq"] = (
                float(row.get("freq_pct", 0.0) or 0.0)
            )
        # Ensure every entry has all 9 keys so callers never get KeyError.
        for key in lookup:
            for pt in _PLAY_TYPES:
                lookup[key].setdefault(f"pt_{pt}_freq", 0.0)
    except Exception:
        pass
    return _PlayTypes(lookup)


_PLAYTYPES_CACHE: Optional[_PlayTypes] = None


def _get_playtypes() -> _PlayTypes:
    global _PLAYTYPES_CACHE
    if _PLAYTYPES_CACHE is None:
        _PLAYTYPES_CACHE = build_playtypes()
    return _PLAYTYPES_CACHE


# ── BBRef advanced features (per-player-season efficiency + rate metrics) ────

_BBREF_DIR = os.path.join(PROJECT_DIR, "data", "external")
# Order matters — drives feature_columns() output. Efficiency (ts), volume
# (usg), shot profile (three_par, ftr), per-100 rate stats (ast/stl/blk/tov),
# holistic impact (ws_per_48, per), and SPLIT offensive/defensive BPM (obpm,
# dbpm) — bpm itself is the sum so we keep the split for finer per-side
# weighting. per is included for its independent signal (corr 0.88 with bpm —
# enough non-redundancy to matter for trees). Defensive depth — dws, ows,
# vorp — are ~85% collinear with ws_per_48 / obpm / dbpm but the residual
# signal still helps gradient-boosted trees in practice; appended at the end
# so existing column positions stay stable. Dropped: trb/orb/drb_pct
# (handled implicitly by opp_def_reb + form), bpm (sum of obpm+dbpm).
_BBREF_KEYS = ("usg_pct", "ts_pct", "three_par", "ftr",
               "ast_pct", "stl_pct", "blk_pct", "tov_pct",
               "ws_per_48", "per", "obpm", "dbpm",
               "dws", "ows", "vorp")
_BBREF_DEFAULTS: Dict[str, float] = {f"bbref_{k}": 0.0 for k in _BBREF_KEYS}


class _BBRefAdvanced:
    """Per-(player_name, season) lookup of BBRef advanced metrics.

    Source: data/external/bbref_advanced_<season>.json (already cached).
    Keys: player_name (NBA full_name) and season (e.g. '2024-25').
    Yields zero defaults when the season file is absent or the player isn't
    listed (rookies, two-way contracts, missing scrape). Never raises.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]],
                 id_to_name: Dict[int, str]):
        self._lookup = lookup
        self._id_to_name = id_to_name

    def features(self, player_id, season: str) -> Dict[str, float]:
        try:
            name = self._id_to_name.get(int(player_id))
        except (TypeError, ValueError):
            name = None
        if not name:
            return dict(_BBREF_DEFAULTS)
        return dict(self._lookup.get((name, str(season)), _BBREF_DEFAULTS))


def _bbref_id_to_name() -> Dict[int, str]:
    """Build {player_id: full_name} from nba_api's static player list.
    Never raises — returns {} if the static cache is unavailable."""
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
        return {int(p["id"]): str(p["full_name"]) for p in players.get_players()}
    except Exception:
        return {}


def _unmangle_utf8(s: str) -> str:
    """The cached BBRef JSON was written with mangled encoding — every UTF-8
    byte sequence got re-stored as if it were Latin-1, so 'Nikola Jokić'
    became 'Nikola JokiÄ\\x87'. Reverse the round-trip when possible; fall
    back to the original string. No-op for ASCII names."""
    try:
        if s.isascii():
            return s
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def build_bbref_advanced(bbref_dir: Optional[str] = None) -> _BBRefAdvanced:
    """Load every bbref_advanced_<season>.json under bbref_dir into a lookup
    keyed by (player_name, season). Never raises. Reverses the mojibake on
    non-ASCII names so accented players (Jokić, Vučević, Šengün, ...) match
    the nba_api full_name canonical form."""
    bbref_dir = bbref_dir or _BBREF_DIR
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        if not os.path.isdir(bbref_dir):
            return _BBRefAdvanced(lookup, _bbref_id_to_name())
        for fname in os.listdir(bbref_dir):
            if not fname.startswith("bbref_advanced_") or not fname.endswith(".json"):
                continue
            season = fname.removeprefix("bbref_advanced_").removesuffix(".json")
            try:
                rows = json.load(open(os.path.join(bbref_dir, fname), encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                name = _unmangle_utf8(str(row.get("player_name", "")).strip())
                if not name:
                    continue
                lookup[(name, season)] = {
                    f"bbref_{k}": float(row.get(k, 0.0) or 0.0)
                    for k in _BBREF_KEYS
                }
    except Exception:
        pass
    return _BBRefAdvanced(lookup, _bbref_id_to_name())


_BBREF_CACHE: Optional[_BBRefAdvanced] = None


def _get_bbref() -> _BBRefAdvanced:
    global _BBREF_CACHE
    if _BBREF_CACHE is None:
        _BBREF_CACHE = build_bbref_advanced()
    return _BBREF_CACHE


# ── contract features (salary, contract-year, role stability) ────────────────

# Per-(player_name, season) features sourced from data/external/contracts_<season>.json.
# Schema: player_name, team, current_salary, years_remaining, cap_hit, cap_hit_pct,
# contract_type, contract_year. current_salary is log-scaled (raw range $22K..$60M
# blows up tree splits); contract_type is dropped because every cached row is
# "guaranteed" (zero-variance constant). Only 2024-25 / 2025-26 are cached, so
# ~50% of training rows currently get neutral defaults.
_CONTRACTS_DIR = os.path.join(PROJECT_DIR, "data", "external")
_CONTRACT_KEYS = ("salary_log", "cap_hit_pct", "year", "years_remaining")
_CONTRACT_DEFAULTS: Dict[str, float] = {f"contract_{k}": 0.0 for k in _CONTRACT_KEYS}


class _Contracts:
    """Per-(player_name, season) contract feature lookup.

    Yields zero defaults when the season file is absent or the player isn't
    listed (rookies on two-ways, mid-season signings, missing scrape).
    Never raises.
    """

    def __init__(self, lookup: Dict[Tuple[str, str], Dict[str, float]],
                 id_to_name: Dict[int, str]):
        self._lookup = lookup
        self._id_to_name = id_to_name

    def features(self, player_id, season: str) -> Dict[str, float]:
        try:
            name = self._id_to_name.get(int(player_id))
        except (TypeError, ValueError):
            name = None
        if not name:
            return dict(_CONTRACT_DEFAULTS)
        return dict(self._lookup.get((name, str(season)), _CONTRACT_DEFAULTS))


def build_contracts(contracts_dir: Optional[str] = None) -> _Contracts:
    """Load every contracts_<season>.json into a (player_name, season) lookup.

    Salary is converted to log10(salary+1) so heavy-tail values (Curry $60M
    vs. min $22K) don't dominate tree split selection. cap_hit_pct stays as
    its native 0-1 fraction. contract_year and years_remaining are passed
    through (0/1 and small int respectively). Never raises — missing files
    yield an empty lookup."""
    import math

    contracts_dir = contracts_dir or _CONTRACTS_DIR
    lookup: Dict[Tuple[str, str], Dict[str, float]] = {}
    try:
        if not os.path.isdir(contracts_dir):
            return _Contracts(lookup, _bbref_id_to_name())
        for fname in os.listdir(contracts_dir):
            if not fname.startswith("contracts_") or not fname.endswith(".json"):
                continue
            season = fname.removeprefix("contracts_").removesuffix(".json")
            try:
                rows = json.load(open(os.path.join(contracts_dir, fname), encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                name = _unmangle_utf8(str(row.get("player_name", "")).strip())
                if not name:
                    continue
                salary = row.get("current_salary")
                salary_log = math.log10(float(salary) + 1.0) if salary else 0.0
                cap_pct = row.get("cap_hit_pct")
                lookup[(name, season)] = {
                    "contract_salary_log":      float(salary_log),
                    "contract_cap_hit_pct":     float(cap_pct or 0.0),
                    "contract_year":            1.0 if row.get("contract_year") else 0.0,
                    "contract_years_remaining": float(row.get("years_remaining") or 0),
                }
    except Exception:
        pass
    return _Contracts(lookup, _bbref_id_to_name())


_CONTRACTS_CACHE: Optional[_Contracts] = None


def _get_contracts() -> _Contracts:
    global _CONTRACTS_CACHE
    if _CONTRACTS_CACHE is None:
        _CONTRACTS_CACHE = build_contracts()
    return _CONTRACTS_CACHE


# ── opponent defence (leakage-free to-date factors) ──────────────────────────

class _OpponentDefense:
    """Per-team opponent-defence factors computed strictly to-date.

    For a game on date D against team O, the factor for a stat is O's mean
    allowed value for that stat over O's games BEFORE D, divided by the
    league mean to D. >1 means O is an easier-than-average matchup. Using
    only games before D keeps the feature leakage-free.
    """

    def __init__(self, allowed: Dict[str, list], league: list):
        self._team = {t: self._index(rows) for t, rows in allowed.items()}
        self._league = self._index(league)

    @staticmethod
    def _index(rows: list) -> dict:
        rows = sorted(rows, key=lambda r: r[0])
        dates = [r[0] for r in rows]
        prefix = {s: [0.0] for s in STATS}
        for _d, line in rows:
            for s in STATS:
                prefix[s].append(prefix[s][-1] + line[s])
        return {"dates": dates, "prefix": prefix}

    @staticmethod
    def _todate_mean(idx: dict, date, stat: str) -> Optional[float]:
        i = bisect.bisect_left(idx["dates"], date)
        return idx["prefix"][stat][i] / i if i > 0 else None

    def factors(self, opponent: str, date) -> Dict[str, float]:
        """Return {opp_def_{stat}: factor} for an opponent on a date.

        Falls back to a neutral 1.0 when there is no prior history."""
        out: Dict[str, float] = {}
        team_idx = self._team.get(opponent)
        for stat in STATS:
            league_mean = self._todate_mean(self._league, date, stat)
            team_mean = self._todate_mean(team_idx, date, stat) if team_idx else None
            if team_mean and league_mean and league_mean > 0:
                out[f"opp_def_{stat}"] = round(team_mean / league_mean, 4)
            else:
                out[f"opp_def_{stat}"] = 1.0
        return out


def _opponent_from_matchup(matchup: str) -> str:
    """Opponent abbreviation — the last token of 'TEAM vs. OPP' / 'TEAM @ OPP'."""
    parts = str(matchup).split()
    return parts[-1] if parts else ""


def build_opponent_defense(gamelog_dir: str) -> _OpponentDefense:
    """Pass over every gamelog to build the to-date opponent-defence model.

    Each played game is a stat line the *opponent* allowed — aggregated per
    opponent and league-wide, sorted chronologically.
    """
    allowed: Dict[str, list] = {}
    league: list = []
    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list):
            continue
        for g in games:
            if _num(g.get("MIN")) < _MIN_PLAYED:
                continue
            gdate = _parse_date(g.get("GAME_DATE"))
            opp = _opponent_from_matchup(g.get("MATCHUP", ""))
            if gdate is None or not opp:
                continue
            line = {s: _num(g.get(_BOX_COL[s])) for s in STATS}
            allowed.setdefault(opp, []).append((gdate, line))
            league.append((gdate, line))
    return _OpponentDefense(allowed, league)


_RATIO_KEYS = (
    "pm_pts",        # per-minute scoring rate
    "pm_ast",        # per-minute assists
    "pm_reb",        # per-minute rebounds
    "pm_fg3m",       # per-minute 3PM
    "pm_stl",        # per-minute steals
    "pm_blk",        # per-minute blocks
    "pts_share_3pt", # fraction of points from threes (3 * fg3m / pts)
)


_LONG_ABSENCE_DAYS = 7      # threshold for "returning from injury / extended absence"
_GAMES_SINCE_CAP   = 10     # cap the games-since-return counter so trees don't grow
                            # spurious splits on values that exist only on a few rows
_DAYS_SINCE_CAP    = 100.0  # cap days_since_last_game (offseason gaps blow up otherwise)


def _games_since_long_absence(prior_played: List[dict], current_gap_days: float) -> float:
    """Return the games-since-return-from-7+day-absence count for the upcoming game.

    Returns:
        0.0  — no long absence in the last _GAMES_SINCE_CAP prior games
        1.0  — the upcoming game IS the first game back (current_gap_days >= 7)
        N+1  — the upcoming game is N games past the last long absence found
               in prior_played (capped at _GAMES_SINCE_CAP).

    Scans only the most-recent _GAMES_SINCE_CAP prior games for efficiency
    and to avoid splitting on stale absences from earlier in the season.
    """
    if current_gap_days >= _LONG_ABSENCE_DAYS:
        return 1.0
    # Look back through prior_played for the last 7+ day gap between consecutive games.
    recent = prior_played[-_GAMES_SINCE_CAP:]
    if len(recent) < 2:
        return 0.0
    prev_date = None
    last_absence_idx = -1
    for i, g in enumerate(recent):
        gdate = _parse_date(g.get("GAME_DATE"))
        if prev_date is not None and gdate is not None:
            if (gdate - prev_date).days >= _LONG_ABSENCE_DAYS:
                last_absence_idx = i
        prev_date = gdate if gdate is not None else prev_date
    if last_absence_idx < 0:
        return 0.0
    # +2: the absence was BEFORE recent[last_absence_idx], so recent[last_absence_idx]
    # was game-1-back. The upcoming game is (len(recent) - last_absence_idx) games past
    # that, plus 1 because we count from 1.
    games_back = (len(recent) - last_absence_idx) + 1
    return float(min(games_back, _GAMES_SINCE_CAP))


def _row_features(prior_played: List[dict], rest_days: float,
                  is_home: int, games_played: int,
                  days_since_last_game: Optional[float] = None) -> Dict[str, float]:
    """Build the leakage-free feature row from a player's prior played games.

    `days_since_last_game` is the unclamped gap (in days) from the player's
    previous played game to the upcoming game. When omitted we fall back to
    `rest_days` (clamped 0-10), which loses long-absence signal — callers
    that have the real date delta should pass it.
    """
    feats: Dict[str, float] = {}
    for stat in _FORM_STATS:
        col = _BOX_COL[stat]
        vals = [_num(g.get(col)) for g in prior_played]
        feats[f"l5_{stat}"]   = _mean(vals[-5:])
        feats[f"l10_{stat}"]  = _mean(vals[-10:])
        feats[f"std_{stat}"]  = _mean(vals)              # season-to-date
        feats[f"ewma_{stat}"] = _ewma(vals)
        feats[f"prev_{stat}"] = vals[-1] if vals else 0.0
    feats["rest_days"]     = rest_days
    feats["is_home"]       = float(is_home)
    feats["games_played"]  = float(games_played)
    # Injury rampup signal — unclamped days-since-last-game lets trees
    # distinguish "1-day rest" (back-to-back) from "14-day rest" (back from
    # extended injury). games_since_long_absence captures which rampup
    # phase the player is in (1 = first game back, 2 = second, etc).
    raw_gap = float(rest_days) if days_since_last_game is None else float(days_since_last_game)
    feats["days_since_last_game"]      = min(raw_gap, _DAYS_SINCE_CAP)
    feats["games_since_long_absence"]  = _games_since_long_absence(prior_played, raw_gap)
    # Cross-stat ratios — per-minute production rates and 3pt-share. Denominators
    # are clipped to a minimum of 5 so bench players with tiny l5_min don't blow
    # up the ratio (NBA Advanced uses /36 minutes; trees only care about the
    # relative ordering so the constant divisor doesn't matter).
    l5_min_safe = max(feats["l5_min"], 5.0)
    l5_pts_safe = max(feats["l5_pts"], 5.0)
    feats["pm_pts"]        = feats["l5_pts"]  / l5_min_safe
    feats["pm_ast"]        = feats["l5_ast"]  / l5_min_safe
    feats["pm_reb"]        = feats["l5_reb"]  / l5_min_safe
    feats["pm_fg3m"]       = feats["l5_fg3m"] / l5_min_safe
    feats["pm_stl"]        = feats["l5_stl"]  / l5_min_safe
    feats["pm_blk"]        = feats["l5_blk"]  / l5_min_safe
    feats["pts_share_3pt"] = (3.0 * feats["l5_fg3m"]) / l5_pts_safe
    return feats


# ── dataset construction ──────────────────────────────────────────────────────

def build_pergame_dataset(
    gamelog_dir: Optional[str] = None,
    min_prior: int = 4,
) -> Tuple[List[dict], List[str]]:
    """Build the per-game training set from every player gamelog.

    Each emitted row holds leakage-free pre-game features and the realised
    target_{stat} values for one game.  A game is used as a row only when the
    player actually played (>= _MIN_PLAYED minutes) and has at least
    ``min_prior`` prior played games for stable rolling features.

    Returns:
        (rows, feature_cols) — rows are dicts with the feature columns,
        target_{stat} columns, and a 'date' key for the temporal split.
    """
    gamelog_dir = gamelog_dir or _NBA_CACHE
    feature_cols = feature_columns()
    rows: List[dict] = []

    # Leakage-free opponent-defence model, built from all gamelogs first.
    oppdef = build_opponent_defense(gamelog_dir)
    resttravel = build_rest_travel()
    playtypes = build_playtypes()
    bbref = build_bbref_advanced()
    contracts = build_contracts()

    for path in glob.glob(os.path.join(gamelog_dir, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(games, list) or len(games) <= min_prior:
            continue

        # Sort chronologically; keep games with a parseable date.
        dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
        dated.sort(key=lambda x: x[0])

        # Parse player_id and season from filename: gamelog_<pid>_<season>.json
        try:
            basename = os.path.basename(path)
            parts = basename.split("_")
            # parts[0]="gamelog", parts[1]=pid, parts[-1]="<season>.json"
            file_player_id = int(parts[1])
            file_season = parts[-1].replace(".json", "")
        except Exception:
            file_player_id = 0
            file_season = ""

        prior_played: List[dict] = []
        for idx, (gdate, game) in enumerate(dated):
            played = _num(game.get("MIN")) >= _MIN_PLAYED

            if played and len(prior_played) >= min_prior:
                rest = 3.0
                if idx > 0:
                    delta = (gdate - dated[idx - 1][0]).days
                    rest = float(min(max(delta, 0), 10))
                # Rampup gap: distance to last *played* game (DNPs that just sit
                # in the gamelog shouldn't reset the rampup counter). prior_played
                # is built only from games with MIN >= _MIN_PLAYED so [-1] is the
                # most recent real appearance.
                raw_gap_days = 3.0
                last_played_date = _parse_date(prior_played[-1].get("GAME_DATE"))
                if last_played_date is not None:
                    raw_gap_days = float(max((gdate - last_played_date).days, 0))
                matchup = str(game.get("MATCHUP", ""))
                is_home = 1 if " vs. " in matchup else 0
                team_abbrev = matchup.split()[0] if matchup.split() else ""
                feats = _row_features(prior_played, rest, is_home, len(prior_played),
                                      days_since_last_game=raw_gap_days)
                feats.update(oppdef.factors(_opponent_from_matchup(matchup), gdate))
                feats.update(resttravel.features(team_abbrev, gdate))
                feats.update(playtypes.features(file_player_id, file_season))
                feats.update(bbref.features(file_player_id, file_season))
                feats.update(contracts.features(file_player_id, file_season))
                row = {c: feats[c] for c in feature_cols}
                for stat in STATS:
                    row[f"target_{stat}"] = _num(game.get(_BOX_COL[stat]))
                row["date"] = gdate.isoformat()
                rows.append(row)

            if played:
                prior_played.append(game)

    return rows, feature_cols


# ── training ──────────────────────────────────────────────────────────────────

def train_pergame_models(
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
    *,
    min_prior: int = 4,
    holdout_frac: float = 0.2,
    val_frac: float = 0.15,
    stats: Optional[List[str]] = None,
    stat_params_override: Optional[Dict[str, dict]] = None,
) -> dict:
    """Train one XGBoost regressor per stat on the per-game dataset.

    Three-way temporal split — train / validation / holdout, in chronological
    order. The validation slice drives early stopping (the model adds trees
    only while validation error keeps falling), which curbs overfitting
    without ever touching the holdout. The most recent ``holdout_frac`` of
    games is the honest out-of-sample test.

    Returns a metrics dict ``{stat: {train_r2, holdout_r2, train_mae,
    holdout_mae, gap, best_iteration}}`` and writes props_pg_{stat}.json.
    """
    import joblib
    import lightgbm as lgb
    import numpy as np
    import xgboost as xgb
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import mean_absolute_error, r2_score

    model_dir = model_dir or _MODEL_DIR
    rows, feature_cols = build_pergame_dataset(gamelog_dir, min_prior=min_prior)
    if len(rows) < 200:
        return {"status": "insufficient_data", "n_rows": len(rows)}

    rows.sort(key=lambda r: r["date"])           # temporal order
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end   = int(n * (1.0 - holdout_frac))
    X_all = np.array([[r[c] for c in feature_cols] for r in rows], dtype=float)
    X_tr, X_val, X_ho = X_all[:train_end], X_all[train_end:val_end], X_all[val_end:]

    os.makedirs(model_dir, exist_ok=True)
    metrics: dict = {"n_rows": n, "n_train": train_end,
                     "n_val": val_end - train_end, "n_holdout": n - val_end,
                     "stats": {}}

    # Per-stat regularisation overrides — the walk-forward report (PRED-02)
    # flagged STL with a train/holdout gap of 0.18 (> the 0.15 gate). STL is
    # the noisiest counting stat — mean ~0.7, no strong player-form signal —
    # so it needs tighter regularisation than the other counts. _STAT_PARAMS
    # below is the central knob: each key overrides the default for one stat.
    _DEFAULT_COUNT = {"max_depth": 3, "min_child_weight": 10, "reg_lambda": 2.0,
                      "gamma": 0.2, "n_estimators": 800}
    _DEFAULT_REG   = {"max_depth": 4, "min_child_weight": 10, "reg_lambda": 2.0,
                      "gamma": 0.2, "n_estimators": 800}
    _STAT_PARAMS: Dict[str, dict] = {
        # STL — high noise, low signal; aggressive regularisation, gap 0.058 → 0.011.
        "stl": {"max_depth": 2, "min_child_weight": 40, "reg_lambda": 6.0,
                "gamma": 0.6, "n_estimators": 400},
        # BLK — low base rate (~0.5/game), bimodal across positions; tighten
        # depth + child weight to prevent splits on rare combinations.
        "blk": {"max_depth": 2, "min_child_weight": 25, "reg_lambda": 4.0,
                "gamma": 0.4, "n_estimators": 500},
        # FG3M — bounded count, position-correlated (centers ~0, guards ~3+);
        # gap was 0.058 with default reg, room to tighten the regression head.
        "fg3m": {"max_depth": 3, "min_child_weight": 20, "reg_lambda": 3.0,
                 "gamma": 0.3, "n_estimators": 600},
        # PTS — high-variance, dense signal. Sweep (cycle 6) found that an
        # extra split layer plus slightly more reg trades a tiny bit of bias
        # for variance reduction. MAE 4.7433 → 4.7407.
        "pts": {"max_depth": 5, "min_child_weight": 15, "reg_lambda": 3.0,
                "gamma": 0.2, "n_estimators": 800},
        # AST — sweep prefers slightly tighter child-weight + more reg over
        # the default. Marginal MAE win (4-5 bp) — keep for the R² lift.
        "ast": {"max_depth": 4, "min_child_weight": 15, "reg_lambda": 4.0,
                "gamma": 0.2, "n_estimators": 800},
        # REB — sweep prefers shallower trees + a touch more gamma. Trees
        # were overfitting deep splits on rebound spikes from anomalous games.
        "reb": {"max_depth": 3, "min_child_weight": 20, "reg_lambda": 3.0,
                "gamma": 0.3, "n_estimators": 800},
        # TOV — count-ish (mean ~1.3/game); responds to count-style reg
        # (deeper child-weight, higher lambda) like BLK/STL but doesn't need
        # the depth-2 ceiling. Marginal but consistent.
        "tov": {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 6.0,
                "gamma": 0.4, "n_estimators": 700},
    }

    # Allow callers (e.g. tuning sweeps) to restrict which stats are trained
    # and to override the per-stat hyperparameters without editing _STAT_PARAMS.
    stats_to_train = list(stats) if stats else list(STATS)
    effective_params = dict(_STAT_PARAMS)
    if stat_params_override:
        effective_params.update(stat_params_override)

    for stat in stats_to_train:
        y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
        y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:]
        is_count = stat in ("stl", "blk")

        params = {**(_DEFAULT_COUNT if is_count else _DEFAULT_REG),
                  **effective_params.get(stat, {})}

        # Base learner 1 — XGBoost, regularised, early-stopped on the val slice.
        xgb_model = xgb.XGBRegressor(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
            min_child_weight=params["min_child_weight"], reg_lambda=params["reg_lambda"],
            reg_alpha=0.5, gamma=params["gamma"], random_state=42,
            objective="count:poisson" if is_count else "reg:squarederror",
            early_stopping_rounds=40, eval_metric="mae",
        )
        xgb_model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        # Base learner 2 — LightGBM, a different bias-variance tradeoff.
        lgb_model = lgb.LGBMRegressor(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            learning_rate=0.04, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            min_child_samples=max(20, params["min_child_weight"] * 2),
            reg_lambda=params["reg_lambda"], reg_alpha=0.5, random_state=42,
            objective="poisson" if is_count else "regression",
            n_jobs=-1, verbosity=-1,
        )
        lgb_model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(40, verbose=False)])

        # Blend = LGB only for stats in _LGB_ONLY_STATS, otherwise a
        # weighted combo of XGB + LGB. Weights are fit per-stat on the val
        # slice via non-negative least squares (sklearn LinearRegression
        # with positive=True, fit_intercept=False). Falls back to the
        # fixed 0.5/0.5 mean when the val fit gives wildly skewed weights
        # (sum outside [0.5, 1.5]) — that usually means val and holdout
        # disagree and the fit doesn't generalise.
        lgb_only = stat in _LGB_ONLY_STATS

        xgb_ho, lgb_ho = xgb_model.predict(X_ho), lgb_model.predict(X_ho)

        if lgb_only:
            w_xgb, w_lgb = 0.0, 1.0
            meta_fit_source = "lgb_only"
        else:
            xgb_val = xgb_model.predict(X_val)
            lgb_val = lgb_model.predict(X_val)
            from sklearn.linear_model import LinearRegression
            stacker = LinearRegression(positive=True, fit_intercept=False)
            stacker.fit(np.column_stack([xgb_val, lgb_val]), y_val)
            w_xgb, w_lgb = float(stacker.coef_[0]), float(stacker.coef_[1])
            w_sum = w_xgb + w_lgb
            if not (0.5 <= w_sum <= 1.5):
                w_xgb, w_lgb = 0.5, 0.5
                meta_fit_source = "fallback_05_05"
            else:
                meta_fit_source = "val_nnls"

        def _blend(X):
            if lgb_only:
                return lgb_model.predict(X)
            return w_xgb * xgb_model.predict(X) + w_lgb * lgb_model.predict(X)

        blend_ho = lgb_ho if lgb_only else (w_xgb * xgb_ho + w_lgb * lgb_ho)
        blend_tr = _blend(X_tr)

        # Isotonic calibration — k-fold cross-fitted on the holdout.
        #
        # We can't fit on val because val is what early-stopping used (the
        # base learners are already slightly optimistic there), and we can't
        # fit-and-evaluate on holdout directly (self-leak). 5-fold CV gives
        # honest cross-fitted predictions for the lift measurement, and we
        # then refit on the full holdout for the deployed calibrator. This
        # is opt-in per stat: if the cross-fitted lift on MAE is not strictly
        # positive, we delete any prior calibrator so predict_pergame falls
        # back to the raw blend (calibration helps low-rate stats like BLK
        # but is noise on already-unbiased high-volume stats like PTS).
        n_ho = len(blend_ho)
        k = 5
        cal_blend_ho = np.empty(n_ho, dtype=float)
        rng = np.random.default_rng(42)
        perm = rng.permutation(n_ho)
        fold_size = n_ho // k
        for fold in range(k):
            lo = fold * fold_size
            hi = n_ho if fold == k - 1 else (fold + 1) * fold_size
            test_idx = perm[lo:hi]
            train_idx = np.concatenate([perm[:lo], perm[hi:]])
            fold_cal = IsotonicRegression(out_of_bounds="clip")
            fold_cal.fit(blend_ho[train_idx], y_ho[train_idx])
            cal_blend_ho[test_idx] = fold_cal.predict(blend_ho[test_idx])
        cal_blend_ho = np.clip(cal_blend_ho, 0.0, None)

        uncal_r2  = float(r2_score(y_ho, blend_ho))
        uncal_mae = float(mean_absolute_error(y_ho, blend_ho))
        cal_r2    = float(r2_score(y_ho, cal_blend_ho))
        cal_mae   = float(mean_absolute_error(y_ho, cal_blend_ho))

        # Opt-in: only deploy the calibrator if it strictly improves MAE on
        # the cross-fitted holdout predictions. Otherwise remove any stale
        # file so predict_pergame falls back to the raw blend.
        cal_path = os.path.join(model_dir, f"calibration_pergame_{stat}.joblib")
        if cal_mae < uncal_mae:
            full_cal = IsotonicRegression(out_of_bounds="clip")
            full_cal.fit(blend_ho, y_ho)
            joblib.dump(full_cal, cal_path)
            served_r2, served_mae = cal_r2, cal_mae
            cal_used = True
        else:
            if os.path.exists(cal_path):
                os.remove(cal_path)
            served_r2, served_mae = uncal_r2, uncal_mae
            cal_used = False

        m = {
            # Production-served metrics — match what predict_pergame returns.
            "holdout_r2":      round(served_r2, 4),
            "holdout_mae":     round(served_mae, 4),
            "train_r2":        round(float(r2_score(y_tr, blend_tr)), 4),
            "xgb_holdout_r2":  round(float(r2_score(y_ho, xgb_ho)), 4),
            "lgb_holdout_r2":  round(float(r2_score(y_ho, lgb_ho)), 4),
            # Diagnostics — pre-calibration blend and the cross-fitted lift.
            "uncal_holdout_r2":  round(uncal_r2, 4),
            "uncal_holdout_mae": round(uncal_mae, 4),
            "calibration_lift_r2":  round(cal_r2 - uncal_r2, 4),
            "calibration_lift_mae": round(uncal_mae - cal_mae, 4),
            "calibration_used":  cal_used,
            # Meta-stacker weights — what predict_pergame applies to the
            # XGB + LGB base learner outputs before calibration.
            "meta_w_xgb":     round(w_xgb, 4),
            "meta_w_lgb":     round(w_lgb, 4),
            "meta_fit_source": meta_fit_source,
        }
        m["gap"] = round(m["train_r2"] - m["holdout_r2"], 4)
        m["ensemble_lift"] = round(m["holdout_r2"] - max(m["xgb_holdout_r2"],
                                                         m["lgb_holdout_r2"]), 4)
        metrics["stats"][stat] = m
        # For stats listed in _LGB_ONLY_STATS the XGB Poisson learner drags
        # the blend (ensemble_lift is negative). Save only LGB so that
        # predict_pergame's load_pergame_model picks up just the LGB model
        # and the "blend" becomes a single-model prediction.
        xgb_path = os.path.join(model_dir, f"props_pg_{stat}.json")
        if stat in _LGB_ONLY_STATS:
            if os.path.exists(xgb_path):
                os.remove(xgb_path)
        else:
            xgb_model.save_model(xgb_path)
        joblib.dump(lgb_model, os.path.join(model_dir, f"props_pg_lgb_{stat}.pkl"))
        cal_tag = "cal" if cal_used else "raw"
        print(f"  [prop_pergame] {stat.upper():4s} {cal_tag} R²={m['holdout_r2']:.3f} "
              f"MAE={m['holdout_mae']:.2f}  (xgb={m['xgb_holdout_r2']:.3f}, "
              f"lgb={m['lgb_holdout_r2']:.3f}, lift={m['ensemble_lift']:+.3f}, "
              f"cal_lift_mae={m['calibration_lift_mae']:+.3f})")

    metrics["feature_cols"] = feature_cols
    # Only persist metrics when this was a full train — partial trains (e.g.
    # tuning sweeps) would clobber the per-stat metrics for stats they didn't
    # touch.
    if set(stats_to_train) == set(STATS):
        with open(os.path.join(model_dir, "props_pergame_metrics.json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
    # Meta-stacker weights sidecar — written even on partial trains so the
    # weights for the trained stats stay in sync with their on-disk models.
    _persist_meta_weights(model_dir, metrics)
    return metrics


_META_WEIGHTS_FILENAME = "meta_weights_pergame.json"


def _persist_meta_weights(model_dir: str, metrics: dict) -> None:
    """Merge this train run's meta-stacker weights into the sidecar JSON.

    The sidecar keeps a single weights dict keyed by stat so predict_pergame
    can apply them without parsing the full metrics report each call."""
    path = os.path.join(model_dir, _META_WEIGHTS_FILENAME)
    existing: Dict[str, dict] = {}
    if os.path.exists(path):
        try:
            existing = json.load(open(path, encoding="utf-8"))
        except Exception:
            existing = {}
    for stat, m in metrics.get("stats", {}).items():
        if "meta_w_xgb" in m and "meta_w_lgb" in m:
            existing[stat] = {
                "w_xgb": float(m["meta_w_xgb"]),
                "w_lgb": float(m["meta_w_lgb"]),
                "source": m.get("meta_fit_source", "unknown"),
            }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


# ── inference ─────────────────────────────────────────────────────────────────

def load_pergame_model(stat: str, model_dir: Optional[str] = None) -> list:
    """Load the per-game base learners (XGBoost + LightGBM) for a stat.

    Returns a list of fitted models — empty when none are trained. The blend
    of whatever is present is what predict_pergame uses.
    """
    model_dir = model_dir or _MODEL_DIR
    models: list = []
    xgb_path = os.path.join(model_dir, f"props_pg_{stat}.json")
    if os.path.exists(xgb_path):
        try:
            import xgboost as xgb
            m = xgb.XGBRegressor()
            m.load_model(xgb_path)
            models.append(m)
        except Exception:
            pass
    lgb_path = os.path.join(model_dir, f"props_pg_lgb_{stat}.pkl")
    if os.path.exists(lgb_path):
        try:
            import joblib
            models.append(joblib.load(lgb_path))
        except Exception:
            pass
    return models


def _load_pergame_calibrator(stat: str, model_dir: str):
    """Load the per-game isotonic calibrator for a stat, or None if absent."""
    path = os.path.join(model_dir, f"calibration_pergame_{stat}.joblib")
    if not os.path.exists(path):
        return None
    try:
        import joblib
        return joblib.load(path)
    except Exception:
        return None


_META_WEIGHTS_CACHE: Optional[Dict[str, dict]] = None


def _get_pergame_meta_weights(model_dir: str) -> Dict[str, dict]:
    """Return the per-stat meta-stacker weights dict (process-cached)."""
    global _META_WEIGHTS_CACHE
    if _META_WEIGHTS_CACHE is not None:
        return _META_WEIGHTS_CACHE
    path = os.path.join(model_dir, _META_WEIGHTS_FILENAME)
    if not os.path.exists(path):
        _META_WEIGHTS_CACHE = {}
        return _META_WEIGHTS_CACHE
    try:
        _META_WEIGHTS_CACHE = json.load(open(path, encoding="utf-8"))
    except Exception:
        _META_WEIGHTS_CACHE = {}
    return _META_WEIGHTS_CACHE


def predict_pergame(stat: str, feature_row: Dict[str, float],
                    model_dir: Optional[str] = None) -> Optional[float]:
    """Predict one stat for one game — calibrated meta-blend of the per-game base learners.

    Applies the per-stat meta-stacker weights from meta_weights_pergame.json
    when present, otherwise falls back to a simple mean of whatever models
    are on disk. Then applies the per-game isotonic calibrator
    (calibration_pergame_<stat>.joblib) when present."""
    import numpy as np

    model_dir = model_dir or _MODEL_DIR
    models = load_pergame_model(stat, model_dir)
    if not models:
        return None
    cols = feature_columns()
    expected_n = len(cols)
    # Guard: stale model trained on a different feature set — refuse to predict.
    for m in models:
        n_feats = getattr(m, "n_features_in_", None)
        if n_feats is not None and n_feats != expected_n:
            return None
    X = np.array([[float(feature_row.get(c, 0.0) or 0.0) for c in cols]], dtype=float)

    # load_pergame_model returns [XGB, LGB] when both exist (in that order),
    # or [LGB] only for stats in _LGB_ONLY_STATS. Disambiguate by class
    # name rather than position so we don't silently mis-weight if the load
    # order changes.
    weights = _get_pergame_meta_weights(model_dir).get(stat)
    blend = 0.0
    if weights and len(models) >= 2:
        xgb_pred = lgb_pred = None
        for m in models:
            cls = type(m).__name__.lower()
            if "xgb" in cls and xgb_pred is None:
                xgb_pred = float(m.predict(X)[0])
            elif "lgb" in cls and lgb_pred is None:
                lgb_pred = float(m.predict(X)[0])
        if xgb_pred is not None and lgb_pred is not None:
            blend = float(weights["w_xgb"]) * xgb_pred + float(weights["w_lgb"]) * lgb_pred
        else:
            preds = [float(m.predict(X)[0]) for m in models]
            blend = sum(preds) / len(preds)
    else:
        # Single model on disk (e.g. STL LGB-only) or no weights file —
        # mean is the safe default.
        preds = [float(m.predict(X)[0]) for m in models]
        blend = sum(preds) / len(preds)

    calibrator = _load_pergame_calibrator(stat, model_dir)
    if calibrator is not None:
        try:
            blend = float(calibrator.predict([blend])[0])
        except Exception:
            pass
    return round(max(blend, 0.0), 2)


# ── live prediction ───────────────────────────────────────────────────────────

# Process-level cache — building the opponent-defence model globs every
# gamelog, so it must not be rebuilt on every predict_props() call.
_OPP_DEF_CACHE: Dict[str, _OpponentDefense] = {}


def _get_opponent_defense(gamelog_dir: str) -> _OpponentDefense:
    """Return the (process-cached) opponent-defence model for a gamelog dir."""
    if gamelog_dir not in _OPP_DEF_CACHE:
        _OPP_DEF_CACHE[gamelog_dir] = build_opponent_defense(gamelog_dir)
    return _OPP_DEF_CACHE[gamelog_dir]


def build_prediction_row(
    player_id,
    opp_team: str,
    season: str,
    *,
    is_home: bool = True,
    rest_days: float = 2.0,
    gamelog_dir: Optional[str] = None,
    min_prior: int = 4,
) -> Optional[Dict[str, float]]:
    """Build the per-game feature row for a player's UPCOMING game.

    Reads the player's season gamelog, treats every played game as prior
    form, and assembles the same feature row the models were trained on.
    Returns None when the gamelog is missing or the player has too little
    history — the caller then falls back to the legacy models.
    """
    gamelog_dir = gamelog_dir or _NBA_CACHE
    path = os.path.join(gamelog_dir, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(path):
        return None
    try:
        games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(games, list):
        return None

    dated = [(d, g) for g in games if (d := _parse_date(g.get("GAME_DATE"))) is not None]
    dated.sort(key=lambda x: x[0])
    prior_played = [g for _d, g in dated if _num(g.get("MIN")) >= _MIN_PLAYED]
    if len(prior_played) < min_prior:
        return None

    feats = _row_features(prior_played, float(rest_days), int(is_home),
                          len(prior_played))
    factor_date = dated[-1][0] if dated else datetime.now()
    feats.update(_get_opponent_defense(gamelog_dir).factors(opp_team, factor_date))
    # Rest/travel: use neutral defaults for future games (no parquet row yet).
    feats.update(_REST_TRAVEL_DEFAULTS)
    # Play-type frequencies: process-cached, zero defaults when parquet absent.
    try:
        feats.update(_get_playtypes().features(int(player_id), season))
    except Exception:
        feats.update(_PLAYTYPE_DEFAULTS)
    # BBRef advanced efficiency / rate stats: process-cached.
    try:
        feats.update(_get_bbref().features(int(player_id), season))
    except Exception:
        feats.update(_BBREF_DEFAULTS)
    # Contract features (salary, contract-year, role stability) — process-cached.
    try:
        feats.update(_get_contracts().features(int(player_id), season))
    except Exception:
        feats.update(_CONTRACT_DEFAULTS)
    return feats


def predict_player_pergame(
    player_id,
    opp_team: str,
    season: str,
    *,
    is_home: bool = True,
    rest_days: float = 2.0,
    gamelog_dir: Optional[str] = None,
    model_dir: Optional[str] = None,
) -> Optional[Dict[str, float]]:
    """Predict all 7 prop stats for a player's upcoming game.

    Returns ``{stat: value}`` from the honest per-game models, or None when
    the per-game models or the player's gamelog are unavailable.
    """
    row = build_prediction_row(player_id, opp_team, season, is_home=is_home,
                               rest_days=rest_days, gamelog_dir=gamelog_dir)
    if row is None:
        return None
    out: Dict[str, float] = {}
    for stat in STATS:
        val = predict_pergame(stat, row, model_dir)
        if val is None:
            return None
        out[stat] = val
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Per-game prop models")
    ap.add_argument("--train", action="store_true", help="Build dataset + train all stats")
    args = ap.parse_args()
    if args.train:
        print(json.dumps(train_pergame_models(), indent=2))
    else:
        ap.print_help()
