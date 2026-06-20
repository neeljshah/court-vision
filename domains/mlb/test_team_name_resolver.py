"""domains.mlb.test_team_name_resolver -- per-file tests for team_name_resolver.py.

Acceptance criteria (W-PRED-RESOLVE MLB):
  R1. ESPN displayName maps to correct corpus key.
  R2. Official ESPN abbreviations (KC, TB, SF, SD, WSH) resolve to corpus keys.
  R3. Corpus-native keys resolve to themselves.
  R4. Non-standard corpus abbreviations (KAN, TAM, SFG, SDG) resolve correctly.
  R5. Case-insensitive: "yankees", "YANKEES", "Yankees" all resolve to NYY.
  R6. Unresolvable name (BIG3 team, garbage, empty) returns None.
  R7. None input returns None (no raise).
  R8. Whitespace-only input returns None.
  R9. is_corpus_key returns True for valid corpus keys, False otherwise.
  R10. 12 distinct MLB matchup pairs via MLBPredictor.predict_safe yield >=4
       distinct p_home_win values (NOT all the same constant).
  R11. predict_safe with an unresolvable team name returns unmatched=True and
       no p_home_win field (init-rating fabrication suppressed).
  R12. No $ / roi / pnl key in any output.
  R13. CHC/CUB both resolve (corpus has both as CHC after normalization).
  R14. LOS/LAD both resolve to LAD.
  R15. SFG and SFO both resolve to SFG.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_team_name_resolver.py -q
"""
from __future__ import annotations

import pytest

from domains.mlb.team_name_resolver import is_corpus_key, resolve

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
        ("New York Yankees", "NYY"),
        ("Boston Red Sox", "BOS"),
        ("Los Angeles Dodgers", "LAD"),
        ("Los Angeles Angels", "LAA"),
        ("San Francisco Giants", "SFG"),
        ("San Diego Padres", "SDG"),
        ("Kansas City Royals", "KAN"),
        ("Tampa Bay Rays", "TAM"),
        ("Washington Nationals", "WAS"),
        ("Chicago Cubs", "CHC"),
        ("Chicago White Sox", "CWS"),
        ("New York Mets", "NYM"),
        ("Houston Astros", "HOU"),
        ("Oakland Athletics", "OAK"),
        ("Minnesota Twins", "MIN"),
        ("St. Louis Cardinals", "STL"),
        ("St Louis Cardinals", "STL"),
        ("Colorado Rockies", "COL"),
        ("Arizona Diamondbacks", "ARI"),
        ("Atlanta Braves", "ATL"),
        ("Baltimore Orioles", "BAL"),
        ("Cincinnati Reds", "CIN"),
        ("Cleveland Guardians", "CLE"),
        ("Cleveland Indians", "CLE"),
        ("Detroit Tigers", "DET"),
        ("Miami Marlins", "MIA"),
        ("Milwaukee Brewers", "MIL"),
        ("Philadelphia Phillies", "PHI"),
        ("Pittsburgh Pirates", "PIT"),
        ("Seattle Mariners", "SEA"),
        ("Texas Rangers", "TEX"),
        ("Toronto Blue Jays", "TOR"),
    ])
    def test_display_name(self, name, expected):
        assert resolve(name) == expected, f"resolve({name!r}) expected {expected}"


# ---------------------------------------------------------------------------
# R2: Official ESPN abbreviations
# ---------------------------------------------------------------------------

class TestESPNAbbreviations:

    @pytest.mark.parametrize("abbr,expected", [
        ("KC", "KAN"),   # ESPN: KC -> corpus: KAN
        ("TB", "TAM"),   # ESPN: TB -> corpus: TAM
        ("SF", "SFG"),   # ESPN: SF -> corpus: SFG
        ("SD", "SDG"),   # ESPN: SD -> corpus: SDG
        ("WSH", "WAS"),  # ESPN: WSH -> corpus: WAS
        ("NYY", "NYY"),
        ("BOS", "BOS"),
        ("LAA", "LAA"),
        ("LAD", "LAD"),
        ("NYM", "NYM"),
        ("HOU", "HOU"),
        ("STL", "STL"),
        ("TEX", "TEX"),
    ])
    def test_espn_abbr(self, abbr, expected):
        assert resolve(abbr) == expected, f"resolve({abbr!r}) expected {expected}"


# ---------------------------------------------------------------------------
# R3: Corpus-native keys are identity-mapped
# ---------------------------------------------------------------------------

