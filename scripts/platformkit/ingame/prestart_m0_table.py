"""Build labelled prestart market-probability rows without using ratings.

The command is deliberately streaming: parquet sources are consumed a row group at
a time, so the large MLB price series is never materialized as one frame.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_REPO = Path(__file__).resolve().parents[3]
_PROB = ("p_prestart", "probability", "implied_probability", "p_close",
         "close_prob", "price", "yes_price", "prob", "market_prob")
_EVENT = ("game_id", "event_id", "event_key", "match_id", "id")
_TIME = ("quote_ts", "timestamp", "ts", "close_ts", "created_at", "time")
_OFFSET = ("close_sec_after_tip", "sec_after_tip")
_START = ("start_ts", "start_time", "commence_time", "start_utc", "tip_ts")
_HOME = ("home", "home_team", "team_home", "player1", "p1")
_AWAY = ("away", "away_team", "team_away", "player2", "p2")
_OUTPUT = ("event_key", "sport", "date", "home", "away", "start_ts", "p_prestart",
           "quote_ts", "sec_before_start", "source", "kind", "venue")
_PREGAME_SOURCES = ("pregame_last_tick_before_commence", "pre_first_pitch_two_sided")
_MLB_ID_TEAMS = re.compile(r"^(?:\d{8}|\d{4}-\d{2}-\d{2})-([A-Za-z]+)-([A-Za-z]+)-\d+$")


def _get(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    lowered = row.get("_s327_lower")
    if not isinstance(lowered, dict):
        lowered = {str(k).lower(): v for k, v in row.items()}
        row["_s327_lower"] = lowered
    for name in names:
        if name in lowered and lowered[name] not in (None, ""):
            return lowered[name]
    return None


def _text(value: Any) -> str:
    return "" if value is None else " ".join(str(value).strip().lower().split())


def _stamp(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
        return number / 1000.0 if number > 10_000_000_000 else number
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _probability(row: dict[str, Any]) -> float | None:
    value = _get(row, _PROB)  # Deliberately excludes p0, Elo, rating, and model fields.
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and 0.0 <= result <= 1.0 else None


def _date(stamp: float | None, row: dict[str, Any]) -> str:
    raw = _get(row, ("date", "game_date", "event_date"))
    if raw not in (None, ""):
        return str(raw)[:10]
    if stamp is None:
        return ""
    return datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()


def _aliases(raw: dict[str, Any], sport: str) -> dict[str, str]:
    block = raw.get(sport, {}) if isinstance(raw, dict) else {}
    aliases = block.get("aliases", {}) if isinstance(block, dict) else {}
    return {_text(k): _text(v) for k, v in aliases.items()}


def _name(value: Any, aliases: dict[str, str], known: set[str], unmapped: Counter[str]) -> str:
    candidate = aliases.get(_text(value), _text(value))
    if candidate and known and candidate not in known:
        unmapped[candidate] += 1
    return candidate


def _ticker_teams(value: Any, known: set[str], aliases: dict[str, str]) -> tuple[str, str]:
    """Return the sole known team pair contained in a market ticker, if any."""
    text = _text(value)
    variants = {team: {team, *(raw for raw, mapped in aliases.items() if mapped == team)} for team in known}
    pairs = {(home, away) for home in known for away in known if home != away
             and any(item in text for item in variants[home]) and any(item in text for item in variants[away])}
    return next(iter(pairs)) if len(pairs) == 1 else ("", "")


def _quote_pair(row: dict[str, Any], aliases: dict[str, str], known: set[str],
                unmapped: Counter[str], ticker_cache: dict[str, tuple[str, str]]) -> tuple[str, str]:
    home, away = _name(_get(row, _HOME), aliases, known, unmapped), _name(_get(row, _AWAY), aliases, known, unmapped)
    if home and away:
        return home, away
    match = _MLB_ID_TEAMS.match(str(_get(row, _EVENT) or ""))
    if match:
        return (_name(match.group(1), aliases, known, unmapped),
                _name(match.group(2), aliases, known, unmapped))
    for field in ("ticker_or_slug", "market_ticker", "event_key", "event_id"):
        ticker = _text(_get(row, (field,)))
        if ticker and ticker not in ticker_cache:
            ticker_cache[ticker] = _ticker_teams(ticker, known, aliases)
        pair = ticker_cache.get(ticker, ("", ""))
        if pair != ("", ""):
            return pair
    return "", ""


def state_events(rows: Iterable[dict[str, Any]], sport: str) -> list[dict[str, Any]]:
    """Reduce state rows to one event record, retaining the state archive key."""
    events: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_key = _text(_get(row, _EVENT))
        if not event_key:
            continue
        start = _stamp(_get(row, _START))
        home, away = _text(_get(row, _HOME)), _text(_get(row, _AWAY))
        ticker = _get(row, ("market_ticker",))
        if not home and not away and ticker:
            parts = str(ticker).split("-")
            if len(parts) >= 3:
                away, home = _text(parts[1]), _text(parts[2])
        alt_key = _text(_get(row, ("event_key",)))
        events.setdefault(event_key, {
            "event_key": event_key, "sport": sport, "date": _date(start, row),
            "home": home, "away": away, "start_ts": start,
            "alt_key": alt_key if alt_key and alt_key != event_key else "",
        })
    return list(events.values())


def build_table(events: list[dict[str, Any]], quotes: Iterable[dict[str, Any]], sport: str,
                mapping: dict[str, Any] | None = None, source: str = "unknown",
                allow_proxy: bool = False, require_team_agreement: bool = False) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Choose labelled quotes; optional proxies still require a complete team pair."""
    mapping = mapping or {}
    aliases = _aliases(mapping, sport)
    known = {x for event in events for x in (event["home"], event["away"]) if x}
    unmapped: Counter[str] = Counter()
    by_id = {event["event_key"]: event for event in events}
    by_alt = {event["alt_key"]: event for event in events if event.get("alt_key")}
    by_pair: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for event in events:
        if event["home"] and event["away"]:
            by_pair.setdefault((event["date"], event["home"], event["away"]), []).append(event)
    for candidates in by_pair.values():
        candidates.sort(key=lambda event: event["event_key"])
    choices: dict[str, dict[str, tuple[float, float, str, str, float]]] = {}
    ticker_cache: dict[str, tuple[str, str]] = {}
    for row in quotes:
        probability = _probability(row)
        if probability is None:
            continue
        home, away = _quote_pair(row, aliases, known, unmapped, ticker_cache)
        event = None if require_team_agreement else (by_id.get(_text(_get(row, _EVENT))) or by_alt.get(_text(_get(row, _EVENT))))
        if event is None and home and away:
            candidates = by_pair.get((_date(None, row), home, away), [])
            event = candidates[0] if candidates else None
        if event is None or (require_team_agreement and (not home or not away or
                                                        (event["home"], event["away"]) != (home, away))):
            continue
        quote_ts = _stamp(_get(row, _TIME))
        if event["start_ts"] is not None and quote_ts is None:
            try:
                quote_ts = float(event["start_ts"]) + float(_get(row, _OFFSET))
            except (TypeError, ValueError):
                continue
        venue = str(_get(row, ("venue", "source", "book")) or "")
        row_source = str(row.get("_s327_source") or source)
        slots = choices.setdefault(event["event_key"], {})
        if event["start_ts"] is not None:
            delta = quote_ts - float(event["start_ts"])
            # S327_spec.md:38 defines sec_before_start as negative = after start; delta is
            # elapsed-since-start (negative before, positive after), so the stored item negates it.
            item = (-delta, quote_ts, venue, row_source, probability)
            if delta < 0 and ("pre" not in slots or quote_ts > slots["pre"][1]):
                slots["pre"] = item
            elif 0 <= delta <= 60 and ("tip" not in slots or quote_ts < slots["tip"][1]):
                slots["tip"] = item
            elif delta > 60 and ("late" not in slots or quote_ts < slots["late"][1]):
                slots["late"] = item
        elif allow_proxy:
            close_source = _get(row, ("close_source",))
            offset = float(_get(row, _OFFSET) or 0.0)  # sec_after_tip convention: negative before tip.
            item = (-offset, quote_ts, venue, row_source, probability)
            if close_source in _PREGAME_SOURCES and ("pre" not in slots or quote_ts > slots["pre"][1]):
                slots["pre"] = item
            elif close_source == "first_inplay_tick" and ("tip" not in slots or quote_ts < slots["tip"][1]):
                slots["tip"] = item
            elif close_source not in _PREGAME_SOURCES and close_source != "first_inplay_tick" and ("late" not in slots or quote_ts < slots["late"][1]):
                slots["late"] = item
    result: list[dict[str, Any]] = []
    for event in events:
        pool = choices.get(event["event_key"], {})
        if "pre" in pool:
            selected, kind = pool["pre"], "PRE_START"
        elif "tip" in pool:
            selected, kind = pool["tip"], "AT_TIP"
        elif "late" in pool:
            selected, kind = pool["late"], "FIRST_INPLAY"
        else:
            selected, kind = None, "NONE"
        result.append({**event, "p_prestart": selected[4] if selected else None,
                       "quote_ts": selected[1] if selected else None,
                       "sec_before_start": selected[0] if selected else None,
                       "source": selected[3] if selected else "", "kind": kind,
                       "venue": selected[2] if selected else ""})
    return result, unmapped


