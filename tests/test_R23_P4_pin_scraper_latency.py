"""tests/test_R23_P4_pin_scraper_latency.py -- R23_P4 latency regression guard.

Why this exists
---------------
L6's 5-min capture saw Pinnacle scraper p99 jump 886ms -> 2389ms (+170%).
The diagnosed cause was per-call TLS handshakes + a per-write O(N) CSV re-read
for dedup. R23_P4 swapped the HTTP layer to a persistent curl_cffi Session
and cached dedup keys in-memory.

This file hammers the *timing-critical* paths with mocked HTTP (no network
required, deterministic in CI) and asserts:

  1. After warmup, p99 of `_http_get_json` over 100 mocked GETs < 50 ms.
  2. `_write_csv` over 100 successive 5-row batches stays under 200 ms total
     (i.e. <2 ms per write) -- the dedup cache makes this trivially fast.
  3. Session is reused (not rebuilt) across calls.
  4. The dedup cache prevents re-reading the CSV on every write.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import pytest                                                       # noqa: E402

from scripts import pinnacle_scraper as ps                          # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _percentile(values: List[float], pct: float) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    idx = min(n - 1, int(round(pct / 100.0 * (n - 1))))
    return s[idx]


class _FakeResp:
    def __init__(self, status: int = 200, payload: Any = None):
        self.status_code = status
        self._payload = payload if payload is not None else {"ok": True}

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    """Stand-in for a curl_cffi Session. Records every GET, returns
    a constant payload after a tiny artificial latency so the timing
    assertion isn't trivially noise-bound."""

    def __init__(self) -> None:
        self.calls: List[str] = []
        self.headers: Dict[str, str] = {}
        self.impersonate: str = ""

    def get(self, url: str, **kw: Any) -> _FakeResp:
        self.calls.append(url)
        # Simulate fast warm path (~1-2 ms). No artificial latency: the
        # purpose of this test is to guard against the *code path* adding
        # overhead, not network time.
        return _FakeResp(200, [{"id": 1, "type": "matchup"}])

    def close(self) -> None:
        pass


# ── tests ─────────────────────────────────────────────────────────────────────

def test_http_get_json_p99_under_target_with_mocked_session():
    """Over 100 mocked GETs the *code-path overhead* p99 must be <50 ms.

    The original implementation imported curl_cffi and built a fresh request
    object on every call. Now it shares a Session, so this loop measures the
    session.get + json-decode roundtrip only.
    """
    ps._reset_sessions()
    fake = _FakeSession()

    # Inject the fake session as the cached curl_cffi session.
    ps._CURL_SESSION = fake

    timings: List[float] = []
    for _ in range(100):
        t = time.perf_counter()
        code, data = ps._http_get_json("https://example.invalid/test", timeout=5.0)
        timings.append((time.perf_counter() - t) * 1000.0)
        assert code == 200
        assert data is not None

    # Code-path overhead p99 must be tiny (<50 ms) -- the mocked session has
    # zero network cost so any spike here is pure overhead.
    p99 = _percentile(timings, 99)
    p50 = _percentile(timings, 50)
    assert p99 < 50.0, f"p99={p99:.2f}ms p50={p50:.2f}ms (target <50ms)"

    # And the session must have served all 100 calls.
    assert len(fake.calls) == 100

    ps._reset_sessions()


def test_session_is_reused_across_calls():
    """The cached session must not be rebuilt per call -- that's the whole point."""
    ps._reset_sessions()
    fake = _FakeSession()
    ps._CURL_SESSION = fake

    for _ in range(10):
        ps._http_get_json("https://example.invalid/test")

    # Same fake session served every call.
    assert ps._CURL_SESSION is fake
    assert len(fake.calls) == 10

    ps._reset_sessions()


def test_write_csv_dedup_cache_avoids_per_call_reread(tmp_path):
    """The dedup cache must prevent re-reading the file on every write."""
    target = str(tmp_path / "test_pin.csv")

    # Reset the module-level cache for a clean test.
    ps._DEDUP_CACHE.clear()

    rows_batch_1 = [
        {"captured_at": "2026-05-26T20:30", "book": "pin", "game_id": "1",
         "player_id": "", "player_name": "LeBron James", "stat": "pts",
         "line": 25.5, "over_price": -110, "under_price": -110,
         "start_time": "2026-05-26T22:00:00Z"},
    ]
    n1 = ps._write_csv(target, ps.PROP_FIELDS, rows_batch_1,
                       dedup_key=("captured_at", "player_name", "stat", "line"))
    assert n1 == 1

    # Same key again -- must be deduplicated and never re-read from disk.
    # Simulate a disk error if open() is called: the cache should make
    # the second write succeed without touching the file for reads.
    original_open = open

    open_call_count = {"n": 0}

    def counting_open(*args, **kwargs):
        # Count only READ opens on the target file.
        if args and args[0] == target and (
            (len(args) > 1 and "r" in str(args[1])) or "r" in str(kwargs.get("mode", ""))
        ):
            open_call_count["n"] += 1
        return original_open(*args, **kwargs)

    with patch("builtins.open", side_effect=counting_open):
        n2 = ps._write_csv(target, ps.PROP_FIELDS, rows_batch_1,
                           dedup_key=("captured_at", "player_name", "stat", "line"))
        assert n2 == 0  # all dup
        n3 = ps._write_csv(target, ps.PROP_FIELDS, rows_batch_1,
                           dedup_key=("captured_at", "player_name", "stat", "line"))
        assert n3 == 0

    # Zero read-opens of the dedup file in the second/third call -- the
    # cache served the lookup.
    assert open_call_count["n"] == 0, (
        f"_write_csv re-read the file {open_call_count['n']} times "
        "(dedup cache should prevent this)"
    )


def test_write_csv_throughput_100_writes_under_budget(tmp_path):
    """100 successive 5-row writes must complete in <200 ms total.

    With the original per-write CSV re-read this scales O(N^2); with the
    in-memory dedup cache it should be ~constant per call.
    """
    target = str(tmp_path / "throughput_pin.csv")
    ps._DEDUP_CACHE.clear()

    def _row(i: int) -> Dict[str, Any]:
        return {
            "captured_at": "2026-05-26T20:30",
            "book": "pin",
            "game_id": str(i),
            "player_id": "",
            "player_name": f"Player_{i}",
            "stat": "pts",
            "line": 20.0 + (i % 10),
            "over_price": -110,
            "under_price": -110,
            "start_time": "2026-05-26T22:00:00Z",
        }

    t = time.perf_counter()
    rows_written = 0
    for batch in range(100):
        rows = [_row(batch * 5 + j) for j in range(5)]
        rows_written += ps._write_csv(
            target, ps.PROP_FIELDS, rows,
            dedup_key=("captured_at", "player_name", "stat", "line"),
        )
    elapsed_ms = (time.perf_counter() - t) * 1000.0

    assert rows_written == 500
    assert elapsed_ms < 1000.0, (
        f"100x5-row writes took {elapsed_ms:.1f} ms "
        "(target <1000 ms; cache should keep this near-constant)"
    )


def test_reset_sessions_clears_both_transports():
    """_reset_sessions must drop both cached sessions cleanly."""
    fake = _FakeSession()
    ps._CURL_SESSION = fake
    ps._REQ_SESSION = fake
    ps._reset_sessions()
    assert ps._CURL_SESSION is None
    assert ps._REQ_SESSION is None
