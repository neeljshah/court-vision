"""Per-file tests for compose_profile (shooter trait-profile family).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_query/test_compose_profile.py -q

Covers: percentile math, band mapping (declared config, boundary-exact),
qualified-subset percentiles, per-axis honest not_in_pool, fail-closed
UNANSWERABLE paths, never-one-score invariant, and ask() routing.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.intel_query import ask as ask_mod
from scripts.platformkit.intel_query import compose_profile as cp


def test_percentile_from_rank_boundaries():
    assert cp.percentile_from_rank(1, 101) == 100.0
    assert cp.percentile_from_rank(101, 101) == 0.0
    assert cp.percentile_from_rank(51, 101) == 50.0
    assert cp.percentile_from_rank(1, 1) == 100.0  # degenerate pool


def test_band_word_declared_boundaries():
    assert cp.band_word(100.0) == "elite"
    assert cp.band_word(90.0) == "elite"   # >= is inclusive at the threshold
    assert cp.band_word(89.9) == "high"
    assert cp.band_word(70.0) == "high"
    assert cp.band_word(69.9) == "mid"
    assert cp.band_word(40.0) == "mid"
    assert cp.band_word(39.9) == "low"
    assert cp.band_word(0.0) == "low"
    assert cp.band_word(None) == "unknown"


def _rank_rows(pairs):
    """[(player_id, name), ...] best-first -> claim ranking rows."""
    return [
        {"rank": i, "player_id": pid, "player_name": name, "value": round(1.0 - 0.01 * i, 4), "n": 40}
        for i, (pid, name) in enumerate(pairs, start=1)
    ]


def _claim(claim_id, rows, extra=None):
    row = {
        "claim_id": claim_id, "kind": "ranking",
        "criteria": {"metric": claim_id, "entity_key": "player_id"},
        "ranking": rows, "source_files": [], "computed_at": "2026-07-07T00:00:00+00:00",
        "caveats": [], "_validator_source": "fixture", "_producer_source": "fixture",
    }
    if extra:
        row.update(extra)
    return row


@pytest.fixture()
def fixture_verified(monkeypatch):
    """3 players: Star (qualifies, high everywhere), Role (qualifies, low
    volume), Scrub (does NOT qualify -- absent from the fg3_pct claim)."""
    players = [(1, "Star"), (2, "Role"), (3, "Scrub")]
    qual_rows = _rank_rows([(2, "Role"), (1, "Star")])  # only 1+2 qualify; Role better fg3_pct
    for i, r in enumerate(qual_rows):
        r["fg3m"] = 150 - i
        r["fg3a"] = 400
    verified = {
        cp.QUALIFIED_POOL_CLAIM_ID: _claim(cp.QUALIFIED_POOL_CLAIM_ID, qual_rows),
        "nba_fg3a_per_game_top50_2024-25": _claim(
            "nba_fg3a_per_game_top50_2024-25", _rank_rows(players)),
        "nba_unassisted_share_3pm_top50_2024-25": _claim(
            "nba_unassisted_share_3pm_top50_2024-25", _rank_rows([(1, "Star"), (3, "Scrub"), (2, "Role")])),
        "nba_canonical_shooter_leaderboard_full_season_2024_25": _claim(
            "nba_canonical_shooter_leaderboard_full_season_2024_25",
            [dict(r, fg3m=100, fg3a=300) for r in _rank_rows(players)]),
        # ts_pct / gravity / pullup / late_clock / share / rest claims absent:
        # those axes must degrade honestly, never crash.
    }
    monkeypatch.setattr(cp, "load_verified_claims", lambda pairs=None: verified)
    return verified


def test_axis_vector_values_and_percentiles(fixture_verified):
    result = cp.compose_profile("Star")
    assert result["status"] == "OK"
    assert result["qualifies_fg3m82"] is True
    by_axis = {a["axis"]: a for a in result["axes"]}
    vol = by_axis["fg3a_per_game"]
    assert vol["status"] == "ok"
    assert vol["rank"] == 1 and vol["pool_n"] == 3
    assert vol["pct_pool"] == 100.0
    # qualified subset = {Star, Role}; Star is rank 1 of 2 -> 100.0
    assert vol["pct_qualified"] == 100.0 and vol["pool_qualified_n"] == 2
    # fg3_pct axis: Star rank 2/2 in the qualified claim -> pct 0.0
    assert by_axis["fg3_pct"]["pct_pool"] == 0.0


def test_non_qualifying_player_gets_null_qualified_percentile(fixture_verified):
    result = cp.compose_profile("Scrub")
    assert result["status"] == "OK"
    assert result["qualifies_fg3m82"] is False
    by_axis = {a["axis"]: a for a in result["axes"]}
    assert by_axis["fg3_pct"]["status"] == "not_in_pool"  # below the 82 floor
    vol = by_axis["fg3a_per_game"]
    assert vol["status"] == "ok"
    assert vol["pct_qualified"] is None  # honestly null, never guessed
    assert "not in the fg3m>=82" in vol["pct_qualified_note"]


def test_missing_axis_claim_reported_not_crashed(fixture_verified):
    result = cp.compose_profile("Star")
    by_axis = {a["axis"]: a for a in result["axes"]}
    assert by_axis["gravity_score"]["status"] == "claim_not_verified"
    assert by_axis["ts_pct"]["status"] == "claim_not_verified"
    # trait line still forms, with 'unknown' for the missing gravity word
    assert "gravity unknown" in result["trait_line"]


def test_trait_line_from_declared_bands_only(fixture_verified):
    result = cp.compose_profile("Star")
    # volume pct_qualified=100 -> elite; efficiency fg3_pct pct=0 -> low;
    # self-creation rank 1/3 qualified-subset rank 1/2 -> elite
    assert result["trait_line"] == (
        "elite-volume, low-efficiency shooter; self-creation elite, gravity unknown"
    )
    assert result["trait_line_rule"] == cp.TRAIT_LINE_RULE
    assert result["bands"] == list(cp.BANDS)


def test_never_one_score_and_no_edge_words(fixture_verified):
    result = cp.compose_profile("Star")
    blob = json.dumps(result).lower()
    for word in ("composite_score", "overall_score", "weighted_score", "roi", "pnl", "bankroll"):
        assert word not in blob
    assert result["edge_claimed"] is False
    assert any(u["axis"].startswith("avg_shot_distance") for u in result["unbuilt_axes"])
    assert any("on_off" in u["axis"] for u in result["unbuilt_axes"])


def test_unknown_player_is_unanswerable(fixture_verified):
    result = cp.compose_profile("Nobody Nowhere")
    assert result["status"] == "UNANSWERABLE"
    assert "NO verified axis claim" in result["missing"][0]


def test_missing_qualified_pool_claim_fails_closed(monkeypatch):
    monkeypatch.setattr(cp, "load_verified_claims", lambda pairs=None: {})
    result = cp.compose_profile("Star")
    assert result["status"] == "UNANSWERABLE"
    assert cp.QUALIFIED_POOL_CLAIM_ID in result["missing"][0]


def test_ask_routes_what_kind_of_shooter(fixture_verified, monkeypatch):
    for q in ("what kind of shooter is Star?", "Shooter profile for Star"):
        result = ask_mod.ask(q)
        assert result["family"] == ask_mod.FAMILY_SHOOTER_PROFILE
        assert result["answerable"] is True
        assert result["question"] == q
        assert result["trait_line"].startswith("elite-volume")


def test_ask_profile_route_unanswerable_for_unknown_player(fixture_verified):
    result = ask_mod.ask("what kind of shooter is Nobody Nowhere?")
    assert result["family"] == ask_mod.FAMILY_SHOOTER_PROFILE
    assert result["answerable"] is False


def test_ask_non_profile_questions_do_not_route_here():
    assert ask_mod._try_shooter_profile("Who are the top 5 best shooters?") is None
    assert ask_mod._try_shooter_profile("what did the tennis gate find?") is None
    assert ask_mod._try_shooter_profile("") is None
