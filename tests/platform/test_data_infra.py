"""tests.platform.test_data_infra — leak-free contract + equivalence tests.

14 tests (all synthetic, no disk I/O):
  1  test_leak_free_expanding_mean     — row i asof == mean of strictly-prior rows
  2  test_flip_future_no_change        — future row doesn't alter past asof values
  3  test_nan_when_zero_prior          — first appearance → NaN
  4  test_nan_when_min_prior_threshold — NaN while n_prior <= min_prior
  5  test_last_n_windowing             — last_n rolling window vs full expanding mean
  6  test_multi_entity_isolation       — two entities accumulate independently
  7  test_composite_entity_key         — entity_cols=[A,B] groups by (A,B) pair
  8  test_make_event_id_no_date        — deterministic id from parts only
  9  test_make_event_id_with_date      — date prefix prepended in YYYYMMDD
  10 test_make_event_id_deterministic  — same input → same output always
  11 test_join_asof_sidecar_left       — left join keeps all spine rows
  12 test_join_asof_sidecar_no_inflation — duplicate sidecar key → ValueError
  13 test_join_asof_sidecar_row_count  — result rows == spine rows
  14 test_equivalence_hand_computed    — walk_forward_asof matches hand-rolled loop
"""
from __future__ import annotations

import math
from typing import List

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.data_infra import (
    join_asof_sidecar,
    make_event_id,
    walk_forward_asof,
)


def _f(rows: list) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


# ── 1. Expanding mean correctness ──────────────────────────────────────────

def test_leak_free_expanding_mean():
    df = _f([
        {"date": "2024-01-01", "team": "A", "pts": 10.0},
        {"date": "2024-01-02", "team": "A", "pts": 20.0},
        {"date": "2024-01-03", "team": "A", "pts": 30.0},
        {"date": "2024-01-04", "team": "A", "pts": 40.0},
    ])
    out = walk_forward_asof(df, date_col="date", entity_cols=["team"], value_cols=["pts"])
    assert _nan(out.loc[0, "pts_asof"]) and out.loc[0, "n_prior"] == 0
    assert out.loc[1, "pts_asof"] == pytest.approx(10.0)
    assert out.loc[2, "pts_asof"] == pytest.approx(15.0)
    assert out.loc[3, "pts_asof"] == pytest.approx(20.0)


# ── 2. Flip future ─────────────────────────────────────────────────────────

def test_flip_future_no_change():
    base = [{"date": "2024-01-01", "team": "X", "v": 5.0},
            {"date": "2024-01-02", "team": "X", "v": 15.0}]
    out_b = walk_forward_asof(_f(base), date_col="date", entity_cols=["team"], value_cols=["v"])
    out_e = walk_forward_asof(
        _f(base + [{"date": "2024-01-10", "team": "X", "v": 999.0}]),
        date_col="date", entity_cols=["team"], value_cols=["v"],
    )
    assert _nan(out_b.loc[0, "v_asof"]) and _nan(out_e.loc[0, "v_asof"])
    assert out_b.loc[1, "v_asof"] == pytest.approx(out_e.loc[1, "v_asof"])


# ── 3. NaN on zero prior ───────────────────────────────────────────────────

def test_nan_when_zero_prior():
    df = _f([
        {"date": "2024-03-01", "p": "alice", "score": 7.0},
        {"date": "2024-03-01", "p": "bob",   "score": 3.0},
        {"date": "2024-03-02", "p": "alice", "score": 9.0},
    ])
    out = walk_forward_asof(df, date_col="date", entity_cols=["p"], value_cols=["score"])
    alice = out[out["p"] == "alice"].reset_index(drop=True)
    bob = out[out["p"] == "bob"].reset_index(drop=True)
    assert _nan(alice.loc[0, "score_asof"]) and alice.loc[0, "n_prior"] == 0
    assert _nan(bob.loc[0, "score_asof"])
    assert alice.loc[1, "score_asof"] == pytest.approx(7.0)


# ── 4. min_prior threshold ─────────────────────────────────────────────────

