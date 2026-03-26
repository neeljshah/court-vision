"""
clv_tracker.py -- Phase D3: Closing Line Value tracker.

After each game: pull closing line, compute CLV = our_line - closing_line.
Positive CLV means we had better info than the market.

Primary success signal: rolling 7-day avg CLV across all props.

Public API
----------
    record_clv(game_id, predictions, season)  -> dict
    get_rolling_clv(n_days, stat)             -> dict
    get_clv_summary()                         -> dict
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_CLV_LOG_PATH = os.path.join(PROJECT_DIR, "data", "nba", "clv_log.json")
_EXT_DIR      = os.path.join(PROJECT_DIR, "data", "external")


# ── Closing line fetcher ──────────────────────────────────────────────────────

def _get_closing_line(game_id: str, season: str) -> Optional[dict]:
    """
    Look up closing spread + total from historical_lines or odds cache.

    Returns:
        {"closing_spread": float, "closing_total": float} or None
    """
    path = os.path.join(_EXT_DIR, f"historical_lines_{season}.json")
    try:
        games = json.load(open(path))
        for g in games:
            if g.get("game_id") == game_id:
                spread = g.get("closing_spread")
                total  = g.get("closing_total")
                if spread is not None or total is not None:
                    return {
                        "closing_spread": float(spread) if spread is not None else None,
                        "closing_total":  float(total)  if total  is not None else None,
                        "source":         g.get("source", "unknown"),
                    }
    except Exception:
        pass
    return None


def _get_actual_result(game_id: str, season: str) -> Optional[dict]:
    """
    Look up actual game result (margin, total) from historical_lines or NBA API.

    Returns:
        {"home_score": int, "away_score": int, "margin": float, "total": float} or None
    """
    path = os.path.join(_EXT_DIR, f"historical_lines_{season}.json")
    try:
        games = json.load(open(path))
        for g in games:
            if g.get("game_id") == game_id:
                h = g.get("home_score")
                a = g.get("away_score")
                if h is not None and a is not None:
                    return {
                        "home_score": int(h),
                        "away_score": int(a),
                        "margin":     float(h) - float(a),
                        "total":      float(h) + float(a),
                    }
    except Exception:
        pass

    # Fallback: NBA API
    try:
        from nba_api.stats.endpoints import boxscoresummaryv2
        time.sleep(0.8)
        resp = boxscoresummaryv2.BoxScoreSummaryV2(game_id=game_id)
        df = resp.get_data_frames()[5]  # line_score
        teams = df.to_dict("records")
        if len(teams) >= 2:
            home  = next((t for t in teams if t.get("TEAM_ABBREVIATION")), teams[0])
            away  = next((t for t in teams if t != home), teams[1])
            h_pts = float(home.get("PTS", 0) or 0)
            a_pts = float(away.get("PTS", 0) or 0)
            return {"margin": h_pts - a_pts, "total": h_pts + a_pts,
                    "home_score": h_pts, "away_score": a_pts}
    except Exception:
        pass
    return None


# ── Core CLV recorder ─────────────────────────────────────────────────────────

def record_clv(
    game_id:     str,
    game_date:   str,
    our_spread:  Optional[float],
    our_total:   Optional[float],
    season:      str = "2024-25",
) -> dict:
    """
    Record CLV for a single game's spread + total predictions.

    Args:
        game_id:    NBA game ID
        game_date:  ISO date string (YYYY-MM-DD)
        our_spread: Our predicted home spread (positive = home favored)
        our_total:  Our predicted game total
        season:     Season string

    Returns:
        {
            "game_id":       str,
            "clv_spread":    float | None,
            "clv_total":     float | None,
            "closing_line":  dict | None,
            "actual_result": dict | None,
            "won_spread":    bool | None,
            "won_total":     bool | None,
        }
    """
    closing = _get_closing_line(game_id, season)
    actual  = _get_actual_result(game_id, season)

    clv_spread = None
    clv_total  = None
    won_spread = None
    won_total  = None

    if closing and our_spread is not None:
        c_spread = closing.get("closing_spread")
        if c_spread is not None:
            clv_spread = round(our_spread - c_spread, 3)

    if closing and our_total is not None:
        c_total = closing.get("closing_total")
        if c_total is not None:
            clv_total = round(our_total - c_total, 3)

    if actual:
        margin = actual.get("margin")
        total  = actual.get("total")
        if our_spread is not None and margin is not None:
            won_spread = (our_spread >= 0) == (margin >= 0)
        if our_total is not None and total is not None:
            # Over/under: we win if we were on right side of closing line
            c_total = (closing or {}).get("closing_total", our_total)
            won_total = (total > c_total) == (our_total > c_total)

    record = {
        "game_id":       game_id,
        "game_date":     game_date,
        "our_spread":    our_spread,
        "our_total":     our_total,
        "clv_spread":    clv_spread,
        "clv_total":     clv_total,
        "closing_line":  closing,
        "actual_result": actual,
        "won_spread":    won_spread,
        "won_total":     won_total,
        "recorded_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # Persist to local JSON log
    _append_clv_log(record)

    # Write to PostgreSQL if available
    _store_clv_to_db(record, season)

    return record


def _append_clv_log(record: dict) -> None:
    """Append record to local CLV log file."""
    log = []
    if os.path.exists(_CLV_LOG_PATH):
        try:
            log = json.load(open(_CLV_LOG_PATH))
        except Exception:
            pass
    log.append(record)
    os.makedirs(os.path.dirname(_CLV_LOG_PATH), exist_ok=True)
    with open(_CLV_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def _store_clv_to_db(record: dict, season: str) -> None:
    """Store CLV record to PostgreSQL clv_log table."""
    try:
        from src.data.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                actual = record.get("actual_result") or {}
                closing = record.get("closing_line") or {}
                cur.execute(
                    """
                    INSERT INTO clv_log
                        (game_id, game_date, bet_type, our_line, closing_line,
                         clv, actual_result, won, recorded_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        record["game_id"],
                        record["game_date"],
                        "spread",
                        record.get("our_spread"),
                        closing.get("closing_spread"),
                        record.get("clv_spread"),
                        actual.get("margin"),
                        record.get("won_spread"),
                    ),
                )
                conn.commit()
    except Exception:
        pass


