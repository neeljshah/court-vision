"""scripts.platformkit.data_infra — shared, sport-blind leak-free walk-forward AS-OF engine.

LEAK-FREE CONTRACT: ``walk_forward_asof`` is the single canonical snapshot-before-update
trailing-aggregate implementation.  For each row (in chronological mergesort order), the
emitted ``<col>_asof`` is the expanding mean of the entity's STRICTLY-PRIOR rows — the
current row never sees its own values.  NaN when n_prior <= min_prior.

COMMON PATTERN EXTRACTED FROM 4 DOMAIN asof_features.py FILES
--------------------------------------------------------------
1. Chronological stable sort by (date, tiebreaker) using mergesort.
2. Per-entity running accumulators: plain Python dicts {entity → (sum, count)}.
3. Snapshot-BEFORE-update: read prior state → emit → push current into acc.
4. NaN when n_prior == 0 (no fabricated prior, no fill).
5. event_id: deterministic string from domain parts joined with "_".
6. Sidecar join: 1:1 left merge on event_id; no row inflation.

Deviations per domain (intentionally left to adapters):
- NBA: multi-stat ratios (ast/fgm) computed from sum/sum, not mean-of-means.
- Tennis: player appears in p1 or p2 slot → adapter maps both slots.
- Soccer: _TeamHistory with deque(maxlen=N) for rolling; last_n covers this generically.
- MLB: outcome lookup (runs-allowed proxy) before the walk → adapter concern.

PURE pandas/numpy.  No src.* / kernel.* / domain imports.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["walk_forward_asof", "make_event_id", "join_asof_sidecar"]


def walk_forward_asof(
    df: pd.DataFrame,
    *,
    date_col: str,
    entity_cols: Sequence[str],
    value_cols: Sequence[str],
    last_n: Optional[int] = None,
    min_prior: int = 0,
) -> pd.DataFrame:
    """Snapshot-before-update trailing-aggregate engine (leak-free).

    Emits per row: ``n_prior``, ``<col>_asof`` (expanding mean of strictly-prior
    rows), and optionally ``<col>_l{last_n}`` (mean of the last *last_n* prior
    values, matching soccer's deque window).  NaN when ``n_prior <= min_prior``.
    Rows are returned in mergesort-stable chronological order by ``date_col``.
    Non-finite values in a source cell are skipped for that column's sum/count
    but still increment ``n_prior``.
    """
    value_cols = list(value_cols)
    entity_cols = list(entity_cols)

    work = df.copy()
    work["_dk"] = pd.to_datetime(work[date_col])
    work = work.sort_values("_dk", kind="mergesort").reset_index(drop=True)
    work = work.drop(columns=["_dk"])
    n_rows = len(work)

    if len(entity_cols) == 1:
        entity_keys = work[entity_cols[0]].astype(str).to_numpy()
    else:
        entity_keys = work[entity_cols].astype(str).agg("|".join, axis=1).to_numpy()

    val_arrays: Dict[str, np.ndarray] = {
        col: pd.to_numeric(work[col], errors="coerce").to_numpy(dtype="float64")
        for col in value_cols
    }

    acc_sum: Dict[str, Dict[str, float]] = {}
    acc_cnt: Dict[str, Dict[str, int]] = {}
    acc_n: Dict[str, int] = {}
    acc_win: Dict[str, Dict[str, deque]] = {}

    out_n: List[int] = []
    out_asof: Dict[str, List[float]] = {col: [] for col in value_cols}
    out_last: Dict[str, List[float]] = (
        {col: [] for col in value_cols} if last_n is not None else {}
    )

    for i in range(n_rows):
        ek = entity_keys[i]
        prior_n = acc_n.get(ek, 0)
        out_n.append(prior_n)

        col_sums = acc_sum.get(ek, {})
        col_cnts = acc_cnt.get(ek, {})
        col_wins = acc_win.get(ek, {}) if last_n is not None else {}

        for col in value_cols:
            if prior_n <= min_prior:
                out_asof[col].append(np.nan)
            else:
                c = col_cnts.get(col, 0)
                out_asof[col].append(col_sums[col] / c if c > 0 else np.nan)

            if last_n is not None:
                win = col_wins.get(col)
                out_last[col].append(
                    float(sum(win) / len(win)) if win else np.nan
                )

        # UPDATE after snapshot — current row enters the accumulator.
        if ek not in acc_sum:
            acc_sum[ek] = {}
            acc_cnt[ek] = {}
        if last_n is not None and ek not in acc_win:
            acc_win[ek] = {}

        for col in value_cols:
            v = val_arrays[col][i]
            if np.isfinite(v):
                acc_sum[ek][col] = acc_sum[ek].get(col, 0.0) + v
                acc_cnt[ek][col] = acc_cnt[ek].get(col, 0) + 1
                if last_n is not None:
                    if col not in acc_win[ek]:
                        acc_win[ek][col] = deque(maxlen=last_n)
                    acc_win[ek][col].append(v)

        acc_n[ek] = prior_n + 1

    work["n_prior"] = out_n
    for col in value_cols:
        work[f"{col}_asof"] = out_asof[col]
    if last_n is not None:
        for col in value_cols:
            work[f"{col}_l{last_n}"] = out_last[col]

    return work


def make_event_id(
    df: pd.DataFrame,
    parts: Sequence[str],
    *,
    date_col: Optional[str] = None,
    date_fmt: str = "%Y%m%d",
) -> pd.Series:
    """Deterministic event id from column parts, joined with ``_``.

    When ``date_col`` is given the formatted date is prepended as the first
    segment.  Mirrors the domain convention: ``"{date}_{home}_{away}"``.
    """
    segments: List[pd.Series] = []
    if date_col is not None:
        segments.append(pd.to_datetime(df[date_col]).dt.strftime(date_fmt))
    for col in parts:
        segments.append(df[col].astype(str))
    if not segments:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    result = segments[0].copy()
    for seg in segments[1:]:
        result = result + "_" + seg
    return result


def join_asof_sidecar(
    spine: pd.DataFrame,
    sidecar: pd.DataFrame,
    key: str,
) -> pd.DataFrame:
    """Left-join sidecar's ``*_asof`` columns onto the spine 1:1 by ``key``.

    Raises ``ValueError`` if the sidecar has duplicate ``key`` values (which
    would inflate the spine row count).  Asserts the result has len(spine) rows.
    """
    if sidecar[key].duplicated().any():
        dupes = sidecar.loc[sidecar[key].duplicated(keep=False), key].unique().tolist()
        raise ValueError(
            f"join_asof_sidecar: sidecar has duplicate '{key}' values — "
            f"would inflate spine rows.  Duplicates: {dupes[:5]}"
        )
    result = spine.merge(sidecar, on=key, how="left")
    if len(result) != len(spine):
        raise AssertionError(
            f"join_asof_sidecar: row count changed "
            f"({len(spine)} → {len(result)})."
        )
    return result
