"""Tests for scripts/measure_live_api_latency.py -- cycle 91e (loop 5).

Pure-offline: no nba_api or network calls. Fakes inject deterministic
clock + payload sequences so the latency math + CSV schema can be pinned
exactly.
"""
from __future__ import annotations

import csv
import math
import os
import sys
from datetime import datetime, timezone

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.measure_live_api_latency as mal  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _virtual_clock(start: datetime):
    """Return (now_fn, sleep_fn) that share a mutable cell."""
    cell = [start]

    def now() -> datetime:
        return cell[0]

    def sleep(s: float) -> None:
        cell[0] = datetime.fromtimestamp(cell[0].timestamp() + float(s),
                                          tz=timezone.utc)
    return now, sleep, cell


def _pbp(actions):
    return {"game": {"actions": list(actions)}}


def _bs(status=2, home=0, away=0):
    return {"game": {
        "gameStatus": status,
        "homeTeam": {"score": home},
        "awayTeam": {"score": away},
    }}


# ---------------------------------------------------------------------------
# 1. Latency math on a synthetic event sequence
# ---------------------------------------------------------------------------

def test_latency_calc_on_synthetic_event_sequence(tmp_path):
    """Three events with known action timestamps; first_seen one tick
    later -> latency = action_to_poll delta + bs_fetch lag."""
    start = datetime(2026, 5, 24, 19, 0, 0, tzinfo=timezone.utc)
    now, sleep, _ = _virtual_clock(start)

    # Events ahead of poll time by 0s/5s/10s respectively. The bs fetch
    # happens immediately after pbp (same now() value because sleep_fn
    # only advances on explicit calls).
    pbp_seq = [
        _pbp([{"actionNumber": 1, "timeActual": "2026-05-24T18:59:55Z"}]),
        _pbp([{"actionNumber": 1, "timeActual": "2026-05-24T18:59:55Z"},
              {"actionNumber": 2, "timeActual": "2026-05-24T19:00:10Z"}]),
        _pbp([{"actionNumber": 1, "timeActual": "2026-05-24T18:59:55Z"},
              {"actionNumber": 2, "timeActual": "2026-05-24T19:00:10Z"},
              {"actionNumber": 3, "timeActual": "2026-05-24T19:00:20Z"}]),
    ]
    bs_seq = [_bs(), _bs(home=2), _bs(home=2, away=3)]
    idx = [0]

    def _pbp_fn(_gid):
        return pbp_seq[min(idx[0], len(pbp_seq) - 1)]

    def _bs_fn(_gid):
        i = min(idx[0], len(bs_seq) - 1)
        idx[0] += 1
        return bs_seq[i]

    path, rows = mal.run_latency_capture(
        "0022400123",
        duration_min=10,
        poll_seconds=15.0,
        fetch_pbp=_pbp_fn,
        fetch_bs=_bs_fn,
        sleep_fn=sleep,
        now_fn=now,
        latency_dir=str(tmp_path),
        max_polls=4,
    )

    # 3 unique events captured (eventIds 1,2,3 each once).
    assert len(rows) == 3, rows
    ids = [r["eventId"] for r in rows]
    assert ids == [1, 2, 3]

    # Latency for event 1: first_seen = start (19:00:00) - action 18:59:55 = +5s.
    assert float(rows[0]["latency_seconds"]) == pytest.approx(5.0, abs=0.1)
    # Latency for event 2: first_seen = start+15s (19:00:15) - action 19:00:10 = +5s.
    assert float(rows[1]["latency_seconds"]) == pytest.approx(5.0, abs=0.1)
    # Latency for event 3: first_seen = start+30s (19:00:30) - action 19:00:20 = +10s.
    assert float(rows[2]["latency_seconds"]) == pytest.approx(10.0, abs=0.1)

    assert os.path.exists(path)


# ---------------------------------------------------------------------------
# 2. CSV written with expected schema
# ---------------------------------------------------------------------------

def test_csv_written_with_expected_schema(tmp_path):
    """Header row matches the canonical 5-column schema; every row has all keys."""
    start = datetime(2026, 5, 24, 19, 0, 0, tzinfo=timezone.utc)
    now, sleep, _ = _virtual_clock(start)

    pbp_payload = _pbp([
        {"actionNumber": 1, "timeActual": "2026-05-24T18:59:55Z"},
        {"actionNumber": 2, "timeActual": "2026-05-24T18:59:58Z"},
    ])

    def _pbp_fn(_gid):
        return pbp_payload

    def _bs_fn(_gid):
        return _bs(home=4)

    path, rows = mal.run_latency_capture(
        "0022400999",
        duration_min=5,
        poll_seconds=15.0,
        fetch_pbp=_pbp_fn,
        fetch_bs=_bs_fn,
        sleep_fn=sleep,
        now_fn=now,
        latency_dir=str(tmp_path),
        max_polls=1,
    )

    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == [
            "poll_iso", "eventId", "action_timestamp",
            "boxscore_first_seen", "latency_seconds",
        ]
        loaded = list(reader)
    assert len(loaded) == len(rows) == 2
    for row in loaded:
        assert set(row.keys()) == set([
            "poll_iso", "eventId", "action_timestamp",
            "boxscore_first_seen", "latency_seconds",
        ])
        assert row["eventId"] in ("1", "2")


