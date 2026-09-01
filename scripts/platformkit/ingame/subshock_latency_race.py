"""Measurement-only audit for the NBA sub-shock latency race.

Inputs are local, append-only artifacts only.  The event manifest is JSONL and
must contain: game_id, player, detect_ts, timestamp_basis, source_path, and
impact_on_home (-1 for a home-player loss, +1 for an away-player loss).  It is
an auditable handoff from the PBP/stint shock assembler: this module rejects
reconstructed clocks and does not infer a wall-clock timestamp from game clock.

The quote source is data/cache/line_history/nba/<date>.jsonl.  For each event,
the baseline is the last home-side quote in the same book and market at or
before detect_ts - 15 minutes.  Reprice time is the first later quote in the
window whose signed movement reaches 0.03 probability or 1.0 home spread point.
Files are opened one at a time; no scraper, model, or production path is used.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REPO = Path(__file__).resolve().parents[3]
DEFAULT_EVENTS = REPO / "data" / "cache" / "team_system" / "subshock_events.jsonl"
DEFAULT_LINES = REPO / "data" / "cache" / "line_history" / "nba"
DEFAULT_RESULTS = Path(__file__).with_name("subshock_latency_race_results.md")
WINDOW = timedelta(minutes=15)
PROB_MOVE = 0.03
SPREAD_MOVE = 1.0
MIN_EVENTS = 30
PASS_SHARE = 0.60


def parse_ts(value: Any) -> Optional[datetime]:
    """Parse an explicit source timestamp as UTC; naive strings are rejected."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        ts = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts.astimezone(timezone.utc) if ts.tzinfo else None


def load_events(path: Path) -> list[dict[str, Any]]:
    """Read a local PBP/stint event manifest sequentially, skipping bad JSON."""
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _valid_event(event: dict[str, Any]) -> tuple[Optional[datetime], Optional[str]]:
    ts = parse_ts(event.get("detect_ts"))
    basis = str(event.get("timestamp_basis") or "").lower()
    required = ("game_id", "player", "source_path", "impact_on_home")
    if any(event.get(k) in (None, "") for k in required):
        return None, "missing_required_event_field"
    if ts is None or "ingest" not in basis or not ("pbp" in basis or "stint" in basis):
        return None, "missing_data_native_pbp_or_stint_timestamp"
    try:
        direction = float(event["impact_on_home"])
    except (TypeError, ValueError):
        return None, "invalid_impact_on_home"
    return (ts, None) if direction in (-1.0, 1.0) else (None, "invalid_impact_on_home")


def _event_date(event: dict[str, Any], detect_ts: datetime) -> str:
    value = event.get("line_history_date")
    return str(value) if value else detect_ts.date().isoformat()


def _quote_value(row: dict[str, Any]) -> Optional[tuple[str, str, float]]:
    """Return (market, book, value) for an explicitly home-side quote only."""
    if str(row.get("side") or "").lower() != "home":
        return None
    market = str(row.get("market_type") or "").lower()
    book = str(row.get("book") or "")
    try:
        if market == "moneyline":
            return market, book, float(row["devigged_prob"])
        if market == "spread":
            return market, book, float(row["line"])
    except (KeyError, TypeError, ValueError):
        return None
    return None


def load_game_quotes(line_dir: Path, day: str, game_id: str) -> list[tuple[datetime, str, str, float]]:
    """Load one daily file only; retain valid home paths for one game."""
    path = line_dir / (day + ".jsonl")
    quotes: list[tuple[datetime, str, str, float]] = []
    if not path.is_file():
        return quotes
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("game_id")) != str(game_id):
                continue
            ts = parse_ts(row.get("captured_at"))
            value = _quote_value(row)
            if ts is not None and value is not None:
                market, book, price = value
                quotes.append((ts, market, book, price))
    return sorted(quotes)


def find_reprice(quotes: Iterable[tuple[datetime, str, str, float]], detect_ts: datetime,
                 impact_on_home: float) -> Optional[tuple[datetime, str, float]]:
    """Return earliest threshold-crossing quote, preserving source timestamps."""
    start, end = detect_ts - WINDOW, detect_ts + WINDOW
    paths: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    for ts, market, book, price in quotes:
        paths.setdefault((market, book), []).append((ts, price))
    found: list[tuple[datetime, str, float]] = []
    for (market, book), points in paths.items():
        before = [point for point in points if point[0] <= start]
        if not before:
            continue
        base_ts, base_price = before[-1]
        threshold = PROB_MOVE if market == "moneyline" else SPREAD_MOVE
        for ts, price in points:
            if ts <= start or ts > end:
                continue
            signed_move = impact_on_home * (price - base_price)
            if signed_move >= threshold:
                found.append((ts, market + ":" + (book or "unknown"), price - base_price))
                break
    return min(found, key=lambda row: row[0]) if found else None


