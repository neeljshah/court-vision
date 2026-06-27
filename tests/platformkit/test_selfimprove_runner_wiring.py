"""Offline test for the SUPERVISED self-improve runner's default settled-games fn.

FIX A: the default fn now wires to the RICHER, STATE-BEARING provider
scripts.platformkit.improve.settled_ingest.settled_games_fn (which fetches+classifies the
keyless-ESPN boards, runs the MF3 anti-0-fill audit, AND reconstructs leak-free
{p0, outcome} state rows per final). The earlier default delegated to the bare
settled_finals.settled_since, which returned STATELESS games -> the audit quarantined every
one as empty_states -> FeedDegradedError -> recalibrator None -> perpetual NO_CANDIDATE.

ZERO network: we monkeypatch settled_ingest.settled_games_fn to a canned provider and
assert the runner's default fn calls IT and forwards since + seen_ids (the primary dedup
guard). A dead provider must still degrade to [] (NO_CANDIDATE), never raise.
"""
from __future__ import annotations

import sys
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.improve import selfimprove_runner as RN  # noqa: E402
from scripts.platformkit.improve import settled_ingest as SI  # noqa: E402


def test_default_settled_fn_wires_to_state_bearing_ingest(monkeypatch):
    """The default fn delegates to settled_ingest.settled_games_fn (FIX A) + forwards keys."""
    captured = {}

    def fake_settled_games_fn(sport, *, since="", seen_ids=None, **_kw):
        captured["sport"] = sport
        captured["since"] = since
        captured["seen_ids"] = seen_ids
        return [{"game_id": "G1", "key": "2026-06-10|G1",
                 "states": [{"p0": 0.55, "outcome": 1.0}], "outcome": 1.0}]

    monkeypatch.setattr(SI, "settled_games_fn", fake_settled_games_fn)
    out = RN._default_settled_games_fn("mlb", since="2026-06-09|G0", seen_ids=["G0"])
    assert len(out) == 1 and out[0]["game_id"] == "G1"
    # the game is STATE-BEARING (the whole point of FIX A) -- not a bare dict
    assert out[0]["states"][0]["p0"] == 0.55
    assert out[0]["states"][0]["outcome"] == 1.0
    assert captured["sport"] == "mlb"
    assert captured["since"] == "2026-06-09|G0"
    assert captured["seen_ids"] == ["G0"]  # seen_ids threaded through (primary dedup)


def test_default_settled_fn_degrades_to_empty_on_dead_provider(monkeypatch):
    """REGRESSION: a raising provider degrades to [] (NO_CANDIDATE), never crashes."""
    assert hasattr(SI, "settled_games_fn")

    def boom(*a, **k):
        raise RuntimeError("feed down")

    monkeypatch.setattr(SI, "settled_games_fn", boom)
    # selfimprove_runner wraps the call; a raising provider must surface [] safely.
    assert RN._default_settled_games_fn("mlb", since="", seen_ids=[]) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
