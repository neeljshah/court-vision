"""scripts.platformkit.ingame.inplay_grade_run -- thin LIVE in-play GRADE harness (Lane G).

Consumes Lane K's connector (odds_provider.inplay_kalshi) and the EXISTING P1 CLV replay
(forward_capture.inplay_clv_replay) to answer ONE honest question for a REAL Kalshi in-play
MLB series: did our in-game model (domains.mlb.predictor.predict_live), repriced LEAK-FREE
from state-as-of-each-tick only, BEAT the in-play close -- or (as expected for one/few games)
is it honestly INSUFFICIENT_DATA?

It REUSES, never rebuilds:
  * the series  -> inplay_kalshi.fetch_price_history (settled-game candles) or fetch_inplay
                   (live snapshot), already canonical ticks (prob in [0,1], ts, side, ...).
  * the grader  -> inplay_clv_replay.replay_series (the gate: BEAT iff mean_clv>eps AND
                   hit_rate>0.5 AND n_scored>=MIN_TICKS). We do NOT re-implement the verdict.
  * the model   -> domains.mlb.predictor.predict_live, reached through an INJECTABLE model_fn
                   with the replay's own signature model_fn(tick, history_so_far)->prob.

LEAK FLOOR (binding): model_fn is handed history_so_far = series[:i+1] ONLY -- ticks up to and
INCLUDING the current one -- never series[i+1:], never the outcome, never the close. The close
is the last tick, derived AFTER scoring by the replay harness; the model never receives it.

ALIGNMENT (binding -- a misaligned pair manufactures fake CLV): market_prob and model_prob MUST
be the SAME side. The convention is HOME: market_prob = the venue's implied P(home), model_prob
= model P(home win). A tick whose side cannot be confirmed HOME-aligned, or whose prob/model
prob is missing / out of [0,1], is SKIPPED (counted), NEVER 0-filled into a fake observation.

HONESTY (binding):
  * A single / few games is variance, NOT signal -> below MIN_TICKS scored the verdict is
    INSUFFICIENT_DATA by design (the replay harness enforces this; we never override it to BEAT).
  * PAPER / measurement only. CLV is in PROBABILITY space. NO $ / ROI / stake / edge field.
  * A missing / illiquid price -> the tick is skipped (VOID), never faked.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no network at import;
never edits live_grade.py or inplay_clv_replay.py (reuse them); never edits src/ or kernel/.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_grade_run.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.forward_capture import inplay_clv_replay as ic

logger = logging.getLogger(__name__)

# The side both numbers are aligned to (see ALIGNMENT in the module docstring).
PAIR_SIDE = "home"

# A model callback with the replay harness's OWN signature -- so the model the harness scores
# is, byte-for-byte, the leak-free model_fn the gate consumes. Returns a HOME-side prob in
# [0,1], or None to SKIP the tick (never a fabricated number).
#   model_fn(tick: dict, history_so_far: list[dict]) -> Optional[float]
ModelFn = Callable[[Dict[str, Any], List[Dict[str, Any]]], Optional[float]]

# A side-alignment predicate: True iff a tick's `prob` already refers to the HOME side. The
# default trusts the connector's HOME-aligned ticks; the live path can inject a stricter check.
SideFn = Callable[[Dict[str, Any]], bool]


# --------------------------------------------------------------------------------------- #
# alignment / validity helpers                                                            #
# --------------------------------------------------------------------------------------- #
def _prob(value: Any) -> Optional[float]:
    """Coerce to a prob in [0,1]; None if non-numeric / out of range (never fabricated)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _default_is_home(tick: Dict[str, Any]) -> bool:
    """Default HOME-alignment check: trust the connector's HOME-aligned ticks.

    The connector emits one YES-prob tick per liquid side; the harness's caller is responsible
    for handing in a HOME-side series (or injecting a stricter side_fn). A tick missing a usable
    prob is rejected here so it is SKIPPED, not graded.
    """
    return _prob(tick.get("prob")) is not None


