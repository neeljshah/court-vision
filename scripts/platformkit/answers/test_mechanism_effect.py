"""FIX-WAVE lane e1 (gap ledger rank 8) -- mechanism_effect resolver category.
Answers "what does the evidence say about <mechanism>?" from the 4
domains/*/knowledge/validation_ledger.jsonl files, with verbatim receipts
(status/effect/n/p/corpus/note), instead of NOT_SUPPORTED. Also makes the
anti-folklore library queryable (e.g. NBA clutch usage compression is
CONFIRMED but INVERTED vs the seeded claim; the ledger itself, not this test,
is the source of truth for that).

A concurrent validation lane appends to the real ledgers while these tests
run -- tests that need a fixed row count/candidate set copy a SNAPSHOT into
tmp_path and monkeypatch resolver_registry._LEDGER_PATHS at it, rather than
asserting on the live, growing file. Only test_growing_ledger_is_tolerated
reads the live file, and only asserts a lower bound.

Run: python -m pytest scripts/platformkit/answers/test_mechanism_effect.py -q
"""
from __future__ import annotations

import shutil

import pytest

from scripts.platformkit.answers import contract_client as CC
from scripts.platformkit.answers import resolver_registry as R

REAL_NBA_LEDGER = "domains/basketball_nba/knowledge/validation_ledger.jsonl"


@pytest.fixture
def frozen_nba_ledger(tmp_path, monkeypatch):
    """A point-in-time copy of the real NBA ledger -- assertions below are
    safe against the live file growing mid-run."""
    snap = tmp_path / "validation_ledger.jsonl"
    shutil.copy(REAL_NBA_LEDGER, snap)
    monkeypatch.setitem(R._LEDGER_PATHS, "nba", str(snap))
    return str(snap)


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------
def test_category_registered():
    assert "mechanism_effect" in R.RESOLVERS
    meta = R.RESOLVERS["mechanism_effect"]
    for field in ("resolver", "source_artifact", "computation", "units", "rounding"):
        assert meta.get(field), f"mechanism_effect registry entry missing '{field}'"


@pytest.mark.parametrize("query", [
    "what does the evidence say about clutch usage compression",
    "is there evidence for the lefty advantage on return folklore",
    "does the data support home court advantage",
    "what does the evidence say about b2b rest penalty",
])
def test_classify_routes_to_mechanism_effect(query):
    assert R.classify(query) == "mechanism_effect"


def test_edge_language_still_wins_priority_over_mechanism_keywords():
    """A query can name both a mechanism AND retracted/edge language --
    the refusal must win (edge_language is checked first in classify())."""
    q = "what edge do we have on b2b rest penalty, 18.38 percent"
    assert R.classify(q) == "edge_language"
    result = R.resolve(q, sport="nba")
    assert result["status"] == "refused"


# ---------------------------------------------------------------------------
# CONFIRMED_LOCAL path, with receipt
# ---------------------------------------------------------------------------
def test_confirmed_local_mechanism_resolves_with_verbatim_receipt(frozen_nba_ledger):
    r = R.mechanism_effect("nba", "home court advantage magnitude")
    assert r["status"] == "ok"
    assert r["hypothesis"] == "home_court_advantage_magnitude"
    assert r["source_artifact"] == frozen_nba_ledger
    assert r["as_of"]
    finding = r["findings"][0]
    assert finding["verdict"] == "CONFIRMED_LOCAL"
    assert finding["effect_local"] == 3.395  # verbatim, not re-rounded
    assert finding["n"] == 4762
    assert "home win%=0.533" in finding["note"]  # verbatim note text
    assert "not a market-beating or causal claim" in r["framing"]


