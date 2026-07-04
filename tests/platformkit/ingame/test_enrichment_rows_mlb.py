"""Tests for scripts.platformkit.ingame.enrichment_rows_mlb (LANE 5: GATE B producer).

All I/O is injected (tmp_path grade/gumbo dirs + an in-memory BridgeRow list + a
stub outcome resolver) -- never touches the real data/ tree. Covers: happy-path
as-of join + enrichment, unbridgeable game_pk skipped, strict as-of (tick before
any gumbo row skipped, never a future gumbo row used), and the gate-contract
row shape (game_id/model_prob/model_prob_enriched/y present).

cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_enrichment_rows_mlb.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import enrichment_rows_mlb as erm
from scripts.platformkit.ingame.game_pk_bridge_live import BridgeRow


class _StubResolver:
    def __init__(self, mapping):
        self._mapping = mapping

    def home_win(self, ticker):
        return self._mapping.get(ticker)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_happy_path_joins_and_enriches(tmp_path):
    grade_dir = tmp_path / "grade"
    gumbo_dir = tmp_path / "gumbo"
    bridge = [BridgeRow(game_pk=111, date="2026-07-03", away="A", home="B",
                        espn_id="9001", kalshi_ticker_stem="KXMLBGAME-26JUL031234ABHM")]
    _write_jsonl(gumbo_dir / "111.jsonl", [
        {"game_pk": 111, "ts": "20260703_180000", "outs": 1, "base_state": 2,
         "balls": 1, "strikes": 2},
        {"game_pk": 111, "ts": "20260703_181000", "outs": 2, "base_state": 5,
         "balls": 0, "strikes": 0},
    ])
    _write_jsonl(grade_dir / "KXMLBGAME-26JUL031234ABHM.jsonl", [
        {"sport": "mlb", "game_id": "KXMLBGAME-26JUL031234ABHM",
         "ts": "2026-07-03T18:05:00Z", "market_prob": 0.55, "model_prob": 0.60},
        {"sport": "mlb", "game_id": "KXMLBGAME-26JUL031234ABHM",
         "ts": "2026-07-03T18:12:00Z", "market_prob": 0.58, "model_prob": 0.62},
    ])
    resolver = _StubResolver({"KXMLBGAME-26JUL031234ABHM": 1})

    rows = erm.build_rows("2026-07-03", grade_dir=grade_dir, gumbo_dir=gumbo_dir,
                          bridge_rows=bridge, outcome_resolver=resolver)

    assert len(rows) == 2
    r0, r1 = rows
    # first grade tick (18:05) as-ofs to the FIRST gumbo row (18:00), not the second (18:10)
    assert r0["base_out_state"] == 2 * 3 + 1  # base_state=2, outs=1
    assert r0["count_state"] == "1-2"
    assert r0["outcome"] == 1 and r0["y"] == 1
    assert r0["model_prob"] == 0.60
    assert 0.0 < r0["model_prob_enriched"] < 1.0
    # second grade tick (18:12) as-ofs to the SECOND gumbo row (18:10)
    assert r1["base_out_state"] == 5 * 3 + 2  # base_state=5, outs=2
    assert r1["count_state"] == "0-0"
    for r in rows:
        assert set(("game_id", "model_prob", "model_prob_enriched", "y")) <= set(r)


def test_unbridgeable_game_pk_skipped_never_guessed(tmp_path):
    grade_dir = tmp_path / "grade"
    gumbo_dir = tmp_path / "gumbo"
    # No espn_id / kalshi_ticker_stem resolved -- an honest bridge miss.
    bridge = [BridgeRow(game_pk=222, date="2026-07-03", away="A", home="B",
                        espn_id=None, kalshi_ticker_stem=None)]
    _write_jsonl(gumbo_dir / "222.jsonl", [
        {"game_pk": 222, "ts": "20260703_180000", "outs": 0, "base_state": 0},
    ])
    rows = erm.build_rows("2026-07-03", grade_dir=grade_dir, gumbo_dir=gumbo_dir,
                          bridge_rows=bridge, outcome_resolver=None)
    assert rows == []


def test_no_gumbo_sidecar_skipped(tmp_path):
    grade_dir = tmp_path / "grade"
    gumbo_dir = tmp_path / "gumbo"
    bridge = [BridgeRow(game_pk=333, date="2026-07-03", away="A", home="B",
                        espn_id="9002", kalshi_ticker_stem=None)]
    _write_jsonl(grade_dir / "9002.jsonl", [
        {"sport": "mlb", "game_id": "9002", "ts": "2026-07-03T18:05:00Z",
         "market_prob": 0.5, "model_prob": 0.5},
    ])
    rows = erm.build_rows("2026-07-03", grade_dir=grade_dir, gumbo_dir=gumbo_dir,
                          bridge_rows=bridge, outcome_resolver=None)
    assert rows == []


def test_tick_before_first_gumbo_row_skipped(tmp_path):
    grade_dir = tmp_path / "grade"
    gumbo_dir = tmp_path / "gumbo"
    bridge = [BridgeRow(game_pk=444, date="2026-07-03", away="A", home="B",
                        espn_id="9003", kalshi_ticker_stem=None)]
    _write_jsonl(gumbo_dir / "444.jsonl", [
        {"game_pk": 444, "ts": "20260703_180000", "outs": 0, "base_state": 0},
    ])
    _write_jsonl(grade_dir / "9003.jsonl", [
        # tick ts is BEFORE the only gumbo row -- no as-of state exists yet.
        {"sport": "mlb", "game_id": "9003", "ts": "2026-07-03T17:00:00Z",
         "market_prob": 0.5, "model_prob": 0.5},
    ])
    rows = erm.build_rows("2026-07-03", grade_dir=grade_dir, gumbo_dir=gumbo_dir,
                          bridge_rows=bridge, outcome_resolver=None)
    assert rows == []


def test_outcome_none_when_no_ticker_or_unresolved(tmp_path):
    grade_dir = tmp_path / "grade"
    gumbo_dir = tmp_path / "gumbo"
    bridge = [BridgeRow(game_pk=555, date="2026-07-03", away="A", home="B",
                        espn_id="9004", kalshi_ticker_stem=None)]
    _write_jsonl(gumbo_dir / "555.jsonl", [
        {"game_pk": 555, "ts": "20260703_180000", "outs": 0, "base_state": 0},
    ])
    _write_jsonl(grade_dir / "9004.jsonl", [
        {"sport": "mlb", "game_id": "9004", "ts": "2026-07-03T18:05:00Z",
         "market_prob": 0.5, "model_prob": 0.5},
    ])
    rows = erm.build_rows("2026-07-03", grade_dir=grade_dir, gumbo_dir=gumbo_dir,
                          bridge_rows=bridge, outcome_resolver=None)
    assert len(rows) == 1
    assert rows[0]["outcome"] is None and rows[0]["y"] is None


def test_rows_fn_today_never_raises(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(erm, "build_rows", boom)
    assert erm.rows_fn_today() == []


def test_malformed_gumbo_row_out_of_range_skipped(tmp_path):
    grade_dir = tmp_path / "grade"
    gumbo_dir = tmp_path / "gumbo"
    bridge = [BridgeRow(game_pk=666, date="2026-07-03", away="A", home="B",
                        espn_id="9005", kalshi_ticker_stem=None)]
    _write_jsonl(gumbo_dir / "666.jsonl", [
        {"game_pk": 666, "ts": "20260703_180000", "outs": 9, "base_state": 0},
    ])
    _write_jsonl(grade_dir / "9005.jsonl", [
        {"sport": "mlb", "game_id": "9005", "ts": "2026-07-03T18:05:00Z",
         "market_prob": 0.5, "model_prob": 0.5},
    ])
    rows = erm.build_rows("2026-07-03", grade_dir=grade_dir, gumbo_dir=gumbo_dir,
                          bridge_rows=bridge, outcome_resolver=None)
    assert rows == []
