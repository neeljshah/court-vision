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


def compose_lineups_cmd(date_str: str, python_exe: str = sys.executable) -> List[str]:
    """Cycle 65: rotowire lineup scrape command."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "fetch_lineups.py"),
        "--date", date_str,
    ]


def compose_dk_props_cmd(date_str: str, books: Optional[List[str]] = None,
                          python_exe: str = sys.executable) -> List[str]:
    """Cycle 65: DraftKings/FanDuel props scrape command."""
    cmd = [
        python_exe,
        os.path.join(SCRIPTS_DIR, "fetch_dk_props.py"),
        "--date", date_str,
    ]
    for b in (books or ["draftkings"]):
        cmd += ["--book", b]
    return cmd


def compose_actuals_cmd(date_str: str, python_exe: str = sys.executable) -> List[str]:
    """Cycle 71: post-game actuals scrape (NBA boxscoretraditionalv2)."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "fetch_actuals.py"),
        "--date", date_str,
    ]


def compose_settle_cmd(date_str: str, project_dir: str = PROJECT_DIR,
                        python_exe: str = sys.executable) -> List[str]:
    """Cycle 71: settle bets vs actuals."""
    bet_path = os.path.join(project_dir, "data", "bets", f"{date_str}.csv")
    actuals_path = os.path.join(project_dir, "data", "actuals", f"{date_str}.csv")
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "settle_bets.py"),
        bet_path, actuals_path,
    ]


def compose_report_cmd(date_str: str, python_exe: str = sys.executable) -> List[str]:
    """Cycle 74: nightly Markdown summary."""
    return [
        python_exe,
        os.path.join(SCRIPTS_DIR, "nightly_report.py"),
        "--date", date_str,
    ]


def compose_slate_cmd(date_str: str, top: Optional[int] = None,
                      with_lineups: bool = False,
                      python_exe: str = sys.executable) -> List[str]:
    """Build the argv list for the predict_slate subprocess.

    --save and --injuries are always passed (bare flags) — that is the
    whole point of running this orchestrator over the raw scripts. Cycle 65:
    --lineups added when auto-lineups was successful.
    """
    cmd = [
        python_exe,
        os.path.join(SCRIPTS_DIR, "predict_slate.py"),
        "--date", date_str,
        "--save",
        "--injuries",
    ]
    if with_lineups:
        cmd.append("--lineups")
    if top is not None:
        cmd += ["--top", str(top)]
    return cmd


