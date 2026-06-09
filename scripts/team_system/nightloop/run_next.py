"""Night-loop driver: run the NEXT backlog experiment, auto-record the verdict, check it off.

Designed so each loop wake-up is a single robust call: this picks the first unchecked BACKLOG.md item,
runs its command with a timeout, extracts the verdict, appends it to RESULTS.md, marks the item done, and
prints a compact summary (so the model only spends tokens deciding whether to escalate a CANDIDATE to
~/.claude memory). Wrapped in try/except so one failing experiment records ERROR and the loop continues.
When the backlog is empty it says so (the model then appends new experiments). ascii-only.

  python scripts/team_system/nightloop/run_next.py            # run one
  python scripts/team_system/nightloop/run_next.py --n 3      # run several this turn (fewer wake-ups)
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BACKLOG = os.path.join(HERE, "BACKLOG.md")
RESULTS = os.path.join(HERE, "RESULTS.md")
ITEM_RE = re.compile(r"^- \[ \] (\S+) \| (.+?) \| (.+)$")


def next_item():
    for i, line in enumerate(open(BACKLOG, encoding="utf-8").read().splitlines()):
        m = ITEM_RE.match(line)
        if m:
            return i, m.group(1), m.group(2).strip(), m.group(3).strip()
    return None


def check_off(item_id):
    lines = open(BACKLOG, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"- [ ] {item_id} "):
            lines[i] = line.replace("- [ ] ", "- [x] ", 1)
            break
    open(BACKLOG, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def extract_verdict(out):
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    v = [l for l in lines if "VERDICT" in l]
    if v:
        return v[-1][:300]
    # else last 2 non-empty lines as a summary
    return " | ".join(lines[-2:])[:300] if lines else "(no output)"


def is_candidate(verdict):
    return any(k in verdict for k in ("CANDIDATE", "FIX candidate", "candidate if")) and "KEEP" not in verdict.split("->")[-1]


def append_result(item_id, verdict, candidate, err=False):
    when = datetime.datetime.now().strftime("%m-%d %H:%M")
    tag = "ERROR" if err else ("CAND" if candidate else "ok")
    safe = verdict.replace("|", "/").replace("\n", " ")
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(f"| {when} | {item_id} | {tag} | {safe} |\n")


def run_one():
    nxt = next_item()
    if nxt is None:
        print("BACKLOG EMPTY -- model should append new experiments (more sweeps / finer grids around candidates / new signals).")
        return False
    _, item_id, cmd, what = nxt
    print(f">>> {item_id}: {what}\n    $ {cmd}")
    try:
        r = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True, timeout=900)
        out = (r.stdout or "") + ("\n" + r.stderr if r.returncode != 0 else "")
        verdict = extract_verdict(out)
        cand = is_candidate(verdict) and r.returncode == 0
        append_result(item_id, verdict, cand, err=(r.returncode != 0))
        check_off(item_id)
        flag = "  *** CANDIDATE -> record to memory ***" if cand else ""
        print(f"<<< {item_id} [{'ERR' if r.returncode else 'ok'}]: {verdict}{flag}")
    except subprocess.TimeoutExpired:
        append_result(item_id, "TIMEOUT (>900s)", False, err=True); check_off(item_id)
        print(f"<<< {item_id} [TIMEOUT]")
    except Exception as e:
        append_result(item_id, f"EXC {type(e).__name__}: {e}", False, err=True); check_off(item_id)
        print(f"<<< {item_id} [EXC] {e}")
    return True


LOCK = os.path.join(HERE, ".lock")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1)
    a = ap.parse_args()
    # lock: if another run is in progress (fresh lock < 1000s), exit cleanly so a fallback wake-up
    # can never collide with an in-flight run and race on BACKLOG.md.
    if os.path.exists(LOCK):
        age = (datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(LOCK))).total_seconds()
        if age < 1000:
            print(f"LOCKED (another run in progress, {age:.0f}s) -- exiting")
            return
    open(LOCK, "w").write(str(os.getpid()))
    try:
        for _ in range(a.n):
            if not run_one():
                break
    finally:
        if os.path.exists(LOCK):
            os.remove(LOCK)


if __name__ == "__main__":
    main()
