"""Per-file tests for apps/live_board/name_maps.py.

Run ONLY this file (never full pytest on this box):
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest tests/test_name_maps.py -q
"""
import os
os.environ.setdefault("NBA_OFFLINE", "1")

from apps.live_board.name_maps import (
    to_corpus_id, SUPPORTED_LEAGUES, _MLB_DISPLAYNAME, _MLB_ABBREV,
)


def test_mlb_displayname():
    assert to_corpus_id("mlb", "Cincinnati Reds") == "CIN"
    assert to_corpus_id("mlb", "New York Yankees") == "NYY"
    assert to_corpus_id("mlb", "Los Angeles Dodgers") == "LAD"
    assert to_corpus_id("mlb", "Athletics") == "OAK"
    assert to_corpus_id("mlb", "San Diego Padres") == "SDG"


def test_mlb_abbreviation():
    assert to_corpus_id("mlb", "CIN") == "CIN"
    assert to_corpus_id("mlb", "KC") == "KAN"
    assert to_corpus_id("mlb", "SD") == "SDG"
    assert to_corpus_id("mlb", "SF") == "SFG"
    assert to_corpus_id("mlb", "TB") == "TAM"
    assert to_corpus_id("mlb", "WSH") == "WAS"
    assert to_corpus_id("mlb", "ATH") == "OAK"


def test_mlb_unknown_is_none():
    assert to_corpus_id("mlb", "Nonexistent Team") is None
    assert to_corpus_id("mlb", "ZZZ") is None


def test_mlb_thirty_franchises():
    # Exactly 30 canonical franchises mapped from displayName.
    assert len(set(_MLB_DISPLAYNAME.values())) == 30


def test_soccer_alias_and_passthrough():
    assert to_corpus_id("soccer", "Manchester City") == "Man City"
    assert to_corpus_id("soccer", "Manchester United") == "Man United"
    assert to_corpus_id("soccer", "Wolverhampton Wanderers") == "Wolves"
    # Exact-match clubs pass through unchanged.
    assert to_corpus_id("soccer", "Arsenal") == "Arsenal"
    assert to_corpus_id("soccer", "Barcelona") == "Barcelona"


def test_soccer_national_teams_none():
    assert to_corpus_id("soccer", "Brazil") is None
    assert to_corpus_id("soccer", "United States") is None
    assert to_corpus_id("soccer", "Argentina") is None


def test_tennis_passthrough():
    assert to_corpus_id("tennis", "Carlos Alcaraz") == "Carlos Alcaraz"
    assert to_corpus_id("tennis", "Some Unknown Player") == "Some Unknown Player"


def test_bad_inputs_never_raise():
    assert to_corpus_id("mlb", None) is None
    assert to_corpus_id("mlb", "") is None
    assert to_corpus_id("soccer", None) is None
    assert to_corpus_id("unknown_sport", "Arsenal") is None
    assert to_corpus_id(None, "Arsenal") is None


def test_supported_leagues():
    assert "mlb" in SUPPORTED_LEAGUES["mlb"]
    assert "fifa.world" in SUPPORTED_LEAGUES["soccer"]
    assert "eng.1" in SUPPORTED_LEAGUES["soccer"]
    assert SUPPORTED_LEAGUES["tennis"] == ["atp", "wta"]


def test_mlb_targets_resolve_in_corpus():
    from scripts.platformkit.predictor_jd import _build_predictor
    corpus = set(_build_predictor("mlb").teams)
    targets = set(_MLB_DISPLAYNAME.values()) | set(_MLB_ABBREV.values())
    assert targets <= corpus
