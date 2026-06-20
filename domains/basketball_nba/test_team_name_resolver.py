"""domains.basketball_nba.test_team_name_resolver -- per-file tests for team_name_resolver.py.

Acceptance criteria (W-PRED-RESOLVE NBA):
  R1. ESPN displayName maps to correct corpus key.
  R2. Official ESPN abbreviations (GS, NY, NO, SA, PHX, UTA, BKN) resolve to corpus keys.
  R3. Corpus-native keys resolve to themselves.
  R4. Case-insensitive resolution.
  R5. Unresolvable name (BIG3 team, garbage, empty) returns None.
  R6. None input returns None (no raise).
  R7. is_corpus_key returns True for valid keys, False for ESPN-only abbreviations.
  R8. NBAPredictor.predict_safe with ESPN names returns unmatched=False and real prediction.
  R9. predict_safe with unresolvable name returns unmatched=True, no p_home_win field.
  R10. No $ / roi / pnl key in any output.
  R11. Legacy name "NJ" (New Jersey Nets) resolves to BKN.
  R12. "SA" (ESPN abbr for Spurs) resolves to SAS.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_team_name_resolver.py -q
"""
from __future__ import annotations

import pytest

from domains.basketball_nba.team_name_resolver import is_corpus_key, resolve

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_FORBIDDEN_KEYS = frozenset({"pnl", "roi", "bankroll", "profit", "stake",
                              "usd", "dollar", "edge_dollars"})


def _no_dollar(d: dict) -> bool:
    for k, v in d.items():
        if str(k).lower() in _FORBIDDEN_KEYS:
            return False
        if isinstance(v, dict) and not _no_dollar(v):
            return False
    return True


# ---------------------------------------------------------------------------
# R1: ESPN displayName -> corpus key
# ---------------------------------------------------------------------------

class TestDisplayNameResolution:

    @pytest.mark.parametrize("name,expected", [
        ("Boston Celtics", "BOS"),
        ("Los Angeles Lakers", "LAL"),
        ("Golden State Warriors", "GSW"),
        ("New York Knicks", "NYK"),
        ("New Orleans Pelicans", "NOP"),
        ("San Antonio Spurs", "SAS"),
        ("Brooklyn Nets", "BKN"),
        ("Phoenix Suns", "PHX"),
        ("Utah Jazz", "UTA"),
        ("Atlanta Hawks", "ATL"),
        ("Charlotte Hornets", "CHA"),
        ("Chicago Bulls", "CHI"),
        ("Cleveland Cavaliers", "CLE"),
        ("Dallas Mavericks", "DAL"),
        ("Denver Nuggets", "DEN"),
        ("Detroit Pistons", "DET"),
        ("Houston Rockets", "HOU"),
        ("Indiana Pacers", "IND"),
        ("Los Angeles Clippers", "LAC"),
        ("Memphis Grizzlies", "MEM"),
        ("Miami Heat", "MIA"),
        ("Milwaukee Bucks", "MIL"),
        ("Minnesota Timberwolves", "MIN"),
        ("Oklahoma City Thunder", "OKC"),
        ("Orlando Magic", "ORL"),
        ("Philadelphia 76ers", "PHI"),
        ("Portland Trail Blazers", "POR"),
        ("Sacramento Kings", "SAC"),
        ("Toronto Raptors", "TOR"),
        ("Washington Wizards", "WAS"),
    ])
    def test_display_name(self, name, expected):
        assert resolve(name) == expected, f"resolve({name!r}) expected {expected}"


# ---------------------------------------------------------------------------
# R2: Official ESPN abbreviations that differ from corpus keys
# ---------------------------------------------------------------------------

