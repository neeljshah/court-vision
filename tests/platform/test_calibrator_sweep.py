"""Tests for scripts.platformkit.calibrator_sweep — synthetic injected loader only.

No pandas / no real corpus.  Verifies the sweep aggregates per-cell results and
the robustness summary flags.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.calibrator_sweep import sweep_all, sweep_sport


def _overconfident_loader(seed: int = 1):
    def _load(sport: str):
        rng = np.random.default_rng(seed + len(sport))
        n = 800
        true_p = rng.uniform(0.3, 0.7, n)
        raw = np.clip(0.5 + (true_p - 0.5) * 2.4, 0.01, 0.99)
        y = rng.binomial(1, true_p).astype(float)
        return raw.astype(float), y
    return _load


def test_sweep_sport_runs_grid():
    grid = [(50, 20), (50, 40)]
    res = sweep_sport("nba", grid, loader=_overconfident_loader())
    assert res["sport"] == "nba" and res["n"] == 800
    assert len(res["cells"]) == 2
    for c in res["cells"]:
        assert c["isotonic_rank"] in (1, 2, 3, 4, 5)
        assert c["chosen"] in {"identity", "temperature", "platt", "beta", "isotonic"}
    # robustness summary keys present
    assert "isotonic_always_worst" in res
    assert isinstance(res["isotonic_never_chosen"], bool)
    # honest note must carry the CALIBRATION != EDGE disclaimer
    assert "calibration != edge" in res["note"].lower()


def test_sweep_handles_load_error():
    def _bad(sport: str):
        raise FileNotFoundError("no corpus")
    res = sweep_sport("mlb", loader=_bad)
    assert "error" in res and "no corpus" in res["error"]


def test_sweep_all_each_sport():
    out = sweep_all(["nba", "tennis"], [(50, 30)], loader=_overconfident_loader())
    assert set(out) == {"nba", "tennis"}
    for r in out.values():
        assert r["n"] == 800 and len(r["cells"]) == 1


def test_overconfident_isotonic_not_chosen():
    """On a clearly-overconfident series a parametric method should win, not isotonic
    (mirrors the real-data finding direction; synthetic so deterministic)."""
    res = sweep_sport("soccer", [(50, 25)], loader=_overconfident_loader())
    assert res["cells"][0]["chosen"] != "isotonic"