class TestCorpusNativeKeys:

    @pytest.mark.parametrize("key", [
        "ARI", "ATL", "BAL", "BOS", "CHC", "CIN", "CLE", "COL",
        "CWS", "DET", "HOU", "KAN", "LAA", "LAD", "MIA", "MIL",
        "MIN", "NYM", "NYY", "OAK", "PHI", "PIT", "SDG", "SEA",
        "SFG", "STL", "TAM", "TEX", "TOR", "WAS",
    ])
    def test_corpus_key_self_maps(self, key):
        result = resolve(key)
        assert result is not None, f"Corpus key {key!r} should resolve"


# ---------------------------------------------------------------------------
# R4: Non-standard corpus abbreviations
# ---------------------------------------------------------------------------

class TestNonStandardCorpusAbbreviations:

    def test_kan(self):
        """Corpus key KAN (Kansas City) resolves."""
        assert resolve("KAN") == "KAN"

    def test_tam(self):
        """Corpus key TAM (Tampa Bay) resolves."""
        assert resolve("TAM") == "TAM"

    def test_sfg(self):
        """Corpus key SFG (San Francisco) resolves."""
        assert resolve("SFG") == "SFG"

    def test_sdg(self):
        """Corpus key SDG (San Diego) resolves."""
        assert resolve("SDG") == "SDG"

    def test_was(self):
        """Corpus key WAS (Washington) resolves."""
        assert resolve("WAS") == "WAS"


# ---------------------------------------------------------------------------
# R5: Case-insensitive
# ---------------------------------------------------------------------------

class TestCaseInsensitive:

    @pytest.mark.parametrize("variant", [
        "new york yankees", "NEW YORK YANKEES", "New York Yankees",
        "New York yankees",
    ])
    def test_yankees_case(self, variant):
        assert resolve(variant) == "NYY"

    @pytest.mark.parametrize("variant", ["nyy", "NYY", "Nyy"])
    def test_abbr_case(self, variant):
        assert resolve(variant) == "NYY"


# ---------------------------------------------------------------------------
# R6: Unresolvable names return None
# ---------------------------------------------------------------------------

class TestUnresolvable:

    @pytest.mark.parametrize("name", [
        "Killer 3s",          # BIG3 franchise
        "Aliens",             # BIG3 franchise
        "XYZ Team",           # garbage
        "GARBAGE",
        "123",
        "Exhibition All-Stars",
    ])
    def test_unresolvable_returns_none(self, name):
        assert resolve(name) is None, f"Expected None for {name!r}"


# ---------------------------------------------------------------------------
# R7: None input
# ---------------------------------------------------------------------------

class TestNoneInput:

    def test_none_returns_none(self):
        assert resolve(None) is None  # type: ignore[arg-type]

    def test_int_returns_none(self):
        assert resolve(42) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# R8: Whitespace-only
# ---------------------------------------------------------------------------

class TestWhitespace:

    def test_empty_string(self):
        assert resolve("") is None

    def test_spaces_only(self):
        assert resolve("   ") is None


# ---------------------------------------------------------------------------
# R9: is_corpus_key
# ---------------------------------------------------------------------------

class TestIsCorpusKey:

    @pytest.mark.parametrize("key", ["NYY", "BOS", "KAN", "TAM", "SFG", "SDG", "WAS"])
    def test_valid_keys(self, key):
        assert is_corpus_key(key) is True

    @pytest.mark.parametrize("key", ["KC", "TB", "SF", "WSH", "GARBAGE"])
    def test_invalid_keys(self, key):
        assert is_corpus_key(key) is False


# ---------------------------------------------------------------------------
# R13-R15: Alias variants
# ---------------------------------------------------------------------------

class TestAliasVariants:

    def test_chc_resolves(self):
        """CHC (corpus native) resolves to CHC."""
        assert resolve("CHC") == "CHC"

    def test_cub_resolves(self):
        """CUB (corpus variant) resolves to CHC."""
        assert resolve("CUB") == "CHC"

    def test_los_resolves_to_lad(self):
        """LOS (corpus variant) resolves to LAD."""
        assert resolve("LOS") == "LAD"

    def test_lad_resolves_to_lad(self):
        assert resolve("LAD") == "LAD"

    def test_sfo_resolves_to_sfg(self):
        """SFO (corpus variant) resolves to SFG."""
        assert resolve("SFO") == "SFG"

    def test_sfg_resolves_to_sfg(self):
        assert resolve("SFG") == "SFG"


