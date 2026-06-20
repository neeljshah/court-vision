"""Per-file test: domains/mlb/predictor.py divergence fix (P0 root-cause regression).

ROOT CAUSE (P0): predict() called home.upper() / away.upper() and passed the result
directly to _elo_of() and _lambdas().  When the slate supplies ESPN display names
(e.g. "New York Yankees") or ESPN abbreviations that differ from corpus keys (KC->KAN,
TB->TAM, SF->SFG, SD->SDG, WSH->WAS), _elo_of returns _MOV_INIT=1500.0 for BOTH
sides -> _p_home(1500, 1500) = 0.5345 for EVERY such matchup.  With 15 MLB games in a
slate, all 15 get identical home_ml=0.5345, the uniformity guard correctly flags the
whole slate as degenerate, suppresses all cards, and 0 legitimate bets can ever surface.

FIX: _resolve_or_upper() now maps any ESPN name or abbreviation to its corpus key
before Elo and run-rate lookups.  predict() / to_jd() / predict_live() all call it.

TESTS (acceptance criteria):
  1. >= 10 distinct real corpus-key matchups -> >1 distinct p_home_win (not all ~0.5345).
  2. ESPN display-name matchups yield the SAME probs as corpus-key equivalents.
  3. ESPN non-corpus abbreviations (KC, TB, SF, SD, WSH) also resolve correctly.
  4. Truly unknown teams ("ZZZ", "QQQ") still fall back to league priors gracefully.
  5. MANUAL PROBE: print the 10-matchup prob vector to stdout so CI output shows
     human-readable divergence evidence.

INVARIANTS: per-file only (never run full pytest); no network; calibration not edge;
ASCII only; <=300 LOC.

Run: python -m pytest domains/mlb/test_mlb_predictor_divergence.py -q
"""
from __future__ import annotations

import pytest

from domains.mlb.predictor import MLBPredictor


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pred():
    try:
        p = MLBPredictor()
        return p
    except FileNotFoundError:
        pytest.skip("MLB games corpus not present (gitignored on a fresh clone)")


# ---------------------------------------------------------------------------
# 1. CORE DIVERGENCE: corpus-key matchups produce distinct p_home_win values
# ---------------------------------------------------------------------------

_CORPUS_MATCHUPS = [
    ("NYY", "BOS"),
    ("ATL", "PHI"),
    ("HOU", "TEX"),
    ("LAD", "SFG"),
    ("STL", "CHC"),
    ("TOR", "BAL"),
    ("MIN", "DET"),
    ("SEA", "OAK"),
    ("MIL", "CIN"),
    ("CLE", "KAN"),
]


def test_corpus_keys_produce_distinct_probs(pred):
    """>=10 corpus-key matchups must yield >1 distinct p_home_win (not all 0.5345)."""
    probs = [pred.predict(h, a)["p_home_win"] for h, a in _CORPUS_MATCHUPS]
    # Manual probe: print the vector so CI output shows divergence evidence.
    print("\nCORPUS-KEY MATCHUP PROB VECTOR (manual probe):")
    for (h, a), p in zip(_CORPUS_MATCHUPS, probs):
        print(f"  {h} vs {a}: p_home_win={p}")
    distinct = len(set(probs))
    print(f"  -> {distinct} distinct values across {len(probs)} matchups\n")
    assert distinct > 1, (
        f"All {len(probs)} matchups collapsed to p_home_win={probs[0]:.4f}. "
        "Elo fallback is uniform -- _resolve_or_upper fix not applied."
    )
    assert len(probs) >= 10, "Fewer than 10 matchups tested"
    for v in probs:
        assert 0.0 < v < 1.0, f"p_home_win {v} not in open (0,1)"


# ---------------------------------------------------------------------------
# 2. ESPN DISPLAY NAMES: full franchise names resolve to the SAME probs
# ---------------------------------------------------------------------------

_ESPN_DISPLAY_MATCHUPS = [
    ("New York Yankees",     "Boston Red Sox",         "NYY", "BOS"),
    ("Atlanta Braves",       "Philadelphia Phillies",  "ATL", "PHI"),
    ("Houston Astros",       "Texas Rangers",          "HOU", "TEX"),
    ("Los Angeles Dodgers",  "San Francisco Giants",   "LAD", "SFG"),
    ("St. Louis Cardinals",  "Chicago Cubs",           "STL", "CHC"),
    ("Toronto Blue Jays",    "Baltimore Orioles",      "TOR", "BAL"),
    ("Minnesota Twins",      "Detroit Tigers",         "MIN", "DET"),
    ("Seattle Mariners",     "Oakland Athletics",      "SEA", "OAK"),
    ("Milwaukee Brewers",    "Cincinnati Reds",        "MIL", "CIN"),
    ("Cleveland Guardians",  "Kansas City Royals",     "CLE", "KAN"),
]


