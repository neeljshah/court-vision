"""daily_run.py — orchestrator for the daily predictions workflow (cycle 54).

The last 11 cycles shipped 5 CLI scripts that together implement the daily
ops flow documented in PREDICTIONS_QUICKSTART.md > "Daily ops workflow":

    fetch_injury_report  ->  predict_slate (--save --injuries)  ->  compare_to_lines (--injuries)

Running them by hand every day is the user's daily ritual. This module
codifies the sequence, surfaces a one-line summary at the end, and stays
out of the way of the underlying scripts (no nba_api imports here; the
sub-scripts already do that work).

This is a **pure orchestrator** — it does not duplicate any logic from
fetch_injury_report.py, predict_slate.py, or compare_to_lines.py. If the
sub-scripts change their flags or output, the equivalent changes only
need to happen there; this module just shells out.

Examples
--------
    python scripts/daily_run.py                              # injuries -> slate
    python scripts/daily_run.py --lines tonight.csv          # full flow
    python scripts/daily_run.py --lines tonight.csv --kelly --bankroll 1000
    python scripts/daily_run.py --date 2026-05-24            # historical replay
    python scripts/daily_run.py --skip-injuries              # already have JSON
    python scripts/daily_run.py --dry-run                    # show commands only

Behaviour
---------
1. Step 1 (unless --skip-injuries): fetch_injury_report --date <date>.
   Non-zero exit prints a warning but does NOT block subsequent steps —
   the injury PDF often 404s before its publish time, and slate
   predictions still have value without the latest injury cross-ref.
2. Step 2: predict_slate --date <date> --save --injuries (+ --top if given).
   Non-zero exit aborts the run.
3. Step 3 (only if --lines given): compare_to_lines <lines> --injuries
   (+ --kelly --bankroll if given). stdout is tee'd through this process
   so the bet count can be parsed for the summary while the user still
   sees the original output live.
4. Final 4-line summary:
       injuries: N players flagged (or "skipped")
       predictions: M rows written to data/predictions/<date>.csv
       bets: K positive-EV bets (or "no bets" / "n/a" if no --lines)
       elapsed: X.Xs

Exit codes
----------
    0  - the full requested flow completed
    1  - predict_slate failed (a fatal step)
    2  - argument error (bad --date format, etc.)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date as _date_cls
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
DATA_DIR = os.path.join(PROJECT_DIR, "data")


# --- pure helpers (kept side-effect-free so tests can hammer them) ---------

def _parse_date_arg(s: Optional[str]) -> str:
    """Return YYYY-MM-DD; defaults to today. Raises ValueError on bad input."""
    if not s:
        return datetime.now().date().isoformat()
    # Validate format by parsing then re-serialising.
    return datetime.strptime(s, "%Y-%m-%d").date().isoformat()


def compose_injury_cmd(date_str: str, python_exe: str = sys.executable) -> List[str]:
    """Build the argv list for the fetch_injury_report subprocess."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "fetch_injury_report.py"),
        "--date", date_str,
    ]


def compose_slate_cmd(date_str: str, top: Optional[int] = None,
                      python_exe: str = sys.executable) -> List[str]:
    """Build the argv list for the predict_slate subprocess.

    --save and --injuries are always passed (bare flags) — that is the
    whole point of running this orchestrator over the raw scripts.
    """
    cmd = [
        python_exe,
        os.path.join(SCRIPTS_DIR, "predict_slate.py"),
        "--date", date_str,
        "--save",
        "--injuries",
    ]
    if top is not None:
        cmd += ["--top", str(top)]
    return cmd


def compose_compare_cmd(lines_path: str, kelly: bool = False,
                        bankroll: Optional[float] = None,
                        python_exe: str = sys.executable) -> List[str]:
    """Build the argv list for the compare_to_lines subprocess."""
    cmd = [
        python_exe,
        os.path.join(SCRIPTS_DIR, "compare_to_lines.py"),
        lines_path,
        "--injuries",
    ]
    if kelly:
        cmd.append("--kelly")
    if bankroll is not None:
        cmd += ["--bankroll", str(bankroll)]
    return cmd


