"""Per-file unit tests for prop_base (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_prop_base.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.prop_base import (
    PropLine, canon_stat, is_unavailable, unavailable)


def test_propline_to_dict_shape():
    pl = PropLine(
        sport="soccer_intl", event_id="e1", match="France vs Senegal",
        player="Kylian Mbappe", team="France", stat="Shots", line=2.5,
        over_price=1.53, under_price=2.57, payout_type="sportsbook",
        source="underdog", as_of="2026-06-17T00:00:00+00:00")
    d = pl.to_dict()
    assert set(d.keys()) == {
        "sport", "event_id", "match", "player", "team", "stat", "line",
        "over_price", "under_price", "payout_type", "source", "as_of"}
    assert d["player"] == "Kylian Mbappe"
    assert d["line"] == 2.5
    assert d["over_price"] == 1.53
    assert d["payout_type"] == "sportsbook"


def test_canon_stat_known_labels():
    assert canon_stat("Shots Attempted") == "Shots"
    assert canon_stat("shots on target") == "Shots On Target"
    assert canon_stat("Fouls Drawn") == "Fouls Drawn"
    assert canon_stat("Fouls Against") == "Fouls Drawn"
    assert canon_stat("Goals + Assists") == "Goal+Assist"
    assert canon_stat("Saves") == "Saves"
    assert canon_stat("  PASSES  ") == "Passes Attempted"


def test_canon_stat_mlb_labels():
    # Batter stats (canonical == domains/mlb MLB_CANON keys).
    assert canon_stat("Hits") == "Hits"
    assert canon_stat("Total Bases") == "Total Bases"
    assert canon_stat("RBIs") == "RBIs"
    assert canon_stat("Runs") == "Runs"
    assert canon_stat("Home Runs") == "Home Runs"
    assert canon_stat("Stolen Bases") == "Stolen Bases"
    # Walks: bare/Batter/Hitter -> batter Walks key.
    assert canon_stat("Walks") == "Walks"
    assert canon_stat("Batter Walks") == "Walks"
    # Batter strikeouts: both "Batter" and "Hitter" wording.
    assert canon_stat("Batter Strikeouts") == "Batter Strikeouts"
    assert canon_stat("Hitter Strikeouts") == "Batter Strikeouts"
    # Combo: both Underdog (spaced) and PrizePicks (tight) spellings.
    assert canon_stat("Hits + Runs + RBIs") == "Hits+Runs+RBIs"
    assert canon_stat("Hits+Runs+RBIs") == "Hits+Runs+RBIs"


def test_canon_stat_mlb_pitcher_disambiguation():
    # Bare "Strikeouts" (pitcher line) -> Pitcher Strikeouts; batter K's always
    # carry Batter/Hitter so the bare label is unambiguously the pitcher's.
    assert canon_stat("Strikeouts") == "Pitcher Strikeouts"
    assert canon_stat("Pitcher Strikeouts") == "Pitcher Strikeouts"
    # Outs: Pitching/Pitcher/bare all -> the per-start "Outs" key.
    assert canon_stat("Pitching Outs") == "Outs"
    assert canon_stat("Pitcher Outs") == "Outs"
    assert canon_stat("Outs") == "Outs"
    # Earned runs: "Allowed" suffix folds onto the engine "Earned Runs" key.
    assert canon_stat("Earned Runs Allowed") == "Earned Runs"
    assert canon_stat("Earned Runs") == "Earned Runs"
    assert canon_stat("Hits Allowed") == "Hits Allowed"
    assert canon_stat("Walks Allowed") == "Walks Allowed"


def test_canon_stat_mlb_unmapped_pass_through():
    # No engine MLB_CANON key -- must pass through raw (never guessed).
    for raw in ("Fantasy Points", "Singles", "Doubles", "Pitches Thrown",
                "Plate Appearances", "1st Inn. Strikeouts",
                "Pitcher Strikeouts (Combo)"):
        assert canon_stat(raw) == raw


def test_canon_stat_unknown_passes_through():
    assert canon_stat("Quantum Dribbles") == "Quantum Dribbles"
    assert canon_stat(None) is None
    assert canon_stat("") == ""


def test_unavailable_passthrough():
    s = unavailable("source down")
    assert is_unavailable(s)
    assert s["reason"] == "source down"
    assert not is_unavailable([])
    assert not is_unavailable({"status": "ok"})
