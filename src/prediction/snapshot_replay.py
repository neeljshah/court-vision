"""snapshot_replay.py — stream historical games through the live projector.

Thin wrapper around the canonical snapshot reconstruction in
``scripts/retro_inplay_mae.py`` that drives ``src.prediction.live_engine.
project_from_snapshot`` at endQ1/endQ2/endQ3 boundaries.

Public API
----------
list_historical_game_ids(min_date, max_date, limit) -> list[str]
replay_game(game_id, *, interval_seconds, snapshot_points) -> list[dict]
replay_game_to_shadow_log(game_id, *, base_dir) -> int

Used by Agent 4 (Backtest Harness) to build the shadow-log corpus that
Agent 2's settle_day consumes.
"""
from __future__ import annotations

import logging
import math
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ── path setup (mirrors retro_inplay_mae.py) ─────────────────────────────────
PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as _rim  # noqa: E402 — canonical snapshot reconstruction

log = logging.getLogger("snapshot_replay")

# Module-level alias so tests can patch ``src.prediction.snapshot_replay.
# project_from_snapshot`` without needing to reach into live_engine.
# Lazy-import inside a try/except so the module is importable even when the
# live_engine dependency chain is absent (e.g. in lightweight CI).
try:
    from src.prediction.live_engine import project_from_snapshot  # noqa: F401
except Exception:  # pragma: no cover — only absent in very stripped envs
    project_from_snapshot = None  # type: ignore[assignment]

# Default snapshot boundary points (endQ1 / endQ2 / endQ3).
_DEFAULT_POINTS: Tuple[str, ...] = ("endQ1", "endQ2", "endQ3")

# Per-stat sigma (from decision_engine — kept local to avoid the event-bus
# import chain that decision_engine carries at module level).
_STAT_SIGMA: Dict[str, float] = {
    "pts": 5.0, "reb": 2.2, "ast": 1.6,
    "fg3m": 1.1, "stl": 0.9, "blk": 0.6, "tov": 1.1,
}

# Conditional shadow_logger import (Agent 1 lands first; graceful no-op when absent).
try:
    from src.prediction import shadow_logger as _sl
    _HAS_SHADOW = True
except ImportError:
    _sl = None  # type: ignore[assignment]
    _HAS_SHADOW = False


# ── helpers ───────────────────────────────────────────────────────────────────

def _period_clock_remaining(point: str) -> Tuple[int, float]:
    """Return (period, clock_remaining_seconds) for a snapshot point."""
    _MAP = {
        "endQ1": (2, 720.0),   # start of Q2 → 12:00 remaining in Q2
        "endQ2": (3, 720.0),
        "endQ3": (4, 720.0),
    }
    return _MAP.get(point, (1, 720.0))


# ── public API ────────────────────────────────────────────────────────────────

