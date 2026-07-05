"""scripts.platformkit.ingame.kbo_live_model -- in-game P(home win) for KBO (NOT WIRED).

LANE (npbkbo-live-model, wire-dispatch stage) CORRECTED FINDING: the KBO BASE fit's own
verdict (data/domains/kbo/ingame_base_fit_verdict.json) is HONEST_NEGATIVE --
disqualified_by_noise_control=true, params_persisted=false. The candidate BASE formula

    p_home = sigmoid((a + b * frac_elapsed) * state_diff + c)

was fit on SYNTHETIC per-inning states (states_source=synthetic_from_final_score; NO real
intra-game tick corpus exists for KBO -- data/cache/ingame has zero kbo_states__*.parquet).
A planted pure_noise_control run through the identical fit+guard pipeline on a ZERO-signal
corpus ALSO reported a non-degenerate/positive BSS (control_passes_as_nondegenerate=true,
bss_vs_coin=0.451525) -- proving the positive number on the real corpus
(bss_vs_coin_pooled=0.472161) is a synthesis artifact (the same endpoint-pin leak that
disqualified NPB), not measured in-game skill. Per the disqualification, params were NEVER
persisted: data/domains/kbo/ingame_base_params.json does not exist on disk.

This module therefore has no frozen params to load: _load_params() always returns None,
so kbo_home_prob() returns None on every input -- an honest, fail-closed gap, not a bug.
It is kept only as inert, unreachable code (no dispatch branch calls it from
scripts.platformkit.frontend.live_board.live_model_home_prob) in case a future lane
locates a real KBO intra-game tick corpus and can re-fit + re-gate a BASE model that
survives the same pure-noise control. Until then, NPB and KBO are symmetric: both
HONEST_NEGATIVE, both unwired (see test_npb_kbo_live_model_gap.py).

  * state_diff must come from an UNFINISHED game (home_score/away_score present, status
    not final) -- a finished game has no "live" prob to serve; returns None regardless.
  * The REAL live feed (scripts.platformkit.ingame.npb_kbo_live_state) also NEVER emits a
    frac_elapsed for KBO (koreabaseball's GetScheduleList exposes no mid-game marker
    keyless) -- a second, independent reason this would return None even if params existed.
  * NO $ edge is claimed anywhere in this module.

INVARIANTS: build only under scripts/platformkit/; never edit src/ or kernel/; ASCII;
<=300 LOC; public fn NEVER raises (a model miss is a clean skip, not a crashed tick).
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_PARAMS_PATH = os.path.join(_REPO, "data", "domains", "kbo", "ingame_base_params.json")

_PARAMS_CACHE: Dict[str, Any] = {}


def _load_params() -> Optional[Dict[str, float]]:
    """Load (once, cached) the frozen fitted (a, b, c) -- None if missing/malformed/
    the fit's own verdict was not DONE (fail closed, never fabricate a slope)."""
    if "params" in _PARAMS_CACHE:
        return _PARAMS_CACHE["params"]
    params: Optional[Dict[str, float]] = None
    try:
        with open(_PARAMS_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if raw.get("verdict") == "DONE" and not raw.get("degenerate_base_guard", {}).get(
                "degenerate", True):
            params = {"a": float(raw["a"]), "b": float(raw["b"]), "c": float(raw.get("c", 0.0))}
    except Exception as exc:  # noqa: BLE001 -- missing/malformed params -> honest None
        logger.debug("kbo_live_model params load failed: %s", exc)
        params = None
    _PARAMS_CACHE["params"] = params
    return params


def _is_final(state: Dict[str, Any]) -> bool:
    st = str(state.get("status") or "").lower()
    return any(k in st for k in ("final", "post", "complete"))


def kbo_home_prob(state: Dict[str, Any]) -> Optional[float]:
    """In-game P(home win) for KBO from {state_diff, frac_elapsed}, or None (clean skip).

    None when: state is not a dict; params unavailable/degenerate; the game is FINAL
    (decided by the real status string, never by frac saturating); state_diff/frac_elapsed
    missing or unparseable; frac_elapsed outside [0,1]. The real live feed
    (npb_kbo_live_state) currently NEVER supplies frac_elapsed, so in practice this always
    returns None on the live path today -- an honest, fail-closed gap, not a crash.
    NEVER raises."""
    try:
        if not isinstance(state, dict) or _is_final(state):
            return None
        params = _load_params()
        if params is None:
            return None
        diff = state.get("state_diff")
        frac = state.get("frac_elapsed")
        if diff is None or frac is None:
            return None
        frac_f = float(frac)
        if not (0.0 <= frac_f <= 1.0):
            return None
        diff_f = float(diff)
        z = (params["a"] + params["b"] * frac_f) * diff_f + params["c"]
        return 1.0 / (1.0 + math.exp(-z))
    except Exception as exc:  # noqa: BLE001 -- a model miss is a clean skip, never a crash
        logger.debug("kbo_live_model.kbo_home_prob failed: %s", exc)
        return None


__all__ = ["kbo_home_prob"]
