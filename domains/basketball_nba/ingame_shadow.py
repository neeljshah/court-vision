"""domains.basketball_nba.ingame_shadow -- SHADOW-ONLY NBA in-game probability
logger (LANE 3, item A). Mirrors scripts.platformkit.ingame.wnba_ingame_shadow
EXACTLY: computes and returns model_prob_nba_shadow from
domains.basketball_nba.predictor.NBAPredictor.predict_live, so a later offline
pass can compare it to the devigged live price / outcome -- before anyone
considers wiring a served NBA in-game model into the decision path.

THE GAP THIS CLOSES
--------------------
scripts.platformkit.frontend.live_board.live_model_home_prob (the production
model_fn dispatch inplay_capture_loop._default_model_fn calls) has branches
ONLY for mlb and soccer/soccer_intl (see live_board.py ~L123-160) -- nba has
no branch there, so every nba in-play tick's model_prob is (correctly) None.
Separately, data/cache/ingame/models/nba_ingame.json is a REPLICATED,
proven (n_games=2634) base+prior calibration surface built by
scripts.platformkit.ingame.ingame_serve, but nothing SERVES it into a live
tick either. domains.basketball_nba.predictor.NBAPredictor.predict_live IS a
real, already-shipped in-game forecaster (W146/W156, temperature-recalibrated)
-- this module surfaces IT as an additional, non-authoritative measurement so
its calibration can be tracked against the venue price / outcome, WITHOUT
touching model_prob, live_board.py, or any decision.

SAFETY CONTRACT (binding, identical to wnba_ingame_shadow.py)
---------------------------------------------------------------
  1. NEVER changes model_prob, the edge signal, or any bet/decision -- shadow_prob()
     is a pure side-computation; its only consumer is one ADDITIONAL logged field.
     model_prob for nba stays None every tick (live_board's dispatch is byte-
     unchanged by this module); the decision path (inplay_daytrader.on_tick) is
     unreachable for nba ticks today regardless of this module's existence.
  2. Every path is wrapped so ANY exception yields None (+ one-time debug log),
     never a raised error into a caller's hot path.
  3. Missing inputs (sport != nba, no period/clock/score in the tick's live
     state, predictor unavailable) -> None. Honest absence, never a guess.

STATE FIELDS CONSUMED (best-effort, all optional)
--------------------------------------------------
scripts.platformkit.ingame.ingame_live_state._SPORTS["nba"] carries period +
clock (seconds remaining in the current quarter, reg_sec=2880.0 = 4x12min) for
every nba tick already (unlike wnba's gap at the time that module shipped, or
tennis's total absence of a clock signal -- see domains/tennis/ingame_shadow.py).
This module reads state["period"], state["clock"], state["home_score"]/
state["away_score"] defensively and returns None the moment any is absent or
unusable.

INVARIANTS: domains/basketball_nba/ only; <=300 LOC; ASCII only; no writes;
reads domains/basketball_nba/predictor.py (constructs NBAPredictor(), which
reads the ingested box corpus, read-only, best-effort). Never imports
src/kernel/api. Measurement only -- no $ / edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_ingame_shadow.py -q
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STALE_AFTER_SEC = 6.0 * 3600.0  # rebuild the cached predictor after 6h (mirrors wnba_ingame_shadow)

_REG_SEC = 2880.0  # 4 x 12min quarters (matches ingame_live_state._SPORTS["nba"]["reg_sec"])
_PERIOD_SEC = _REG_SEC / 4.0


def _prob01(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v if 0.0 <= v <= 1.0 else None


def _to_clock_s(value: Any) -> Optional[float]:
    """Seconds-remaining-in-period from the tick's raw 'clock' field. None if
    absent/unusable -- never a guessed 0.0 (a real buzzer must be reported as
    0.0 by the feed itself, not fabricated here). Mirrors wnba_ingame_shadow."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v < 0.0:
        return None
    return v


def _score(value: Any) -> Optional[float]:
    """A realized score is a non-negative float; None on any miss (never a
    guessed 0)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v < 0.0:
        return None
    return v


def _elapsed_minutes(period: int, clock_s: float) -> float:
    """Minutes ELAPSED in regulation from (period, seconds-left-in-period),
    clamped to [0, 48]. Same shape as WNBAAdapter.predict_live_state's inverse
    math, scaled to NBA's 12-min quarters. OT (period>=5) reports 48.0
    (regulation fully elapsed) since NBAPredictor.predict_live has no OT-length
    parameter -- an honest ceiling, not a fabricated OT clock."""
    if period >= 5:
        return 48.0
    sec_elapsed = (period - 1) * _PERIOD_SEC + (_PERIOD_SEC - min(_PERIOD_SEC, clock_s))
    return max(0.0, min(48.0, sec_elapsed / 60.0))


class NbaIngameShadow:
    """Lazy, once-per-process NBAPredictor prober. Rebuilds if stale (>6h) or
    if never successfully built. A broken build leaves the instance
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
                from domains.basketball_nba.predictor import NBAPredictor
                self._predictor = NBAPredictor()
            self._built_at = self._now()
            self._broken = False
        except Exception as exc:  # noqa: BLE001 -- a broken build -> permanent None, once
            if not self._warned:
                logger.debug("nba ingame_shadow build failed (permanent None this process): %s", exc)
                self._warned = True
            self._broken = True
            self._predictor = None

    def shadow_prob(self, sport: str, home: Any, away: Any,
                    state: Dict[str, Any]) -> Optional[float]:
        """NBA in-game P(home win) via NBAPredictor.predict_live, for
        measurement only. nba-only; None on ANY miss (non-nba, missing
        period/clock/score, an unbuildable predictor, or a raise anywhere in
        predict_live) -- never raises."""
        try:
            if str(sport or "").lower() != "nba":
                return None
            if not isinstance(state, dict):
                return None
            home_s, away_s = str(home or "").strip(), str(away or "").strip()
            if not home_s or not away_s:
                return None
            period = state.get("period")
            if period is None:
                return None
            try:
                period_i = int(period)
            except (TypeError, ValueError):
                return None
            if period_i <= 0:
                return None
            clock_s = _to_clock_s(state.get("clock"))
            if clock_s is None:
                return None
            hs = _score(state.get("home_score"))
            as_ = _score(state.get("away_score"))
            if hs is None or as_ is None:
                return None
            self._ensure_built()
            if self._broken or self._predictor is None:
                return None
            elapsed = _elapsed_minutes(period_i, clock_s)
            out = self._predictor.predict_live(home_s, away_s, elapsed, int(hs), int(as_))
            p = out.get("p_home_win") if isinstance(out, dict) else None
            return _prob01(p)
        except Exception as exc:  # noqa: BLE001 -- shadow measurement never raises
            logger.debug("nba ingame_shadow shadow_prob failed: %s", exc)
            return None


_SINGLETON: Optional[NbaIngameShadow] = None


def get_shadow() -> NbaIngameShadow:
    """Module-level singleton so a repeated caller reuses one cached predictor per process."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = NbaIngameShadow()
    return _SINGLETON


__all__ = ["NbaIngameShadow", "get_shadow", "STALE_AFTER_SEC"]