# ---------------------------------------------------------------------------
# Folklore / NULL_LOCAL path -- the anti-folklore library query
# ---------------------------------------------------------------------------
def test_null_local_folklore_mechanism_resolves(frozen_nba_ledger):
    """three_in_four_fatigue is a classic schedule-fatigue folklore claim
    that came back NULL_LOCAL on this corpus -- must be answerable, not
    dropped as NOT_SUPPORTED."""
    r = R.mechanism_effect("nba", "three in four fatigue")
    assert r["status"] == "ok"
    finding = r["findings"][0]
    assert finding["verdict"] == "NULL_LOCAL"
    assert finding["p"] > 0.01


def test_confirmed_but_reversed_direction_mechanism_still_ok(frozen_nba_ledger):
    """clutch_usage_compression: CONFIRMED_LOCAL in the ledger, but the
    measured direction is the OPPOSITE of the seeded folklore claim
    (amplification, not compression) -- the resolver must hand back the
    ledger's verdict/note verbatim, never re-interpret direction."""
    r = R.mechanism_effect("nba", "clutch usage compression")
    assert r["status"] == "ok"
    finding = r["findings"][0]
    assert finding["verdict"] == "CONFIRMED_LOCAL"
    assert "compresses" in finding["note"]  # the seeded-claim wording, quoted verbatim as recorded


# ---------------------------------------------------------------------------
# Ambiguous / not_supported / unwired-sport paths
# ---------------------------------------------------------------------------
def test_ambiguous_multiple_hypothesis_match(frozen_nba_ledger):
    r = R.mechanism_effect("nba", "b2b")
    assert r["status"] == "ambiguous"
    assert set(r["candidates"]) == {"b2b_rest_penalty", "player_b2b_scoring_dip"}


def test_unknown_mechanism_is_not_supported_never_improvised(frozen_nba_ledger):
    r = R.mechanism_effect("nba", "teleportation field advantage")
    assert r["status"] == "not_supported"
    assert "Registered hypotheses" in r["note"]


def test_unwired_sport_is_not_supported():
    r = R.mechanism_effect("wnba", "anything")
    assert r["status"] == "not_supported"
    assert "not wired" in r["note"]


# ---------------------------------------------------------------------------
# Robust to the live ledger growing (concurrent drain lane appends rows) --
# lower-bound assertions only, never an exact row count on the live file.
# ---------------------------------------------------------------------------
def test_growing_ledger_is_tolerated():
    r = R.mechanism_effect("nba", "b2b_rest_penalty")
    assert r["status"] == "ok"
    assert len(r["findings"]) >= 1
    assert all(f["verdict"] in ("CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE") for f in r["findings"])


def test_dispatch_through_resolve_end_to_end(frozen_nba_ledger):
    result = R.resolve("what does the evidence say about clutch usage compression", sport="nba")
    assert result["status"] == "ok" and result["category"] == "mechanism_effect"
    assert result["hypothesis"] == "clutch_usage_compression"


# ---------------------------------------------------------------------------
# contract_client rendering + resolver/client consistency
# ---------------------------------------------------------------------------
def test_contract_client_renders_confirmed_mechanism(frozen_nba_ledger):
    q = "what does the evidence say about home court advantage magnitude"
    direct = R.resolve(q, sport="nba")
    rendered = CC.answer(q, sport="nba")
    assert direct["status"] == "ok"
    assert direct["hypothesis"] in rendered
    assert "CONFIRMED_LOCAL" in rendered
    assert direct["source_artifact"] in rendered and direct["as_of"] in rendered
    assert "not a market-beating or causal claim" in rendered


def test_contract_client_renders_ambiguous(frozen_nba_ledger):
    rendered = CC.answer("what does the evidence say about b2b", sport="nba")
    assert rendered.startswith("AMBIGUOUS")
    assert "b2b_rest_penalty" in rendered and "player_b2b_scoring_dip" in rendered


def test_contract_client_renders_not_supported(frozen_nba_ledger):
    rendered = CC.answer("what does the evidence say about teleportation field advantage", sport="nba")
    assert rendered.startswith("NOT_SUPPORTED")
