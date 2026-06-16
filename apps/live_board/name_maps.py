"""Map ESPN scoreboard names to our predictor-corpus identifiers.

Contract:
  to_corpus_id(sport, espn_name) -> str | None
    MLB:    ESPN displayName OR abbreviation -> our 30-team corpus abbrev.
    Soccer: ESPN displayName -> football-data club name (alias dict;
            default = passthrough title-case). National teams -> None.
    Tennis: passthrough (board hands the name to predictor._resolve,
            which returns None for unknown players).
  SUPPORTED_LEAGUES: per-sport ESPN league slugs the board may request.

All inputs are best-effort; never raise. Unknown / out-of-corpus -> None.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# Leagues the board is willing to query (ESPN slugs).
# --------------------------------------------------------------------------
SUPPORTED_LEAGUES = {
    "mlb": ["mlb"],
    "soccer": [
        "fifa.world",        # World Cup (out-of-corpus -> market-implied)
        "eng.1",             # Premier League
        "esp.1",             # La Liga
        "ita.1",             # Serie A
        "ger.1",             # Bundesliga
        "fra.1",             # Ligue 1
        "usa.1",             # MLS
        "uefa.champions",    # Champions League
    ],
    "tennis": ["atp", "wta"],
}

# --------------------------------------------------------------------------
# MLB: ESPN displayName AND ESPN abbreviation -> our corpus abbrev.
# Our corpus has 30 canonical franchises (the source list carries a few
# duplicate spellings: BRS, CUB, LOS, SFO -- we map each franchise to ONE
# canonical corpus abbrev below).
# --------------------------------------------------------------------------
_MLB_DISPLAYNAME = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Cleveland Indians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KAN",
    "Los Angeles Angels": "LAA",
    "Los Angeles Angels of Anaheim": "LAA",
    "Anaheim Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Florida Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Athletics": "OAK",
    "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SDG",
    "San Francisco Giants": "SFG",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "St Louis Cardinals": "STL",
    "Tampa Bay Rays": "TAM",
    "Tampa Bay Devil Rays": "TAM",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WAS",
}

# ESPN current abbreviation -> corpus abbrev (covers cases where only the
# abbreviation is available and it differs from our corpus spelling).
_MLB_ABBREV = {
    "ARI": "ARI", "ATL": "ATL", "BAL": "BAL", "BOS": "BOS",
    "CHC": "CHC", "CHW": "CWS", "CWS": "CWS", "CIN": "CIN",
    "CLE": "CLE", "COL": "COL", "DET": "DET", "HOU": "HOU",
    "KC": "KAN", "KAN": "KAN", "LAA": "LAA", "LAD": "LAD",
    "MIA": "MIA", "MIL": "MIL", "MIN": "MIN", "NYM": "NYM",
    "NYY": "NYY", "ATH": "OAK", "OAK": "OAK", "PHI": "PHI",
    "PIT": "PIT", "SD": "SDG", "SDG": "SDG", "SEA": "SEA",
    "SF": "SFG", "SFG": "SFG", "STL": "STL", "TB": "TAM",
    "TAM": "TAM", "TEX": "TEX", "TOR": "TOR", "WSH": "WAS",
    "WAS": "WAS",
}

# --------------------------------------------------------------------------
# Soccer: ESPN displayName -> football-data club name (only the deltas).
# Anything not listed passes through unchanged (most names match exactly).
# National teams (single-token country names) -> None: out of corpus.
# --------------------------------------------------------------------------
_SOCCER_ALIAS = {
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Manchester Utd": "Man United",
    "Wolverhampton Wanderers": "Wolves",
    "Wolverhampton": "Wolves",
    "Tottenham Hotspur": "Tottenham",
    "Newcastle United": "Newcastle",
    "Brighton & Hove Albion": "Brighton",
    "West Ham United": "West Ham",
    "Nottingham Forest": "Nottm Forest",
    "Sheffield United": "Sheffield United",
    "Leeds United": "Leeds",
    "Leicester City": "Leicester",
    "Norwich City": "Norwich",
    "Cardiff City": "Cardiff",
    "Stoke City": "Stoke",
    "Swansea City": "Swansea",
    "Hull City": "Hull",
    "Birmingham City": "Birmingham",
    "Atletico Madrid": "Ath Madrid",
    "Athletic Club": "Ath Bilbao",
    "Athletic Bilbao": "Ath Bilbao",
    "Real Betis": "Betis",
    "Real Sociedad": "Sociedad",
    "Celta Vigo": "Celta",
    "Deportivo Alaves": "Alaves",
    "Deportivo La Coruna": "La Coruna",
    "Rayo Vallecano": "Vallecano",
    "Real Valladolid": "Valladolid",
    "RCD Espanyol": "Espanol",
    "Espanyol": "Espanol",
    "Sporting Gijon": "Sp Gijon",
    "Bayern Munich": "Bayern Munich",
    "Borussia Dortmund": "Dortmund",
    "Borussia Monchengladbach": "M'gladbach",
    "Bayer Leverkusen": "Leverkusen",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "RB Leipzig": "RB Leipzig",
    "FC Koln": "FC Koln",
    "1. FC Koln": "FC Koln",
    "Cologne": "FC Koln",
    "TSG Hoffenheim": "Hoffenheim",
    "VfB Stuttgart": "Stuttgart",
    "VfL Wolfsburg": "Wolfsburg",
    "Werder Bremen": "Werder Bremen",
    "FC Augsburg": "Augsburg",
    "Mainz 05": "Mainz",
    "FSV Mainz 05": "Mainz",
    "FC Union Berlin": "Union Berlin",
    "Schalke 04": "Schalke 04",
    "Inter Milan": "Inter",
    "Internazionale": "Inter",
    "AC Milan": "Milan",
    "AS Roma": "Roma",
    "SSC Napoli": "Napoli",
    "Hellas Verona": "Verona",
    "Paris Saint-Germain": "Paris SG",
    "Olympique Lyonnais": "Lyon",
    "Olympique de Marseille": "Marseille",
    "AS Monaco": "Monaco",
    "AS Saint-Etienne": "St Etienne",
    "Saint-Etienne": "St Etienne",
    "LOSC Lille": "Lille",
}

# A small set of common country names so national sides (World Cup etc.)
# are reliably treated as out-of-corpus even when not a single token.
_COUNTRIES = {
    "united states", "usa", "england", "spain", "france", "germany",
    "italy", "brazil", "argentina", "portugal", "netherlands", "belgium",
    "croatia", "uruguay", "mexico", "canada", "japan", "south korea",
    "australia", "morocco", "senegal", "ghana", "nigeria", "cameroon",
    "iran", "iraq", "saudi arabia", "qatar", "switzerland", "denmark",
    "sweden", "norway", "poland", "serbia", "wales", "scotland",
    "ireland", "austria", "ukraine", "turkey", "greece", "colombia",
    "chile", "peru", "ecuador", "paraguay", "costa rica", "panama",
    "egypt", "tunisia", "algeria", "ivory coast", "south africa",
    "new zealand", "china", "india",
}


def _is_national_team(name: str) -> bool:
    # Conservative: only an explicit country name is treated as a national
    # side. (Single-word CLUB names like "Arsenal"/"Barcelona" are valid
    # corpus clubs, so we must not flag them by token count. World Cup
    # rows are already routed to market-implied via their league slug.)
    return name.strip().lower() in _COUNTRIES


def to_corpus_id(sport: str, espn_name):
    """ESPN name -> our corpus id, or None when out-of-corpus / invalid."""
    if not espn_name or not isinstance(espn_name, str):
        return None
    sport = (sport or "").lower()
    name = espn_name.strip()
    if not name:
        return None

    if sport == "mlb":
        if name in _MLB_DISPLAYNAME:
            return _MLB_DISPLAYNAME[name]
        up = name.upper()
        if up in _MLB_ABBREV:
            return _MLB_ABBREV[up]
        return None

    if sport == "soccer":
        if name in _SOCCER_ALIAS:
            return _SOCCER_ALIAS[name]
        if _is_national_team(name):
            return None
        # Passthrough: most club names match football-data exactly.
        return name

    if sport == "tennis":
        # Hand the raw name to predictor._resolve downstream.
        return name

    return None


if __name__ == "__main__":
    # SELF-TEST
    assert to_corpus_id("mlb", "Cincinnati Reds") == "CIN"
    assert to_corpus_id("mlb", "CIN") == "CIN"
    assert to_corpus_id("mlb", "KC") == "KAN"
    assert to_corpus_id("mlb", "SD") == "SDG"
    assert to_corpus_id("mlb", "Athletics") == "OAK"
    assert to_corpus_id("mlb", "Nonexistent Team") is None
    assert to_corpus_id("soccer", "Manchester City") == "Man City"
    assert to_corpus_id("soccer", "Arsenal") == "Arsenal"
    assert to_corpus_id("soccer", "Brazil") is None
    assert to_corpus_id("soccer", "United States") is None
    assert to_corpus_id("tennis", "Carlos Alcaraz") == "Carlos Alcaraz"
    assert to_corpus_id("mlb", None) is None
    assert to_corpus_id("mlb", "") is None
    assert "mlb" in SUPPORTED_LEAGUES and "fifa.world" in SUPPORTED_LEAGUES["soccer"]
    print("name_maps self-test PASSED")
