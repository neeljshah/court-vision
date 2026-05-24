"""live_engine.py -- consolidated entry point for live in-game predictions.

Cycle 95c (loop 5) -- ENTRY-POINT consolidation, not code consolidation.

Background
----------
The cycle-88 in-game prediction system currently exists as 14 scripts
(live_game_poll, predict_in_game, foul_trouble_adjust, blowout_adjust,
save_live_predictions, live_dashboard, live_player, live_edge_eval, ...).
Cycle 94d EMPIRICALLY VALIDATED that this stack beats the cycle-47/49/80
PRE-GAME predictor at endQ3 on 7/7 stats (PTS -42%, BLK -56% MAE), but the
operational surface is fragmented -- consumers must remember which script
owns which transform.

This module gives ONE clean functional API for the validated core:

    project_from_snapshot(snap)   -> per-(player, stat) projections
    project_full_slate(date_iso)  -> {game_id: [rows]} for today's games
    edge_vs_pregame(snap)         -> projections + pregame_pred deltas
    write_ledger(rows, date_iso)  -> append to data/predictions/<d>_inplay.csv

Design rule -- WRAPPERS, NOT REWRITES
-------------------------------------
This module does NOT re-implement any projection math. It calls:

  * ``scripts.predict_in_game.project_snapshot`` (cycle 88b -- the validated core)
  * ``src.prediction.live_factors.foul_trouble_factor`` (cycle 89b canonical table)
  * ``scripts.blowout_adjust.blowout_factor`` (cycle 88f buckets)
  * ``scripts.save_live_predictions.derive_inplay_predictions`` +
    ``append_to_ledger`` (cycle 88n ledger schema)
  * ``src.data.live`` loader helpers (canonical snapshot schema)

The existing consumers (live_dashboard, live_player, live_edge_eval, ...)
keep their current imports -- this module is ADDITIVE, providing one
clean entry point for NEW consumers and for orchestrators that want a
single import to drive the whole live stack.

See ``tests/test_live_engine.py`` for the 5 regression + integration tests.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import date as _date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# scripts/ is on the load path so we can call the validated pure functions
# without copying them.
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Canonical snapshot loaders + helpers.
from src.data.live import (  # noqa: E402
    list_today_snapshots,
    latest_snapshot_path,
    load_live_state,
)

PRED_DIR = os.path.join(PROJECT_DIR, "data", "predictions")

__all__ = [
    "project_from_snapshot",
    "project_full_slate",
    "edge_vs_pregame",
    "write_ledger",
]


# ── 1. project_from_snapshot ──────────────────────────────────────────────────

def project_from_snapshot(snap: dict, *, period: Optional[int] = None) -> List[Dict]:
    """Single entry point: snapshot dict -> per-(player, stat) projections.

    Thin wrapper around ``scripts.predict_in_game.project_snapshot`` (cycle 88b)
    which composes:

      * pace-based extrapolation against the regulation 48-min baseline
      * ``src.prediction.live_factors.foul_trouble_factor`` (cycle 89b canonical)
      * ``scripts.blowout_adjust.blowout_factor`` semantics (cycle 88f)
      * bench-player handling (project at player-clock rate, not game-clock)

    Empirically validated by **cycle 94d** -- this combined system beats the
    cycle-47/49/80 pre-game predictor at endQ3 on 7/7 stats (PTS MAE -42%,
    BLK MAE -56%) on the retro_inplay_mae_v2 backtest.

    Parameters
    ----------
    snap : dict
        Canonical snapshot per ``src/data/live.py``. Legacy nested
        ``{home: {abbrev, score}}`` form is auto-normalized.
    period : int, optional
        Override the snapshot's reported period. Useful when the caller has
        a more authoritative period (e.g. end-of-period trigger). When None
        (the default), the snapshot's own ``period`` field is used.

    Returns
    -------
    list of dict
        One row per (player, stat). Keys:

            player_id, name, team, stat,
            current, projected_final,
            period, foul_factor, blow_factor,
            snapshot_period, snapshot_clock
    """
    import predict_in_game as pig    # local import: keeps module import cheap

    if period is not None:
        # Don't mutate the caller's dict -- shallow-copy.
        snap = dict(snap)
        snap["period"] = int(period)

    rows = pig.project_snapshot(snap)
    snap_period = snap.get("period")
    snap_clock = snap.get("clock")
    for r in rows:
        # Match the cycle-88n ledger schema for downstream consumers.
        r.setdefault("snapshot_period", snap_period)
        r.setdefault("snapshot_clock", snap_clock)
    return rows


# ── 2. project_full_slate ─────────────────────────────────────────────────────

def project_full_slate(date_iso: Optional[str] = None) -> Dict[str, List[Dict]]:
    """For every active game today, project all players.

    Iterates the latest snapshot per ``game_id`` discovered in
    ``data/live/`` for the requested date.

    Parameters
    ----------
    date_iso : str, optional
        Target date (YYYY-MM-DD). Defaults to today.

    Returns
    -------
    dict[str, list[dict]]
        ``{game_id: [projection_row, ...]}``. Games with no snapshot or
        an empty snapshot are silently skipped.
    """
    if date_iso is None:
        date_iso = _date.today().isoformat()

    out: Dict[str, List[Dict]] = {}
    for path in list_today_snapshots(date_iso):
        snap = load_live_state(path)
        if not snap:
            continue
        game_id = str(snap.get("game_id") or "")
        if not game_id:
            continue
        rows = project_from_snapshot(snap)
        out[game_id] = rows
    return out


# ── 3. edge_vs_pregame ────────────────────────────────────────────────────────

def edge_vs_pregame(snap: dict,
                    date_iso: Optional[str] = None) -> List[Dict]:
    """Project from snapshot, then attach pregame_pred + delta when available.

    Joins each (player_id, stat) projection against the cycle-47/49/80
    pre-game ledger ``data/predictions/<date>.csv``. When the ledger is
    absent or a player/stat is missing, the row is returned unchanged
    (no ``pregame_pred`` key, ``delta`` not set) -- callers that want a
    strict-join should filter on ``"pregame_pred" in row``.

    Parameters
    ----------
    snap : dict
        Canonical snapshot.
    date_iso : str, optional
        Target date (YYYY-MM-DD). Defaults to today.

    Returns
    -------
    list of dict
        Projection rows. When the ledger is present and a match exists,
        each row also carries ``pregame_pred`` (float) and ``delta``
        (projected_final - pregame_pred).
    """
    import predict_in_game as pig    # cycle 88b loader is the source of truth

    if date_iso is None:
        date_iso = _date.today().isoformat()

    pregame = pig.load_pregame_predictions(date_iso)
    rows = project_from_snapshot(snap)

    if not pregame:
        return rows

    for r in rows:
        pid = r.get("player_id")
        stat = r.get("stat")
        if pid is None or stat is None:
            continue
        try:
            key = (int(pid), str(stat).lower())
        except (TypeError, ValueError):
            continue
        pred = pregame.get(key)
        if pred is None:
            continue
        r["pregame_pred"] = float(pred)
        try:
            r["delta"] = float(r.get("projected_final", 0.0)) - float(pred)
        except (TypeError, ValueError):
            pass
    return rows


# ── 4. write_ledger ───────────────────────────────────────────────────────────

# Ledger schema mirrors scripts/save_live_predictions.py (cycle 88n).
_LEDGER_FIELDS = [
    "date", "game_id", "player_id", "player", "team", "opp", "venue",
    "stat", "pred", "lineup_status", "lineup_class", "play_pct",
    "injury_status", "pred_kind", "snapshot_period", "snapshot_clock",
    "current_stat",
]


def write_ledger(rows: List[Dict], date_iso: str,
                 out_path: Optional[str] = None) -> int:
    """Append projection rows to ``data/predictions/<date>_inplay.csv``.

    Accepts BOTH row shapes:

      * Rows from ``project_from_snapshot`` (cycle 88b output --
        keys: player_id/name/team/stat/projected_final/current/...).
      * Rows already in the cycle-88n ledger shape (output of
        ``scripts.save_live_predictions.derive_inplay_predictions``).

    For the former, this function coerces each row into the canonical
    cycle-88n schema before append; for the latter, the row is written
    through unchanged. The header is written iff the file doesn't yet
    exist (idempotent, matches ``save_live_predictions.append_to_ledger``).

    Parameters
    ----------
    rows : list of dict
        Projection rows in either shape above.
    date_iso : str
        Date stamp written into each row's ``date`` column. Also drives
        the default ``out_path``.
    out_path : str, optional
        Override the default ``data/predictions/<date>_inplay.csv``.

    Returns
    -------
    int
        Number of rows appended.
    """
    from scripts.save_live_predictions import append_to_ledger  # noqa: PLC0415

    if out_path is None:
        out_path = os.path.join(PRED_DIR, f"{date_iso}_inplay.csv")

    coerced: List[Dict] = []
    for r in rows:
        # If the row already speaks the cycle-88n schema (has 'pred' +
        # 'player' keys), trust it.
        if "pred" in r and "player" in r:
            row = dict(r)
            row.setdefault("date", date_iso)
            for key in _LEDGER_FIELDS:
                row.setdefault(key, "")
            coerced.append(row)
            continue

        # Otherwise it came from project_from_snapshot -- coerce.
        try:
            current = float(r.get("current", 0) or 0)
        except (TypeError, ValueError):
            current = 0.0
        try:
            pred = float(r.get("projected_final", 0) or 0)
        except (TypeError, ValueError):
            pred = 0.0

        period = r.get("snapshot_period", r.get("period", ""))
        period_str = str(period) if period not in (None, "") else ""
        kind = f"Q{period_str}_inplay" if period_str else "inplay"
        coerced.append({
            "date": date_iso,
            "game_id": r.get("game_id", ""),
            "player_id": r.get("player_id", ""),
            "player": r.get("name", ""),
            "team": r.get("team", ""),
            "opp": r.get("opp", ""),
            "venue": r.get("venue", ""),
            "stat": r.get("stat", ""),
            "pred": f"{pred:.4f}",
            "lineup_status": r.get("lineup_status", ""),
            "lineup_class": r.get("lineup_class", ""),
            "play_pct": r.get("play_pct", ""),
            "injury_status": r.get("injury_status", ""),
            "pred_kind": r.get("pred_kind", kind),
            "snapshot_period": period_str,
            "snapshot_clock": r.get("snapshot_clock", ""),
            "current_stat": f"{current:.4f}",
        })

    return append_to_ledger(coerced, out_path)
