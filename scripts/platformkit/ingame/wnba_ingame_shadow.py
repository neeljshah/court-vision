"""scripts.platformkit.ingame.wnba_ingame_shadow -- SHADOW-ONLY WNBA in-game prob
(LANE 3, item C). Mirrors scripts.platformkit.ingame.ingame_sp_shadow EXACTLY:
computes and LOGS (never trades) model_prob_wnba_shadow from
domains.basketball_wnba.adapter.WNBAAdapter.predict_live, so a later offline pass
can compare it to the devigged live price / outcome -- before anyone considers
wiring a real wnba in-game model into the decision path.

THE GAP THIS CLOSES
-------------------
inplay_capture_loop.DEFAULT_SPORTS already captures "wnba" ticks (score/venue-price
pairs + settle labels), but _default_model_fn's ONLY production model dispatch
(live_board.live_model_home_prob) has no wnba branch -- every wnba tick's
model_prob is (correctly) None, so wnba stays capture+grade-label only with no
served in-game model number at all. WNBAAdapter.predict_live (LANE 4, wired) IS a
real, leak-free, calibration-checked in-game blend (see domains/basketball_wnba/
ingame_blend.py) -- this module surfaces it as an ADDITIONAL logged field so its
calibration can be measured against the venue price / outcome, WITHOUT touching
the served model_prob or any decision.

SAFETY CONTRACT (binding, identical to ingame_sp_shadow.py)
------------------------------------------------------------
  1. NEVER changes model_prob, the edge signal, or any bet/decision -- shadow_prob()
     is a pure side-computation appended to the row AFTER inplay_daytrader.on_tick
     has already decided; its only consumer is one ADDITIONAL logged field.
  2. Every path is wrapped so ANY exception yields None (+ one-time debug log),
     never a raised error into the capture path.
  3. Missing inputs (sport != wnba, no period/clock/score in the tick's live
     state, adapter unavailable) -> None. Honest absence, never a guess.

STATE FIELDS CONSUMED (best-effort, all optional)
--------------------------------------------------
The capture loop's live-state payload (ingame_live_state._extract) carries
period/clock ONLY for sport=="nba" today (_segment_fields gates it there) and
ingame_live_state._SPORTS has no "wnba" entry yet -- both pre-existing gaps
OUTSIDE this lane's scope (see inplay_capture_loop.DEFAULT_SPORTS' npb/kbo
comment for the analogous no-model-branch convention). This module reads
state["period"], state["clock"] (ESPN seconds-remaining-in-period, same shape
verified live for basketball/wnba/scoreboard), state["home_score"]/
state["away_score"] defensively and returns None the moment any is absent or
unusable -- so it is CORRECT TODAY (None every tick, honestly) and becomes
USEFUL the moment a future lane wires wnba into ingame_live_state._SPORTS,
with zero change needed here.

INVARIANTS: scripts/platformkit/ingame/ only; <=300 LOC; ASCII only; no writes;
reads domains/basketball_wnba/* (adapter construction reads
data/domains/wnba/espn_scoreboard.parquet, read-only, best-effort). Never
imports src/kernel/api. Calibration measurement only -- no $ / edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_wnba_ingame_shadow.py -q
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STALE_AFTER_SEC = 6.0 * 3600.0  # rebuild the cached adapter after 6h (mirrors ingame_sp_shadow)


def _prob01(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v if 0.0 <= v <= 1.0 else None


class WnbaIngameShadow:
    """Lazy, once-per-process WNBAAdapter prober. Rebuilds if stale (>6h) or if
    never successfully built. A broken build leaves the instance permanently
    None-returning for shadow_prob (logged once), never raising into the
    capture loop.

    Optional constructor args exist ONLY to make the class hermetically
    testable (a fake adapter / clock) -- production code should use the
    module-level get_shadow(), which always uses the real adapter + wall clock.
    """

    def __init__(self, *, adapter: Any = None, clock: Optional[Any] = None) -> None:
        self._inject_adapter = adapter
        self._clock = clock or (lambda: time.time())
        self._adapter: Any = None
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
        if self._adapter is not None and not self._is_stale():
            return
        self._build()

    def _build(self) -> None:
        try:
            if self._inject_adapter is not None:
                self._adapter = self._inject_adapter
            else:
                from domains.basketball_wnba.adapter import WNBAAdapter
                self._adapter = WNBAAdapter()
            self._built_at = self._now()
            self._broken = False
        except Exception as exc:  # noqa: BLE001 -- a broken build -> permanent None, once
            if not self._warned:
                logger.debug("wnba_ingame_shadow build failed (permanent None this process): %s", exc)
                self._warned = True
            self._broken = True
            self._adapter = None

    def shadow_prob(self, sport: str, home: Any, away: Any,
                    state: Dict[str, Any]) -> Optional[float]:
        """WNBA in-game P(home win) via WNBAAdapter.predict_live, for logging
        only. wnba-only; None on ANY miss (non-wnba, missing period/clock/score,
        an unbuildable adapter, or a raise anywhere in predict_live) -- never
        raises."""
        try:
            if str(sport or "").lower() != "wnba":
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
            hs = _prob01_score(state.get("home_score"))
            as_ = _prob01_score(state.get("away_score"))
            if hs is None or as_ is None:
                return None
            self._ensure_built()
            if self._broken or self._adapter is None:
                return None
            neutral = bool(state.get("neutral") or False)
            out = self._adapter.predict_live(
                home_s, away_s, datetime.now(timezone.utc), period_i, clock_s, hs, as_,
                neutral_site=neutral)
            p = out.get("p_home_win") if isinstance(out, dict) else None
            return _prob01(p)
        except Exception as exc:  # noqa: BLE001 -- shadow measurement never raises
            logger.debug("wnba_ingame_shadow shadow_prob failed: %s", exc)
            return None


def _to_clock_s(value: Any) -> Optional[float]:
    """Seconds-remaining-in-period from the tick's raw 'clock' field. None if
    absent/unusable -- never a guessed 0.0 (a real buzzer must be reported as
    0.0 by the feed itself, not fabricated here)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v < 0.0:  # NaN or negative is not a real clock reading
        return None
    return v


def _prob01_score(value: Any) -> Optional[float]:
    """A realized score is a non-negative float; None on any miss (never a
    guessed 0)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v < 0.0:
        return None
    return v


_SINGLETON: Optional[WnbaIngameShadow] = None


def get_shadow() -> WnbaIngameShadow:
    """Module-level singleton so the capture loop reuses one cached adapter per process."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = WnbaIngameShadow()
    return _SINGLETON


__all__ = ["WnbaIngameShadow", "get_shadow", "STALE_AFTER_SEC"]
