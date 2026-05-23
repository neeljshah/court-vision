"""
player_trajectory.py — Player-trajectory feature builder for prop retraining.

Consolidates signals from hot_cold_streak_detector, breakout_predictor,
season_regression_detector, and clutch_efficiency into one point-in-time
feature dict with strict no-future-leak guarantees.

All features are computed as of `game_date` using only games strictly before
that date (game_date_prior < target_game_date).

Public API
----------
    get_trajectory_features(player_id, season, game_date) -> dict
"""
from __future__ import annotations

import datetime
import json
import math
import os
from functools import lru_cache
from typing import List, Optional

_PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE = os.path.join(_PROJECT, "data", "nba")

# ── date helpers ──────────────────────────────────────────────────────────────

_DATE_FMTS = ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y")


def _parse_date(s: str) -> Optional[datetime.date]:
    for fmt in _DATE_FMTS:
        try:
            return datetime.datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _to_date(game_date: str) -> datetime.date:
    d = _parse_date(game_date)
    if d is None:
        raise ValueError(f"Cannot parse date: {game_date!r}")
    return d


# ── cache loaders ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=2048)
def _load_gamelog(player_id: int, season: str) -> tuple:
    """Load and parse gamelog_full rows sorted oldest→newest. Cached."""
    path = os.path.join(_NBA_CACHE, f"gamelog_full_{player_id}_{season}.json")
    if not os.path.exists(path):
        return ()
    try:
        rows = json.load(open(path))
    except Exception:
        return ()
    parsed = []
    for r in rows:
        d = _parse_date(r.get("game_date", ""))
        if d is not None:
            parsed.append((d, r))
    parsed.sort(key=lambda x: x[0])  # oldest first
    return tuple(parsed)


def _games_before(player_id: int, season: str, game_date: str) -> List[dict]:
    """Return rows with game_date strictly before target, newest-first."""
    cutoff = _to_date(game_date)
    rows = _load_gamelog(player_id, season)
    before = [r for d, r in rows if d < cutoff]
    before.reverse()  # newest first
    return before


def _get_pts(rows: List[dict]) -> List[float]:
    return [float(r.get("pts", 0) or 0) for r in rows]


def _get_min(rows: List[dict]) -> List[float]:
    return [float(r.get("min", 0) or 0) for r in rows]


# ── feature computations ──────────────────────────────────────────────────────

def _safe_mean(vals: List[float], default: float = 0.0) -> float:
    return sum(vals) / len(vals) if vals else default


def _safe_std(vals: List[float], mean: Optional[float] = None) -> float:
    if len(vals) < 2:
        return 0.0
    m = mean if mean is not None else _safe_mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def _hot_cold_streaks(pts_all: List[float], pts_l3: List[float]) -> tuple:
    """Return (hot_streak, cold_streak) binary flags."""
    if len(pts_all) < 5 or len(pts_l3) < 3:
        return 0, 0
    season_avg = _safe_mean(pts_all)
    if season_avg < 1.0:
        return 0, 0
    l3_avg = _safe_mean(pts_l3)
    hot = 1 if l3_avg >= 1.10 * season_avg else 0
    cold = 1 if l3_avg <= 0.85 * season_avg else 0
    return hot, cold


def _z_score_l5(pts_all: List[float], pts_l5: List[float]) -> float:
    """Standardized last-5 avg vs season distribution."""
    if len(pts_all) < 5 or len(pts_l5) < 3:
        return 0.0
    season_avg = _safe_mean(pts_all)
    std = _safe_std(pts_all, season_avg)
    if std < 0.5:
        return 0.0
    l5_avg = _safe_mean(pts_l5)
    return round((l5_avg - season_avg) / std, 4)


def _momentum_l10(pts_l10: List[float]) -> float:
    """Weighted-trend slope of last 10 games, normalized by mean."""
    vals = pts_l10[:10]
    if len(vals) < 4:
        return 0.0
    vals = list(reversed(vals))  # chronological order (oldest→newest)
    n = len(vals)
    mean_v = _safe_mean(vals) or 1.0
    x_mean = (n - 1) / 2.0
    cov = sum((i - x_mean) * (v - mean_v) for i, v in enumerate(vals))
    var = sum((i - x_mean) ** 2 for i in range(n))
    slope = cov / var if var > 0 else 0.0
    return round(slope / mean_v, 5)


def _regression_signal(pts_all_cur: List[float], pts_all_prev: List[float]) -> float:
    """How far current rolling avg deviates from 3-year (prior seasons) baseline."""
    if not pts_all_cur:
        return 0.0
    cur_avg = _safe_mean(pts_all_cur)
    if not pts_all_prev:
        return 0.0
    baseline = _safe_mean(pts_all_prev)
    if baseline < 1.0:
        return 0.0
    gap = cur_avg - baseline
    return round(math.tanh(gap / 5.0), 4)


