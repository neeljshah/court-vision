"""Per-file test for the MEASUREMENT-ONLY improvement_finder.

Asserts the binding honesty rails + determinism:
  * deterministic ranking (stable order across runs; priority desc)
  * dedupe (no duplicate category|sport|what keys)
  * NO $ field on any candidate (units/probability only)
  * the no-force-feed rule: no candidate recommends wiring a rejected signal as
    a model feature
  * an item with a recorded gate verdict is EXCLUDED (closed)
Run ONLY this file:
  python -m pytest tests/platformkit/meta/test_improvement_finder.py -q
"""
from __future__ import annotations

from dataclasses import asdict

from scripts.platformkit.meta import improvement_finder as F


def test_ranking_is_deterministic():
    a = F.discover()
    b = F.discover()
    assert [c.id for c in a] == [c.id for c in b]
    # priority is non-increasing (the primary sort key)
    pris = [c.priority for c in a]
    assert pris == sorted(pris, reverse=True)


def test_dedupe_no_duplicate_keys():
    cands = F.discover()
    keys = [c.key() for c in cands]
    assert len(keys) == len(set(keys)), "duplicate candidate keys leaked"


def test_no_dollar_field_anywhere():
    cands = F.discover()
    assert cands, "expected at least one candidate from real artifacts"
    for c in cands:
        d = asdict(c)
        assert "$" not in str(d), f"dollar sign leaked into {c.id}"
        for forbidden in ("dollars", "edge_usd", "roi", "profit", "usd"):
            assert forbidden not in d, f"forbidden $ key {forbidden} in {c.id}"
        # only the known measurement fields exist (no smuggled $ field)
        assert set(d) == {"id", "category", "sport", "what", "where",
                          "expected_outcome", "gate_action", "priority"}


def test_no_force_feed_rejected_signal_rule():
    cands = F.discover()
    for c in cands:
        blob = (c.what + c.expected_outcome + c.gate_action).lower()
        assert "force-feed" not in blob and "force feed" not in blob
        # a SURFACE_VALIDATED_PRIOR item must NEVER be framed as a model feature
        if c.category == "SURFACE_VALIDATED_PRIOR":
            assert "feature" not in c.expected_outcome.lower() or \
                   "never" in c.expected_outcome.lower()


def test_force_feed_candidate_is_filtered():
    # a hand-injected force-feed candidate must be dropped by rank_and_dedupe
    bad = F.Candidate(
        id="BAD_x", category="UNTESTED_DATA", sport="nba",
        what="rejected q4 margin signal",
        where="domains/basketball_nba", expected_outcome="add reject as a feature",
        gate_action="force-feed the rejected signal into the model", priority=999.0)
    good = F.Candidate(
        id="GOOD_x", category="UNTESTED_DATA", sport="nba", what="untested travel",
        where="domains/basketball_nba", expected_outcome="REJECT-scouting likely",
        gate_action="run leak-free gate; record verdict", priority=10.0)
    out = F.rank_and_dedupe([bad, good])
    ids = [c.id for c in out]
    assert "BAD_x" not in ids
    assert "GOOD_x" in ids


def test_verdicted_item_is_excluded_as_closed():
    # a data point whose tokens all appear in the closed (verdicted) set is dropped
    closed = {"travel", "home", "away"}
    assert F._is_closed("travel_home/away", closed) is True
    # an untested point with no recorded verdict is NOT closed
    assert F._is_closed("per-at-bat states (RE24, leverage)", closed) is False


def test_real_ledger_verdicts_close_their_signals():
    closed = F.load_verdicted_signals()
    # the reject ledger records nba quarter-shape REJECTs -> those tokens are closed
    if closed:
        # a coverage row naming an already-verdicted signal is excluded from discover()
        cands = F.discover()
        for c in cands:
            # no emitted candidate should be a verbatim already-verdicted signal
            assert c.what.lower() not in closed
