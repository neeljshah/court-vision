"""Static NBA abbreviation <-> numeric team_id map.

Copied (not imported) from api/courtvision_router.py's `_STATIC_ABBREV_TO_ID` --
api/** is a human-gated path this lane must not import or edit, and this is a
small, stable, public reference table (NBA franchise IDs), so duplicating the
30-line literal here is cheaper and safer than reaching into the gated router
module. If the router's table ever changes, update both by hand.
"""
from __future__ import annotations

from typing import Dict, Optional

ABBR_TO_TEAM_ID: Dict[str, int] = {
    "ATL": 1610612737, "BKN": 1610612751, "BOS": 1610612738, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}
TEAM_ID_TO_ABBR: Dict[int, str] = {v: k for k, v in ABBR_TO_TEAM_ID.items()}

# NBA code -> full franchise name, for matching against edge_engine's injury/news
# jsonl stores (those carry the full name, e.g. "Oklahoma City Thunder").
ABBR_TO_FULLNAME: Dict[str, str] = {
    "ATL": "Atlanta Hawks", "BKN": "Brooklyn Nets", "BOS": "Boston Celtics",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}


def team_id_for(abbr: str) -> Optional[int]:
    return ABBR_TO_TEAM_ID.get(str(abbr).upper())


def fullname_for(abbr: str) -> Optional[str]:
    return ABBR_TO_FULLNAME.get(str(abbr).upper())


def is_known_abbr(abbr: str) -> bool:
    return str(abbr).upper() in ABBR_TO_TEAM_ID
