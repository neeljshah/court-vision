"""S124/S125 -- the in-game tier's leak guards, split out of `ingame_screen` for the LOC rail.

TICK-TIME AS-OF (S82's rule, unchanged): `assert_tick_asof` rebuilds the table from the causal
prefix src[:k+1] and requires row k to equal row k of the full build, so a feature that peeks
at a LATER tick raises TickTimeLeak.  `ingame_screen` re-exports it, so every existing import
site (`ingame_screen_nba`, `ingame_screen_soccer`, `run_ingame_screen`, the grammar tests)
keeps working unchanged (A5/B6).

LABEL BLINDNESS (S124, added 2026-09-03): truncation invariance CANNOT see a SAME-TICK leak.
A feature reading its own tick's label is invariant under src[:k+1], so it passed the guard and
then scored improvement_vs_null +0.598900, CI [+0.58464,+0.61316], clears_bar True on the
reproduction probe.  `assert_label_blind` rebuilds with every label column PERMUTED (a fixed
half-length roll -- a derangement, not a random draw) and requires every feature column to be
unchanged over ALL rows, not a probe sample.  Where no label is reachable from `src` -- the
S82/S102/S114 production path, whose `causal_source` frame carries game/timestamp/
state_summary/_row_id only -- it reports the empty list and changes nothing, so those archives
reproduce byte-identically; a caller holding the labels passes them as `labels=`.

UTC STAMPS (S125): `utc_stamps` parses tick stamps ONCE to tz-aware UTC.  String ordering is
not a time ordering -- ' ' (0x20) sorts before 'T' (0x54), so a space-separated stamp read as
EARLIER than an ISO-Z embargo cut and admitted a train game that settled 2 h before the fold
(n_train 8 where 0 is correct), and both purge asserts passed because they shared the broken
ordering.

A SCREEN IS A NON-FINDING: no ledger row, no prereg seal, no charge.  Calibration language
only.  ASCII only.
Per-file test: python -m pytest tests/platformkit/foundry/test_ingame_guards.py -q
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

import numpy as np
import pandas as pd

# A column with any of these names carries the tick's OUTCOME and no feature may read it.
LABEL_COLUMNS = ("outcome", "y", "label", "settled", "result", "won")
_KEYS = ("game", "timestamp", "_row_id")


class TickTimeLeak(AssertionError):
    """A feature changed when a later tick -- or the tick's own label -- was withheld."""


def utc_stamps(values: Any) -> pd.Series:
    """Tick stamps as tz-aware UTC datetimes, index preserved (S125)."""
    series = values if isinstance(values, pd.Series) else pd.Series(list(values))
    out = pd.to_datetime(series, utc=True, format="mixed")
    assert str(out.dtype) == "datetime64[ns, UTC]", (
        "tick stamps did not parse to UTC datetimes: %s" % out.dtype)
    return out


def _relabelled(src: pd.DataFrame, labels: Optional[Sequence[Any]]):
    """(base frame, the same frame with every label column permuted, those column names).

    The base carries `labels` too, so BOTH builds see the same columns and only the label
    VALUES differ. `permuted` is None when no label is reachable -- nothing to check."""
    base = src if labels is None else src.assign(outcome=list(labels))
    columns = [c for c in LABEL_COLUMNS if c in base.columns]
    if not columns or len(base) < 2:
        return base, None, columns
    frame = base.copy()
    for column in columns:
        values = base[column].to_numpy()
        for seed in range(8):    # a permutation of a periodic label can be value-identical
            shuffled = values[np.random.default_rng(seed).permutation(len(values))]
            if (shuffled != values).any():
                break
        frame[column] = shuffled
    if all(base[c].equals(frame[c]) for c in columns):
        return base, None, columns          # every label column is constant: nothing to leak
    return base, frame, columns


def assert_label_blind(src: pd.DataFrame, builder: Callable[[pd.DataFrame], pd.DataFrame],
                       labels: Optional[Sequence[Any]] = None) -> List[str]:
    """Every feature column must be UNCHANGED when the tick's own label is permuted (S124).

    Returns the label columns it permuted -- an EMPTY list means no label was reachable from
    `src` and nothing was checked, which is honest, not a pass."""
    base, permuted, columns = _relabelled(src, labels)
    if permuted is None:
        return []
    full, other = builder(base), builder(permuted)
    for column in [c for c in full.columns if c not in _KEYS]:
        left = full[column].reset_index(drop=True)
        right = other[column].reset_index(drop=True)
        if not left.equals(right):
            raise TickTimeLeak(
                "%s changed on %d of %d rows when the label columns %s were permuted: it reads "
                "its own tick's label" % (column, int((left != right).sum()), len(left), columns))
    return columns


def assert_tick_asof(src: pd.DataFrame, builder: Callable[[pd.DataFrame], pd.DataFrame],
                     probes: int = 8, labels: Optional[Sequence[Any]] = None) -> List[int]:
    """Truncation invariance at EVENLY spaced probe rows (A3), THEN label blindness (S124)."""
    full = builder(src)
    columns = [c for c in full.columns if c not in _KEYS]
    step, checked = max(1, len(src) // (probes + 1)), []
    for k in range(step, len(src), step):
        if len(checked) >= probes:
            break
        row, want = builder(src.iloc[:k + 1]).iloc[k][columns], full.iloc[k][columns]
        for column in columns:
            a, b = row[column], want[column]
            if not ((a != a and b != b) or a == b):
                raise TickTimeLeak("%s at row %d is %r on the causal prefix but %r on the full "
                                   "corpus: it reads an event later than its own tick"
                                   % (column, k, a, b))
        checked.append(k)
    assert_label_blind(src, builder, labels)
    return checked


__all__ = ["LABEL_COLUMNS", "TickTimeLeak", "assert_label_blind", "assert_tick_asof",
           "utc_stamps"]
