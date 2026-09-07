"""S304 construct guards for S108's as-of feature assembly.

Run only this file: python -m pytest tests/platformkit/eval_gate/test_s108_features.py -q
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s108_features as s108


def _build(monkeypatch, sources):
    states = [
        {"event_id": "event-a", "game_id": "event-a", "state_ts": "2024-01-01T00:00:00",
         "game_date": "2024-01-01", "devig_close_prob": 0.25, "outcome": 0,
         "corpus_unit": "fixture-a"},
        {"event_id": "event-b", "game_id": "event-b", "state_ts": "2024-01-02T00:00:00",
         "game_date": "2024-01-02", "devig_close_prob": 0.75, "outcome": 1,
         "corpus_unit": "fixture-b"},
    ]
    monkeypatch.setattr(s108, "corpus_states", lambda sport: (states, pd.DataFrame(), None))
    monkeypatch.setattr(s108, "partition_corpus", lambda states, seed: SimpleNamespace(
        screen_ids=frozenset(("event-a", "event-b")), screen_sha256="fixture-screen", basis="fixture"))
    monkeypatch.setattr(s108, "asof_sources", lambda sport: list(sources))
    monkeypatch.setattr(s108.pd, "read_parquet", lambda path: sources[path].copy())
    monkeypatch.setattr(s108, "load_gate_corpus", lambda sport, portable: pd.DataFrame(
        {"event_id": ["event-a", "event-b"], "corpus_unit": ["fixture-a", "fixture-b"]}))
    monkeypatch.setattr(s108, "_cluster_ids", lambda screen, sport: ("fixture", ["fixture-a", "fixture-b"]))
    return s108.build("nba")


def _source(**columns):
    return pd.DataFrame({"event_id": ["event-a", "event-b"], **columns})


def test_same_game_name_is_refused_before_its_values_are_read(monkeypatch):
    plant = _source(home_final=[0.0, 1.0], asof_rating=[10.0, 20.0])
    original_to_numeric = s108.pd.to_numeric
    seen = []

    def guard(series, *args, **kwargs):
        seen.append(getattr(series, "name", None))
        if getattr(series, "name", None) == "home_final":
            raise AssertionError("same-game values were read")
        return original_to_numeric(series, *args, **kwargs)

    monkeypatch.setattr(s108.pd, "to_numeric", guard)
    out = _build(monkeypatch, {"/fixture/plant.parquet": plant})
    assert "plant.parquet:home_final" in out["refusals"]
    assert "home_final" not in seen and "home_final" not in out["X"]
    assert out["X"]["asof_rating"].tolist() == [10.0, 20.0]


def test_duplicate_key_source_is_refused_whole(monkeypatch):
    duplicate = pd.DataFrame({"event_id": ["event-a", "event-a"],
                              "asof_rating": [10.0, 20.0], "asof_speed": [3.0, 4.0]})
    out = _build(monkeypatch, {"/fixture/duplicate.parquet": duplicate})
    assert "duplicate.parquet" in out["refusals"]
    assert "duplicate.parquet" not in out["sources"]
    assert set(("asof_rating", "asof_speed")).isdisjoint(out["X"].columns)


def test_first_source_wins_and_second_source_fills_only_gaps(monkeypatch):
    first = _source(asof_rating=[1.0, np.nan])
    second = _source(asof_rating=[9.0, 2.0])
    out = _build(monkeypatch, {"/fixture/first.parquet": first, "/fixture/second.parquet": second})
    assert out["X"]["asof_rating"].tolist() == [1.0, 2.0]
    assert out["sources"] == {"first.parquet": 1, "second.parquet": 1}


@pytest.mark.xfail(strict=True, reason="S304 finding: a one-finite-value source is dropped before missingness is added")
def test_missing_value_adds_indicator_column(monkeypatch):
    out = _build(monkeypatch, {"/fixture/missing.parquet": _source(asof_rating=[1.0, np.nan])})
    assert out["X"]["asof_rating"].tolist() == [1.0, np.nan]
    assert out["X"]["asof_rating__isna"].tolist() == [0.0, 1.0]
    assert out["n_missing_cols"] == 1
