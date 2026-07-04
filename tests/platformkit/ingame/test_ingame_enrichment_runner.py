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


def test_heartbeat_component_name_matches_registered_spec():
    assert runner.HEARTBEAT_COMPONENT == "m37_ingame_enrichment"