def align_home_series(series: List[Dict[str, Any]], *,
                      side_fn: SideFn = _default_is_home) -> List[Dict[str, Any]]:
    """Filter a raw tick series to HOME-aligned ticks with a valid prob, sorted by ts.

    A tick that is not confirmed HOME-aligned, or whose prob is missing / out of [0,1], is
    DROPPED (VOID) -- never 0-filled, never side-flipped silently into a fake observation.
    Returns a new list; never raises (a malformed tick is dropped).
    """
    out: List[Dict[str, Any]] = []
    for t in series:
        if not isinstance(t, dict):
            continue
        p = _prob(t.get("prob"))
        if p is None:
            continue
        try:
            if not side_fn(t):
                continue
        except Exception as exc:  # noqa: BLE001 -- a bad predicate drops the tick, never crashes
            logger.debug("side_fn failed for tick: %s", exc)
            continue
        t2 = dict(t)
        t2["prob"] = p
        out.append(t2)
    out.sort(key=lambda r: str(r.get("ts", "")))
    return out


# --------------------------------------------------------------------------------------- #
# the harness                                                                             #
# --------------------------------------------------------------------------------------- #
def grade_inplay_series(series: List[Dict[str, Any]],
                        model_fn: ModelFn,
                        *,
                        side_fn: SideFn = _default_is_home,
                        eps: float = ic.EPS_DEFAULT,
                        min_ticks: int = ic.MIN_TICKS_DEFAULT) -> Dict[str, Any]:
    """Grade ONE real in-play price series vs the model's repriced number; honest verdict.

    1. ALIGN: keep only HOME-aligned, valid-prob ticks (align_home_series); a misaligned / None
       tick is SKIPPED, never faked.
    2. PAIR + GRADE: feed the aligned series to the EXISTING inplay_clv_replay.replay_series with
       a leak-free wrapper that calls model_fn(tick, history_so_far=series[:i+1]) ONLY. If model_fn
       returns None (cannot price this tick) we fall back to the market prob so that tick scores as
       a NO-LEAN (clv 0) -- it can never manufacture a fake beat, and the tick is recorded as
       skipped_model. The harness's gate decides BEAT / BEHIND / MATCH / INSUFFICIENT_DATA.

    Returns the ReplayResult-as-dict plus {n_input, n_aligned, n_skipped_align, n_skipped_model,
    side, edge_claimed:False}. mean_clv is PROBABILITY space; there is NO $ / ROI field. Never
    raises (an empty / unusable series -> INSUFFICIENT_DATA).
    """
    n_input = len(series)
    aligned = align_home_series(series, side_fn=side_fn)
    n_aligned = len(aligned)
    n_skipped_align = n_input - n_aligned

    skipped_model = {"n": 0}

    def _wrapped(tick: Dict[str, Any], history: List[Dict[str, Any]]) -> float:
        # LEAK-FREE: `history` IS series[:i+1] (handed in by replay_series). model_fn must use
        # only it -- never the outcome, never the close. None -> no lean (clv 0), never faked.
        try:
            mp = model_fn(tick, history)
        except Exception as exc:  # noqa: BLE001 -- a model failure skips the tick, never crashes
            logger.debug("model_fn failed at tick ts=%s: %s", tick.get("ts"), exc)
            mp = None
        p = _prob(mp)
        if p is None:
            skipped_model["n"] += 1
            return float(tick["prob"])  # market-follow on this tick -> edge 0 -> no fake beat
        return p

    result = ic.replay_series(aligned, _wrapped, eps=eps, min_ticks=min_ticks)
    out = result.as_dict()
    out.update({
        "n_input": n_input,
        "n_aligned": n_aligned,
        "n_skipped_align": n_skipped_align,
        "n_skipped_model": skipped_model["n"],
        "side": PAIR_SIDE,
        "edge_claimed": False,
    })
    return out


