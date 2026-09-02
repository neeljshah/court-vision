"""scripts.platformkit.eval_gate.asof_join -- one backward as-of join with a staleness rail.

THE DEFECT IT EXISTS FOR (S99, 2026-09-03): a joined-store state series stops when the
capture stops, but the price series runs to settlement, so a bare
`pd.merge_asof(direction="backward")` silently carried a 2-HOUR-STALE score forward onto
every later tick. S99's MLB moneyline Brier read 0.3234 that way and 0.201034 once a 300 s
tolerance was applied. `pd.merge_asof(tolerance=)` nulls those rows but tells you NOTHING
about how many it nulled, so a corpus can lose most of its ticks in silence.

This helper is that join plus the number: the SAME null set as `tolerance=`, and the share
of ticks whose state was too stale (or absent) to use. Missing state is nulled and the tick
is passed on to the caller's own dropna -- never guessed, never carried forward (B3).

Per-file test: python -m pytest tests/platformkit/eval_gate/test_asof_join.py -q
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


def asof_join_state(ticks: pd.DataFrame, states: pd.DataFrame, key: str = "ts",
                    max_staleness_s: float = 300.0) -> Tuple[pd.DataFrame, float]:
    """Backward as-of join of `states` onto `ticks` on `key`, nulling state older than
    `max_staleness_s`.

    Returns (merged, stale_share). `stale_share` is the fraction of tick rows carrying no
    usable state -- either no earlier state row at all, or one further back than the rail.
    The null set is byte-identical to `pd.merge_asof(..., tolerance=max_staleness_s)`; the
    join is done without the tolerance only so the lag stays observable.

    `key` must be numeric (epoch seconds is what every caller here uses).
    ponytail: no forward/nearest direction and no `by=` grouping -- add when a caller needs one.
    """
    state_cols = [c for c in states.columns if c != key]
    ticks = ticks.sort_values(key, kind="stable")
    states = states.sort_values(key, kind="stable")
    merged = pd.merge_asof(ticks, states.assign(_state_ts=states[key].to_numpy()),
                           on=key, direction="backward")
    lag = merged[key] - merged["_state_ts"]
    stale = lag.isna() | (lag > max_staleness_s)
    if stale.any() and state_cols:
        merged.loc[stale, state_cols] = np.nan
    merged = merged.drop(columns=["_state_ts"])
    return merged, float(stale.mean()) if len(merged) else 0.0
