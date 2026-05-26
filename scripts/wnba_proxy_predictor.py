"""wnba_proxy_predictor.py - lean WNBA player-prop predictor (R17_J6).

This is a deliberately minimal baseline so we can rank WNBA bets the same day
the Bovada daemon starts producing WNBA prop lines. It is NOT a production
model - just an L5 rolling-mean predictor with league-mean shrinkage and a
normal-approx quantile band derived from the player's own recent stddev.

Design (mirrors the q50 / q10 / q90 contract used by live_bet_ranker):

    q50 = (1-w) * L5_mean(player) + w * league_mean(stat)
    q10 = q50 - 1.2816 * sigma_player
    q90 = q50 + 1.2816 * sigma_player

where w = league_shrink / (n_recent + league_shrink) and sigma_player is the
sample stddev of the same L5 window (floored).

Public API:
    predict_player(player_id, ...) -> dict[stat -> {q10,q50,q90,n_games,...}]
    predict_player_by_name(name, ...) -> dict
    league_means(season=...) -> dict[stat -> float]

Stats covered: pts, reb, ast, fg3m, stl, blk, tov - identical to NBA pipeline.
"""
from __future__ import annotations

import logging
import time
import unicodedata
from functools import lru_cache
from typing import Any, Dict, Iterable, Optional

import pandas as pd

log = logging.getLogger("wnba_proxy_predictor")

# League ID for WNBA in the NBA Stats API
WNBA_LEAGUE_ID = "10"

# 7-stat canonical universe (matches NBA pipeline)
STATS: tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Map our canonical codes -> NBA Stats column names in PlayerGameLog
_STAT_TO_COL = {
    "pts":  "PTS",
    "reb":  "REB",
    "ast":  "AST",
    "fg3m": "FG3M",
    "stl":  "STL",
    "blk":  "BLK",
    "tov":  "TOV",
}

# Conservative WNBA league per-game means (2025 season ballpark).
# Used as the shrinkage prior; daily tuning unnecessary at this scale.
LEAGUE_MEAN_2025 = {
    "pts":  9.1,
    "reb":  3.7,
    "ast":  2.1,
    "fg3m": 0.9,
    "stl":  0.7,
    "blk":  0.4,
    "tov":  1.3,
}

# Floor sigma per stat so we never collapse the quantile band to ~0.
# Roughly half of league mean - keeps Phi-based hit probs from degenerating.
_SIGMA_FLOOR = {
    "pts":  4.0,
    "reb":  1.8,
    "ast":  1.2,
    "fg3m": 0.7,
    "stl":  0.6,
    "blk":  0.4,
    "tov":  0.9,
}

# z * sigma to hit the 10th / 90th normal quantile.
_Z_80 = 1.2816

# Shrinkage strength (in pseudo-games). w = K / (n + K)
DEFAULT_SHRINK = 3.0

# Default L5 lookback
DEFAULT_LOOKBACK = 5


# ----- helpers ---------------------------------------------------------------
def _strip_diacritics(name: str) -> str:
    n = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in n if not unicodedata.combining(c)).lower().strip()


@lru_cache(maxsize=4)
def _wnba_roster(season: str = "2025") -> pd.DataFrame:
    """Return active WNBA players for the given season. Cached.

    Uses is_only_current_season=0 + TO_YEAR filter because the
    `is_only_current_season=1` path returns an incomplete league subset
    (only ~74 rows, missing big-name 2025/2026 stars).
    """
    from nba_api.stats.endpoints import commonallplayers
    df = commonallplayers.CommonAllPlayers(
        league_id=WNBA_LEAGUE_ID, season=season,
        is_only_current_season=0, timeout=30,
    ).get_data_frames()[0]
    # Keep only currently-rostered players (ROSTERSTATUS == 1) whose TO_YEAR
    # is at or past the requested season. Cheap, robust, and includes stars
    # like A'ja Wilson / Caitlin Clark / Sabrina Ionescu that the
    # `current_season=1` query omits.
    try:
        season_int = int(season)
        to_year = pd.to_numeric(df["TO_YEAR"], errors="coerce").fillna(0).astype(int)
        roster = pd.to_numeric(df.get("ROSTERSTATUS", 0), errors="coerce").fillna(0).astype(int)
        df = df[(to_year >= season_int) & (roster == 1)].reset_index(drop=True)
    except Exception:  # noqa: BLE001
        pass
    return df


def resolve_wnba_player(name: str, season: str = "2025") -> Optional[int]:
    """Look up the WNBA PERSON_ID for a player name. Case- and accent-insensitive."""
    try:
        df = _wnba_roster(season)
    except Exception as e:  # noqa: BLE001
        log.warning("WNBA roster fetch failed: %s", e)
        return None
    needle = _strip_diacritics(name)
    for _, r in df.iterrows():
        if _strip_diacritics(r["DISPLAY_FIRST_LAST"]) == needle:
            return int(r["PERSON_ID"])
    for _, r in df.iterrows():
        last_first = _strip_diacritics(r["DISPLAY_LAST_COMMA_FIRST"]).replace(",", "")
        if last_first == needle.replace(",", ""):
            return int(r["PERSON_ID"])
    for _, r in df.iterrows():
        if needle in _strip_diacritics(r["DISPLAY_FIRST_LAST"]):
            return int(r["PERSON_ID"])
    return None


