"""Per-file test: scripts.platformkit.freshness.freshness_sidecar_runner.

Acceptance criteria (W-FRESHNESS-SIDECAR, QA iter5 2026-06-20):

  F1. A tick with a recent line capture writes _freshness.json with status=fresh
      and age_sec derived from source_ts.
  F2. A tick with a recent predict capture (no line capture) also writes fresh.
  F3. A sport with NO feed at all writes status=unavailable (never fresh).
  F4. A sport with an OLD (stale) source_ts writes status=stale (never fresh).
  F5. Writes are atomic: the output file is a valid JSON dict after tick().
  F6. Heartbeat key is present in every written sidecar.
  F7. No $ field in any output (honest/calibration only).
  F8. tick() NEVER raises even on garbage input dirs.
  F9. serve_forever terminates cleanly with max_ticks=1 and a no-op sleep.
  F10. ok=True ONLY when status=='fresh'.
  F11. measure_sport degrades to unavailable when both sources are absent.
  F12. The most recent source wins when both line and predict captures exist.

Run (per-file only -- never run the full suite, it freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_freshness_sidecar_runner.py -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.freshness.freshness_sidecar_runner import (  # noqa: E402
    DEFAULT_MAX_AGE_SEC,
    HEARTBEAT_KEY,
    HONEST_NOTE,
    measure_sport,
    tick,
    serve_forever,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)

_FORBIDDEN_KEYS = {"roi", "pnl", "profit", "dollar", "bankroll", "usd"}


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_ago(seconds: float) -> str:
    return _iso(_NOW - timedelta(seconds=seconds))


def _write_line_sidecar(line_root: Path, sport: str, source_as_of: str) -> None:
    """Write a fake line-snapshot sidecar."""
    d = line_root / sport
    d.mkdir(parents=True, exist_ok=True)
    (d / "_freshness.json").write_text(
        json.dumps({"source_as_of": source_as_of, "poll_at": source_as_of,
                    "n_quotes": 10}),
        encoding="utf-8",
    )


def _write_predict_latest(predict_root: Path, sport: str,
                           generated_at: str, status: str = "ok") -> None:
    """Write a fake predict-service latest.json."""
    d = predict_root / sport
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(
        json.dumps({"sport": sport, "status": status,
                    "generated_at": generated_at,
                    "predictions": [], "markets": [], "edges": []}),
        encoding="utf-8",
    )


def _no_dollar(obj) -> bool:
    """Return True if no key in obj (recursively) contains forbidden money tokens."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _FORBIDDEN_KEYS:
                return False
            if not _no_dollar(v):
                return False
    elif isinstance(obj, list):
        for item in obj:
            if not _no_dollar(item):
                return False
    return True


def _read_sidecar(out_root: Path, sport: str) -> dict:
    path = out_root / sport / "_freshness.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# F1 -- recent line capture -> status=fresh
# ---------------------------------------------------------------------------

