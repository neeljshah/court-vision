"""S117 per-file test: python -m pytest tests/platformkit/foundry/test_ingame_screen_soccer.py -q

The one thing that must not break is the tick-time as-of contract: every soccer feature is a
function of that game's rows up to and including the tick's own. The guard is proven live (it
fires on a planted peeking builder) rather than merely asserted.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.foundry.ingame_screen import TickTimeLeak, assert_tick_asof
from scripts.platformkit.foundry import ingame_screen_soccer as s117


def _ticks():
    """Two interleaved games, a goal in each, minutes rising."""
    rows = []
    for i in range(12):
        for game, home in (("G1", 1.0 if i >= 6 else 0.0), ("G2", 0.0)):
            rows.append({"game": game, "timestamp": "2026-07-01T20:%02d:00Z" % (i * 5),
                         "market_prob": 0.4 + 0.01 * i, "model_prob": 0.5 - 0.01 * i,
                         "home_score": home, "away_score": 1.0 if (game == "G2" and i >= 9)
                         else 0.0, "minute": float(1 + i * 7), "_row_id": len(rows)})
    return rows


def test_features_are_truncation_invariant():
    src = s117.causal_source(_ticks())
    assert assert_tick_asof(src, s117.build_features, probes=5), "no probe row was checked"


def test_the_guard_actually_fires_on_a_peeking_feature():
    src = s117.causal_source(_ticks())

    def peeking(frame: pd.DataFrame) -> pd.DataFrame:
        out = s117.build_features(frame)
        out["minute"] = float(frame["minute"].max())     # reads the whole corpus, not the prefix
        return out

    with pytest.raises(TickTimeLeak):
        assert_tick_asof(src, peeking, probes=5)


def test_minutes_since_last_goal_resets_on_a_score_change():
    table = s117.build_features(s117.causal_source(_ticks()))
    g1 = table[table["game"] == "G1"].sort_values("minute")
    since = g1["minutes_since_last_goal"].tolist()
    assert since[0] == 1.0, "before any goal it is minutes since kickoff"
    assert since[5] == 36.0, since               # minute 36, still no goal
    assert since[6] == 0.0, since                # the goal tick itself
    assert since[7] == 7.0, since                # one 7-minute step later


def test_load_ticks_drops_bare_live_and_counts_what_it_dropped(tmp_path):
    base = {"game_id": "G1", "market_prob": 0.5, "model_prob": 0.5, "outcome": 1.0}
    lines = [dict(base, ts="2026-07-01T20:00:00Z", state_summary="live"),
             dict(base, ts="2026-07-01T20:01:00Z", state_summary="home_score=0.0 away_score=0.0"),
             dict(base, ts="2026-07-01T20:02:00Z",
                  state_summary="home_score=1.0 away_score=0.0 minute=12")]
    (tmp_path / "G1.jsonl").write_text("\n".join(json.dumps(r) for r in lines), encoding="utf-8")
    ticks, first, census = s117.load_ticks(tmp_path)
    assert len(ticks) == 1 and ticks[0]["minute"] == 12.0
    assert census == {"files": 1, "ticks": 3, "no_state": 1, "no_minute": 1, "no_market": 0,
                      "no_outcome": 0, "kept": 1, "games": 1}
    assert first == {"G1": "2026-07-01"}
