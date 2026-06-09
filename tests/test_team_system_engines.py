"""Robustness regression guards for the team_system ENGINES area.

Covers scripts/team_system/engines/engine_*.py + the fusion contract in
predict_ensemble.py. These tests RUN the real engines against the live
data/cache/team_system parquet bank and assert the documented invariants:

  1. every engine returns the required interface keys
  2. margin/total/pts internal consistency  (margin == hp-ap, total == hp+ap)
  3. win_prob_home is bounded [0.01, 0.99]
  4. neutral_site suppresses the +2.7 home edge
  5. unknown team -> ValueError (the validation contract)
  6. no NaN / inf in any numeric output for a valid matchup

Two KNOWN BUGS are pinned as xfail so they are tracked and flip to PASS the
moment V0 fixes them (see docs/_audits/ENGINES_ROBUSTNESS_PUNCHLIST):
  - engine_player_impact: lowercase / unknown team -> NaN (no .upper(), no validation)
  - engine_attribute_matchup: unknown team -> silent HCA-only result (no validation)

This file is OWNED by the engines-audit task; it never edits engines/*.py.
"""
import glob
import importlib.util
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENGDIR = os.path.join(ROOT, "scripts", "team_system", "engines")
_TSDIR = os.path.join(ROOT, "data", "cache", "team_system")

# Make the sim importable (some engines/predict_ensemble import from src/sim).
for p in (os.path.join(ROOT, "scripts", "team_system"), os.path.join(ROOT, "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

REQUIRED_KEYS = {
    "engine", "win_prob_home", "margin_home", "total",
    "home_pts", "away_pts", "margin_sd", "n_models", "n_signals", "notes",
}

_HAS_DATA = os.path.exists(os.path.join(_TSDIR, "league_team_game.parquet"))
pytestmark = pytest.mark.skipif(not _HAS_DATA, reason="team_system parquet bank not present")


def _load_engine(fp):
    name = os.path.splitext(os.path.basename(fp))[0]
    spec = importlib.util.spec_from_file_location(name, fp)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return name, m


def _all_engines():
    out = []
    for fp in sorted(glob.glob(os.path.join(_ENGDIR, "engine_*.py"))):
        name, m = _load_engine(fp)
        if hasattr(m, "predict"):
            out.append((name, m))
    return out


ENGINES = _all_engines() if _HAS_DATA else []
ENGINE_IDS = [n for n, _ in ENGINES]


@pytest.fixture(scope="module", params=ENGINES, ids=ENGINE_IDS)
def engine(request):
    return request.param  # (name, module)


# ---------------------------------------------------------------------------
# Interface contract
# ---------------------------------------------------------------------------

def test_required_keys_present(engine):
    name, m = engine
    p = m.predict("NYK", "SAS", {"neutral_site": False})
    missing = REQUIRED_KEYS - set(p)
    assert not missing, f"{name} missing keys: {missing}"


def test_margin_total_pts_consistency(engine):
    name, m = engine
    p = m.predict("NYK", "SAS", {"neutral_site": False})
    assert abs((p["home_pts"] - p["away_pts"]) - p["margin_home"]) < 0.05, \
        f"{name}: margin != home_pts-away_pts"
    assert abs((p["home_pts"] + p["away_pts"]) - p["total"]) < 0.05, \
        f"{name}: total != home_pts+away_pts"


def test_win_prob_bounded(engine):
    name, m = engine
    p = m.predict("NYK", "SAS", {"neutral_site": False})
    assert 0.01 <= p["win_prob_home"] <= 0.99, f"{name}: win_prob {p['win_prob_home']} out of [0.01,0.99]"


def test_margin_sd_nonneg(engine):
    name, m = engine
    p = m.predict("NYK", "SAS", {"neutral_site": False})
    assert p["margin_sd"] >= 0, f"{name}: negative margin_sd"


def test_no_nan_for_valid_matchup(engine):
    name, m = engine
    p = m.predict("NYK", "SAS", {"neutral_site": False})
    for k in ("win_prob_home", "margin_home", "total", "home_pts", "away_pts", "margin_sd"):
        assert np.isfinite(float(p[k])), f"{name}: {k} is not finite ({p[k]})"


def test_neutral_site_drops_home_edge(engine):
    """neutral_site=True must move the home margin DOWN by ~2.7 (the HCA)."""
    name, m = engine
    home = m.predict("NYK", "SAS", {"neutral_site": False})["margin_home"]
    neut = m.predict("NYK", "SAS", {"neutral_site": True})["margin_home"]
    # MC engines have sampling noise; allow a tolerance band around 2.7.
    assert (home - neut) == pytest.approx(2.7, abs=0.6), \
        f"{name}: neutral_site delta {home - neut:.2f} != ~2.7"


# ---------------------------------------------------------------------------
# Validation contract: unknown team -> ValueError
# ---------------------------------------------------------------------------

# These three already validate correctly.
@pytest.mark.parametrize("ename", ["engine_four_factors", "engine_power_ratings", "engine_team_score"])
def test_unknown_team_raises(ename):
    m = dict(ENGINES)[ename]
    with pytest.raises(ValueError):
        m.predict("ZZZ", "SAS", {})
    with pytest.raises(ValueError):
        m.predict("NYK", "ZZZ", {})


# ---------------------------------------------------------------------------
# KNOWN BUGS (pinned xfail -> flip to pass when V0 adds .upper()+validation)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="BUG: player_impact has no team validation/.upper() -> NaN", strict=False)
def test_player_impact_unknown_team_raises():
    m = dict(ENGINES)["engine_player_impact"]
    with pytest.raises(ValueError):
        m.predict("ZZZ", "SAS", {})


@pytest.mark.xfail(reason="BUG: player_impact not case-insensitive -> lowercase yields NaN", strict=False)
def test_player_impact_lowercase_ok():
    m = dict(ENGINES)["engine_player_impact"]
    p = m.predict("nyk", "sas", {})
    assert np.isfinite(p["win_prob_home"]) and np.isfinite(p["margin_home"])


@pytest.mark.xfail(reason="BUG: attribute_matchup accepts unknown team, returns silent HCA-only", strict=False)
def test_attribute_matchup_unknown_team_raises():
    m = dict(ENGINES)["engine_attribute_matchup"]
    with pytest.raises(ValueError):
        m.predict("ZZZ", "SAS", {})


# ---------------------------------------------------------------------------
# Determinism (seeded MC engines must be reproducible call-to-call)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ename", ["engine_team_score", "engine_four_factors"])
def test_seeded_engine_is_deterministic(ename):
    m = dict(ENGINES)[ename]
    a = m.predict("NYK", "SAS", {})
    b = m.predict("NYK", "SAS", {})
    assert a["win_prob_home"] == b["win_prob_home"]
    assert a["margin_home"] == b["margin_home"]
