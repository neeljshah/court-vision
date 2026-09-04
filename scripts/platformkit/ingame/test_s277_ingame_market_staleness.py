"""Focused construct and archived-differential checks for S277 Attempt 2."""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.ingame import s277_ingame_market_staleness as s277


def test_staleness_states_and_fresh_archive_brier() -> None:
    fixture = pd.DataFrame({"game_id": ["g", "g", "g", "g", "h", "h"], "ts": [0, 10000, 10000, 30000, 0, 20000], "market_prob": [0.40, 0.40, 0.60, 0.60, 0.20, 0.20]})
    ages = s277.add_staleness(fixture)
    assert ages["staleness_bin"].tolist()[:4] == ["first_tick_exclusion", "stale", "fresh", "stale"]
    assert ages["state_age_s"].iloc[2] == 0.0
    prior = pd.DataFrame({"game_id": ["prior", "prior"], "ts": [0, 10_000], "market_prob": [0.40, 0.40]})
    planted_future = pd.concat([prior, pd.DataFrame({"game_id": ["prior"], "ts": [30_000], "market_prob": [0.90]})], ignore_index=True)
    assert s277.add_staleness(planted_future).iloc[1][["state_age_s", "staleness_bin"]].equals(s277.add_staleness(prior).iloc[1][["state_age_s", "staleness_bin"]])
    ticks = pd.DataFrame({"game_id": ["g", "g"], "ts": ["1970-01-01T00:01:40Z", "1970-01-01T00:03:20Z"], "market_prob": [0.11, 0.91], "recal_null": [0.12, 0.92], "outcome_home_win": [0, 0]})
    states, _ = s277._game_states(ticks)
    assert len(states) == len(ticks)
    assert states[0]["features"] == {"market": 0.11, "recal": 0.12}
    assert states[0]["state_ts"].startswith("1970-01-01T00:01:40")
    s277._verify_prereg()
    paired = pd.read_csv(s277.EVIDENCE / (s277.STEM + "_paired_losses.csv"))
    summary = json.loads((s277.EVIDENCE / (s277.STEM + "_summary.json")).read_text(encoding="ascii"))
    assert paired["outcome_home_win"].equals(paired["y"])
    assert summary["mode"] == "SEALED_STRATIFICATION"
    assert summary["attempt"] == 2
    assert summary["rss_bytes"] == summary["rss_after_bytes"]
    fresh = paired[paired["staleness_bin"] == "fresh"]
    assert abs(fresh["loss_market"].mean() - summary["metrics"]["fresh"]["market_brier"]) < 1e-12
    assert abs(fresh["loss_recal_null"].mean() - summary["metrics"]["fresh"]["recal_null_brier"]) < 1e-12
