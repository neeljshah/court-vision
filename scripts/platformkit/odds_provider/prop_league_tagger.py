"""scripts.platformkit.odds_provider.prop_league_tagger -- PropLine league labeler.

PROBLEM: Underdog Fantasy maps ALL basketball sport_ids to 'BASKETBALL' -- so
NBA, BIG3 (3-on-3 league), and exhibition players all surface tagged sport='nba'
when we filter on that sport_id. During the NBA off-season BIG3 props appear (e.g.
'Houston Rig Hands @ Chicago Triplets'; players like Brandon Moss, Dwight Howard,
Corey Brewer) and consumers must NOT treat them as genuine NBA lines.

SOLUTION: A pure, network-free tagger that stamps a 'league' label on each PropLine
row by matching known BIG3 team tokens against the match/team fields, and known
BIG3 player tokens against the player field.

Output contract:
  league='nba'       -- match/team resolves to a real NBA franchise
  league='big3'      -- match/team or player matches a BIG3 roster/team token
  league='unknown'   -- no match on either side; never silently 'nba'

Design:
  * Pure (no network, no I/O).
  * Input PropLine rows are NEVER mutated -- caller receives new dicts or tagged copies.
  * No $ field; no edge claim; sport field is unchanged.
  * Token match is case-insensitive; single-word fragments only (avoid partial hits
    like 'Power' matching 'Empowerment').
  * NBA franchise matching uses the canonical 30-team set (city OR nickname).
  * BIG3 tokens are sourced from the publicly known BIG3 team/franchise list (2024+)
    plus confirmed player roster fragments from QA observations.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .prop_base import PropLine

# ---------------------------------------------------------------------------
# NBA franchise tokens -- city OR nickname (single word preferred; multi-word
# nicknames use their most distinctive word to avoid spurious hits).
# 30 NBA teams as of 2024-25 season.
# ---------------------------------------------------------------------------
_NBA_TOKENS: frozenset = frozenset({
    # Atlantic
    "celtics", "nets", "knicks", "76ers", "sixers", "raptors",
    # Central
    "bulls", "cavaliers", "cavs", "pistons", "pacers", "bucks",
    # Southeast
    "hawks", "hornets", "heat", "magic", "wizards",
    # Northwest
    "nuggets", "timberwolves", "wolves", "thunder", "blazers",
    "trailblazers", "jazz",
    # Pacific
    "warriors", "clippers", "lakers", "suns", "kings",
    # Southwest
    "mavericks", "mavs", "rockets", "grizzlies", "pelicans", "spurs",
    # City names that are distinctive enough
    "boston", "brooklyn", "toronto", "chicago", "cleveland",
    "detroit", "indiana", "milwaukee", "atlanta", "charlotte",
    "miami", "orlando", "washington", "denver", "minnesota",
    "oklahoma", "portland", "utah", "golden", "memphis",
    "new orleans", "san antonio", "dallas", "houston", "phoenix",
    "sacramento", "los angeles",
})

# ---------------------------------------------------------------------------
# BIG3 team tokens -- franchise nicknames and city prefixes that appear in
# Underdog's matchup strings. Sourced from the BIG3 public team list (2024+)
# confirmed via QA_FEED 2026-06-19 (Rig Hands, Triplets observed live).
# We use the MOST DISTINCTIVE part of each name to avoid collision with NBA.
# ---------------------------------------------------------------------------
_BIG3_TEAM_TOKENS: frozenset = frozenset({
    # Confirmed from QA_FEED (2026-06-19)
    "rig hands",       # Houston Rig Hands
    "triplets",        # Chicago Triplets / Triplets (BIG3)
    # Known BIG3 franchises 2018-2024
    "trilogy",
    "tri state",
    "tri-state",
    "ghost ballers",
    "ball hogs",
    "3 headed monsters",
    "aliens",
    "bivouac",
    "cold as ice",
    "beasts",
    "killer 3s",
    "killer3s",
    "halfcourt mafia",
    "half court mafia",
    "enemies",
})

# BIG3 player tokens -- confirmed from QA_FEED. Case-folded full names or
# distinctive last names (last name alone only when rare enough not to match
# active NBA players).
_BIG3_PLAYER_TOKENS: frozenset = frozenset({
    # Confirmed from QA_FEED (2026-06-19)
    "brandon moss",
    "dwight howard",
    "corey brewer",
})


def _tokens_from(text: Optional[str]) -> str:
    """Return lowercased stripped text for token search, or empty string."""
    if not text:
        return ""
    return " ".join(str(text).strip().lower().split())


def _hits_any(haystack: str, token_set: frozenset) -> bool:
    """True iff any token in token_set appears in haystack as a substring."""
    for tok in token_set:
        if tok in haystack:
            return True
    return False


def tag_league(row: PropLine) -> str:
    """Return 'nba', 'big3', or 'unknown' for a single PropLine.

    Checks the match (matchup title) and team fields against BIG3 team tokens
    and the player field against BIG3 player tokens. NBA franchise tokens are
    checked ONLY in match/team, not player (player names are not NBA-exclusive).

    Precedence:
      1. If match or team contains a BIG3 team token -> 'big3'
      2. Else if player contains a BIG3 player token -> 'big3'
      3. Else if match or team contains an NBA franchise token -> 'nba'
      4. Else -> 'unknown'

    The sport field is never examined or changed; this tagger is purely additive.
    """
    match_text = _tokens_from(row.match)
    team_text = _tokens_from(row.team)
    player_text = _tokens_from(row.player)

    # Step 1: BIG3 team token in match or team field
    if _hits_any(match_text, _BIG3_TEAM_TOKENS) or _hits_any(team_text, _BIG3_TEAM_TOKENS):
        return "big3"

    # Step 2: BIG3 player name
    if _hits_any(player_text, _BIG3_PLAYER_TOKENS):
        return "big3"

    # Step 3: NBA franchise token in match or team field
    if _hits_any(match_text, _NBA_TOKENS) or _hits_any(team_text, _NBA_TOKENS):
        return "nba"

    # Step 4: unknown -- never silently 'nba'
    return "unknown"


def tag_rows(rows: Sequence[PropLine]) -> List[Dict]:
    """Tag a list of PropLine rows; return list of dicts with 'league' added.

    The original PropLine objects are NEVER mutated. The returned dicts are
    PropLine.to_dict() output with a 'league' key appended. Input rows that
    are not PropLine instances are skipped (defensive; never raises).
    """
    out: List[Dict] = []
    for row in rows:
        if not isinstance(row, PropLine):
            continue
        d = row.to_dict()
        d["league"] = tag_league(row)
        out.append(d)
    return out


__all__ = ["tag_league", "tag_rows", "_NBA_TOKENS", "_BIG3_TEAM_TOKENS", "_BIG3_PLAYER_TOKENS"]
