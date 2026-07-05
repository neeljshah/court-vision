"""scripts.platformkit.ingame.kbo_team_alias -- KBO 3-alphabet team-code bridge
(kbo-alias-wire-soak lane).

THE GAP: inplay_capture_loop.py keys KBO games by their KALSHI ticker (e.g.
KXKBOGAME-26JUL070530NCDHAN), but kbo_relay_state_provider.py's relay fetch needs the
NAVER gameId (e.g. 20260705OBWO02026), which embeds a DIFFERENT 2-letter team-code
alphabet. A third alphabet (the results-parquet EN team code, e.g. "DOOSAN") is also in
play as the corpus-facing canonical name. This module is the single EXPLICIT dict per
alphabet, cross-checked so no two silently drift.

ALIAS RAIL (binding, from the 2026-06-25 prop-settler city-abbrev bug): every lookup here
is EXACT-match on a literal code -- NEVER substring/city/fuzzy matching. An unknown code
returns None (fail-open); this module never guesses a team.

HOW EACH ALPHABET WAS DERIVED (no guessing -- see the lane's own audit trail):
  * kalshi 3-letter token: solved by cross-checking every (ticker, home, away) triple in
    data/cache/line_history/kbo/2026-07-{04,05}.jsonl (10 tickers observed, home+away
    ALWAYS reconstructable as an UNORDERED concatenation of the two teams' tokens --
    Kalshi does not fix away-then-home order the way MLB's KXMLBGAME series does, so the
    matcher below tries both split orders and requires an EXACT set match, never a
    positional parse).
  * naver 2-letter code: solved by fetching the live 2026-07-05 slate (kbo_naver_relay.
    fetch_slate) and reading each game's homeTeamName/awayTeamName (Korean-glyph or
    Latin), which decodes 1:1 through the EXISTING domains.baseball_kbo.team_map.TEAM_MAP
    glyph dict (zero new glyph literals invented here -- this module only carries the
    already-verified EN code as the join value).
  * results-parquet EN code: read directly off data/domains/kbo/kbo_results.parquet's
    distinct home_team/away_team values (10 codes, already ASCII EN names).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_team_alias.py -q
"""
from __future__ import annotations

import logging
from typing import Dict, FrozenSet, Optional

logger = logging.getLogger(__name__)

# EN canonical code (matches domains.baseball_kbo.team_map.TEAM_MAP's values, and
# data/domains/kbo/kbo_results.parquet's home_team/away_team column values verbatim) ->
# Naver schedule-API 2-letter team code (verified live via kbo_naver_relay.fetch_slate
# against 2026-07-05's 5-game slate; see module docstring).
EN_TO_NAVER: Dict[str, str] = {
    "DOOSAN": "OB",
    "HANWHA": "HH",
    "KIA": "HT",
    "KIWOOM": "WO",
    "KT": "KT",
    "LG": "LG",
    "LOTTE": "LT",
    "NC": "NC",
    "SAMSUNG": "SS",
    "SSG": "SK",
}

# EN canonical code -> Kalshi KXKBOGAME ticker-blob team token (solved by cross-checking
# every 2026-07-04/05 cached ticker's home/away against its reconstructed blob; see
# module docstring). Widths are per-team natural abbreviations (2-4 chars), NOT fixed.
EN_TO_KALSHI: Dict[str, str] = {
    "DOOSAN": "DOO",
    "HANWHA": "HAN",
    "KIA": "KIA",
    "KIWOOM": "KIW",
    "KT": "KTW",
    "LG": "LG",
    "LOTTE": "LOT",
    "NC": "NCD",
    "SAMSUNG": "SAM",
    "SSG": "SSG",
}

# The results-parquet EN codes ARE the canonical keys above (verbatim, read straight off
# data/domains/kbo/kbo_results.parquet's home_team/away_team distinct values) -- kept as
# its own named alphabet (identity map) so assert_complete() checks all THREE alphabets
# by name, not two dicts plus an implicit third.
EN_TO_RESULTS: Dict[str, str] = {code: code for code in EN_TO_NAVER}

ALL_EN_CODES: FrozenSet[str] = frozenset(EN_TO_NAVER)

_NAVER_TO_EN: Dict[str, str] = {v: k for k, v in EN_TO_NAVER.items()}
_KALSHI_TO_EN: Dict[str, str] = {v: k for k, v in EN_TO_KALSHI.items()}


def naver_code_for(en_code: str) -> Optional[str]:
    """EN canonical code -> Naver 2-letter code, or None if unrecognized (EXACT match)."""
    return EN_TO_NAVER.get(str(en_code or "").strip().upper())


def kalshi_token_for(en_code: str) -> Optional[str]:
    """EN canonical code -> Kalshi ticker-blob token, or None if unrecognized (EXACT match)."""
    return EN_TO_KALSHI.get(str(en_code or "").strip().upper())


def en_from_naver(naver_code: str) -> Optional[str]:
    """Naver 2-letter code -> EN canonical code, or None if unrecognized (EXACT match)."""
    return _NAVER_TO_EN.get(str(naver_code or "").strip().upper())


def en_from_kalshi_token(token: str) -> Optional[str]:
    """Kalshi ticker-blob token -> EN canonical code, or None if unrecognized (EXACT match)."""
    return _KALSHI_TO_EN.get(str(token or "").strip().upper())


def assert_complete() -> None:
    """Raise AssertionError iff any of the 3 alphabets is missing a team or the 3
    dicts disagree on team COUNT. Intended for test-time use (never called from a
    production hot path) -- a bridge with a silently-incomplete alphabet is worse than
    one that fails loudly at import/test time."""
    en_keys = frozenset(EN_TO_NAVER)
    assert en_keys == frozenset(EN_TO_KALSHI), (
        "EN_TO_NAVER / EN_TO_KALSHI key sets differ: %s vs %s"
        % (sorted(en_keys), sorted(EN_TO_KALSHI)))
    assert en_keys == frozenset(EN_TO_RESULTS), (
        "EN_TO_NAVER / EN_TO_RESULTS key sets differ: %s vs %s"
        % (sorted(en_keys), sorted(EN_TO_RESULTS)))
    assert len(en_keys) == 10, "expected exactly 10 KBO teams, found %d" % len(en_keys)
    assert len(set(EN_TO_NAVER.values())) == 10, "duplicate Naver code detected"
    assert len(set(EN_TO_KALSHI.values())) == 10, "duplicate Kalshi token detected"


__all__ = [
    "EN_TO_NAVER", "EN_TO_KALSHI", "EN_TO_RESULTS", "ALL_EN_CODES",
    "naver_code_for", "kalshi_token_for", "en_from_naver", "en_from_kalshi_token",
    "assert_complete",
]
