"""Tests for the best-bets portfolio composer (Lane B4).
cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/composer/test_composer.py -q
"""
from __future__ import annotations

import inspect

from scripts.platformkit.execution.composer import cli as _cli
from scripts.platformkit.execution.composer import composer as _composer
from scripts.platformkit.execution.composer.composer import (
    cap_exposure, compose, score_candidate,
)


def _card(sport="nba", game_id="g1", matchup="Lakers vs Celtics",
          market_type="moneyline", side="home", model_prob=0.62,
          market_prob=0.50, confidence=0.7, tier="A", decision="bet",
          units=1.0) -> dict:
    return {
        "sport": sport, "game_id": game_id, "matchup": matchup,
        "market_type": market_type, "side": side, "model_prob": model_prob,
        "market_prob": market_prob, "confidence": confidence, "tier": tier,
        "decision": decision, "units": units,
        "edge_vs_market": model_prob - market_prob,
        "clv": {"clv_pct": None, "clv_status": "INSUFFICIENT_DATA"},
        "status": "pregame",
    }


# -- correlation cap ---------------------------------------------------------

def test_correlation_cap_collapses_same_game_to_best():
    weak = _card(game_id="g1", side="home", model_prob=0.55, market_prob=0.50)
    strong = _card(game_id="g1", side="away", model_prob=0.70, market_prob=0.50)
    other_game = _card(game_id="g2", matchup="Heat vs Bucks")
    out = compose([weak, strong, other_game])
    g1_survivors = [c for c in out if c["game_id"] == "g1"]
    assert len(g1_survivors) == 1
    assert g1_survivors[0]["side"] == "away"  # the stronger-divergence leg wins
    assert any(c["game_id"] == "g2" for c in out)


def test_correlation_cap_ignores_market_type_within_same_game():
    """A moneyline card and a total card on the SAME game are still correlated
    legs of one event -- only one survives, whichever scores higher."""
    ml = _card(game_id="g1", market_type="moneyline", model_prob=0.60, market_prob=0.50)
    tot = _card(game_id="g1", market_type="total", model_prob=0.65, market_prob=0.50)
    out = compose([ml, tot])
    assert len(out) == 1
    assert out[0]["market_type"] == "total"


# -- exposure cap -------------------------------------------------------------

def test_exposure_cap_limits_positions_per_team():
    cards = [
        _card(game_id="g0", matchup="Lakers vs Celtics", model_prob=0.62),
        _card(game_id="g1", matchup="Lakers vs Heat", model_prob=0.61),
        _card(game_id="g2", matchup="Lakers vs Bucks", model_prob=0.60),
    ]
    for c in cards:
        c["_score"] = score_candidate(c)
    out = cap_exposure(cards, per_team_cap=2, slate_max=20)
    assert len(out) == 2
    assert {c["game_id"] for c in out} == {"g0", "g1"}  # two highest-scored survive


def test_exposure_cap_enforces_slate_max():
    cards = [_card(game_id=f"g{i}", matchup=f"T{i}a vs T{i}b",
                   model_prob=0.55 + i * 0.001) for i in range(10)]
    for c in cards:
        c["_score"] = score_candidate(c)
    out = cap_exposure(cards, per_team_cap=99, slate_max=3)
    assert len(out) == 3


def test_compose_end_to_end_respects_all_caps():
    cards = []
    for i in range(25):
        cards.append(_card(game_id=f"g{i}", matchup=f"Lakers vs Opp{i}",
                           model_prob=0.55 + (i % 5) * 0.01))
    out = compose(cards)
    assert len(out) <= 20  # SLATE_MAX_POSITIONS
    team_counts = {}
    for c in out:
        team_counts["Lakers"] = team_counts.get("Lakers", 0) + 1
    assert team_counts["Lakers"] <= 2  # PER_TEAM_SLATE_CAP


# -- filtering ----------------------------------------------------------------

def test_no_bet_or_untiered_cards_excluded():
    no_bet = _card(decision="no_bet")
    no_tier = _card(tier=None)
    out = compose([no_bet, no_tier])
    assert out == []


def test_compose_empty_and_garbage_input_never_raises():
    assert compose([]) == []
    assert compose([{}, None, "garbage", 42]) == []


def test_score_candidate_pure_no_crash_on_garbage():
    assert score_candidate({}) == 0.0
    assert score_candidate({"model_prob": None, "market_prob": None}) == 0.0
    assert score_candidate(None) == 0.0


# -- no meta-label weighting (ARTIFACT_CONFIRMED retired table) ---------------

def test_no_meta_label_weighting():
    """The composer must never IMPORT or call into the retired meta-label
    divergence-bucket table -- it was ARTIFACT_CONFIRMED (no bucket replicates
    out-of-corpus, docs/research/meta_label_replication_2026-07-11.md). A prose
    mention (documenting the deliberate exclusion) is fine; an import is not."""
    src = inspect.getsource(_composer)
    for line in src.splitlines():
        if "meta_label" in line and "import" in line:
            raise AssertionError(f"composer.py must not import meta_label_*: {line!r}")
    # functional check: none of the bucket-table's exported names ever entered
    # this module's namespace (nothing was imported, aliased, or called).
    bucket_table_names = {
        "build_bucket_table", "load_true_close_kalshi_bets",
        "edge_bucket_label", "wilson_ci", "edge_quartiles",
    }
    assert not (bucket_table_names & set(dir(_composer)))


def test_score_candidate_only_uses_divergence_and_confidence():
    """Score must be invariant to any 'bucket'/'tier'-table style field --
    only model_prob/market_prob/sigma (divergence) and confidence matter."""
    base = _card(model_prob=0.6, market_prob=0.5, confidence=0.8)
    with_bucket_field = dict(base, edge_bucket="Q4_largest_divergence",
                             clv_positive_rate=0.99)
    assert score_candidate(base) == score_candidate(with_bucket_field)


# -- CLI board building (no live-feed network calls; injected candidates) ----

def test_build_board_ranks_and_stamps_entry_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(_cli, "TIMING_POLICY", tmp_path / "missing_timing_policy.json")
    cards = [
        _card(sport="nba", game_id="g1", model_prob=0.70, market_prob=0.50, tier="A"),
        _card(sport="nba", game_id="g2", matchup="Heat vs Bucks",
              model_prob=0.55, market_prob=0.50, tier="C"),
    ]
    doc = _cli.build_board(candidates=cards)
    assert doc["edge_claimed"] is False
    assert doc["count"] == 2
    assert doc["positions"][0]["rank"] == 1
    assert doc["positions"][0]["score"] >= doc["positions"][1]["score"]
    # missing timing_policy.json -> hint degrades to None, never raises
    assert doc["positions"][0]["entry_horizon_hint"] is None


def test_md_board_never_raises_on_empty_doc():
    doc = _cli.build_board(candidates=[])
    md = _cli._md_board(doc)
    assert "positions: 0" in md