def count_injuries(date_str: str, project_dir: str = PROJECT_DIR) -> Optional[int]:
    """Return number of player rows in data/injuries_<date>.json; None on miss."""
    path = os.path.join(project_dir, "data", f"injuries_{date_str}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        players = payload.get("players") or []
        return len(players)
    except (json.JSONDecodeError, OSError):
        return None


def count_predictions(date_str: str, project_dir: str = PROJECT_DIR) -> Optional[int]:
    """Return number of data rows in data/predictions/<date>.csv; None on miss.

    Excludes the header line. Returns None if the file is missing — the
    summary printer then surfaces that instead of a misleading "0".
    """
    path = os.path.join(project_dir, "data", "predictions", f"{date_str}.csv")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            # Total lines minus the header. Strip blanks defensively.
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        return max(0, len(lines) - 1)
    except OSError:
        return None


# compare_to_lines prints either:
#   "[done] no bets passed --min-edge filter"  (no positive EV bets)
# or a header line followed by one bet per line. The header looks like
# "  player  stat  line   model  edge   side   prob   odds   EV/$   Kelly%"
# and the separator line is all dashes + spaces. The body rows start with
# two spaces then a name (any non-dash char) — we count those.
_NO_BETS_RE = re.compile(r"no bets passed", re.IGNORECASE)
_HEADER_RE = re.compile(r"^\s*player\s+stat\s+line\s+model\s+edge", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"^[\s\-]+$")


def parse_bet_count(stdout: str) -> int:
    """Count positive-EV bet rows in compare_to_lines stdout.

    Returns 0 when the script printed "no bets passed --min-edge filter"
    OR when no header was found (e.g. all rows were skipped for injuries).
    """
    if not stdout:
        return 0
    if _NO_BETS_RE.search(stdout):
        return 0

    # Walk lines: count rows that appear AFTER the header row, skipping
    # the dashed separator and any blank lines / trailing Kelly summary.
    in_table = False
    count = 0
    for raw in stdout.splitlines():
        line = raw.rstrip()
        if not in_table:
            if _HEADER_RE.match(line):
                in_table = True
            continue
        if not line.strip():
            # blank line ends the table
            break
        if _SEPARATOR_RE.match(line):
            continue
        # The "Total Kelly stake on positive-EV bets" line starts with
        # spaces+"Total" — treat any non-numeric-leading row after a
        # blank-or-separator as end-of-table.
        if line.lstrip().startswith("Total Kelly stake"):
            break
        count += 1
    return count


def _print_cmd(prefix: str, cmd: List[str]) -> None:
    """Render a command in a copy-pastable form for the dry-run output."""
    # Use the script's basename (not the full python path) for legibility.
    rendered_parts: List[str] = ["python"]
    for token in cmd[1:]:
        if token.endswith(".py") and os.path.isabs(token):
            # Show path relative to PROJECT_DIR.
            try:
                rel = os.path.relpath(token, PROJECT_DIR).replace("\\", "/")
                rendered_parts.append(rel)
            except ValueError:
                rendered_parts.append(token)
        else:
            rendered_parts.append(token)
    print(f"  {prefix} {' '.join(rendered_parts)}")


def _run_step(name: str, cmd: List[str], capture_stdout: bool = False
              ) -> Tuple[int, str]:
    """Run a subprocess; return (exit_code, captured_stdout_or_empty).

    When ``capture_stdout`` is False the child's output is inherited so the
    user sees it live; the returned stdout is ''.

    When True we still want the user to see output AS it streams, so we
    tee: read stdout line-by-line, echo to our own stdout, and collect
    into a string for parsing. This is the "tee semantics" the task
    specifies.
    """
    print(f"\n[daily_run] step: {name}")
    if not capture_stdout:
        result = subprocess.run(cmd, check=False)
        return result.returncode, ""

    # Tee mode: stream child stdout to our stdout AND capture it.
    captured: List[str] = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            captured.append(line)
        rc = proc.wait()
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
    return rc, "".join(captured)


def _print_summary(date_str: str, injuries_count: Optional[int],
                   injuries_skipped: bool,
                   predictions_count: Optional[int],
                   bets_count: Optional[int],
                   elapsed: float, project_dir: str = PROJECT_DIR) -> None:
    """Render the final 4-line orchestrator summary."""
    if injuries_skipped:
        inj_line = "  injuries:    skipped"
    elif injuries_count is None:
        inj_line = "  injuries:    no report fetched"
    else:
        inj_line = f"  injuries:    {injuries_count} players flagged"

    if predictions_count is None:
        pred_line = "  predictions: (no CSV written)"
    else:
        rel = os.path.relpath(
            os.path.join(project_dir, "data", "predictions", f"{date_str}.csv"),
            project_dir,
        ).replace("\\", "/")
        pred_line = f"  predictions: {predictions_count} rows -> {rel}"

    if bets_count is None:
        bet_line = "  bets:        n/a (no --lines)"
    elif bets_count == 0:
        bet_line = "  bets:        no positive-EV bets"
    else:
        bet_line = f"  bets:        {bets_count} positive-EV bet(s)"

    print("\n[daily_run] summary")
    print(inj_line)
    print(pred_line)
    print(bet_line)
    print(f"  elapsed:     {elapsed:.1f}s")


# --- main entry point ------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Orchestrate the daily NBA predictions ops flow "
                    "(injuries -> slate -> compare_to_lines).",
    )
    ap.add_argument("--date", default=None,
                    help="Target date YYYY-MM-DD (default: today).")
    ap.add_argument("--lines", default=None,
                    help="Path to sportsbook lines CSV. Required for the "
                         "compare_to_lines step; omit to skip it.")
    ap.add_argument("--top", type=int, default=None,
                    help="Players per team for predict_slate.")
    ap.add_argument("--kelly", action="store_true",
                    help="Pass --kelly to compare_to_lines.")
    ap.add_argument("--bankroll", type=float, default=None,
                    help="Pass --bankroll N to compare_to_lines.")
    ap.add_argument("--skip-injuries", action="store_true",
                    help="Skip fetch_injury_report (use the JSON you already have).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the commands that would run and exit.")
    args = ap.parse_args(argv)

    try:
        date_str = _parse_date_arg(args.date)
    except ValueError:
        print(f"[fail] bad --date format '{args.date}' (need YYYY-MM-DD)")
        return 2

    # Build all commands up front so --dry-run can show them and tests can
    # assert on the exact argv lists without invoking subprocess.
    inj_cmd = compose_injury_cmd(date_str)
    slate_cmd = compose_slate_cmd(date_str, top=args.top)
    compare_cmd = (
        compose_compare_cmd(args.lines, kelly=args.kelly, bankroll=args.bankroll)
        if args.lines else None
    )

    if args.dry_run:
        print(f"[daily_run] dry-run plan for {date_str}:")
        if not args.skip_injuries:
            _print_cmd("[1]", inj_cmd)
        else:
            print("  [1] (skipped — --skip-injuries)")
        _print_cmd("[2]", slate_cmd)
        if compare_cmd is not None:
            _print_cmd("[3]", compare_cmd)
        else:
            print("  [3] (skipped — no --lines)")
        return 0

    t0 = time.time()

    # --- Step 1: injuries ---
    if not args.skip_injuries:
        rc, _ = _run_step("fetch_injury_report", inj_cmd, capture_stdout=False)
        if rc != 0:
            # Non-fatal — predictions still ship without latest injuries.
            print(f"[daily_run] warn: fetch_injury_report exited {rc} "
                  f"(continuing without the latest report)")

    # --- Step 2: slate predictions ---
    rc, _ = _run_step("predict_slate", slate_cmd, capture_stdout=False)
    if rc != 0:
        print(f"[daily_run] FAIL: predict_slate exited {rc}")
        return 1

    # --- Step 3: compare to lines (optional) ---
    bets_count: Optional[int] = None
    if compare_cmd is not None:
        rc, captured = _run_step("compare_to_lines", compare_cmd, capture_stdout=True)
        if rc != 0:
            print(f"[daily_run] warn: compare_to_lines exited {rc}")
        bets_count = parse_bet_count(captured)

    elapsed = time.time() - t0
    _print_summary(
        date_str=date_str,
        injuries_count=count_injuries(date_str),
        injuries_skipped=args.skip_injuries,
        predictions_count=count_predictions(date_str),
        bets_count=bets_count,
        elapsed=elapsed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