class TestESPNAbbreviations:

    @pytest.mark.parametrize("abbr,expected", [
        ("GS", "GSW"),    # ESPN: GS -> corpus: GSW
        ("NY", "NYK"),    # ESPN: NY -> corpus: NYK
        ("NO", "NOP"),    # ESPN: NO -> corpus: NOP
        ("SA", "SAS"),    # ESPN: SA -> corpus: SAS
        ("PHX", "PHX"),   # ESPN PHX matches corpus PHX
        ("UTA", "UTA"),   # ESPN UTA matches corpus UTA
        ("BKN", "BKN"),   # ESPN BKN matches corpus BKN
        ("BRK", "BKN"),   # alternate Brooklyn abbr
        ("NJ", "BKN"),    # legacy New Jersey
        ("WSH", "WAS"),   # ESPN WSH -> corpus WAS
        ("CHO", "CHA"),   # alternate Charlotte abbr
        ("PHO", "PHX"),   # alternate Phoenix abbr
    ])
    def test_espn_abbr(self, abbr, expected):
        assert resolve(abbr) == expected, f"resolve({abbr!r}) expected {expected}"


# ---------------------------------------------------------------------------
# R3: Corpus-native keys resolve to themselves
# ---------------------------------------------------------------------------

class TestCorpusNativeKeys:

    @pytest.mark.parametrize("key", [
        "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET",
        "GSW", "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN",
        "NOP", "NYK", "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS",
        "TOR", "UTA", "WAS",
    ])
    def test_corpus_key_self_maps(self, key):
        result = resolve(key)
        assert result is not None, f"Corpus key {key!r} should resolve"
        assert result == key, f"Corpus key {key!r} should self-map, got {result!r}"


# ---------------------------------------------------------------------------
# R4: Case-insensitive
# ---------------------------------------------------------------------------

class TestCaseInsensitive:

    @pytest.mark.parametrize("variant", [
        "boston celtics", "BOSTON CELTICS", "Boston Celtics", "Boston celtics",
    ])
    def test_celtics_case(self, variant):
        assert resolve(variant) == "BOS"

    @pytest.mark.parametrize("variant", ["bos", "BOS", "Bos"])
    def test_abbr_case(self, variant):
        assert resolve(variant) == "BOS"

    def test_gs_lowercase(self):
        assert resolve("gs") == "GSW"

    def test_sa_lowercase(self):
        assert resolve("sa") == "SAS"


# ---------------------------------------------------------------------------
# R5: Unresolvable names return None
# ---------------------------------------------------------------------------

class TestUnresolvable:

    @pytest.mark.parametrize("name", [
        "3 Headed Monsters",   # BIG3 franchise
        "Aliens",              # BIG3 franchise
        "UNKNOWN",
        "XYZ",
        "123",
        "All-Star West",
        "",
        "   ",
    ])
    def test_unresolvable_returns_none(self, name):
        assert resolve(name) is None, f"Expected None for {name!r}"


# ---------------------------------------------------------------------------
# R6: None / non-string input
# ---------------------------------------------------------------------------

class TestNoneInput:

    def test_none_returns_none(self):
        assert resolve(None) is None  # type: ignore[arg-type]

    def test_int_returns_none(self):
        assert resolve(42) is None  # type: ignore[arg-type]

    def test_list_returns_none(self):
        assert resolve([]) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# R7: is_corpus_key
# ---------------------------------------------------------------------------

class TestIsCorpusKey:

    @pytest.mark.parametrize("key", [
        "ATL", "BKN", "BOS", "GSW", "NYK", "NOP", "SAS", "PHX", "UTA", "WAS",
    ])
    def test_valid_keys(self, key):
        assert is_corpus_key(key) is True

    @pytest.mark.parametrize("key", ["GS", "NY", "NO", "SA", "WSH", "NJ", "GARBAGE"])
    def test_invalid_keys(self, key):
        assert is_corpus_key(key) is False


# ---------------------------------------------------------------------------
# R11: Legacy and alternate abbreviations
# ---------------------------------------------------------------------------

