"""S24: one-pass refresher for the MCP front-door artifacts.

Every tool in ``artifact_tools.py`` reads an artifact that some OTHER module
wrote; nothing ever scheduled those writers, so the MCP front door served
whatever age happened to be on disk (`fleet_on` is false by design for the
resident server). This module maps each tool's artifact to its producer
CALLABLE and runs them in one pass.

Supervisor-independent: it does NOT read `fleet_on`, does NOT depend on the
fleet, and STARTS NO DAEMON. `--once` runs one pass and exits; the cadence
belongs to the OS scheduler, which the ORCHESTRATOR arms with the line in
``SCHTASKS`` -- this module never creates a task. `--loop` is provided for a
supervisor ProcSpec but is never run by the landing lane.

Artifact paths are IMPORTED from artifact_tools, never re-declared here.
One failing producer is recorded as a FAILED row; the rest of the pass runs.

    python -m scripts.platformkit.mcp_server.artifact_refresh --once
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence

from scripts.platformkit.mcp_server import artifact_tools

ROOT = artifact_tools._ROOT
OUT_DIR_REL = "data/cache/mcp_server"
HEARTBEAT_NAME = "artifact_refresh_heartbeat.jsonl"
STATUS_NAME = "artifact_refresh_status.json"

# The orchestrator arms this; this module NEVER runs it.
SCHTASKS = ('schtasks /Create /SC HOURLY /TN CourtVision-ArtifactRefresh '
            '/TR "<python> -m scripts.platformkit.mcp_server.artifact_refresh --once"')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- producers -------------------------------------------------------------
# Each adapter takes the repo root and writes the FIRST path its MCP tool reads.
# Imports are lazy so a heavy or missing dependency is a FAILED row, not an
# import error that kills the whole pass.

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
    # ponytail: the paper ledger is a fixed repo artifact, so the producer reads
    # DEFAULT_LEDGER as-is; --root steers only the OUTPUT.
    from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
    from scripts.platformkit.pm_trading import clv_daily_readout as m
    m.write_readout(Path(DEFAULT_LEDGER), root / artifact_tools._EXECUTION[0],
                    root / OUT_DIR_REL / "execution_status_rows.md", now_iso=_now())


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="ascii")


class Target(NamedTuple):
    """One MCP tool, the artifact paths IT reads, and the producer that writes them."""
    name: str
    rels: Sequence[str]
    producer: Optional[Callable[[Path], None]]


TARGETS: Sequence[Target] = (
    Target("strength_atlas", (artifact_tools._ATLAS,), _run_atlas),
    Target("mechanism_exposure", artifact_tools._MECHANISM, _run_mechanism),
    Target("harness_health", artifact_tools._HEALTH, _run_harness_health),
    Target("execution_status", artifact_tools._EXECUTION, _run_execution),
    # tracking_program_status derives itself from a glob over docs/evidence/tracking
    # and data/tracking_reports -- no single artifact, no producer. Recorded
    # NO_PRODUCER honestly; never invented, never counted as advanced.
    Target("tracking_program_status", (), None),
)


def _probe(root: Path, rels: Sequence[str]) -> Dict[str, Any]:
    """Freshness of the first readable artifact, exactly as the MCP tool resolves it.

    `stamp` prefers ``generated_at`` (the producer's own write time) because some
    artifacts declare a descriptive `as_of` that is not a freshness stamp at all
    (market_strength_atlas: "latest accepted game date per sport"). `as_of` is the
    value the MCP tool itself reports and is carried alongside, never replaced.
    """
    loaded = artifact_tools._load(root, rels) if rels else None
    if loaded is None:
        return {"source_artifact": None, "stamp": None, "as_of": None, "bytes": None}
    path, rel, value = loaded
    generated = value.get("generated_at") if isinstance(value, dict) else None
    as_of = artifact_tools._as_of(path, value)
    return {"source_artifact": rel, "stamp": str(generated) if generated else as_of,
            "as_of": as_of, "bytes": path.stat().st_size}


def _refresh_target(root: Path, target: Target) -> Dict[str, Any]:
    before = _probe(root, target.rels)
    row: Dict[str, Any] = {"name": target.name, "stamp_before": before["stamp"],
                           "as_of_before": before["as_of"]}
    if target.producer is None:
        row.update({"status": "NO_PRODUCER", "rc": None, "advanced": False,
                    "source_artifact": before["source_artifact"],
                    "stamp_after": before["stamp"], "as_of": before["as_of"],
                    "generated_at": before["stamp"], "bytes": before["bytes"],
                    "error": "no producer module writes this artifact"})
        return row
    rc, error = 0, None
    try:
        target.producer(root)
    except Exception:  # never raises out: one bad producer must not kill the pass
        rc, error = 1, traceback.format_exc().strip().splitlines()[-1][:300]
    after = _probe(root, target.rels)
    advanced = bool(rc == 0 and after["stamp"] and after["stamp"] != before["stamp"])
    if rc:
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
                 targets: Sequence[Target] = TARGETS) -> Dict[str, Any]:
    """Run every producer once, append ONE heartbeat line, rewrite status.json."""
    root = Path(root)
    out = Path(out_dir) if out_dir else root / OUT_DIR_REL
    started = _now()
    rows: List[Dict[str, Any]] = [_refresh_target(root, target) for target in targets]
    record = {
        "started_at": started, "finished_at": _now(),
        "n_targets": len(rows),
        "n_advanced": sum(row["advanced"] for row in rows),
        "n_failed": sum(row["status"] == "FAILED" for row in rows),
        "n_no_producer": sum(row["status"] == "NO_PRODUCER" for row in rows),
        "n_stale": sum(row["status"] in ("STALE", "NO_ARTIFACT") for row in rows),
        "targets": rows,
    }
    out.mkdir(parents=True, exist_ok=True)
    with (out / HEARTBEAT_NAME).open("a", encoding="ascii") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")
    (out / STATUS_NAME).write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="ascii")
    return record


def _select(names: Optional[str]) -> Sequence[Target]:
    if not names:
        return TARGETS
    wanted = [part.strip() for part in names.split(",") if part.strip()]
    chosen = [t for t in TARGETS if t.name in wanted]
    unknown = sorted(set(wanted) - {t.name for t in chosen})
    if unknown:
        raise SystemExit("unknown target(s): " + ", ".join(unknown))
    return chosen


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="refresh the MCP front-door artifacts")
    ap.add_argument("--once", action="store_true", help="run one pass and exit")
    ap.add_argument("--loop", action="store_true",
                    help="repeat every --interval seconds (for a supervisor ProcSpec; "
                         "prefer the OS scheduler line in SCHTASKS)")
    ap.add_argument("--interval", type=float, default=3600.0, help="--loop period, seconds")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--targets", default=None, help="comma-separated target names")
    args = ap.parse_args(argv)
    if not (args.once or args.loop):
        ap.error("pass --once (or --loop for the cadence mode)")
    targets = _select(args.targets)
    while True:
        record = refresh_once(args.root, args.out_dir, targets)
        print("artifact refresh -- {0} target(s), {1} advanced, {2} failed, {3} no_producer".format(
            record["n_targets"], record["n_advanced"], record["n_failed"], record["n_no_producer"]))
        for row in record["targets"]:
            print("  {0:<24} {1:<12} {2} -> {3}".format(
                row["name"], row["status"], row["stamp_before"], row["stamp_after"]))
        if not args.loop:
            return 0
        # ponytail: one global hourly cadence. If a target needs its own period,
        # give it a second scheduler entry with --targets rather than a scheduler here.
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
