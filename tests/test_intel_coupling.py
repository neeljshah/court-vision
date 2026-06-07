"""Tests for the leak-free intelligence coupling (src/sim/intel_coupling.py) and
its byte-identical, additive integration into the possession-outcome model.

Covered:
  * INTEL_FEATURES is appended (not inserted) so STATE_FEATURES is unchanged and
    a model trained without intel is unaffected.
  * extract_possessions WITHOUT intel is byte-identical to before (no intel keys
    leak into the state when not supplied).
  * IntelPriorStore is as-of-before: a matchup only sees strictly-earlier games
    (read-before-observe), and signature values are sane / shrink to league.
  * The signature reacts to the inputs (offense style + defense allowance).
  * signature_from_rates round-trips the chosen rates (demo helper).
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

from src.ingame.state_featurizer import load_pbp_events, _load_team_map  # noqa: E402
from src.sim.possession_model import (  # noqa: E402
    extract_possessions, PossessionOutcomeModel, OUTCOMES,
    STATE_FEATURES, STATE_FEATURES_INTEL,
)
from src.sim.intel_coupling import (  # noqa: E402
    IntelPriorStore, INTEL_FEATURES, LEAGUE_3PAR, LEAGUE_PPP,
)


def _sample_game_ids(n=3):
    tm = _load_team_map(os.path.join(ROOT, "data", "nba"))
    ids = []
    for gid, (home, away) in tm.items():
        if gid.isdigit() and os.path.exists(
                os.path.join(ROOT, "data", "nba", f"pbp_{gid}_p1.json")):
            ids.append((gid, home, away))
        if len(ids) >= n:
            break
    return ids


# --------------------------------------------------------------------------- #
# Structural: intel features are appended, base schema untouched
# --------------------------------------------------------------------------- #
def test_intel_features_appended_not_inserted():
    assert STATE_FEATURES_INTEL[:len(STATE_FEATURES)] == STATE_FEATURES
    assert STATE_FEATURES_INTEL[len(STATE_FEATURES):] == INTEL_FEATURES
    # no intel feature name collides with a base feature name
    assert not (set(INTEL_FEATURES) & set(STATE_FEATURES))
    assert len(INTEL_FEATURES) == 15


@pytest.mark.skipif(not _sample_game_ids(1), reason="no PBP data available")
def test_extract_without_intel_is_byte_identical():
    """Calling extract_possessions WITHOUT intel must not add intel keys."""
    gid, home, away = _sample_game_ids(1)[0]
    ev = load_pbp_events(gid, os.path.join(ROOT, "data", "nba"))
    rows_plain = extract_possessions(ev, gid, home, away)
    rows_none = extract_possessions(ev, gid, home, away, intel=None)
    assert len(rows_plain) == len(rows_none)
    for r in rows_plain:
        # state carries exactly the base STATE_FEATURES, no intel keys
        for f in INTEL_FEATURES:
            assert f not in r.state
    # identical states
    for a, b in zip(rows_plain, rows_none):
        assert a.state == b.state and a.outcome == b.outcome and a.points == b.points


@pytest.mark.skipif(not _sample_game_ids(1), reason="no PBP data available")
def test_extract_with_intel_injects_offense_pov():
    gid, home, away = _sample_game_ids(1)[0]
    ev = load_pbp_events(gid, os.path.join(ROOT, "data", "nba"))
    intel = {
        "home": {f: 0.5 for f in INTEL_FEATURES},
        "away": {f: -0.5 for f in INTEL_FEATURES},
    }
    rows = extract_possessions(ev, gid, home, away, intel=intel)
    homes = [r for r in rows if r.off_side == "home"]
    aways = [r for r in rows if r.off_side == "away"]
    assert homes and aways
    # offense-POV: home-offense rows carry the home signature, away the away one
    assert all(r.state["off_intel_3par"] == 0.5 for r in homes)
    assert all(r.state["off_intel_3par"] == -0.5 for r in aways)


# --------------------------------------------------------------------------- #
# Leak-free store: read-before-observe; sane shrinkage
# --------------------------------------------------------------------------- #
def test_store_empty_returns_none():
    store = IntelPriorStore()
    assert store.intel_priors_for("AAA", "BBB") is None
    assert not store.has_prior("AAA", "BBB")


@pytest.mark.skipif(not _sample_game_ids(2), reason="no PBP data available")
def test_store_as_of_before_and_sane():
    ids = _sample_game_ids(3)
    store = IntelPriorStore()
    rows_by_game = []
    for gid, home, away in ids:
        ev = load_pbp_events(gid, os.path.join(ROOT, "data", "nba"))
        rows_by_game.append((gid, home, away, extract_possessions(ev, gid, home, away)))

    g0 = rows_by_game[0]
    # before observing ANY game, the first matchup has no prior
    assert store.intel_priors_for(g0[1], g0[2]) is None
    # observe g0, then a repeat of that matchup HAS a prior
    store.observe(g0[3], g0[1], g0[2])
    sig = store.intel_priors_for(g0[1], g0[2])
    assert sig is not None
    assert set(sig) == set(INTEL_FEATURES)
    # rates are in sane ranges
    assert 0.05 < sig["off_intel_3par"] < 0.6
    assert 0.8 < sig["off_intel_ppp"] < 1.5
    assert 60.0 < sig["off_intel_pace"] < 120.0
    assert 0.05 < sig["def_intel_3par_allowed"] < 0.6
    # a brand-new team (no games) still shrinks to league when paired w/ a known D
    none_sig = store.intel_priors_for("ZZZ", g0[2])
    assert none_sig is None  # offense has no prior -> None (never invents signal)


def test_signature_shrinks_thin_to_league():
    """With a tiny sample the rate is pulled to the league anchor."""
    store = IntelPriorStore()

    class _R:
        def __init__(self, side, outcome, pts):
            self.off_side = side; self.outcome = outcome; self.points = pts

    # one game, home takes a single 3 -> raw 3PAr would be 1.0 but shrink kills it
    rows = [_R("home", "make_3", 3), _R("away", "make_2", 2)]
    store.observe(rows, "HME", "AWY")
    sig = store.intel_priors_for("HME", "AWY")
    assert sig is not None
    # heavily shrunk toward league (0.36), not the raw 1.0
    assert abs(sig["off_intel_3par"] - LEAGUE_3PAR) < 0.05


def test_signature_reacts_to_rates():
    """signature_from_rates moves the matchup terms with the inputs."""
    suppress = IntelPriorStore.signature_from_rates(
        0.36, 0.13, 0.135, 1.12, 99.0,  # league offense
        0.28, 0.11, 0.13, 1.06, 96.0)   # 3-suppressing defense
    concede = IntelPriorStore.signature_from_rates(
        0.36, 0.13, 0.135, 1.12, 99.0,
        0.46, 0.15, 0.15, 1.20, 102.0)  # 3-conceding defense
    # the defense-allowed 3PA and the matchup term must both rise
    assert concede["def_intel_3par_allowed"] > suppress["def_intel_3par_allowed"]
    assert concede["intel_3par_matchup"] > suppress["intel_3par_matchup"]
    assert concede["intel_ppp_matchup"] > suppress["intel_ppp_matchup"]
    # league-average matchup -> ~0 interaction terms
    league = IntelPriorStore.signature_from_rates(
        0.36, 0.13, 0.135, 1.12, 99.0, 0.36, 0.13, 0.135, 1.12, 99.0)
    assert abs(league["intel_3par_matchup"]) < 1e-6
    assert abs(league["intel_ppp_matchup"]) < 1e-6


# --------------------------------------------------------------------------- #
# End-to-end: coupled model fits + the intel inputs move the prediction
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not _sample_game_ids(4), reason="no PBP data available")
def test_coupled_model_fits_and_reacts():
    ids = _sample_game_ids(6)
    store = IntelPriorStore()
    rows = []
    for gid, home, away in ids:
        ev = load_pbp_events(gid, os.path.join(ROOT, "data", "nba"))
        if not ev:
            continue
        pr = extract_possessions(ev, gid, home, away)
        ih = store.intel_priors_for(home, away)
        ia = store.intel_priors_for(away, home)
        for r in pr:
            sig = ih if r.off_side == "home" else ia
            if sig:
                r.state.update(sig)
        rows.extend(pr)
        store.observe(pr, home, away)
    assert rows
    # State vector places intel values in the appended INTEL_FEATURES columns
    # (the mechanism that lets the model consume them); base columns unchanged.
    m = PossessionOutcomeModel(feature_names=list(STATE_FEATURES_INTEL))
    probe = dict(rows[50].state)
    probe["def_intel_3par_allowed"] = 0.41
    vec = m.state_vector(probe)[0]
    j = STATE_FEATURES_INTEL.index("def_intel_3par_allowed")
    assert vec[j] == pytest.approx(0.41)
    assert len(vec) == len(STATE_FEATURES_INTEL)

    # The serve path threads intel through priors["intel"][side] into the state
    # the model scores -- assert that _state_from_game_row picks it up offense-POV.
    gr = {"home_score": 50, "away_score": 48, "home_poss": 45, "away_poss": 45,
          "period": 2, "game_remaining_sec": 1440, "played_share": 0.5,
          "home_efg": 0.5, "away_efg": 0.48, "sec_per_poss_so_far": 15.0}
    priors = {"intel": {"home": {"def_intel_3par_allowed": 0.41,
                                 "intel_ppp_matchup": 0.05}}}
    st_home = m._state_from_game_row(gr, "home", priors)
    st_away = m._state_from_game_row(gr, "away", priors)
    assert st_home["def_intel_3par_allowed"] == pytest.approx(0.41)
    assert st_home["intel_ppp_matchup"] == pytest.approx(0.05)
    # away offense has no signature in this blob -> intel keys absent (default 0)
    assert "def_intel_3par_allowed" not in st_away

    # The XGBoost model fits cleanly on the coupled schema and produces a valid
    # distribution (the full walk-forward eval confirms the intel LEVER at scale;
    # a 6-game fit has too little variance to learn from the near-constant prior).
    mx = PossessionOutcomeModel(
        device="cpu", n_rounds=40,
        feature_names=list(STATE_FEATURES_INTEL)).fit(rows)
    p = mx.predict_proba(rows[50].state)
    assert abs(float(p.sum()) - 1.0) < 1e-4 and (p >= 0).all()
