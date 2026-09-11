"""G389: dispatch the blind native adjudication batches in the SEALED sweep order.

Reuses the G373 rater driver (prompt, codex resolver, batch parser, Q6 reason
normalisation) and changes only what G389 seals differently: the queue order is the
archived bin/round-robin permutation -- never sorted, never a prefix -- each rater
sees only its disjoint allocation plus the sealed 30-key audit duplicate, and the
PC gate counts codex.exe processes by COMMAND LINE (the always-on app server shares
the image name, so an image-name count would silently spend a slot on it).

A launch through a codex directory without the image/tool host rates nothing while
every process signal stays healthy, so the batch is recorded as a FAULT here and is
never silently re-run.
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g373_rate as base

CODEX_HOME = {"terra": r"C:\Users\neelj\.codex-a7", "sol": r"C:\Users\neelj\.codex-sol"}
MIN_FREE_GB = 2.8
MAX_CODEX_EXEC = 3
GATE_RETRY_S = 110
LOCK = Path(r"C:\Users\neelj\AppData\Local\Temp\g389_launch.lock")
GATE_PS = ("@(Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | "
           "Where-Object { $_.CommandLine -match ' exec ' }).Count")
FREE_PS = "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)"


def _ps(command: str) -> float:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                         capture_output=True, text=True, timeout=180).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return -1.0


def gate_state() -> tuple[float, float]:
    """The binding PC gate: live `codex exec` processes and free physical GB."""
    return _ps(GATE_PS), _ps(FREE_PS)


def gate_open() -> bool:
    running, free_gb = gate_state()
    ok = 0 <= running < MAX_CODEX_EXEC and free_gb >= MIN_FREE_GB
    print(f"GATE exec={running} free_gb={free_gb} ok={ok}", flush=True)
    return ok


def _lock() -> bool:
    """One launcher at a time, so two G389 lanes cannot both pass a 2/3 gate."""
    try:
        handle = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - LOCK.stat().st_mtime > 600:
            LOCK.unlink(missing_ok=True)
        return False
    os.close(handle)
    return True


def launch(rater: str, prompt: str, log: Path, cwd: Path, tag: str) -> str:
    """Spawn one windowless rater batch; returns the codex binary it used."""
    binary = base.codex_binary()
    command = [base.PYTHONW, base.LAUNCHER, "--log", str(log), "--cwd", str(cwd),
               "--tag", tag, "--env", "CODEX_HOME=" + CODEX_HOME[rater],
               "--", binary, "exec", "--skip-git-repo-check", "--sandbox",
               "workspace-write", "-c", "model_reasoning_effort=medium", "--", prompt]
    subprocess.Popen(command, cwd=str(cwd), close_fds=True)
    return binary


def queue_for(sweep: list[dict], rater: str) -> list[dict]:
    """Sealed order, this rater's disjoint allocation plus the audit duplicates."""
    return [row for row in sweep
            if row["allocation"] == rater or row["audit_duplicate"] == "1"]


def done_keys(out: Path, rater: str) -> set[str]:
    """Completed keys are excluded from every restart; none is ever re-judged."""
    if not out.exists():
        return set()
    with out.open(encoding="utf-8", newline="") as handle:
        return {row["frame_key"] for row in csv.DictReader(handle) if row["rater"] == rater}


def run(args) -> int:
    cwd = Path(args.cwd).resolve()
    sheets = (cwd / args.sheets_dir).resolve()
    with (cwd / args.sweep).open(encoding="utf-8", newline="") as handle:
        sweep = list(csv.DictReader(handle))
    keys = {row["frame_key"][:12]: row["frame_key"] for row in sweep}
    out = Path(args.out)
    raw_dir, log_dir = Path(args.raw_dir), Path(args.log_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    faults = Path(args.raw_dir) / (args.rater + "_faults.txt")

    todo_rows = [row for row in queue_for(sweep, args.rater)
                 if row["frame_key"] not in done_keys(out, args.rater)]
    todo = [row["frame_key"][:12] for row in todo_rows]
    print(f"QUEUE rater={args.rater} todo={len(todo)}", flush=True)
    batches = [todo[index:index + args.batch_size]
               for index in range(0, len(todo), args.batch_size)][:args.max_batches]
    relative = sheets.relative_to(cwd).as_posix()
    for number, ids in enumerate(batches, 1):
        tag = f"g389_rater_{args.rater}_{args.start + number:02d}"
        raw = raw_dir.resolve() / (tag + ".txt")
        log = log_dir.resolve() / ("cx_" + tag + ".log")
        raw.unlink(missing_ok=True)
        log.unlink(missing_ok=True)
        while not (gate_open() and _lock()):
            time.sleep(GATE_RETRY_S)
        prompt = base.PROMPT.format(sheets=relative, out=raw.relative_to(cwd).as_posix(),
                                    count=len(ids), ids="\n".join(ids))
        binary = launch(args.rater, prompt, log, cwd, tag)
        time.sleep(45)
        LOCK.unlink(missing_ok=True)
        code = base.wait_for_exit(log, args.timeout_s)
        # A recovered batch can already be in the table (the operator may replay a raw
        # file after a halt), so the completed key set is re-read here and a key is
        # never appended twice: a duplicate row would double-count one judgment.
        already = done_keys(out, args.rater)
        rows = [row for row in base.parse_batch(raw, args.rater, ids, keys)
                if row["frame_key"] not in already]
        if not rows:
            faults.open("a", encoding="ascii").write(
                f"{tag} ids={len(ids)} parsed=0 exit={code} binary={binary}\n")
        base.append(out, rows)
        print(f"BATCH {tag} ids={len(ids)} parsed={len(rows)} exit={code}", flush=True)
    print("QUEUE-DONE rater=" + args.rater, flush=True)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g389_rate")
    for flag in ("--sweep", "--sheets-dir", "--out", "--raw-dir", "--log-dir", "--rater"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--cwd", default=r"C:\Users\neelj\nba-track-a11")
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--max-batches", type=int, default=200)
    parser.add_argument("--timeout-s", type=int, default=2400)
    parser.add_argument("--start", type=int, default=0)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
