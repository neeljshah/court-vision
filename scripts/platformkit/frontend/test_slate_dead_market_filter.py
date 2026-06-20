"""Per-file test for slate_dead_market_filter (QA-ISSUE-1, :8098 slate path).

Asserts the 558934-style dead/stale Polymarket binary game is EXCLUDED and that
honest live games survive untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.frontend import slate_dead_market_filter as F

_NOW = datetime(2026, 6, 20, tzinfo=timezone.utc)

# The exact QA-reported record: Polymarket binary, tipoff ~11 months past,
# market_prob ~0.0005, ev=683.2 (model 0.3421 vs market 0.0005).
_DEAD_GAME = {
    "game_id": "558934", "home": "Yes", "away": "No",
    "tipoff": "2025-07-02T00:00:00+00:00",
    "edges": [{"game_id": "558934", "market_type": "binary", "side": "home",
               "model_prob": 0.3421, "market_prob": 0.0005, "ev": 683.2}],
}

_LIVE_GAME = {
    "game_id": "999", "home": "New York Knicks", "away": "San Antonio Spurs",
    "tipoff": "2026-06-21T00:00:00+00:00",
    "edges": [{"game_id": "999", "market_type": "moneyline", "side": "home",
               "model_prob": 0.55, "market_prob": 0.52, "ev": 0.06}],
}


def test_dead_binary_game_excluded():
    payload = {"sport": "soccer_intl", "status": "ok",
               "games": [_DEAD_GAME, _LIVE_GAME]}
    out = F.sanitize_slate(payload, now=_NOW)
    ids = [g["game_id"] for g in out["games"]]
    assert "558934" not in ids, "dead Polymarket binary 558934 must be dropped"
    assert ids == ["999"], "the honest live game must survive"
    assert out["dead_market_dropped"] == 1


def test_stale_tipoff_alone_drops_even_if_not_binary():
    stale = dict(_LIVE_GAME, game_id="stale", tipoff="2024-01-01T00:00:00+00:00")
    out = F.sanitize_slate({"games": [stale, _LIVE_GAME]}, now=_NOW)
    assert [g["game_id"] for g in out["games"]] == ["999"]


def test_dead_market_prob_edge_scrubbed_not_whole_game():
    # A non-binary future game whose only edge is dead survives but emits NO edge
    # (an EV is never served against a resolved market; the game itself is not
    # spuriously dropped just because one edge collapsed).
    dead = dict(_LIVE_GAME, game_id="deadprob",
                edges=[{"model_prob": 0.34, "market_prob": 0.0005, "ev": 600.0}])
    out = F.sanitize_slate({"games": [dead, _LIVE_GAME]}, now=_NOW)
    by_id = {g["game_id"]: g for g in out["games"]}
    assert set(by_id) == {"deadprob", "999"}
    assert by_id["deadprob"]["edges"] == [], "dead edge must be scrubbed"


def test_individual_dead_edge_scrubbed_in_live_game():
    mixed = dict(_LIVE_GAME, game_id="mixed", edges=[
        {"model_prob": 0.55, "market_prob": 0.52, "ev": 0.06},   # good
        {"model_prob": 0.34, "market_prob": 0.0005, "ev": 600.0},  # dead
    ])
    out = F.sanitize_slate({"games": [mixed]}, now=_NOW)
    assert len(out["games"]) == 1
    kept_edges = out["games"][0]["edges"]
    assert len(kept_edges) == 1 and kept_edges[0]["market_prob"] == 0.52


def test_live_only_payload_unchanged_shape():
    payload = {"sport": "nba", "status": "ok", "games": [_LIVE_GAME]}
    out = F.sanitize_slate(payload, now=_NOW)
    assert out["games"] == [_LIVE_GAME]
    assert "dead_market_dropped" not in out


def test_non_dict_and_missing_games_passthrough():
    assert F.sanitize_slate({"status": "unavailable"}, now=_NOW) == {
        "status": "unavailable"}
    assert F.sanitize_slate("nope", now=_NOW) == "nope"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
