from datetime import datetime, timezone

from scripts.platformkit.ingame import mlb_book_capture as capture


class StubClient:
    def __init__(self):
        self.n_429 = 0
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return {"orderbook_fp": {"yes_dollars": [["0.30", "2"], ["0.40", "3"]],
                                 "no_dollars": [["0.40", "4"], ["0.50", "5"]]}}


def test_capture_writes_complete_ladder_and_paper_cell(tmp_path):
    client = StubClient()

    def live_games(_client, _date, _state):
        return [{"game_pk": "123", "ticker": "KXMLBGAME-26SEP011200LADSF",
                 "game_state": {"ts": "2026-09-01T12:00:00.000000Z", "inning": 4}}]

    out = capture.capture_once(client=client, now=datetime(2026, 9, 1, tzinfo=timezone.utc),
                                live_games_fn=live_games, output=tmp_path / "books.jsonl")
    row = out["rows"][0]
    assert row["yes_ladder"] == [["0.30", "2"], ["0.40", "3"]]
    assert row["no_ladder"] == [["0.40", "4"], ["0.50", "5"]]
    assert row["top_of_book_depth"] == 8.0
    assert row["src_ts"] == "2026-09-01T12:00:00.000000Z"
    assert out["cell_table"] == [{"game_pk": "123", "inplay_snapshots": 1,
                                   "median_top_of_book_depth": 8.0,
                                   "pre_registered_unit": 1.0, "depth_threshold": 5.0,
                                   "cell": "NOT_YET"}]


def test_local_archive_is_scratch_and_429_doubles_cadence(tmp_path):
    client = StubClient()
    def rate_limited(_client, _date, _state):
        client.n_429 += 1
        return []

    out = capture.capture_once(client=client, now=datetime(2026, 9, 1, tzinfo=timezone.utc),
                                live_games_fn=rate_limited, output=tmp_path / "books.jsonl")
    assert out["n_429"] == 1
    assert out["cadence_sec"] == 10.0
    assert capture.archive_path(datetime(2026, 9, 1, tzinfo=timezone.utc), {}) == capture.SCRATCH_ARCHIVE / "2026-09-01.jsonl"
    assert capture.live_archive_enabled({"CV_CAPTURE_POD": "1", "CV_MLB_BOOK_ARCHIVE_LIVE": "1"})


# ---------------------------------------------------------------------------
# S1e-CADENCE (2026-09-01): run_pod_capture deadline pacing + the additive
# record_type='cadence' heartbeat row (same archive file, no second metrics file).
# ---------------------------------------------------------------------------
import json


class _FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        assert s >= 0.0, "a deadline-paced loop never sleeps a negative residual"
        self.t += s
        self.slept.append(round(s, 6))


def _paced_loop(monkeypatch, tmp_path, *, fetch_cost, n_ticks, n_live=2):
    """Run run_pod_capture for n_ticks with a fake clock and a fake pass of known cost."""
    monkeypatch.setenv("CV_CAPTURE_POD", "1")
    monkeypatch.setenv("CV_MLB_BOOK_ARCHIVE_LIVE", "1")
    clock = _FakeClock()
    out = tmp_path / "books.jsonl"
    calls = {"n": 0}

    def fake_capture_once(*, client, state, output=None, **_):
        calls["n"] += 1
        clock.t += fetch_cost
        state["n_live_games"] = n_live
        state.setdefault("cadence_sec", capture.TARGET_CADENCE_SEC)
        return {"path": str(output), "rows": [], "cell_table": [],
                "cadence_sec": state["cadence_sec"], "n_429": 0}

    monkeypatch.setattr(capture, "capture_once", fake_capture_once)
    capture.run_pod_capture(stop=lambda: calls["n"] >= n_ticks,
                            sleep=clock.sleep, clock=clock, output=out)
    rows = [json.loads(line) for line in out.read_text(encoding="ascii").splitlines()]
    return clock, rows


def test_run_pod_capture_holds_target_cadence_when_pass_is_fast(monkeypatch, tmp_path):
    clock, rows = _paced_loop(monkeypatch, tmp_path, fetch_cost=1.0, n_ticks=5)
    assert [r["record_type"] for r in rows] == ["cadence"] * 5
    achieved = [r["achieved_cadence_sec"] for r in rows]
    assert achieved[0] is None, "first tick has no predecessor -- honest None, not 0"
    assert achieved[1:] == [5.0, 5.0, 5.0, 5.0], "period == target, not target + pass"
    assert rows[0]["tick_latency_sec"] == 1.0 and rows[0]["target_cadence_sec"] == 5.0
    assert clock.slept == [4.0] * 5, "sleeps only the residual (5 - 1), never a flat 5"


def test_run_pod_capture_degrades_without_pileup_when_pass_exceeds_cadence(monkeypatch, tmp_path):
    clock, rows = _paced_loop(monkeypatch, tmp_path, fetch_cost=12.0, n_ticks=4)
    assert clock.slept == [0.0] * 4, "an overrunning pass sleeps zero, never negative"
    assert [r["achieved_cadence_sec"] for r in rows][1:] == [12.0, 12.0, 12.0], \
        "period degrades to the pass duration (12s), not pass + cadence (17s)"
    assert clock.t == 48.0, "no drift debt accumulates across overrunning ticks"


def test_run_pod_capture_idles_slowly_and_metrics_row_survives_truncation(monkeypatch, tmp_path):
    monkeypatch.setenv("CV_CAPTURE_POD", "1")
    monkeypatch.setenv("CV_MLB_BOOK_ARCHIVE_LIVE", "1")
    clock, rows = _paced_loop(monkeypatch, tmp_path, fetch_cost=1.0, n_ticks=3, n_live=0)
    assert rows[0]["target_cadence_sec"] == capture.IDLE_CHECK_SEC
    assert clock.slept == [29.0] * 3, "idle check keeps its 30s period, residual-paced"

    # The archive is append-only line-JSON: a crash mid-append tears ONLY the last line.
    out = tmp_path / "books.jsonl"
    lines_on_disk = out.read_text(encoding="ascii").splitlines()
    torn = chr(10).join(lines_on_disk[:-1]) + chr(10) + lines_on_disk[-1][:20]
    out.write_text(torn, encoding="ascii")

    def tolerant_read():
        kept = []
        for line in out.read_text(encoding="ascii").splitlines():
            try:
                kept.append(json.loads(line))
            except ValueError:
                continue
        return kept

    assert tolerant_read() == rows[:-1], "torn tail dropped; earlier rows byte-identical"
    assert tolerant_read() == tolerant_read(), "re-reading the metrics rows is idempotent"
