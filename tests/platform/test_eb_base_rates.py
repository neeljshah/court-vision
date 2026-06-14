"""Tests for scripts.platformkit.eb_base_rates — synthetic injected records only.

No pandas / no real corpus: a fake loader returns grouped (team, season, k, n)
records so the EB shrinkage + artifact logic is exercised pytest-clean.
"""
from __future__ import annotations

from scripts.platformkit.eb_base_rates import build_for_sport, write_artifact


def _records_loader():
    """Mix of short-season (small n) and full-season (large n) groups, with some
    extreme single-season rates that EB should pull toward the pooled mean."""
    def _load(sport: str):
        recs = []
        # full seasons near .5 (anchor the pooled mean + give kappa signal)
        for t in range(20):
            recs.append({"team": f"T{t}", "season": "2020", "k": 41.0, "n": 82.0})
        # a SHORT season with an extreme rate (should shrink a lot)
        recs.append({"team": "SHORT", "season": "2021", "k": 8.0, "n": 10.0})   # raw 0.80
        # a FULL season with the SAME extreme rate (should shrink less)
        recs.append({"team": "LONG", "season": "2021", "k": 65.0, "n": 82.0})   # raw ~0.79
        return recs
    return _load


def test_build_for_sport_shrinks():
    rep = build_for_sport("nba", loader=_records_loader())
    assert rep["sport"] == "nba"
    assert rep["n_groups"] == 22
    assert 0.0 <= rep["prior"]["pooled_mean"] <= 1.0
    assert rep["prior"]["a"] > 0 and rep["prior"]["b"] > 0
    assert "a prior is not an edge" in rep["note"].lower()


def test_short_season_shrinks_more_than_long():
    rep = build_for_sport("nba", loader=_records_loader())
    by = {(g["team"], g["season"]): g for g in rep["groups"]}
    short = by[("SHORT", "2021")]
    long = by[("LONG", "2021")]
    # both start ~0.80 raw; the small-n group is pulled harder toward the pooled mean
    assert short["raw_rate"] > 0.75 and long["raw_rate"] > 0.75
    assert short["abs_shrink"] > long["abs_shrink"]
    # shrunk rate moves toward the pooled mean (downward from .80)
    assert short["shrunk_rate"] < short["raw_rate"]


def test_unwired_sport_errors():
    rep = build_for_sport("soccer", loader=_records_loader())
    assert "error" in rep and "not wired" in rep["error"]


def test_write_artifact(tmp_path):
    rep = build_for_sport("nba", loader=_records_loader())
    path = write_artifact("nba", rep, organized_root=tmp_path)
    assert path is not None
    p = tmp_path / "NBA" / "_Team_Base_Rates_EB.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "EB-Regularized Team Base Rates" in text
    assert "prior is not an edge" in text.lower()
    # no forbidden edge/odds token
    assert "roi" not in text.lower() and "+ev" not in text.lower()
