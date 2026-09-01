"""One-shot health snapshot for the pod, or a table of local fleet-lane output.

MODE pod makes exactly ONE ssh call. The remote side is bash only -- no
python needed there, so nothing to keep in sync with this repo's checkout --
and it only dumps raw signals; every bit of parsing lives here in Python so
it is unit-testable against fixtures without a real ssh call.

Landmines this is built to avoid (same lesson as track_daemon.py /
pod_supervisor.py, learned the hard way on this pod before):
  - never `pgrep`/`ps` a process by name -- the checking command's own argv
    can contain the same substring and match itself. The daemon check reads
    /workspace/track_daemon.pid -> /proc/<pid> existence instead, and the
    capture-process scan is handed the remote shell's own pid and its parent
    so it can exclude exactly the two pids most likely to self-match.
  - `pkill` no-ops on Windows python -- moot here, this only reads.

Run:
    python -m scripts.platformkit.ops_healthcheck --mode pod
    python -m scripts.platformkit.ops_healthcheck --mode local --tasks-dir <dir>
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

SSH_HOST = "root@213.192.2.83"
SSH_PORT = "40048"
SSH_TIMEOUT_S = 25
CAPTURE_PATTERN = "mlb_book_capture"

# Raw signals only. df / nvidia-smi / tail / a /proc cmdline dump -- parsed
# on the Python side below so the parsing has fixtures instead of a live pod.
_REMOTE_SCRIPT = r"""
set -u
if [ -f /workspace/track_daemon.pid ]; then
  DPID=$(cat /workspace/track_daemon.pid 2>/dev/null)
else
  DPID=""
fi
if [ -n "$DPID" ] && [ -d "/proc/$DPID" ]; then
  echo "DAEMON_ALIVE=1"
else
  echo "DAEMON_ALIVE=0"
fi
if [ -f /tmp/synthcal_verdict/COMPLETE ]; then
  echo "SYNTH_VERDICT_COMPLETE=1"
else
  echo "SYNTH_VERDICT_COMPLETE=0"
fi
# COMPLETE alone lied on 2026-09-01 (watcher wrote it after failed stages); count the judge reports too.
echo "SYNTH_VERDICT_REPORTS=$(ls /tmp/synthcal_verdict/*_report.json 2>/dev/null | wc -l)"
echo "SELF_PID=$$"
echo "PARENT_PID=$PPID"
echo "===DISK_DF==="
df -Pk /workspace 2>/dev/null
echo "===END_DISK_DF==="
echo "===GPU_RAW==="
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null
echo "===END_GPU_RAW==="
echo "===SYNTH_TAIL==="
tail -n 20 /tmp/synthcal_refine_run.log 2>/dev/null
echo "===END_SYNTH_TAIL==="
echo "===PROC_DUMP==="
for f in /proc/[0-9]*/cmdline; do
  pid=$(basename "$(dirname "$f")")
  printf '%s\t' "$pid"
  tr '\0' ' ' < "$f" 2>/dev/null
  printf '\n'
