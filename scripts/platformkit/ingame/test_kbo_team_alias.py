"""Per-file tests for scripts.platformkit.ingame.kbo_team_alias (pure, offline).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_team_alias.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame.kbo_team_alias import (
    ALL_EN_CODES,
    EN_TO_KALSHI,
    EN_TO_NAVER,
    EN_TO_RESULTS,
    assert_complete,
    en_from_kalshi_token,
    en_from_naver,
    kalshi_token_for,
    naver_code_for,
)


def test_all_three_alphabets_have_all_ten_teams():
    assert_complete()  # must not raise
    assert len(ALL_EN_CODES) == 10
    assert len(EN_TO_NAVER) == 10
    assert len(EN_TO_KALSHI) == 10
    assert len(EN_TO_RESULTS) == 10


def test_naver_code_for_known_teams():
    assert naver_code_for("DOOSAN") == "OB"
    assert naver_code_for("KIWOOM") == "WO"
    assert naver_code_for("KIA") == "HT"
    assert naver_code_for("SSG") == "SK"
    assert naver_code_for("NC") == "NC"


def test_kalshi_token_for_known_teams():
    assert kalshi_token_for("NC") == "NCD"
    assert kalshi_token_for("KT") == "KTW"
    assert kalshi_token_for("KIWOOM") == "KIW"
    assert kalshi_token_for("SSG") == "SSG"
    assert kalshi_token_for("LG") == "LG"


def test_en_from_naver_round_trips():
    for en in EN_TO_NAVER:
        naver = naver_code_for(en)
        assert en_from_naver(naver) == en


def test_en_from_kalshi_token_round_trips():
    for en in EN_TO_KALSHI:
        token = kalshi_token_for(en)
        assert en_from_kalshi_token(token) == en


def test_unknown_code_returns_none_never_guesses():
    assert naver_code_for("NOTATEAM") is None
    assert kalshi_token_for("NOTATEAM") is None
    assert en_from_naver("ZZ") is None
    assert en_from_kalshi_token("ZZZ") is None


def test_lookup_is_case_and_whitespace_insensitive_but_exact():
    assert naver_code_for("  doosan  ") == "OB"
    # substring/fuzzy must NOT match (ALIAS RAIL): "DOO" is not a valid EN code.
    assert naver_code_for("DOO") is None


def test_no_duplicate_codes_across_teams():
    assert len(set(EN_TO_NAVER.values())) == 10
    assert len(set(EN_TO_KALSHI.values())) == 10


def test_real_ticker_blob_reconstructs_via_kalshi_tokens():
    # Verified live cases (data/cache/line_history/kbo/2026-07-{04,05}.jsonl): the ticker
    # blob is always an UNORDERED concatenation of the two teams' Kalshi tokens.
    cases = [
        ("NCDHAN", "NC", "HANWHA"),
        ("KIWKTW", "KIWOOM", "KT"),
        ("LGSAM", "LG", "SAMSUNG"),
        ("KIALOT", "KIA", "LOTTE"),
        ("SSGDOO", "SSG", "DOOSAN"),
    ]
    for blob, t1, t2 in cases:
        tok1, tok2 = kalshi_token_for(t1), kalshi_token_for(t2)
        assert blob in (tok1 + tok2, tok2 + tok1)


def test_real_naver_slate_codes_match_2026_07_05():
    # Verified live via kbo_naver_relay.fetch_slate('2026-07-05','2026-07-05').
    cases = [
        ("WO", "KIWOOM"), ("OB", "DOOSAN"), ("LG", "LG"), ("HH", "HANWHA"),
        ("KT", "KT"), ("LT", "LOTTE"), ("HT", "KIA"), ("NC", "NC"),
        ("SK", "SSG"), ("SS", "SAMSUNG"),
    ]
    for naver, en in cases:
        assert en_from_naver(naver) == en