# ---------------------------------------------------------------------------
# 3. Missing action timestamp -> row included with latency=NaN
# ---------------------------------------------------------------------------

def test_missing_event_timestamp_yields_nan_latency(tmp_path):
    """Event with null/missing timeActual is still captured; latency field empty."""
    start = datetime(2026, 5, 24, 19, 0, 0, tzinfo=timezone.utc)
    now, sleep, _ = _virtual_clock(start)

    pbp_payload = _pbp([
        {"actionNumber": 1, "timeActual": "2026-05-24T18:59:55Z"},
        {"actionNumber": 2, "timeActual": None},
        {"actionNumber": 3},  # totally absent
    ])

    def _pbp_fn(_gid):
        return pbp_payload

    def _bs_fn(_gid):
        return _bs(home=6)

    path, rows = mal.run_latency_capture(
        "0022400777",
        duration_min=5,
        poll_seconds=15.0,
        fetch_pbp=_pbp_fn,
        fetch_bs=_bs_fn,
        sleep_fn=sleep,
        now_fn=now,
        latency_dir=str(tmp_path),
        max_polls=1,
    )

    assert len(rows) == 3
    # event 1 has a finite latency
    assert float(rows[0]["latency_seconds"]) == pytest.approx(5.0, abs=0.1)
    # events 2 and 3 -> empty latency string (NaN sentinel)
    assert rows[1]["latency_seconds"] == ""
    assert rows[2]["latency_seconds"] == ""

    # And the CSV round-trips that empty cell.
    with open(path, encoding="utf-8") as fh:
        loaded = list(csv.DictReader(fh))
    assert loaded[1]["latency_seconds"] == ""
    assert loaded[2]["latency_seconds"] == ""


# ---------------------------------------------------------------------------
# 4. Summary stats on N=10 synthetic latencies (median + p90)
# ---------------------------------------------------------------------------

def test_summary_stats_median_and_p90_on_10_events():
    """Inject 10 synthetic latencies 1..10; median ~= 5.5, p90 ~= 9.1."""
    rows = [{"latency_seconds": str(float(i))} for i in range(1, 11)]
    s = mal.summarize_latencies(rows)
    assert s["n_total"] == 10
    assert s["n_finite"] == 10
    # Linear interpolation between rank 4 and 5 -> 5.5.
    assert s["median"] == pytest.approx(5.5, abs=1e-6)
    # 10 values, p90 -> rank 8.1 -> 9.1.
    assert s["p90"] == pytest.approx(9.1, abs=1e-6)
    assert s["mean"] == pytest.approx(5.5, abs=1e-6)


def test_summary_stats_handles_nan_and_empty():
    """NaN / empty / non-numeric latency cells are excluded from the stats."""
    rows = [
        {"latency_seconds": "3.0"},
        {"latency_seconds": ""},
        {"latency_seconds": "nan"},
        {"latency_seconds": "5.0"},
    ]
    s = mal.summarize_latencies(rows)
    assert s["n_total"] == 4
    assert s["n_finite"] == 2  # only 3.0 and 5.0 are finite
    assert s["median"] == pytest.approx(4.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Bonus: latency_calc helper directly + parser
# ---------------------------------------------------------------------------

def test_compute_latency_seconds_pure_helper():
    """The pure latency helper: simple delta between two ISO timestamps."""
    out = mal.compute_latency_seconds(
        "2026-05-24T19:00:00Z", "2026-05-24T19:00:08+00:00")
    assert out == pytest.approx(8.0, abs=1e-6)
    # Missing inputs -> NaN.
    assert math.isnan(mal.compute_latency_seconds(None, "2026-05-24T19:00:08Z"))
    assert math.isnan(mal.compute_latency_seconds("2026-05-24T19:00:00Z", None))


def test_extract_pbp_events_parses_action_list():
    """The PBP extractor returns (eventId, timestamp) tuples sorted as in payload."""
    payload = _pbp([
        {"actionNumber": 1, "timeActual": "2026-05-24T19:00:00Z"},
        {"actionNumber": 2, "timeActual": "2026-05-24T19:00:05Z"},
        {"actionNumber": "junk"},
    ])
    out = mal.extract_pbp_events(payload)
    assert out == [
        (1, "2026-05-24T19:00:00Z"),
        (2, "2026-05-24T19:00:05Z"),
    ]
    assert mal.extract_pbp_events({}) == []
