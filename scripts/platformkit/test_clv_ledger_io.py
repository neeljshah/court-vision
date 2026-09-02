"""test_clv_ledger_io.py -- hermetic race test for clv_ledger_io's lock-guarded
append primitives (append_row / append_row_if_new / ledger_lock).

Spawns two REAL OS subprocesses that race writes against the SAME temp ledger
path -- the process-level race the lock is meant to close, not just a
same-process threading race.

Acceptance criteria (seed D4 / LEAD 9 -- clv_ledger concurrent-write race):
  1. Two subprocesses appending distinct rows concurrently -> all rows land,
     none dropped or corrupted by interleaved byte-level writes.
  2. Two subprocesses racing to settle the SAME bet_id via append_row_if_new
     -> exactly ONE settled row lands (the double-settled-row race).

Run with:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_clv_ledger_io.py -q
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

from scripts.platformkit import clv_ledger_io as _CLV
from scripts.platformkit.clv_ledger_io import (
    LedgerLockError, append_row, ledger_lock, load_rows,
)

_ROOT = Path(__file__).resolve().parents[2]

# Worker: appends N distinct "open" rows via the lock-guarded raw primitive --
# exercises the byte-level interleave race across two OS processes.
_APPEND_WORKER = (
    "import sys\n"
    "sys.path.insert(0, " + repr(str(_ROOT)) + ")\n"
    "from pathlib import Path\n"
    "from scripts.platformkit.clv_ledger_io import append_row\n"
    "path = Path(sys.argv[1])\n"
    "n = int(sys.argv[2])\n"
    "prefix = sys.argv[3]\n"
    "for i in range(n):\n"
    "    append_row({'bet_id': '%s-%d' % (prefix, i), 'status': 'open'}, path=path)\n"
)

# Worker: both invocations race to settle the SAME bet_id via the atomic
# check-then-append primitive -- exercises the double-settled-row race.
_SETTLE_WORKER = (
    "import sys\n"
    "sys.path.insert(0, " + repr(str(_ROOT)) + ")\n"
    "from pathlib import Path\n"
    "from scripts.platformkit.clv_ledger_io import append_row_if_new\n"
    "path = Path(sys.argv[1])\n"
    "worker = sys.argv[2]\n"
    "def _key(r):\n"
    "    return '%s|%s' % (r.get('bet_id'), r.get('status'))\n"
    "append_row_if_new(\n"
    "    {'bet_id': 'shared-bet', 'status': 'settled', 'worker': worker},\n"
    "    _key, path=path,\n"
    ")\n"
)


def _run_workers(script: str, args_list: List[List[str]]) -> None:
    """Write *script* to a temp file, launch one subprocess per args tuple,
    wait for all to exit 0."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8"
    ) as sf:
        sf.write(script)
        script_path = sf.name
    try:
        procs = [
            subprocess.Popen([sys.executable, script_path, *args])
            for args in args_list
        ]
        for p in procs:
            rc = p.wait(timeout=60)
            assert rc == 0, "worker exited %d" % rc
    finally:
        Path(script_path).unlink(missing_ok=True)


def test_concurrent_append_no_lost_rows():
    """Two subprocesses each append 25 distinct rows concurrently -> all 50
    land; none dropped or corrupted by interleaved writes."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "race_open.jsonl"
        _run_workers(
            _APPEND_WORKER,
            [[str(target), "25", "a"], [str(target), "25", "b"]],
        )
        rows = load_rows(path=target)
        assert len(rows) == 50, "lost/corrupted rows: got %d/50" % len(rows)
        assert all(r.get("status") == "open" for r in rows)
        assert len({r["bet_id"] for r in rows}) == 50  # every id distinct, none merged


def test_concurrent_settle_no_duplicate():
    """Two subprocesses race to settle the SAME bet_id via append_row_if_new
    -> exactly ONE settled row lands (the double-settled-row race)."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "race_settle.jsonl"
        _run_workers(
            _SETTLE_WORKER,
            [[str(target), "1"], [str(target), "2"]],
        )
        rows = load_rows(path=target)
        settled = [r for r in rows if r.get("bet_id") == "shared-bet"]
        assert len(settled) == 1, "expected exactly 1 settled row, got %d" % len(settled)


def test_contended_required_lock_fails_closed():
    """A required lock that cannot be taken RAISES; the body never runs unlocked.

    Measured before the fix (_LOCK_KIND="msvcrt"): a contended _acquire returned
    False after its 5s timeout and ledger_lock ran the critical section anyway --
    two concurrent charges then both read prior=K and both wrote K+1, a lost
    update that UNDERCOUNTS K. append_row keeps its documented never-raise
    contract (required=False) so a settlement row is never silently dropped.
    """
    if _CLV._LOCK_KIND == "none":
        return  # no lock backend on this platform: nothing to fail closed against
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "contended.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        holder = _CLV._lock_path(target).open("a+", encoding="utf-8")
        assert _CLV._acquire(holder) is True, "could not take the lock to contend it"
        try:
            ran = False
            try:
                with ledger_lock(target):
                    ran = True
                raise AssertionError("a contended required lock must not run the body")
            except LedgerLockError:
                pass
            assert ran is False
            append_row({"bet_id": "still-lands", "status": "open"}, path=target)
            assert len(load_rows(path=target)) == 1
        finally:
            _CLV._release(holder)
            holder.close()


if __name__ == "__main__":
    test_concurrent_append_no_lost_rows()
    test_concurrent_settle_no_duplicate()
    test_contended_required_lock_fails_closed()
    print("OK")
