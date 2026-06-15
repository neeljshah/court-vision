"""Per-file tests for scripts.platformkit.predictor_jd (the predictor->JD cohesion seam).

Run ONLY this file (full pytest freezes the box):
    python -m pytest tests/platform/test_predictor_jd.py -q
"""
from __future__ import annotations

import scripts.platformkit.predictor_jd as pj
from scripts.platformkit.predictor_jd import demo_matchup, get_demo_jd, clear_cache

_SPORTS = ("nba", "mlb", "soccer", "tennis")


def test_demo_matchup_defined_for_all_sports():
    for sp in _SPORTS:
        mu = demo_matchup(sp)
        assert mu is not None and mu["label"] and mu["args"]
    assert demo_matchup("cricket") is None


def test_get_demo_jd_returns_real_distribution_per_sport():
    clear_cache()
    for sp in _SPORTS:
        jd = get_demo_jd(sp)
        assert jd is not None, f"{sp}: expected a JD from the validated predictor"
        assert jd.n_outcomes >= 2  # at least (home, away)
        assert jd.n_sims > 0


def test_get_demo_jd_surface_flows_into_cohesive_read():
    from scripts.platformkit.cohesive_read import build_cohesive_read  # noqa: PLC0415
    clear_cache()
    for sp in _SPORTS:
        cr = build_cohesive_read(sp, jd=get_demo_jd(sp), use_llm=False)
        surf = cr["read"]["surface"]
        assert surf is not None, f"{sp}: surface should be non-None"
        assert "moneyline" in surf and "score_means" in surf
        assert cr["read"]["edge_claimed"] is False


def test_get_demo_jd_degrades_to_none_on_predictor_failure(monkeypatch):
    clear_cache()
    monkeypatch.setattr(
        pj, "_build_predictor",
        lambda s: (_ for _ in ()).throw(RuntimeError("forced")))
    clear_cache()  # drop any cached value so the patched builder is exercised
    assert get_demo_jd("mlb") is None
    assert get_demo_jd("nba") is None


def test_get_demo_jd_unknown_sport_is_none():
    clear_cache()
    assert get_demo_jd("cricket") is None
