"""Per-file tests for prop_history_backtest (leak-free historical prop calibration feed).

Verifies:
  * build_history_corpus reads synthetic gamelogs and emits correctly-shaped settled-prop
    rows (sport=nba, market_type=prop, model_prob in [0,1], outcome in win/loss, no push,
    market_prob=None, chronological ts),
  * leak-free gating: a player with <= MIN_HISTORY games yields NO rows,
  * same seed -> reproducible corpus,
  * run_history_fold runs the ratchet, tags source=history + fold_seed, writes the corpus
    to its OWN file (never a live ledger), records a valid verdict,
  * NO banned $-keys anywhere (real honesty linter).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/improve/test_prop_history_backtest.py -q
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

import scripts.platformkit.improve.prop_history_backtest as H
from predict_service.honesty_mw import _money_key_violations


def _make_gamelogs(tmp, *, n_players=8, n_games=34, seed=0):
    rng = random.Random(seed)
    d0 = datetime(2023, 1, 1)
    for pid in range(n_players):
        base = rng.uniform(8.0, 22.0)
        rows = []
        for g in range(n_games):
            date = (d0 + timedelta(days=2 * g)).strftime("%b %d, %Y")
            rows.append({
                "GAME_DATE": date,
                "PTS": max(0, round(rng.gauss(base, 5))),
                "REB": max(0, round(rng.gauss(6, 3))),
                "AST": max(0, round(rng.gauss(4, 2))),
                "FG3M": max(0, round(rng.gauss(2, 1.5))),
                "STL": max(0, round(rng.gauss(1, 1))),
                "BLK": max(0, round(rng.gauss(0.5, 0.8))),
                "TOV": max(0, round(rng.gauss(2, 1.2))),
            })
        rows = list(reversed(rows))  # mimic real files (newest-first)
        (tmp / ("gamelog_%d_2023-24.json" % (1000 + pid))).write_text(
            json.dumps(rows), encoding="utf-8")


def test_build_corpus_shape_and_leakfree_gating(tmp_path):
    _make_gamelogs(tmp_path, n_players=6, n_games=34, seed=1)
    rows = H.build_history_corpus(seed=0, max_rows=5000, gamelog_dir=tmp_path)
    assert len(rows) > 100
    for r in rows[:50]:
        assert r["sport"] == "nba" and r["market_type"] == "prop" and r["status"] == "settled"
        assert 0.0 <= r["model_prob"] <= 1.0
        assert r["outcome"] in ("win", "loss")          # half-point line -> never push
        assert r["market_prob"] is None                 # no historical prop close
        assert r["prop_side"] == "over"
    # chronological
    ts = [r["ts"] for r in rows]
    assert ts == sorted(ts)


def test_player_with_too_little_history_yields_nothing(tmp_path):
    # exactly MIN_HISTORY games -> no game index N satisfies N >= MIN_HISTORY with a usable
    # prior of >= MIN_HISTORY, so no rows.
    _make_gamelogs(tmp_path, n_players=1, n_games=H.MIN_HISTORY, seed=2)
    rows = H.build_history_corpus(seed=0, max_rows=5000, gamelog_dir=tmp_path)
    assert rows == []


def test_same_seed_reproducible(tmp_path):
    _make_gamelogs(tmp_path, n_players=8, n_games=34, seed=3)
    a = H.build_history_corpus(seed=7, max_rows=600, gamelog_dir=tmp_path)
    b = H.build_history_corpus(seed=7, max_rows=600, gamelog_dir=tmp_path)
    assert [r["bet_id"] for r in a] == [r["bet_id"] for r in b]


def test_run_fold_tags_isolates_and_records(tmp_path):
    _make_gamelogs(tmp_path, n_players=8, n_games=40, seed=4)
    corpus = tmp_path / "corpus.jsonl"
    ledger = tmp_path / "prop_improve.jsonl"
    rec = H.run_history_fold(seed=5, max_rows=2000, corpus_path=corpus,
                             ledger_path=ledger, gamelog_dir=tmp_path, append=True)
    assert rec["source"] == "history" and rec["fold_seed"] == 5
    assert rec["verdict"] in ("SHIP", "HOLD", "REJECT", "INSUFFICIENT_DATA")
    assert rec["n_rows"] > 0
    assert corpus.exists()                              # corpus written to its OWN file
    lines = [x for x in ledger.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) == 1 and json.loads(lines[0])["source"] == "history"


def test_no_money_keys_in_corpus_or_verdict(tmp_path):
    _make_gamelogs(tmp_path, n_players=8, n_games=40, seed=6)
    corpus = tmp_path / "corpus.jsonl"
    ledger = tmp_path / "prop_improve.jsonl"
    rec = H.run_history_fold(seed=8, max_rows=1500, corpus_path=corpus,
                             ledger_path=ledger, gamelog_dir=tmp_path, append=True)
    assert _money_key_violations(rec, "verdict") == []
    rows = [json.loads(x) for x in corpus.read_text(encoding="utf-8").splitlines() if x.strip()]
    for r in rows[:30]:
        assert _money_key_violations(r, "corpus_row") == []


def test_missing_gamelog_dir_is_honest_empty(tmp_path):
    rows = H.build_history_corpus(seed=0, max_rows=100, gamelog_dir=tmp_path / "nope")
    assert rows == []
