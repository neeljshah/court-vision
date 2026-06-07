"""src/prediction/pregame_layer_log.py — log base vs calibrated vs live-adjusted
pregame projections so the live-only layers can finally be graded against actuals.

Why this exists
---------------
docs/VS_VEGAS_ASSESSMENT.md §4 explains that the same-day live-adjustment
layer (inactives bump + pace + blowout) is **~neutral on historical
reconstruction** because the production OOF already saw DNP/context features.
The layer's edge — if any — exists only on the LIVE feed (confirmed inactives
+ tonight's mainline) that the model's serve-time features don't carry. That
edge can't be proven from history; it needs a LIVE shadow A/B.

This logger gives us that A/B. On every serve-time prediction (one row per
(player, stat, line) emitted by ``scripts/compare_to_lines.py``) it appends
ONE row carrying:

  date | player_id | stat | line | side
  base       — model projection BEFORE any adjustment layer
  after_cal  — projection AFTER pregame_calibration.apply() (if enabled; else None)
  after_live — projection AFTER live_adjustment.adjust_projection() (if enabled; else None)
  vac_share, game_total, game_spread     — the live-feed inputs that drove the
                                            live-adjustment, so we can later
                                            slice by "did the inactives feed
                                            actually fire" etc.

Per-day actuals are joined OFFLINE by scripts/grade_pregame_layers.py from
``data/nba/gamelogs_<season>.json`` (the canonical box-score store the rest of
the pipeline already maintains). That decouples the prediction-time logger
(must be fast, no network) from the grader (slow, runs after final scores).

Strict no-op unless CV_LAYER_LOG=1 (or ``log(..., force=True)``). Failures
NEVER raise — a logger that breaks production is worse than no logger.

Distinct from src/prediction/shadow_logger.py (in-play bet-evaluation CSVs
keyed by game_id) — this one is the pregame projection-layer record, keyed by
(date, player, stat), and goes to a single rolling JSONL.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_LOG = _ROOT / "data" / "cache" / "pregame_layer_log.jsonl"
_LOCK = threading.Lock()


def _log_path() -> Path:
    """Resolve the log file path, allowing env override for tests."""
    override = os.environ.get("CV_LAYER_LOG_PATH")
    return Path(override) if override else _DEFAULT_LOG


def is_enabled() -> bool:
    """Master opt-in. Mirrors CV_PREGAME_CAL / CV_LIVE_ADJUST."""
    return os.environ.get("CV_LAYER_LOG", "0") == "1"


def log(
    *,
    date: str,
    player_id: int,
    stat: str,
    line: float,
    base: float,
    after_cal: Optional[float] = None,
    after_live: Optional[float] = None,
    side: Optional[str] = None,
    over_odds: Optional[float] = None,
    under_odds: Optional[float] = None,
    vac_share: Optional[float] = None,
    game_total: Optional[float] = None,
    game_spread: Optional[float] = None,
    opp: Optional[str] = None,
    book: Optional[str] = None,
    force: bool = False,
) -> bool:
    """Append one prediction-layer row. Returns True on success.

    Strict no-op when the flag is off (unless ``force=True``). Catches every
    exception — this MUST NOT crash compare_to_lines.
    """
    if not (force or is_enabled()):
        return False
    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date": date, "player_id": int(player_id), "stat": stat.lower(),
        "line": float(line),
        "base": round(float(base), 3),
        "after_cal": (None if after_cal is None else round(float(after_cal), 3)),
        "after_live": (None if after_live is None else round(float(after_live), 3)),
        "side": side,
        "over_odds": (None if over_odds is None else float(over_odds)),
        "under_odds": (None if under_odds is None else float(under_odds)),
        "vac_share": (None if vac_share is None else round(float(vac_share), 4)),
        "game_total": (None if game_total is None else float(game_total)),
        "game_spread": (None if game_spread is None else float(game_spread)),
        "opp": opp, "book": book,
    }
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return True
    except Exception:
        return False
