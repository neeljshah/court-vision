"""scripts.platformkit.ingame.state_bus -- sport-blind GameState + in-process bus.

A normalized, sport-blind snapshot of realized live game state, plus a tiny
in-process publish/latest bus. This layer carries STATE ONLY:

  * It never predicts and never claims an edge (markets are efficient; the
    validated in-game number is produced downstream and is eval-gated).
  * It never fabricates. A caller that has no valid game publishes nothing;
    latest() of an unknown game returns None.

PURE + NEVER RAISES (binding): publish()/latest() swallow any internal error so a
bad row can never sink the live loop. GameState construction validates and clamps.

HONEST in-game invariant (downstream contract): a correct reprice's variance must
SHRINK as the game progresses (Q1 wide -> Q4 tight). GameState exposes
fraction_elapsed() as the freshness lever the repricer keys on -- the ONLY
validated in-game lever (pregame prior + realized live state).

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; no network.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional

# Lifecycle status values (sport-blind). 'live' == a game in progress.
_STATUS = ("pre", "live", "final")

# Total regulation minutes per sport, used only to derive a freshness fraction.
# Unknown sports fall back to None (fraction unavailable, never fabricated).
_REGULATION_MIN: Dict[str, float] = {
    "nba": 48.0,
    "soccer": 90.0,
    "soccer_intl": 90.0,
}


def _coerce_int(v: Any) -> Optional[int]:
    """Best-effort int; None on anything non-numeric (never raises)."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _coerce_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class GameState:
    """A sport-blind snapshot of realized live game state.

    Fields:
      sport       -- platform sport id ("nba", "mlb", "soccer_intl", ...).
      game_id     -- stable id for this game within the sport (str).
      period      -- current period/quarter/inning (1-based), or None pre-tip.
      clock_sec   -- seconds REMAINING in the current period, or None.
      home_score  -- realized home score (int), 0 at tip, never None when live.
      away_score  -- realized away score (int).
      possession  -- "home" | "away" | None (None when unknown -- not fabricated).
      status      -- "pre" | "live" | "final".
      extras      -- generic sport-specific dict (e.g. inning half, elapsed_min,
                     period_len_sec); carried verbatim, never required.

    Construction coerces/validates and clamps; it never raises on bad input.
    """

    sport: str
    game_id: str
    period: Optional[int] = None
    clock_sec: Optional[float] = None
    home_score: int = 0
    away_score: int = 0
    possession: Optional[str] = None
    status: str = "pre"
    extras: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalize without ever raising: use object.__setattr__ (frozen dataclass).
        st = str(self.status).lower()
        object.__setattr__(self, "status", st if st in _STATUS else "pre")
        object.__setattr__(self, "sport", str(self.sport).lower())
        object.__setattr__(self, "game_id", str(self.game_id))
        object.__setattr__(self, "period", _coerce_int(self.period))
        cs = _coerce_float(self.clock_sec)
        object.__setattr__(self, "clock_sec", None if cs is None else max(0.0, cs))
        object.__setattr__(self, "home_score", _coerce_int(self.home_score) or 0)
        object.__setattr__(self, "away_score", _coerce_int(self.away_score) or 0)
        poss = self.possession
        object.__setattr__(self, "possession",
                           poss if poss in ("home", "away") else None)
        object.__setattr__(self, "extras", dict(self.extras or {}))

    # -- derived freshness lever -------------------------------------------
    def is_live(self) -> bool:
        return self.status == "live"

    def fraction_elapsed(self) -> Optional[float]:
        """Fraction of regulation that has ELAPSED in [0, 1], or None if unknown.

        This is the freshness lever the repricer keys on: variance must SHRINK as
        this rises (Q1 ~ 0.25 -> end of Q4 -> 1.0). Prefers extras['elapsed_min']
        when an upstream parser already computed elapsed minutes; otherwise derives
        it from period + clock_sec + per-period length. Returns None (never a faked
        number) if there is not enough information.
        """
        if self.status == "final":
            return 1.0
        if self.status != "live":
            return 0.0
        elapsed_min = _coerce_float(self.extras.get("elapsed_min"))
        total = _REGULATION_MIN.get(self.sport)
        if elapsed_min is not None and total:
            return _clamp01(elapsed_min / total)
        # Derive from period + clock_sec when a per-period length is known.
        per_len = _coerce_float(self.extras.get("period_len_sec"))
        if self.period and per_len and self.clock_sec is not None and total:
            done_periods = max(0, self.period - 1)
            elapsed_sec = done_periods * per_len + (per_len - self.clock_sec)
            return _clamp01(elapsed_sec / (total * 60.0))
        return None

    def with_extras(self, **kw: Any) -> "GameState":
        """Return a copy with merged extras (frozen-safe convenience)."""
        merged = dict(self.extras)
        merged.update(kw)
        return replace(self, extras=merged)

    def to_dict(self) -> Dict[str, Any]:
        return {"sport": self.sport, "game_id": self.game_id,
                "period": self.period, "clock_sec": self.clock_sec,
                "home_score": self.home_score, "away_score": self.away_score,
                "possession": self.possession, "status": self.status,
                "fraction_elapsed": self.fraction_elapsed(),
                "extras": dict(self.extras)}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


# --------------------------------------------------------------------------- bus
class StateBus:
    """A tiny thread-safe in-process bus: publish(state) / latest(game_id).

    Keyed by (sport, game_id) so two sports can share a bus without collision.
    Pure and never raises: a bad publish is silently dropped (returns False),
    latest() of an unknown/absent game returns None.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: Dict[str, GameState] = {}

    @staticmethod
    def _key(sport: str, game_id: str) -> str:
        return f"{str(sport).lower()}:{game_id}"

    def publish(self, state: Optional[GameState]) -> bool:
        """Store *state* as the latest for its game. Returns True if stored.

        None or a non-GameState is ignored (never raises, never fabricates).
        """
        if not isinstance(state, GameState):
            return False
        try:
            with self._lock:
                self._latest[self._key(state.sport, state.game_id)] = state
            return True
        except Exception:  # pragma: no cover - defensive; bus must never sink loop
            return False

    def latest(self, game_id: str, sport: str = "nba") -> Optional[GameState]:
        """Most recent GameState for *game_id* in *sport*, or None if none seen."""
        try:
            with self._lock:
                return self._latest.get(self._key(sport, game_id))
        except Exception:  # pragma: no cover - defensive
            return None

    def all_live(self) -> Dict[str, GameState]:
        """Snapshot of every currently-live game keyed by 'sport:game_id'."""
        try:
            with self._lock:
                return {k: v for k, v in self._latest.items() if v.is_live()}
        except Exception:  # pragma: no cover - defensive
            return {}

    def clear(self) -> None:
        with self._lock:
            self._latest.clear()


# Process-wide default bus the live loop + repricer share.
STATE_BUS = StateBus()


def publish(state: Optional[GameState]) -> bool:
    """Publish to the process-wide default bus (convenience)."""
    return STATE_BUS.publish(state)


def latest(game_id: str, sport: str = "nba") -> Optional[GameState]:
    """Read the latest GameState from the process-wide default bus."""
    return STATE_BUS.latest(game_id, sport=sport)
