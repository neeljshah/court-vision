"""Focused S310 seal, identity, tail, denominator, and future-label tests."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from scripts.platformkit import s310_tail_beta_offset as s310


def test_s310_prereg_seal_normalizes_crlf_to_lf() -> None:
    raw = s310.PREREG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = raw.split(b"Seal-SHA256-LF: ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.decode("ascii").strip()
    assert s310._verify_prereg() == seal.decode("ascii").strip()


def test_identity_and_fixed_tail_endpoints() -> None:
    raw = np.array([0.0, .01, .05, .050001, .949999, .95, .99, 1.0])
    base = raw.copy()
    assert s310._tail_bin(base).tolist() == ["outside", "low_001_005", "low_001_005", "outside", "outside", "high_095_099", "high_095_099", "outside"]
    assert np.array_equal(s310._apply_candidate(raw, base, np.zeros(3)), base)
    moved = s310._apply_candidate(raw, base, np.array([.1, 0., 0.]))
    assert np.array_equal(moved[[0, 3, 4, 7]], base[[0, 3, 4, 7]])


def test_fixed_tail_denominator_excludes_only_named_outside_states() -> None:
    baseline = np.array([.01, .05, .30, .95, .99])
    mask = s310._tail_bin(baseline) != "outside"
    assert mask.tolist() == [True, True, False, True, True]
    assert int(mask.sum()) == 4


def test_state_schema_carries_the_frozen_outer_group_key() -> None:
    # `ts` matches the corpus dtype: int64 epoch seconds, here 2025-01-01T00:00:00Z.
    frame = pd.DataFrame({"state_key": ["g:1735689600:0"], "game_id": ["g"],
                          "ts": np.array([1735689600], dtype="int64"),
                          "outcome_home_win": [0], "market_prob": [.1], "game_date": ["2025-01-01"],
                          "season": ["2024-25"]})
    state = s310._states(frame)[0]
    assert state["season"] == "2024-25"
    assert state["state_ts"].startswith("2025-01-01T")


def test_nested_oof_earlier_predictions_ignore_future_labels() -> None:
    dates = pd.date_range("2025-01-01", periods=10, tz="UTC")
    frame = pd.DataFrame({"game_date": dates, "raw": np.linspace(.01, .99, 10),
                          "y": [0, 1] * 5})
    raw_a, oof_a, y_a = s310._nested_oof(frame)
    changed = frame.copy()
    changed.loc[changed.game_date >= dates[8], "y"] = 1 - changed.loc[changed.game_date >= dates[8], "y"]
    raw_b, oof_b, y_b = s310._nested_oof(changed)
    assert np.array_equal(raw_a[:6], raw_b[:6])
    assert np.array_equal(y_a[:6], y_b[:6])
    assert np.allclose(oof_a[:6], oof_b[:6])


def test_supplement_seal_matches_its_own_bytes() -> None:
    raw = s310.SUPPLEMENT.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = raw.split(b"Seal-SHA256-LF: ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.decode("ascii").strip()
    assert s310._verify_seal(s310.SUPPLEMENT) == seal.decode("ascii").strip()


def test_thin_keeps_one_lowest_index_row_per_clock_bucket_and_ignores_outcome() -> None:
    frame = pd.DataFrame({
        "row_index": [3, 1, 2, 0, 4],
        "game_id": ["g", "g", "g", "g", "h"],
        "period": [1, 1, 1, 2, 1],
        "game_clock_s": [700.0, 690.0, 660.0, 700.0, 700.0],
        "outcome_home_win": [0, 0, 0, 0, 1],
    })
    thinned = s310._thin(frame)
    # 690 and 700 share bucket 23; 660 is bucket 22; period 2 and game h are separate cells.
    assert sorted(thinned.row_index) == [0, 1, 2, 4]
    assert thinned.loc[thinned.clock_bucket.eq(23) & thinned.game_id.eq("g")
                       & thinned.period.eq(1), "row_index"].tolist() == [1]
    flipped = frame.assign(outcome_home_win=1 - frame.outcome_home_win)
    assert sorted(s310._thin(flipped).row_index) == sorted(thinned.row_index)


def test_states_read_ts_as_epoch_seconds_not_nanoseconds() -> None:
    """Regression: `pd.Timestamp(int)` reads nanoseconds, which put every state on
    1970-01-01, collapsed the corpus to one calendar day, and made the shared
    calendar-day embargo block every train row on every path."""
    frame = pd.DataFrame({"state_key": ["g:1729640162:0"], "game_id": ["g"],
                          "ts": np.array([1729640162], dtype="int64"),
                          "outcome_home_win": [0], "market_prob": [.1],
                          "game_date": ["2024-10-23"], "season": ["2024-25"]})
    state = s310._states(frame)[0]
    assert state["state_ts"].startswith("2024-10-22T"), state["state_ts"]
    assert state["feature_avail"]["raw"] < state["state_ts"]


def test_distinct_game_days_are_not_collapsed_into_one_embargo_block() -> None:
    from scripts.platformkit.eval_gate import cpcv_engine as ce
    from datetime import datetime
    frame = pd.DataFrame({
        "state_key": ["a:1729640162:0", "b:1735000000:1"],
        "game_id": ["a", "b"],
        "ts": np.array([1729640162, 1735000000], dtype="int64"),
        "outcome_home_win": [0, 1], "market_prob": [.2, .8],
        "game_date": ["2024-10-22", "2024-12-24"], "season": ["2024-25", "2024-25"]})
    states = s310._states(frame)
    stamps = [datetime.fromisoformat(s["state_ts"]) for s in states]
    assert stamps[0].date() != stamps[1].date()
    # The second state is 63 days away, so scoring it must not embargo the first.
    assert 0 not in ce._blocked_indices(states, stamps, [1], s310.EMBARGO_DAYS)


def test_corrected_supplement_seal_matches_its_own_bytes() -> None:
    raw = s310.SUPPLEMENT_CORRECTED.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = raw.split(b"Seal-SHA256-LF: ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.decode("ascii").strip()
    assert s310._verify_seal(s310.SUPPLEMENT_CORRECTED) == seal.decode("ascii").strip()
