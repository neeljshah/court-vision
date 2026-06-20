"""Per-file test for ingame_pred_tick_runner -- supervised M11 daemon.

Covers:
  - tick writes per-game live_pred_<id>.json
  - <5 graded pairs -> clv_status INSUFFICIENT_DATA (never fabricated)
  - writes m11 heartbeat at boot and per tick
  - absent live games -> UNAVAILABLE sentinel (honest, never green)
  - no $ field in output

NO full pytest. Run only this file:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest scripts/platformkit/ingame/test_ingame_pred_tick_runner.py -q
"""
from __future__ import annotations

import json
import pathlib

import pytest

import scripts.platformkit.ingame.ingame_pred_tick_runner as r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_sleep(s):
    pass


def _make_live_game_ids(*gids):
    return lambda: list(gids)


def _make_compose(doc_extra=None):
    def _compose(gid, now):
        d = {"game_id": gid, "generated_at": now, "win_prob": 0.55,
             "clv_status": "INSUFFICIENT_DATA", "edge_claimed": False}
        if doc_extra:
            d.update(doc_extra)
        return d
    return _compose


def _write_pairs(path: pathlib.Path, n: int) -> None:
    """Write n synthetic grade-pair rows to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(n):
        rows.append(json.dumps({
            "sport": "nba", "game_id": path.stem,
            "model_prob": 0.55, "market_prob": 0.52,
            "ts": "2026-06-20T01:0%d:00Z" % i,
        }))
    path.write_text("\n".join(rows), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLV pair count threshold
# ---------------------------------------------------------------------------

def test_clv_status_below_threshold():
    assert r.clv_status_from_pairs(0) == "INSUFFICIENT_DATA"
    assert r.clv_status_from_pairs(4) == "INSUFFICIENT_DATA"


def test_clv_status_at_threshold():
    assert r.clv_status_from_pairs(5) == "graded"


def test_clv_status_above_threshold():
    assert r.clv_status_from_pairs(10) == "graded"


def test_count_grade_pairs_no_file(tmp_path):
    """Missing JSONL -> 0 pairs (never raises)."""
    n = r._count_grade_pairs("nonexistent_game", sport="nba", grade_dir=tmp_path)
    assert n == 0


def test_count_grade_pairs_correct_count(tmp_path):
    """3 valid rows -> n=3."""
    _write_pairs(tmp_path / "nba" / "g100.jsonl", 3)
    n = r._count_grade_pairs("g100", sport="nba", grade_dir=tmp_path)
    assert n == 3


def test_count_grade_pairs_skips_incomplete_rows(tmp_path):
    """Rows missing model_prob/market_prob are excluded from count."""
    p = tmp_path / "nba" / "g200.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"model_prob": 0.5, "market_prob": 0.48}),  # valid
        json.dumps({"model_prob": 0.5}),                        # missing market_prob
        json.dumps({"market_prob": 0.48}),                      # missing model_prob
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    n = r._count_grade_pairs("g200", sport="nba", grade_dir=tmp_path)
    assert n == 1


# ---------------------------------------------------------------------------
# tick writes per-game JSON
# ---------------------------------------------------------------------------

def test_live_games_produce_files(tmp_path):
    """When live game IDs returned, a JSON file is written per game."""
    out_path = lambda gid: tmp_path / ("live_pred_%s.json" % gid)
    r.tick(now=1234.0,
           game_ids_fn=_make_live_game_ids("g001", "g002"),
           compose_fn=_make_compose(),
           out_path_fn=out_path)
    for gid in ("g001", "g002"):
        p = tmp_path / ("live_pred_%s.json" % gid)
        assert p.exists(), "Expected %s" % p
        data = json.loads(p.read_text(encoding="ascii"))
        assert data["game_id"] == gid
        assert data["clv_status"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# INSUFFICIENT_DATA honesty - compose sets it
# ---------------------------------------------------------------------------

def test_clv_insufficient_data_in_output(tmp_path):
    """Output JSON must carry clv_status=INSUFFICIENT_DATA by default."""
    out = tmp_path / "live_pred_gX.json"
    r.tick(now=2.0,
           game_ids_fn=lambda: ["gX"],
           compose_fn=_make_compose(),
           out_path_fn=lambda gid: out)
    assert out.exists()
    data = json.loads(out.read_text(encoding="ascii"))
    assert data["clv_status"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Absent live games -> UNAVAILABLE sentinel
# ---------------------------------------------------------------------------

def test_no_live_games_returns_false(tmp_path):
    """tick() returns ([], False) when no live games are found."""
    gids, has_live = r.tick(now=1.0,
                            game_ids_fn=lambda: [],
                            compose_fn=_make_compose(),
                            out_path_fn=lambda gid: tmp_path / gid)
    assert gids == []
    assert has_live is False


def test_unavailable_sentinel_written_when_no_live_games(tmp_path, monkeypatch):
    """When no live games, live_pred_UNAVAILABLE.json is written (honest)."""
    monkeypatch.setattr(r, "_INGAME_DIR", tmp_path)
    r.tick(now=3.0,
           game_ids_fn=lambda: [],
           compose_fn=_make_compose(),
           out_path_fn=lambda gid: tmp_path / ("live_pred_%s.json" % gid))
    upath = tmp_path / "live_pred_UNAVAILABLE.json"
    assert upath.exists(), "UNAVAILABLE sentinel not written"
    data = json.loads(upath.read_text(encoding="ascii"))
    assert data["status"] == "UNAVAILABLE"
    assert data["n_live_games"] == 0
    assert data["edge_claimed"] is False
    assert "pnl" not in str(data).lower()


# ---------------------------------------------------------------------------
# No $ field
# ---------------------------------------------------------------------------

def test_no_dollar_pnl_in_output(tmp_path):
    """Output JSON must NEVER carry a dollar P&L field."""
    # Inject a compose that adds forbidden keys.
    def _evil_compose(gid, now):
        return {"game_id": gid, "clv_status": "INSUFFICIENT_DATA",
                "dollar_pnl": 99, "pnl_usd": 50, "edge_claimed": False}

    out = tmp_path / "live_pred_gA.json"
    r.tick(now=2.0,
           game_ids_fn=lambda: ["gA"],
           compose_fn=_evil_compose,
           out_path_fn=lambda gid: out)
    if out.exists():
        raw = out.read_text(encoding="ascii")
        assert "dollar_pnl" not in raw, "dollar_pnl must be stripped"
        assert "pnl_usd" not in raw, "pnl_usd must be stripped"


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def test_heartbeat_at_boot_and_per_tick(monkeypatch, tmp_path):
    """Heartbeat advanced at boot + after each tick."""
    beats = []
    monkeypatch.setattr(r, "_beat", lambda now=None: beats.append(now))
    r.run(game_ids_fn=lambda: [],
          compose_fn=_make_compose(),
          out_path_fn=lambda gid: tmp_path / ("lp_%s.json" % gid),
          clock=lambda: 9.0, sleep=_no_sleep, max_ticks=2)
    assert len(beats) == 3  # 1 boot + 2 per-tick
    assert 9.0 in beats


# ---------------------------------------------------------------------------
# Bounded run + stop
# ---------------------------------------------------------------------------

def test_bounded_run_stops_at_max_ticks(tmp_path):
    """run() with max_ticks=2 executes exactly 2 ticks."""
    n = r.run(game_ids_fn=lambda: [],
              compose_fn=_make_compose(),
              out_path_fn=lambda gid: tmp_path / ("live_pred_%s.json" % gid),
              clock=lambda: 1.0, sleep=_no_sleep, max_ticks=2)
    assert n == 2


def test_live_games_returns_true(tmp_path):
    """tick() returns (gids, True) when live games are found."""
    gids, has_live = r.tick(now=1.0,
                            game_ids_fn=_make_live_game_ids("g1"),
                            compose_fn=_make_compose(),
                            out_path_fn=lambda gid: tmp_path / ("lp_%s.json" % gid))
    assert has_live is True
    assert "g1" in gids


def test_game_ids_fn_raise_degrades(tmp_path):
    """A raising game_ids_fn causes tick() to emit [] and not crash."""
    def _boom():
        raise OSError("no ids")

    gids, has_live = r.tick(now=0.0, game_ids_fn=_boom,
                            compose_fn=_make_compose(),
                            out_path_fn=lambda gid: tmp_path / gid)
    assert gids == []
    assert has_live is False


def test_should_stop_halts_loop(tmp_path):
    calls = {"n": 0}

    def _stop():
        calls["n"] += 1
        return calls["n"] >= 2

    n = r.run(game_ids_fn=lambda: [],
              compose_fn=_make_compose(),
              out_path_fn=lambda gid: tmp_path / gid,
              clock=lambda: 0.0, sleep=_no_sleep,
              should_stop=_stop, max_ticks=99)
    assert n == 1


def test_compose_exception_does_not_crash_tick(tmp_path):
    """A raising compose_fn must not crash tick()."""
    def _boom(gid, now):
        raise RuntimeError("compose dead")

    gids, has_live = r.tick(now=5.0,
                            game_ids_fn=_make_live_game_ids("x"),
                            compose_fn=_boom,
                            out_path_fn=lambda gid: tmp_path / ("lp_%s.json" % gid))
    # tick() must NOT raise even when compose explodes
    assert "x" in gids


# ---------------------------------------------------------------------------
# edge_claimed is always False
# ---------------------------------------------------------------------------

def test_edge_claimed_false_in_output(tmp_path):
    """Output JSON must have edge_claimed=False."""
    out = tmp_path / "live_pred_g99.json"
    r.tick(now=7.0,
           game_ids_fn=lambda: ["g99"],
           compose_fn=_make_compose(),
           out_path_fn=lambda gid: out)
    assert out.exists()
    data = json.loads(out.read_text(encoding="ascii"))
    assert data.get("edge_claimed") is False