def test_display_names_match_corpus_keys(pred):
    """ESPN display names must produce identical p_home_win as their corpus-key equivalents.

    This is the core regression: before the fix, all display-name matchups produced
    p_home_win=0.5345 because _elo_of fell back to _MOV_INIT for both sides.
    After the fix, they match the corpus-key predictions exactly.
    """
    mismatches = []
    display_probs = []
    for espn_h, espn_a, corp_h, corp_a in _ESPN_DISPLAY_MATCHUPS:
        p_display = pred.predict(espn_h, espn_a)["p_home_win"]
        p_corpus  = pred.predict(corp_h, corp_a)["p_home_win"]
        display_probs.append(p_display)
        if abs(p_display - p_corpus) > 1e-6:
            mismatches.append(
                f"{espn_h} vs {espn_a}: display={p_display} corpus={p_corpus}"
            )

    # All display-name probs must be in (0,1) and distinct (not all 0.5345)
    distinct = len(set(display_probs))
    assert distinct > 1, (
        f"All display-name matchups collapsed to p={display_probs[0]:.4f}. "
        "Resolution fix not working for ESPN display names."
    )
    assert not mismatches, (
        "Display-name predictions diverge from corpus-key predictions:\n"
        + "\n".join(mismatches)
    )


# ---------------------------------------------------------------------------
# 3. ESPN NON-CORPUS ABBREVIATIONS: KC, TB, SF, SD, WSH
# ---------------------------------------------------------------------------

_ESPN_ABBR_MAP = [
    ("KC",  "KAN"),   # Kansas City Royals
    ("TB",  "TAM"),   # Tampa Bay Rays
    ("SF",  "SFG"),   # San Francisco Giants
    ("SD",  "SDG"),   # San Diego Padres
    ("WSH", "WAS"),   # Washington Nationals
]


def test_espn_abbreviations_resolve_correctly(pred):
    """ESPN abbreviations that differ from corpus keys must resolve to the correct team.

    Concretely: predict("KC", "NYY")["p_home_win"] must equal
    predict("KAN", "NYY")["p_home_win"], not the init-pair value.
    """
    opponent = "NYY"
    mismatches = []
    for espn_abbr, corpus_key in _ESPN_ABBR_MAP:
        p_espn   = pred.predict(espn_abbr, opponent)["p_home_win"]
        p_corpus = pred.predict(corpus_key, opponent)["p_home_win"]
        assert 0.0 < p_espn < 1.0, f"{espn_abbr}: p_home_win {p_espn} not in (0,1)"
        if abs(p_espn - p_corpus) > 1e-6:
            mismatches.append(
                f"{espn_abbr}->{corpus_key} vs {opponent}: "
                f"espn={p_espn} corpus={p_corpus}"
            )
    assert not mismatches, (
        "ESPN abbreviation predictions diverge from corpus-key predictions:\n"
        + "\n".join(mismatches)
    )


# ---------------------------------------------------------------------------
# 4. UNKNOWN TEAMS: fall back to league priors gracefully (no crash, in (0,1))
# ---------------------------------------------------------------------------

def test_unknown_teams_fall_back_gracefully(pred):
    """Truly unknown teams (not in the MLB resolver) still produce a valid prediction.

    The league-prior fallback is intentional for non-MLB entities.  What we guard
    against is the prior failing silently for KNOWN teams like NYY or KC.
    """
    r = pred.predict("ZZZ", "QQQ")
    assert 0.0 < r["p_home_win"] < 1.0
    assert r["expected_total"] > 0.0
    # p_home_win for two equally unknown teams is ~0.5345 (init vs init) -- that is
    # correct behaviour for genuinely unknown names, not a regression.
    assert r["p_home_win"] == pytest.approx(0.5345, abs=0.001), (
        "Expected init-vs-init fallback (~0.5345) for two unknown teams"
    )


# ---------------------------------------------------------------------------
# 5. UNIFORMITY GUARD: a GENUINE all-same slate IS flagged (guard stays intact)
# ---------------------------------------------------------------------------

