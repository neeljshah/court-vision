"""domains.mlb.team_name_resolver -- slate->corpus team-name resolver for MLB.

ESPN scoreboard sends team names in several forms:
  displayName  "New York Yankees", "Boston Red Sox", ...
  abbreviation "NYY", "BOS", "KC", "TB", "SF", "SD", ...

The corpus (data/domains/mlb/games.parquet, beat_the_close_ml Elo ratings) uses
a NON-STANDARD abbreviation set that differs from official ESPN abbreviations in
several cases (e.g. KAN for Royals, TAM for Rays, SFO/SFG for Giants, CUB/CHC
for Cubs, LOS/LAD for Dodgers).

This module provides:
  resolve(name) -> str | None
    Maps any ESPN slate name (displayName or abbreviation) to the corpus key.
    Returns None (unmatched) if the name cannot be resolved -- signals the
    predictor to emit unmatched=True rather than fall back to a fabricated
    init-rating probability.

  BIG3/exhibition exclusion: names that cannot map to an MLB franchise return
  None rather than silently collapsing to the league-init constant.

INVARIANTS: no $, no edge, calibration only; <=300 LOC.
"""
from __future__ import annotations

from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Canonical alias map: every known form -> corpus key
#
# Structure: all values are keys that actually appear in games.parquet.
# Sources covered:
#   - ESPN displayName (full franchise names, city-only variants)
#   - ESPN abbreviation (official, e.g. KC, TB, SF, SD, WSH)
#   - Corpus-native keys (self-referential; identity entries for safety)
# ---------------------------------------------------------------------------
_ALIAS: Dict[str, str] = {
    # Arizona Diamondbacks
    "arizona diamondbacks": "ARI", "diamondbacks": "ARI",
    "arizona": "ARI", "ari": "ARI",
    # Atlanta Braves
    "atlanta braves": "ATL", "braves": "ATL",
    "atlanta": "ATL", "atl": "ATL",
    # Baltimore Orioles
    "baltimore orioles": "BAL", "orioles": "BAL",
    "baltimore": "BAL", "bal": "BAL",
    # Boston Red Sox
    "boston red sox": "BOS", "red sox": "BOS",
    "boston": "BOS", "bos": "BOS",
    # Chicago Cubs -- corpus has both CUB and CHC variants
    "chicago cubs": "CHC", "cubs": "CHC",
    "chc": "CHC", "cub": "CHC",
    # Chicago White Sox
    "chicago white sox": "CWS", "white sox": "CWS",
    "cws": "CWS",
    # Cincinnati Reds
    "cincinnati reds": "CIN", "reds": "CIN",
    "cincinnati": "CIN", "cin": "CIN",
    # Cleveland Guardians (and legacy Indians)
    "cleveland guardians": "CLE", "guardians": "CLE",
    "cleveland indians": "CLE", "indians": "CLE",
    "cleveland": "CLE", "cle": "CLE",
    # Colorado Rockies
    "colorado rockies": "COL", "rockies": "COL",
    "colorado": "COL", "col": "COL",
    # Detroit Tigers
    "detroit tigers": "DET", "tigers": "DET",
    "detroit": "DET", "det": "DET",
    # Houston Astros
    "houston astros": "HOU", "astros": "HOU",
    "houston": "HOU", "hou": "HOU",
    # Kansas City Royals -- corpus key KAN; ESPN abbr KC
    "kansas city royals": "KAN", "royals": "KAN",
    "kansas city": "KAN", "kc": "KAN", "kan": "KAN",
    # Los Angeles Angels
    "los angeles angels": "LAA", "angels": "LAA",
    "laa": "LAA", "ana": "LAA",
    # Los Angeles Dodgers -- corpus has both LOS and LAD
    "los angeles dodgers": "LAD", "dodgers": "LAD",
    "lad": "LAD", "los": "LAD",
    # Miami Marlins
    "miami marlins": "MIA", "marlins": "MIA",
    "miami": "MIA", "mia": "MIA",
    # Milwaukee Brewers
    "milwaukee brewers": "MIL", "brewers": "MIL",
    "milwaukee": "MIL", "mil": "MIL",
    # Minnesota Twins
    "minnesota twins": "MIN", "twins": "MIN",
    "minnesota": "MIN", "min": "MIN",
    # New York Mets
    "new york mets": "NYM", "mets": "NYM",
    "nym": "NYM",
    # New York Yankees
    "new york yankees": "NYY", "yankees": "NYY",
    "nyy": "NYY",
    # Oakland Athletics / Sacramento (legacy Oakland)
    "oakland athletics": "OAK", "athletics": "OAK",
    "oakland": "OAK", "oak": "OAK",
    "sacramento river cats": "OAK",  # temporary branding
    "las vegas athletics": "OAK",
    # Philadelphia Phillies
    "philadelphia phillies": "PHI", "phillies": "PHI",
    "philadelphia": "PHI", "phi": "PHI",
    # Pittsburgh Pirates
    "pittsburgh pirates": "PIT", "pirates": "PIT",
    "pittsburgh": "PIT", "pit": "PIT",
    # San Diego Padres -- corpus key SDG; ESPN abbr SD
    "san diego padres": "SDG", "padres": "SDG",
    "san diego": "SDG", "sd": "SDG", "sdg": "SDG", "sdp": "SDG",
    # Seattle Mariners
    "seattle mariners": "SEA", "mariners": "SEA",
    "seattle": "SEA", "sea": "SEA",
    # San Francisco Giants -- corpus has SFG and SFO
    "san francisco giants": "SFG", "giants": "SFG",
    "san francisco": "SFG", "sf": "SFG", "sfg": "SFG", "sfo": "SFG",
    # St. Louis Cardinals
    "st. louis cardinals": "STL", "st louis cardinals": "STL",
    "cardinals": "STL", "st. louis": "STL", "st louis": "STL",
    "stl": "STL",
    # Tampa Bay Rays -- corpus key TAM; ESPN abbr TB
    "tampa bay rays": "TAM", "rays": "TAM",
    "tampa bay": "TAM", "tb": "TAM", "tam": "TAM", "tbr": "TAM",
    # Texas Rangers
    "texas rangers": "TEX", "rangers": "TEX",
    "texas": "TEX", "tex": "TEX",
    # Toronto Blue Jays
    "toronto blue jays": "TOR", "blue jays": "TOR",
    "toronto": "TOR", "tor": "TOR",
    # Washington Nationals -- corpus key WAS; ESPN abbr WSH
    "washington nationals": "WAS", "nationals": "WAS",
    "washington": "WAS", "wsh": "WAS", "was": "WAS",
    # BRS -- legacy/minor corpus artifact (Brooklyn/historical); keep identity
    "brs": "BRS",
}

# Corpus keys that are known valid -- used for identity fast-path
_CORPUS_KEYS = frozenset(_ALIAS.values())


def resolve(name: str) -> Optional[str]:
    """Map an ESPN slate team name to a corpus key.

    Returns the corpus key (str) on success, or None if the name cannot be
    resolved to any known MLB franchise.  Callers MUST treat None as unmatched
    and signal unmatched=True rather than falling back to a league-init rating.

    Case-insensitive; strips whitespace; handles displayName, official ESPN
    abbreviations, and corpus-native keys.
    """
    if not isinstance(name, str) or not name.strip():
        return None
    key = name.strip().lower()
    return _ALIAS.get(key)


def is_corpus_key(key: str) -> bool:
    """Return True if the string is already a valid corpus key (no resolution needed)."""
    return key.upper() in _CORPUS_KEYS
