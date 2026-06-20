"""domains.basketball_nba.team_name_resolver -- slate->corpus team-name resolver for NBA.

ESPN scoreboard sends team names in several forms:
  displayName  "Boston Celtics", "Los Angeles Lakers", ...
  abbreviation "BOS", "LAL", "GS", "NY", "NO", "SA", "PHX", ...

The corpus (ESPN box score, proof_nba ml_accuracy Elo) uses a 3-letter
abbreviation set.  Most official ESPN abbreviations match the corpus directly
(BOS, LAL, etc.) but several differ:
  GS  -> GSW   (Golden State Warriors)
  NY  -> NYK   (New York Knicks)
  NO  -> NOP   (New Orleans Pelicans)
  SA  -> SAS   (San Antonio Spurs)
  PHX not PHO  (Phoenix Suns -- corpus uses PHX)
  UTA / UTAH   (Utah Jazz -- corpus uses UTA)
  BKN / BRK    (Brooklyn Nets -- corpus uses BKN)

This module provides:
  resolve(name) -> str | None
    Maps any ESPN slate name (displayName or abbreviation) to the corpus key.
    Returns None (unmatched) for names that cannot be resolved to an NBA
    franchise -- BIG3, exhibition, and G-League names return None.

  Callers MUST treat None as unmatched and signal unmatched=True rather than
  falling back to a league-init rating.

INVARIANTS: no $, no edge, calibration only; <=300 LOC.
"""
from __future__ import annotations

from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Canonical alias map: every known form -> corpus key
#
# Corpus keys (from proof_nba asof_box_accuracy):
#   ATL BKN BOS CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL
#   MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS
# ---------------------------------------------------------------------------
_ALIAS: Dict[str, str] = {
    # Atlanta Hawks
    "atlanta hawks": "ATL", "hawks": "ATL",
    "atlanta": "ATL", "atl": "ATL",
    # Brooklyn Nets
    "brooklyn nets": "BKN", "nets": "BKN",
    "brooklyn": "BKN", "bkn": "BKN", "brk": "BKN", "nj": "BKN",
    "new jersey nets": "BKN",
    # Boston Celtics
    "boston celtics": "BOS", "celtics": "BOS",
    "boston": "BOS", "bos": "BOS",
    # Charlotte Hornets
    "charlotte hornets": "CHA", "hornets": "CHA",
    "charlotte": "CHA", "cha": "CHA", "cho": "CHA",
    # Chicago Bulls
    "chicago bulls": "CHI", "bulls": "CHI",
    "chicago": "CHI", "chi": "CHI",
    # Cleveland Cavaliers
    "cleveland cavaliers": "CLE", "cavaliers": "CLE",
    "cleveland": "CLE", "cle": "CLE", "cavs": "CLE",
    # Dallas Mavericks
    "dallas mavericks": "DAL", "mavericks": "DAL",
    "dallas": "DAL", "dal": "DAL", "mavs": "DAL",
    # Denver Nuggets
    "denver nuggets": "DEN", "nuggets": "DEN",
    "denver": "DEN", "den": "DEN",
    # Detroit Pistons
    "detroit pistons": "DET", "pistons": "DET",
    "detroit": "DET", "det": "DET",
    # Golden State Warriors -- ESPN abbr GS
    "golden state warriors": "GSW", "warriors": "GSW",
    "golden state": "GSW", "gsw": "GSW", "gs": "GSW",
    # Houston Rockets
    "houston rockets": "HOU", "rockets": "HOU",
    "houston": "HOU", "hou": "HOU",
    # Indiana Pacers
    "indiana pacers": "IND", "pacers": "IND",
    "indiana": "IND", "ind": "IND",
    # Los Angeles Clippers
    "los angeles clippers": "LAC", "clippers": "LAC",
    "la clippers": "LAC", "lac": "LAC",
    # Los Angeles Lakers
    "los angeles lakers": "LAL", "lakers": "LAL",
    "la lakers": "LAL", "lal": "LAL",
    # Memphis Grizzlies
    "memphis grizzlies": "MEM", "grizzlies": "MEM",
    "memphis": "MEM", "mem": "MEM",
    # Miami Heat
    "miami heat": "MIA", "heat": "MIA",
    "miami": "MIA", "mia": "MIA",
    # Milwaukee Bucks
    "milwaukee bucks": "MIL", "bucks": "MIL",
    "milwaukee": "MIL", "mil": "MIL",
    # Minnesota Timberwolves
    "minnesota timberwolves": "MIN", "timberwolves": "MIN",
    "minnesota": "MIN", "min": "MIN",
    # New Orleans Pelicans -- ESPN abbr NO
    "new orleans pelicans": "NOP", "pelicans": "NOP",
    "new orleans": "NOP", "nop": "NOP", "no": "NOP",
    "new orleans hornets": "NOP",  # legacy
    # New York Knicks -- ESPN abbr NY
    "new york knicks": "NYK", "knicks": "NYK",
    "new york": "NYK", "nyk": "NYK", "ny": "NYK",
    # Oklahoma City Thunder
    "oklahoma city thunder": "OKC", "thunder": "OKC",
    "oklahoma city": "OKC", "okc": "OKC",
    # Orlando Magic
    "orlando magic": "ORL", "magic": "ORL",
    "orlando": "ORL", "orl": "ORL",
    # Philadelphia 76ers
    "philadelphia 76ers": "PHI", "76ers": "PHI",
    "philadelphia": "PHI", "phi": "PHI", "sixers": "PHI",
    # Phoenix Suns
    "phoenix suns": "PHX", "suns": "PHX",
    "phoenix": "PHX", "phx": "PHX", "pho": "PHX",
    # Portland Trail Blazers
    "portland trail blazers": "POR", "trail blazers": "POR",
    "portland": "POR", "por": "POR", "blazers": "POR",
    # Sacramento Kings
    "sacramento kings": "SAC", "kings": "SAC",
    "sacramento": "SAC", "sac": "SAC",
    # San Antonio Spurs -- ESPN abbr SA
    "san antonio spurs": "SAS", "spurs": "SAS",
    "san antonio": "SAS", "sas": "SAS", "sa": "SAS",
    # Toronto Raptors
    "toronto raptors": "TOR", "raptors": "TOR",
    "toronto": "TOR", "tor": "TOR",
    # Utah Jazz
    "utah jazz": "UTA", "jazz": "UTA",
    "utah": "UTA", "uta": "UTA", "utah jazz": "UTA",
    # Washington Wizards
    "washington wizards": "WAS", "wizards": "WAS",
    "washington": "WAS", "was": "WAS", "wsh": "WAS",
}

# Corpus keys that are valid -- used for identity fast-path
_CORPUS_KEYS = frozenset(_ALIAS.values())


def resolve(name: str) -> Optional[str]:
    """Map an ESPN slate team name to a corpus key.

    Returns the corpus key (str) on success, or None if the name cannot be
    resolved to any known NBA franchise.  Callers MUST treat None as unmatched
    and signal unmatched=True rather than falling back to a league-init rating.

    Case-insensitive; strips whitespace; handles displayName, official ESPN
    abbreviations, and corpus-native keys.  BIG3 and exhibition names return None.
    """
    if not isinstance(name, str) or not name.strip():
        return None
    key = name.strip().lower()
    return _ALIAS.get(key)


def is_corpus_key(key: str) -> bool:
    """Return True if the string is already a valid corpus key (no resolution needed)."""
    return key.upper() in _CORPUS_KEYS