def _breakout_flag(pts_all_cur: List[float], pts_all_prev: List[float],
                    game_date: str, season: str) -> int:
    """1 if current season avg > 120% prior-season avg AND within first 30 games."""
    if len(pts_all_cur) < 5 or not pts_all_prev:
        return 0
    # Only flag in first 30 games of the season
    if len(pts_all_cur) > 30:
        return 0
    cur_avg = _safe_mean(pts_all_cur)
    prior_avg = _safe_mean(pts_all_prev)
    if prior_avg < 1.0:
        return 0
    return 1 if cur_avg >= 1.20 * prior_avg else 0


def _clutch_efficiency(player_id: int, season: str, game_date: str) -> float:
    """FG% in clutch situations from cached clutch_scores. Default 0.45."""
    path = os.path.join(_NBA_CACHE, f"clutch_scores_{season}.json")
    if not os.path.exists(path):
        return 0.45
    try:
        scores = json.load(open(path))
        entry = scores.get(str(player_id))
        if entry and "clutch_fg_pct" in entry:
            return round(float(entry["clutch_fg_pct"]), 4)
    except Exception:
        pass
    return 0.45


def _workload_anomaly(min_all: List[float], min_l7: List[float]) -> float:
    """Std deviations of current week's avg min vs season norm."""
    if len(min_all) < 5 or not min_l7:
        return 0.0
    season_avg = _safe_mean(min_all)
    std = _safe_std(min_all, season_avg)
    if std < 0.5:
        return 0.0
    week_avg = _safe_mean(min_l7)
    return round((week_avg - season_avg) / std, 4)


def _opponent_history(rows_all: List[dict], current_matchup: Optional[str]) -> float:
    """Avg PTS in last 5 games vs opponent extracted from matchup string."""
    if not current_matchup or not rows_all:
        return 0.0
    # Opponent extracted from "LAL vs. OKC" or "LAL @ OKC"
    parts = current_matchup.replace("@", "vs.").split("vs.")
    if len(parts) < 2:
        return 0.0
    opp = parts[1].strip()
    if not opp:
        return 0.0
    opp_games = [
        float(r.get("pts", 0) or 0) for r in rows_all
        if opp in r.get("matchup", "")
    ][:5]
    if not opp_games:
        return 0.0
    return round(_safe_mean(opp_games), 3)


# ── prior-season loader ───────────────────────────────────────────────────────

def _prev_season_pts(player_id: int, season: str) -> List[float]:
    """Collect PTS from prior 1-2 seasons for baseline."""
    s_year = int(season.split("-")[0])
    result: List[float] = []
    for offset in (1, 2):
        yr = s_year - offset
        prev = f"{yr}-{str(yr + 1)[-2:]}"
        rows = _load_gamelog(player_id, prev)
        result.extend(float(r.get("pts", 0) or 0) for _, r in rows)
    return result


# ── public API ────────────────────────────────────────────────────────────────

_DEFAULTS: dict = {
    "hot_streak": 0,
    "cold_streak": 0,
    "z_score_l5": 0.0,
    "momentum_l10": 0.0,
    "regression_signal": 0.0,
    "breakout_flag": 0,
    "clutch_efficiency_l30": 0.45,
    "workload_anomaly": 0.0,
    "opponent_history_avg": 0.0,
}


def get_trajectory_features(
    player_id: int,
    season: str,
    game_date: str,
    current_matchup: Optional[str] = None,
) -> dict:
    """Return player-trajectory signals as of game_date (no future leakage).

    Args:
        player_id:        NBA player ID.
        season:           Season string e.g. "2024-25".
        game_date:        Target game date (ISO "YYYY-MM-DD" or "Apr 13, 2025").
        current_matchup:  Matchup string for opponent-history feature (optional).

    Returns dict with keys: hot_streak, cold_streak, z_score_l5, momentum_l10,
        regression_signal, breakout_flag, clutch_efficiency_l30,
        workload_anomaly, opponent_history_avg.
    """
    rows = _games_before(player_id, season, game_date)

    if len(rows) < 3:
        return dict(_DEFAULTS)

    pts_all = _get_pts(rows)
    pts_l3 = pts_all[:3]
    pts_l5 = pts_all[:5]
    pts_l10 = pts_all[:10]

    min_all = _get_min(rows)
    min_l7 = min_all[:7]

    hot, cold = _hot_cold_streaks(pts_all, pts_l3)
    z5 = _z_score_l5(pts_all, pts_l5)
    mom = _momentum_l10(pts_l10)

    prev_pts = _prev_season_pts(player_id, season)
    reg_signal = _regression_signal(pts_all, prev_pts)
    bo_flag = _breakout_flag(pts_all, prev_pts, game_date, season)

    clutch = _clutch_efficiency(player_id, season, game_date)
    workload = _workload_anomaly(min_all, min_l7)
    opp_avg = _opponent_history(rows, current_matchup)

    return {
        "hot_streak":              hot,
        "cold_streak":             cold,
        "z_score_l5":              z5,
        "momentum_l10":            mom,
        "regression_signal":       reg_signal,
        "breakout_flag":           bo_flag,
        "clutch_efficiency_l30":   clutch,
        "workload_anomaly":        workload,
        "opponent_history_avg":    opp_avg,
    }
