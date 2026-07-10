"""Per-file test for scripts.platformkit.gate_run_an_sentiment_mlb.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/test_gate_run_an_sentiment_mlb.py -q
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit import gate_run_an_sentiment_mlb as G


def _splits_row(game_id, side, home_abbr, away_abbr, tickets_pct, money_pct,
               market="moneyline", start_time="2026-07-09T16:35:00.000Z"):
    return {"game_id": game_id, "market": market, "side": side,
            "home_abbr": home_abbr, "away_abbr": away_abbr,
            "tickets_pct": tickets_pct, "money_pct": money_pct,
            "start_time": start_time}


def test_aggregate_sentiment_home_direct_derived_and_dropped():
    rows = [
        # game 1: home + away rows across 2 "books" -> averaged
        _splits_row(1, "home", "PIT", "ATL", 70, 60),
        _splits_row(1, "home", "PIT", "ATL", 74, 64),
        _splits_row(1, "away", "PIT", "ATL", 28, 36),
        # game 2: away-side only -> home derived as 100-away
        _splits_row(2, "away", "BAL", "CHC", 40, 45),
        # game 3: totals-only, no moneyline row at all -> dropped
        _splits_row(3, "home", "SF", "TOR", 55, 55, market="total"),
    ]
    out = G.aggregate_sentiment(pd.DataFrame(rows))
    assert set(out["game_id"]) == {1, 2}
    g1 = out[out["game_id"] == 1].iloc[0]
    assert g1["home_tickets_pct"] == 72.0 and g1["home_money_pct"] == 62.0
    g2 = out[out["game_id"] == 2].iloc[0]
    assert g2["home_tickets_pct"] == 60.0   # 100 - 40


def test_aggregate_sentiment_empty_input():
    assert G.aggregate_sentiment(pd.DataFrame()).empty


def test_load_outcomes_abbr_override_and_ties(tmp_path):
    box = pd.DataFrame([
        {"date": "2026-07-09", "home_abbr": "CHW", "away_abbr": "BOS",
         "home_score": 1.0, "away_score": 2.0, "status": "STATUS_FINAL", "event_id": "E1"},
        {"date": "2026-07-09", "home_abbr": "NYM", "away_abbr": "KC",
         "home_score": 3.0, "away_score": 3.0, "status": "STATUS_FINAL", "event_id": "E2"},  # tie
        {"date": "2026-07-09", "home_abbr": "SEA", "away_abbr": "MIA",
         "home_score": 5.0, "away_score": 1.0, "status": "STATUS_SCHEDULED", "event_id": "E3"},
    ])
    p = tmp_path / "box.parquet"
    box.to_parquet(p)
    out = G._load_outcomes(p)
    assert list(out["event_id"]) == ["E1"]   # tie + non-final dropped
    assert out.iloc[0]["y_home"] == 0.0

    games = pd.DataFrame([{"game_id": 1, "date": "2026-07-09",
                          "home_abbr": "CWS", "away_abbr": "BOS",   # AN spelling
                          "home_tickets_pct": 70.0, "home_money_pct": 60.0}])
    resolved = G.resolve_outcomes(games, out)
    assert resolved.iloc[0]["event_id"] == "E1"   # CWS->CHW override matched
    assert resolved.iloc[0]["y_home"] == 0.0


def test_load_market_close_latest_and_filters(tmp_path):
    d = tmp_path / "line_hist"
    d.mkdir()
    rows_0708 = [
        {"sport": "mlb", "market_type": "moneyline", "side": "home", "game_id": "E1",
         "devigged_prob": 0.40, "captured_at": "2026-07-08T23:00:00+00:00"},
    ]
    rows_0709 = [
        {"sport": "mlb", "market_type": "moneyline", "side": "home", "game_id": "E1",
         "devigged_prob": 0.55, "captured_at": "2026-07-09T23:58:00+00:00"},  # latest -> wins
        {"sport": "mlb", "market_type": "moneyline", "side": "away", "game_id": "E1",
         "devigged_prob": 0.45, "captured_at": "2026-07-09T23:58:00+00:00"},  # wrong side
        {"sport": "mlb", "market_type": "spread", "side": "home", "game_id": "E1",
         "devigged_prob": 0.90, "captured_at": "2026-07-09T23:59:00+00:00"},  # wrong market
        {"sport": "nba", "market_type": "moneyline", "side": "home", "game_id": "E1",
         "devigged_prob": 0.10, "captured_at": "2026-07-09T23:59:00+00:00"},  # wrong sport
    ]
    (d / "2026-07-08.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows_0708), encoding="utf-8")
    (d / "2026-07-09.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows_0709), encoding="utf-8")
    close = G.load_market_close(["E1"], ["2026-07-09"], line_hist_dir=d)
    assert close == {"E1": 0.55}


def test_build_corpus_full_join_and_null_column(tmp_path):
    splits_dir = tmp_path / "splits"
    splits_dir.mkdir()
    box_path = tmp_path / "box.parquet"
    line_dir = tmp_path / "line_hist"
    line_dir.mkdir()

    splits_rows = [
        _splits_row(1, "home", "PIT", "ATL", 72, 62),
        _splits_row(1, "away", "PIT", "ATL", 28, 38),
        _splits_row(2, "home", "BAL", "CHC", 55, 55),
        _splits_row(2, "away", "BAL", "CHC", 45, 45),
    ]
    (splits_dir / "2026-07-09.jsonl").write_text(
        "\n".join(json.dumps(r) for r in splits_rows), encoding="utf-8")

    pd.DataFrame([
        {"date": "2026-07-09", "home_abbr": "PIT", "away_abbr": "ATL",
         "home_score": 5.0, "away_score": 10.0, "status": "STATUS_FINAL", "event_id": "401816084"},
        {"date": "2026-07-09", "home_abbr": "BAL", "away_abbr": "CHC",
         "home_score": 3.0, "away_score": 2.0, "status": "STATUS_FINAL", "event_id": "401816085"},
    ]).to_parquet(box_path)

    line_rows = [
        {"sport": "mlb", "market_type": "moneyline", "side": "home", "game_id": "401816084",
         "devigged_prob": 0.40, "captured_at": "2026-07-09T23:58:00+00:00"},
        {"sport": "mlb", "market_type": "moneyline", "side": "home", "game_id": "401816085",
         "devigged_prob": 0.53, "captured_at": "2026-07-09T23:58:00+00:00"},
    ]
    (line_dir / "2026-07-09.jsonl").write_text(
        "\n".join(json.dumps(r) for r in line_rows), encoding="utf-8")

    frame, diag = G.build_corpus(splits_dir=splits_dir, box_path=box_path, line_hist_dir=line_dir)
    assert diag == {"n_an_games": 2, "n_outcome_joined": 2, "n_price_joined": 2,
                    "n_gateable_rows": 2, "outcome_join_rate": 1.0, "price_join_rate": 1.0}
    assert set(frame["sent_tickets_diff"] + 50.0) == {72.0, 55.0}
    assert G._NULL_COL in frame.columns
    row1 = frame[frame["event_id"] == "401816084"].iloc[0]
    assert row1["p_poisson"] == 0.40 and row1["y_home"] == 0.0   # PIT (home) lost


def test_run_underpowered_reports_n_needed_and_ledger_row(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(G.reject_ledger, "record", lambda *a, **k: calls.append((a, k)))
    tiny = pd.DataFrame({
        "event_id": ["E1", "E2"], "p_poisson": [0.4, 0.6], "y_home": [0.0, 1.0],
        "sent_tickets_diff": [10.0, -5.0], "sent_money_diff": [8.0, -4.0],
        G._NULL_COL: [0.1, -0.2],
    })
    diag = {"n_an_games": 2, "n_outcome_joined": 2, "n_price_joined": 2,
            "n_gateable_rows": 2, "outcome_join_rate": 1.0, "price_join_rate": 1.0}
    monkeypatch.setattr(G, "build_corpus", lambda **kw: (tiny, diag))

    out_path = tmp_path / "verdict.json"
    out = G.run(out_path=out_path)
    assert out["verdict"] == "UNDERPOWERED"
    assert out["n_needed"] == G._MIN_GATEABLE == 600
    assert out["n_gateable_rows"] == 2
    assert json.loads(out_path.read_text())["verdict"] == "UNDERPOWERED"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:3] == ("mlb", "an_sentiment_moneyline_mlb", "UNDERPOWERED")
    assert kwargs["source"] == "funnel_gate"


def _synthetic_gateable_frame(n=700, seed=0):
    rng = np.random.default_rng(seed)
    p_true = rng.uniform(0.3, 0.7, n)
    y = rng.binomial(1, p_true).astype(float)
    p_poisson = np.clip(p_true + rng.normal(0, 0.03, n), 0.01, 0.99)   # skillful base
    return pd.DataFrame({
        "event_id": [f"E{i}" for i in range(n)], "p_poisson": p_poisson, "y_home": y,
        "sent_tickets_diff": rng.normal(0, 10, n),   # pure noise -> honest REJECT expected
        "sent_money_diff": rng.normal(0, 10, n),
        G._NULL_COL: rng.standard_normal(n),
    })


def test_run_gateable_path_wires_gate_one(tmp_path, monkeypatch):
    monkeypatch.setattr(G.reject_ledger, "record", lambda *a, **k: None)
    big = _synthetic_gateable_frame()
    diag = {"n_an_games": 700, "n_outcome_joined": 700, "n_price_joined": 700,
            "n_gateable_rows": 700, "outcome_join_rate": 1.0, "price_join_rate": 1.0}
    monkeypatch.setattr(G, "build_corpus", lambda **kw: (big, diag))
    out = G.run(out_path=tmp_path / "v.json", seed=3)
    assert out["verdict"] in ("NOT_TESTABLE", "INVALID_BASE", "SHIP", "REJECT")
    assert "null_rejects" in out and "base_skillful" in out
    assert out["n_gateable_rows"] == 700
