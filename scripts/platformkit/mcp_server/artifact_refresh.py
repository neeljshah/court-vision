"""S24: one-pass refresher for the MCP front-door artifacts.

Every tool in ``artifact_tools.py`` reads an artifact some OTHER module wrote and
nothing ever scheduled those writers, so the front door served whatever age was on
disk. This module maps each tool's artifact to its producer CALLABLE and runs them.

Supervisor-independent: it does NOT read `fleet_on`, STARTS NO DAEMON, and never
creates a scheduler task -- the ORCHESTRATOR arms ``SCHTASKS``.

Artifact paths are IMPORTED from artifact_tools, never re-declared. A failing
producer is a FAILED row, one past PRODUCER_TIMEOUT_SEC a TIMEOUT row (S66); either
way the rest of the pass runs.

S57 adds ``data/intelligence`` behind ``--intelligence`` (opt-in: the hourly pass
must not start 95 batch builders); its map lives in ``intelligence_producers``. A
producer that exists but may not run -- gated tree, absent script, out of scope --
is a NO_RUN row naming its reason, never a silent skip. S77: the wall cap has ONE
owner (``intelligence_producers``), is exposed as ``--timeout-sec``, and a timeout
KILLS the child instead of abandoning it.

    python -m scripts.platformkit.mcp_server.artifact_refresh --once [--timeout-sec N]
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence

from scripts.platformkit.mcp_server import artifact_tools
from scripts.platformkit.mcp_server.intelligence_producers import PRODUCER_TIMEOUT_S

ROOT = artifact_tools._ROOT
OUT_DIR_REL = "data/cache/mcp_server"
# S66 set this to 120.0 here while intelligence_producers carried its own 900.0;
# four of the five walls S69 MEASURED (77-275 s) sat above 120, so the CLI reported
# 5 TIMEOUT / 0 advanced for producers that all completed. S77: ONE owner, the
# value beside those walls; this name stays an alias (B2).
PRODUCER_TIMEOUT_SEC = PRODUCER_TIMEOUT_S
HEARTBEAT_NAME = "artifact_refresh_heartbeat.jsonl"
STATUS_NAME = "artifact_refresh_status.json"

# The orchestrator arms this; this module NEVER runs it.
SCHTASKS = ('schtasks /Create /SC HOURLY /TN CourtVision-ArtifactRefresh '
            '/TR "<python> -m scripts.platformkit.mcp_server.artifact_refresh --once"')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- producers: each adapter takes the repo root and writes the FIRST path its
# MCP tool reads. Imports are lazy: a missing dep is a FAILED row, not a dead pass.

def _run_atlas(root: Path) -> None:
    from scripts.platformkit.analytics_showcase import market_strength_atlas as m
    _write(root / m.OUT_RELATIVE_PATH, m.build(root))


def _run_mechanism(root: Path) -> None:
    from scripts.platformkit.analytics_showcase import mechanism_exposure as m
    _write(root / artifact_tools._MECHANISM[0], m.build(root))


def _run_harness_health(root: Path) -> None:
    from scripts.platformkit.eval_gate import harness_health_report as m
    m.build(out_path=str(root / artifact_tools._HEALTH[0]), root=root)


def _run_execution(root: Path) -> None:
    # ponytail: the ledger is a fixed repo artifact; --root steers only the OUTPUT.
    from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
    from scripts.platformkit.pm_trading import clv_daily_readout as m
    m.write_readout(Path(DEFAULT_LEDGER), root / artifact_tools._EXECUTION[0],
                    root / OUT_DIR_REL / "execution_status_rows.md", now_iso=_now())


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="ascii")


class Target(NamedTuple):
    """One MCP tool, the artifact paths IT reads, and the producer that writes them.

    ``no_run_reason`` (S57) separates "exists but may not run here" (NO_RUN --
    gated tree, absent script, out of scope) from "nothing writes this at all"
    (NO_PRODUCER). Defaulted: every pre-existing Target is unchanged.
    """
    name: str
    rels: Sequence[str]
    producer: Optional[Callable[[Path], None]]
    no_run_reason: Optional[str] = None


TARGETS: Sequence[Target] = (
    Target("strength_atlas", (artifact_tools._ATLAS,), _run_atlas),
    Target("mechanism_exposure", artifact_tools._MECHANISM, _run_mechanism),
    Target("harness_health", artifact_tools._HEALTH, _run_harness_health),
    Target("execution_status", artifact_tools._EXECUTION, _run_execution),
    # tracking_program_status globs two trees -- no artifact, no producer: NO_PRODUCER.
    Target("tracking_program_status", (), None),
)


def _probe(root: Path, rels: Sequence[str]) -> Dict[str, Any]:
    """Freshness of the first readable artifact, exactly as the MCP tool resolves it.

    `stamp` prefers ``generated_at`` because some artifacts declare a descriptive
    `as_of` that is not a freshness stamp; `as_of` is carried alongside, never lost.
    """
    loaded = artifact_tools._load(root, rels) if rels else None
    if loaded is None:
        # S57: parquet/pkl/png cannot be parsed by _load, but a PRESENT artifact
        # still has a write time; without it a rebuild never shows as advanced.
        for rel in rels:
            path = root / rel
            if path.is_file() and path.suffix not in (".json", ".jsonl"):
                stat = path.stat()
                stamp = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                return {"source_artifact": rel.replace("\\", "/"),
                        "stamp": "mtime:" + stamp, "as_of": None, "bytes": stat.st_size}
        return {"source_artifact": None, "stamp": None, "as_of": None, "bytes": None}
    path, rel, value = loaded
    generated = value.get("generated_at") if isinstance(value, dict) else None
    as_of = artifact_tools._as_of(path, value)
    return {"source_artifact": rel, "stamp": str(generated) if generated else as_of,
            "as_of": as_of, "bytes": path.stat().st_size}


def _run_producer(producer: Callable[[Path], None], root: Path,
                  timeout_sec: float) -> tuple:
    """Run one producer under a wall cap. Returns (rc, error, timed_out).

    S77: a producer that shells out publishes its child as ``.proc`` and reads its
    cap from ``.timeout_sec``, so this cap is the ONLY number and a TIMEOUT cannot
    leave a writer running. Ceiling: an IN-PROCESS producer has no child to kill,
    so its daemon thread is still abandoned."""
    if hasattr(producer, "timeout_sec"):
        producer.timeout_sec = timeout_sec   # one owner, propagated to the child
    box: Dict[str, Optional[str]] = {}
    def target() -> None:
        try:
            producer(root)
        except Exception:
            box["error"] = traceback.format_exc().strip().splitlines()[-1][:300]
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_sec)
    if thread.is_alive():
        proc = getattr(producer, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.kill()
            thread.join(30.0)
        return 1, "producer exceeded {0:.0f}s wall cap".format(timeout_sec), True
    return (1, box["error"], False) if box.get("error") else (0, None, False)


def _refresh_target(root: Path, target: Target,
                    timeout_sec: float = PRODUCER_TIMEOUT_SEC) -> Dict[str, Any]:
    before = _probe(root, target.rels)
    row: Dict[str, Any] = {"name": target.name, "stamp_before": before["stamp"],
                           "as_of_before": before["as_of"]}
    if target.no_run_reason is not None:
        # NEVER a silent skip: the reason is on the row and in the pass counts.
        row.update({"status": "NO_RUN", "rc": None, "advanced": False,
                    "source_artifact": before["source_artifact"],
                    "stamp_after": before["stamp"], "as_of": before["as_of"],
                    "generated_at": before["stamp"], "bytes": before["bytes"],
                    "error": target.no_run_reason})
        return row
    if target.producer is None:
        row.update({"status": "NO_PRODUCER", "rc": None, "advanced": False,
                    "source_artifact": before["source_artifact"],
                    "stamp_after": before["stamp"], "as_of": before["as_of"],
                    "generated_at": before["stamp"], "bytes": before["bytes"],
                    "error": "no producer module writes this artifact"})
        return row
    # never raises out: one bad or HUNG producer must not kill the pass
    rc, error, timed_out = _run_producer(target.producer, root, timeout_sec)
    after = _probe(root, target.rels)
    advanced = bool(rc == 0 and after["stamp"] and after["stamp"] != before["stamp"])
    if timed_out:
        status = "TIMEOUT"
    elif rc:
        status = "FAILED"
    elif advanced:
        status = "ok"
    elif after["stamp"]:
        status = "STALE"
    else:
        status = "NO_ARTIFACT"
    row.update({"status": status, "rc": rc, "advanced": advanced, "error": error,
                "source_artifact": after["source_artifact"], "stamp_after": after["stamp"],
                "generated_at": after["stamp"], "as_of": after["as_of"],
                "bytes": after["bytes"]})
    return row


def refresh_once(root: Path | str = ROOT, out_dir: Path | str | None = None,
                 targets: Sequence[Target] = TARGETS,
                 timeout_sec: float = PRODUCER_TIMEOUT_SEC) -> Dict[str, Any]:
    """Run every producer once, append ONE heartbeat line, rewrite status.json."""
    root = Path(root)
    out = Path(out_dir) if out_dir else root / OUT_DIR_REL
    started = _now()
    rows: List[Dict[str, Any]] = [_refresh_target(root, t, timeout_sec) for t in targets]
    record = {
        "started_at": started, "finished_at": _now(),
        "n_targets": len(rows),
        "n_advanced": sum(row["advanced"] for row in rows),
        "n_failed": sum(row["status"] == "FAILED" for row in rows),
        "n_timeout": sum(row["status"] == "TIMEOUT" for row in rows),
        "n_no_producer": sum(row["status"] == "NO_PRODUCER" for row in rows),
        "n_no_run": sum(row["status"] == "NO_RUN" for row in rows),
        "n_stale": sum(row["status"] in ("STALE", "NO_ARTIFACT") for row in rows),
        "targets": rows,
    }
    out.mkdir(parents=True, exist_ok=True)
    with (out / HEARTBEAT_NAME).open("a", encoding="ascii") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")
    (out / STATUS_NAME).write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="ascii")
    return record


def _select(names: Optional[str], pool: Sequence[Target] = TARGETS) -> Sequence[Target]:
    if not names:
        return pool
    wanted = [part.strip() for part in names.split(",") if part.strip()]
    chosen = [t for t in pool if t.name in wanted]
    unknown = sorted(set(wanted) - {t.name for t in chosen})
    if unknown:
        raise SystemExit("unknown target(s): " + ", ".join(unknown))
    return chosen


def _pool(root: Path, intelligence: bool, scope: str) -> Sequence[Target]:
    """S57: the intelligence targets are OPT-IN -- the hourly front-door pass must
    not start 95 batch builders, so --intelligence is what adds them."""
    if not intelligence:
        return TARGETS
    from scripts.platformkit.mcp_server import intelligence_producers as ip
    return tuple(TARGETS) + tuple(ip.targets(root, scope))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="refresh the MCP front-door artifacts")
    ap.add_argument("--once", action="store_true", help="run one pass and exit")
    ap.add_argument("--loop", action="store_true",
                    help="repeat every --interval seconds (the m51 ProcSpec mode)")
    ap.add_argument("--interval", type=float, default=3600.0, help="--loop period, seconds")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--targets", default=None, help="comma-separated target names")
    ap.add_argument("--intelligence", action="store_true",
                    help="also carry the data/intelligence producers (S57, opt-in)")
    ap.add_argument("--scope", default="rebuilt", choices=("rebuilt", "all"),
                    help="rebuilt (default): only producers whose input is newer "
                         "than the artifact may run; the rest are NO_RUN by reason")
    ap.add_argument("--timeout-sec", type=float, default=PRODUCER_TIMEOUT_SEC,
                    help="per-producer wall cap, seconds (default %(default)s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan (name, status, artifacts) and run nothing")
    args = ap.parse_args(argv)
    if not (args.once or args.loop or args.dry_run):
        ap.error("pass --once (or --loop for the cadence mode, or --dry-run)")
    targets = _select(args.targets, _pool(Path(args.root), args.intelligence, args.scope))
    if args.dry_run:
        runnable = sum(1 for t in targets if t.producer is not None)
        print("dry run -- {0} target(s), {1} runnable, {2} artifact path(s)".format(
            len(targets), runnable, sum(len(t.rels) for t in targets)))
        for t in targets:
            state = ("RUN" if t.producer is not None
                     else ("NO_RUN " + (t.no_run_reason or "") if t.no_run_reason
                           else "NO_PRODUCER"))
            print("  {0:<40} {1}".format(t.name, state[:120]))
        return 0
    while True:
        record = refresh_once(args.root, args.out_dir, targets, args.timeout_sec)
        print("artifact refresh -- {0} target(s), {1} advanced, {2} failed, {3} timeout,"
              " {4} no_producer, {5} no_run".format(
                  record["n_targets"], record["n_advanced"], record["n_failed"],
                  record["n_timeout"], record["n_no_producer"], record["n_no_run"]))
        for row in record["targets"]:
            print("  {0:<24} {1:<12} {2} -> {3}".format(
                row["name"], row["status"], row["stamp_before"], row["stamp_after"]))
        if not args.loop:
            return 0
        # ponytail: one global cadence. A target needing its own period gets a
        # second scheduler entry with --targets, not a scheduler in here.
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