def iter_rows(path: Path, columns: list[str] | None = None) -> Iterable[dict[str, Any]]:
    """Yield parquet rows by row group or JSONL rows; never load a whole store."""
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)
        return
    import pyarrow.parquet as pq
    parquet = pq.ParquetFile(path)
    names = set(parquet.schema_arrow.names)
    projected = [column for column in columns if column in names] if columns else None
    for group_index in range(parquet.metadata.num_row_groups):
        yield from parquet.read_row_group(group_index, columns=projected).to_pylist()


def _write(rows: list[dict[str, Any]], path: Path) -> None:
    import pandas as pd
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=_OUTPUT).to_parquet(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build labelled prestart M0 rows.")
    parser.add_argument("--sport", required=True)
    parser.add_argument("--states", required=True, type=Path, nargs="+")
    parser.add_argument("--quotes", required=True, type=Path, nargs="+")
    parser.add_argument("--source", default="")
    parser.add_argument("--mapping", type=Path, default=_REPO / "domains" / "cross_sport_market" / "prestart_m0_name_map.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unmapped", type=Path, required=True)
    args = parser.parse_args()
    state_paths, quote_paths = [], []
    for path in args.states:
        if path.exists():
            state_paths.append(path)
        else:
            print("ABSENT-IN-WORKTREE %s" % path.as_posix())
    for path in args.quotes:
        if path.exists():
            quote_paths.append(path)
        else:
            print("ABSENT-IN-WORKTREE %s" % path.as_posix())
    mapping = json.loads(args.mapping.read_text()) if args.mapping.exists() else {}
    events = [event for path in state_paths for event in state_events(iter_rows(path), args.sport)]
    events = list({event["event_key"]: event for event in events}.values())
    quotes = ({**row, "_s327_source": path.as_posix()}
              for path in quote_paths for row in iter_rows(path))
    rows, unmapped = build_table(events, quotes, args.sport, mapping, args.source)
    _write(rows, args.output)
    args.unmapped.write_text(json.dumps(dict(unmapped), indent=2, sort_keys=True) + "\n")
    print("INTERPRETER %s" % __import__("sys").executable)
    print("M0_ROWS %d" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
