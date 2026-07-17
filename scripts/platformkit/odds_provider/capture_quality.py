"""scripts.platformkit.odds_provider.capture_quality -- per-day capture-quality scoreboard.

THE GAP: feed_health.py measures whether a PROVIDER responds; it says nothing
about whether quotes actually LAND in the day's history file at a healthy
rate/coverage. A provider can be GREEN while the write path silently degrades
(fewer games, fewer venues, a stalled cadence) and nobody notices until CLV/
close coverage is already gapped. This reads back
data/cache/line_history/<sport>/<date>.jsonl (snapshot.py's write_quotes()
output) and scores today's capture against yesterday's.

PER-PROVIDER GAP (fixed here): the sport-level aggregate (n_rows/n_games/
n_venues) can stay GREEN even when ONE provider goes fully silent -- a
single-venue provider (e.g. pinnacle, the closing-line source) can produce
ZERO rows while other venues keep the aggregate healthy. _provider_drops()
buckets rows by provider (same "book" -> provider split as schema_snapshot's
_provider_of) and flags a REGRESSION, naming the provider, when a provider
with real coverage yesterday (>= _MIN_PROVIDER_ROWS_FOR_SIGNAL rows) produced
zero today. schema_snapshot.check_sport only diffs the SHAPE of providers
that ARE present -- it never notices one going missing; this is the
presence/row-count check that gap needs.

COVERAGE MEASUREMENT ONLY -- no $ field, no ROI, no edge claim, no flag flip,
no data/registry/ write. A quiet/empty day (offseason sport) is NO_DATA, not
a failure.

Row schema read (ground truth = snapshot.py's write_quotes/_row_from_quote):
  sport, game_id, home, away, market_type, side, line, odds (decimal >1.0),
  book (venue/book label), devigged_prob, captured_at (ISO-8601 UTC),
  commence_time.

ELAPSED-NORMALIZATION CHOICE (documented, not hidden): a same-clock-time
today-vs-yesterday n_rows comparison is noisy early in the day (6am today has
captured far fewer rows than a FULL yesterday just because fewer hours have
elapsed, not because anything broke). REGRESSION instead compares an
elapsed-normalized rate: today's n_rows / hours-since-first-capture vs
yesterday's n_rows / 24h (yesterday = a complete day). This under-flags very
early in the day but never over-flags a healthy slow start as broken -- the
honest tradeoff for a fail-closed-on-real-regressions scoreboard.

Run:  python -m scripts.platformkit.odds_provider.capture_quality
Per-file test: scripts/platformkit/odds_provider/test_capture_quality.py
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .schema_snapshot import _provider_of

_REPO = Path(__file__).resolve().parents[3]
DEFAULT_HISTORY_DIR = _REPO / "data" / "cache" / "line_history"
_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "capture_quality.json"

DEFAULT_SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis")

GREEN = "GREEN"
REGRESSION = "REGRESSION"
NO_DATA = "NO_DATA"

# A day needs at least this many distinct games captured to count as "real
# coverage" for the venue-drop / rate-collapse regression checks below.
_MIN_GAMES_FOR_SIGNAL = 3
# n_venues dropping by this much or more (today vs yesterday) is a REGRESSION
# on its own, independent of the rate check.
_VENUE_DROP_THRESHOLD = 2
# today's elapsed-normalized hourly rate below this fraction of yesterday's
# full-day hourly rate is a REGRESSION.
_RATE_FLOOR_FRACTION = 0.5

# A provider needs at least this many rows YESTERDAY to count as "real
# coverage" for the per-provider drop check below -- a provider that barely
# showed up (1-2 rows) going quiet today is noise, not a signal.
_MIN_PROVIDER_ROWS_FOR_SIGNAL = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(iso_ts: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def measure(sport: str, date_str: str, *, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Capture-quality metrics for one (sport, date) from its jsonl history file.

    Missing file -> zeros with "no_file": true. A corrupt/unparseable line is
    skipped and counted in "n_corrupt", never fabricated. Never raises.
    """
    base = Path(base_dir) if base_dir is not None else DEFAULT_HISTORY_DIR
    path = base / sport / ("%s.jsonl" % date_str)
    out: Dict[str, Any] = {
        "sport": sport, "date": date_str, "n_rows": 0, "n_games": 0, "n_venues": 0,
        "venues_per_game": 0.0, "tail_share": 0.0, "max_gap_min": None,
        "first_ts": None, "last_ts": None, "n_corrupt": 0, "no_file": False,
        "rows_by_provider": {},
    }
    if not path.exists():
        out["no_file"] = True
        return out
    try:
        game_venues: Dict[str, set] = {}
        venues: set = set()
        timestamps: List[datetime] = []
        rows_by_provider: Dict[str, int] = {}
        n_rows = n_tail = n_priced = 0
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    out["n_corrupt"] += 1
                    continue
                if not isinstance(row, dict):
                    out["n_corrupt"] += 1
                    continue
                n_rows += 1
                game_id = str(row.get("game_id") or "")
                book = str(row.get("book") or "")
                if game_id:
                    game_venues.setdefault(game_id, set())
                    if book:
                        game_venues[game_id].add(book)
                if book:
                    venues.add(book)
                    provider = _provider_of(book)
                    rows_by_provider[provider] = rows_by_provider.get(provider, 0) + 1
                ts = _parse_ts(row.get("captured_at"))
                if ts is not None:
                    timestamps.append(ts)
                try:
                    odds_f = float(row.get("odds"))
                except (TypeError, ValueError):
                    odds_f = None
                if odds_f is not None and odds_f > 1.0:
                    n_priced += 1
                    implied = 1.0 / odds_f
                    if implied < 0.20 or implied > 0.80:
                        n_tail += 1
        out["n_rows"] = n_rows
        out["n_games"] = len(game_venues)
        out["n_venues"] = len(venues)
        out["rows_by_provider"] = rows_by_provider
        if game_venues:
            out["venues_per_game"] = sum(len(v) for v in game_venues.values()) / len(game_venues)
        out["tail_share"] = (n_tail / n_priced) if n_priced else 0.0
        if timestamps:
            timestamps.sort()
            out["first_ts"] = timestamps[0].isoformat()
            out["last_ts"] = timestamps[-1].isoformat()
        if len(timestamps) >= 2:
            gaps = [(timestamps[i + 1] - timestamps[i]).total_seconds() / 60.0
                    for i in range(len(timestamps) - 1)]
            out["max_gap_min"] = max(gaps)
        else:
            out["max_gap_min"] = None
    except Exception as exc:  # noqa: BLE001 -- measure() must never raise
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out


