import subprocess

from scripts.platformkit import ops_healthcheck as ops

RAW_FIXTURE = """DAEMON_ALIVE=1
SYNTH_VERDICT_COMPLETE=0
SELF_PID=555
PARENT_PID=554
===DISK_DF===
Filesystem     1024-blocks      Used Available Capacity Mounted on
/dev/sda1      1000000000 600000000 400000000      61% /workspace
===END_DISK_DF===
===GPU_RAW===
23 %
===END_GPU_RAW===
===SYNTH_TAIL===
[10:00:00] step 100 loss=0.5231
[10:00:05] step 200 loss=0.4899
===END_SYNTH_TAIL===
===PROC_DUMP===
554\tbash -c set -u ... mlb_book_capture ...
555\tbash -c set -u ... mlb_book_capture ...
9001\tpython3 -m scripts.platformkit.ingame.mlb_book_capture --pod
9002\tpython3 something_unrelated.py
===END_PROC_DUMP===
"""


def test_extract_block_and_parse_kv():
    assert ops.parse_kv(RAW_FIXTURE) == {
        "DAEMON_ALIVE": "1", "SYNTH_VERDICT_COMPLETE": "0",
        "SELF_PID": "555", "PARENT_PID": "554",
    }
    assert "23 %" in ops.extract_block(RAW_FIXTURE, "GPU_RAW")
    assert ops.extract_block(RAW_FIXTURE, "NOPE") == ""


def test_parse_disk_free_gb():
    block = ops.extract_block(RAW_FIXTURE, "DISK_DF")
    assert ops.parse_disk_free_gb(block) == round(400000000 / 1024 / 1024, 3)


def test_parse_disk_free_gb_malformed():
    assert ops.parse_disk_free_gb("") is None
    assert ops.parse_disk_free_gb("header only\n") is None


def test_parse_gpu_util():
    assert ops.parse_gpu_util("23 %\n") == 23
    assert ops.parse_gpu_util("0 %\n") == 0
    assert ops.parse_gpu_util("") is None
    assert ops.parse_gpu_util("   \n") is None


def test_parse_synthcal_tail_takes_last_line():
    tail = ops.extract_block(RAW_FIXTURE, "SYNTH_TAIL")
    assert ops.parse_synthcal_tail(tail) == {"step": 200, "loss": 0.4899}


def test_parse_synthcal_tail_no_match():
    assert ops.parse_synthcal_tail("no useful lines here\n") == {"step": None, "loss": None}


def test_capture_running_excludes_self_and_parent():
    dump = ops.extract_block(RAW_FIXTURE, "PROC_DUMP")
    # self (555) and parent (554) both mention the pattern in their own
    # cmdline (as the ssh-invoked shell carrying the whole script text
    # would) -- excluding them is what keeps this from self-matching.
    assert ops.capture_running(dump, self_pid="555", parent_pid="554") is True  # pid 9001 is real
    only_self_and_parent = "554\tmlb_book_capture\n555\tmlb_book_capture\n"
    assert ops.capture_running(only_self_and_parent, self_pid="555", parent_pid="554") is False


def test_capture_running_no_match():
    assert ops.capture_running("1\tunrelated\n2\tother\n", "9", "8") is False


def test_build_report_end_to_end():
    report = ops.build_report(RAW_FIXTURE)
    assert report["reachable"] is True
    assert report["daemon_alive"] is True
    assert report["synthcal"] == {"step": 200, "loss": 0.4899, "complete": False}
    assert report["capture_running"] is True
    assert report["gpu_util_pct"] == 23
    assert report["disk_free_gb"] == round(400000000 / 1024 / 1024, 3)


def test_run_pod_check_fails_closed_on_nonzero_exit(monkeypatch):
    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, returncode=255, stdout="", stderr="Connection refused")
    monkeypatch.setattr(ops.subprocess, "run", fake_run)
    result = ops.run_pod_check()
    assert result == {"reachable": False, "error": "Connection refused"}


def test_run_pod_check_fails_closed_on_timeout(monkeypatch):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=25)
    monkeypatch.setattr(ops.subprocess, "run", fake_run)
    result = ops.run_pod_check()
    assert result["reachable"] is False
    assert "error" in result


def test_run_pod_check_reachable(monkeypatch):
    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, returncode=0, stdout=RAW_FIXTURE, stderr="")
    monkeypatch.setattr(ops.subprocess, "run", fake_run)
    result = ops.run_pod_check()
    assert result["reachable"] is True
    assert result["daemon_alive"] is True


# ---- MODE local ----

def test_collect_lane_status_picks_newest_and_parses_exit(tmp_path):
    (tmp_path / "laneA.log").write_text("line one\nline two\nEXIT=0\n")
    older = tmp_path / "laneA_old.log"
    older.write_text("stale run\n")
    import os
    os.utime(older, (1, 1))  # force it older than laneA.log

    (tmp_path / "laneB.out").write_text("running fine\nlast bit here\n")
    (tmp_path / "laneB.exit").write_text("7\n")

    rows = ops.collect_lane_status(tmp_path)
    by_lane = {r["lane"]: r for r in rows}
    assert by_lane["laneA"]["exit"] == 0
    assert by_lane["laneA"]["last_line"] == "EXIT=0"
    assert by_lane["laneB"]["exit"] == 7
    assert by_lane["laneB"]["last_line"] == "last bit here"


def test_collect_lane_status_groups_by_subdir(tmp_path):
    sub = tmp_path / "laneC"
    sub.mkdir()
    (sub / "run1.log").write_text("first\n")
    rows = ops.collect_lane_status(tmp_path)
    assert any(r["lane"] == "laneC" for r in rows)


def test_collect_lane_status_empty_dir(tmp_path):
    assert ops.collect_lane_status(tmp_path) == []


def test_parse_exit_code_sibling_wins_over_inline():
    text = "EXIT=1\n"
    assert ops.parse_exit_code(text, sibling_exit="9") == 9
    assert ops.parse_exit_code(text, sibling_exit=None) == 1
    assert ops.parse_exit_code("no exit marker\n", None) is None


def test_last_nonempty_line_trims_trailing_blank():
    assert ops.last_nonempty_line("a\nb\n\n") == "b"
    assert ops.last_nonempty_line("") == ""


def test_render_table_empty_and_nonempty():
    assert ops.render_table([]) == "(no task output files found)"
    out = ops.render_table([{"lane": "x", "exit": None, "last_line": "hi"}])
    assert "x" in out and "exit=?" in out and "hi" in out
