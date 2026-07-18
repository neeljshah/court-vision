"""Per-file tests for scripts.platformkit.predictive_validity.mlb_adapters --
SYNTHETIC pitch frames only (this worktree has no data/ dir); real-data smokes
run post-merge against the real corpus (see run_mlb.py's NO_DATA fail-close).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/predictive_validity/test_mlb_adapters.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.matchup.pitch_mix_profiles import classify_terminal_k
from domains.mlb.prereg_shift_framing import build_taken_pitches, classify_borderline
from scripts.platformkit.predictive_validity import mlb_adapters as A
from scripts.platformkit.predictive_validity.harness import MetricTest, run_metric_test

CUTOFF = "2023-08-01"


# --------------------------------------------------------------------------- #
# derivation correctness -- real imported functions, hand-computed expectations
# --------------------------------------------------------------------------- #
def test_classify_terminal_k_derivation():
    des = pd.Series([
        "Player A strikes out swinging.",
        "Player B called out on strikes.",
        "Player C grounds out.",
        "Player D strikes out on a foul tip.",  # K, not "called out on strikes" -> swinging
    ])
    events = pd.Series(["strikeout", "strikeout", "field_out", "strikeout"])
    out = classify_terminal_k(des, events)
    assert list(out) == ["swinging", "looking", None, "swinging"]


def test_build_taken_pitches_and_classify_borderline_derivation():
    # sz_top=3.5, sz_bot=1.5 (typical zone). PLATE_HALF_WIDTH_FT=0.83, SHELL_FT=0.25.
    raw = pd.DataFrame([
        # comfortably in zone -- called strike, NOT borderline (edge_dist well beyond shell)
        {"description": "called_strike", "plate_x": 0.0, "plate_z": 2.5, "sz_top": 3.5, "sz_bot": 1.5,
         "fielder_2": 1, "strikes": 0, "balls": 0},
        # just above the top edge (within 0.25 shell) -- borderline, called a strike
        {"description": "called_strike", "plate_x": 0.0, "plate_z": 3.6, "sz_top": 3.5, "sz_bot": 1.5,
         "fielder_2": 1, "strikes": 0, "balls": 0},
        # clearly out of zone (0.5 past the shell) -- NOT borderline, a ball
        {"description": "ball", "plate_x": 0.0, "plate_z": 4.0, "sz_top": 3.5, "sz_bot": 1.5,
         "fielder_2": 1, "strikes": 0, "balls": 1},
        # a swing -- excluded from "taken" entirely regardless of geometry
        {"description": "swinging_strike", "plate_x": 0.0, "plate_z": 2.5, "sz_top": 3.5, "sz_bot": 1.5,
         "fielder_2": 1, "strikes": 0, "balls": 0},
    ])
    taken = build_taken_pitches(raw)
    assert len(taken) == 3  # swinging_strike row dropped, not "taken"
    border = classify_borderline(taken)
    assert list(border) == [False, True, False]
    assert list(taken["is_strike"]) == [1, 1, 0]


# --------------------------------------------------------------------------- #
# framing adapter: leak-freedom + floor
# --------------------------------------------------------------------------- #
def _taken_row(entity_id, game_pk, date, is_strike, borderline=True):
    return {"entity_id": entity_id, "game_pk": game_pk, "game_date": pd.Timestamp(date),
            "is_strike": is_strike, "borderline": borderline}


def _framing_precutoff_frame(n=25, entity_id=1):
    # 15 strikes / 10 balls, all borderline, all pre-cutoff -> rate = 0.6
    rows = []
    for i in range(n):
        rows.append(_taken_row(entity_id, 5000 + i, "2023-06-01", 1 if i < 15 else 0))
    return pd.DataFrame(rows)


def test_framing_metric_asof_correct_rate_and_floor():
    taken = _framing_precutoff_frame(n=25, entity_id=1)
    below_floor = pd.DataFrame([_taken_row(2, 9000 + i, "2023-06-01", 1) for i in range(5)])  # only 5 rows
    combined = pd.concat([taken, below_floor], ignore_index=True)
    out = A._framing_metric_asof(combined, CUTOFF)
    row1 = out[out["entity_id"] == 1].iloc[0]
    assert abs(row1["value"] - 0.6) < 1e-9
    assert 2 not in set(out["entity_id"])  # below MIN_BORDERLINE_PRECUTOFF floor


def test_framing_metric_asof_leak_free():
    taken = _framing_precutoff_frame(n=25, entity_id=1)
    before = A._framing_metric_asof(taken, CUTOFF)
    # a post-cutoff row that would drag the rate toward 0 if leaked in
    leaked = pd.concat(
        [taken, pd.DataFrame([_taken_row(1, 99999, "2023-09-01", 0)])], ignore_index=True,
    )
    after = A._framing_metric_asof(leaked, CUTOFF)
    assert before[before["entity_id"] == 1].iloc[0]["value"] == after[after["entity_id"] == 1].iloc[0]["value"]


def test_framing_baseline_uses_all_taken_not_just_borderline():
    rows = [_taken_row(1, 6000 + i, "2023-06-01", 1, borderline=False) for i in range(10)]
    rows += [_taken_row(1, 7000 + i, "2023-06-01", 0, borderline=True) for i in range(10)]
    taken = pd.DataFrame(rows)
    baseline = A._framing_baseline_asof(taken, CUTOFF)
    row1 = baseline[baseline["entity_id"] == 1].iloc[0]
    assert abs(row1["value"] - 0.5) < 1e-9  # 10 strikes / 20 total taken, borderline or not


def test_framing_forward_outcome_window_and_leak():
    pre = _framing_precutoff_frame(n=25, entity_id=1)
    fwd_games = pd.DataFrame([
        _taken_row(1, 8000 + i, pd.Timestamp("2023-08-02") + pd.Timedelta(days=i), 1)
        for i in range(15)
    ])
    combined = pd.concat([pre, fwd_games], ignore_index=True)
    out = A._framing_forward_outcome(combined, CUTOFF, forward_games=20)
    row1 = out[out["entity_id"] == 1].iloc[0]
    assert row1["n_forward"] == 15  # only the 15 forward games, pre-cutoff rows excluded
    assert abs(row1["outcome"] - 1.0) < 1e-9  # all forward rows are strikes


# --------------------------------------------------------------------------- #
# putaway adapter: recent-form vs full-history, leak-freedom
# --------------------------------------------------------------------------- #
def _k_row(entity_id, game_pk, date, is_swinging):
    return {"entity_id": entity_id, "game_pk": game_pk, "game_date": pd.Timestamp(date), "is_swinging": is_swinging}


def test_putaway_metric_recent_vs_baseline_full_history():
    rows = []
    # 20 older games, all looking (is_swinging=0)
    for i in range(20):
        rows.append(_k_row(1, 1000 + i, "2023-05-01", 0))
    # last 15 games (most recent, still pre-cutoff), all swinging (is_swinging=1)
    for i in range(15):
        rows.append(_k_row(1, 2000 + i, pd.Timestamp("2023-06-01") + pd.Timedelta(days=i), 1))
    k = pd.DataFrame(rows)

    recent = A._putaway_metric_asof(k, CUTOFF)  # last N_RECENT_GAMES_PUTAWAY=15 games -> all swinging
    baseline = A._putaway_baseline_asof(k, CUTOFF)  # full 35 games -> 15/35 swinging

    row_recent = recent[recent["entity_id"] == 1].iloc[0]
    row_baseline = baseline[baseline["entity_id"] == 1].iloc[0]
    assert abs(row_recent["value"] - 1.0) < 1e-9
    assert abs(row_baseline["value"] - (15 / 35)) < 1e-9


def test_putaway_baseline_floor_excludes_thin_pitcher():
    k = pd.DataFrame([_k_row(2, 3000 + i, "2023-06-01", 1) for i in range(10)])  # only 10 Ks, floor=30
    baseline = A._putaway_baseline_asof(k, CUTOFF)
    assert 2 not in set(baseline["entity_id"])


def test_putaway_metric_asof_leak_free():
    rows = [_k_row(1, 1000 + i, pd.Timestamp("2023-06-01") + pd.Timedelta(days=i), 0) for i in range(15)]
    k = pd.DataFrame(rows)
    before = A._putaway_metric_asof(k, CUTOFF)
    leaked = pd.concat([k, pd.DataFrame([_k_row(1, 9999, "2023-09-01", 1)])], ignore_index=True)
    after = A._putaway_metric_asof(leaked, CUTOFF)
    assert before[before["entity_id"] == 1].iloc[0]["value"] == after[after["entity_id"] == 1].iloc[0]["value"]


def test_putaway_forward_outcome_min_games_floor():
    rows = [_k_row(1, 1000 + i, "2023-06-01", 1) for i in range(35)]  # clears baseline floor
    rows += [_k_row(1, 4000 + i, pd.Timestamp("2023-08-02") + pd.Timedelta(days=i), 0) for i in range(10)]
    k = pd.DataFrame(rows)
    out = A._putaway_forward_outcome(k, CUTOFF, forward_games=20)
    row1 = out[out["entity_id"] == 1].iloc[0]
    assert row1["n_forward"] == 10  # below MIN_FORWARD_GAMES=12 -- harness would skip this fold


# --------------------------------------------------------------------------- #
# full harness plumbing -- a verdict comes out the other end, no exception
# --------------------------------------------------------------------------- #
def _synthetic_framing_taken(n_entities=4, n_pre=30, n_fwd=15):
    rows = []
    for eid in range(1, n_entities + 1):
        for i in range(n_pre):
            rows.append(_taken_row(eid, 100000 + eid * 1000 + i,
                                    pd.Timestamp("2023-06-01") + pd.Timedelta(days=i), 1 if i % 2 == 0 else 0))
        for i in range(n_fwd):
            rows.append(_taken_row(eid, 200000 + eid * 1000 + i,
                                    pd.Timestamp("2023-08-02") + pd.Timedelta(days=i), 1 if i % 3 == 0 else 0))
    return pd.DataFrame(rows)


def test_framing_test_runs_through_harness_and_yields_verdict():
    taken = _synthetic_framing_taken()
    test = MetricTest(
        family="mlb_framing", sport="mlb", metric_name="borderline_called_strike_rate_asof",
        baseline_name="plain_called_strike_rate_asof", cutoffs=[CUTOFF],
        forward_games=20, min_forward_games=12, min_entities_per_fold=3,
        metric_asof=lambda c: A._framing_metric_asof(taken, c),
        baseline_asof=lambda c: A._framing_baseline_asof(taken, c),
        forward_outcome=lambda c: A._framing_forward_outcome(taken, c, 20),
        caveat=A.FRAMING_CAVEAT,
    )
    result = run_metric_test(test)
    assert result["verdict"] in {"PREDICTIVE_VERIFIED", "DESCRIPTIVE_ONLY", "UNDERPOWERED"}
    assert result["n_folds"] == 1  # single cutoff -> UNDERPOWERED by construction, still a clean run


def _synthetic_putaway_k(n_entities=4, n_pre=35, n_fwd=15):
    rows = []
    for eid in range(1, n_entities + 1):
        for i in range(n_pre):
            rows.append(_k_row(eid, 100000 + eid * 1000 + i,
                                pd.Timestamp("2022-06-01") + pd.Timedelta(days=i), 1 if i % 2 == 0 else 0))
        for i in range(n_fwd):
            rows.append(_k_row(eid, 200000 + eid * 1000 + i,
                                pd.Timestamp("2022-08-02") + pd.Timedelta(days=i), 1 if i % 3 == 0 else 0))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# batter_context adapter: literal zero baseline degeneracy, leak-freedom, floor
# --------------------------------------------------------------------------- #
def _ctx_row(entity_id, game_pk, date, xwoba, velo_bucket):
    return {"entity_id": entity_id, "game_pk": game_pk, "game_date": pd.Timestamp(date),
            "xwoba": xwoba, "velo_bucket": velo_bucket}


def test_context_metric_asof_bucket_math_and_floor():
    rows = [_ctx_row(1, 1000 + i, "2022-05-01", 0.5, "hi") for i in range(25)]
    rows += [_ctx_row(1, 2000 + i, "2022-05-01", 0.2, "lo") for i in range(25)]
    rows += [_ctx_row(2, 3000 + i, "2022-05-01", 0.5, "hi") for i in range(10)]  # below floor=20
    rows += [_ctx_row(2, 4000 + i, "2022-05-01", 0.2, "lo") for i in range(25)]
    df = pd.DataFrame(rows)
    out = A._context_metric_asof(df, CUTOFF)
    row1 = out[out["entity_id"] == 1].iloc[0]
    assert abs(row1["value"] - (0.5 - 0.2)) < 1e-9
    assert 2 not in set(out["entity_id"])  # below CONTEXT_MIN_VELO_PA_ASOF on the hi side


def test_context_baseline_is_literal_zero():
    rows = [_ctx_row(1, 1000 + i, "2022-05-01", 0.5, "hi") for i in range(25)]
    rows += [_ctx_row(1, 2000 + i, "2022-05-01", 0.2, "lo") for i in range(25)]
    df = pd.DataFrame(rows)
    baseline = A._context_baseline_asof(df, CUTOFF)
    assert (baseline["value"] == 0.0).all()
    assert set(baseline["entity_id"]) == set(A._context_metric_asof(df, CUTOFF)["entity_id"])


def test_context_metric_asof_leak_free():
    rows = [_ctx_row(1, 1000 + i, "2022-05-01", 0.5, "hi") for i in range(25)]
    rows += [_ctx_row(1, 2000 + i, "2022-05-01", 0.2, "lo") for i in range(25)]
    df = pd.DataFrame(rows)
    before = A._context_metric_asof(df, CUTOFF)
    leaked = pd.concat([df, pd.DataFrame([_ctx_row(1, 9999, "2023-09-01", 0.9, "hi")])], ignore_index=True)
    after = A._context_metric_asof(leaked, CUTOFF)
    assert before[before["entity_id"] == 1].iloc[0]["value"] == after[after["entity_id"] == 1].iloc[0]["value"]


def test_context_forward_outcome_window_and_n_forward():
    pre = [_ctx_row(1, 1000 + i, "2022-05-01", 0.5, "hi") for i in range(25)]
    pre += [_ctx_row(1, 2000 + i, "2022-05-01", 0.2, "lo") for i in range(25)]
    fwd_hi = [_ctx_row(1, 5000 + i, pd.Timestamp("2023-08-02") + pd.Timedelta(days=i), 0.6, "hi") for i in range(20)]
    fwd_lo = [_ctx_row(1, 6000 + i, pd.Timestamp("2023-08-02") + pd.Timedelta(days=i), 0.3, "lo") for i in range(20)]
    df = pd.DataFrame(pre + fwd_hi + fwd_lo)
    out = A._context_forward_outcome(df, CUTOFF, forward_games=200)
    row1 = out[out["entity_id"] == 1].iloc[0]
    assert abs(row1["outcome"] - (0.6 - 0.3)) < 1e-9
    assert row1["n_forward"] == 40  # 20 hi + 20 lo forward games, pre-cutoff rows excluded


def test_batter_context_test_runs_through_harness_with_degenerate_baseline():
    rows = []
    for eid in range(1, 5):
        for i in range(25):
            rows.append(_ctx_row(eid, 100000 + eid * 1000 + i, "2022-05-01", 0.5, "hi"))
            rows.append(_ctx_row(eid, 150000 + eid * 1000 + i, "2022-05-01", 0.2, "lo"))
        for i in range(20):
            rows.append(_ctx_row(eid, 200000 + eid * 1000 + i,
                                  pd.Timestamp("2023-08-02") + pd.Timedelta(days=i), 0.6, "hi"))
            rows.append(_ctx_row(eid, 250000 + eid * 1000 + i,
                                  pd.Timestamp("2023-08-02") + pd.Timedelta(days=i), 0.3, "lo"))
    df = pd.DataFrame(rows)
    test = A.batter_context_test(df, forward_games=200)
    result = run_metric_test(test)
    assert result["verdict"] in {"PREDICTIVE_VERIFIED", "DESCRIPTIVE_ONLY", "UNDERPOWERED"}
    # a literal-zero baseline has no variance -> rho_baseline is NaN for every fold
    assert all(np.isnan(f.get("rho_baseline", float("nan"))) for f in result["per_cutoff"] if f["status"] == "OK")


def test_putaway_test_runs_through_harness_and_yields_verdict():
    k = _synthetic_putaway_k()
    test = MetricTest(
        family="mlb_pitcher_putaway", sport="mlb", metric_name="putaway_swinging_rate_asof",
        baseline_name="putaway_swinging_rate_full_history_asof", cutoffs=["2022-08-01"],
        forward_games=20, min_forward_games=12, min_entities_per_fold=3,
        metric_asof=lambda c: A._putaway_metric_asof(k, c),
        baseline_asof=lambda c: A._putaway_baseline_asof(k, c),
        forward_outcome=lambda c: A._putaway_forward_outcome(k, c, 20),
        caveat=A.PUTAWAY_CAVEAT,
    )
    result = run_metric_test(test)
    assert result["verdict"] in {"PREDICTIVE_VERIFIED", "DESCRIPTIVE_ONLY", "UNDERPOWERED"}
    assert result["n_folds"] == 1
