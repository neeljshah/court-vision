"""Per-file tests for meta_label_replication's corpus builder + adjudication.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/fill_model/test_meta_label_replication.py -q
All fixtures synthetic -- no real data dirs touched."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.execution.fill_model.meta_label_replication import (
    adjudicate, binom_p_vs_half, bucket_table, build_synthetic_corpus,
    cluster_ci, synthetic_orders_for_file, walk_forward_table)


def _tick(inning: int, model: float, market: float, close: float, ts: str = "2026-07-01T00:00:00Z"):
    return {"ts": ts, "model_prob": model, "market_prob": market, "close_prob": close,
            "state_summary": "home_score=0 away_score=0 inning=%d half=top outs=0" % inning,
            "outcome": 1.0}


def _write(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_orders_at_checkpoints_only_first_tick_each(tmp_path):
    p = _write(tmp_path / "KXTEST-A.jsonl", [
        _tick(1, 0.6, 0.5, 0.9),          # inning 1: not a checkpoint
        _tick(2, 0.6, 0.5, 0.9),          # checkpoint 2, first tick -> order
        _tick(2, 0.7, 0.5, 0.9),          # second tick of inning 2 -> ignored
        _tick(4, 0.4, 0.5, 0.9),          # checkpoint 4, model favors away
        _tick(6, 0.5, 0.5, 0.9),          # checkpoint 6, zero divergence -> skipped
    ])
    orders = synthetic_orders_for_file(p)
    assert [o["checkpoint_inning"] for o in orders] == [2, 4]
    o2, o4 = orders
    # order-time features only: edge from THAT tick's model/market
    assert o2["side"] == "home" and abs(o2["edge"] - 0.1) < 1e-9
    # home order, close 0.9 > entry 0.5 -> beat_close
    assert o2["beat_close"] is True
    # away order: close moved UP (toward home) -> did NOT beat
    assert o4["side"] == "away" and o4["beat_close"] is False


def test_beat_close_strict_tie_loses(tmp_path):
    p = _write(tmp_path / "KXTEST-B.jsonl", [_tick(2, 0.6, 0.5, 0.5)])
    (o,) = synthetic_orders_for_file(p)
    assert o["beat_close"] is False  # close == entry: strict, mirrors clv_pct > 0


def test_build_corpus_excludes_paper_tickers(tmp_path):
    sport_dir = tmp_path / "mlb"
    _write(sport_dir / "KXMLBGAME-26JUL01AAA.jsonl", [_tick(2, 0.6, 0.5, 0.9)])
    _write(sport_dir / "KXMLBGAME-26JUL01BBB.jsonl", [_tick(2, 0.6, 0.5, 0.9)])
    all_rows = build_synthetic_corpus("mlb", joined_dir=tmp_path)
    assert len(all_rows) == 2
    kept = build_synthetic_corpus("mlb", joined_dir=tmp_path,
                                  exclude_tickers={"KXMLBGAME-26JUL01AAA"})
    assert [r["game_id"] for r in kept] == ["KXMLBGAME-26JUL01BBB"]


def test_bucket_table_same_bucketing_and_cluster_ci():
    rows = [{"game_id": "g%d" % (i % 6), "ts": "t", "edge": 0.01 * (i + 1),
             "beat_close": i % 2 == 0} for i in range(40)]
    tbl = bucket_table(rows)
    assert set(tbl["by_edge_quartile"]) == {"Q1_smallest_divergence", "Q2", "Q3",
                                            "Q4_largest_divergence"}
    for st in tbl["by_edge_quartile"].values():
        lo, hi = st["clv_positive_ci95_game_clustered"]
        assert 0.0 <= lo <= st["clv_positive_rate"] <= hi <= 1.0
        assert st["n_games"] <= 6


def test_walk_forward_breakpoints_from_first_half_only():
    # first half edges tiny, second half edges huge: WF must bucket the whole
    # second half as Q4 under first-half breakpoints
    rows = ([{"game_id": "a%d" % i, "ts": "2026-01-0%d" % (i % 9 + 1), "edge": 0.01,
              "beat_close": True} for i in range(10)]
            + [{"game_id": "b%d" % i, "ts": "2026-02-0%d" % (i % 9 + 1), "edge": 0.9,
                "beat_close": False} for i in range(10)])
    wf = walk_forward_table(rows)
    assert wf["fit_n"] == wf["eval_n"] == 10
    assert list(wf["by_edge_quartile"]) == ["Q4_largest_divergence"]


def test_cluster_ci_and_binom_edge_cases():
    assert cluster_ci([]) is None
    assert binom_p_vs_half(0, 0) is None
    assert binom_p_vs_half(5, 10) == 1.0
    assert binom_p_vs_half(10, 10) < 0.01


def test_adjudicate_family_artifact_when_nothing_replicates():
    # all quartiles at coin on the disjoint corpus; paper 2nd half stays positive
    rows = [{"game_id": "g%d" % i, "ts": "t", "edge": 0.01 * (i + 1),
             "beat_close": i % 2 == 0} for i in range(48)]
    tbl = bucket_table(rows)
    paper_split = {"second_half": {"by_edge_quartile": {
        "Q1_smallest_divergence": {"clv_positive_rate": 0.85},
        "Q4_largest_divergence": {"clv_positive_rate": 0.89}}}}
    verdicts = adjudicate(tbl, paper_split)
    per_bucket = [v for v in verdicts if "table_all_positive" not in v["hypothesis"]]
    assert all(v["verdict"] == "FAILED_REPLICATION" for v in per_bucket)
    family = verdicts[-1]
    assert family["hypothesis"] == "meta_label_divergence_bucket_table_all_positive"
    assert family["verdict"] == "ARTIFACT_CONFIRMED"
    assert all(v["edge_claimed"] is False for v in verdicts)
