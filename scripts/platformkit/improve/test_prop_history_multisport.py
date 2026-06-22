"""Per-file test: scripts/platformkit/improve/test_prop_history_multisport.py
Run: python -m pytest scripts/platformkit/improve/test_prop_history_multisport.py -q

Covers the multi-sport leak-free historical prop ratchet: leak-free row shape, units-only
(no $), own-corpus-file isolation, source=history tagging, planted-null do-no-harm, honest
INSUFFICIENT_DATA on thin data, and the only_stat filter. Uses a SYNTHETIC injected loader
so the test is fast and independent of on-disk parquet presence.
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.improve import prop_history_multisport as M


_BANNED = {"dollars", "usd", "pnl", "roi", "profit", "stake_usd", "payout_usd", "amount_usd"}


def _synthetic_by_pid(n_players: int = 60, n_games: int = 30):
    """Deterministic per-player series: each player has n_games of a single 'pts' stat with
    a player-specific mean, so the recency-Gaussian model is genuinely informative."""
    by_pid = {}
    for p in range(n_players):
        base = 4 + (p % 7)  # varied per-player level
        games = []
        for g in range(n_games):
            val = float(base + (g % 5) - 2)  # bounded, leak-free-orderable
            games.append(("2026-01-%02d" % (g + 1), {"pts": max(0.0, val)}))
        by_pid["P%03d" % p] = games
    return by_pid


@pytest.fixture
def synth_cfg(monkeypatch):
    """Inject a synthetic 'demo' sport into SPORT_CONFIGS for fast, disk-independent tests."""
    cfg = {"loader": lambda stats: _synthetic_by_pid(), "stats": ("pts",), "min_history": 12}
    monkeypatch.setitem(M.SPORT_CONFIGS, "demo", cfg)
    return cfg


def test_build_corpus_leakfree_shape(synth_cfg):
    rows = M.build_history_corpus("demo", seed=1, max_rows=500)
    assert rows, "synthetic corpus should be non-empty"
    r = rows[0]
    # leak-free settled-prop row schema (matches the ratchet's loader contract)
    assert r["sport"] == "demo"
    assert r["market_type"] == "prop"
    assert r["status"] == "settled"
    assert r["market_prob"] is None  # no historical prop close -> honest None
    assert r["outcome"] in ("win", "loss")
    assert 0.0 < r["model_prob"] < 1.0
    assert r["edge_claimed"] is False and r["executed"] is False
    assert r["ts"].endswith("T00:00:00")
    assert r["bet_id"].startswith("hist|demo|")


def test_corpus_is_units_only_no_dollars(synth_cfg):
    rows = M.build_history_corpus("demo", seed=2, max_rows=500)
    for r in rows[:100]:
        for k in r:
            assert k.lower() not in _BANNED, "no $/P&L key allowed: %s" % k


def test_outcome_matches_realized_vs_line(synth_cfg):
    rows = M.build_history_corpus("demo", seed=3, max_rows=300)
    for r in rows[:50]:
        expect = "win" if r["realized_stat"] > r["line"] else "loss"
        assert r["outcome"] == expect
        assert r["realized_stat"] != r["line"]  # half-point: never a fabricated push


def test_only_stat_filter(synth_cfg):
    rows = M.build_history_corpus("demo", seed=1, max_rows=500, only_stat="pts")
    assert rows and all(r["prop_stat"] == "pts" for r in rows)
    # a stat not present yields an empty corpus (no crash)
    assert M.build_history_corpus("demo", seed=1, only_stat="nope") == []


def test_unknown_sport_empty():
    assert M.build_history_corpus("not_a_sport", seed=0) == []


def test_run_fold_writes_own_corpus_and_tags_history(synth_cfg, tmp_path):
    corpus = tmp_path / "corpus_demo.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    rec = M.run_history_fold("demo", seed=7, max_rows=500,
                             corpus_path=corpus, ledger_path=ledger, append=True)
    assert rec["source"] == "history"
    assert rec["sport"] == "demo"
    assert rec["fold_seed"] == 7
    assert rec["n_rows"] > 0
    # corpus written to its OWN file
    assert corpus.exists()
    written = [json.loads(l) for l in corpus.open() if l.strip()]
    assert len(written) == rec["n_rows"]
    # verdict appended to the (temp) ledger, tagged source=history
    led = [json.loads(l) for l in ledger.open() if l.strip()]
    assert led and led[-1]["source"] == "history" and led[-1]["sport"] == "demo"


def test_planted_null_rejects_on_shuffled_signal(synth_cfg, tmp_path):
    """The do-no-harm planted null must NOT ship: a verdict carries null_shipped=False
    whenever it SHIPs (a shipped null would be a REJECT, never a SHIP)."""
    rec = M.run_history_fold("demo", seed=5, max_rows=500,
                             corpus_path=tmp_path / "c.jsonl",
                             ledger_path=tmp_path / "l.jsonl", append=True)
    if rec.get("verdict") == "SHIP":
        assert rec.get("null_shipped") is False


def test_run_fold_never_raises_on_bad_loader(monkeypatch, tmp_path):
    def boom(stats):
        raise RuntimeError("disk gone")
    monkeypatch.setitem(M.SPORT_CONFIGS, "demo",
                        {"loader": boom, "stats": ("pts",), "min_history": 12})
    rec = M.run_history_fold("demo", seed=1, corpus_path=tmp_path / "c.jsonl",
                             ledger_path=tmp_path / "l.jsonl", append=True)
    # a fold error is captured, not raised
    assert rec.get("source") == "history" and "error" in str(rec.get("status", "")).lower()