# --------------------------------------------------------------------------------------- #
# default model wrapper (domains.mlb.predictor.predict_live)                               #
# --------------------------------------------------------------------------------------- #
def make_mlb_model_fn(home: str, away: str,
                      state_fn: Callable[[Dict[str, Any], List[Dict[str, Any]]],
                                         Optional[Dict[str, Any]]],
                      *, predictor: Any = None) -> ModelFn:
    """Build a leak-free MLB model_fn for grade_inplay_series.

    The real Kalshi in-play tick carries a PRICE + timestamp, NOT a box score. To run the
    domains.mlb.predictor.predict_live model we need the game STATE (inning/half/score) as-of
    each tick. That mapping is a SEPARATE, synchronized score feed the CALLER injects via
    state_fn(tick, history_so_far) -> {"inning","half","home_runs","away_runs"} | None. We do
    NOT invent a score from the price -- that would be circular (pricing the market off itself).

    If state_fn returns None for a tick (no synchronized state), the model_fn returns None and
    that tick is recorded as skipped_model (no lean) -- an HONEST "cannot price this tick", never
    a fabricated number. predictor defaults to a lazily-built MLBPredictor (network/corpus at
    CALL time, never import); inject a stub in tests so NO corpus is required.
    """
    pred_holder = {"p": predictor}

    def _model_fn(tick: Dict[str, Any], history: List[Dict[str, Any]]) -> Optional[float]:
        st = state_fn(tick, history)
        if not isinstance(st, dict):
            return None
        try:
            inning = int(st["inning"])
            half = str(st["half"])
            hr = int(st["home_runs"])
            ar = int(st["away_runs"])
        except (KeyError, TypeError, ValueError):
            return None
        if pred_holder["p"] is None:
            from domains.mlb.predictor import MLBPredictor  # noqa: PLC0415 -- lazy, no import net
            pred_holder["p"] = MLBPredictor()
        live = pred_holder["p"].predict_live(home, away, inning, half, hr, ar)
        return _prob(live.get("p_home_win"))

    return _model_fn


# --------------------------------------------------------------------------------------- #
# live read-only entry point                                                              #
# --------------------------------------------------------------------------------------- #
def run_live_once(market_ref: str, *, sport: str = "mlb", side: str = "",
                  model_fn: Optional[ModelFn] = None,
                  fetch_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
                  window: Optional[int] = None,
                  eps: float = ic.EPS_DEFAULT,
                  min_ticks: int = ic.MIN_TICKS_DEFAULT) -> Dict[str, Any]:
    """Fetch ONE real (settled) Kalshi in-play series via fetch_price_history and grade it.

    READ-ONLY network GET (no orders, no auth). fetch_fn defaults to
    inplay_kalshi.fetch_price_history; inject it (and model_fn) in tests for full offline runs.
    If no model_fn is given we use the market-follow baseline (naive) -- which can NEVER score
    BEAT, so an honest run with no synchronized score feed reports MATCH / INSUFFICIENT_DATA, not
    a fake edge. A feed failure -> empty series -> INSUFFICIENT_DATA. Never raises.
    """
    if fetch_fn is None:
        from scripts.platformkit.odds_provider.inplay_kalshi import (  # noqa: PLC0415
            fetch_price_history as fetch_fn,  # type: ignore[assignment]
        )
    try:
        series = fetch_fn(market_ref, window, sport=sport, side=side)
    except Exception as exc:  # noqa: BLE001 -- a read failure is INSUFFICIENT_DATA, never a crash
        logger.warning("run_live_once fetch failed for %s: %s", market_ref, exc)
        series = []
    mf: ModelFn = model_fn if model_fn is not None else (
        lambda tick, history: _prob(tick.get("prob")))  # naive market-follow baseline
    out = grade_inplay_series(series or [], mf, eps=eps, min_ticks=min_ticks)
    out["market_ref"] = str(market_ref)
    return out


__all__ = [
    "PAIR_SIDE", "ModelFn", "SideFn",
    "align_home_series", "grade_inplay_series", "make_mlb_model_fn", "run_live_once",
]
