"""Per-file test for inplay_capture_runner -- supervised W4 capture loop-wrapper. NO full pytest.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_capture_runner.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import inplay_capture_runner as r


def _offline_kwargs(tmp_path):
    """Stub every external chain so the tested path needs NO network / NO predictor."""
    return dict(
        sports=["mlb"],
        live_state_fn=lambda s, g: None,        # no live games -> idle, zero pairs
        model_fn=lambda s, st: None,
        inplay_fetch_fn=lambda s: [],           # dead feed -> zero live games, clean tick
        finals_fn=lambda s: [],
        grade_dir=tmp_path / "grade",
        ledger_path=tmp_path / "ledger.jsonl",
        heartbeat_path=tmp_path / "_hb.json",
    )


def test_bounded_run_stops(tmp_path):
    """A bounded run executes exactly max_ticks and ALWAYS stops (no real sleep)."""
    slept = []
    n = r.run(sleep=lambda s: slept.append(s), max_ticks=3, **_offline_kwargs(tmp_path))
    assert n == 3
    # serve_forever breaks at max_ticks BEFORE the post-tick sleep on the last tick,
    # so sleeps == max_ticks - 1.
    assert len(slept) == 2


def test_heartbeat_beats_at_boot_and_each_sleep(tmp_path, monkeypatch):
    """The runner beats m2_inplay_capture at boot + on every poll/sleep boundary."""
    beats = []
    monkeypatch.setattr(r, "_beat", lambda now=None: beats.append(now))
    r.run(sleep=lambda s: None, max_ticks=2, **_offline_kwargs(tmp_path))
    # 1 boot beat + 1 per sleep boundary (max_ticks-1 boundaries) = 2 total.
    assert len(beats) == 2


def test_writes_capture_heartbeat_file(tmp_path):
    """Each tick writes the stale-never-green JSON heartbeat envelope (paper, no $)."""
    hb = tmp_path / "_hb.json"
    kwargs = _offline_kwargs(tmp_path)
    kwargs["heartbeat_path"] = hb
    r.run(sleep=lambda s: None, max_ticks=1, **kwargs)
    assert hb.exists()
    import json
    doc = json.loads(hb.read_text(encoding="ascii"))
    assert doc["measurement_only"] is True
    assert doc["executed"] is False and doc["edge_claimed"] is False
    # PAPER-ONLY: no $ field key anywhere in the heartbeat.
    assert not any("$" in str(k) for k in doc)


def test_tick_error_never_crashes(tmp_path):
    """A raising fetch is isolated inside poll_once; the loop keeps ticking, never raises."""
    kwargs = _offline_kwargs(tmp_path)

    def _boom(s):
        raise RuntimeError("feed dead")

    kwargs["inplay_fetch_fn"] = _boom
    n = r.run(sleep=lambda s: None, max_ticks=2, **kwargs)
    assert n == 2


def test_default_kwargs_enable_both_mlb_deep_and_kbo_deep(tmp_path, monkeypatch):
    """The wave-58 fix: run() must setdefault BOTH mlb_deep and kbo_deep to True so the
    kbo_capture_wire enrichment chain (kbo_relay_state_provider) is no longer dead code
    in production, exactly mirroring the existing mlb_deep production default. Spies on
    serve_forever's effective kwargs rather than asserting behavior, since the offline
    fixture never has a live kbo/mlb game to enrich."""
    seen_kwargs = {}

    def _spy_serve_forever(**kwargs):
        seen_kwargs.update(kwargs)
        return 0

    monkeypatch.setattr(r, "serve_forever", _spy_serve_forever)
    r.run(sleep=lambda s: None, max_ticks=1, **_offline_kwargs(tmp_path))
    assert seen_kwargs.get("mlb_deep") is True
    assert seen_kwargs.get("kbo_deep") is True


if __name__ == "__main__":
    import sys
    import tempfile
    import pathlib
    for fn in (test_bounded_run_stops, test_writes_capture_heartbeat_file,
               test_tick_error_never_crashes):
        with tempfile.TemporaryDirectory() as d:
            fn(pathlib.Path(d))
        print("ok:", fn.__name__)
    sys.exit(0)
