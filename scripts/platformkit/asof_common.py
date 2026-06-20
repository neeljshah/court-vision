"""scripts.platformkit.asof_common -- one hardened leak-free walk-forward primitive.

Extracts the snapshot-before-update pattern duplicated across every
domains/<sport>/asof_*.py builder (tennis asof_hold, mlb asof_sp_form, ...):

  1. sort events into a stable chronological order (mergesort-stable, multi-key),
  2. for each event, SNAPSHOT every entity's prior-only state and record it,
  3. only AFTER all snapshots in that event, UPDATE each entity's state with the
     event's realized observation.

State is keyed by the GLOBAL entity id, shared across slots, so a player/pitcher
that appears as p1 in one game and p2 in another accumulates one history (this is
what the existing per-sport builders do). Debut entities snapshot to NaN. A
no-future-leak assertion (debut row => NaN) is built in.

Accumulators provided: ExpandingMean (asof_hold-style), EWMean (asof_sp_form-style).
Both are pure. Callers can pass any object implementing the Accumulator protocol.

LEAK CONTRACT: snapshot strictly precedes update; an entity never sees its own
current event. A null entity id in a slot emits NaN and does not update.

PURE pandas/numpy. No src/kernel/api/domain imports. ASCII only.
ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, Sequence

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Accumulator protocol + two pure implementations
# --------------------------------------------------------------------------- #
class Accumulator(Protocol):
    """Per-entity running state. ``n`` counts prior appearances (update calls)."""

    n: int

    def snapshot(self) -> float:
        """Prior-only value, or NaN if insufficient history."""

    def update(self, obs: float) -> None:
        """Fold one realized observation in AFTER the snapshot was taken."""


class ExpandingMean:
    """Expanding (career) mean. ``n`` = appearances; NaN obs bump n but not the mean.

    Mirrors domains.tennis.asof_hold._PlayerHistory: the running mean is over
    non-NaN observations, while ``n`` counts every appearance. ``min_prior`` forces
    NaN until at least that many appearances have accrued (default 0 = emit as soon
    as one valid observation exists).
    """

    __slots__ = ("n", "_sum", "_cnt", "_min_prior")

    def __init__(self, min_prior: int = 0) -> None:
        self.n: int = 0
        self._sum: float = 0.0
        self._cnt: int = 0
        self._min_prior: int = int(min_prior)

    def snapshot(self) -> float:
        if self.n < self._min_prior or self._cnt == 0:
            return float("nan")
        return self._sum / self._cnt

    def update(self, obs: float) -> None:
        self.n += 1
        if obs is not None and not (isinstance(obs, float) and np.isnan(obs)):
            self._sum += float(obs)
            self._cnt += 1


class EWMean:
    """Exponential-weighted trailing mean (recency-weighted).

    Mirrors domains.mlb.asof_sp_form._EWState: ``ew_new = (1-alpha)*ew_old +
    alpha*obs``; first observation initialises exactly. ``min_prior`` gates the
    snapshot to NaN until enough observations accrue. NaN obs are ignored (no n bump),
    matching the sp_form convention where an unparseable start is simply not folded in.
    """

    __slots__ = ("n", "_ew", "_alpha", "_min_prior")

    def __init__(self, alpha: float, min_prior: int = 0) -> None:
        if not 0.0 < float(alpha) <= 1.0:
            raise ValueError(f"alpha must be in (0, 1], got {alpha!r}")
        self.n: int = 0
        self._ew: Optional[float] = None
        self._alpha: float = float(alpha)
        self._min_prior: int = int(min_prior)

    def snapshot(self) -> float:
        if self.n < self._min_prior or self._ew is None:
            return float("nan")
        return self._ew

    def update(self, obs: float) -> None:
        if obs is None or (isinstance(obs, float) and np.isnan(obs)):
            return
        if self._ew is None:
            self._ew = float(obs)
        else:
            self._ew = (1.0 - self._alpha) * self._ew + self._alpha * float(obs)
        self.n += 1


# --------------------------------------------------------------------------- #
# Spec + stable chronological order
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AsofSpec:
    """Declarative spec for one walk-forward pass.

    sort_keys   : columns defining the stable chronological order (date first).
    slots       : per output slot, the (id_col, obs_col, out_prefix) triple. Both
                  slots that name the same entity id share one accumulator.
    id_col      : event identifier carried through to the output (default event_id).
    """

    sort_keys: Sequence[str]
    slots: Sequence[tuple]  # each: (id_col, obs_col, out_prefix)
    id_col: str = "event_id"


def stable_chrono_order(df: pd.DataFrame, sort_keys: Sequence[str]) -> pd.DataFrame:
    """Return ``df`` in mergesort-stable order on ``sort_keys`` (datelike key 0 parsed).

    Missing key columns are treated as a constant blank so the sort is total and
    deterministic regardless of which optional tiebreak columns a corpus carries.
    """
    n = len(df)
    cols: dict[str, np.ndarray] = {}
    for j, key in enumerate(sort_keys):
        if key in df.columns:
            series = df[key]
        else:
            series = pd.Series([""] * n, index=df.index)
        if j == 0:
            cols[f"k{j}"] = pd.to_datetime(series, errors="coerce").values
        else:
            cols[f"k{j}"] = series.astype(str).values
    key_df = pd.DataFrame(cols, index=df.index)
    order = key_df.sort_values(list(cols.keys()), kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# The walk-forward primitive
# --------------------------------------------------------------------------- #
def _is_null(v: object) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def walk_forward_asof(
    events: pd.DataFrame,
    spec: AsofSpec,
    accumulator_factory: Callable[[], Accumulator],
) -> pd.DataFrame:
    """Run a leak-free as-of pass; return one row per event.

    Output columns: ``spec.id_col`` plus, for each slot, ``<out_prefix>_asof`` and
    ``<out_prefix>_n_prior`` (int). A null entity id in a slot yields NaN / 0 and
    does not update state. State is keyed by entity id and SHARED across slots.
    """
    ordered = stable_chrono_order(events, spec.sort_keys)
    n = len(ordered)
    states: dict[object, Accumulator] = {}

    id_out = ordered[spec.id_col].tolist()
    slot_ids = [ordered[id_col].tolist() for (id_col, _o, _p) in spec.slots]
    slot_obs = [ordered[obs_col].tolist() for (_i, obs_col, _p) in spec.slots]
    asof_cols: list[list[float]] = [[] for _ in spec.slots]
    nprior_cols: list[list[int]] = [[] for _ in spec.slots]

    for i in range(n):
        # SNAPSHOT phase -- prior-only, before any update for this event.
        for s in range(len(spec.slots)):
            eid = slot_ids[s][i]
            if _is_null(eid):
                asof_cols[s].append(float("nan"))
                nprior_cols[s].append(0)
                continue
            acc = states.get(eid)
            if acc is None:
                acc = accumulator_factory()
                states[eid] = acc
            asof_cols[s].append(acc.snapshot())
            nprior_cols[s].append(int(acc.n))
        # UPDATE phase -- only after every slot in this event was snapshotted.
        for s in range(len(spec.slots)):
            eid = slot_ids[s][i]
            if _is_null(eid):
                continue
            states[eid].update(slot_obs[s][i])

    out: dict[str, object] = {spec.id_col: id_out}
    for s, (_i, _o, prefix) in enumerate(spec.slots):
        out[f"{prefix}_asof"] = np.asarray(asof_cols[s], dtype="float64")
        out[f"{prefix}_n_prior"] = np.asarray(nprior_cols[s], dtype="int64")
    result = pd.DataFrame(out)
    assert_no_future_leak(result, [p for (_i, _o, p) in spec.slots])
    return result


def assert_no_future_leak(df: pd.DataFrame, prefixes: Sequence[str]) -> None:
    """Raise AssertionError if any debut row (n_prior == 0) has a non-NaN as-of value."""
    for prefix in prefixes:
        a = df[f"{prefix}_asof"]
        np_ = df[f"{prefix}_n_prior"]
        bad = int(((np_ == 0) & a.notna()).sum())
        if bad > 0:
            raise AssertionError(
                f"Future-leak: {bad} debut rows (n_prior==0) with non-NaN {prefix}_asof."
            )
