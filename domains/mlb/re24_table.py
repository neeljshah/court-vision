"""domains.mlb.re24_table -- STATIC RE24 run-expectancy table + leverage rule.

MUST-FIX #8: this is a PINNED PUBLISHED CONSTANT, never a runtime / test-season fit.
The RE24 matrix below is the classic 24-state base-out run-expectancy table from
Tango, Lichtman & Dolphin, "The Book: Playing the Percentages in Baseball" (2007),
estimated on MLB seasons 1999-2002. Those estimation seasons are DISJOINT from the
in-game gate corpora (2022 and 2023), so using this table to feature-ize a 2022/2023
at-bat introduces NO future leak: the numbers were fixed years before either gate
season and depend on NO data from them.

The values are expected runs scored by the batting team from that base-out state
through the end of the half-inning. The KEY is (runners_bitmask, outs) where the
bitmask is bit2=1B bit1=2B bit0=3B (identical to ingest_states.py:18-19), and outs
in {0,1,2} (the as-of outs FACING the batter; a 3rd out ends the half-inning).

There is NO pandas/numpy import and NO file/network read here -- the table is a
module-level dict literal. The companion test asserts:
  * RE24 has exactly 24 entries (8 base states x 3 out states),
  * no value is data-derived at import/call time (pure dict lookup),
  * the estimation-season docstring constant is disjoint from the gate seasons.

ASCII only.  <=300 LOC.  No src/kernel/api imports.  No $ -- this is run expectancy,
a descriptive baseball quantity, never a market edge.
"""
from __future__ import annotations

from typing import Dict, Tuple

# Estimation provenance (PINNED -- asserted disjoint from gate seasons by the test).
RE24_SOURCE = "Tango-Lichtman-Dolphin 'The Book' (2007), MLB 1999-2002"
RE24_ESTIMATION_SEASONS: Tuple[int, ...] = (1999, 2000, 2001, 2002)

# Bitmask helpers (documentation-only; the table is keyed by the raw bitmask int).
#   bit2 = runner on 1B, bit1 = runner on 2B, bit0 = runner on 3B
#   0 = bases empty ... 7 = bases loaded
_EMPTY = 0
_1B = 4
_2B = 2
_3B = 1
_1B_2B = _1B | _2B          # 6
_1B_3B = _1B | _3B          # 5
_2B_3B = _2B | _3B          # 3
_LOADED = _1B | _2B | _3B   # 7

# STATIC published RE24 matrix: {(runners_bitmask, outs): expected_runs}.
# Source: "The Book" (1999-2002). Values pinned, NOT computed.
RE24: Dict[Tuple[int, int], float] = {
    (_EMPTY, 0): 0.555, (_EMPTY, 1): 0.297, (_EMPTY, 2): 0.117,
    (_1B, 0): 0.953, (_1B, 1): 0.573, (_1B, 2): 0.251,
    (_2B, 0): 1.189, (_2B, 1): 0.725, (_2B, 2): 0.344,
    (_3B, 0): 1.482, (_3B, 1): 0.983, (_3B, 2): 0.387,
    (_1B_2B, 0): 1.573, (_1B_2B, 1): 0.971, (_1B_2B, 2): 0.466,
    (_1B_3B, 0): 1.904, (_1B_3B, 1): 1.243, (_1B_3B, 2): 0.538,
    (_2B_3B, 0): 2.052, (_2B_3B, 1): 1.467, (_2B_3B, 2): 0.634,
    (_LOADED, 0): 2.417, (_LOADED, 1): 1.650, (_LOADED, 2): 0.815,
}


def base_run_value(runners: int, outs: int) -> float:
    """Pure static lookup of expected runs for a base-out state.

    runners: bitmask bit2=1B bit1=2B bit0=3B (0..7). outs: 0,1,2.
    Returns 0.0 for an out-of-range/unknown state (e.g. outs=3 or -1) -- a neutral,
    non-fabricated default, never a data-derived number. NO runtime estimation.
    """
    key = (int(runners) & 0b111, int(outs))
    return RE24.get(key, 0.0)


def leverage_bucket(inning: int, state_diff: float, runners: int, outs: int) -> str:
    """STATIC rule mapping (inning, margin, base-out) -> {low, mid, high}.

    A hand-specified leverage proxy -- NEVER future-fit. The idea: leverage rises late
    in close games, especially with runners on and few outs. The thresholds are fixed
    constants, not learned from any season.

    Rules (evaluated in order):
      * Blowout (|margin| >= 5) at any time -> low (outcome ~ decided).
      * Late (inning >= 7) AND close (|margin| <= 2) AND runners on base -> high.
      * Late (inning >= 7) AND close (|margin| <= 2) -> mid.
      * Runners in scoring position (2B or 3B occupied) with <2 outs, margin<=3 -> mid.
      * Otherwise -> low.
    """
    margin = abs(float(state_diff))
    risp = bool((int(runners) & _2B) or (int(runners) & _3B))
    on_base = bool(int(runners) & 0b111)
    if margin >= 5.0:
        return "low"
    if int(inning) >= 7 and margin <= 2.0:
        return "high" if on_base else "mid"
    if risp and int(outs) < 2 and margin <= 3.0:
        return "mid"
    return "low"
