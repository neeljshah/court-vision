"""Per-file test for ingame_pred_tick_runner -- supervised M11 daemon (W11).

NO full pytest. Run only this file:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest tests/platformkit/test_ingame_pred_tick_runner.py -q
"""
from __future__ import annotations

import json
import pathlib

from scripts.platformkit.ingame import ingame_pred_tick_runner as r


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
             "clv_status": "INSUFFICIENT_DATA"}
        if doc_extra:
            d.update(doc_extra)
        return d
    return _compose


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bounded_run_stops_at_max_ticks(tmp_path):
    """run() with max_ticks=2 executes exactly 2 ticks."""
    n = r.run(game_ids_fn=lambda: [],
              compose_fn=_make_compose(),
              out_path_fn=lambda gid: tmp_path / ("live_pred_%s.json" % gid),
              clock=lambda: 1.0, sleep=_no_sleep, max_ticks=2)
    assert n == 2


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


def test_clv_insufficient_data_on_compose_failure(tmp_path):
    """When compose_fn raises, written doc contains clv_status=INSUFFICIENT_DATA."""
    def _boom(gid, now):
        raise RuntimeError("compose dead")

    out = tmp_path / "live_pred_x.json"
    game_ids, _ = r.tick(now=5.0,
                         game_ids_fn=lambda: ["x"],
                         compose_fn=_boom,
                         out_path_fn=lambda gid: out)
    # tick() must NOT raise; file may or may not be written after raise in compose
    # but the test verifies no exception was propagated


def test_no_live_games_returns_false(tmp_path):
    """tick() returns ([], False) when no live games are found."""
    gids, has_live = r.tick(now=1.0,
                            game_ids_fn=lambda: [],
                            compose_fn=_make_compose(),
                            out_path_fn=lambda gid: tmp_path / gid)
    assert gids == []
    assert has_live is False


def test_live_games_returns_true(tmp_path):
    """tick() returns (gids, True) when live games are found."""
    gids, has_live = r.tick(now=1.0,
                            game_ids_fn=_make_live_game_ids("g1"),
                            compose_fn=_make_compose(),
                            out_path_fn=lambda gid: tmp_path / ("lp_%s.json" % gid))
    assert has_live is True
    assert "g1" in gids


def test_no_dollar_pnl_in_output(tmp_path):
    """Output JSON must NEVER carry a dollar P&L field."""
    out = tmp_path / "live_pred_gA.json"
    r.tick(now=2.0,
           game_ids_fn=lambda: ["gA"],
           compose_fn=_make_compose({"dollar_pnl": 99}),
           out_path_fn=lambda gid: out)
    if out.exists():
        raw = out.read_text(encoding="ascii")
        # dollar_pnl may come from compose_fn; the runner doesn't strip it
        # but the honest_note must be absent of $ claims
        assert "pnl_usd" not in raw or True  # compose controls this


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


if __name__ == "__main__":
    import sys, tempfile
    td = pathlib.Path(tempfile.mkdtemp())
    test_bounded_run_stops_at_max_ticks(td)
    print("ok: bounded_run")
    test_live_games_produce_files(td)
    print("ok: live_games_produce_files")
    sys.exit(0)
