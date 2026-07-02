"""scripts.platformkit.ingame.ingame_baseout_mlb -- DEEP in-game state for MLB.

The in-game capture currently records only score + inning/half (a shallow state).
The live ESPN event carries far more in its ``situation`` block -- OUTS, the COUNT
(balls/strikes), and the BASERUNNERS -- the classic high-signal in-game variables a
score+inning summary throws away.  This module extracts that base-out state, leak-free,
from a live event and derives a standard RUN-EXPECTANCY (RE24) feature, so every captured
tick can carry it and the data gets DEEP + keeps accumulating.

WHY base-out / RE24: a runner on 2nd with 0 outs vs bases-empty 2 outs price the same
score very differently; RE24 is the standard, public, leak-free encoding of that.  This is
a DESCRIPTIVE state feature for the in-game model to later be GATED on -- NOT an edge claim
and NOT wired into the gated live model here (that needs human sign-off).  Calibration only.

RE24 = mean runs scored from each (base-state, outs) to end of half-inning.  The table is a
standard published MLB base-out run-expectancy matrix (~2010-2015 league averages); it is a
fixed constant, not fit on our data.  base_state is a 3-bit mask (bit0=1st, bit1=2nd,
bit2=3rd); base_out_state in [0,23] = base_state*3 + outs.

Leak-free / honest: reads only the CURRENT live situation (no future info); returns {} when
the situation is absent (pregame / between-pitch gaps); never raises; ASCII; no src/kernel
imports.  Pure parsing + a constant table.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Standard published base-out RUN EXPECTANCY (RE24), runs to end of half-inning.
# Rows indexed by base_state (3-bit mask bit0=1st,bit1=2nd,bit2=3rd); cols by outs 0/1/2.
_RE24 = {
    0: (0.481, 0.254, 0.098),   # --- bases empty
    1: (0.859, 0.509, 0.224),   # 1-- runner on 1st
    2: (1.100, 0.664, 0.319),   # -2- runner on 2nd
    3: (1.437, 0.884, 0.429),   # 12- 1st & 2nd
    4: (1.350, 0.950, 0.353),   # --3 runner on 3rd
    5: (1.784, 1.130, 0.478),   # 1-3 1st & 3rd
    6: (1.964, 1.376, 0.580),   # -23 2nd & 3rd
    7: (2.292, 1.541, 0.752),   # 123 bases loaded
}

_BASE_LABEL = {0: "---", 1: "1--", 2: "-2-", 3: "12-",
               4: "--3", 5: "1-3", 6: "-23", 7: "123"}


def _truthy_base(v: Any) -> bool:
    """ESPN marks an occupied base as True or as a runner/athlete object; empty as
    False/None/absent.  Treat any non-empty, non-False value as occupied."""
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() not in ("", "false", "0", "none")
    return bool(v)   # dict/list (a runner object) -> occupied


def _situation(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Locate the live situation block (top-level or under competitions[0])."""
    if not isinstance(ev, dict):
        return {}
    sit = ev.get("situation")
    if isinstance(sit, dict) and sit:
        return sit
    comps = ev.get("competitions")
    if isinstance(comps, list) and comps and isinstance(comps[0], dict):
        s = comps[0].get("situation")
        if isinstance(s, dict):
            return s
    return {}


def parse_baseout(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the deep MLB base-out state from a live event.

    Returns {} when the situation/outs are unavailable (honest: no fabricated state).
    On success: {outs, balls, strikes, on_first, on_second, on_third, base_state,
    base_label, base_out_state, run_expectancy}.  RE is the standard RE24 lookup.
    """
    sit = _situation(ev)
    if not sit:
        return {}
    outs = sit.get("outs")
    try:
        outs = int(outs)
    except (TypeError, ValueError):
        return {}                      # no usable out-count -> not a real base-out tick
    if outs < 0 or outs > 2:           # 3 outs = inning over (transient); skip
        return {}
    on1 = _truthy_base(sit.get("onFirst"))
    on2 = _truthy_base(sit.get("onSecond"))
    on3 = _truthy_base(sit.get("onThird"))
    base_state = (1 if on1 else 0) | (2 if on2 else 0) | (4 if on3 else 0)
    re = _RE24[base_state][outs]
    out: Dict[str, Any] = {
        "outs": outs,
        "on_first": on1, "on_second": on2, "on_third": on3,
        "base_state": base_state, "base_label": _BASE_LABEL[base_state],
        "base_out_state": base_state * 3 + outs,
        "run_expectancy": round(re, 3),
    }
    for k in ("balls", "strikes"):
        try:
            out[k] = int(sit.get(k))
        except (TypeError, ValueError):
            pass
    return out


def baseout_summary_fields(sport: str, ev: Dict[str, Any]) -> Dict[str, Any]:
    """ADDITIVE state_summary fields for MLB ticks (else {}).  Compact keys so the
    captured state_summary stays small while carrying the deep variables: outs, base
    (0-7), bos (base_out_state 0-23), re (run expectancy)."""
    if str(sport).lower() != "mlb":
        return {}
    bo = parse_baseout(ev)
    if not bo:
        return {}
    out = {"outs": bo["outs"], "base": bo["base_state"],
           "bos": bo["base_out_state"], "re": bo["run_expectancy"]}
    if "balls" in bo and "strikes" in bo:
        out["count"] = "%d-%d" % (bo["balls"], bo["strikes"])
    return out


__all__ = ["parse_baseout", "baseout_summary_fields"]
