"""Per-file test for ci_state.build_durable_state (W4 cadence step B). NO full pytest."""
from __future__ import annotations

import json

from scripts.platformkit.progress import ci_state
from scripts.platformkit.autonomy import schedule_policy


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="ascii")


def _write_backlog(path, cands):
    path.write_text(json.dumps({"candidates": cands}), encoding="ascii")


def test_shape_parity_with_schedule_policy(tmp_path):
    """Output keys must be EXACTLY what SchedulePolicy._task_for_sport consumes."""
    lp = tmp_path / "improve_ledger.jsonl"
    bp = tmp_path / "backlog.json"
    _write_jsonl(lp, [{"sport": "nba", "verdict": "INSUFFICIENT_DATA", "n_settled": 0}])
    _write_backlog(bp, [{"category": "UNTESTED_DATA", "sport": "mlb"}])
    state = ci_state.build_durable_state(
        1_700_000_000.0, ledger_path=lp, backlog_path=bp, corpora_dir=tmp_path)
    for sp, st in state.items():
        assert set(st.keys()) == {"settled_pending", "ingame_pending", "corpus_age_days"}
    # The policy must accept the state and never raise on a forbidden kind.
    dec = schedule_policy.SchedulePolicy().decide(state)
    assert dec.status in (schedule_policy.TASK, schedule_policy.NO_CANDIDATE,
                          schedule_policy.IDLE_OFFSEASON, schedule_policy.IDLE_ALL)
    if dec.task is not None:
        assert dec.task.kind in schedule_policy.MEASUREMENT_KINDS


def test_untested_backlog_sets_settled_pending(tmp_path):
    lp = tmp_path / "l.jsonl"
    bp = tmp_path / "b.json"
    lp.write_text("", encoding="ascii")
    _write_backlog(bp, [{"category": "UNTESTED_DATA", "sport": "nba"},
                        {"category": "LOC_VIOLATION", "sport": "platform"}])
    state = ci_state.build_durable_state(
        1_700_000_000.0, ledger_path=lp, backlog_path=bp, corpora_dir=tmp_path)
    assert state["nba"]["settled_pending"] >= 1
    # LOC_VIOLATION is code-hygiene, not data coverage -> mlb stays 0.
    assert state["mlb"]["settled_pending"] == 0


def test_missing_inputs_degrade_to_no_work(tmp_path):
    """Missing ledger/backlog/corpora -> all-zero, never raises."""
    state = ci_state.build_durable_state(
        1_700_000_000.0,
        ledger_path=tmp_path / "absent.jsonl",
        backlog_path=tmp_path / "absent.json",
        corpora_dir=tmp_path / "absent_dir")
    for st in state.values():
        assert st["settled_pending"] == 0
        assert st["ingame_pending"] == 0
        assert st["corpus_age_days"] == 0.0


def test_no_dollar_field(tmp_path):
    state = ci_state.build_durable_state(corpora_dir=tmp_path,
                                         ledger_path=tmp_path / "x",
                                         backlog_path=tmp_path / "y")
    blob = json.dumps(state).lower()
    for tok in ("$", "pnl", "roi", "bankroll", "profit", "usd"):
        assert tok not in blob  # state has no disclaimer note -> a clean check


if __name__ == "__main__":
    import sys
    import tempfile
    import pathlib
    for fn in (test_shape_parity_with_schedule_policy,
               test_untested_backlog_sets_settled_pending,
               test_missing_inputs_degrade_to_no_work, test_no_dollar_field):
        with tempfile.TemporaryDirectory() as d:
            fn(pathlib.Path(d))
        print("ok:", fn.__name__)
    sys.exit(0)
