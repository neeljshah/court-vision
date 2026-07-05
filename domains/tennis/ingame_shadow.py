"""domains.tennis.ingame_shadow -- SHADOW-ONLY tennis in-game probability
logger (LANE 3, item A). Mirrors scripts.platformkit.ingame.wnba_ingame_shadow
EXACTLY: computes and returns model_prob_tennis_shadow from
domains.tennis.predictor.TennisPredictor.predict_live, so a later offline pass
can compare it to the devigged live price / outcome -- before anyone considers
wiring a served tennis in-game model into the decision path.

THE GAP THIS CLOSES
--------------------
scripts.platformkit.frontend.live_board.live_model_home_prob (the production
model_fn dispatch inplay_capture_loop._default_model_fn calls) has branches
ONLY for mlb and soccer/soccer_intl (see live_board.py ~L123-160) -- tennis has
no branch there, so every tennis in-play tick's model_prob is (correctly)
None. Separately, data/cache/ingame/models/tennis_ingame.json is a
REPLICATED, proven (n_games=40588) base+prior calibration surface built by
scripts.platformkit.ingame.ingame_serve, but nothing SERVES it into a live
tick either. domains.tennis.predictor.TennisPredictor.predict_live IS a real,
already-shipped in-game forecaster (W156 Platt-on-logit in-game recal) -- this
module surfaces IT as an additional, non-authoritative measurement so its
calibration can be tracked against the venue price / outcome, WITHOUT
touching model_prob, live_board.py, or any decision.

SAFETY CONTRACT (binding, identical to wnba_ingame_shadow.py)
---------------------------------------------------------------
  1. NEVER changes model_prob, the edge signal, or any bet/decision -- shadow_prob()
     is a pure side-computation; its only consumer is one ADDITIONAL logged field.
     model_prob for tennis stays None every tick (live_board's dispatch is
     byte-unchanged by this module); the decision path (inplay_daytrader.
     on_tick) is unreachable for tennis ticks today regardless of this
     module's existence.
  2. Every path is wrapped so ANY exception yields None (+ one-time debug log),
     never a raised error into a caller's hot path.
  3. Missing inputs (sport != tennis, no set score in the tick's live state,
     predictor unavailable) -> None. Honest absence, never a guess.

STATE FIELDS CONSUMED (best-effort, all optional) -- and the honest gap
-------------------------------------------------------------------------
scripts.platformkit.ingame.ingame_live_state has NO clock/games-within-set
signal for tennis at all: _frac_elapsed returns None for sport=="tennis"
(no game-clock exists in the sport), and _segment_fields only derives a "set"
number from `period` -- games_p1/games_p2 are simply never populated anywhere
upstream. state["home_score"]/state["away_score"] ARE usable: _score()'s
tennis fallback (no .score field on an ESPN tennis competitor -- verified live
2026-07-03, see ingame_live_state.py) derives a SETS-WON count from
.linescores, which is exactly the sets_p1/sets_p2 predict_live expects. So
this module reads state["home_score"]/state["away_score"] as sets-won and
passes games_p1=games_p2=0 (predict_live's own default for a missing games
score, not a fabricated in-set count) -- an HONEST DEGRADE, not a fake value:
domains.tennis.repricer.TennisRepricer DOES apply a small bounded lean
(+/-0.04 max) from extra['games_1']/['games_2'] when g1+g2>0 (an in-progress
set's game score), so passing 0/0 is not a no-op in general -- it correctly
SKIPS that lean (the repricer's own `if (g1 + g2) > 0` guard) rather than
inventing a fake in-set game score, so p1_match_win here is the set-score-only
conditional with no games-within-set nudge (confirmed by reading
domains/tennis/repricer.py's reprice() in full before writing this module).
Tour defaults to ATP (TennisPredictor()'s own default; the capture
loop's single "tennis" sport id merges ATP+WTA boards with no tour tag on the
tick, same honest default _build_predictor("tennis") already uses).

INVARIANTS: domains/tennis/ only; <=300 LOC; ASCII only; no writes; reads
domains/tennis/predictor.py (constructs TennisPredictor(), which reads the
ingested matches/asof_hold corpus, read-only, best-effort). Never imports
src/kernel/api. Measurement only -- no $ / edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/test_ingame_shadow.py -q
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STALE_AFTER_SEC = 6.0 * 3600.0  # rebuild the cached predictor after 6h (mirrors wnba_ingame_shadow)


def _prob01(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v if 0.0 <= v <= 1.0 else None


def _sets(value: Any) -> Optional[int]:
    """A realized sets-won count is a non-negative int; None on any miss
    (never a guessed 0). Mirrors wnba_ingame_shadow's score-parsing discipline."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v < 0.0:
        return None
    return int(v)


