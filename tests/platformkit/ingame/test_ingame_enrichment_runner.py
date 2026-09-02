"""Per-file tests for ingame_enrichment_runner (injected fns, no real I/O).

cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_enrichment_runner.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_enrichment_runner as runner


def test_tick_composes_all_three_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    calls = {"fotmob": 0, "gumbo": 0, "book_depth": 0}

    def fotmob_fn():
        calls["fotmob"] += 1
        return {"n_matches": 2, "n_snapshots": 1}

    def gumbo_fn():
        calls["gumbo"] += 1
        return {"n_live_games": 3, "n_rows_written": 3}

    def book_depth_fn():
        calls["book_depth"] += 1
        return {"kalshi": {"n_snapshotted": 4}, "polymarket": {"n_snapshotted": 0}}

    doc = runner.tick(now=1000.0, fotmob_fn=fotmob_fn, gumbo_fn=gumbo_fn,
                      book_depth_fn=book_depth_fn)

    assert calls == {"fotmob": 1, "gumbo": 1, "book_depth": 1}
    assert doc["component"] == "ingame_enrichment"
    assert doc["edge_claimed"] is False
    assert doc["fotmob"]["n_snapshots"] == 1
    assert doc["gumbo"]["n_rows_written"] == 3
    assert doc["book_depth"]["kalshi"]["n_snapshotted"] == 4
    written = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert written["gumbo"]["n_live_games"] == 3


def test_one_source_raising_never_sinks_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom():
        raise RuntimeError("fotmob feed exploded")

    gumbo_called = []
    book_depth_called = []

    doc = runner.tick(
        now=1000.0,
        fotmob_fn=_boom,
        gumbo_fn=lambda: (gumbo_called.append(1), {"n_live_games": 1})[1],
        book_depth_fn=lambda: (book_depth_called.append(1), {"kalshi": {}})[1],
    )

    assert "error" in doc["fotmob"]
    assert doc["fotmob"]["error"] == "fotmob feed exploded"
    assert gumbo_called == [1]
    assert book_depth_called == [1]
    assert doc["gumbo"]["n_live_games"] == 1


def test_gumbo_raising_isolated_from_fotmob_and_book_depth(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom():
        raise ValueError("gumbo bootstrap failed")

    doc = runner.tick(
        now=1000.0,
        fotmob_fn=lambda: {"n_matches": 0},
        gumbo_fn=_boom,
        book_depth_fn=lambda: {"kalshi": {"n_snapshotted": 1}},
    )
    assert "error" in doc["gumbo"]
    assert doc["fotmob"]["n_matches"] == 0
    assert doc["book_depth"]["kalshi"]["n_snapshotted"] == 1


def test_all_three_raising_still_writes_a_doc_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom(name):
        def f():
            raise RuntimeError(name)
        return f

    doc = runner.tick(now=1000.0, fotmob_fn=_boom("a"), gumbo_fn=_boom("b"),
                      book_depth_fn=_boom("c"))
    assert doc["fotmob"]["error"] == "a"
    assert doc["gumbo"]["error"] == "b"
    assert doc["book_depth"]["error"] == "c"
    assert (tmp_path / "summary.json").exists()


def test_run_stops_after_max_ticks(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    monkeypatch.setattr(runner, "tick", lambda **kw: {"fotmob": {}, "gumbo": {}, "book_depth": {}})
    ticks = runner.run(max_ticks=3, clock=lambda: 1.0, sleep=lambda s: None)
    assert ticks == 3


def test_intertick_wait_plain_sleep_when_idle():
    slept = []
    runner._intertick_wait(30.0, {"gumbo": {"n_live_games": 0}}, slept.append)
    runner._intertick_wait(30.0, {"gumbo": {"error": "x"}}, slept.append)
    runner._intertick_wait(30.0, {}, slept.append)
    assert slept == [30.0, 30.0, 30.0], "no live MLB game -> idle cadence unchanged"


def test_intertick_wait_runs_gumbo_live_window_when_live(monkeypatch):
    from scripts.platformkit.ingame import gumbo_mlb_poller as poller
    calls = []
    monkeypatch.setattr(poller, "run_live_window",
                        lambda window_sec, **kw: calls.append(window_sec) or {"passes": 3})
    slept = []
    runner._intertick_wait(30.0, {"gumbo": {"n_live_games": 2}}, slept.append)
    assert calls == [30.0], "live MLB game -> inter-tick wait spent fast-polling gumbo"
    assert slept == [], "no idle sleep when the live window ran"


def test_heartbeat_component_name_matches_registered_spec():
    assert runner.HEARTBEAT_COMPONENT == "m37_ingame_enrichment"


def test_retention_runs_on_tick_zero_and_is_periodic(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)
    calls = []

    def _retention_fn():
        calls.append(1)
        return {"total_archived": 0, "total_errors": 0, "trees": []}

    doc0 = runner.tick(now=1000.0, tick_index=0,
                       fotmob_fn=lambda: {}, gumbo_fn=lambda: {}, book_depth_fn=lambda: {},
                       retention_fn=_retention_fn)
    assert "retention" in doc0 and calls == [1]

    doc1 = runner.tick(now=1030.0, tick_index=1,
                       fotmob_fn=lambda: {}, gumbo_fn=lambda: {}, book_depth_fn=lambda: {},
                       retention_fn=_retention_fn)
    assert "retention" not in doc1, "retention only fires on its periodic cadence"
    assert calls == [1], "not called again on a non-periodic tick"


def test_retention_raising_is_isolated_and_never_sinks_the_tick(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_SUMMARY_OUT", tmp_path / "summary.json")
    monkeypatch.setattr(runner, "_beat", lambda now_epoch=None: None)

    def _boom():
        raise RuntimeError("retention sweep exploded")

    doc = runner.tick(now=1000.0, tick_index=0,
                      fotmob_fn=lambda: {"n_matches": 1}, gumbo_fn=lambda: {},
                      book_depth_fn=lambda: {}, retention_fn=_boom)
    assert doc["retention"]["error"] == "retention sweep exploded"
    assert doc["fotmob"]["n_matches"] == 1, "a raising retention pass never sinks other sources"


def test_book_depth_state_is_threaded_across_ticks(monkeypatch):
    """S105 root cause: the runner is the only production caller of poll_once, and
    it used to pass state=None every tick -- so the sticky active-ticker list and
    the trade watermarks were discarded 30 s after being built."""
    from scripts.platformkit.ingame import ingame_book_depth_poller as poller

    seen = []

    def fake_poll_once(*, sports, state=None, **kw):
        seen.append(id(state))
        state.setdefault("kalshi_active", {}).setdefault("mlb", []).append("KXMLBGAME-X-AAA")
        return {"kalshi": {"n_snapshotted": 1}, "polymarket": {}}

    monkeypatch.setattr(poller, "poll_once", fake_poll_once)
    monkeypatch.setattr(runner, "_BOOK_DEPTH_STATE", {})
    runner._run_book_depth()
    runner._run_book_depth()
    assert len(set(seen)) == 1, "each tick got a fresh state dict"
    assert runner._BOOK_DEPTH_STATE["kalshi_active"]["mlb"] == ["KXMLBGAME-X-AAA"] * 2