@lru_cache(maxsize=256)
def _gamelog_cached(player_id: int, season: str) -> Optional[pd.DataFrame]:
    """Return PlayerGameLog rows sorted newest-first. Cached per (pid, season)."""
    from nba_api.stats.endpoints import playergamelog
    try:
        df = playergamelog.PlayerGameLog(
            player_id=player_id,
            season=season,
            league_id_nullable=WNBA_LEAGUE_ID,
            season_type_all_star="Regular Season",
            timeout=30,
        ).get_data_frames()[0]
    except Exception as e:  # noqa: BLE001
        log.warning("gamelog fetch %s/%s failed: %s", player_id, season, e)
        return None
    if df is None or df.empty:
        return df
    df = df.copy()
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], format="%b %d, %Y", errors="coerce")
    df = df.sort_values("GAME_DATE", ascending=False).reset_index(drop=True)
    return df


def league_means(season: str = "2025") -> Dict[str, float]:
    """Return league per-game means for each canonical stat."""
    return dict(LEAGUE_MEAN_2025)


def _normal_quantile_band(mu: float, sigma: float) -> tuple[float, float, float]:
    """Return (q10, q50, q90) clipped to >= 0."""
    q50 = max(0.0, mu)
    q10 = max(0.0, mu - _Z_80 * sigma)
    q90 = max(0.0, mu + _Z_80 * sigma)
    return q10, q50, q90


# ----- public API ------------------------------------------------------------
def predict_player(
    player_id: int,
    season: str = "2025",
    lookback: int = DEFAULT_LOOKBACK,
    shrink: float = DEFAULT_SHRINK,
    league_priors: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Return per-stat quantile predictions for a WNBA player_id.

    Output shape (matches NBA model contract):
        {
          'pts': {'q10':..., 'q50':..., 'q90':..., 'point':..., 'n_games':int,
                  'mu_raw':float, 'sigma':float, 'shrink_weight':float,
                  'availability_factor': 1.0},
          ...
        }

    Returns None if no gamelog rows could be fetched.
    """
    df = _gamelog_cached(int(player_id), season)
    if df is None or df.empty:
        return None
    league = league_priors if league_priors is not None else LEAGUE_MEAN_2025
    recent = df.head(int(lookback))
    n = len(recent)
    if n == 0:
        return None

    out: Dict[str, Dict[str, Any]] = {}
    for stat in STATS:
        col = _STAT_TO_COL[stat]
        if col not in recent.columns:
            continue
        vals = pd.to_numeric(recent[col], errors="coerce").dropna()
        # Season-long baseline for this player: the right prior for an
        # individual's small-sample L5 is the player's own season mean,
        # NOT the league average (which over-shrinks stars by ~6+ PTS).
        season_vals = pd.to_numeric(df[col], errors="coerce").dropna()
        season_mean = float(season_vals.mean()) if not season_vals.empty \
            else float(league.get(stat, 0.0))
        if vals.empty:
            mu_raw = season_mean
            sigma = float(_SIGMA_FLOOR[stat])
            w = 1.0
        else:
            mu_raw = float(vals.mean())
            sigma_obs = float(vals.std(ddof=1)) if len(vals) >= 2 else 0.0
            sigma = max(sigma_obs, float(_SIGMA_FLOOR[stat]))
            w = float(shrink) / (float(len(vals)) + float(shrink))
        # Shrink L5 toward the player's season mean (small-sample stabiliser).
        prior = season_mean
        mu = (1.0 - w) * mu_raw + w * prior
        q10, q50, q90 = _normal_quantile_band(mu, sigma)
        out[stat] = {
            "q10": q10,
            "q50": q50,
            "q90": q90,
            "point": q50,
            "n_games": n,
            "mu_raw": mu_raw,
            "sigma": sigma,
            "shrink_weight": w,
            "prior": prior,
            "availability_factor": 1.0,
        }
    return out


def predict_player_by_name(
    name: str,
    season: str = "2025",
    lookback: int = DEFAULT_LOOKBACK,
    shrink: float = DEFAULT_SHRINK,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Convenience wrapper: name -> predict_player."""
    pid = resolve_wnba_player(name, season=season)
    if pid is None:
        log.warning("WNBA player not found: %s", name)
        return None
    return predict_player(pid, season=season, lookback=lookback, shrink=shrink)


def predict_many(
    player_ids: Iterable[int],
    season: str = "2025",
    lookback: int = DEFAULT_LOOKBACK,
    shrink: float = DEFAULT_SHRINK,
    sleep_sec: float = 0.6,
) -> Dict[int, Dict[str, Dict[str, Any]]]:
    """Batch over player_ids with a polite sleep between API calls."""
    out: Dict[int, Dict[str, Dict[str, Any]]] = {}
    for pid in player_ids:
        try:
            pred = predict_player(int(pid), season=season,
                                  lookback=lookback, shrink=shrink)
            if pred is not None:
                out[int(pid)] = pred
        except Exception as e:  # noqa: BLE001
            log.warning("predict %s failed: %s", pid, e)
        time.sleep(sleep_sec)
    return out


def _cli_main() -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="WNBA lean prop predictor (L5 + shrinkage).")
    ap.add_argument("--player", required=True, help="WNBA player name OR numeric player_id")
    ap.add_argument("--season", default="2025")
    ap.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK)
    ap.add_argument("--shrink", type=float, default=DEFAULT_SHRINK)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    try:
        pid = int(args.player)
        pred = predict_player(pid, season=args.season,
                              lookback=args.lookback, shrink=args.shrink)
    except ValueError:
        pred = predict_player_by_name(args.player, season=args.season,
                                       lookback=args.lookback, shrink=args.shrink)
    if pred is None:
        print("No prediction"); return 2
    print(json.dumps(pred, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