def _hourly_rate(day: Dict[str, Any], *, full_day: bool, now: datetime) -> float:
    """n_rows per elapsed hour. full_day=True treats yesterday as a complete
    24h day; otherwise uses hours since first_ts (or since UTC midnight if
    first_ts is missing) up to `now`."""
    if full_day:
        hours = 24.0
    else:
        first = _parse_ts(day.get("first_ts")) if day.get("first_ts") else None
        if first is None:
            first = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hours = max((now - first).total_seconds() / 3600.0, 0.25)
    return (day.get("n_rows", 0) or 0) / hours


def _expected_providers() -> Optional[set]:
    """The provider names capture_quality expects to see, reusing feed_health's
    SAME provider stack (so the two lists never drift apart). Returns None (not
    an empty set) on any failure/import error -- callers then fall back to an
    UNFILTERED per-provider comparison rather than silently skipping the check.
    Constructing the provider objects is offline (no network call; fetch() is
    never invoked here)."""
    try:
        from .feed_health import _default_providers
        names = {getattr(p, "name", None) for p in _default_providers()}
        names.discard(None)
        return names or None
    except Exception:  # noqa: BLE001 -- must never sink capture_quality
        return None


def _provider_drops(today: Dict[str, Any], yesterday: Dict[str, Any], *,
                     min_rows: int = _MIN_PROVIDER_ROWS_FOR_SIGNAL,
                     expected: Optional[set] = None) -> List[str]:
    """Providers present in *yesterday* with >= min_rows rows that are absent
    or zero in *today* -- the per-provider drop a sport-level aggregate (venue
    count / overall rate) can mask (see module docstring, THE GAP). When
    *expected* is given, a provider outside it is never flagged (avoids a
    false positive on a one-off/malformed "book" label)."""
    yest_by = yesterday.get("rows_by_provider") or {}
    today_by = today.get("rows_by_provider") or {}
    dropped = [p for p, n in yest_by.items()
               if n >= min_rows and (today_by.get(p, 0) or 0) == 0
               and (expected is None or p in expected)]
    return sorted(dropped)


