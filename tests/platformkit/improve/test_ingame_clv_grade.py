"""Per-file test for scripts.platformkit.improve.ingame_clv_grade.

Proves the in-play CLV grader is HONEST:
  - a model that leans the way the market later moves -> BEAT
  - a model that just copies the market price (market-follow) -> never BEAT (the anchor)
  - too few ticks -> INSUFFICIENT_DATA (honest "can't tell", not a beat)
  - aggregate per-sport verdict respects the gate
  - no $/roi/pnl key ever appears on a summary
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.improve import ingame_clv_grade as g


def _write(path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _row(ts, market_prob, model_prob, side="home", game_id="G1"):
    return {
        "sport": "mlb", "game_id": game_id, "ts": ts,
        "market_prob": market_prob, "model_prob": model_prob, "side": side,
    }


def _beat_rows(n=11):
    """Market drifts up toward a 0.58 close; model leans up (above market) the whole way."""
    rows = []
    for i in range(n):
        mp = round(0.40 + 0.018 * i, 4)          # rising market -> close near 0.58
        rows.append(_row("2026-06-21T00:%02d:00Z" % i, mp, min(0.99, mp + 0.05)))
    return rows


def test_beat_when_model_leans_toward_close(tmp_path):
    p = tmp_path / "G1.jsonl"
    _write(p, _beat_rows())
    res = g.grade_game(p)
    assert len(res) == 1
    r = res[0]
    assert r["verdict"] == "BEAT"
    assert r["mean_clv"] > 0.0
    assert r["hit_rate"] > 0.5
    assert r["n_ticks_scored"] >= 8


def test_market_follow_never_beats(tmp_path):
    # model_prob == market_prob on every tick -> edge 0 -> can never BEAT (anchor).
    rows = [_row("2026-06-21T00:%02d:00Z" % i, round(0.40 + 0.018 * i, 4),
                 round(0.40 + 0.018 * i, 4)) for i in range(11)]
    p = tmp_path / "G1.jsonl"
    _write(p, rows)
    r = g.grade_game(p)[0]
    assert r["verdict"] != "BEAT"


def test_insufficient_data_when_thin(tmp_path):
    p = tmp_path / "G1.jsonl"
    _write(p, _beat_rows(n=3))               # 3 ticks -> 2 scored < MIN_TICKS
    r = g.grade_game(p)[0]
    assert r["verdict"] == "INSUFFICIENT_DATA"


def test_rows_missing_probs_are_skipped(tmp_path):
    rows = _beat_rows()
    rows.append({"sport": "mlb", "game_id": "G1", "ts": "2026-06-21T01:00:00Z",
                 "market_prob": None, "model_prob": 0.7, "side": "home"})  # dropped
    p = tmp_path / "G1.jsonl"
    _write(p, rows)
    by_side = g.load_grade_series(p)
    assert all(t.get("prob") is not None for t in by_side["home"])


def test_two_sided_file_grades_each_side(tmp_path):
    rows = _beat_rows() + [_row("2026-06-21T00:%02d:00Z" % i,
                                round(0.60 - 0.018 * i, 4),
                                max(0.01, round(0.60 - 0.018 * i, 4) - 0.05),
                                side="away") for i in range(11)]
    p = tmp_path / "G1.jsonl"
    _write(p, rows)
    res = g.grade_game(p)
    assert {r["side"] for r in res} == {"home", "away"}


def test_grade_sport_aggregates(tmp_path):
    sdir = tmp_path / "mlb"
    sdir.mkdir()
    _write(sdir / "G1.jsonl", _beat_rows())
    _write(sdir / "G2.jsonl", _beat_rows())
    summary = g.grade_sport("mlb", grade_dir=tmp_path)
    assert summary["verdict"] == "BEAT"
    assert summary["n_markets_scored"] == 2
    assert summary["n_ticks_scored"] >= 16
    assert summary["edge_claimed"] is False


def test_majority_guard_downgrades_fragile_beat(tmp_path):
    # One huge BEAT market + two small BEHIND markets. Tick-weighting alone would
    # call BEAT; the market-majority guard must downgrade the headline to MATCH.
    sdir = tmp_path / "mlb"
    sdir.mkdir()
    _write(sdir / "BIG.jsonl", _beat_rows(n=60))          # strong BEAT, many ticks
    # two small markets where the model leans AGAINST the move (BEHIND)
    for name in ("S1", "S2"):
        rows = [_row("2026-06-21T00:%02d:00Z" % i, round(0.40 + 0.018 * i, 4),
                     max(0.01, round(0.40 + 0.018 * i, 4) - 0.05)) for i in range(11)]
        _write(sdir / ("%s.jsonl" % name), rows)
    summary = g.grade_sport("mlb", grade_dir=tmp_path)
    assert summary["n_markets_beat"] <= summary["n_markets_behind"]
    assert summary["tick_verdict"] == "BEAT"
    assert summary["majority_downgraded"] is True
    assert summary["verdict"] == "MATCH"


def test_grade_sport_empty_is_insufficient(tmp_path):
    summary = g.grade_sport("nba", grade_dir=tmp_path)   # no dir -> nothing
    assert summary["verdict"] == "INSUFFICIENT_DATA"
    assert summary["n_ticks_scored"] == 0


def test_summary_has_no_dollar_keys(tmp_path):
    sdir = tmp_path / "mlb"
    sdir.mkdir()
    _write(sdir / "G1.jsonl", _beat_rows())
    summary = g.grade_sport("mlb", grade_dir=tmp_path)
    # The no-dollar contract is about KEYS, not the explanatory note (which says
    # "UNITS not $" on purpose). No key may carry a $/roi/pnl/stake token.
    for k in summary:
        kl = str(k).lower()
        for bad in ("$", "roi", "pnl", "stake", "bankroll", "profit"):
            assert bad not in kl


def test_resolve_clv_status_injected_summary():
    beat = {"verdict": "BEAT", "mean_clv": 0.03, "hit_rate": 0.6,
            "n_ticks_scored": 100, "n_markets_scored": 5,
            "n_markets_beat": 4, "n_markets_behind": 1, "min_ticks": 8}
    status, reason = g.resolve_clv_status("mlb", summary=beat)
    assert status == "BEAT"
    assert "mean_clv=+0.0300" in reason and "BEAT=4" in reason

    insuf = {"verdict": "INSUFFICIENT_DATA", "n_ticks_scored": 2, "min_ticks": 8}
    status2, reason2 = g.resolve_clv_status("nba", summary=insuf)
    assert status2 == "INSUFFICIENT_DATA"
    assert isinstance(reason2, str) and len(reason2) > 10


def test_emit_wiring_uses_data_driven_clv(tmp_path):
    # Inject a BEAT summary -> the emitted segment row must carry the real verdict,
    # proving the hard-coded INSUFFICIENT_DATA is gone (data-driven wiring).
    from scripts.platformkit.improve.ingame_segment_emit import emit_ingame_segments
    beat = {"verdict": "BEAT", "mean_clv": 0.03, "hit_rate": 0.6,
            "n_ticks_scored": 100, "n_markets_scored": 5,
            "n_markets_beat": 4, "n_markets_behind": 1, "min_ticks": 8}
    led = tmp_path / "led.jsonl"
    rows = emit_ingame_segments("mlb", [("close", "late", "ample")],
                                ledger_path=led, ts="2026-06-26T00:00:00Z",
                                clv_summary=beat)
    assert rows[0]["clv"] == "BEAT"
    assert rows[0]["vs_close"] == "BEAT"        # no longer hard-coded UNPROVEN


def test_format_report_is_ascii(tmp_path):
    sdir = tmp_path / "mlb"
    sdir.mkdir()
    _write(sdir / "G1.jsonl", _beat_rows())
    txt = g.format_sport_report(g.grade_sport("mlb", grade_dir=tmp_path))
    txt.encode("ascii")          # raises if any non-ASCII slips in
    assert "verdict" in txt
