"""domains.basketball_nba.pbp_mapper — NBAPBPEventMapper.

Maps cdn.nba.com liveData ``game.actions`` records to the kernel
``CanonicalEvent`` schema defined in ``kernel.config.pbp``.

Design
------
* ``to_canonical`` converts a single raw action dict.  Made shots/free
  throws become ``SCORE`` events with per-event ``points`` (2, 3, or 1).
  Missed shots become ``MISS``.  All other event types map to their
  closest canonical kind.
* ``iter_game`` reads the cached PBP file at
  ``data/cache/team_system/pbp/<game_id>.json`` (offline-only).
* ``possession_side`` returns the ``side`` string from the event itself
  (the NBA liveData ``possession`` field carries the possessing team ID
  at the moment the action was recorded; for most events this is the
  team that performed the action).
* Clock / elapsed-time arithmetic is delegated to ``scripts/team_system/
  pbp_parse.py`` (``parse_clock``, ``period_len``, ``game_sec``).  Those
  helpers are imported via ``importlib.util`` (scripts/ is not a package)
  on first use.

Python 3.9 floor.  No cv2/torch — import-weight near-zero at module load.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from kernel.config.pbp import (
    CanonicalEvent,
    CanonicalEventKind,
    PBPEventMapper,
)

# ---------------------------------------------------------------------------
# Project root + cache paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PBP_DIR = _PROJECT_ROOT / "data" / "cache" / "team_system" / "pbp"
_BOX_DIR = _PROJECT_ROOT / "data" / "cache" / "team_system" / "box"


# ---------------------------------------------------------------------------
# Lazy import of pbp_parse helpers (scripts/ is NOT a package)
# ---------------------------------------------------------------------------

def _load_pbp_parse():
    """Import ``scripts/team_system/pbp_parse.py`` via importlib on first call."""
    mod_name = "_nba_pbp_parse_helpers"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec_path = _PROJECT_ROOT / "scripts" / "team_system" / "pbp_parse.py"
    spec = importlib.util.spec_from_file_location(mod_name, spec_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot locate pbp_parse.py at {spec_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# NBA actionType → CanonicalEventKind mapping table
# ---------------------------------------------------------------------------

_ACTION_KIND: Dict[str, CanonicalEventKind] = {
    # scoring / attempts (handled specially; listed here for completeness)
    "2pt": CanonicalEventKind.SCORE,
    "3pt": CanonicalEventKind.SCORE,
    "freethrow": CanonicalEventKind.SCORE,
    # non-scoring
    "rebound": CanonicalEventKind.POSSESSION_CHANGE,
    "turnover": CanonicalEventKind.TURNOVER,
    "steal": CanonicalEventKind.POSSESSION_CHANGE,
    "foul": CanonicalEventKind.PENALTY,
    "violation": CanonicalEventKind.PENALTY,
    "block": CanonicalEventKind.MISS,
    "substitution": CanonicalEventKind.SUBSTITUTION,
    "timeout": CanonicalEventKind.STOPPAGE,
    "jumpball": CanonicalEventKind.POSSESSION_CHANGE,
    "heave": CanonicalEventKind.MISS,
    # period lifecycle
    "period": CanonicalEventKind.OTHER,   # refined by subType below
    "game": CanonicalEventKind.OTHER,     # refined by subType below
}

# Legacy EVENTMSGTYPE integer codes (stats.nba.com schema) → kind
_LEGACY_TYPE_KIND: Dict[int, CanonicalEventKind] = {
    1: CanonicalEventKind.SCORE,          # made FG
    2: CanonicalEventKind.MISS,           # missed FG
    3: CanonicalEventKind.SCORE,          # made FT
    4: CanonicalEventKind.OTHER,          # rebound
    5: CanonicalEventKind.TURNOVER,       # turnover
    6: CanonicalEventKind.PENALTY,        # foul
    8: CanonicalEventKind.SUBSTITUTION,   # substitution
    12: CanonicalEventKind.PERIOD_START,  # period start
    13: CanonicalEventKind.PERIOD_END,    # period end
}


# ---------------------------------------------------------------------------
# NBAPBPEventMapper
# ---------------------------------------------------------------------------

class NBAPBPEventMapper:
    """Implements the kernel ``PBPEventMapper`` protocol for NBA liveData PBP.

    Parameters
    ----------
    home_team_id:
        NBA team ID of the home team for the current game context.  Required
        for ``possession_side`` to resolve home/away strings.  If ``None``,
        ``possession_side`` returns the raw team-ID string.

    Notes
    -----
    The mapper is stateless with respect to individual events; ``home_team_id``
    only affects the string representation returned by ``possession_side``.
    """

    def __init__(self, home_team_id: Optional[int] = None) -> None:
        self._home_id = home_team_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ts(self, raw: Dict[str, Any]) -> float:
        """Convert a raw action's period + clock to elapsed game seconds."""
        pbp_parse = _load_pbp_parse()
        period = int(raw.get("period") or 1)
        clock_str = raw.get("clock") or ""
        rem = pbp_parse.parse_clock(clock_str)
        return float(pbp_parse.game_sec(period, rem))

    def _side(self, raw: Dict[str, Any]) -> Optional[str]:
        """Return the team-side string for the acting team, or None."""
        tid = raw.get("teamId")
        if not tid:
            return None
        tid_int = int(tid)
        if self._home_id is not None:
            return "home" if tid_int == self._home_id else "away"
        return str(tid_int)

    @staticmethod
    def _score_points(raw: Dict[str, Any]) -> int:
        """Return points for a SCORED play (0 if missed)."""
        at = raw.get("actionType", "")
        sr = raw.get("shotResult", "")
        if sr != "Made":
            return 0
        if at == "3pt":
            return 3
        if at == "2pt":
            return 2
        if at == "freethrow":
            return 1
        return 0

    @staticmethod
    def _resolve_kind(raw: Dict[str, Any]) -> CanonicalEventKind:
        """Determine ``CanonicalEventKind`` from raw action fields."""
        at = raw.get("actionType", "")
        sub = (raw.get("subType") or "").lower()

        # --- scoring / attempt events ---
        if at in ("2pt", "3pt"):
            return (CanonicalEventKind.SCORE
                    if raw.get("shotResult") == "Made"
                    else CanonicalEventKind.MISS)
        if at == "freethrow":
            return (CanonicalEventKind.SCORE
                    if raw.get("shotResult") == "Made"
                    else CanonicalEventKind.MISS)

        # --- period / game lifecycle ---
        if at == "period":
            if sub == "start":
                return CanonicalEventKind.PERIOD_START
            if sub == "end":
                return CanonicalEventKind.PERIOD_END
            return CanonicalEventKind.OTHER
        if at == "game":
            if sub in ("start",):
                return CanonicalEventKind.PERIOD_START
            if sub in ("end", "final"):
                return CanonicalEventKind.PERIOD_END
            return CanonicalEventKind.OTHER

        # --- legacy integer EVENTMSGTYPE (some cached records carry this) ---
        legacy = raw.get("EVENTMSGTYPE")
        if legacy is not None:
            try:
                return _LEGACY_TYPE_KIND.get(int(legacy),
                                             CanonicalEventKind.OTHER)
            except (ValueError, TypeError):
                pass

        return _ACTION_KIND.get(at, CanonicalEventKind.OTHER)

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def to_canonical(self, raw_event: Any) -> CanonicalEvent:
        """Convert a single cdn.nba.com liveData action dict to a CanonicalEvent.

        Parameters
        ----------
        raw_event:
            A dict corresponding to one element from ``game.actions``.

        Returns
        -------
        CanonicalEvent
            Never returns ``None``; unmappable events get kind ``OTHER``.
        """
        raw: Dict[str, Any] = raw_event  # type: ignore[assignment]
        kind = self._resolve_kind(raw)
        pts = self._score_points(raw) if kind == CanonicalEventKind.SCORE else 0
        side = self._side(raw)
        actor_raw = raw.get("personId")
        actor_id: Optional[str] = str(actor_raw) if actor_raw else None
        return CanonicalEvent(
            kind=kind,
            ts_game_sec=self._ts(raw),
            period=int(raw.get("period") or 1),
            side=side,
            points=pts,
            actor_id=actor_id,
            detail=dict(raw),
        )

    def iter_game(self, game_id: str) -> Iterator[CanonicalEvent]:
        """Yield CanonicalEvents for all actions in *game_id* (offline cache).

        Reads ``data/cache/team_system/pbp/<game_id>.json``.  Also reads the
        corresponding box score to resolve the home team ID so that ``side``
        fields are "home"/"away" strings (not raw team IDs).

        Parameters
        ----------
        game_id:
            NBA game ID string, e.g. ``"0042500401"``.

        Raises
        ------
        FileNotFoundError
            If the cached PBP file does not exist.
        """
        pbp_path = _PBP_DIR / f"{game_id}.json"
        box_path = _BOX_DIR / f"{game_id}.json"
        with open(pbp_path, encoding="utf-8") as fh:
            pbp_data = json.load(fh)

        # Resolve home_team_id from box if available; fall back to raw IDs.
        if box_path.exists():
            with open(box_path, encoding="utf-8") as fh:
                box_data = json.load(fh)
            game_box = box_data.get("game", {})
            home_raw = game_box.get("homeTeam", {}).get("teamId")
            if home_raw is not None:
                self._home_id = int(home_raw)

        actions = pbp_data.get("game", {}).get("actions", [])
        for raw in actions:
            yield self.to_canonical(raw)

    def possession_side(self, event: CanonicalEvent) -> Optional[str]:
        """Return the possessing team's side after *event*, or None.

        Uses the ``possession`` field preserved in ``event.detail`` (the NBA
        liveData ``possession`` key is the possessing team ID at event time).
        Falls back to ``event.side`` for scoring events (possession transfers
        to the non-scoring team, but we surface the acting side here; callers
        that need the defensive side should flip).

        Parameters
        ----------
        event:
            A ``CanonicalEvent`` produced by this mapper (detail must contain
            the raw NBA action fields).

        Returns
        -------
        str or None
        """
        raw_poss = event.detail.get("possession")
        if raw_poss:
            try:
                poss_id = int(raw_poss)
                if self._home_id is not None:
                    return "home" if poss_id == self._home_id else "away"
                return str(poss_id)
            except (ValueError, TypeError):
                pass
        return event.side


# ---------------------------------------------------------------------------
# Protocol conformance assertion (module-load sanity)
# ---------------------------------------------------------------------------

assert isinstance(NBAPBPEventMapper(), PBPEventMapper), (
    "NBAPBPEventMapper does not satisfy the PBPEventMapper protocol"
)