# ── Rolling CLV summary ────────────────────────────────────────────────────────

def get_rolling_clv(n_days: int = 7, bet_type: str = "spread") -> dict:
    """
    Compute rolling CLV over the last N days from the local log.

    Returns:
        {
            "n_days":       int,
            "n_games":      int,
            "mean_clv":     float,
            "pct_positive": float,
            "win_rate":     float | None,
        }
    """
    if not os.path.exists(_CLV_LOG_PATH):
        return {"n_days": n_days, "n_games": 0, "mean_clv": 0.0, "pct_positive": 0.0}

    try:
        log = json.load(open(_CLV_LOG_PATH))
    except Exception:
        return {"n_days": n_days, "n_games": 0, "mean_clv": 0.0, "pct_positive": 0.0}

    cutoff = (datetime.utcnow() - timedelta(days=n_days)).strftime("%Y-%m-%d")

    clv_key = f"clv_{bet_type}"
    won_key = f"won_{bet_type}"

    recent = [
        r for r in log
        if r.get("game_date", "") >= cutoff and r.get(clv_key) is not None
    ]

    if not recent:
        return {"n_days": n_days, "n_games": 0, "mean_clv": 0.0, "pct_positive": 0.0}

    clvs    = [r[clv_key] for r in recent]
    mean_clv = round(sum(clvs) / len(clvs), 4)
    pct_pos  = round(sum(1 for c in clvs if c > 0) / len(clvs) * 100, 1)

    won_vals = [r[won_key] for r in recent if r.get(won_key) is not None]
    win_rate = round(sum(won_vals) / len(won_vals) * 100, 1) if won_vals else None

    return {
        "n_days":       n_days,
        "n_games":      len(recent),
        "mean_clv":     mean_clv,
        "pct_positive": pct_pos,
        "win_rate":     win_rate,
    }


def get_clv_summary() -> dict:
    """Full CLV dashboard: 7d, 30d, all-time for spread and total."""
    return {
        "spread_7d":  get_rolling_clv(7,   "spread"),
        "spread_30d": get_rolling_clv(30,  "spread"),
        "total_7d":   get_rolling_clv(7,   "total"),
        "total_30d":  get_rolling_clv(30,  "total"),
    }


if __name__ == "__main__":
    summary = get_clv_summary()
    print("\nCLV Summary:")
    for key, val in summary.items():
        print(f"  {key}: mean_clv={val['mean_clv']:+.3f}  "
              f"win_rate={val.get('win_rate', 'N/A')}%  "
              f"n={val['n_games']}")