def _verdict(today: Dict[str, Any], yesterday: Dict[str, Any], *, now: datetime,
             dropped_providers: Optional[Sequence[str]] = None) -> str:
    """GREEN / REGRESSION / NO_DATA -- see scoreboard() docstring for the rule."""
    today_empty = (today.get("n_rows", 0) or 0) == 0
    if today_empty and (yesterday.get("n_rows", 0) or 0) == 0:
        return NO_DATA
    if (yesterday.get("n_games", 0) or 0) < _MIN_GAMES_FOR_SIGNAL:
        return GREEN if not today_empty else NO_DATA  # no baseline to regress against
    if dropped_providers:
        return REGRESSION
    venue_drop = (yesterday.get("n_venues", 0) or 0) - (today.get("n_venues", 0) or 0)
    if venue_drop >= _VENUE_DROP_THRESHOLD:
        return REGRESSION
    today_rate = _hourly_rate(today, full_day=False, now=now)
    yest_rate = _hourly_rate(yesterday, full_day=True, now=now)
    if yest_rate > 0 and today_rate < (_RATE_FLOOR_FRACTION * yest_rate):
        return REGRESSION
    return GREEN


def scoreboard(sports: Sequence[str] = DEFAULT_SPORTS, *, now: Optional[datetime] = None,
               base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Measure today + yesterday per sport and assign a verdict. Never raises.

    Verdict rule (see module docstring for the elapsed-normalization rationale):
      NO_DATA     -- both days empty (an offseason sport; not a failure).
      REGRESSION  -- yesterday had real coverage (n_games >= 3) AND ANY OF:
                     today's elapsed-normalized hourly rate < 50% of
                     yesterday's full-day hourly rate; n_venues dropped by 2+
                     (today vs yesterday); OR a single provider that had real
                     coverage yesterday (>= _MIN_PROVIDER_ROWS_FOR_SIGNAL rows)
                     produced ZERO rows today (provider_regression names it --
                     see _provider_drops, THE GAP in the module docstring).
      GREEN       -- everything else (including "no baseline to regress
                     against yet").
    """
    nowdt = now if now is not None else _now()
    today_str = nowdt.date().isoformat()
    yest_str = (nowdt - timedelta(days=1)).date().isoformat()
    expected_providers = _expected_providers()
    by_sport: Dict[str, Any] = {}
    n_regression = 0
    n_no_data = 0
    for sport in sports:
        try:
            today = measure(sport, today_str, base_dir=base_dir)
            yesterday = measure(sport, yest_str, base_dir=base_dir)
            dropped = _provider_drops(today, yesterday, expected=expected_providers)
            verdict = _verdict(today, yesterday, now=nowdt, dropped_providers=dropped)
        except Exception as exc:  # noqa: BLE001 -- one bad sport must not sink the board
            today = {"sport": sport, "date": today_str, "error": "%s: %s" % (
                type(exc).__name__, exc)}
            yesterday = {"sport": sport, "date": yest_str}
            dropped = []
            verdict = NO_DATA
        if verdict == REGRESSION:
            n_regression += 1
        elif verdict == NO_DATA:
            n_no_data += 1
        by_sport[sport] = {"today": today, "yesterday": yesterday, "verdict": verdict,
                           "provider_regression": dropped}

    overall = REGRESSION if n_regression else (
        NO_DATA if n_no_data == len(sports) else GREEN)
    return {
        "sports": list(sports),
        "by_sport": by_sport,
        "n_regression": n_regression,
        "n_no_data": n_no_data,
        "overall": overall,
        "honest_note": (
            "reads back data/cache/line_history/<sport>/<date>.jsonl (snapshot.py's "
            "write_quotes output). Coverage measurement only -- no $ field, no ROI, "
            "no edge claim. Early-in-the-day comparisons are noisy; REGRESSION uses "
            "an elapsed-normalized hourly rate (today's partial day vs yesterday's "
            "full day) as mitigation -- see module docstring. by_sport[sport]."
            "provider_regression names any provider with real coverage yesterday "
            "that produced zero rows today, even when the sport-level aggregate "
            "stays healthy (see THE GAP / PER-PROVIDER GAP in the module docstring)."
        ),
    }


def write_status(doc: Dict[str, Any], *, out_path: Optional[Path] = None,
                  now: Optional[float] = None) -> bool:
    """Atomically write the scoreboard (tmp + os.replace). Never raises."""
    try:
        path = Path(out_path) if out_path is not None else _OUT_PATH
        ts = float(now) if now is not None else time.time()
        full = dict(doc)
        full["generated_at"] = ts
        full["component"] = "m_capture_quality"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(full, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001 -- write must never crash the caller
        return False


def load_status(*, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Best-effort read of the last written scoreboard. None on any failure/missing."""
    try:
        p = Path(path) if path is not None else _OUT_PATH
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="ascii"))
    except Exception:  # noqa: BLE001
        return None


