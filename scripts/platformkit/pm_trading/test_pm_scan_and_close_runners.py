"""Per-file test for the M17 (kalshi_scan) + M18 (pm_close_capture) runners.

Offline (injected scan_fn / sweep_fn): each runner advances its heartbeat every tick,
writes a $-free status/high-water artifact, never raises on a failing sweep, and the run
loop honors max_ticks / should_stop. No network.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/pm_trading/test_pm_scan_and_close_runners.py -q
"""
from __future__ import annotations

import json

import scripts.platformkit.pm_trading.kalshi_scan_runner as scan
import scripts.platformkit.pm_trading.pm_close_capture_runner as cap


# -- M17 kalshi scan runner ---------------------------------------------------

def test_scan_tick_updates_highwater_and_beats(monkeypatch, tmp_path):
    monkeypatch.setattr(scan, "_HWM_PATH", tmp_path / "hwm.json")
    beats = []
    monkeypatch.setattr(scan, "_beat", lambda now=None: beats.append(now))
    rep = scan.tick(now=5.0, scan_fn=lambda lg: {
        "by_type": {"game_winner": {"n_liquid": 7}}, "n_liquid_total": 7})
    assert rep["n_liquid_total"] == 7 and beats == [5.0]
    hwm = json.loads((tmp_path / "hwm.json").read_text(encoding="ascii"))
    assert hwm["by_type_max_liquid"]["game_winner"] == 7
    # a later LOWER scan must not lower the high-water mark
    scan.tick(now=6.0, scan_fn=lambda lg: {
        "by_type": {"game_winner": {"n_liquid": 2}}, "n_liquid_total": 2})
    hwm = json.loads((tmp_path / "hwm.json").read_text(encoding="ascii"))
    assert hwm["by_type_max_liquid"]["game_winner"] == 7   # peak retained


def test_scan_run_honors_max_ticks(monkeypatch, tmp_path):
    monkeypatch.setattr(scan, "_HWM_PATH", tmp_path / "hwm.json")
    monkeypatch.setattr(scan, "_beat", lambda now=None: None)
    n = scan.run(scan_fn=lambda lg: {"by_type": {}, "n_liquid_total": 0},
                 interval_sec=0.0, clock=lambda: 1.0, sleep=lambda s: None, max_ticks=3)
    assert n == 3


def test_scan_tick_never_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(scan, "_HWM_PATH", tmp_path / "hwm.json")
    monkeypatch.setattr(scan, "_beat", lambda now=None: None)
    rep = scan.tick(now=1.0, scan_fn=lambda lg: (_ for _ in ()).throw(RuntimeError("x")))
    assert rep["n_liquid_total"] == 0


# -- M18 pm close-capture runner ----------------------------------------------

def test_close_tick_writes_status_and_beats(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    beats = []
    monkeypatch.setattr(cap, "_beat", lambda now=None: beats.append(now))
    doc = cap.tick(now=9.0, status_path=status_p, sweep_fn=lambda: {
        "n_targets": 3, "n_captured": 2, "n_no_close": 1, "n_proxy": 0})
    assert doc["n_captured"] == 2 and doc["executed"] is False and beats == [9.0]
    on_disk = json.loads(status_p.read_text(encoding="ascii"))
    assert on_disk["component"] == "m18_pm_close_capture"


def test_close_status_is_dollar_free(monkeypatch, tmp_path):
    status_p = tmp_path / "s.json"
    monkeypatch.setattr(cap, "_beat", lambda now=None: None)
    cap.tick(now=1.0, status_path=status_p, sweep_fn=lambda: {"n_captured": 1})
    doc = json.loads(status_p.read_text(encoding="ascii"))
    doc.pop("honest_note", None)
    raw = json.dumps(doc).lower()
    for banned in ("$", "roi", "pnl", "dollar", "usd"):
        assert banned not in raw


def test_close_run_honors_should_stop(monkeypatch, tmp_path):
    monkeypatch.setattr(cap, "_beat", lambda now=None: None)
    n = cap.run(sweep_fn=lambda: {"n_captured": 0}, status_path=tmp_path / "s.json",
                interval_sec=0.0, clock=lambda: 1.0, sleep=lambda s: None,
                should_stop=lambda: True, max_ticks=9)
    assert n == 0
