"""scripts.platformkit.odds_provider.team_resolver -- code<->name canonical keys.

Our NBA/MLB slates carry SHORT CODES ("BOS", "CIN") while the odds feed
(ESPN/Kalshi/Polymarket) carries FULL names ("Boston Celtics", "Cincinnati
Reds"). `canonical(sport, name)` collapses EITHER form to one stable key per
team (e.g. canonical("nba","BOS") == canonical("nba","Boston Celtics")), so the
strict aggregate.teams_match can compare resolved keys and finally link codes to
full names -- WITHOUT loosening the false-match guard.

Honesty contract: an UNKNOWN team degrades to a normalized fallback (its own
nickname token), never a crash and never a collision with a different team.
Sports without codes (soccer/tennis/world-cup) pass through unchanged via the
same normalize path, so their existing full-name matching is untouched.

Maps are static 30-team reference literals copied from the repo's authoritative
sources (NBA: src/data/odds_scraper.py; MLB: domains/mlb/ingest_current.py).
Re-defined here (not imported) to avoid importing the gated src/ tree.
"""
from __future__ import annotations

import re
from typing import Dict

# --------------------------------------------------------------------------- #
# NBA: code -> canonical nickname token; full-name nickname is the same token.
# (Authoritative 30-team set; mirrors src/data/odds_scraper.py.)
# --------------------------------------------------------------------------- #
_NBA_CODE_TO_NICK: Dict[str, str] = {
    "ATL": "hawks", "BOS": "celtics", "BKN": "nets", "CHA": "hornets",
    "CHI": "bulls", "CLE": "cavaliers", "DAL": "mavericks", "DEN": "nuggets",
    "DET": "pistons", "GSW": "warriors", "HOU": "rockets", "IND": "pacers",
    "LAC": "clippers", "LAL": "lakers", "MEM": "grizzlies", "MIA": "heat",
    "MIL": "bucks", "MIN": "timberwolves", "NOP": "pelicans", "NYK": "knicks",
    "OKC": "thunder", "ORL": "magic", "PHI": "76ers", "PHX": "suns",
    "POR": "trailblazers", "SAC": "kings", "SAS": "spurs", "TOR": "raptors",
    "UTA": "jazz", "WAS": "wizards",
}
# ESPN/alt code spellings -> our canonical NBA code (mirrors ingest_espn_odds._ALIAS).
_NBA_CODE_ALIASES: Dict[str, str] = {
    "GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS", "UTAH": "UTA",
    "WSH": "WAS", "BRK": "BKN", "PHO": "PHX", "CHO": "CHA", "NOR": "NOP",
}

# --------------------------------------------------------------------------- #
# MLB: code -> canonical nickname token (mirrors domains/mlb NAME_TO_CODE,
# inverted). Same-city pairs (CWS White Sox vs CUB Cubs) get DISTINCT tokens.
# --------------------------------------------------------------------------- #
_MLB_CODE_TO_NICK: Dict[str, str] = {
    "ARI": "diamondbacks", "ATL": "braves", "BAL": "orioles", "BOS": "redsox",
    "CUB": "cubs", "CWS": "whitesox", "CIN": "reds", "CLE": "guardians",
    "COL": "rockies", "DET": "tigers", "HOU": "astros", "KAN": "royals",
    "LAA": "angels", "LAD": "dodgers", "MIA": "marlins", "MIL": "brewers",
    "MIN": "twins", "NYM": "mets", "NYY": "yankees", "OAK": "athletics",
    "PHI": "phillies", "PIT": "pirates", "SDG": "padres", "SFO": "giants",
    "SEA": "mariners", "STL": "cardinals", "TAM": "rays", "TEX": "rangers",
    "TOR": "bluejays", "WAS": "nationals",
}
# Common alternate MLB codes -> our canonical code.
_MLB_CODE_ALIASES: Dict[str, str] = {
    "CHC": "CUB", "CHW": "CWS", "SD": "SDG", "SF": "SFO", "KC": "KAN",
    "TB": "TAM", "WSH": "WAS", "WSN": "WAS", "ARZ": "ARI", "LA": "LAD",
}

# Multi-word full-name nicknames that must collapse to a single token so a
# full name resolves to the SAME key as its code (e.g. "Red Sox" -> "redsox").
_NAME_NICK_FIXUPS = {
    ("nba", "trail blazers"): "trailblazers",
    ("mlb", "red sox"): "redsox",
    ("mlb", "white sox"): "whitesox",
    ("mlb", "blue jays"): "bluejays",
}

_CODE_TO_NICK = {"nba": _NBA_CODE_TO_NICK, "mlb": _MLB_CODE_TO_NICK}
_CODE_ALIASES = {"nba": _NBA_CODE_ALIASES, "mlb": _MLB_CODE_ALIASES}
_STOP = {"the", "fc", "afc", "cf", "sc"}


def _norm(name: str) -> str:
    """Lowercase, strip punctuation/stopwords -> space-joined tokens."""
    s = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    return " ".join(t for t in s.split() if t and t not in _STOP)


def canonical(sport: str, name: str) -> str:
    """Map a short code OR a full name to one canonical key per team.

    canonical("nba", "BOS") == canonical("nba", "Boston Celtics") == "nba:celtics".
    For sports without codes (soccer/tennis/world-cup) this is just the
    normalized full-name nickname token -- a pass-through that does not change
    their existing matching. Unknown input degrades to its normalized nickname
    token (never crashes, never collides with a known different team).
    """
    sp = str(sport).lower()
    raw = str(name).strip()
    norm = _norm(raw)
    if not norm:
        return f"{sp}:"

    code_map = _CODE_TO_NICK.get(sp)
    if code_map is not None:
        # 1) Pure short code (a single all-letters token like "BOS"/"CIN").
        if " " not in norm:
            up = raw.upper().strip()
            up = _CODE_ALIASES.get(sp, {}).get(up, up)
            if up in code_map:
                return f"{sp}:{code_map[up]}"
        # 2) Full name -> nickname token via explicit multi-word fixups...
        for (fsp, phrase), tok in _NAME_NICK_FIXUPS.items():
            if fsp == sp and phrase in norm:
                return f"{sp}:{tok}"
        # 3) ...else nickname = last significant token; keep only if it is a
        #    real nickname for this sport (so it converges with the code key).
        last = norm.split()[-1]
        if last in set(code_map.values()):
            return f"{sp}:{last}"

    # Fallback (sports without codes, or unknown team): normalized last token.
    return f"{sp}:{norm.split()[-1]}"


__all__ = ["canonical"]
