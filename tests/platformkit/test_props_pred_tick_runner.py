"""Per-file test for props_pred_tick_runner -- supervised M13 daemon (W11).

NO full pytest. Run only this file:
  cd /c/Users/neelj/nba-ai-system &&
  python -m pytest tests/platformkit/test_props_pred_tick_runner.py -q
"""
from __future__ import annotations

import json
import pathlib

from scripts.platformkit.props import props_pred_tick_runner as r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_sleep(s):
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bounded_run_stops_at_max_ticks(tmp_path):
    """run() with max_ticks=3 executes exactly 3 ticks."""
    n = r.run(score_fn=lambda now: [],
              output_path=tmp_path / "snap.json",
              clock=lambda: 1.0, sleep=_no_sleep, max_ticks=3)
    assert n == 3


def test_heartbeat_at_boot_and_per_tick(monkeypatch, tmp_path):
    """Heartbeat advanced at boot + after each tick."""
    beats = []
    monkeypatch.setattr(r, "_beat", lambda now=None: beats.append(now))
    r.run(score_fn=lambda now: [],
          output_path=tmp_path / "snap.json",
          clock=lambda: 11.0, sleep=_no_sleep, max_ticks=2)
    assert len(beats) == 3
    assert 11.0 in beats


def test_unavailable_when_no_lines(tmp_path):
    """When score_fn returns [], overall=UNAVAILABLE in the snapshot."""
    out = tmp_path / "props.json"
    doc = r.tick(now=5.0, score_fn=lambda now: [], output_path=out)
    assert doc["overall"] == "UNAVAILABLE"
    assert doc["card_count"] == 0
    data = json.loads(out.read_text(encoding="ascii"))
    assert data["overall"] == "UNAVAILABLE"


def test_props_written_when_available(tmp_path):
    """When score_fn returns rows, they appear in the snapshot."""
    rows = [
        {"player": "LeBron James", "stat": "PTS", "line": 27.5,
         "p_over": 0.54, "p_under": 0.46, "proj_mean": 28.1,
         "tier": "A", "confidence": 0.72, "clv_is_proxy": True},
    ]
    out = tmp_path / "props.json"
    doc = r.tick(now=100.0, score_fn=lambda now: rows, output_path=out)
    assert doc["card_count"] == 1
    assert doc["overall"] == "ok"
    data = json.loads(out.read_text(encoding="ascii"))
    assert data["rows"][0]["player"] == "LeBron James"


def test_no_dollar_pnl_in_envelope(tmp_path):
    """Envelope must NEVER contain a dollar P&L field."""
    out = tmp_path / "props.json"
    r.tick(now=1.0, score_fn=lambda now: [], output_path=out)
    raw = out.read_text(encoding="ascii")
    assert "dollar_pnl" not in raw
    assert "pnl_usd" not in raw


def test_score_fn_raise_degrades(tmp_path):
    """A raising score_fn degrades to UNAVAILABLE; loop continues."""
    def _boom(now):
        raise RuntimeError("pricer down")

    n = r.run(score_fn=_boom,
              output_path=tmp_path / "snap.json",
              clock=lambda: 0.0, sleep=_no_sleep, max_ticks=2)
    assert n == 2
    # After a raise, the file should exist with degraded or UNAVAILABLE state
    snap = tmp_path / "snap.json"
    assert snap.exists()
    data = json.loads(snap.read_text(encoding="ascii"))
    assert data["card_count"] == 0


def test_p_over_in_range(tmp_path):
    """p_over values from score_fn must be in [0, 1]."""
    rows = [{"player": "X", "stat": "REB", "p_over": 0.6, "p_under": 0.4}]
    out = tmp_path / "props.json"
    r.tick(now=1.0, score_fn=lambda now: rows, output_path=out)
    data = json.loads(out.read_text(encoding="ascii"))
    for row in data["rows"]:
        p = row.get("p_over")
        if p is not None:
            assert 0.0 <= float(p) <= 1.0


def test_should_stop_halts_loop(tmp_path):
    calls = {"n": 0}

    def _stop():
        calls["n"] += 1
        return calls["n"] >= 2

    n = r.run(score_fn=lambda now: [],
              output_path=tmp_path / "snap.json",
              clock=lambda: 0.0, sleep=_no_sleep,
              should_stop=_stop, max_ticks=99)
    assert n == 1


def test_honest_note_in_snapshot(tmp_path):
    """The snapshot must include an honest_note (calibration not edge)."""
    out = tmp_path / "props.json"
    r.tick(now=2.0, score_fn=lambda now: [], output_path=out)
    data = json.loads(out.read_text(encoding="ascii"))
    assert "honest_note" in data
    note = data["honest_note"].lower()
    assert "measurement" in note or "calibration" in note or "unavailable" in note


def test_tick_writes_prop_cards_cache(tmp_path, monkeypatch):
    """The tick writes the decoupled prop_cards_cache the fast m10 board reads."""
    import scripts.platformkit.bestbets.prop_cards_cache as cache
    cache_path = tmp_path / "prop_cards_cache.json"
    monkeypatch.setattr(cache, "_DEFAULT_PATH", cache_path)

    rows = [{"player": "X", "stat": "PTS", "p_over": 0.6,
             "sport": "mlb", "model_only": True}]
    out = tmp_path / "snap.json"
    r.tick(now=1000.0, score_fn=lambda now: rows, output_path=out)
    assert cache_path.exists()
    doc = json.loads(cache_path.read_text(encoding="ascii"))
    assert doc["card_count"] == 1
    assert doc["overall"] == "ok"


def test_tick_write_cache_false_skips_cache(tmp_path, monkeypatch):
    """write_cache=False isolates a tick from the cache side-write."""
    import scripts.platformkit.bestbets.prop_cards_cache as cache
    cache_path = tmp_path / "prop_cards_cache.json"
    monkeypatch.setattr(cache, "_DEFAULT_PATH", cache_path)
    out = tmp_path / "snap.json"
    r.tick(now=1.0, score_fn=lambda now: [{"player": "Y"}],
           output_path=out, write_cache=False)
    assert not cache_path.exists()


def test_envelope_has_n_more_field(tmp_path):
    """The snapshot envelope carries the honest n_more_model_only tally."""
    out = tmp_path / "snap.json"
    doc = r.tick(now=1.0, score_fn=lambda now: [], output_path=out,
                 write_cache=False)
    assert "n_more_model_only" in doc


if __name__ == "__main__":
    import sys, tempfile
    td = pathlib.Path(tempfile.mkdtemp())
    test_unavailable_when_no_lines(td)
    print("ok: unavailable_when_no_lines")
    test_props_written_when_available(td)
    print("ok: props_written_when_available")
    sys.exit(0)