class TestLegacyAbbreviations:

    def test_nj_resolves_to_bkn(self):
        """R11: Legacy NJ (New Jersey Nets) -> BKN."""
        assert resolve("NJ") == "BKN"

    def test_new_jersey_nets_resolves(self):
        assert resolve("New Jersey Nets") == "BKN"

    def test_sa_resolves_to_sas(self):
        """R12: SA (ESPN abbr for Spurs) -> SAS."""
        assert resolve("SA") == "SAS"

    def test_new_orleans_hornets_resolves(self):
        """Legacy New Orleans Hornets -> NOP."""
        assert resolve("New Orleans Hornets") == "NOP"


# ---------------------------------------------------------------------------
# R8, R9, R10: Integration with NBAPredictor
# ---------------------------------------------------------------------------

class TestNBAPredictorIntegration:

    @pytest.fixture(scope="class")
    def predictor(self):
        """Build a real NBAPredictor (uses the corpus on disk)."""
        try:
            from domains.basketball_nba.predictor import NBAPredictor
            return NBAPredictor()
        except FileNotFoundError:
            pytest.skip("NBA corpus not available in this environment")

    def test_espn_display_names_resolve_and_predict(self, predictor):
        """R8: ESPN displayName pairs resolve and produce real predictions."""
        pairs = [
            ("Boston Celtics", "Los Angeles Lakers"),
            ("Golden State Warriors", "New York Knicks"),
            ("San Antonio Spurs", "New Orleans Pelicans"),
        ]
        for home_raw, away_raw in pairs:
            result = predictor.predict_safe(home_raw, away_raw)
            assert result.get("unmatched") is False, (
                f"Expected resolution for ({home_raw}, {away_raw}), "
                f"got unmatched: {result.get('unmatched_names')}")
            assert 0.0 < result["p_home_win"] < 1.0

    def test_espn_short_abbrs_resolve_and_predict(self, predictor):
        """R8: ESPN short abbreviations GS, NY, NO, SA resolve correctly."""
        pairs = [
            ("GS", "BOS"),    # Golden State -> GSW
            ("NY", "MIA"),    # New York -> NYK
            ("NO", "DAL"),    # New Orleans -> NOP
            ("SA", "OKC"),    # San Antonio -> SAS
        ]
        for h, a in pairs:
            result = predictor.predict_safe(h, a)
            assert result.get("unmatched") is False, (
                f"Expected {h}/{a} to resolve but got unmatched: {result}")
            assert 0.0 < result["p_home_win"] < 1.0

    def test_unresolvable_name_unmatched(self, predictor):
        """R9: Unresolvable team name -> unmatched=True, no p_home_win field."""
        result = predictor.predict_safe("3 Headed Monsters", "Boston Celtics")
        assert result["unmatched"] is True
        assert "p_home_win" not in result
        assert "3 Headed Monsters" in result["unmatched_names"]

    def test_no_dollar_keys_matched(self, predictor):
        """R10: No $ / roi / pnl key in a matched prediction."""
        result = predictor.predict_safe("Boston Celtics", "Los Angeles Lakers")
        assert _no_dollar(result)

    def test_no_dollar_keys_unmatched(self, predictor):
        """R10: No $ / roi / pnl key in an unmatched response."""
        result = predictor.predict_safe("BIG3 Aliens", "Boston Celtics")
        assert _no_dollar(result)

    def test_both_unresolvable(self, predictor):
        """Both teams unresolvable -> unmatched=True, 2 unmatched names."""
        result = predictor.predict_safe("BIG3 Foo", "BIG3 Bar")
        assert result["unmatched"] is True
        assert len(result["unmatched_names"]) == 2

    def test_honest_note_present_and_ascii(self, predictor):
        """honest_note in matched result is ASCII (no emoji or non-ASCII)."""
        result = predictor.predict_safe("BOS", "LAL")
        note = result.get("honest_note", "")
        assert isinstance(note, str) and note
        note.encode("ascii")  # raises if non-ASCII