class TennisIngameShadow:
    """Lazy, once-per-process TennisPredictor prober. Rebuilds if stale (>6h)
    or if never successfully built. A broken build leaves the instance
    permanently None-returning for shadow_prob (logged once), never raising
    into a caller's hot path.

    Optional constructor args exist ONLY to make the class hermetically
    testable (a fake predictor / clock) -- production code should use the
    module-level get_shadow(), which always uses the real predictor + wall clock.
    """

    def __init__(self, *, predictor: Any = None, clock: Optional[Any] = None) -> None:
        self._inject_predictor = predictor
        self._clock = clock or (lambda: time.time())
        self._predictor: Any = None
        self._built_at: Optional[float] = None
        self._broken = False
        self._warned = False

    def _now(self) -> float:
        try:
            return float(self._clock())
        except Exception:  # noqa: BLE001
            return time.time()

    def _is_stale(self) -> bool:
        if self._built_at is None:
            return True
        return (self._now() - self._built_at) > STALE_AFTER_SEC

    def _ensure_built(self) -> None:
        if self._broken:
            return
        if self._predictor is not None and not self._is_stale():
            return
        self._build()

    def _build(self) -> None:
        try:
            if self._inject_predictor is not None:
                self._predictor = self._inject_predictor
            else:
                from domains.tennis.predictor import TennisPredictor
                self._predictor = TennisPredictor()
            self._built_at = self._now()
            self._broken = False
        except Exception as exc:  # noqa: BLE001 -- a broken build -> permanent None, once
            if not self._warned:
                logger.debug("tennis ingame_shadow build failed (permanent None this process): %s", exc)
                self._warned = True
            self._broken = True
            self._predictor = None

    def shadow_prob(self, sport: str, home: Any, away: Any,
                    state: Dict[str, Any]) -> Optional[float]:
        """Tennis in-game P(p1/home win) via TennisPredictor.predict_live, for
        measurement only. tennis-only; None on ANY miss (non-tennis, missing
        set score, an unbuildable predictor, or a raise anywhere in
        predict_live) -- never raises. games_p1/games_p2 are passed as their
        honest default 0 (see module docstring -- no games-within-set signal
        exists upstream; predict_live does not use them in its probability
        math)."""
        try:
            if str(sport or "").lower() != "tennis":
                return None
            if not isinstance(state, dict):
                return None
            home_s, away_s = str(home or "").strip(), str(away or "").strip()
            if not home_s or not away_s:
                return None
            sets_home = _sets(state.get("home_score"))
            sets_away = _sets(state.get("away_score"))
            if sets_home is None or sets_away is None:
                return None
            self._ensure_built()
            if self._broken or self._predictor is None:
                return None
            out = self._predictor.predict_live(home_s, away_s, sets_home, sets_away)
            p = out.get("p1_match_win") if isinstance(out, dict) else None
            return _prob01(p)
        except Exception as exc:  # noqa: BLE001 -- shadow measurement never raises
            logger.debug("tennis ingame_shadow shadow_prob failed: %s", exc)
            return None


_SINGLETON: Optional[TennisIngameShadow] = None


def get_shadow() -> TennisIngameShadow:
    """Module-level singleton so a repeated caller reuses one cached predictor per process."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = TennisIngameShadow()
    return _SINGLETON


__all__ = ["TennisIngameShadow", "get_shadow", "STALE_AFTER_SEC"]
