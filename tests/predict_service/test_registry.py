"""Per-file test: predict_service.registry capability map.

Tests:
  * active_sports() includes "nba" when the corpus is present; degrades to []
    gracefully on a fresh clone (no crash either way).
  * capabilities("nba") returns a truthy dict with expected keys.
  * capabilities(unknown) returns a safe zeroed-out dict, never raises.
  * build_predictor(unknown) returns None, never raises.
  * Honesty invariant: no $ / edge / roi / profit in the note field.

Run: python -m pytest tests/predict_service/test_registry.py -q
"""
from __future__ import annotations

import importlib
from typing import Any, Dict, Optional


def _registry():
    """Import the registry fresh (allows patching without side-effects)."""
    import predict_service.registry as reg
    return reg


# ---------------------------------------------------------------------------
# active_sports()
# ---------------------------------------------------------------------------

def test_active_sports_is_list():
    reg = _registry()
    result = reg.active_sports()
    assert isinstance(result, list)


def test_active_sports_no_crash():
    """active_sports() must never raise even on a fresh clone (no corpus)."""
    reg = _registry()
    try:
        sports = reg.active_sports()
    except Exception as exc:  # noqa: BLE001
        raise AssertionError("active_sports() raised: %s" % exc) from exc
    assert isinstance(sports, list)


def test_active_sports_includes_nba_when_available():
    """If the NBA corpus is present (normal dev env), nba appears in active_sports.

    When the corpus is absent (fresh clone), active_sports() returns [] and this
    test passes trivially -- the contract is "never crashes + list output".
    """
    reg = _registry()
    sports = reg.active_sports()
    # On a fully provisioned machine nba must appear; degrade gracefully if absent.
    if sports:
        # At least one sport is available -- ensure nba is among the known sports.
        # We cannot assert it is present without knowing if the corpus is local,
        # but we CAN assert every returned sport is a non-empty string.
        for s in sports:
            assert isinstance(s, str) and s
    # Corpus-present path: nba should be in active_sports if predictor built ok.
    reg2 = _registry()
    nba_pred = reg2.build_predictor("nba")
    if nba_pred is not None:
        assert "nba" in reg2.active_sports(), \
            "nba predictor built but not in active_sports()"


def test_active_sports_only_known_sports():
    """active_sports() returns only sports declared in the registry table."""
    reg = _registry()
    known = {"nba", "mlb", "soccer", "soccer_intl", "tennis"}
    for s in reg.active_sports():
        assert s in known, "unexpected sport in active_sports: %r" % s


# ---------------------------------------------------------------------------
# capabilities(sport)
# ---------------------------------------------------------------------------

def test_capabilities_nba_has_required_keys():
    reg = _registry()
    cap = reg.capabilities("nba")
    assert isinstance(cap, dict)
    for key in ("has_predictor", "markets", "produce", "note"):
        assert key in cap, "capabilities('nba') missing key %r" % key


def test_capabilities_nba_truthy():
    """capabilities('nba') must be a truthy dict (non-empty, has the keys we need)."""
    reg = _registry()
    cap = reg.capabilities("nba")
    assert cap  # truthy overall
    assert isinstance(cap["markets"], list)
    assert len(cap["markets"]) > 0, "nba capabilities should list at least one market"
    assert isinstance(cap["produce"], bool)
    assert isinstance(cap["has_predictor"], bool)


def test_capabilities_nba_markets_are_strings():
    reg = _registry()
    cap = reg.capabilities("nba")
    for m in cap["markets"]:
        assert isinstance(m, str) and m


def test_capabilities_nba_produce_true():
    """NBA produce flag must be True (end-to-end produce_sport() is wired)."""
    reg = _registry()
    assert reg.capabilities("nba")["produce"] is True


def test_capabilities_known_sports_all_have_keys():
    reg = _registry()
    for sport in ("nba", "mlb", "soccer", "soccer_intl", "tennis"):
        cap = reg.capabilities(sport)
        for key in ("has_predictor", "markets", "produce", "note"):
            assert key in cap, "%s capabilities missing %r" % (sport, key)


def test_capabilities_unknown_sport_zeroed_out():
    """An unknown sport returns a safe, zeroed-out dict -- never raises."""
    reg = _registry()
    cap = reg.capabilities("unknownsport_xyz")
    assert cap["has_predictor"] is False
    assert cap["markets"] == []
    assert cap["produce"] is False
    assert "unknown" in cap["note"].lower()


def test_capabilities_unknown_sport_no_raise():
    """capabilities() must never raise for any input."""
    reg = _registry()
    for bad in ("", "XYZXYZ", "nba ", "basketball", "123"):
        try:
            cap = reg.capabilities(bad)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                "capabilities(%r) raised: %s" % (bad, exc)) from exc
        assert isinstance(cap, dict)


def test_capabilities_note_no_dollar_edge():
    """Honesty: no $ edge / roi / profit in any note field."""
    reg = _registry()
    for sport in ("nba", "mlb", "soccer", "soccer_intl", "tennis"):
        note = reg.capabilities(sport).get("note", "").lower()
        for banned in ("$edge", "roi", "profit"):
            assert banned not in note, \
                "banned term %r found in %s note: %r" % (banned, sport, note)


# ---------------------------------------------------------------------------
# build_predictor(sport)
# ---------------------------------------------------------------------------

def test_build_predictor_unknown_returns_none():
    reg = _registry()
    result = reg.build_predictor("unknownsport_xyz")
    assert result is None


def test_build_predictor_unknown_no_raise():
    """build_predictor must never raise for any input."""
    reg = _registry()
    for bad in ("", "XYZXYZ", "basketball", "nba ", "123"):
        try:
            result = reg.build_predictor(bad)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                "build_predictor(%r) raised: %s" % (bad, exc)) from exc
        assert result is None


def test_build_predictor_nba_consistent_with_capabilities():
    """build_predictor('nba') and capabilities('nba')['has_predictor'] agree."""
    reg = _registry()
    pred = reg.build_predictor("nba")
    cap = reg.capabilities("nba")
    if pred is not None:
        assert cap["has_predictor"] is True
    else:
        # Corpus absent on this machine -- both must agree on False.
        assert cap["has_predictor"] is False


def test_build_predictor_result_type():
    """When a predictor is returned it must have a predict method (or be None)."""
    reg = _registry()
    pred = reg.build_predictor("nba")
    if pred is not None:
        assert hasattr(pred, "predict"), \
            "build_predictor('nba') returned object with no predict() method"