done
echo "===END_PROC_DUMP==="
""".strip("\n")


def extract_block(text: str, name: str) -> str:
    """Text between ===<name>=== and ===END_<name>=== markers, "" if absent."""
    m = re.search(r"===%s===\n(.*?)===END_%s===" % (re.escape(name), re.escape(name)),
                  text, re.S)
    return m.group(1) if m else ""


def parse_kv(text: str) -> dict:
    """KEY=value lines printed before the first marker block."""
    values: dict = {}
    for line in text.splitlines():
        if line.startswith("==="):
            break
        m = re.match(r"^([A-Z_]+)=(.*)$", line)
        if m:
            values[m.group(1)] = m.group(2)
    return values


def parse_disk_free_gb(df_text: str) -> Optional[float]:
    """Available GB from `df -Pk`'s data row (field 4, kilobytes)."""
    lines = [ln for ln in df_text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    fields = lines[1].split()
    if len(fields) < 4:
        return None
    try:
        return round(int(fields[3]) / 1024 / 1024, 3)
    except ValueError:
        return None


def parse_gpu_util(raw_text: str) -> Optional[int]:
    """Integer percent from an `nvidia-smi --query-gpu=utilization.gpu` line."""
    stripped = raw_text.strip()
    if not stripped:
        return None
    digits = re.sub(r"[^0-9]", "", stripped.splitlines()[0])
    return int(digits) if digits else None


# ponytail: assumed log shape is "...step <n>...loss <f>..." on one line,
# last such line wins. No real synthcal_refine_run.log was available to
# confirm the format -- if it turns out step/loss print in reverse order or
# on separate lines, widen this regex (or add a second reversed pattern)
# rather than restructure the caller.
_STEP_LOSS_RE = re.compile(
    r"step[\s:=]*(\d+).*?loss[\s:=]*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", re.I)


def parse_synthcal_tail(tail_text: str) -> dict:
    """Last {step, loss} found in a synthcal_refine_run.log tail."""
    for line in reversed(tail_text.splitlines()):
        m = _STEP_LOSS_RE.search(line)
        if m:
            return {"step": int(m.group(1)), "loss": float(m.group(2))}
    return {"step": None, "loss": None}


def capture_running(proc_dump: str, self_pid: str, parent_pid: str,
                     pattern: str = CAPTURE_PATTERN) -> bool:
    """True if a /proc cmdline other than the remote shell's own/parent matches.

    Takes the raw dump text (not a live /proc) so this is fixture-testable.
    """
    for line in proc_dump.splitlines():
        pid, _, cmdline = line.partition("\t")
        if pid in (self_pid, parent_pid):
            continue
        if pattern in cmdline:
            return True
    return False


def synthcal_complete(kv: dict) -> bool:
    """Sentinel AND at least one judge report json -- a bare COMPLETE is not a verdict."""
    reports = kv.get("SYNTH_VERDICT_REPORTS", "0").strip()
    return kv.get("SYNTH_VERDICT_COMPLETE") == "1" and reports.isdigit() and int(reports) > 0


def build_report(raw: str) -> dict:
    """Assemble the final report dict from the remote script's raw stdout."""
    kv = parse_kv(raw)
    step_loss = parse_synthcal_tail(extract_block(raw, "SYNTH_TAIL"))
    return {
        "reachable": True,
        "daemon_alive": kv.get("DAEMON_ALIVE") == "1",
        "synthcal": {"step": step_loss["step"], "loss": step_loss["loss"],
                     "complete": synthcal_complete(kv)},
        "capture_running": capture_running(extract_block(raw, "PROC_DUMP"),
                                            kv.get("SELF_PID", ""),
                                            kv.get("PARENT_PID", "")),
        "disk_free_gb": parse_disk_free_gb(extract_block(raw, "DISK_DF")),
        "gpu_util_pct": parse_gpu_util(extract_block(raw, "GPU_RAW")),
    }


def run_pod_check(host: str = SSH_HOST, port: str = SSH_PORT,
                   timeout: int = SSH_TIMEOUT_S) -> dict:
    """Fail-closed: any ssh problem returns {"reachable": False, "error": ...}."""
    try:
        result = subprocess.run(
            ["ssh", "-p", port, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
             host, _REMOTE_SCRIPT],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"reachable": False, "error": str(exc)}
    if result.returncode != 0:
        return {"reachable": False,
                 "error": (result.stderr or "ssh exit %d" % result.returncode).strip()[:300]}
    return build_report(result.stdout)


# ---- MODE local: newest task output file per lane ----

_EXIT_RE = re.compile(r"^EXIT(?:_CODE)?[:=\s]+(-?\d+)\s*$", re.I | re.M)
_OUTPUT_SUFFIXES = {".log", ".out", ".txt"}


def lane_of(path: Path, tasks_dir: Path) -> str:
    """Lane name for one task output file.

    ponytail: no fixed naming convention is documented for a "session tasks
    dir", so a file directly under tasks_dir is its own lane (stem) and a
    file nested one level down is grouped by its parent dir -- replace with
    the real scheme if/when the fleet standardizes one.
    """
    rel = path.relative_to(tasks_dir)
    return rel.parts[0] if len(rel.parts) > 1 else path.stem


def last_nonempty_line(text: str, limit: int = 200) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()[:limit]
    return ""


def parse_exit_code(text: str, sibling_exit: Optional[str] = None) -> Optional[int]:
    """Exit code for one lane: prefer a sibling `.exit` file, else the last
    inline EXIT=/EXIT_CODE= line in the output itself."""
    if sibling_exit is not None:
        try:
            return int(sibling_exit.strip())
        except ValueError:
            pass
    matches = _EXIT_RE.findall(text)
    return int(matches[-1]) if matches else None


def collect_lane_status(tasks_dir: Path) -> list:
    """Newest output file per lane -> [{lane, exit, last_line, file}, ...]."""
    newest: dict = {}
    for path in tasks_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _OUTPUT_SUFFIXES:
            continue
        lane = lane_of(path, tasks_dir)
        if lane not in newest or path.stat().st_mtime > newest[lane].stat().st_mtime:
            newest[lane] = path
    rows = []
    for lane, path in sorted(newest.items()):
        text = path.read_text(encoding="utf-8", errors="replace")
        sibling = path.with_suffix(".exit")
        sibling_text = sibling.read_text(encoding="utf-8") if sibling.is_file() else None
        rows.append({"lane": lane, "exit": parse_exit_code(text, sibling_text),
                     "last_line": last_nonempty_line(text), "file": str(path)})
    return rows


def render_table(rows: list) -> str:
    if not rows:
        return "(no task output files found)"
    lane_w = max(len(r["lane"]) for r in rows)
    return "\n".join(
        "%-*s  exit=%-4s  %s" % (lane_w, r["lane"],
                                  "?" if r["exit"] is None else str(r["exit"]),
                                  r["last_line"])
        for r in rows)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["pod", "local"], required=True)
    parser.add_argument("--host", default=SSH_HOST)
    parser.add_argument("--port", default=SSH_PORT)
    parser.add_argument("--timeout", type=int, default=SSH_TIMEOUT_S)
    parser.add_argument("--tasks-dir")
    args = parser.parse_args(argv[1:])

    if args.mode == "pod":
        report = run_pod_check(args.host, args.port, args.timeout)
        print(json.dumps(report, sort_keys=True))
        return 0 if report.get("reachable") else 1

    if not args.tasks_dir:
        parser.error("--mode local requires --tasks-dir")
    rows = collect_lane_status(Path(args.tasks_dir))
    print(render_table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