def list_historical_game_ids(
    min_date: Optional[str] = None,
    max_date: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[str]:
    """Discover game_ids with sufficient data for replay.

    Pulls from ``data/player_quarter_stats.parquet`` (via
    ``retro_inplay_mae.load_quarter_stats``).  When ``min_date`` / ``max_date``
    are supplied (ISO format, e.g. ``'2025-01-01'``), the list is filtered by
    the game date resolved via ``retro_inplay_mae.find_game_date``.

    Sorted chronologically (by resolved date when available, by game_id string
    otherwise).  Returns at most ``limit`` ids.
    """
    try:
        qstats = _rim.load_quarter_stats()
    except Exception as exc:
        log.warning("load_quarter_stats failed: %s", exc)
        return []

    raw_ids: List[str] = sorted(qstats["game_id"].unique().tolist())

    if min_date is None and max_date is None:
        ids = raw_ids
    else:
        # Date-filter path: resolve each game's date (slow first call).
        dated: List[Tuple[str, str]] = []
        for gid in raw_ids:
            d = _rim.find_game_date(gid, qstats) or ""
            if min_date and d and d < min_date:
                continue
            if max_date and d and d > max_date:
                continue
            dated.append((d, gid))
        dated.sort()
        ids = [gid for _, gid in dated]

    if limit is not None:
        ids = ids[:limit]
    return ids


def replay_game(
    game_id: str,
    *,
    interval_seconds: int = 30,
    snapshot_points: Tuple[str, ...] = _DEFAULT_POINTS,
) -> List[Dict]:
    """Replay one historical game through ``live_engine.project_from_snapshot``.

    For each snapshot point in ``snapshot_points``:
      - Reconstruct the snapshot via ``retro_inplay_mae.build_snapshot``.
      - Run it through ``src.prediction.live_engine.project_from_snapshot``.
      - Collect all projection rows.

    The ``interval_seconds`` parameter is accepted for future mid-quarter
    expansion but currently only the 3 quarter-boundary points are generated
    (sub-720s intervals are not yet supported — noted for Agent 4).

    Returns one entry per snapshot_point that produced a valid snapshot.
    None snapshots (missing quarter data) are silently skipped.
    """
    # Use the module-level alias (patchable by tests); fall back to lazy import
    # only when the module-level import failed at startup.
    _pfs = project_from_snapshot
    if _pfs is None:
        from src.prediction.live_engine import project_from_snapshot as _pfs  # type: ignore[assignment]

    try:
        qstats = _rim.load_quarter_stats()
    except Exception as exc:
        log.warning("replay_game(%s): load_quarter_stats failed: %s", game_id, exc)
        return []

    results: List[Dict] = []
    for point in snapshot_points:
        snap = _rim.build_snapshot(game_id, point, qstats)
        if snap is None:
            log.debug("replay_game(%s, %s): build_snapshot returned None — skipping",
                      game_id, point)
            continue

        try:
            projection_rows = _pfs(snap)
        except Exception as exc:
            log.warning("replay_game(%s, %s): project_from_snapshot failed: %s",
                        game_id, point, exc)
            continue

        period, clock_rem = _period_clock_remaining(point)
        results.append({
            "game_id": game_id,
            "snapshot_point": point,
            "period": period,
            "clock_remaining": clock_rem,
            "projection_rows": projection_rows,
            "snapshot": snap,
        })

    return results


def replay_game_to_shadow_log(
    game_id: str,
    *,
    base_dir: Optional[str] = None,
) -> int:
    """End-to-end: replay the game AND log every evaluated (line, side) through
    the shadow logger.

    Steps per projection row:
      1. Look up an L5-proxy line for (player_id, stat) via
         ``retro_inplay_mae.pregame_predictions_via_gamelog``.
      2. Build a synthetic ``line`` dict compatible with the gate chain.
      3. Run ``decision_engine._passes_gates`` (read-only import).
      4. Compute hit_probability / ev / kelly via ``decision_engine`` helpers.
      5. Append to shadow_logger with gate_status = "passed" | "blocked".

    When the shadow_logger is unavailable (Agent 1 not merged yet), rows are
    counted but not written — the function still returns the row count.

    Returns the number of (line, side) evaluations logged (including blocked).
    """
    from src.prediction.decision_engine import (  # read-only imports
        _passes_gates,
        hit_probability,
        ev_per_dollar,
        kelly_fraction,
        classify_tier,
    )

    # Replay the game to get projection rows per snapshot.
    entries = replay_game(game_id)
    if not entries:
        log.info("replay_game_to_shadow_log(%s): no entries produced", game_id)
        return 0

    # Build L5 pregame proxy lines (single parquet load).
    try:
        qstats = _rim.load_quarter_stats()
        game_dates: Dict[str, str] = {}
        d = _rim.find_game_date(game_id, qstats)
        if d:
            game_dates[game_id] = d
        l5_preds: Dict[Tuple[str, int, str], float] = (
            _rim.pregame_predictions_via_gamelog(game_dates, qstats)
        )
    except Exception as exc:
        log.warning("replay_game_to_shadow_log(%s): L5 proxy failed: %s",
                    game_id, exc)
        l5_preds = {}

    ts_now = datetime.utcnow().isoformat()
    total_logged = 0
    batch: List[Dict] = []

    for entry in entries:
        point = entry["snapshot_point"]
        period = entry["period"]
        clock_rem = entry["clock_remaining"]
        snap = entry["snapshot"]

        for row in entry["projection_rows"]:
            pid = row.get("player_id")
            stat = (row.get("stat") or "").lower()
            proj = row.get("projected_final")
            current = row.get("current") or row.get("current_stat") or 0.0

            if pid is None or not stat or proj is None:
                continue

            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                continue

            # Look up L5 proxy line (pregame estimate as stand-in for sportsbook).
            l5_val = l5_preds.get((game_id, pid_int, stat))
            if l5_val is None:
                # No proxy line → can't evaluate; still count as blocked.
                batch.append(_make_shadow_record(
                    ts=ts_now, game_id=game_id, period=period,
                    clock_remaining=clock_rem, row=row, side="over",
                    line_val=None, book="l5_proxy", odds=-110,
                    sigma=_STAT_SIGMA.get(stat, 1.0),
                    ev=0.0, kelly=0.0, tier="C",
                    gate_status="blocked", gate_blocked_by="line_present",
                    source="snapshot_replay",
                ))
                total_logged += 1
                continue

            sigma = _STAT_SIGMA.get(stat, 1.0)

            for side in ("over", "under"):
                # Build synthetic line dict compatible with _passes_gates.
                odds = -110  # standard juice
                line_dict: Dict = {
                    "line": l5_val,
                    "book": "l5_proxy",
                    "over_price": odds if side == "over" else None,
                    "under_price": odds if side == "under" else None,
                    "market_status": "open",
                }

                passed, blocked_by = _passes_gates(row, line_dict)

                if passed:
                    try:
                        p_hit = hit_probability(float(proj), float(l5_val),
                                                side, sigma)
                        ev = ev_per_dollar(p_hit, odds)
                        kf = kelly_fraction(p_hit, odds)
                        delta = abs(float(proj) - float(l5_val))
                        tier = classify_tier(ev, delta)
                    except Exception:
                        p_hit = ev = kf = 0.0
                        tier = "C"
                    gate_status = "passed"
                    gate_blocked_by = ""
                else:
                    p_hit = ev = kf = 0.0
                    tier = "C"
                    gate_status = "blocked"
                    gate_blocked_by = blocked_by

                batch.append(_make_shadow_record(
                    ts=ts_now, game_id=game_id, period=period,
                    clock_remaining=clock_rem, row=row, side=side,
                    line_val=l5_val, book="l5_proxy", odds=odds,
                    sigma=sigma, ev=ev, kelly=kf, tier=tier,
                    gate_status=gate_status,
                    gate_blocked_by=gate_blocked_by,
                    source="snapshot_replay",
                ))
                total_logged += 1

    # Write in one batch for I/O efficiency.
    if batch and _HAS_SHADOW and _sl is not None:
        try:
            _sl.log_batch(batch, base_dir=base_dir)
        except Exception as exc:
            log.warning("replay_game_to_shadow_log(%s): log_batch failed: %s",
                        game_id, exc)
    elif batch and not _HAS_SHADOW:
        log.debug("shadow_logger absent — %d rows counted but not written", len(batch))

    return total_logged


# ── internal helpers ──────────────────────────────────────────────────────────

def _make_shadow_record(
    *,
    ts: str,
    game_id: str,
    period: int,
    clock_remaining: float,
    row: Dict,
    side: str,
    line_val: Optional[float],
    book: str,
    odds: int,
    sigma: float,
    ev: float,
    kelly: float,
    tier: str,
    gate_status: str,
    gate_blocked_by: str,
    source: str,
) -> Dict:
    """Build a dict compatible with shadow_logger._COLUMNS."""
    return {
        "ts": ts,
        "game_id": game_id,
        "period": period,
        "clock_remaining": clock_remaining,
        "player_id": row.get("player_id"),
        "name": row.get("name", f"pid_{row.get('player_id')}"),
        "team": row.get("team", ""),
        "stat": row.get("stat", ""),
        "side": side,
        "line": line_val,
        "book": book,
        "odds": odds,
        "model_proj": row.get("projected_final"),
        "current_stat": row.get("current") or row.get("current_stat") or 0.0,
        "sigma": sigma,
        "raw_ev": ev,
        "kelly": kelly,
        "tier": tier,
        "gate_status": gate_status,
        "gate_blocked_by": gate_blocked_by,
        "source": source,
    }
