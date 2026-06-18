"""Per-file test for scripts.platformkit.prop_loop (network-free, all seams stubbed).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_loop.py -q
"""
from __future__ import annotations

from scripts.platformkit.prop_loop import run_forever, run_tick


class _Spy:
    """Records call counts so we can assert each stage ran exactly once per tick."""

    def __init__(self):
        self.n_ingest = 0
        self.n_writer = 0
        self.n_board = 0
        self.n_record = 0
        self.n_grade = 0
        self.n_summary = 0

    def ingester(self, dates, leagues=("fifa.world",)):
        self.n_ingest += 1
        return "parquet"

    def writer(self, sports):
        self.n_writer += 1
        return {s: "path" for s in sports}

    def board_builder(self, sport):
        self.n_board += 1
        return {"sport": sport, "edges": []}

    def recorder(self, board, only_reliable=True, ledger_path=None):
        self.n_record += 1
        return {"recorded": 2, "skipped_existing": 0, "status": "ok"}

    def grader(self, ledger_path=None):
        self.n_grade += 1
        return {"graded": 1, "status": "ok"}

    def summarizer(self, ledger_path=None):
        self.n_summary += 1
        return {"overall": {"n": 3, "hit_rate": 0.66, "paper_roi": 0.1,
                            "mean_model_p_over": 0.58},
                "by_stat": {"Shots": {"n": 3, "hit_rate": 0.66,
                                      "paper_roi": 0.1, "mean_model_p_over": 0.58}},
                "note": "TODO CLV", "status": "ok"}


def test_run_tick_assembles_and_calls_each_stage_once(tmp_path):
    spy = _Spy()
    out = run_tick(
        sports=("soccer_intl",), ingest=True, ingester=spy.ingester,
        writer=spy.writer, board_builder=spy.board_builder, recorder=spy.recorder,
        grader=spy.grader, summarizer=spy.summarizer,
        ledger_path=tmp_path / "led.jsonl",
    )
    assert out["recorded"] == 2
    assert out["graded"] == 1
    assert out["summary"]["overall"]["n"] == 3
    assert out["sources"]["ingest"] == "ok"
    assert out["sources"]["record:soccer_intl"] == "ok"
    assert spy.n_ingest == 1 and spy.n_writer == 1 and spy.n_board == 1
    assert spy.n_record == 1 and spy.n_grade == 1 and spy.n_summary == 1


def test_run_tick_ingest_off_skips_ingest(tmp_path):
    spy = _Spy()
    out = run_tick(
        ingest=False, ingester=spy.ingester, writer=spy.writer,
        board_builder=spy.board_builder, recorder=spy.recorder,
        grader=spy.grader, summarizer=spy.summarizer,
        ledger_path=tmp_path / "led.jsonl",
    )
    assert spy.n_ingest == 0
    assert out["sources"]["ingest"] == "skipped"


def test_run_tick_catches_a_raising_stage(tmp_path):
    spy = _Spy()

    def boom(*a, **k):
        raise RuntimeError("feed down")

    out = run_tick(
        sports=("soccer_intl",), ingest=True, ingester=boom, writer=spy.writer,
        board_builder=spy.board_builder, recorder=spy.recorder,
        grader=spy.grader, summarizer=spy.summarizer,
        ledger_path=tmp_path / "led.jsonl",
    )
    # The raising ingest stage is caught; the tick still returns + later stages run.
    assert out["sources"]["ingest"].startswith("error")
    assert out["recorded"] == 2
    assert out["graded"] == 1
    assert spy.n_record == 1 and spy.n_summary == 1


def test_run_tick_never_raises_on_all_stages_failing(tmp_path):
    def boom(*a, **k):
        raise RuntimeError("everything is down")

    out = run_tick(
        ingest=True, ingester=boom, writer=boom, board_builder=boom,
        recorder=boom, grader=boom, summarizer=boom,
        ledger_path=tmp_path / "led.jsonl",
    )
    assert out["recorded"] == 0
    assert out["graded"] == 0
    assert out["summary"] is None
    assert out["sources"]["ingest"].startswith("error")


def test_run_forever_runs_exactly_max_ticks(tmp_path):
    spy = _Spy()
    slept = []
    ticks = run_forever(
        interval_s=900, sleep=lambda s: slept.append(s), max_ticks=2,
        sports=("soccer_intl",), ingest=False, ingester=spy.ingester,
        writer=spy.writer, board_builder=spy.board_builder, recorder=spy.recorder,
        grader=spy.grader, summarizer=spy.summarizer,
        ledger_path=tmp_path / "led.jsonl",
    )
    assert len(ticks) == 2
    # Sleeps BETWEEN ticks only -> exactly 1 sleep for 2 ticks.
    assert len(slept) == 1
    assert spy.n_record == 2
