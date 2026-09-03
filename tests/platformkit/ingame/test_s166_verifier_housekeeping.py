"""Construct check for the S166 empty-pair ESS fallback."""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_baseline_lock as lock


def test_empty_pair_uses_complete_effective_sample_size_shape(tmp_path) -> None:
    """n = 1 (CONSTRUCT): an empty pair set reports the shared ESS bound flag."""
    store = tmp_path / "ingame_grade_joined"
    store.mkdir()

    report = lock.summarize(store)

    assert report["n_games"] == 0
    assert report["ess"] == 0.0
    assert report["n_eff_bound_ok"] is True