def test_uniformity_guard_still_flags_fabricated_uniform_slate(pred):
    """The uniformity guard must still flag an artificially constructed flat slate.

    This confirms we did NOT break the guard when fixing the resolution bug --
    a board where every card truly has the same model_prob (e.g. from a corrupt
    slate) is still detected and suppressed.
    """
    from scripts.platformkit.bestbets.mlb_prob_uniformity_guard import (
        check_uniformity, STATUS_FALLBACK_SUSPECTED,
    )
    flat_cards = [{"model_prob": 0.5345} for _ in range(6)]
    result = check_uniformity(flat_cards)
    assert result["status"] == STATUS_FALLBACK_SUSPECTED, (
        "Uniformity guard did not flag a flat slate -- guard may be broken"
    )
    assert result["uniform"] is True


# ---------------------------------------------------------------------------
# 6. ACCEPTANCE CRITERION: real diverse slate has >=3 distinct home_ml probs
#    and the uniformity guard is NOT tripped on it.
# ---------------------------------------------------------------------------

_DIVERSE_SLATE = [
    ("NYY", "BOS"),
    ("ATL", "PHI"),
    ("HOU", "TEX"),
    ("LAD", "SFG"),
    ("STL", "CHC"),
    ("TOR", "BAL"),
]


def test_diverse_slate_min3_distinct_probs(pred):
    """A 6-game diverse slate must yield >=3 distinct home_ml probs.

    Acceptance criterion (ws3-mlb-differentiation P1):
      'across a multi-game MLB slate the predictor yields >=3 distinct
       home_ml probs (no single 0.5345 constant)'.
    """
    probs = [pred.predict(h, a)["p_home_win"] for h, a in _DIVERSE_SLATE]
    print("\nDIVERSE-SLATE PROB VECTOR:")
    for (h, a), prob in zip(_DIVERSE_SLATE, probs):
        print(f"  {h} vs {a}: p_home_win={prob:.4f}")
    distinct = len(set(probs))
    print(f"  -> {distinct} distinct values across {len(probs)} matchups")
    assert distinct >= 3, (
        f"Only {distinct} distinct home_ml prob(s) across {len(probs)}-game slate "
        f"(probs={probs}). Predictor is not differentiating per matchup."
    )
    # Paranoia: no all-0.5345 collapse
    assert not all(abs(p - 0.5345) < 1e-3 for p in probs), (
        "All probs collapsed to init-rating ~0.5345; Elo differentiation is broken."
    )


def test_diverse_slate_uniformity_guard_not_tripped(pred):
    """A healthy diverse slate must NOT trip the uniformity guard (status=OK).

    Acceptance criterion (ws3-mlb-differentiation P1):
      'uniformity guard not tripped' on a real multi-game MLB slate.

    This is the end-to-end check: predictor + guard together must clear cleanly
    on a typical pre-game slate built from corpus teams with real Elo ratings.
    """
    from scripts.platformkit.bestbets.mlb_prob_uniformity_guard import (
        check_uniformity, STATUS_OK,
    )
    cards = [{"model_prob": pred.predict(h, a)["p_home_win"]}
             for h, a in _DIVERSE_SLATE]
    result = check_uniformity(cards)
    print("\nUNIFORMITY GUARD ON DIVERSE SLATE:")
    print(f"  status={result['status']} uniform={result['uniform']} "
          f"n_unique={result['n_unique']} n_cards={result['n_cards']}")
    assert result["status"] == STATUS_OK, (
        f"Uniformity guard tripped on a healthy diverse slate: {result['reason']}"
    )
    assert result["uniform"] is False, (
        "Guard reports uniform=True on a diverse slate -- predictor may be collapsing."
    )
    assert result["n_unique"] >= 3, (
        f"Only {result['n_unique']} unique probs in guard output; need >=3."
    )


# ---------------------------------------------------------------------------
# 7. RESOLUTION CORRECTNESS: _resolve_or_upper returns corpus keys
# ---------------------------------------------------------------------------

def test_resolve_or_upper_maps_known_names(pred):
    """_resolve_or_upper must return the corpus key, not the raw input."""
    assert pred._resolve_or_upper("New York Yankees") == "NYY"
    assert pred._resolve_or_upper("Kansas City Royals") == "KAN"
    assert pred._resolve_or_upper("KC") == "KAN"
    assert pred._resolve_or_upper("TB") == "TAM"
    assert pred._resolve_or_upper("SF") == "SFG"
    assert pred._resolve_or_upper("SD") == "SDG"
    assert pred._resolve_or_upper("WSH") == "WAS"
    # Corpus keys pass through unchanged (identity fast-path)
    assert pred._resolve_or_upper("NYY") == "NYY"
    assert pred._resolve_or_upper("BOS") == "BOS"
    # Unknown names -> uppercase (league-prior fallback, not a crash)
    assert pred._resolve_or_upper("ZZZ") == "ZZZ"
