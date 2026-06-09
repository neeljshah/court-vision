"""STOP -- the unattended kill-switch (MASTER_SYSTEM_BUILD section 7.6).

The user is away for days. They stop the run with:   New-Item data/registry/STOP -ItemType File
The loop checks check_stop() at the TOP of every iteration AND before every subagent fan-out; when the
file is present it finishes the current atomic write, reaps all proc_ledger processes, writes a STOP
report, sets state.status=STOPPED, and EXITS. The STOP file is NEVER ignored or deleted by the loop.

`python scripts/team_system/loop/stop_run.py` is the HARD kill (e.g. `bot stop`): reap every proc_ledger
pid, drop the STOP file (so any live loop instance halts), release the registry .lock, write the report.
"""
from __future__ import annotations
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from autoloop import state as st  # noqa: E402

REPORT = os.path.join(st.ROOT, "OVERNIGHT_MORNING_REPORT.md")
_LOCK = os.path.join(st.REG, ".lock")


def check_stop() -> bool:
    """True if the user dropped data/registry/STOP. Call at the top of every iteration + before fan-out."""
    return os.path.exists(st.STOP_PATH)


def drop_stop_file(reason: str = "manual") -> None:
    os.makedirs(st.REG, exist_ok=True)
    if not os.path.exists(st.STOP_PATH):
        with open(st.STOP_PATH, "w", encoding="utf-8") as f:
            f.write(f"STOP requested {time.strftime('%Y-%m-%dT%H:%M:%S')} -- {reason}\n")


def _kill(pid: int) -> bool:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           capture_output=True, timeout=10)
        else:
            import signal
            os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


def reap_procs() -> list:
    """Kill every process registered in proc_ledger.json; clear the ledger. Returns reaped pids."""
    procs = st.read_proc_ledger()
    reaped = []
    for p in procs:
        pid = int(p.get("pid", -1))
        if pid > 0 and _kill(pid):
            reaped.append(pid)
    st._atomic_json(st.PROC_LEDGER, [])
    return reaped


def release_lock() -> None:
    try:
        os.remove(_LOCK)
    except FileNotFoundError:
        pass


def write_stop_report(reason: str, status: str = "STOPPED") -> str:
    s = st.read_state()
    df = st.ledger_df()
    closed = df[df.verdict != "IN_FLIGHT"] if not df.empty else df
    last = closed.tail(8)
    fr = s.get("frontier_status", {})
    open_frontiers = [k for k, v in fr.items() if (v or {}).get("status") != "EXHAUSTED"]
    lines = [
        f"# RUN REPORT -- {status}", "",
        f"- when: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"- reason: {reason}",
        f"- phase: {s.get('phase')}  iter: {s.get('iter_id')}  last board: {s.get('last_board')}",
        f"- budget: {s.get('budget', {})}",
        f"- open frontiers: {open_frontiers or '(none / all exhausted)'}",
        f"- exhausted frontiers: {[k for k in fr if (fr[k] or {}).get('status')=='EXHAUSTED']}",
        "", "## Last levers", "", "| iter | frontier | verdict | delta | notes |", "|--:|---|---|---|---|",
    ]
    for _, r in last.iterrows():
        lines.append(f"| {r.get('iter_id')} | {r.get('frontier')} | {r.get('verdict')} | "
                     f"{r.get('delta')} | {str(r.get('notes'))[:60]} |")
    lines += ["", "## Resume", "",
              "Re-paste scripts/team_system/MASTER_SYSTEM_BUILD_PROMPT.md as the first message to resume.",
              "The loop reads data/registry/state.json on wake and continues from the cursor.",
              "To clear a manual STOP: `Remove-Item data/registry/STOP`.", ""]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return REPORT


def graceful_stop(reason: str = "stop requested", status: str = "STOPPED") -> dict:
    """Leave the system known-good: reap procs, write report, set status, release lock. Does NOT create
    the STOP file (the caller already saw it / the user created it)."""
    reaped = reap_procs()
    report = write_stop_report(reason, status)
    st.update_state(status=status, in_flight=st.read_state().get("in_flight"),
                    notes=f"{status}: {reason}")
    release_lock()
    return dict(status=status, reaped=reaped, report=report)


def hard_stop(reason: str = "manual stop_run.py") -> dict:
    """The forceful kill (bot stop): drop STOP file so any live loop halts, then graceful_stop."""
    drop_stop_file(reason)
    out = graceful_stop(reason, status="STOPPED")
    print(f"HARD STOP complete. reaped pids={out['reaped']}. STOP file dropped at {st.STOP_PATH}.")
    print(f"report -> {out['report']}")
    return out


if __name__ == "__main__":
    hard_stop(" ".join(sys.argv[1:]) or "manual stop_run.py")
