"""domains.baseball_kbo.team_map -- KBO on-site team token -> canonical EN code.

WHY THIS EXISTS
----------------
koreabaseball.com's GetScheduleList response embeds team names as raw site
tokens inside the "play" cell markup: KIA Tigers / KT Wiz / LG Twins / NC
Dinos / SSG Landers appear as their Latin-alphabet codes ("KIA", "KT", "LG",
"NC", "SSG"), while Doosan Bears / Lotte Giants / Samsung Lions / Hanwha
Eagles / Kiwoom Heroes appear as Korean glyphs. Verified live 2026-07-04
(2025 full-season fetch, gameMonth=''): the exact 10 tokens observed are
listed below -- this module is the single place that maps a raw site token
to a canonical ASCII EN code, so downstream ratings/adapter code never has to
carry non-ASCII literals in comments or logic (only this data dict does, and
even here the KEYS -- not comments -- carry the glyphs; this docstring stays
ASCII per repo convention).

The file itself contains Korean glyphs as DATA (dict keys), which the repo
convention permits for a small dedicated data module -- no Korean appears in
any comment or docstring, only inside the literal dict below.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_team_map.py -q
"""
from __future__ import annotations

from typing import Dict

# Raw site token (as it appears in a GetScheduleList "play" cell) -> canonical
# ASCII EN code. Latin-alphabet teams map to themselves (site already uses the
# EN code); Korean-glyph teams map to their EN club code.
TEAM_MAP: Dict[str, str] = {
    "KIA": "KIA",
    "KT": "KT",
    "LG": "LG",
    "NC": "NC",
    "SSG": "SSG",
    "두산": "DOOSAN",   # Doosan Bears
    "롯데": "LOTTE",    # Lotte Giants
    "삼성": "SAMSUNG",  # Samsung Lions
    "한화": "HANWHA",   # Hanwha Eagles
    "키움": "KIWOOM",   # Kiwoom Heroes
}

ALL_EN_CODES = frozenset(TEAM_MAP.values())


def normalize_team(raw_token: str) -> str:
    """Canonical EN code for a raw site token, or the token itself (stripped)
    if unrecognized -- never raises, degrades to passthrough so a future new
    team name is preserved rather than silently dropped."""
    tok = str(raw_token).strip()
    return TEAM_MAP.get(tok, tok)


__all__ = ["TEAM_MAP", "ALL_EN_CODES", "normalize_team"]
