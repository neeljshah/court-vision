"""Synthetic S328 rails; no parquet replay or calibration comparison is run here."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from scripts.platformkit.ingame.s328_asof_replay import (
    AccessViolation, external_asof_frame, replay, summary,
)


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/harness/S328_asof_join_falsification_2026-09-08_prereg.md"


def _source() -> pd.DataFrame:
    return pd.DataFrame({"game_id": ["g1", "g1", "g1", "g1"], "ts": [100, 160, 200, 300],
                         "period": [1, 1, 1, 1], "game_clock_s": [600.0, 540.0, 500.0, 400.0],
                         "market_prob": [0.2, 0.6, 0.6, 0.9]})


def _states(n: int = 1) -> pd.DataFrame:
    return pd.DataFrame({"state_id": list(range(n)), "game_id": ["g1"] * n, "ts": [200] * n,
                         "period": [1] * n, "game_clock_s": [500.0] * n})


def _builder(frame: pd.DataFrame, state: dict) -> tuple[list[dict], list[dict]]:
    stamp = "2026-01-01T00:00:00"
    features = []
    labels = []
    for index, row in enumerate(frame.itertuples(index=False)):
        key = "%s|%06d|home_win" % (row.game_id, index)
        feature = {"sport": "basketball", "league": "NBA", "rule_version": "S328-test", "game_id": row.game_id,
                   "home_team_id": None, "away_team_id": None, "season": "2025-26", "corpus": "construct", "venue": "test",
                   "target_id": "home_win", "line": None, "class_order": ("away", "home"), "settlement_rule": "home_win",
                   "void_rule": "none", "event_id": key, "sequence": index, "event_time": stamp, "received_at": stamp,
                   "feature_available_at": stamp, "prediction_at": "2026-01-01T00:00:01", "state": {"period": 1, "clock_seconds": 1.0},
                   "score_home": 0, "score_away": 0, "status": "checkpoint", "unknown_flags": ("home_team_id", "away_team_id", "line", "ml_source", "ml_time", "ml_probabilities"),
                   "provenance": {"source": "construct"}, "m0_source": "market", "m0_time": stamp, "m0_probabilities": (0.5, 0.5),
                   "ml_source": None, "ml_time": None, "ml_probabilities": None, "candidate_probabilities": (0.5, 0.5),
                   "null_probabilities": (0.5, 0.5), "state_key": key, "exclusions": (), "weight": 1.0, "fold_id": "fold_a",
                   "input_hash": "input", "code_hash": "code", "seal_hash": "seal", "maximum_feed_delay_seconds": 0, "features": {"market_prob": row.market_prob}}
        features.append(feature)
        labels.append({"game_id": row.game_id, "target_id": "home_win", "state_key": key, "outcome": 1,
                       "outcome_known_at": "2026-01-02T00:00:00"})
    return features, labels


def _latest(frame: pd.DataFrame, _state: dict, loader: object) -> float:
    return float(frame.market_prob.iloc[-1]) if len(frame) else 0.5


def test_planted_future_row_is_refused_by_external_join() -> None:
    frame = external_asof_frame(_source(), _states().iloc[0].to_dict(), 0)
    assert list(frame.ts) == [100, 160, 200]
    records = replay(_source(), _states(), {"S320_SUBSTITUTE": _latest}, _builder)
    assert set(records.prefix_changed) == {0}
    assert set(records.loc[records.delay_seconds.eq(0), "p_delay_probability"]) == {0.6}


def test_recording_loader_catches_read_outside_allowed_frame() -> None:
    source = _source()

    def bad(_frame: pd.DataFrame, _state: dict, loader: object) -> float:
        with pytest.raises(AccessViolation):
            loader.read(source)
        return 0.5

    records = replay(source, _states(), {"bad": bad}, _builder)
    assert set(records.access_violations) == {3}
    assert set(records.verdict) == {"VIOLATION"}


def test_delay_sweep_on_twenty_state_construct_has_pinned_changes() -> None:
    records = replay(_source(), _states(20), {"S320_SUBSTITUTE": _latest}, _builder)
    table = summary(records).set_index("delay_seconds")
    assert table.loc[0, "n_changed"] == 0
    assert table.loc[30, "n_changed"] == 0
    assert table.loc[60, "n_changed"] == 20
    assert table.loc[120, "n_changed"] == 20
    assert table.loc[60, "n_delay_window_records"] == 40


def test_prereg_seal_normalizes_crlf_without_git_show() -> None:
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = raw.rsplit(b"SEAL sha256 ", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.decode("ascii").strip()
