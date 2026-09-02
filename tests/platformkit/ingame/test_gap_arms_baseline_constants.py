"""Regression coverage for the real-corpus baseline denominators."""
from pathlib import Path

import pytest

from scripts.platformkit.ingame import run_gap_arms_real_corpus as subject
from scripts.platformkit.ingame_replay_scoreboard import discover_store


def test_baseline_constants_match_real_loader_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep both baseline denominators aligned with the canonical local store."""
    cache_root = Path("data/cache")
    store = discover_store(cache_root)
    if store is None:
        pytest.skip("real local tick store is absent under data/cache")

    ticks, features = subject._load_ticks(store)
    loader_counts = (len(ticks), sum(tick["in_window"] for tick in ticks))
    assert (subject._BASELINE_TICKS, subject._BASELINE_WINDOW_TICKS) == loader_counts

    monkeypatch.setattr(subject.gap_blend_arm, "evaluate", lambda *args, **kwargs: {})
    monkeypatch.setattr(subject.gap_regime_arm, "evaluate", lambda *args, **kwargs: {})
    monkeypatch.setattr(subject.gap_offset_arm, "evaluate", lambda *args, **kwargs: {})
    monkeypatch.setattr(subject, "_load_ticks", lambda _store: (ticks, features))
    report = subject.evaluate(cache_root, bootstrap_iterations=0)
    assert report["baseline_corpus"]["matches"] is True
