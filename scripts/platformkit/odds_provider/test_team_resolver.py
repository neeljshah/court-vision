"""Per-file tests for the code<->name team resolver + its aggregate wiring.

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_team_resolver.py -q

NETWORK-FREE. Asserts canonical() collapses code==fullname for NBA + MLB, that
teams_match links codes to full names once sport is threaded through, and that
genuinely DIFFERENT teams (same-city pairs) still do NOT match. Also confirms
soccer/tennis (no codes) pass through unchanged and unknown teams degrade.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider import aggregate
from scripts.platformkit.odds_provider.team_resolver import canonical


# --------------------------------------------------------------------------- #
# canonical(): code and full name collapse to the same key.
# --------------------------------------------------------------------------- #
def test_canonical_nba_code_equals_fullname():
    for code, full in [("BOS", "Boston Celtics"), ("LAL", "Los Angeles Lakers"),
                       ("NYK", "New York Knicks"), ("GSW", "Golden State Warriors"),
                       ("POR", "Portland Trail Blazers"), ("PHI", "Philadelphia 76ers")]:
        assert canonical("nba", code) == canonical("nba", full), (code, full)


def test_canonical_mlb_code_equals_fullname():
    for code, full in [("CIN", "Cincinnati Reds"), ("BOS", "Boston Red Sox"),
                       ("NYM", "New York Mets"), ("NYY", "New York Yankees"),
                       ("CWS", "Chicago White Sox"), ("CUB", "Chicago Cubs"),
                       ("SFO", "San Francisco Giants"), ("TOR", "Toronto Blue Jays")]:
        assert canonical("mlb", code) == canonical("mlb", full), (code, full)


def test_canonical_distinguishes_different_teams():
    # Same city, different team -> distinct keys.
    assert canonical("nba", "New York Knicks") != canonical("nba", "Brooklyn Nets")
    assert canonical("mlb", "Chicago White Sox") != canonical("mlb", "Chicago Cubs")
    # NBA BOS (Celtics) and MLB BOS (Red Sox) are namespaced by sport -> distinct.
    assert canonical("nba", "BOS") != canonical("mlb", "BOS")


def test_canonical_code_aliases():
    assert canonical("nba", "GS") == canonical("nba", "Golden State Warriors")
    assert canonical("nba", "NY") == canonical("nba", "New York Knicks")
    assert canonical("mlb", "CHC") == canonical("mlb", "Chicago Cubs")
    assert canonical("mlb", "SF") == canonical("mlb", "San Francisco Giants")


def test_canonical_soccer_tennis_passthrough_and_unknown_degrade():
    # No codes for soccer/tennis: pure normalized pass-through (no crash).
    assert canonical("soccer", "Manchester City") == "soccer:city"
    assert canonical("tennis", "Carlos Alcaraz") == "tennis:alcaraz"
    # Unknown NBA token degrades to its own nickname token, never crashes.
    assert canonical("nba", "Fake Town Aliens") == "nba:aliens"
    assert canonical("nba", "") == "nba:"


def test_canonical_kbo_kalshi_fullname_equals_parquet_code():
    # LANE 4: Kalshi's ODDS FEED (yes_sub_title / title) carries each club's
    # FULL English name ("NC Dinos"), verified live 2026-07-06 direct against
    # /trade-api/v2/markets?series_ticker=KXKBOGAME -- NOT the ticker's 3-letter
    # tail code. canonical() must collapse the full name to the SAME key as
    # the parquet's own ASCII EN spelling for all 10 real clubs.
    for full_name, parquet_code in [
        ("NC Dinos", "NC"), ("Kia Tigers", "KIA"), ("Lotte Giants", "LOTTE"),
        ("KT Wiz", "KT"), ("Samsung Lions", "SAMSUNG"), ("SSG Landers", "SSG"),
        ("LG Twins", "LG"), ("Hanwha Eagles", "HANWHA"),
        ("Kiwoom Heroes", "KIWOOM"), ("Doosan Bears", "DOOSAN")]:
        assert canonical("kbo", full_name) == canonical("kbo", parquet_code), \
            (full_name, parquet_code)


# --------------------------------------------------------------------------- #
# NPB (LANE 2): Kalshi full English name <-> parquet kanji/katakana club name.
# --------------------------------------------------------------------------- #
# All 12 real NPB clubs: (Kalshi yes_sub_title/title full English name,
# npb_results.parquet's exact team-name spelling). Verified live 2026-07-06
# direct against /trade-api/v2/markets?series_ticker=KXNPBGAME (both open and
# settled markets) AND cross-checked against the parquet's own distinct
# home_team/away_team strings + npb_outcome_resolver._CODE_TO_NAME.
_NPB_FULLNAME_KANJI_PAIRS = [
    ("Yokohama DeNA BayStars", "DeNA"),
    ("Tokyo Yakult Swallows", "ヤクルト"),
    ("Hiroshima Toyo Carp", "広島"),
    ("Hanshin Tigers", "阪神"),
    ("Hokkaido Nippon-Ham Fighters", "日本ハム"),
    ("Tohoku Rakuten Golden Eagles", "楽天"),
    ("Saitama Seibu Lions", "西武"),
    ("Orix Buffaloes", "オリックス"),
    ("Fukuoka Hawks", "ソフトバンク"),
    ("Chiba Lotte Marines", "ロッテ"),
    ("Yomiuri Giants", "巨人"),
    ("Chunichi Dragons", "中日"),
]


def test_canonical_npb_kalshi_fullname_equals_parquet_kanji():
    # LANE 2: Kalshi's ODDS FEED carries each club's FULL English name; the
    # local parquet stores the npb.jp scrape's native kanji/katakana spelling.
    # canonical() must collapse both forms to the SAME key for all 12 clubs.
    for full_name, kanji in _NPB_FULLNAME_KANJI_PAIRS:
        assert canonical("npb", full_name) == canonical("npb", kanji), \
            (full_name, kanji)


def test_canonical_npb_zero_cross_club_collisions():
    # Exhaustive 12x12 (132 ordered off-diagonal pairs): no two DIFFERENT NPB
    # clubs may ever resolve to the same canonical key (would mean a false
    # odds-attachment between two different real games).
    kanjis = [k for _, k in _NPB_FULLNAME_KANJI_PAIRS]
    n_checked = 0
    for i, ki in enumerate(kanjis):
        for j, kj in enumerate(kanjis):
            if i == j:
                continue
            n_checked += 1
            assert canonical("npb", ki) != canonical("npb", kj), (ki, kj)
    assert n_checked == 12 * 11 == 132


def test_canonical_npb_unknown_team_degrades_no_crash():
    # An unresolvable NPB name must degrade honestly, never crash or collide
    # with a real club.
    key = canonical("npb", "Fake Town Aliens")
    assert key not in {canonical("npb", k) for _, k in _NPB_FULLNAME_KANJI_PAIRS}
    assert canonical("npb", "") == "npb:"


# --------------------------------------------------------------------------- #
# WNBA (LANE 1): Kalshi CITY-only label ("Las Vegas") <-> ESPN full franchise
# name ("Las Vegas Aces"). GROUNDED live 2026-07-03 direct against the Kalshi
# public API (KXWNBAGAME open + settled markets) and against the local
# data/domains/wnba/espn_scoreboard.parquet -- see team_resolver.py's own
# module note for the full derivation.
# --------------------------------------------------------------------------- #
_WNBA_CITY_FULLNAME_PAIRS = [
    ("Atlanta", "Atlanta Dream"), ("Chicago", "Chicago Sky"),
    ("Connecticut", "Connecticut Sun"), ("Dallas", "Dallas Wings"),
    ("Golden State", "Golden State Valkyries"), ("Indiana", "Indiana Fever"),
    ("Las Vegas", "Las Vegas Aces"), ("Los Angeles", "Los Angeles Sparks"),
    ("Minnesota", "Minnesota Lynx"), ("New York", "New York Liberty"),
    ("Portland", "Portland Fire"), ("Phoenix", "Phoenix Mercury"),
    ("Seattle", "Seattle Storm"), ("Toronto", "Toronto Tempo"),
    ("Washington", "Washington Mystics"),
]


def test_canonical_wnba_kalshi_city_equals_espn_fullname():
    for city, full in _WNBA_CITY_FULLNAME_PAIRS:
        assert canonical("wnba", city) == canonical("wnba", full), (city, full)


def test_canonical_wnba_zero_cross_franchise_collisions():
    # Exhaustive 15x15 (210 ordered off-diagonal pairs): no two DIFFERENT WNBA
    # franchises may ever resolve to the same canonical key (would mean a
    # false odds-attachment between two different real games). Specifically
    # covers the city-word-overlap worry: Los Angeles vs Las Vegas (both
    # start "L"), New York vs Golden State/others.
    cities = [c for c, _ in _WNBA_CITY_FULLNAME_PAIRS]
    n_checked = 0
    for i, ci in enumerate(cities):
        for j, cj in enumerate(cities):
            if i == j:
                continue
            n_checked += 1
            assert canonical("wnba", ci) != canonical("wnba", cj), (ci, cj)
    assert n_checked == 15 * 14 == 210
    # Explicit call-out: Los Angeles vs Las Vegas must be distinct.
    assert canonical("wnba", "Los Angeles") != canonical("wnba", "Las Vegas")
    assert canonical("wnba", "Los Angeles Sparks") != canonical("wnba", "Las Vegas Aces")


def test_canonical_wnba_non_franchise_noise_never_collides():
    # Exhibition / all-star / national-team rows seen live in BOTH feeds
    # (Kalshi: "Japan National Team", "Nigeria National Team"; ESPN: Brazil,
    # JAPAN, NIGERIA, Puerto Rico, Team USA, Team WNBA, TEAM CLARK, TEAM
    # COLLIER, Toyota Antelopes) must never resolve to a real franchise key.
    real_keys = {canonical("wnba", c) for c, _ in _WNBA_CITY_FULLNAME_PAIRS}
    noise = ["Japan National Team", "Nigeria National Team", "Brazil", "JAPAN",
             "NIGERIA", "Puerto Rico", "Team USA", "Team WNBA", "TEAM CLARK",
             "TEAM COLLIER", "Toyota Antelopes"]
    for n in noise:
        assert canonical("wnba", n) not in real_keys, n


def test_teams_match_wnba_kalshi_city_links_and_rejects_wrong_pair():
    # LANE 1: the Kalshi city-only label vs ESPN full-name WNBA link.
    assert aggregate.teams_match("Las Vegas", "Las Vegas Aces", "wnba")
    assert aggregate.teams_match("New York", "New York Liberty", "wnba")
    assert aggregate.teams_match("Golden State", "Golden State Valkyries", "wnba")
    assert aggregate.teams_match("Toronto", "Toronto Tempo", "wnba")
    # Los Angeles vs Las Vegas: both start "L", must NOT match.
    assert not aggregate.teams_match("Los Angeles", "Las Vegas", "wnba")
    assert not aggregate.teams_match("Los Angeles Sparks", "Las Vegas Aces", "wnba")
    # A wrong pair must NOT match (never a mispriced game).
    assert not aggregate.teams_match("New York", "Golden State", "wnba")
    assert aggregate.teams_match("Chicago", "Chicago Sky", "wnba")


def test_lookup_links_city_slate_to_fullname_feed_wnba():
    # LANE 1: this is the exact live shape -- Kalshi's odds FEED event carries
    # the CITY-only label; our ESPN-derived slate probes with the full name.
    from scripts.platformkit.odds_provider.base import OddsEvent
    feed = OddsEvent("e5", "wnba", "Las Vegas", "Chicago", None,
                     {"kalshi": {"home": 1.5, "away": 2.6}})
    probe = OddsEvent("", "wnba", "Las Vegas Aces", "Chicago Sky", None, {})
    assert aggregate._event_match(feed, probe)
    # A different WNBA matchup must NOT link.
    other = OddsEvent("", "wnba", "Indiana Fever", "Dallas Wings", None, {})
    assert not aggregate._event_match(feed, other)


# --------------------------------------------------------------------------- #
# teams_match(): codes now link to full names, different teams still do not.
# --------------------------------------------------------------------------- #
def test_teams_match_links_code_to_fullname():
    assert aggregate.teams_match("BOS", "Boston Celtics", "nba")
    assert aggregate.teams_match("Boston Celtics", "BOS", "nba")
    assert aggregate.teams_match("CIN", "Cincinnati Reds", "mlb")
    assert aggregate.teams_match("LAL", "Los Angeles Lakers", "nba")


def test_teams_match_rejects_different_teams():
    # Different teams must NOT match even with sport threaded through.
    assert not aggregate.teams_match("New York Knicks", "New York Nets", "nba")
    assert not aggregate.teams_match("NYK", "Brooklyn Nets", "nba")
    assert not aggregate.teams_match("Chicago White Sox", "Chicago Cubs", "mlb")
    assert not aggregate.teams_match("CWS", "CHC", "mlb")
    # Cross-team code/name pair stays unmatched.
    assert not aggregate.teams_match("BOS", "Los Angeles Lakers", "nba")
    # NBA BOS code vs MLB Red Sox full name (wrong sport) does not match.
    assert not aggregate.teams_match("BOS", "Cincinnati Reds", "mlb")


def test_teams_match_soccer_strict_name_unchanged():
    # Soccer has no codes -> still the strict name rule (no false links).
    assert aggregate.teams_match("Manchester City", "Manchester City", "soccer")
    assert not aggregate.teams_match("Manchester City", "Manchester United", "soccer")
    assert aggregate.teams_match("San Antonio Spurs", "Spurs", "soccer")  # subset rule


def test_teams_match_kbo_kalshi_fullname_links_and_rejects_wrong_pair():
    # LANE 4: the Kalshi full-name vs parquet-code KBO link (this lane's fix).
    assert aggregate.teams_match("NC Dinos", "NC", "kbo")
    assert aggregate.teams_match("KT Wiz", "KT", "kbo")
    assert aggregate.teams_match("Hanwha Eagles", "HANWHA", "kbo")
    # A wrong pair must NOT match (never a mispriced game).
    assert not aggregate.teams_match("NC Dinos", "KIA", "kbo")
    assert not aggregate.teams_match("Hanwha Eagles", "KT", "kbo")


def test_teams_match_npb_kalshi_fullname_links_and_rejects_wrong_pair():
    # LANE 2: the Kalshi full-name vs parquet-kanji NPB link (this lane's fix).
    assert aggregate.teams_match("Hanshin Tigers", "阪神", "npb")
    assert aggregate.teams_match("Yomiuri Giants", "巨人", "npb")
    assert aggregate.teams_match("Yokohama DeNA BayStars", "DeNA", "npb")
    assert aggregate.teams_match("Hokkaido Nippon-Ham Fighters", "日本ハム", "npb")
    # A wrong pair must NOT match (never a mispriced game).
    assert not aggregate.teams_match("Hanshin Tigers", "巨人", "npb")
    assert not aggregate.teams_match("Hokkaido Nippon-Ham Fighters", "楽天", "npb")


# --------------------------------------------------------------------------- #
# to_odds_lookup-style probe: a coded slate now links to a full-name feed event.
# --------------------------------------------------------------------------- #
def test_lookup_links_code_slate_to_fullname_feed_nba():
    from scripts.platformkit.odds_provider.base import OddsEvent
    # Feed event uses FULL names; slate probes with CODES.
    feed = OddsEvent("e1", "nba", "Boston Celtics", "Los Angeles Lakers", None,
                     {"kalshi": {"home": 1.67, "away": 2.22}})
    probe = OddsEvent("", "nba", "BOS", "LAL", None, {})
    assert aggregate._event_match(feed, probe)
    # A different game does NOT link.
    other = OddsEvent("", "nba", "NYK", "BKN", None, {})
    assert not aggregate._event_match(feed, other)


def test_lookup_links_code_slate_to_fullname_feed_mlb():
    from scripts.platformkit.odds_provider.base import OddsEvent
    feed = OddsEvent("e2", "mlb", "Cincinnati Reds", "New York Mets", None,
                     {"espn:DraftKings": {"home": 1.8, "away": 2.0}})
    probe = OddsEvent("", "mlb", "CIN", "NYM", None, {})
    assert aggregate._event_match(feed, probe)
    # Same-city different team (Cubs vs White Sox) must NOT collide.
    cubs = OddsEvent("e3", "mlb", "Chicago Cubs", "Cincinnati Reds", None, {})
    sox = OddsEvent("", "mlb", "CWS", "CIN", None, {})
    assert not aggregate._event_match(cubs, sox)


def test_lookup_links_kanji_slate_to_fullname_feed_npb():
    # LANE 2: this is the exact live shape -- Kalshi's odds FEED event carries
    # the FULL English name; our parquet-derived slate probes with kanji.
    from scripts.platformkit.odds_provider.base import OddsEvent
    feed = OddsEvent("e4", "npb", "Hanshin Tigers", "Yomiuri Giants", None,
                     {"kalshi": {"home": 1.9, "away": 1.95}})
    probe = OddsEvent("", "npb", "阪神", "巨人", None, {})
    assert aggregate._event_match(feed, probe)
    # A different NPB matchup must NOT link.
    other = OddsEvent("", "npb", "楽天", "西武", None, {})
    assert not aggregate._event_match(feed, other)
