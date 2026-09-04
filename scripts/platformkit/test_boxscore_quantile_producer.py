"""Focused S271 attempt-2b tests for purge, arithmetic, and evaluator ownership."""

import hashlib

import numpy as np
import pandas as pd

from scripts.platformkit import boxscore_quantile_producer as producer


def test_s271_purge_fixture_and_lf_normalized_seal() -> None:
    frame = pd.DataFrame({"player_id": [7, 7, 7], "date": ["2025-01-01", "2025-01-03", "2025-02-01"],
                          "target_pts": [10.0, 20.0, 999.0]})
    features = producer.build_features(frame, "target_pts")
    row = features.loc[features.date.eq(pd.Timestamp("2025-01-03"))].iloc[0]
    assert row.prior_count == 1 and row.prior_mean == 10.0 and row.prior_last == 10.0
    assert (features.feature_source_max_date < features.date).all()
    raw = producer.PREREG_PATH.read_bytes().replace(b"\r\n", b"\n")
    prefix, suffix = raw.split(b"SEAL_SHA256:", 1)
    assert hashlib.sha256(prefix).hexdigest() == suffix.splitlines()[0].strip().decode("ascii")


def test_s271_three_row_coverage_and_evaluator_only_scoring() -> None:
    assert np.mean(np.array([True, False, True], dtype=float)) == 2 / 3
    states = [{"game_id": "g0", "state_ts": "2024-01-01T12:00:00", "home": "player:7", "away": "nba_boxscore",
               "outcome": 10.0, "features": dict.fromkeys(producer.FEATURES, 0.0),
               "feature_avail": dict.fromkeys(producer.FEATURES, "1900-01-01T00:00:00")},
              {"game_id": "g1", "state_ts": "2025-10-02T12:00:00", "home": "player:7", "away": "nba_boxscore",
               "outcome": 20.0, "features": dict.fromkeys(producer.FEATURES, 1.0),
               "feature_avail": dict.fromkeys(producer.FEATURES, "2024-01-01T00:00:00")}]
    def evaluator(all_states, fit_predict, score, **kwargs):
        assert kwargs["embargo_days"] == 1
        view = {key: value for key, value in all_states[1].items() if key != "outcome"}
        prediction = fit_predict([all_states[0]], [view])[0]
        return [{"game_id": "g1", "ts": all_states[1]["state_ts"], "n_train": 1, "evaluator_output": True,
                 **score(all_states[1], prediction)}]
    record = producer.evaluate_states(states, "pts", evaluator=evaluator)[0]
    assert record["evaluator_output"] is True and record["q10"] <= record["q50"] <= record["q90"]
