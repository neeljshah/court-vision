"""tests.platformkit.improve.test_prioritizer -- A1 ranker contract (UH3 + FWER).

Asserts (per A1 + SKEPTIC_REVIEW UH3):
  (a) ordering is DETERMINISTIC: same input + ledger -> byte-identical order, and
      order is independent of the input shuffle for distinct scores.
  (b) a historically-REJECTING family sinks below an untried / passing family.
  (c) a planted null never outranks a real, DISTINCT candidate purely by its
      family name (real-before-null at equal score; UH3 clamp on a named favorite).
  (d) UH3: a named-favorite family ('leverage') REAL candidate does NOT outrank its
      OWN planted null -- the prioritizer gives no family a name-based advantage.
  (e) per-family FREEZE: a family whose planted null is recorded as 'shipped' is a
      flexibility_alarm and sinks to the bottom (loop-level FWER guard).
  (f) display-only purity: no $/pnl/roi/edge field; malformed rows never crash.

Per-file test only (full pytest freezes the box). ASCII; stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import prioritizer as P  # noqa: E402


# --------------------------------------------------------------------------- helpers

def C(name, family, *, is_planted_null=False, n_corpora=2, screen_score=0.0,
      novel=None):
    """Build a duck-typed candidate dict the prioritizer consumes."""
    d = {
        "name": name,
        "family": family,
        "is_planted_null": is_planted_null,
        "n_corpora": n_corpora,
        "screen_score": screen_score,
    }
    if novel is not None:
        d["novel"] = novel
    return d


def names(ordered):
    return [c["name"] for c in ordered]


# --------------------------------------------------------------------------- tests

def test_ordering_is_deterministic_and_shuffle_invariant():
    cands = [
        C("a", "rest", n_corpora=2),
        C("b", "leverage", n_corpora=2),
        C("c", "quarter_shape", n_corpora=1),  # thin corpus -> lower readiness
    ]
    ledger = {"rest": {"ships": 0, "rejects": 5}}  # rest historically rejects

    o1 = names(P.rank(cands, ledger))
    o2 = names(P.rank(cands, ledger))
    assert o1 == o2, "same input must yield identical order"

    # Shuffling the input list must not change the resulting order (total ordering).
    shuffled = [cands[2], cands[0], cands[1]]
    o3 = names(P.rank(shuffled, ledger))
    assert o3 == o1, "order must be independent of input arrangement"


def test_rejecting_family_sinks_below_untried_family():
    cands = [
        C("rejecter", "rest", n_corpora=2),
        C("fresh", "leverage", n_corpora=2),
    ]
    # 'rest' has a long REJECT history; 'leverage' is untried (novel + neutral prior).
    ledger = {"rest": {"ships": 0, "rejects": 8}}
    ordered = names(P.rank(cands, ledger))
    assert ordered.index("fresh") < ordered.index("rejecter"), (
        "a historically-rejecting family must sink below an untried family"
    )


def test_real_distinct_candidate_outranks_a_null_at_equal_score():
    # Same family, same readiness/history -> equal base score. The REAL candidate
    # must come before the planted NULL purely on the real-before-null rule.
    cands = [
        C("the_null", "leverage", is_planted_null=True, n_corpora=2),
        C("the_real", "leverage", is_planted_null=False, n_corpora=2),
    ]
    ordered = names(P.rank(cands))
    assert ordered[0] == "the_real", (
        "a real, distinct candidate must not be outranked by a planted null by name"
    )
    assert ordered[1] == "the_null"


def test_uh3_named_favorite_does_not_outrank_its_own_planted_null():
    """UH3: 'leverage' (the named most-probable SHIP) must NOT be ranked above its
    own planted null. No family gets a built-in priority advantage by name."""
    # Give the real leverage candidate a genuine score advantage the null lacks
    # (richer corpora + forced novelty). Absent the UH3 clamp it would outscore its
    # own family's null; the clamp must pull it DOWN to the null's noise floor so the
    # named favorite buys no priority advantage over its own null.
    cands = [
        C("leverage_null", "leverage", is_planted_null=True, n_corpora=1,
          screen_score=0.0, novel=False),
        C("leverage_real", "leverage", is_planted_null=False, n_corpora=2,
          screen_score=0.99, novel=True),
        # an unrelated control family to ensure the assertion is about names, not luck
        C("other_real", "rest", is_planted_null=False, n_corpora=2),
    ]
    rows = P.rank_with_reasons(cands)
    by_name = {r["name"]: r for r in rows}
    # The UH3 clamp must hold: the real leverage candidate's score is AT MOST its
    # family's planted-null score, so it gets NO name-based advantage over the null
    # (it must clear the noise floor at the honest GATE, not via priority).
    assert by_name["leverage_real"]["score"] <= by_name["leverage_null"]["score"], (
        "UH3: a named-favorite real candidate must not score above its own planted null"
    )
    assert by_name["leverage_real"].get("uh3_clamped") is True, (
        "UH3: the named favorite's score must be clamped to its null's noise floor"
    )
    # And at the clamped (equal) score the null gets no name-based lift over the real
    # candidate either: the real one is ordered first by the real-before-null rule.
    ordered = names(P.rank(cands))
    assert ordered.index("leverage_real") < ordered.index("leverage_null"), (
        "at the clamped equal score, the null must not jump above the real candidate"
    )


def test_planted_null_ship_freezes_the_family():
    cands = [
        C("frozen_real", "leverage", n_corpora=2),
        C("clean_real", "rest", n_corpora=2),
    ]
    # leverage's planted null is recorded as having shipped -> flexibility alarm.
    ledger = {"leverage": {"null_shipped": True, "ships": 1, "rejects": 0}}

    assert "leverage" in P.frozen_families(ledger)
    rows = P.rank_with_reasons(cands, ledger)
    by_name = {r["name"]: r for r in rows}
    assert by_name["frozen_real"]["flexibility_alarm"] is True
    assert by_name["clean_real"]["flexibility_alarm"] is False

    ordered = names(P.rank(cands, ledger))
    assert ordered.index("clean_real") < ordered.index("frozen_real"), (
        "a frozen (flexibility-alarm) family must sink to the bottom"
    )


def test_readiness_outranks_thin_corpus():
    cands = [
        C("thin", "rest", n_corpora=1),
        C("rich", "rest", n_corpora=2),
    ]
    ordered = names(P.rank(cands))
    assert ordered[0] == "rich", "a >=2-corpora candidate must outrank a thin one"


def test_screen_is_tiebreak_only_not_a_decider():
    # Identical primary score (same family/history/readiness/novelty) -> screen
    # breaks the tie. But it must never override a real readiness/history gap.
    tie = [
        C("low_screen", "rest", n_corpora=2, screen_score=0.1),
        C("high_screen", "rest", n_corpora=2, screen_score=0.9),
    ]
    ordered = names(P.rank(tie))
    assert ordered[0] == "high_screen", "screen breaks an exact score tie"

    # readiness gap must dominate the screen tie-break
    dominated = [
        C("rich_low_screen", "rest", n_corpora=2, screen_score=0.0),
        C("thin_high_screen", "rest", n_corpora=1, screen_score=0.99),
    ]
    ordered2 = names(P.rank(dominated))
    assert ordered2[0] == "rich_low_screen", (
        "screen is a tie-break only; a readiness gap must dominate it"
    )


def test_display_only_no_money_fields_and_purity():
    cands = [C("a", "rest", n_corpora=2), C("b", "leverage", n_corpora=2)]
    rows = P.rank_with_reasons(cands)
    banned = {"$", "pnl", "roi", "edge", "profit", "dollars"}
    for r in rows:
        assert not (banned & set(r.keys())), "no money/edge field may be emitted"

    # malformed rows never crash ranking (purity contract).
    malformed = [object(), {"name": "ok", "family": "rest", "n_corpora": 2}, None]
    out = P.rank(malformed)
    assert len(out) == 3, "ranking must not drop or crash on malformed rows"
