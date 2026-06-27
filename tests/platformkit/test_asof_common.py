"""Per-file tests for scripts.platformkit.asof_common.

Synthetic hand-computed goldens for the two accumulators and the walk-forward
primitive (shared per-entity state, snapshot-before-update, debut => NaN, leak
assertion), plus a GUARDED real-parquet equivalence against the live
tennis asof_hold.parquet (skipped if the corpus is absent).

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_asof_common.py -q
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.asof_common import (
    AsofSpec,
    EWMean,
    ExpandingMean,
    assert_no_future_leak,
    stable_chrono_order,
    walk_forward_asof,
)


# --------------------------------------------------------------------------- #
# Accumulators
# --------------------------------------------------------------------------- #
def test_expanding_mean_golden():
    m = ExpandingMean()
    assert np.isnan(m.snapshot()) and m.n == 0
    m.update(2.0)
    assert m.n == 1 and m.snapshot() == pytest.approx(2.0)
    m.update(4.0)
    assert m.n == 2 and m.snapshot() == pytest.approx(3.0)
    m.update(float("nan"))  # NaN obs bumps appearances but not the mean
    assert m.n == 3 and m.snapshot() == pytest.approx(3.0)


def test_expanding_mean_min_prior_gate():
    m = ExpandingMean(min_prior=2)
    m.update(5.0)
    assert np.isnan(m.snapshot())  # n=1 < min_prior
    m.update(5.0)
    assert m.snapshot() == pytest.approx(5.0)


def test_ew_mean_golden():
    e = EWMean(alpha=0.5)
    assert np.isnan(e.snapshot())
    e.update(2.0)
    assert e.snapshot() == pytest.approx(2.0) and e.n == 1
    e.update(4.0)
    assert e.snapshot() == pytest.approx(3.0) and e.n == 2  # 0.5*2 + 0.5*4
    e.update(float("nan"))  # ignored entirely for EW
    assert e.snapshot() == pytest.approx(3.0) and e.n == 2


def test_ew_mean_min_prior_and_bad_alpha():
    e = EWMean(alpha=0.5, min_prior=3)
    e.update(1.0)
    e.update(2.0)
    assert np.isnan(e.snapshot())  # n=2 < 3
    e.update(3.0)
    assert not np.isnan(e.snapshot())
    with pytest.raises(ValueError):
        EWMean(alpha=0.0)
    with pytest.raises(ValueError):
        EWMean(alpha=1.5)


# --------------------------------------------------------------------------- #
# stable_chrono_order
# --------------------------------------------------------------------------- #
def test_stable_chrono_order_sorts_by_date_and_is_stable():
    df = pd.DataFrame({
        "date": ["2024-01-03", "2024-01-01", "2024-01-01", "2024-01-02"],
        "tag": ["a", "b", "c", "d"],  # b,c share a date -> input order preserved
    })
    out = stable_chrono_order(df, ["date", "tag_missing"])
    assert list(out["date"]) == ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03"]
    # same-date rows keep their original relative order (mergesort stability)
    assert list(out.loc[out["date"] == "2024-01-01", "tag"]) == ["b", "c"]


# --------------------------------------------------------------------------- #
# walk_forward_asof -- shared state across slots, snapshot-before-update
# --------------------------------------------------------------------------- #
def test_walk_forward_shared_state_and_leak_free():
    events = pd.DataFrame({
        "event_id": ["ev1", "ev2", "ev3"],
        "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "p1_id": ["A", "B", "A"],
        "p2_id": ["B", "C", "C"],
        "p1_obs": [10.0, 30.0, 50.0],
        "p2_obs": [20.0, 40.0, 60.0],
    })
    spec = AsofSpec(
        sort_keys=["date"],
        slots=[("p1_id", "p1_obs", "p1_hold"), ("p2_id", "p2_obs", "p2_hold")],
    )
    out = walk_forward_asof(events, spec, ExpandingMean).set_index("event_id")

    # ev1: both debut -> NaN / n_prior 0
    assert np.isnan(out.loc["ev1", "p1_hold_asof"])
    assert np.isnan(out.loc["ev1", "p2_hold_asof"])
    assert out.loc["ev1", "p1_hold_n_prior"] == 0
    # ev2 p1 = B, whose only prior obs (as p2 in ev1) was 20 -> SHARED history
    assert out.loc["ev2", "p1_hold_asof"] == pytest.approx(20.0)
    assert out.loc["ev2", "p1_hold_n_prior"] == 1
    assert np.isnan(out.loc["ev2", "p2_hold_asof"])  # C debut
    # ev3 p1 = A (prior obs 10), p2 = C (prior obs 40 from ev2)
    assert out.loc["ev3", "p1_hold_asof"] == pytest.approx(10.0)
    assert out.loc["ev3", "p2_hold_asof"] == pytest.approx(40.0)
    assert out.loc["ev3", "p2_hold_n_prior"] == 1


def test_null_entity_emits_nan_and_does_not_update():
    events = pd.DataFrame({
        "event_id": ["ev1", "ev2"],
        "date": ["2024-01-01", "2024-01-02"],
        "h_id": [None, "X"],
        "h_obs": [9.0, 1.0],
    })
    spec = AsofSpec(sort_keys=["date"], slots=[("h_id", "h_obs", "h")])
    out = walk_forward_asof(events, spec, ExpandingMean).set_index("event_id")
    assert np.isnan(out.loc["ev1", "h_asof"]) and out.loc["ev1", "h_n_prior"] == 0
    # ev1 had a null id so X has no prior history at ev2 -> still debut
    assert np.isnan(out.loc["ev2", "h_asof"]) and out.loc["ev2", "h_n_prior"] == 0


def test_assert_no_future_leak_fires():
    bad = pd.DataFrame({
        "event_id": ["e1"],
        "p1_asof": [0.5],          # non-NaN value...
        "p1_n_prior": [0],         # ...on a debut row -> leak
    })
    with pytest.raises(AssertionError, match="Future-leak"):
        assert_no_future_leak(bad, ["p1"])


# --------------------------------------------------------------------------- #
# GUARDED real-parquet equivalence vs live tennis asof_hold.parquet
# --------------------------------------------------------------------------- #
def test_equivalence_vs_tennis_asof_hold():
    """Primitive reproduces asof_hold's overall p1/p2 hold% on real data (head slice).

    As-of values depend only on PRIOR rows, so truncating the chronologically-sorted
    spine to its head is leak-correct and fast. We pre-sort with the domain's own
    multi-key sorter, then drive walk_forward_asof with a date-only stable sort, so
    same-day ordering is preserved byte-for-byte against the live builder.
    """
    try:
        from domains.tennis.asof_hold import (  # noqa: PLC0415
            _MATCHES_DEFAULT,
            _MATCH_STATS_DEFAULT,
            _OUT_DEFAULT,
            _STATS_COLS,
            _derive_realized,
            _stable_chrono_sort,
        )
    except Exception:  # pragma: no cover - import guard
        pytest.skip("tennis asof_hold module unavailable")

    for p in (_MATCH_STATS_DEFAULT, _MATCHES_DEFAULT, _OUT_DEFAULT):
        if not os.path.exists(p):
            pytest.skip(f"corpus absent: {p}")

    ms = pd.read_parquet(_MATCH_STATS_DEFAULT)
    mt = pd.read_parquet(_MATCHES_DEFAULT)
    golden = pd.read_parquet(_OUT_DEFAULT)

    avail = [c for c in _STATS_COLS if c in ms.columns]
    ms_r = _derive_realized(ms[avail].copy())
    spine = mt[["event_id", "date", "tour", "tourney_id", "round", "match_num",
                "p1_id", "p2_id", "surface"]].merge(
        ms_r[["event_id", "p1_hold_realized", "p2_hold_realized"]],
        on="event_id", how="left",
    )
    spine = _stable_chrono_sort(spine)
    spine["p1_id"] = pd.to_numeric(spine["p1_id"], errors="coerce")
    spine["p2_id"] = pd.to_numeric(spine["p2_id"], errors="coerce")
    head = spine.head(1500).copy()

    spec = AsofSpec(
        sort_keys=["date"],  # date-only + stability preserves the pre-sort order
        slots=[("p1_id", "p1_hold_realized", "p1_hold"),
               ("p2_id", "p2_hold_realized", "p2_hold")],
    )
    got = walk_forward_asof(head, spec, ExpandingMean)

    cmp = got.merge(
        golden[["event_id", "p1_hold_pct_asof", "p2_hold_pct_asof"]],
        on="event_id", how="inner",
    )
    assert len(cmp) > 100, "too few overlapping rows to be a meaningful check"
    for got_col, gold_col in (("p1_hold_asof", "p1_hold_pct_asof"),
                              ("p2_hold_asof", "p2_hold_pct_asof")):
        a = cmp[got_col].to_numpy(dtype="float64")
        b = cmp[gold_col].to_numpy(dtype="float64")
        both = ~np.isnan(a) & ~np.isnan(b)
        assert both.sum() > 100
        np.testing.assert_allclose(a[both], b[both], rtol=0, atol=1e-9)
        # NaN pattern matches too (debut/insufficient identical)
        np.testing.assert_array_equal(np.isnan(a), np.isnan(b))
