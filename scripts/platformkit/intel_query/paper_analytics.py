"""ask-style natural-language surface over PAPER TRADING performance --
NOT the VERIFIED-claims surface in ask.py (that answers from validated
intelligence claims; this answers from the live paper ledger, a different
kind of source that is never "validated" the same way, only fresh-read).

Every answer dict carries source file paths + edge_claimed: false, and any
net_units number is always paired with its channel's greenlight verdict
(RED/AMBER/GREEN) from data/frontend/ops/edge_greenlight.json so a positive
units figure is never shown without its fail-closed gate status alongside it.

Streams clv_ledger.jsonl line-by-line (never json.load's the whole file --
the ledger is large and growing; same pattern as the claims streaming
validator: one bad line is skipped, not fatal).

CLI:
    python -m scripts.platformkit.intel_query.paper_analytics "this week by channel"
    python -m scripts.platformkit.intel_query.paper_analytics "today"
    python -m scripts.platformkit.intel_query.paper_analytics "arb lane"
    python -m scripts.platformkit.intel_query.paper_analytics "settlement backlog"
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = REPO_ROOT / "data" / "frontend" / "clv_ledger.jsonl"
GREENLIGHT_PATH = REPO_ROOT / "data" / "frontend" / "ops" / "edge_greenlight.json"

_GROUP_FIELDS = {
    "channel": "channel",
    "venue": "taken_book",
    "sport": "sport",
    "market_type": "market_type",
}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _iter_ledger(path: Path = LEDGER_PATH) -> Iterator[dict[str, Any]]:
    """Line-at-a-time generator -- never holds the whole file in memory.
    One malformed line is skipped, matching load_verified_claims' per-line
    fail-open behavior in ask.py."""
    if not path.exists():
        return
    with open(path, "r", encoding="ascii", errors="strict") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue


def _parse_ts(row: dict[str, Any], field: str = "ts") -> datetime | None:
    raw = row.get(field)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_greenlight(path: Path | None = None) -> dict[str, Any]:
    # path=None (not a def-time Path=GREENLIGHT_PATH default) so a caller
    # (or test) that monkeypatches the module-level GREENLIGHT_PATH is
    # honored at CALL time, not baked in at import time.
    path = path if path is not None else GREENLIGHT_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="ascii", errors="strict") as f:
            return json.load(f).get("channels", {})
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}


def _greenlight_status(channel: str, channels: dict[str, Any]) -> str:
    """RED/AMBER/GREEN for a given channel key, or 'unknown' if the
    greenlight gate has no verdict for it (fail-closed default: never
    claim GREEN when the gate is silent)."""
    entry = channels.get(channel)
    if not entry:
        return "unknown"
    return entry.get("status", "unknown")


def _bucket(row: dict[str, Any]) -> dict[str, Any]:
    """One row's contribution: (outcome, unit_result) for settled bets."""
    return {
        "settled": row.get("status") == "settled",
        "outcome": row.get("outcome"),
        "unit_result": row.get("unit_result"),
    }


def summary(
    window_days: int | None = None,
    group_by: str | None = None,
    ledger_path: Path = LEDGER_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    """{n_settled, w/l/push, net_units, n_open} overall or grouped by
    channel|venue|sport|market_type. window_days=None means all-time.
    group_by=None returns one flat totals dict under "overall"."""
    if group_by is not None and group_by not in _GROUP_FIELDS:
        raise ValueError(f"group_by must be one of {sorted(_GROUP_FIELDS)} or None, got {group_by!r}")
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days) if window_days is not None else None
    field = _GROUP_FIELDS.get(group_by) if group_by else None

    groups: dict[Any, dict[str, Any]] = defaultdict(
        lambda: {"n_settled": 0, "n_win": 0, "n_loss": 0, "n_push": 0, "net_units": 0.0, "n_open": 0}
    )
    n_rows = 0
    for row in _iter_ledger(ledger_path):
        ts = _parse_ts(row)
        if cutoff is not None and (ts is None or ts < cutoff):
            continue
        n_rows += 1
        key = row.get(field) if field else "overall"
        g = groups[key]
        if row.get("status") == "settled":
            g["n_settled"] += 1
            outcome = row.get("outcome")
            if outcome == "win":
                g["n_win"] += 1
            elif outcome == "loss":
                g["n_loss"] += 1
            elif outcome == "push":
                g["n_push"] += 1
            g["net_units"] += float(row.get("unit_result") or 0.0)
        elif row.get("status") == "open":
            g["n_open"] += 1

    greenlight = _load_greenlight()
    result_groups = {}
    for key, g in groups.items():
        g = dict(g)
        g["net_units"] = round(g["net_units"], 4)
        if field == "channel":
            g["greenlight_status"] = _greenlight_status(str(key), greenlight)
        result_groups[key] = g

    return {
        "answerable": True,
        "edge_claimed": False,
        "window_days": window_days,
        "group_by": group_by,
        "n_rows_considered": n_rows,
        "groups": result_groups,
        "source_files": [_display_path(ledger_path), _display_path(GREENLIGHT_PATH)],
        "note": "net_units is a units count, not a dollar figure; a positive value carries no "
                "claim of edge without its channel's greenlight status (RED/AMBER/GREEN).",
    }


