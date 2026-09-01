"""Create a local-only, ASCII morning rollup for overnight tracking work."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


DEFAULT_TRACKING = Path("data/tracking/track_daemon_ledger.jsonl")
DEFAULT_BRIDGE = Path("data/tracking/footage_bridge_ledger.jsonl")
DEFAULT_SUPERVISOR = Path("data/tracking/bridge_supervisor_status.json")
DEFAULT_OUT = Path("logs/night_report.txt")


def _ascii(value: Any) -> str:
    """Return a printable ASCII representation of a local ledger value."""
    return str(value).encode("ascii", "replace").decode("ascii")


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.is_file():
        return [], "no data (file missing)"
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    except OSError:
        return [], "no data (file unreadable)"
    if not records:
        return [], "no data (empty or malformed)"
    return records, None


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "no data (file missing)"
    try:
        item = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None, "no data (unreadable or malformed)"
    if not isinstance(item, dict):
        return None, "no data (malformed)"
    return item, None


def _sport(record: dict[str, Any]) -> str:
    return _ascii(record.get("sport") or "unknown")


def _top(counter: Counter[str], limit: int = 3) -> str:
    if not counter:
        return "none"
    return ", ".join(
        "%s (%d)" % (_ascii(text), count)
        for text, count in sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    )


def _number(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coordinate_contract_items(records: Iterable[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for record in records:
        failures = record.get("failures")
        if not isinstance(failures, list):
            continue
        matched = [str(item) for item in failures if "coordinate_contract" in str(item).lower()]
        if matched:
            game_id = _ascii(record.get("game_id") or "unknown-game")
            items.append("coordinate_contract: %s (%s)" % (game_id, "; ".join(_ascii(x) for x in matched)))
    return sorted(items)


def build_report(
    tracking_path: Path = DEFAULT_TRACKING,
    bridge_path: Path = DEFAULT_BRIDGE,
    supervisor_path: Path = DEFAULT_SUPERVISOR,
) -> str:
    """Build the morning report from the three local tracking status files."""
    tracking, tracking_problem = _read_jsonl(tracking_path)
    bridge, bridge_problem = _read_jsonl(bridge_path)
    supervisor, supervisor_problem = _read_json(supervisor_path)
    sports = sorted({_sport(item) for item in tracking + bridge})

    tracked: dict[str, int] = defaultdict(int)
    thin: dict[str, int] = defaultdict(int)
    passing: dict[str, int] = defaultdict(int)
    best_rows: dict[str, int] = defaultdict(int)
    failures: dict[str, Counter[str]] = defaultdict(Counter)
    for item in tracking:
        sport = _sport(item)
        if item.get("status") == "tracked":
            tracked[sport] += 1
        elif item.get("status") == "thin":
            thin[sport] += 1
        if item.get("passed") is True:
            passing[sport] += 1
        best_rows[sport] = max(best_rows[sport], _number(item.get("rows")))
        if isinstance(item.get("failures"), list):
            failures[sport].update(_ascii(reason) for reason in item["failures"])

    staged: dict[str, int] = defaultdict(int)
    bridge_failed: dict[str, int] = defaultdict(int)
    bridge_failures: dict[str, Counter[str]] = defaultdict(Counter)
    for item in bridge:
        sport = _sport(item)
        status = _ascii(item.get("status") or "").strip()
        lowered = status.lower()
        if lowered.startswith("staged"):
            staged[sport] += 1
        if lowered.startswith("failed"):
            bridge_failed[sport] += 1
            text = status.split(":", 1)[1].strip() if ":" in status else status
            bridge_failures[sport][text] += 1

    lanes: dict[str, Any] = {}
    if supervisor is not None and isinstance(supervisor.get("lanes"), dict):
        lanes = supervisor["lanes"]
    alive_lanes = sorted(_ascii(name) for name, lane in lanes.items()
                         if isinstance(lane, dict) and lane.get("alive") is True)
    stopped_lanes = sorted(_ascii(name) for name, lane in lanes.items()
                           if not isinstance(lane, dict) or lane.get("alive") is not True)
    queue_depth = sum(_number(lane.get("untracked")) for lane in lanes.values()
                      if isinstance(lane, dict))

    human: list[str] = []
    human.extend("lane not alive: %s" % name for name in stopped_lanes)
    human.extend("zero passing games: %s" % sport for sport in sports if passing[sport] == 0)
    human.extend(_coordinate_contract_items(tracking))

    lines = [
        "NIGHT REPORT",
        "============",
        "HEADLINE: %d games PASSING the harness." % sum(passing.values()),
        "IMPORTANT: row count is secondary. >=500 rows does NOT mean a game PASSES the harness.",
        "",
        "WHAT NEEDS A HUMAN",
        "-------------------",
    ]
    lines.extend("- " + item for item in human) if human else lines.append("- None.")
    lines.extend(["", "TRACKING HARNESS"])
    if tracking_problem:
        lines.append(tracking_problem)
    else:
        for sport in sports:
            lines.append(
                "%s: tracked=%d thin=%d PASSING=%d best_rows=%d failures=%s"
                % (sport, tracked[sport], thin[sport], passing[sport], best_rows[sport], _top(failures[sport]))
            )
    lines.extend(["", "FOOTAGE BRIDGE"])
    if bridge_problem:
        lines.append(bridge_problem)
    else:
        for sport in sorted({_sport(item) for item in bridge}):
            lines.append("%s: staged=%d failed=%d top_failures=%s" % (
                sport, staged[sport], bridge_failed[sport], _top(bridge_failures[sport])
            ))
    lines.extend(["", "BRIDGE SUPERVISOR"])
    if supervisor_problem:
        lines.append(supervisor_problem)
    else:
        tracked_games = _number(supervisor.get("tracked_games"))
        lines.append("tracked_games=%d alive_lanes=%s total_queue_depth=%d" % (
            tracked_games, ", ".join(alive_lanes) if alive_lanes else "none", queue_depth
        ))
    return "\n".join(lines) + "\n"


def main() -> int:
    """Print and write the local morning report."""
    parser = argparse.ArgumentParser(description="Write an ASCII overnight tracking report.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    report = build_report()
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="ascii", errors="replace")
    except OSError as error:
        print("Could not write report: %s" % _ascii(error))
        print(report, end="")
        return 1
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
