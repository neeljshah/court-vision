"""Per-file tests for scripts.platformkit.clv.kx_ticker_close (Lane 5).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/clv/test_kx_ticker_close.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.clv import kx_ticker_close as K


def _write_ticks(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# derive_close: still-open series (no settle row) -> last tick is the proxy
# ---------------------------------------------------------------------------

def test_derive_close_last_tick_still_open(tmp_path):
    p = tmp_path / "mlb" / "KXMLBGAME-TEST.jsonl"
    _write_ticks(p, [
        {"sport": "mlb", "game_id": "KXMLBGAME-TEST", "ts": "2026-07-01T00:00:00Z",
         "market_prob": 0.51, "model_prob": 0.50, "side": "home"},
        {"sport": "mlb", "game_id": "KXMLBGAME-TEST", "ts": "2026-07-01T01:00:00Z",
         "market_prob": 0.63, "model_prob": 0.55, "side": "home"},
    ])
    out = K.derive_close(p)
    assert out is not None
    assert out["close_prob"] == 0.63
    assert out["close_ts"] == "2026-07-01T01:00:00Z"
    assert out["n_ticks"] == 2
    assert out["close_kind"] == "last_tick"
    assert out["ticker"] == "KXMLBGAME-TEST"


# ---------------------------------------------------------------------------
# derive_close: game with a trailing settle-stamp row (no market_prob) -- the
# settle row must be EXCLUDED and the last real tick used instead.
# ---------------------------------------------------------------------------

def test_derive_close_final_game_ignores_settle_stamp_row(tmp_path):
    p = tmp_path / "mlb" / "KXMLBGAME-FINAL.jsonl"
    _write_ticks(p, [
        {"sport": "mlb", "game_id": "KXMLBGAME-FINAL", "ts": "2026-07-01T00:00:00Z",
         "market_prob": 0.40, "model_prob": 0.42, "side": "home"},
        {"sport": "mlb", "game_id": "KXMLBGAME-FINAL", "ts": "2026-07-01T02:00:00Z",
         "market_prob": 0.97, "model_prob": 0.95, "side": "home"},
        # settle_stamp.py's trailing row: no market_prob key at all.
        {"sport": "mlb", "game_id": "KXMLBGAME-FINAL", "ts": "2026-07-01T02:05:00Z",
         "settled": True, "home_win": 1.0, "state_summary": "FINAL"},
    ])
    out = K.derive_close(p)
    assert out is not None
    assert out["close_prob"] == 0.97
    assert out["n_ticks"] == 2  # settle row excluded from the count


# ---------------------------------------------------------------------------
# Honest absence: empty / all-invalid file yields None, never a fabricated close.
# ---------------------------------------------------------------------------

def test_derive_close_empty_file_returns_none(tmp_path):
    p = tmp_path / "mlb" / "KXMLBGAME-EMPTY.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    assert K.derive_close(p) is None


def test_derive_close_missing_file_returns_none(tmp_path):
    p = tmp_path / "mlb" / "KXMLBGAME-NOPE.jsonl"
    assert K.derive_close(p) is None


def test_derive_close_all_invalid_probs_returns_none(tmp_path):
    p = tmp_path / "mlb" / "KXMLBGAME-BAD.jsonl"
    _write_ticks(p, [
        {"sport": "mlb", "game_id": "KXMLBGAME-BAD", "ts": "2026-07-01T00:00:00Z",
         "market_prob": None, "model_prob": 0.5, "side": "home"},
        {"sport": "mlb", "game_id": "KXMLBGAME-BAD", "ts": "2026-07-01T00:01:00Z",
         "market_prob": 1.5, "model_prob": 0.5, "side": "home"},  # out of range
    ])
    assert K.derive_close(p) is None


# ---------------------------------------------------------------------------
# _iter_tick_files / _is_kx_ticker: only non-numeric (ticker) files are scanned;
# an ESPN-numeric game_id file must NEVER be picked up by this module.
# ---------------------------------------------------------------------------

def test_iter_tick_files_skips_espn_numeric_ids(tmp_path):
    _write_ticks(tmp_path / "mlb" / "401815820.jsonl", [
        {"sport": "mlb", "game_id": "401815820", "ts": "2026-07-01T00:00:00Z",
         "market_prob": 0.5, "model_prob": 0.5, "side": "home"},
    ])
    _write_ticks(tmp_path / "mlb" / "KXMLBGAME-X.jsonl", [
        {"sport": "mlb", "game_id": "KXMLBGAME-X", "ts": "2026-07-01T00:00:00Z",
         "market_prob": 0.5, "model_prob": 0.5, "side": "home"},
    ])
    files = K._iter_tick_files("mlb", grade_dir=tmp_path)
    names = [f.stem for f in files]
    assert "KXMLBGAME-X" in names
    assert "401815820" not in names


# ---------------------------------------------------------------------------
# write_closes: writes date-bucketed jsonl, idempotent on re-run.
# ---------------------------------------------------------------------------

def test_write_closes_writes_and_is_idempotent(tmp_path):
    grade_dir = tmp_path / "grade"
    out_dir = tmp_path / "closes"
    _write_ticks(grade_dir / "mlb" / "KXMLBGAME-A.jsonl", [
        {"sport": "mlb", "game_id": "KXMLBGAME-A", "ts": "2026-07-01T05:00:00Z",
         "market_prob": 0.61, "model_prob": 0.5, "side": "home"},
    ])
    _write_ticks(grade_dir / "mlb" / "KXMLBGAME-B.jsonl", [
        {"sport": "mlb", "game_id": "KXMLBGAME-B", "ts": "2026-07-01T06:00:00Z",
         "market_prob": 0.44, "model_prob": 0.5, "side": "home"},
    ])
    r1 = K.write_closes("mlb", grade_dir=grade_dir, out_dir=out_dir)
    assert r1["n_written"] == 2
    assert r1["n_skipped_existing"] == 0

    r2 = K.write_closes("mlb", grade_dir=grade_dir, out_dir=out_dir)
    assert r2["n_written"] == 0
    assert r2["n_skipped_existing"] == 2

    target = out_dir / "mlb" / "2026-07-01.jsonl"
    lines = [json.loads(l) for l in target.open(encoding="utf-8") if l.strip()]
    assert len(lines) == 2
    for row in lines:
        assert row["close_kind"] == "last_tick"


def test_write_closes_no_ticker_files_is_clean(tmp_path):
    grade_dir = tmp_path / "grade"
    out_dir = tmp_path / "closes"
    r = K.write_closes("mlb", grade_dir=grade_dir, out_dir=out_dir)
    assert r["n_ticker_files"] == 0
    assert r["n_written"] == 0


# ---------------------------------------------------------------------------
# get_close_prob: reads back a derived close by ticker across date buckets.
# ---------------------------------------------------------------------------

def test_get_close_prob_roundtrip(tmp_path):
    grade_dir = tmp_path / "grade"
    out_dir = tmp_path / "closes"
    _write_ticks(grade_dir / "mlb" / "KXMLBGAME-C.jsonl", [
        {"sport": "mlb", "game_id": "KXMLBGAME-C", "ts": "2026-07-02T10:00:00Z",
         "market_prob": 0.77, "model_prob": 0.5, "side": "home"},
    ])
    K.write_closes("mlb", grade_dir=grade_dir, out_dir=out_dir)
    rec = K.get_close_prob("KXMLBGAME-C", "mlb", closes_dir=out_dir)
    assert rec is not None
    assert rec["close_prob"] == 0.77
    assert rec["close_kind"] == "last_tick"


def test_get_close_prob_miss_returns_none(tmp_path):
    out_dir = tmp_path / "closes"
    assert K.get_close_prob("KXMLBGAME-NEVER-DERIVED", "mlb", closes_dir=out_dir) is None


# ---------------------------------------------------------------------------
# W1 FIX real-slice join-rate gate: after write_closes(), >=90% of a real
# 50-row slice of settled paper_ingame bets must resolve a kx close. This is
# the actual diagnosis this fix targets (436/436 settled paper_ingame rows
# were clv_status='no_close'); a real join-rate check, not a synthetic one.
# Skips (not fails) when this machine has <50 real settled paper_ingame rows
# on disk -- honest absence of data, never a weakened threshold.
# ---------------------------------------------------------------------------
def test_real_slice_join_rate_after_write_closes():
    from scripts.platformkit.ingame import paper_ingame as _pi

    rows = _pi.load_ingame_bets()
    settled = [r for r in rows if r.get("status") == "settled"]
    if len(settled) < 50:
        pytest.skip("fewer than 50 real settled paper_ingame rows on this machine")
    slice_ = settled[:50]

    for sport in {str(r.get("sport") or "").lower() for r in slice_ if r.get("sport")}:
        K.write_closes(sport)  # real derive pass against real data/cache/ingame_grade

    hits = 0
    for r in slice_:
        rec = K.get_close_prob(str(r.get("game_id")), str(r.get("sport") or ""))
        if rec is not None:
            hits += 1
    rate = hits / len(slice_)
    assert rate >= 0.90, (
        "BLOCKED-partial: real kx-close join rate is %.1f%% (%d/%d), below the "
        "90%% floor -- reporting honestly, not weakening the assert."
        % (rate * 100.0, hits, len(slice_)))
