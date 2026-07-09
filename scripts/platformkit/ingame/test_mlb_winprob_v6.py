"""Per-file test for mlb_winprob_v6: matched-OOS wiring + paired bootstrap + verdict.
Uses a synthetic composite table + a tiny fake grade file; never builds the real corpus.
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_mlb_winprob_v6.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import scripts.platformkit.ingame.mlb_winprob_v6 as v6


def test_paired_bootstrap_detects_ahead_and_match():
    rng = np.random.default_rng(0)
    y = (rng.random(400) < 0.5).astype(float)
    gids = [f"g{i % 40}" for i in range(400)]
    # candidate strictly closer to truth than base -> AHEAD (lower Brier)
    base = np.clip(y * 0.5 + 0.25 + rng.normal(0, 0.05, 400), 0.01, 0.99)
    cand = np.clip(y * 0.9 + 0.05 + rng.normal(0, 0.05, 400), 0.01, 0.99)
    r = v6.paired_game_bootstrap(base, cand, y, gids)
    assert r["verdict"] == "AHEAD" and r["ci95"][0] > 0
    # identical models -> MATCH (CI straddles 0)
    r2 = v6.paired_game_bootstrap(base, base, y, gids)
    assert r2["verdict"] == "MATCH" and r2["delta_brier"] == 0.0


def test_paired_bootstrap_insufficient_games():
    y = np.array([0.0, 1.0, 0.0, 1.0])
    r = v6.paired_game_bootstrap(y, y, y, ["a", "a", "b", "b"])
    assert r["verdict"] == "INSUFFICIENT"


def test_build_benchmark_wiring_and_reject(monkeypatch):
    # synthetic composite table + fake eval ticks; base==candidate when w=0 => REJECT.
    table = pd.DataFrame([{"date": "2026-06-20", "home": "SF", "away": "LAD",
                           "composite": 0.5, "p_home": 0.62}])

    class _FakeClf:
        pass

    def fake_score(clf, iso, ticks):
        # deterministic base probs from score margin
        return np.array([0.5 + 0.01 * t["score_margin"] for t in ticks], dtype=float)

    def fake_eval_ticks(grade_dir, resolver):
        ticks = []
        for i in range(120):
            ticks.append({"game_id": "KXMLBGAME-26JUN201310LADSF", "bucket": "early|tied",
                          "old_model_prob": 0.5, "market_prob": 0.5,
                          "outcome": float(i % 2), "score_margin": (i % 5) - 2,
                          "inning": 3, "home_score": 2, "away_score": 2})
        return ticks, {"n_files": 1, "n_games_resolved": 1, "n_games_unresolved": 0,
                       "n_ticks_seen": 120, "n_ticks_missing_state": 0, "n_ticks_used": 120}

    monkeypatch.setattr(v6.wp, "build_eval_ticks", fake_eval_ticks)
    monkeypatch.setattr(v6.wp, "score_new_model", fake_score)
    # best_w=0 -> candidate == base -> REJECT
    bundle = {"clf_state": _FakeClf(), "iso_state": None, "table": table, "best_w": 0.0,
              "val_game_brier_candidate": 0.20, "val_game_brier_state_alone": 0.20,
              "meta": {}}
    doc = v6.build_benchmark(bundle, grade_dir=None, resolver=object())
    assert doc["verdict"] == "REJECT"
    assert doc["selection"]["composition_beat_state_on_val"] is False
    assert doc["n_ticks_used"] == 120 and doc["edge_claimed"] is False
    # composite attached to the parsed ticker
    assert doc["n_ticks_composite_covered"] == 120


if __name__ == "__main__":
    test_paired_bootstrap_detects_ahead_and_match()
    test_paired_bootstrap_insufficient_games()
    print("ok (run via pytest for the monkeypatch test)")