def today(ledger_path: Path = LEDGER_PATH, now: datetime | None = None) -> dict[str, Any]:
    return summary(window_days=1, group_by="channel", ledger_path=ledger_path, now=now)


def this_week(ledger_path: Path = LEDGER_PATH, now: datetime | None = None) -> dict[str, Any]:
    return summary(window_days=7, group_by="channel", ledger_path=ledger_path, now=now)


def arb_lane_summary(
    window_days: int | None = None, ledger_path: Path = LEDGER_PATH, now: datetime | None = None
) -> dict[str, Any]:
    """Rows tagged market_type == 'arb' only -- same shape as summary()'s
    overall totals, scoped to the arb lane."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days) if window_days is not None else None
    g = {"n_settled": 0, "n_win": 0, "n_loss": 0, "n_push": 0, "net_units": 0.0, "n_open": 0}
    n_rows = 0
    for row in _iter_ledger(ledger_path):
        if row.get("market_type") != "arb":
            continue
        ts = _parse_ts(row)
        if cutoff is not None and (ts is None or ts < cutoff):
            continue
        n_rows += 1
        if row.get("status") == "settled":
            g["n_settled"] += 1
            outcome = row.get("outcome")
            if outcome == "win":
                g["n_win"] += 1
            elif outcome == "loss":
                g["n_loss"] += 1
            elif outcome == "push":
                g["n_push"] += 1
            g["net_units"] += float(row.get("unit_result") or 0.0)
        elif row.get("status") == "open":
            g["n_open"] += 1
    g["net_units"] = round(g["net_units"], 4)
    return {
        "answerable": True,
        "edge_claimed": False,
        "window_days": window_days,
        "n_rows_considered": n_rows,
        "arb": g,
        "source_files": [_display_path(ledger_path)],
        "note": "arb lane = market_type=='arb' rows only; net_units is a units count, not a dollar figure.",
    }


_AGE_BUCKETS = ((1, "under_1d"), (3, "1_to_3d"), (7, "3_to_7d"), (float("inf"), "over_7d"))


def settlement_backlog(ledger_path: Path = LEDGER_PATH, now: datetime | None = None) -> dict[str, Any]:
    """Open (unsettled) bet counts by age bucket -- how stale is the open book."""
    now = now or datetime.now(timezone.utc)
    buckets: dict[str, int] = {label: 0 for _, label in _AGE_BUCKETS}
    n_open = 0
    n_open_no_ts = 0
    for row in _iter_ledger(ledger_path):
        if row.get("status") != "open":
            continue
        n_open += 1
        ts = _parse_ts(row)
        if ts is None:
            n_open_no_ts += 1
            continue
        age_days = (now - ts).total_seconds() / 86400.0
        for limit, label in _AGE_BUCKETS:
            if age_days < limit:
                buckets[label] += 1
                break
    return {
        "answerable": True,
        "edge_claimed": False,
        "n_open": n_open,
        "n_open_missing_timestamp": n_open_no_ts,
        "age_buckets": buckets,
        "source_files": [_display_path(ledger_path)],
        "note": "age bucket = now - ts (bet-placed time), for OPEN rows only.",
    }


# ---------------------------------------------------------------------------
# Tiny keyword router -- not the ask.py claims-family dispatch (this answers
# from the live ledger, a different source kind). "today"/"this week" pick
# the matching convenience; "arb" routes to arb_lane_summary; "backlog"
# routes to settlement_backlog; group_by is sniffed from "by <field>";
# anything else falls back to all-time summary(group_by="channel").
# ---------------------------------------------------------------------------
def ask_paper(question: str) -> dict[str, Any]:
    q = (question or "").lower()
    if "backlog" in q:
        return settlement_backlog()
    if "arb" in q:
        window = 7 if "week" in q else (1 if "today" in q else None)
        return arb_lane_summary(window_days=window)
    group_by = None
    for name in _GROUP_FIELDS:
        if f"by {name}" in q or name in q:
            group_by = name
            break
    if group_by is None and "fill quality" in q:
        group_by = "venue"
    if "today" in q:
        return summary(window_days=1, group_by=group_by or "channel")
    if "this week" in q or "past week" in q or "last 7" in q:
        return summary(window_days=7, group_by=group_by or "channel")
    if "this month" in q or "last 30" in q:
        return summary(window_days=30, group_by=group_by or "channel")
    return summary(window_days=None, group_by=group_by or "channel")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ask-anything over PAPER TRADING performance")
    parser.add_argument("question", nargs="?", default="this week by channel")
    args = parser.parse_args(argv)
    result = ask_paper(args.question)
    print(f"Q: {args.question}")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