def render(doc: Dict[str, Any]) -> str:
    """ASCII table summary of a scoreboard doc."""
    lines: List[str] = ["=" * 78,
        "CAPTURE QUALITY -- per-sport line-capture coverage (%s)" % ",".join(
            doc.get("sports", [])),
        "=" * 78,
        "%-12s %-11s %6s %6s %6s %8s %8s %10s" % (
            "SPORT", "VERDICT", "ROWS", "GAMES", "VENUE", "V/GAME", "TAIL%", "MAXGAP_M")]
    for sport in doc.get("sports", []):
        today = ((doc.get("by_sport", {}) or {}).get(sport, {})).get("today", {}) or {}
        verdict = (doc.get("by_sport", {}) or {}).get(sport, {}).get("verdict", "?")
        gap = today.get("max_gap_min")
        lines.append("%-12s %-11s %6d %6d %6d %8.2f %7.1f%% %10s" % (
            sport, verdict, today.get("n_rows", 0) or 0, today.get("n_games", 0) or 0,
            today.get("n_venues", 0) or 0, today.get("venues_per_game", 0.0) or 0.0,
            (today.get("tail_share", 0.0) or 0.0) * 100.0,
            ("%.1f" % gap) if gap is not None else "-"))
    for sport in doc.get("sports", []):
        dropped = (doc.get("by_sport", {}) or {}).get(sport, {}).get("provider_regression") or []
        if dropped:
            lines.append("  PROVIDER DROP  %-12s %s" % (sport, ", ".join(dropped)))
    lines += ["-" * 78, "OVERALL: " + doc.get("overall", "?"), "=" * 78]
    return "\n".join(lines)


def main() -> int:
    doc = scoreboard()
    print(render(doc))
    write_status(doc)
    print("\nwrote %s" % _OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["GREEN", "REGRESSION", "NO_DATA", "DEFAULT_SPORTS", "DEFAULT_HISTORY_DIR",
           "measure", "scoreboard", "write_status", "load_status", "render"]
