"""Per-file tests for xg_market_awareness (LANE 3 item 3: the killer
market-awareness question, walk-forward, synthetic-data regression math).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_xg_market_awareness.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import xg_market_awareness as M
from scripts.platformkit.ingame.xg_crossfit_conditioning import conditioned_prob


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_read_market_probs_joins_by_game_and_ts(tmp_path):
    gdir = tmp_path / "grade"
    _write_jsonl(gdir / "KXWCGAME-A.jsonl", [
        {"ts": "2026-07-01T20:00:00Z", "market_prob": 0.6, "model_prob": 0.5},
        {"ts": "2026-07-01T20:01:00Z", "market_prob": 0.65, "model_prob": 0.55},
    ])
    out = M._read_market_probs(gdir)
    assert out[("KXWCGAME-A", "2026-07-01T20:00:00Z")] == 0.6
    assert out[("KXWCGAME-A", "2026-07-01T20:01:00Z")] == 0.65


def test_read_market_probs_missing_dir_is_honest_empty(tmp_path):
    out = M._read_market_probs(tmp_path / "absent")
    assert out == {}


def test_build_rows_skips_rows_with_no_market_match(tmp_path):
    gdir = tmp_path / "grade"
    _write_jsonl(gdir / "KXWCGAME-A.jsonl", [
        {"ts": "2026-07-01T20:00:00Z", "market_prob": 0.6, "model_prob": 0.5},
    ])

    def xg_rows_fn():
        return [
            {"game_id": "KXWCGAME-A", "ts": "2026-07-01T20:00:00Z", "y": 1.0,
             "model_prob": 0.5, "xg_home": 1.0, "xg_away": 0.0},
            {"game_id": "KXWCGAME-A", "ts": "NO_MATCH_TS", "y": 1.0,
             "model_prob": 0.5, "xg_home": 1.0, "xg_away": 0.0},
        ]

    rows = M.build_rows(xg_rows_fn=xg_rows_fn, grade_dir=gdir)
    assert len(rows) == 1
    assert rows[0]["market_prob"] == 0.6
    assert rows[0]["xg_diff"] == 1.0


def test_walk_forward_split_earlier_games_train_later_eval():
    rows = [
        {"game_id": "g1", "ts": "2026-06-11T10:00:00Z"},
        {"game_id": "g2", "ts": "2026-06-15T10:00:00Z"},
        {"game_id": "g3", "ts": "2026-06-20T10:00:00Z"},
        {"game_id": "g4", "ts": "2026-06-25T10:00:00Z"},
    ]
    train, ev = M.walk_forward_split(rows)
    train_games = {r["game_id"] for r in train}
    eval_games = {r["game_id"] for r in ev}
    assert train_games == {"g1", "g2"}
    assert eval_games == {"g3", "g4"}
    assert train_games.isdisjoint(eval_games)  # no leak: disjoint game sets


def test_walk_forward_split_deterministic():
    rows = [{"game_id": "g%d" % i, "ts": "2026-06-%02dT10:00:00Z" % (11 + i)} for i in range(10)]
    t1, e1 = M.walk_forward_split(rows)
    t2, e2 = M.walk_forward_split(rows)
    assert [r["game_id"] for r in t1] == [r["game_id"] for r in t2]
    assert [r["game_id"] for r in e1] == [r["game_id"] for r in e2]


def test_synthetic_market_already_prices_xg_yields_no_add():
    """SYNTHETIC REGRESSION MATH: construct rows where market_prob ALREADY
    encodes xg_diff perfectly (same generative process) -- xg_diff should
    add NOTHING beyond market_prob; verdict must be NO_ADD_BEYOND_MARKET,
    never XG_ADDS_BEYOND_MARKET."""
    rows = []
    for gi in range(20):
        ts_prefix = "2026-06-%02dT10:00:00Z" % (11 + gi)
        xg_diff = -1.0 + 0.1 * gi
        # market_prob is generated via the EXACT SAME xg-conditioning family
        # used elsewhere in this lane -- i.e. the market already "knows" xg.
        market_prob = conditioned_prob(0.5, xg_diff, beta=1.2)
        n_pos = round(market_prob * 10)
        for k in range(10):
            y = 1.0 if k < n_pos else 0.0
            rows.append({"game_id": "g%d_%d" % (gi, k), "ts": ts_prefix,
                        "y": y, "model_prob": 0.5, "market_prob": market_prob,
                        "xg_diff": xg_diff})

    doc = M.run_market_awareness(rows_fn=lambda: rows)
    assert doc["verdict"] == "NO_ADD_BEYOND_MARKET"
    assert doc["edge_claimed"] is False


def test_synthetic_market_ignorant_of_xg_yields_add():
    """SYNTHETIC REGRESSION MATH: market_prob carries NO xg information
    (constant 0.5 regardless of xg_diff) while y is driven by xg_diff --
    xg_diff should clearly ADD beyond the (uninformative) market price."""
    rows = []
    for gi in range(20):
        ts_prefix = "2026-06-%02dT10:00:00Z" % (11 + gi)
        xg_diff = -1.0 + 0.1 * gi
        true_p = conditioned_prob(0.5, xg_diff, beta=2.0)
        n_pos = round(true_p * 10)
        for k in range(10):
            y = 1.0 if k < n_pos else 0.0
            rows.append({"game_id": "g%d_%d" % (gi, k), "ts": ts_prefix,
                        "y": y, "model_prob": 0.5, "market_prob": 0.5,
                        "xg_diff": xg_diff})

    doc = M.run_market_awareness(rows_fn=lambda: rows)
    assert doc["verdict"] == "XG_ADDS_BEYOND_MARKET"
    assert doc["brier_delta"] < 0


def test_run_market_awareness_insufficient_below_min_games():
    rows = [{"game_id": "g1", "ts": "2026-06-11T10:00:00Z", "y": 1.0,
            "model_prob": 0.5, "market_prob": 0.5, "xg_diff": 0.5}]
    doc = M.run_market_awareness(rows_fn=lambda: rows)
    assert doc["verdict"] == "MATCH_INSUFFICIENT_DATA"


def test_run_market_awareness_honesty_fields_present():
    doc = M.run_market_awareness(rows_fn=lambda: [])
    assert doc["edge_claimed"] is False
    assert doc["provenance"] == "backfill_validation"
    assert "killer question" in doc["hypothesis"].lower()


def test_run_market_awareness_producer_exception_is_honest():
    def boom():
        raise RuntimeError("producer broke")

    doc = M.run_market_awareness(rows_fn=boom)
    assert doc["verdict"] == "MATCH_INSUFFICIENT_DATA"
    assert "error" in doc


def test_run_market_awareness_never_raises_with_real_default_wiring():
    """Exercises the real default build_rows() wiring against whatever data
    currently exists on disk -- must never raise."""
    doc = M.run_market_awareness()
    assert isinstance(doc, dict)
    assert "verdict" in doc


def test_fit_gamma_deterministic():
    train = [{"market_prob": 0.5, "xg_diff": 1.0, "y": 1.0}] * 5 + \
            [{"market_prob": 0.5, "xg_diff": -1.0, "y": 0.0}] * 5
    g1 = M.fit_gamma(train)
    g2 = M.fit_gamma(train)
    assert g1 == g2


def test_fit_gamma_empty_returns_zero():
    assert M.fit_gamma([]) == 0.0