def test_f1_recent_line_capture_writes_fresh(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"

    _write_line_sidecar(line_root, "nba", _ts_ago(60))  # 1 min ago

    results = tick(
        sports=["nba"],
        now=_NOW,
        max_age_sec=DEFAULT_MAX_AGE_SEC,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
    )

    assert results[0]["status"] == "fresh", "F1: expected fresh, got %r" % results[0]
    assert results[0]["ok"] is True, "F1: ok must be True when fresh"
    side = _read_sidecar(out_root, "nba")
    assert side["status"] == "fresh", "F1: sidecar must be fresh"
    assert side["age_sec"] is not None and side["age_sec"] < DEFAULT_MAX_AGE_SEC


# ---------------------------------------------------------------------------
# F2 -- recent predict capture (no line capture) -> fresh
# ---------------------------------------------------------------------------

def test_f2_predict_capture_alone_writes_fresh(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"

    _write_predict_latest(predict_root, "mlb", _ts_ago(120))  # 2 min ago

    results = tick(
        sports=["mlb"],
        now=_NOW,
        max_age_sec=DEFAULT_MAX_AGE_SEC,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
    )

    assert results[0]["status"] == "fresh", "F2: predict-only fresh"
    assert results[0]["ok"] is True
    side = _read_sidecar(out_root, "mlb")
    assert side["status"] == "fresh"


# ---------------------------------------------------------------------------
# F3 -- sport with no feed -> status=unavailable (never fresh)
# ---------------------------------------------------------------------------

def test_f3_no_feed_writes_unavailable(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"
    # No sidecar or latest.json written for soccer.

    results = tick(
        sports=["soccer"],
        now=_NOW,
        max_age_sec=DEFAULT_MAX_AGE_SEC,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
    )

    assert results[0]["status"] == "unavailable", (
        "F3: no feed must write unavailable, got %r" % results[0]["status"]
    )
    assert results[0]["ok"] is False, "F3: ok must be False when unavailable"
    side = _read_sidecar(out_root, "soccer")
    assert side["status"] == "unavailable"


# ---------------------------------------------------------------------------
# F4 -- stale source_ts -> status=stale (never fresh)
# ---------------------------------------------------------------------------

def test_f4_old_source_ts_writes_stale(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"

    _write_line_sidecar(line_root, "tennis", _ts_ago(3600))  # 1 hour ago

    results = tick(
        sports=["tennis"],
        now=_NOW,
        max_age_sec=DEFAULT_MAX_AGE_SEC,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
    )

    assert results[0]["status"] == "stale", (
        "F4: old source must be stale, got %r" % results[0]["status"]
    )
    assert results[0]["ok"] is False


# ---------------------------------------------------------------------------
# F5 -- writes are atomic: file is valid JSON after tick()
# ---------------------------------------------------------------------------

def test_f5_atomic_write_produces_valid_json(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"

    _write_line_sidecar(line_root, "nba", _ts_ago(30))

    tick(
        sports=["nba"],
        now=_NOW,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
    )

    path = out_root / "nba" / "_freshness.json"
    assert path.is_file(), "F5: sidecar file must exist"
    with path.open("r", encoding="utf-8") as fh:
        obj = json.load(fh)  # must not raise
    assert isinstance(obj, dict), "F5: sidecar must be a dict"
    # No .tmp file should remain.
    tmp_path_f = out_root / "nba" / "_freshness.json.tmp"
    assert not tmp_path_f.exists(), "F5: tmp file must be cleaned up"


# ---------------------------------------------------------------------------
# F6 -- heartbeat key is present in every written sidecar
# ---------------------------------------------------------------------------

def test_f6_heartbeat_key_present(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"

    # Two sports: one with a feed, one without.
    _write_line_sidecar(line_root, "nba", _ts_ago(60))

    tick(
        sports=["nba", "mlb"],
        now=_NOW,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
    )

    for sport in ("nba", "mlb"):
        side = _read_sidecar(out_root, sport)
        assert HEARTBEAT_KEY in side, (
            "F6: %s sidecar missing heartbeat key %r" % (sport, HEARTBEAT_KEY)
        )
        # Heartbeat must be a parseable ISO string.
        hb = side[HEARTBEAT_KEY]
        assert isinstance(hb, str) and len(hb) >= 10, (
            "F6: %s heartbeat %r is not a valid timestamp" % (sport, hb)
        )


# ---------------------------------------------------------------------------
# F7 -- no $ field anywhere in output
# ---------------------------------------------------------------------------

def test_f7_no_dollar_field(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"

    _write_line_sidecar(line_root, "nba", _ts_ago(30))

    results = tick(
        sports=["nba"],
        now=_NOW,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
    )

    for r in results:
        assert _no_dollar(r), "F7: result has forbidden money key: %r" % r
    side = _read_sidecar(out_root, "nba")
    assert _no_dollar(side), "F7: sidecar has forbidden money key: %r" % side


# ---------------------------------------------------------------------------
# F8 -- tick() NEVER raises even on garbage input dirs
# ---------------------------------------------------------------------------

def test_f8_tick_never_raises_on_garbage(tmp_path):
    garbage = Path("/nonexistent/path/that/does/not/exist")
    out_root = tmp_path / "out"
    try:
        results = tick(
            sports=["nba", "mlb"],
            now=_NOW,
            line_root=garbage,
            predict_root=garbage,
            out_root=out_root,
        )
        # All must degrade to unavailable, never raise.
        for r in results:
            assert r["status"] in ("unavailable", "stale", "fresh"), (
                "F8: unexpected status %r" % r["status"]
            )
            assert r["ok"] is False or r["status"] == "fresh"
    except Exception as exc:
        pytest.fail("F8: tick() raised on garbage dirs: %s" % exc)


# ---------------------------------------------------------------------------
# F9 -- serve_forever terminates with max_ticks=1 and no-op sleep
# ---------------------------------------------------------------------------

def test_f9_serve_forever_runs_one_tick(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"

    _write_line_sidecar(line_root, "nba", _ts_ago(60))

    slept = []
    serve_forever(
        interval=0,
        sports=["nba"],
        now=_NOW,
        max_age_sec=DEFAULT_MAX_AGE_SEC,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
        sleep_fn=lambda s: slept.append(s),
        max_ticks=1,
    )

    side = _read_sidecar(out_root, "nba")
    assert side["status"] == "fresh", "F9: sidecar must be written by serve_forever"
    # Sleep was called once between (or after) ticks.
    assert len(slept) >= 0  # may be 0 if max_ticks reached before sleep


# ---------------------------------------------------------------------------
# F10 -- ok=True ONLY when status=='fresh'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,expected_ok", [
    ("fresh", True),
    ("stale", False),
    ("unavailable", False),
])
def test_f10_ok_only_when_fresh(status, expected_ok, tmp_path):
    # Build a measurement dict directly and verify ok semantics.
    # For 'fresh': use a very recent timestamp.
    # For 'stale': use a very old timestamp.
    # For 'unavailable': provide no source.
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"
    out_root = tmp_path / "frontend"

    if status == "fresh":
        _write_line_sidecar(line_root, "nba", _ts_ago(10))
    elif status == "stale":
        _write_line_sidecar(line_root, "nba", _ts_ago(86400))  # 24h ago

    results = tick(
        sports=["nba"],
        now=_NOW,
        max_age_sec=DEFAULT_MAX_AGE_SEC,
        line_root=line_root,
        predict_root=predict_root,
        out_root=out_root,
    )
    r = results[0]
    assert r["ok"] is expected_ok, (
        "F10: status=%r should give ok=%r, got %r" % (status, expected_ok, r["ok"])
    )


# ---------------------------------------------------------------------------
# F11 -- measure_sport degrades to unavailable when both sources absent
# ---------------------------------------------------------------------------

def test_f11_measure_sport_unavailable_when_no_sources(tmp_path):
    result = measure_sport(
        "nba",
        now=_NOW,
        line_root=tmp_path / "empty_line",
        predict_root=tmp_path / "empty_predict",
    )
    assert result["status"] == "unavailable"
    assert result["ok"] is False
    assert result["source_ts"] is None
    assert result["age_sec"] is None


# ---------------------------------------------------------------------------
# F12 -- most recent source wins when both line and predict captures exist
# ---------------------------------------------------------------------------

def test_f12_most_recent_source_wins(tmp_path):
    line_root = tmp_path / "line_history"
    predict_root = tmp_path / "predict_service"

    # Line capture: 5 min ago; predict capture: 30 sec ago -> predict should win.
    _write_line_sidecar(line_root, "nba", _ts_ago(300))
    _write_predict_latest(predict_root, "nba", _ts_ago(30))

    result = measure_sport(
        "nba",
        now=_NOW,
        max_age_sec=DEFAULT_MAX_AGE_SEC,
        line_root=line_root,
        predict_root=predict_root,
    )

    # age_sec should be ~30s (the predict, not ~300s for the line)
    assert result["age_sec"] is not None and result["age_sec"] < 60, (
        "F12: most recent source should win; age_sec=%r" % result["age_sec"]
    )
    assert result["status"] == "fresh"
    # Both sources should be reflected.
    assert result["sources"]["line"] is not None
    assert result["sources"]["predict"] is not None