def test_nan_when_min_prior_threshold():
    df = _f([{"date": f"2024-01-0{i+1}", "e": "Z", "x": float(i * 10)} for i in range(5)])
    out = walk_forward_asof(
        df, date_col="date", entity_cols=["e"], value_cols=["x"], min_prior=2
    )
    assert _nan(out.loc[0, "x_asof"])   # n_prior=0
    assert _nan(out.loc[1, "x_asof"])   # n_prior=1
    assert _nan(out.loc[2, "x_asof"])   # n_prior=2 <= min_prior
    assert not _nan(out.loc[3, "x_asof"])  # n_prior=3 > 2


# ── 5. last_n windowing ────────────────────────────────────────────────────

def test_last_n_windowing():
    df = _f([
        {"date": "2024-01-01", "t": "T", "v": 10.0},
        {"date": "2024-01-02", "t": "T", "v": 20.0},
        {"date": "2024-01-03", "t": "T", "v": 30.0},
        {"date": "2024-01-04", "t": "T", "v": 40.0},
    ])
    out = walk_forward_asof(df, date_col="date", entity_cols=["t"], value_cols=["v"], last_n=2)
    assert "v_l2" in out.columns
    assert _nan(out.loc[0, "v_l2"])
    assert out.loc[1, "v_l2"] == pytest.approx(10.0)
    assert out.loc[2, "v_l2"] == pytest.approx(15.0)   # window=[10,20]
    assert out.loc[3, "v_l2"] == pytest.approx(25.0)   # window=[20,30] (10 evicted)
    assert out.loc[3, "v_asof"] == pytest.approx(20.0) # expanding mean still all-prior


# ── 6. Multi-entity isolation ──────────────────────────────────────────────

def test_multi_entity_isolation():
    df = _f([
        {"date": "2024-01-01", "team": "A", "pts": 100.0},
        {"date": "2024-01-01", "team": "B", "pts": 50.0},
        {"date": "2024-01-02", "team": "A", "pts": 80.0},
        {"date": "2024-01-02", "team": "B", "pts": 60.0},
        {"date": "2024-01-03", "team": "A", "pts": 90.0},
    ])
    out = walk_forward_asof(df, date_col="date", entity_cols=["team"], value_cols=["pts"])
    a = out[out["team"] == "A"].reset_index(drop=True)
    b = out[out["team"] == "B"].reset_index(drop=True)
    assert _nan(a.loc[0, "pts_asof"])
    assert a.loc[1, "pts_asof"] == pytest.approx(100.0)
    assert a.loc[2, "pts_asof"] == pytest.approx(90.0)
    assert _nan(b.loc[0, "pts_asof"])
    assert b.loc[1, "pts_asof"] == pytest.approx(50.0)


# ── 7. Composite entity key ────────────────────────────────────────────────

def test_composite_entity_key():
    df = _f([
        {"date": "2024-01-01", "league": "L1", "team": "A", "v": 10.0},
        {"date": "2024-01-02", "league": "L2", "team": "A", "v": 20.0},
        {"date": "2024-01-03", "league": "L1", "team": "A", "v": 30.0},
        {"date": "2024-01-04", "league": "L2", "team": "A", "v": 40.0},
    ])
    out = walk_forward_asof(df, date_col="date", entity_cols=["league", "team"], value_cols=["v"])
    l1 = out[out["league"] == "L1"].reset_index(drop=True)
    l2 = out[out["league"] == "L2"].reset_index(drop=True)
    assert _nan(l1.loc[0, "v_asof"])
    assert l1.loc[1, "v_asof"] == pytest.approx(10.0)
    assert _nan(l2.loc[0, "v_asof"])
    assert l2.loc[1, "v_asof"] == pytest.approx(20.0)


# ── 8. make_event_id — parts only ─────────────────────────────────────────

def test_make_event_id_no_date():
    df = _f([{"home": "NYK", "away": "SAS"}, {"home": "GSW", "away": "LAL"}])
    assert list(make_event_id(df, ["home", "away"])) == ["NYK_SAS", "GSW_LAL"]


# ── 9. make_event_id — with date prefix ───────────────────────────────────

def test_make_event_id_with_date():
    df = _f([{"date": "2024-06-01", "home": "NYK", "away": "SAS"}])
    assert make_event_id(df, ["home", "away"], date_col="date").iloc[0] == "20240601_NYK_SAS"


