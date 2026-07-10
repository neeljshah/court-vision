"""Per-file test for scripts.platformkit.autoloop.log_reaper_job.

Never touches real logs/ -- every case uses tmp_path fixtures only.

Acceptance criteria:
1. File under cap: left untouched, not archived.
2. File over cap: copy_fn + truncate_fn both called, ops row records it.
3. copy_fn/truncate_fn raising OSError for one file: isolated, doesn't
   block a second over-cap file in the same scan.
4. watermarks param accepted positionally and ignored (call-shape parity).
5. Live-append semantics: a real os.truncate on a file still open for
   append in this process succeeds and a subsequent write lands at the
   new EOF (regression guard for the Windows measurement this job relies on).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_log_reaper_job.py -q
"""
from __future__ import annotations

import json
import os

from scripts.platformkit.autoloop import log_reaper_job as LR


def _mk(tmp_path, name, size_bytes):
    p = tmp_path / name
    p.write_bytes(b"x" * size_bytes)
    return p


def test_under_cap_left_alone(tmp_path):
    _mk(tmp_path, "small.out", 100)
    ops = tmp_path / "ops.json"
    calls = []
    out = LR.run_log_reaper(
        logs_dir=tmp_path, cap_bytes=1000, ops_path=ops,
        copy_fn=lambda s, d: calls.append(("copy", s, d)),
        truncate_fn=lambda p, n: calls.append(("truncate", p, n)),
    )
    assert out["checked"] == 1
    assert out["archived"] == []
    assert calls == []
    assert (tmp_path / "small.out").stat().st_size == 100


def test_over_cap_archives_and_truncates(tmp_path):
    _mk(tmp_path, "big.out", 2000)
    ops = tmp_path / "ops.json"
    calls = []
    out = LR.run_log_reaper(
        logs_dir=tmp_path, cap_bytes=1000, ops_path=ops,
        copy_fn=lambda s, d: calls.append(("copy", s, d)),
        truncate_fn=lambda p, n: calls.append(("truncate", p, n)),
        now_fn=lambda: "20260710T000000Z",
    )
    assert len(out["archived"]) == 1
    assert out["archived"][0]["name"] == "big.out"
    assert out["archived"][0]["size_before"] == 2000
    assert calls[0][0] == "copy"
    assert calls[1] == ("truncate", str(tmp_path / "big.out"), 0)
    row = json.loads(ops.read_text(encoding="utf-8"))
    assert row["archived"][0]["name"] == "big.out"


def test_one_failure_does_not_block_the_rest(tmp_path):
    _mk(tmp_path, "bad.out", 2000)
    _mk(tmp_path, "good.err", 2000)
    ops = tmp_path / "ops.json"

    def copy_fn(src, dst):
        if "bad" in src:
            raise OSError("locked")

    calls = []
    out = LR.run_log_reaper(
        logs_dir=tmp_path, cap_bytes=1000, ops_path=ops,
        copy_fn=copy_fn,
        truncate_fn=lambda p, n: calls.append(p),
    )
    assert len(out["failed"]) == 1
    assert out["failed"][0]["name"] == "bad.out"
    assert len(out["archived"]) == 1
    assert out["archived"][0]["name"] == "good.err"


def test_watermarks_accepted_and_ignored(tmp_path):
    ops = tmp_path / "ops.json"
    watermarks = {"unrelated": "untouched"}
    out = LR.run_log_reaper(watermarks, logs_dir=tmp_path, ops_path=ops)
    assert out["status"] == "ok"
    assert watermarks == {"unrelated": "untouched"}


def test_real_truncate_on_open_append_handle_lands_at_new_eof(tmp_path):
    """Regression guard for the measured Windows sharing behavior this
    job's design depends on: truncating a file this process still holds
    open in append mode must succeed, and the next write must land at 0,
    not raise and not corrupt."""
    p = tmp_path / "live.out"
    fh = open(p, "a", encoding="utf-8")
    try:
        fh.write("before\n")
        fh.flush()
        os.truncate(str(p), 0)
        fh.write("after\n")
        fh.flush()
    finally:
        fh.close()
    assert p.read_text(encoding="utf-8") == "after\n"