def score_event(event: dict[str, Any], line_dir: Path) -> dict[str, Any]:
    """Score one source event; missing evidence is explicit, never filled in."""
    detect_ts, reason = _valid_event(event)
    row = {"game": str(event.get("game_id") or ""), "player": str(event.get("player") or ""),
           "detect_ts": detect_ts.isoformat() if detect_ts else None, "reprice_ts": None,
           "delta_s": None, "verdict": "UNSCOREABLE", "reason": reason,
           "clock_basis": event.get("timestamp_basis"), "market": None}
    if detect_ts is None:
        return row
    quotes = load_game_quotes(line_dir, _event_date(event, detect_ts), row["game"])
    if not quotes:
        row["reason"] = "no_matching_line_history_quotes"
        return row
    reprice = find_reprice(quotes, detect_ts, float(event["impact_on_home"]))
    if reprice is None:
        row["reason"] = "no_threshold_reprice_in_window"
        return row
    reprice_ts, market, _move = reprice
    delta_s = int((reprice_ts - detect_ts).total_seconds())
    row.update({"reprice_ts": reprice_ts.isoformat(), "delta_s": delta_s, "market": market,
                "verdict": "AT_OR_BEFORE" if delta_s <= 0 else "AFTER", "reason": None})
    return row


def verdict(rows: list[dict[str, Any]]) -> tuple[str, int, Optional[float]]:
    scoreable = [row for row in rows if row["verdict"] in ("AT_OR_BEFORE", "AFTER")]
    n = len(scoreable)
    if n < MIN_EVENTS:
        return "FAIL: INSUFFICIENT_SCOREABLE_EVENTS", n, None
    share = sum(row["verdict"] == "AT_OR_BEFORE" for row in scoreable) / n
    return ("PASS" if share >= PASS_SHARE else "FAIL"), n, share


def render(rows: list[dict[str, Any]], event_count: int,
           events_path: Optional[Path] = None, line_dir: Optional[Path] = None) -> str:
    """Render the requested event table and exactly one PASS/FAIL outcome line."""
    outcome, n, share = verdict(rows)
    lines = ["# E2 NBA Sub-Shock Latency Race Results", "",
             "Clock basis: `detect_ts` is accepted only when the event manifest labels it "
             "a PBP/stint ingest timestamp. `reprice_ts` is the feed's recorded `captured_at`; "
             "no game-clock-to-wall-clock reconstruction is used.", "",
             "| game | player | detect_ts | reprice_ts | delta_s | verdict |",
             "| --- | --- | --- | --- | ---: | --- |"]
    for row in rows:
        lines.append("| {game} | {player} | {detect_ts} | {reprice_ts} | {delta_s} | {verdict} |".format(
            **{key: ("" if value is None else value) for key, value in row.items()}))
    share_text = "N/A" if share is None else "{:.1%}".format(share)
    if events_path is not None:
        lines.append("")
        lines.append("Event manifest: {} ({}).".format(events_path, "present" if events_path.is_file() else "MISSING"))
    if line_dir is not None:
        lines.append("Line-history directory: {} ({}).".format(line_dir, "present" if line_dir.is_dir() else "MISSING"))
    lines.extend(["", "Events read: {}; scoreable: {}.".format(event_count, n),
                  "{}: share={} (gate: >=60% of >=30 scoreable events).".format(outcome, share_text)])
    return "\n".join(lines) + "\n"


def run(events_path: Path = DEFAULT_EVENTS, line_dir: Path = DEFAULT_LINES) -> tuple[list[dict[str, Any]], int]:
    """Read candidates and score sequentially against the local own-feed files."""
    events = load_events(events_path)
    return [score_event(event, line_dir) for event in events], len(events)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure NBA PBP/stint detection vs own-feed repricing.")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--line-history-dir", type=Path, default=DEFAULT_LINES)
    parser.add_argument("--out", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    rows, count = run(args.events, args.line_history_dir)
    text = render(rows, count, args.events, args.line_history_dir)
    args.out.write_text(text, encoding="ascii")
    print(text.rsplit("\n", 2)[-2])


if __name__ == "__main__":
    main()