# ── 10. make_event_id — deterministic ─────────────────────────────────────

def test_make_event_id_deterministic():
    df = _f([{"date": "2024-01-15", "p1": "Federer", "p2": "Nadal"}])
    id1 = make_event_id(df, ["p1", "p2"], date_col="date").iloc[0]
    id2 = make_event_id(df, ["p1", "p2"], date_col="date").iloc[0]
    assert id1 == id2 == "20240115_Federer_Nadal"


# ── 11. join_asof_sidecar — left join ─────────────────────────────────────

def test_join_asof_sidecar_left():
    spine = _f([{"eid": "e1", "x": 1}, {"eid": "e2", "x": 2}, {"eid": "e3", "x": 3}])
    sidecar = _f([{"eid": "e1", "v_asof": 10.0}, {"eid": "e3", "v_asof": 30.0}])
    out = join_asof_sidecar(spine, sidecar, "eid")
    assert len(out) == 3
    assert out.loc[out["eid"] == "e2", "v_asof"].isna().all()
    assert out.loc[out["eid"] == "e1", "v_asof"].iloc[0] == pytest.approx(10.0)


# ── 12. join_asof_sidecar — duplicate key raises ValueError ───────────────

def test_join_asof_sidecar_no_inflation():
    spine = _f([{"eid": "e1"}, {"eid": "e2"}])
    sidecar = _f([{"eid": "e1", "v_asof": 1.0}, {"eid": "e1", "v_asof": 2.0}])
    with pytest.raises(ValueError, match="duplicate"):
        join_asof_sidecar(spine, sidecar, "eid")


# ── 13. join_asof_sidecar — row count invariant ───────────────────────────

def test_join_asof_sidecar_row_count():
    spine = _f([{"eid": f"e{i}"} for i in range(5)])
    sidecar = _f([{"eid": f"e{i}", "v_asof": float(i)} for i in range(5)])
    assert len(join_asof_sidecar(spine, sidecar, "eid")) == len(spine)


# ── 14. Equivalence: walk_forward_asof vs hand-rolled snapshot-before-update

def test_equivalence_hand_computed():
    """CRUCIAL: walk_forward_asof must reproduce the same values a hand-rolled
    domain loop would compute.  Expected values (hand-computed):
      Entity P rows (v=[4,8,2,6]): asof=[NaN,4.0,6.0,14/3]
      Entity Q rows (v=[10,20]):   asof=[NaN,10.0]
    """
    df = _f([
        {"date": "2024-01-01", "entity": "P", "v": 4.0},
        {"date": "2024-01-02", "entity": "Q", "v": 10.0},
        {"date": "2024-01-03", "entity": "P", "v": 8.0},
        {"date": "2024-01-04", "entity": "Q", "v": 20.0},
        {"date": "2024-01-05", "entity": "P", "v": 2.0},
        {"date": "2024-01-06", "entity": "P", "v": 6.0},
    ])
    out = walk_forward_asof(df, date_col="date", entity_cols=["entity"], value_cols=["v"])

    # Hand-roll the same logic (mirrors the domain pattern exactly).
    sorted_df = df.sort_values("date", kind="mergesort").reset_index(drop=True)
    acc_s: dict = {}
    acc_c: dict = {}
    exp_asof: List[float] = []
    exp_n: List[int] = []
    for _, row in sorted_df.iterrows():
        e = row["entity"]
        n = acc_c.get(e, 0)
        exp_n.append(n)
        exp_asof.append(acc_s[e] / n if n > 0 else float("nan"))
        acc_s[e] = acc_s.get(e, 0.0) + row["v"]
        acc_c[e] = n + 1

    for i in range(len(out)):
        assert out.loc[i, "n_prior"] == exp_n[i], f"row {i} n_prior mismatch"
        ev = exp_asof[i]
        gv = out.loc[i, "v_asof"]
        if math.isnan(ev):
            assert _nan(gv), f"row {i}: expected NaN, got {gv}"
        else:
            assert gv == pytest.approx(ev, rel=1e-9), f"row {i}: {gv} != {ev}"