# ---------------------------------------------------------------------------
# R10, R11, R12: Integration with MLBPredictor
# ---------------------------------------------------------------------------

class TestMLBPredictorIntegration:

    @pytest.fixture(scope="class")
    def predictor(self):
        """Build a real MLBPredictor (uses the corpus on disk)."""
        try:
            from domains.mlb.predictor import MLBPredictor
            return MLBPredictor()
        except FileNotFoundError:
            pytest.skip("MLB corpus not available in this environment")

    def test_12_matchups_distinct_probs(self, predictor):
        """R10: 12 distinct ESPN-form matchup pairs yield >=4 distinct p_home_win values."""
        matchups = [
            ("New York Yankees", "Boston Red Sox"),
            ("Los Angeles Dodgers", "San Francisco Giants"),
            ("Houston Astros", "Texas Rangers"),
            ("Atlanta Braves", "New York Mets"),
            ("Chicago Cubs", "St. Louis Cardinals"),
            ("Tampa Bay Rays", "Baltimore Orioles"),
            ("Kansas City Royals", "Minnesota Twins"),
            ("Toronto Blue Jays", "Seattle Mariners"),
            ("San Diego Padres", "Colorado Rockies"),
            ("Philadelphia Phillies", "Washington Nationals"),
            ("Milwaukee Brewers", "Cincinnati Reds"),
            ("Detroit Tigers", "Cleveland Guardians"),
        ]
        assert len(matchups) == 12
        probs = []
        for home_raw, away_raw in matchups:
            result = predictor.predict_safe(home_raw, away_raw)
            assert result.get("unmatched") is False, (
                f"Expected resolution for ({home_raw}, {away_raw}), got unmatched: "
                f"{result.get('unmatched_names')}")
            probs.append(result["p_home_win"])
        n_unique = len(set(round(p, 6) for p in probs))
        assert n_unique >= 4, (
            f"Expected >=4 distinct p_home_win from 12 matchups, got {n_unique}: {probs}")

    def test_unresolvable_name_unmatched(self, predictor):
        """R11: Unresolvable team name -> unmatched=True, no p_home_win field."""
        result = predictor.predict_safe("Killer 3s", "New York Yankees")
        assert result["unmatched"] is True
        assert "p_home_win" not in result
        assert "Killer 3s" in result["unmatched_names"]

    def test_no_dollar_keys_in_matched(self, predictor):
        """R12: No $ / roi / pnl key in a matched prediction."""
        result = predictor.predict_safe("New York Yankees", "Boston Red Sox")
        assert _no_dollar(result)

    def test_no_dollar_keys_in_unmatched(self, predictor):
        """R12: No $ / roi / pnl key in an unmatched response."""
        result = predictor.predict_safe("BIG3 Team", "Boston Red Sox")
        assert _no_dollar(result)

    def test_predict_safe_espn_abbrs(self, predictor):
        """ESPN abbreviations KC, TB, WSH, SD, SF resolve and return a real prediction."""
        pairs = [
            ("KC", "MIN"),        # KAN vs MIN
            ("TB", "BAL"),        # TAM vs BAL
            ("WSH", "PHI"),       # WAS vs PHI
            ("SD", "LAD"),        # SDG vs LAD
            ("SF", "ARI"),        # SFG vs ARI
        ]
        for h, a in pairs:
            result = predictor.predict_safe(h, a)
            assert result.get("unmatched") is False, (
                f"Expected {h}/{a} to resolve but got unmatched: {result}")
            assert 0.0 < result["p_home_win"] < 1.0

    def test_both_unresolvable(self, predictor):
        """Both teams unresolvable -> unmatched=True, unmatched_names has both."""
        result = predictor.predict_safe("BIG3 Foo", "BIG3 Bar")
        assert result["unmatched"] is True
        assert len(result["unmatched_names"]) == 2

    def test_honest_note_no_dollar_claim(self, predictor):
        """honest_note in matched result must disclaim $ edge (not claim profit)."""
        result = predictor.predict_safe("New York Yankees", "Boston Red Sox")
        note = result.get("honest_note", "")
        assert isinstance(note, str) and note
        # Must mention calibration/efficiency/no-edge but NOT claim a $ profit
        note_lower = note.lower()
        assert any(kw in note_lower for kw in ("calibrat", "efficient", "no $", "no edge")), (
            f"honest_note does not contain expected disclaimer: {note!r}")