def compose_compare_cmd(lines_path: str, kelly: bool = False,
                        bankroll: Optional[float] = None,
                        with_lineups: bool = False,
                        python_exe: str = sys.executable) -> List[str]:
    """Build the argv list for the compare_to_lines subprocess."""
    cmd = [
        python_exe,
        os.path.join(SCRIPTS_DIR, "compare_to_lines.py"),
        lines_path,
        "--injuries",
    ]
    if with_lineups:
        cmd.append("--lineups")
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
    ap.add_argument("--auto-lineups", action="store_true",
                    help="Cycle 65: also run scripts/fetch_lineups.py and pass --lineups "
                         "through to predict_slate + compare_to_lines.")
    ap.add_argument("--auto-lines", action="store_true",
                    help="Cycle 65: also run scripts/fetch_dk_props.py and use its output "
                         "(data/lines/<date>.csv) as the --lines input to compare_to_lines. "
                         "Overrides --lines if both are passed.")
    ap.add_argument("--settle", action="store_true",
                    help="Cycle 71: post-game mode. Skips slate/compare; runs fetch_actuals "
                         "+ settle_bets for --date. Use this AFTER games complete.")
    ap.add_argument("--report", action="store_true",
                    help="Cycle 74: also run nightly_report.py at the end of the chosen mode "
                         "(works with both morning + --settle).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the commands that would run and exit.")
    args = ap.parse_args(argv)

    try:
        date_str = _parse_date_arg(args.date)
    except ValueError:
        print(f"[fail] bad --date format '{args.date}' (need YYYY-MM-DD)")
        return 2

    # Cycle 71: --settle is a post-game mode (no slate / compare).
    if args.settle:
        actuals_cmd = compose_actuals_cmd(date_str)
        settle_cmd = compose_settle_cmd(date_str)
        report_cmd = compose_report_cmd(date_str) if args.report else None
        if args.dry_run:
            print(f"[daily_run] dry-run SETTLE plan for {date_str}:")
            _print_cmd("[A] fetch_actuals", actuals_cmd)
            _print_cmd("[B] settle_bets", settle_cmd)
            if report_cmd is not None:
                _print_cmd("[C] nightly_report", report_cmd)
            return 0
        t0 = time.time()
        rc, _ = _run_step("fetch_actuals", actuals_cmd, capture_stdout=False)
        if rc != 0:
            print(f"[daily_run] FAIL: fetch_actuals exited {rc} — can't settle.")
            return 1
        rc, _ = _run_step("settle_bets", settle_cmd, capture_stdout=False)
        if rc != 0:
            print(f"[daily_run] warn: settle_bets exited {rc}")
        if report_cmd is not None:
            _run_step("nightly_report", report_cmd, capture_stdout=False)
        print(f"\n[daily_run] settle complete in {time.time()-t0:.1f}s")
        return rc

    # Cycle 65: auto-lines uses fetch_dk_props output as the --lines path.
    effective_lines = args.lines
    if args.auto_lines:
        effective_lines = os.path.join(PROJECT_DIR, "data", "lines", f"{date_str}.csv")

    # Build all commands up front so --dry-run can show them and tests can
    # assert on the exact argv lists without invoking subprocess.
    inj_cmd = compose_injury_cmd(date_str)
    lineups_cmd = compose_lineups_cmd(date_str) if args.auto_lineups else None
    dk_cmd = compose_dk_props_cmd(date_str) if args.auto_lines else None
    slate_cmd = compose_slate_cmd(date_str, top=args.top,
                                    with_lineups=args.auto_lineups)
    compare_cmd = (
        compose_compare_cmd(effective_lines, kelly=args.kelly,
                              bankroll=args.bankroll,
                              with_lineups=args.auto_lineups)
        if effective_lines else None
    )

    if args.dry_run:
        print(f"[daily_run] dry-run plan for {date_str}:")
        if not args.skip_injuries:
            _print_cmd("[1] injuries", inj_cmd)
        else:
            print("  [1] (skipped — --skip-injuries)")
        if lineups_cmd is not None:
            _print_cmd("[1b] lineups", lineups_cmd)
        if dk_cmd is not None:
            _print_cmd("[1c] dk_props", dk_cmd)
        _print_cmd("[2] predict_slate", slate_cmd)
        if compare_cmd is not None:
            _print_cmd("[3] compare_to_lines", compare_cmd)
        else:
            print("  [3] (skipped — no --lines / --auto-lines)")
        if args.report:
            _print_cmd("[4] nightly_report", compose_report_cmd(date_str))
        return 0

    t0 = time.time()

    # --- Step 1: injuries ---
    if not args.skip_injuries:
        rc, _ = _run_step("fetch_injury_report", inj_cmd, capture_stdout=False)
        if rc != 0:
            # Non-fatal — predictions still ship without latest injuries.
            print(f"[daily_run] warn: fetch_injury_report exited {rc} "
                  f"(continuing without the latest report)")

    # --- Step 1b: lineups (cycle 65) ---
    if lineups_cmd is not None:
        rc, _ = _run_step("fetch_lineups", lineups_cmd, capture_stdout=False)
        if rc != 0:
            print(f"[daily_run] warn: fetch_lineups exited {rc} "
                  f"(slate + compare will run without --lineups context)")
            # Strip --lineups from downstream commands so they don't try to
            # read a JSON that wasn't created.
            slate_cmd = [a for a in slate_cmd if a != "--lineups"]
            if compare_cmd:
                compare_cmd = [a for a in compare_cmd if a != "--lineups"]

    # --- Step 1c: DraftKings props (cycle 65) ---
    if dk_cmd is not None:
        rc, _ = _run_step("fetch_dk_props", dk_cmd, capture_stdout=False)
        if rc != 0:
            print(f"[daily_run] warn: fetch_dk_props exited {rc} "
                  f"(compare step will be skipped if --auto-lines was the only line source)")
            if args.lines is None:
                compare_cmd = None

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

    # --- Step 4 (cycle 74): nightly Markdown report (optional) ---
    if args.report:
        _run_step("nightly_report", compose_report_cmd(date_str), capture_stdout=False)

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
