"""Per-file tests for hist_mlb_forward_gate.py (LANE 3 sub-task B, forward
leg). Hermetic synthetic fixtures for load_ticks/build_forward_rows; a real-
corpus smoke test is SKIPPED (not failed) if the local capture corpus and/or
boxscore parquet are absent.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_hist_mlb_forward_gate.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.ingame.hist_mlb_forward_gate import (
    DEFAULT_CAPTURE_DIR,
    build_forward_rows,
    load_ticks,
    run_forward_gate,
)
from scripts.platformkit.ingame.hist_mlb_outcome_resolver import (
    DEFAULT_BOXSCORE_PARQUET,
    MlbTickerOutcomeResolver,
)


def _tick(gid, ticker_suffix, prob, ts, phase="in_play", market_type="moneyline"):
    return {"sport": "mlb", "game_id": gid, "ticker": f"{gid}-{ticker_suffix}",
            "prob": prob, "ts": ts, "phase": phase, "market_type": market_type,
            "side": ticker_suffix}


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# load_ticks
# ---------------------------------------------------------------------------


def test_load_ticks_groups_by_game_and_side(tmp_path):
    gid = "KXMLBGAME-26JUL011235CWSBAL"
    rows = [
        _tick(gid, "BAL", 0.55, "2026-07-01T00:00:01Z"),
        _tick(gid, "BAL", 0.58, "2026-07-01T00:05:01Z"),
        _tick(gid, "CWS", 0.45, "2026-07-01T00:00:01Z"),
    ]
    f = tmp_path / "2026-07-01.jsonl"
    _write_jsonl(f, rows)
    ticks = load_ticks(tmp_path)
    assert gid in ticks
    assert set(ticks[gid].keys()) == {"BAL", "CWS"}
    assert len(ticks[gid]["BAL"]) == 2
    assert ticks[gid]["BAL"][0][0] < ticks[gid]["BAL"][1][0]  # sorted by ts


def test_load_ticks_excludes_non_moneyline_and_non_inplay(tmp_path):
    gid = "KXMLBGAME-26JUL011235CWSBAL"
    rows = [
        _tick(gid, "BAL", 0.55, "t1", phase="pregame"),
        _tick(gid, "BAL", 0.55, "t2", market_type="total"),
        _tick(gid, "BAL", 0.55, "t3"),  # valid
    ]
    f = tmp_path / "d.jsonl"
    _write_jsonl(f, rows)
    ticks = load_ticks(tmp_path)
    assert len(ticks[gid]["BAL"]) == 1


def test_load_ticks_missing_dir_returns_empty(tmp_path):
    assert load_ticks(tmp_path / "nope") == {}


def test_load_ticks_never_raises_on_malformed_line(tmp_path):
    f = tmp_path / "d.jsonl"
    f.write_text("not-json\n" + json.dumps(_tick("g1", "BAL", 0.5, "t1")) + "\n", encoding="utf-8")
    ticks = load_ticks(tmp_path)
    assert "g1" in ticks


# ---------------------------------------------------------------------------
# build_forward_rows
# ---------------------------------------------------------------------------


def _synthetic_boxscores():
    return pd.DataFrame([
        {"date": "2026-07-01", "home_abbr": "BAL", "away_abbr": "CHW",
         "home_score": 5.0, "away_score": 3.0, "status": "STATUS_FINAL"},
    ])


def test_build_forward_rows_home_and_away_side_agree_direction():
    gid = "KXMLBGAME-26JUL011235CWSBAL"
    # BAL (home) side ticks trending up; CWS (away) ticks trending down --
    # both should map to a rising prob_home after inversion of the away side.
    home_series = [(f"t{i}", 0.5 + 0.03 * i) for i in range(10)]
    away_series = [(f"t{i}", 0.5 - 0.03 * i) for i in range(10)]
    ticks = {gid: {"BAL": home_series, "CWS": away_series}}
    resolver = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    rows = build_forward_rows(ticks, resolver)
    assert len(rows) == 4  # one per CHECKPOINT_FRACTIONS
    for r in rows:
        assert 0.0 <= r["raw_prob"] <= 1.0
        assert r["outcome"] == 1.0  # BAL (home) won 5-3


def test_build_forward_rows_skips_unresolved_game():
    gid = "KXMLBGAME-26JUL011235ZZZQQQ"  # unresolvable team codes
    ticks = {gid: {"ZZZ": [(f"t{i}", 0.5) for i in range(5)]}}
    resolver = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    rows = build_forward_rows(ticks, resolver)
    assert rows == []


def test_build_forward_rows_skips_too_few_ticks():
    gid = "KXMLBGAME-26JUL011235CWSBAL"
    ticks = {gid: {"BAL": [("t0", 0.5), ("t1", 0.5)]}}  # < MIN_TICKS_PER_SIDE
    resolver = MlbTickerOutcomeResolver(boxscore_df=_synthetic_boxscores())
    rows = build_forward_rows(ticks, resolver)
    assert rows == []


# ---------------------------------------------------------------------------
# run_forward_gate end-to-end
# ---------------------------------------------------------------------------


def test_run_forward_gate_insufficient_data_on_empty(tmp_path):
    report = run_forward_gate(capture_dir=tmp_path)
    assert report["verdict"] == "INSUFFICIENT_DATA"
    assert report["edge_claimed"] is False


def test_run_forward_gate_end_to_end_synthetic(tmp_path):
    import random
    rng = random.Random(7)
    boxscore_rows = []
    tick_lines = []
    # Each synthetic game gets its OWN day (01..15): 15 games sharing one exact
    # (date, away, home) key would be an unrealistic 15-team doubleheader and,
    # post-fix, the resolver correctly fails closed (ambiguous) on a shared key
    # with no G-suffix -- see hist_mlb_outcome_resolver's doubleheader fix.
    for i in range(15):
        day = i + 1
        home_won = rng.random() < 0.55
        hs, aws = (5, 2) if home_won else (2, 5)
        boxscore_rows.append({"date": f"2026-07-{day:02d}", "home_abbr": "BAL", "away_abbr": "CHW",
                              "home_score": float(hs), "away_score": float(aws),
                              "status": "STATUS_FINAL"})
        gid = f"KXMLBGAME-26JUL{day:02d}12{i:02d}CWSBAL"
        base = 0.6 if home_won else 0.4
        for j in range(10):
            p = max(0.02, min(0.98, base + rng.uniform(-0.1, 0.1)))
            tick_lines.append(json.dumps(_tick(gid, "BAL", p, f"2026-07-{day:02d}T00:{j:02d}:00Z")))
    f = tmp_path / "2026-07-01.jsonl"
    f.write_text("\n".join(tick_lines) + "\n", encoding="utf-8")

    resolver = MlbTickerOutcomeResolver(boxscore_df=pd.DataFrame(boxscore_rows))
    report = run_forward_gate(capture_dir=tmp_path, resolver=resolver, min_history=5)
    assert report["edge_claimed"] is False
    assert report["verdict"] in ("MATCH", "IMPROVED", "WORSENED")
    json.dumps(report, default=str)


def test_real_corpus_smoke():
    if not DEFAULT_CAPTURE_DIR.exists() or not DEFAULT_BOXSCORE_PARQUET.exists():
        pytest.skip("local MLB forward capture / boxscore corpus absent (gitignored data/ dir)")
    report = run_forward_gate()
    assert report["edge_claimed"] is False
    assert report["verdict"] in ("MATCH", "IMPROVED", "WORSENED", "INSUFFICIENT_DATA")
    json.dumps(report, default=str)
