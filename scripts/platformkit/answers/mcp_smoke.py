"""In-process smoke test for the CourtVision MCP tool surface.

Drives every registered tool (scripts.platformkit.mcp_server.tools) through the
SAME handler the live server calls, with a known-good AND a known-bad input,
and asserts the fail-closed envelope contract (docs/AI_CONSUMER_CONTRACT.md):

  * a handler NEVER lets an exception escape (fail-closed, not fail-crash),
  * status is always one of the contract's enum values,
  * an `ok` leaf answer carries source_artifact + as_of,
  * a `no_data` answer carries a reason (note / reason / source_artifact),
  * a known-bad leaf input fails CLOSED (never fabricates an `ok`),
  * NO absolute box-local path (drive-letter, e.g. C:\\Users\\...) leaks into
    ANY envelope -- the clone-portability landmine (source_artifact must be
    repo-relative; see scripts/platformkit/analytics_showcase/_clone_safe.py).

Prints an ASCII scoreboard (tool | ok-case | bad-case | clone_safe) and exits 0
only if every column passes. Read-only: run_burst is exercised in a no-op mode
(bogus step, report redirected to a temp file) so the smoke never fires the
network/disk maintenance job or clobbers the real burst_report.json.

Run:  python -m scripts.platformkit.answers.mcp_smoke [--check]
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

try:  # package import (normal launch from repo root)
    from scripts.platformkit.mcp_server import tools as _tools
    from scripts.platformkit import burst_run as _burst
except ImportError:  # direct-script / per-file-test fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.mcp_server import tools as _tools  # type: ignore
    from scripts.platformkit import burst_run as _burst  # type: ignore

VALID_STATUS = {"ok", "no_data", "not_supported", "refused", "ambiguous", "aborted"}
# Composite / executor tools whose top-level `ok` is a fan-out envelope with no
# single number, so the source_artifact+as_of leaf rule and the bad-input-must-
# fail-closed rule do not apply (matchup_preview stays ok with absent blocks;
# system_health is a status read; run_burst returns a run report).
_COMPOSITE = {"matchup_preview", "system_health", "run_burst"}
# ponytail: drive-letter absolute path (C:\ or C:/) is the clone-portability
# landmine we scan for. Repo-relative strings ("data/cache/...") never match.
# Ceiling: catches Windows abs paths only; a POSIX "/home/..." leak would slip
# past -- extend the pattern if the server ever runs on a POSIX box.
_ABS_RE = re.compile(r"[A-Za-z]:[\\/]")


def _leaked_paths(obj: Any, out: List[str]) -> None:
    """Collect every string anywhere in the envelope that looks like a
    box-local absolute path."""
    if isinstance(obj, str):
        if _ABS_RE.search(obj):
            out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _leaked_paths(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _leaked_paths(v, out)


def _call(handler: Callable[[Dict[str, Any]], Dict[str, Any]], args: Dict[str, Any]) -> Tuple[Any, str]:
    """Invoke a handler, converting an escaping exception into a recorded
    failure (a handler that raises instead of returning an envelope is a
    fail-closed violation, not a smoke crash)."""
    try:
        return handler(args), ""
    except Exception as exc:  # noqa: BLE001 -- the contract is that this never happens
        return None, "EXCEPTION %s: %s" % (type(exc).__name__, str(exc)[:80])


def _validate(tool: str, env: Any, exc: str, must_be_closed: bool) -> Tuple[bool, str, List[str]]:
    """(passed, label, leaked_paths) for one case."""
    if exc:
        return False, exc, []
    if not isinstance(env, dict):
        return False, "envelope is not a dict (%s)" % type(env).__name__, []
    leaks: List[str] = []
    _leaked_paths(env, leaks)
    status = env.get("status")
    if status not in VALID_STATUS:
        return False, "bad status %r" % (status,), leaks
    problems: List[str] = []
    if status == "ok":
        if tool not in _COMPOSITE:
            if not env.get("source_artifact"):
                problems.append("ok w/o source_artifact")
            if not env.get("as_of"):
                problems.append("ok w/o as_of")
        if must_be_closed:
            problems.append("known-bad input returned ok (fabrication risk)")
    elif status == "no_data":
        if not any(env.get(k) for k in ("note", "reason", "source_artifact")):
            problems.append("no_data w/o reason")
    label = status if not problems else "%s (%s)" % (status, "; ".join(problems))
    return (not problems), label, leaks


def _run_burst_noop(args: Dict[str, Any]) -> Dict[str, Any]:
    """run_burst driven read-only: a step name that matches nothing runs zero
    real steps, and the report is redirected to a temp file so the real
    data/cache/analytics_verify/burst_report.json is never clobbered. Applies
    the same top-level status the MCP handler adds."""
    tmp = Path(tempfile.gettempdir()) / "mcp_smoke_burst.json"
    report = _burst.run_burst(steps=["__mcp_smoke_noop__"], skip_slow=bool(args.get("skip_slow")),
                              report_path=tmp)
    report.setdefault("status", "aborted" if report.get("aborted_reason") else "ok")
    return report


# tool -> (good_args, bad_args). bad_args exercises the fail-closed path
# (unknown entity / edge language / unsupported kind). Leaf tools must fail
# closed on bad input; composites (see _COMPOSITE) are exempt from that rule.
_NOBODY = "Zzzq Nobodyson"
_CASES: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = [
    ("ask",
     {"query": "Stephen Curry three point percentage", "sport": "nba"},
     {"query": "what is my roi edge over the market", "sport": "nba"}),
    # streaks route (via the ask resolver): a real team streak query resolves ok
    # where the calendar is present, no_data (with reason) in a bare clone; a
    # nonexistent team must fail CLOSED, never fabricate a streak.
    ("ask",
     {"query": "longest win streak for the Lakers this season", "sport": "nba"},
     {"query": "current streak for %s" % _NOBODY, "sport": "nba"}),
    ("scouting_report",
     {"sport": "nba", "player": "Stephen Curry"},
     {"sport": "nba", "player": _NOBODY}),
    ("comparables",
     {"sport": "nba", "player": "Stephen Curry"},
     {"sport": "nba", "player": _NOBODY}),
    ("matchup_preview",
     {"sport": "nba", "home": "Los Angeles Lakers", "away": "Boston Celtics"},
     {"sport": "nba", "home": "Zzz Aaa", "away": "Qqq Bbb"}),
    ("win_probability",
     {"sport": "nba", "home": "Los Angeles Lakers", "away": "Boston Celtics"},
     {"sport": "nba", "home": "Zzz Aaa", "away": "Qqq Bbb"}),
    ("injury_report",
     {"sport": "nba", "team_or_player": "Los Angeles Lakers"},
     {"sport": "nba", "team_or_player": _NOBODY}),
    ("analytics_receipts",
     {"kind": "attribution"},
     {"kind": "__bogus_kind__"}),
    ("run_burst",
     {"skip_slow": True},
     {"skip_slow": False}),
    # system_health takes no meaningful args (fixed cheap-read files); both
    # cases are identical -- it's a composite status read, never fails closed.
    ("system_health", {}, {}),
]


def _handler_for(tool: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    if tool == "run_burst":
        return _run_burst_noop  # read-only override; never the real network/disk job
    h = _tools.handler_for(tool)
    assert h is not None, "no handler registered for tool %r" % tool
    return h


def run() -> int:
    covered = {c[0] for c in _CASES}
    registered = {t["name"] for t in _tools.tool_specs()}
    missing = registered - covered
    assert not missing, "smoke does not cover registered tools: %s" % sorted(missing)

    rows: List[Tuple[str, bool, str, bool, str, bool]] = []
    all_pass = True
    for tool, good, bad in _CASES:
        handler = _handler_for(tool)
        composite = tool in _COMPOSITE
        genv, gexc = _call(handler, good)
        benv, bexc = _call(handler, bad)
        gpass, glabel, gleaks = _validate(tool, genv, gexc, must_be_closed=False)
        bpass, blabel, bleaks = _validate(tool, benv, bexc, must_be_closed=not composite)
        clone_safe = not (gleaks or bleaks)
        rows.append((tool, gpass, glabel, bpass, blabel, clone_safe))
        all_pass = all_pass and gpass and bpass and clone_safe
        if gleaks or bleaks:
            for p in (gleaks + bleaks)[:2]:
                rows.append(("  leak-> " + p[:60], gpass, "", bpass, "", clone_safe))

    print("=" * 72)
    print("CourtVision MCP smoke -- envelope contract + clone-portability")
    print("=" * 72)
    print("%-20s %-6s %-6s %-10s" % ("tool", "ok", "bad", "clone_safe"))
    print("-" * 72)
    for tool, gp, gl, bp, bl, cs in rows:
        if tool.startswith("  leak->"):
            print(tool)
            continue
        print("%-20s %-6s %-6s %-10s" % (
            tool, "PASS" if gp else "FAIL", "PASS" if bp else "FAIL",
            "PASS" if cs else "LEAK"))
    print("-" * 72)
    # detail lines for any non-trivial label (failures / interesting statuses)
    for tool, gp, gl, bp, bl, _cs in rows:
        if tool.startswith("  leak->"):
            continue
        if not gp:
            print("  %-18s ok-case  : %s" % (tool, gl))
        if not bp:
            print("  %-18s bad-case : %s" % (tool, bl))
    print("=" * 72)
    print("RESULT: %s" % ("ALL PASS" if all_pass else "FAILURES PRESENT"))
    return 0 if all_pass else 1


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="In-process MCP tool-surface smoke test.")
    ap.add_argument("--check", action="store_true",
                    help="run the smoke (identical to the default run; present for --check callers)")
    ap.parse_args(argv)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
