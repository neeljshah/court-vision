"""shadow_logger.py — append-only log of every bet the engine evaluated.

Every (player, stat, side, line, book) tuple that passes through
rank_for_game is written here — including the ones the gate chain or
EV filters silently dropped — so downstream agents can settle outcomes
and calibrate filter thresholds against real ROI data.

CSV columns (21 fields):
    ts, game_id, period, clock_remaining, player_id, name, team, stat, side,
    line, book, odds, model_proj, current_stat, sigma, raw_ev, kelly,
    tier, gate_status, gate_blocked_by, source

Files land at:
    data/shadow/<game_id>_<YYYY-MM-DD>.csv   (one file per game per day)

The directory is created on first write.  File handles are NOT kept open
between calls (low-frequency writes; avoids handle leaks across event ticks).
"""
from __future__ import annotations

import csv
import os
from typing import Any, Optional

# Column order is part of the contract — do not reorder.
_COLUMNS = [
    "ts", "game_id", "period", "clock_remaining",
    "player_id", "name", "team", "stat", "side",
    "line", "book", "odds", "model_proj", "current_stat",
    "sigma", "raw_ev", "kelly", "tier",
    "gate_status", "gate_blocked_by", "source",
]

_PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_DEFAULT_BASE_DIR = os.path.join(_PROJECT_DIR, "data", "shadow")


def _resolve_base(base_dir: Optional[str]) -> str:
    return base_dir if base_dir is not None else _DEFAULT_BASE_DIR


def _csv_path(game_id: str, base_dir: str, date_str: str) -> str:
    safe = game_id.replace("/", "_").replace("\\", "_")
    return os.path.join(base_dir, f"{safe}_{date_str}.csv")


def _to_str(val: Any) -> str:
    """Convert any value to CSV-safe string; None → empty string."""
    if val is None:
        return ""
    return str(val)


def _write_rows(path: str, rows: list[dict]) -> None:
    """Append *rows* to *path*, writing the header if the file is new."""
    is_new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        for row in rows:
            # Fill missing keys with empty string so DictWriter never KeyErrors.
            complete = {col: _to_str(row.get(col)) for col in _COLUMNS}
            writer.writerow(complete)


def log_evaluation(
    *,
    ts: Any,
    game_id: str,
    period: Any = None,
    clock_remaining: Any = None,
    player_id: Any = None,
    name: Any = None,
    team: Any = None,
    stat: Any = None,
    side: Any = None,
    line: Any = None,
    book: Any = None,
    odds: Any = None,
    model_proj: Any = None,
    current_stat: Any = None,
    sigma: Any = None,
    raw_ev: Any = None,
    kelly: Any = None,
    tier: Any = None,
    gate_status: Any = None,
    gate_blocked_by: Any = None,
    source: Any = None,
    base_dir: Optional[str] = None,
) -> None:
    """Write a single evaluation record to the per-game shadow CSV.

    Parameters map 1-to-1 to the 21 CSV columns.  All are keyword-only.
    None values are written as empty strings.

    Args:
        ts: ISO timestamp (or epoch float) of the evaluation.
        game_id: NBA game identifier (e.g. "0022301234").
        gate_status: "passed" or "blocked".
        gate_blocked_by: Name of the failing gate, or "" when passed.
        source: One of "in_play_decision", "pregame_ev", "lines_refresh".
        base_dir: Override the default ``data/shadow/`` directory (tests).
    """
    from src.live.time_utils import slate_date  # lazy — avoids import-cycle risk

    base = _resolve_base(base_dir)
    os.makedirs(base, exist_ok=True)
    date_str = slate_date().isoformat()
    path = _csv_path(game_id, base, date_str)

    record = {
        "ts": ts,
        "game_id": game_id,
        "period": period,
        "clock_remaining": clock_remaining,
        "player_id": player_id,
        "name": name,
        "team": team,
        "stat": stat,
        "side": side,
        "line": line,
        "book": book,
        "odds": odds,
        "model_proj": model_proj,
        "current_stat": current_stat,
        "sigma": sigma,
        "raw_ev": raw_ev,
        "kelly": kelly,
        "tier": tier,
        "gate_status": gate_status,
        "gate_blocked_by": gate_blocked_by,
        "source": source,
    }
    _write_rows(path, [record])


def log_batch(records: list[dict], base_dir: Optional[str] = None) -> int:
    """Append a list of evaluation records, grouped by game_id for I/O efficiency.

    Args:
        records: List of dicts with the same keys as :func:`log_evaluation`.
        base_dir: Override the default ``data/shadow/`` directory (tests).

    Returns:
        Number of rows written.
    """
    from src.live.time_utils import slate_date  # lazy

    if not records:
        return 0

    base = _resolve_base(base_dir)
    os.makedirs(base, exist_ok=True)
    date_str = slate_date().isoformat()

    # Group by game_id so we open each file at most once.
    by_game: dict[str, list[dict]] = {}
    for rec in records:
        gid = rec.get("game_id") or "unknown"
        by_game.setdefault(gid, []).append(rec)

    total = 0
    for gid, group in by_game.items():
        path = _csv_path(gid, base, date_str)
        _write_rows(path, group)
        total += len(group)
    return total
