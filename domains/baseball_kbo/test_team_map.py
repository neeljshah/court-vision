"""Per-file tests for domains.baseball_kbo.team_map (pure, offline).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_team_map.py -q
"""
from __future__ import annotations

from domains.baseball_kbo.team_map import TEAM_MAP, ALL_EN_CODES, normalize_team


def test_all_ten_teams_present():
    assert len(TEAM_MAP) == 10


def test_latin_alphabet_teams_map_to_themselves():
    for tok in ("KIA", "KT", "LG", "NC", "SSG"):
        assert normalize_team(tok) == tok


def test_korean_glyph_teams_map_to_en_codes():
    # keys are the exact glyphs observed live 2026-07-04 in a GetScheduleList
    # "play" cell -- see the module dict for the literal tokens.
    assert normalize_team("두산") == "DOOSAN"
    assert normalize_team("롯데") == "LOTTE"
    assert normalize_team("삼성") == "SAMSUNG"
    assert normalize_team("한화") == "HANWHA"
    assert normalize_team("키움") == "KIWOOM"


def test_normalize_team_strips_whitespace():
    assert normalize_team("  KIA  ") == "KIA"


def test_normalize_team_unknown_token_passthrough():
    assert normalize_team("UnknownTeam") == "UnknownTeam"


def test_all_en_codes_is_frozenset_of_ten():
    assert isinstance(ALL_EN_CODES, frozenset)
    assert len(ALL_EN_CODES) == 10
    assert "DOOSAN" in ALL_EN_CODES
    assert "KIA" in ALL_EN_CODES
