"""live_matchup_seeder.py — pre-tip / live defender assignment seeder.

Bridges the gap between the live-snapshot poller (which only carries box
score numbers, not defender assignments) and
``src/prediction/defender_matchup_residual.py`` (which NO-OPs unless the
snapshot carries ``snap["matchups"] = {off_pid: def_pid}``).

Two signals fill the gap, in order of trust:

  1. **Series prior** — for each offensive player on tonight's slate,
     pick the defender with the MOST partial-possessions in the series
     to date (``data/cache/intel_<date>/wcf_defensive_matchups.csv``).
     Available pre-tip. The Wemby example: Hartenstein led him with
     90.0 partial-poss across G1-G4, so Wemby's seed defender is
     Hartenstein's player_id (1628392).

  2. **Live override** — once a game is LIVE, call
     ``BoxScoreMatchupsV3(game_id=...)`` and overwrite each player's
     defender with the one they've actually been matched up with the
     most in the CURRENT game's most recent quarter. Closer to truth.

Hot path NEVER raises. Missing CSV → snapshot returned unchanged. Both
helpers are pure functions over the snapshot dict + a CSV path / game_id.

Public API
----------
    seed_matchups_from_series(snap, series_csv_path=None) -> snap
        Mutates and returns ``snap`` in place, adding/extending
        ``snap["matchups"]`` keyed by ``off_player_id`` (int) →
        ``def_player_id`` (int). Only fills players who appear as an
        offensive player in the series matchup CSV AND who have a
        defender row with the most matchup minutes / partial-possessions.

    override_matchups_from_live_game(snap, game_id=None,
                                      period_filter=None) -> snap
        After the game is LIVE, query BoxScoreMatchupsV3 for the current
        game and OVERWRITE any seed entries with the per-game leader.
        Optional ``period_filter`` (int) — currently unused, reserved for
        when a per-period column is added.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

# Lazy pandas — keep module import cheap. Caller can run without pandas
# (no-op gracefully) but no real path here works without it.
try:
    import pandas as _pd
except Exception:    # pragma: no cover - env without pandas
    _pd = None


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── csv discovery ───────────────────────────────────────────────────────────

def _default_series_path() -> Optional[str]:
    """Return the most-recent ``wcf_defensive_matchups.csv`` we can find."""
    cache_root = os.path.join(PROJECT_DIR, "data", "cache")
    if not os.path.isdir(cache_root):
        return None
    candidates = []
    for name in os.listdir(cache_root):
        if not name.startswith("intel_"):
            continue
        p = os.path.join(cache_root, name, "wcf_defensive_matchups.csv")
        if os.path.isfile(p):
            candidates.append(p)
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1]


# ── public API ──────────────────────────────────────────────────────────────

def seed_matchups_from_series(
    snap: Dict[str, Any],
    series_csv_path: Optional[str] = None,
    *,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Fill ``snap["matchups"]`` from the series-prior matchup CSV.

    Strategy: for each ``off_player_id`` in the CSV, pick the defender
    row with the maximum ``matchup_min`` (tie-break on ``partial_poss``).
    That is the most-likely starting defender tonight.

    Idempotent: if a key is already in ``snap["matchups"]`` and
    ``overwrite=False`` (default), leaves it alone. Set ``overwrite=True``
    to force-refresh from the CSV.
    """
    if not isinstance(snap, dict):
        return snap
    if _pd is None:
        return snap

    if series_csv_path is None:
        series_csv_path = _default_series_path()
    if not series_csv_path or not os.path.isfile(series_csv_path):
        return snap

    try:
        df = _pd.read_csv(series_csv_path)
    except Exception:
        return snap

    needed = {"off_player_id", "def_player_id", "matchup_min", "partial_poss"}
    if not needed.issubset(df.columns):
        return snap

    # Sort so groupby + first picks the highest matchup_min row.
    df = df.sort_values(
        ["off_player_id", "matchup_min", "partial_poss"],
        ascending=[True, False, False],
    )
    leaders = df.groupby("off_player_id", as_index=False).first()

    matchups = snap.get("matchups")
    if not isinstance(matchups, dict):
        matchups = {}

    filled = 0
    for _, row in leaders.iterrows():
        try:
            off_pid = int(row["off_player_id"])
            def_pid = int(row["def_player_id"])
        except (TypeError, ValueError):
            continue
        if (not overwrite) and (off_pid in matchups):
            continue
        matchups[off_pid] = def_pid
        filled += 1

    snap["matchups"] = matchups
    # Provenance trail so the daemon log / consumers can see how the
    # dict was populated. Optional metadata; downstream code ignores it.
    meta = snap.setdefault("_matchups_meta", {})
    meta["series_csv"] = series_csv_path
    meta["seeded_from_series"] = filled
    return snap


def override_matchups_from_live_game(
    snap: Dict[str, Any],
    game_id: Optional[str] = None,
    *,
    fetch_fn=None,
) -> Dict[str, Any]:
    """Overwrite ``snap["matchups"]`` with leaders from the CURRENT game.

    Once a game has been live for ~1 period there's enough matchup data
    on the live ``BoxScoreMatchupsV3`` endpoint to supersede the series
    prior. We pick, per offensive player, the defender with the highest
    ``matchup_minutes_float`` (falling back to partial_possessions on
    tie / missing).

    ``fetch_fn`` is an injection point for tests — defaults to the real
    ``scripts.fetch_defender_matchup.fetch_game_matchups`` function.
    Failure (no nba_api, network error, empty payload) is silently
    swallowed; the seed-from-series values remain intact.
    """
    if not isinstance(snap, dict):
        return snap
    gid = game_id or snap.get("game_id")
    if not gid:
        return snap

    if fetch_fn is None:
        try:
            from scripts.fetch_defender_matchup import fetch_game_matchups  # noqa
            fetch_fn = fetch_game_matchups
        except Exception:
            return snap

    try:
        records = fetch_fn(str(gid)) or []
    except Exception:
        return snap
    if not records:
        return snap

    # Per off_player_id, pick the leader. Use a small dict to avoid
    # depending on pandas here — the live override is on the hot path.
    leader_by_off: Dict[int, Dict[str, Any]] = {}
    for rec in records:
        try:
            off_pid = int(rec.get("off_player_id"))
            def_pid = int(rec.get("def_player_id"))
        except (TypeError, ValueError):
            continue
        # Score: prefer matchup_minutes_float, else partial_possessions.
        try:
            score = float(rec.get("matchup_minutes_float") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score <= 0:
            try:
                score = float(rec.get("partial_possessions") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
        if score <= 0:
            continue
        current = leader_by_off.get(off_pid)
        if current is None or score > current["_score"]:
            leader_by_off[off_pid] = {"def_pid": def_pid, "_score": score}

    matchups = snap.get("matchups")
    if not isinstance(matchups, dict):
        matchups = {}

    overridden = 0
    for off_pid, info in leader_by_off.items():
        prev = matchups.get(off_pid)
        new = info["def_pid"]
        if prev != new:
            overridden += 1
        matchups[off_pid] = new

    snap["matchups"] = matchups
    meta = snap.setdefault("_matchups_meta", {})
    meta["live_overrides"] = overridden
    meta["live_game_id"] = str(gid)
    return snap


__all__ = [
    "seed_matchups_from_series",
    "override_matchups_from_live_game",
]
