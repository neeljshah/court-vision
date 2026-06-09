"""steam_detector.py — Pinnacle-anchored sharp/steam move detector.

Long-running async loop (30s tick) that watches multi-book line movement
and emits sharp.steam / sharp.rlm events when ≥3 books move ≥0.5pt in
the same direction within a 5-minute window.

Events are:
  * Published to the in-process EventBus (topic "sharp.steam" / "sharp.rlm")
  * Appended to data/cache/steam_events.jsonl
  * Optionally SMSed via Twilio REST (urllib only, no pip dep)
  * Optionally posted to a Slack webhook

Run standalone (one tick, prints events):
    python scripts/steam_detector.py --tick-once
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger("steam_detector")

# ── paths ──────────────────────────────────────────────────────────────────────
_CACHE_DIR = Path(PROJECT_DIR) / "data" / "cache"
_EVENTS_PATH = _CACHE_DIR / "steam_events.jsonl"
_DEDUP_PATH = _CACHE_DIR / "steam_dedup.json"
_SMS_COUNT_PATH = _CACHE_DIR / "sms_count.json"

# ── config ─────────────────────────────────────────────────────────────────────
_TICK_INTERVAL_SEC = 30
_WINDOW_MINUTES = 5
_MIN_BOOKS_MOVING = 3
_MIN_DELTA = 0.5          # points
_DEDUP_WINDOW_SEC = 600   # 10 minutes
_SMS_DAILY_CAP = int(os.environ.get("STEAM_SMS_DAILY_CAP", "20"))
_PIN_FOLLOWER_WINDOW_SEC = 90   # seconds within which soft books must follow Pin

# Wagered-pct directory (optional — RLM detection)
_WAGERED_PCT_DIR = _CACHE_DIR / "wagered_pct"
_RLM_THRESHOLD = 0.60     # public side ≥60% but line moves OTHER way

# ── in-memory state ────────────────────────────────────────────────────────────
# {(player, stat, line, direction): last_emit_timestamp}
_last_emit: Dict[Tuple, float] = {}


# ── helpers ────────────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_ts() -> float:
    return time.time()


def _parse_ts(ts: str) -> float:
    """ISO timestamp → float. Handles Z suffix and offset-aware."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        try:
            return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc).timestamp()
        except (TypeError, ValueError):
            return 0.0


def _slate_date() -> str:
    from datetime import date
    return date.today().isoformat()


# ── dedup persistence ──────────────────────────────────────────────────────────

def _load_dedup() -> Dict[str, float]:
    """Load last-emit map from disk. Keys are serialised tuples."""
    try:
        with open(_DEDUP_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_dedup(d: Dict[str, float]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_DEDUP_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f)


def _dedup_key(player: str, stat: str, line: float, direction: str) -> str:
    return f"{player.lower()}|{stat}|{line}|{direction}"


def _restore_last_emit() -> None:
    """Reload dedup state from disk so we survive restarts."""
    raw = _load_dedup()
    now = _now_ts()
    for k, ts in raw.items():
        if now - ts < _DEDUP_WINDOW_SEC:
            _last_emit[tuple(k.split("|"))] = ts  # type: ignore[assignment]
    log.info("steam_detector restored %d dedup entries from disk", len(_last_emit))


def _flush_dedup() -> None:
    """Persist current in-memory dedup map to disk."""
    out: Dict[str, float] = {}
    for k, v in _last_emit.items():
        out["|".join(str(x) for x in k)] = v
    _save_dedup(out)


# ── SMS via Twilio REST (urllib, no pip dep) ───────────────────────────────────

def _sms_count_today() -> int:
    try:
        with open(_SMS_COUNT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") == _slate_date():
            return int(data.get("count", 0))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return 0


def _inc_sms_count() -> int:
    count = _sms_count_today() + 1
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_SMS_COUNT_PATH, "w", encoding="utf-8") as f:
        json.dump({"date": _slate_date(), "count": count}, f)
    return count


def _send_sms(body: str) -> bool:
    """Send SMS via Twilio REST API (no twilio package). Returns True on success."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
    to_num = os.environ.get("STEAM_SMS_TO_NUMBER", "").strip()
    if not all([sid, auth, from_num, to_num]):
        return False
    if _sms_count_today() >= _SMS_DAILY_CAP:
        log.warning("steam_detector SMS daily cap (%d) reached, skipping", _SMS_DAILY_CAP)
        return False
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        data = urllib.parse.urlencode({
            "From": from_num, "To": to_num, "Body": body,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        import base64
        creds = base64.b64encode(f"{sid}:{auth}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status in (200, 201)
        if ok:
            _inc_sms_count()
            log.info("steam_detector SMS sent (count=%d)", _sms_count_today())
        return ok
    except Exception as exc:  # noqa: BLE001
        log.warning("steam_detector SMS failed: %s", exc)
        return False


def _format_sms(event: Dict[str, Any]) -> str:
    direction = "up" if event["direction"] == "up" else "down"
    arrow = "↑" if direction == "up" else "↓"
    books_line = " / ".join(
        f"{d['book'].upper()} {'+' if (d.get('over_price') or 0) >= 0 else ''}{d.get('over_price', '?')}"
        for d in event.get("books_detail", [])[:4]
    )
    pin_tag = " · pin lead" if event.get("pin_moved") else ""
    elapsed_tags = [d.get("delta_minutes", 0) for d in event.get("books_detail", [])]
    max_elapsed = f"{max(elapsed_tags):.0f}s" if elapsed_tags else "?"
    return (
        f"\U0001f30a STEAM: {event['player']} {event['stat'].upper()} "
        f"{arrow} {event['new_line']} (was {event['old_line']})\n"
        f"{event['n_books_moving']} books moved {direction}{pin_tag} · {max_elapsed}\n"
        f"{books_line}"
    )


# ── Slack webhook ──────────────────────────────────────────────────────────────

def _post_slack(event: Dict[str, Any]) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        return
    topic_emoji = "\U0001f30a" if event["topic"] == "sharp.steam" else "\U0001f4a1"
    text = (
        f"{topic_emoji} *{event['topic'].upper()}* "
        f"{event['player']} {event['stat'].upper()} {event['direction']} "
        f"{event['old_line']} → {event['new_line']} "
        f"({event['n_books_moving']} books, conf={event['confidence']}, "
        f"pin={'Y' if event['pin_moved'] else 'N'})"
    )
    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(webhook, data=payload,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)
    except Exception as exc:  # noqa: BLE001
        log.warning("steam_detector Slack post failed: %s", exc)


# ── wagered-pct helper (RLM) ───────────────────────────────────────────────────

def _get_public_pct(player: str, stat: str) -> Optional[float]:
    """Return the fraction wagered on the OVER side, or None if unavailable."""
    if not _WAGERED_PCT_DIR.exists():
        return None
    date = _slate_date()
    candidate = _WAGERED_PCT_DIR / f"{date}.json"
    if not candidate.exists():
        return None
    try:
        with open(candidate, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Expected format: [{player, stat, over_pct}, ...]
        for row in data:
            if (row.get("player", "").lower() == player.lower()
                    and row.get("stat", "").lower() == stat.lower()):
                return float(row["over_pct"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        pass
    return None


# ── core detection logic ───────────────────────────────────────────────────────

def _compute_steam_events(date: str) -> List[Dict[str, Any]]:
    """Synchronous: read CSVs, detect steam events. Returns list of event dicts."""
    from api._courtvision_odds import line_moves, _book_csv_paths, _to_float, _BOOK_DISPLAY
    import csv

    # 1. Collect all line moves in the 5-min window.
    moves = line_moves(date, window_minutes=_WINDOW_MINUTES)
    if not moves:
        return []

    # Enrich moves with exact timestamps from raw CSV for fine-grained timing
    # (line_moves() only gives ts_open/ts_close strings, not per-quote series).
    # Build a quick (player, stat, book) → sorted [(ts_float, line)] index.
    raw_series: Dict[Tuple[str, str, str], List[Tuple[float, float]]] = {}
    cutoff = _now_ts() - _WINDOW_MINUTES * 60
    for path in _book_csv_paths(date):
        try:
            with path.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    stat = (r.get("stat") or "").lower()
                    player = (r.get("player_name") or "").strip()
                    if not player or stat not in {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}:
                        continue
                    line = _to_float(r.get("line"))
                    ts_str = r.get("captured_at") or ""
                    if line is None or not ts_str:
                        continue
                    ts = _parse_ts(ts_str)
                    if ts < cutoff:
                        continue
                    book = (r.get("book") or path.stem.split("_")[-1]).lower()
                    key = (player.lower(), stat, book)
                    raw_series.setdefault(key, []).append((ts, line))
        except OSError:
            continue
    for series in raw_series.values():
        series.sort()

    # 2. Group moves by (player, stat) and find consensus direction.
    from collections import defaultdict
    by_prop: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for m in moves:
        key = (m["player"].lower(), m["stat"])
        by_prop[key].append(m)

    now = _now_ts()
    events: List[Dict[str, Any]] = []

    for (player_lower, stat), book_moves in by_prop.items():
        if len(book_moves) < 2:
            continue  # need ≥2 books to have any pattern

        # Resolve canonical player name (capitalised).
        player_name = next((m["player"] for m in book_moves if m["player"]), player_lower)

        # Classify each move as "up", "down", or "mixed".
        up_moves = [m for m in book_moves if m["delta"] >= _MIN_DELTA]
        down_moves = [m for m in book_moves if m["delta"] <= -_MIN_DELTA]

        for direction, qualifying in [("up", up_moves), ("down", down_moves)]:
            if len(qualifying) < 2:
                continue  # need ≥2 before we do further analysis

            # Determine the representative old/new line as median of the movers.
            old_lines = [m["line_open"] for m in qualifying]
            new_lines = [m["line_close"] for m in qualifying]
            old_line = sorted(old_lines)[len(old_lines) // 2]
            new_line = sorted(new_lines)[len(new_lines) // 2]

            # Build books_detail with fine timing info.
            books_detail: List[Dict[str, Any]] = []
            for m in qualifying:
                book = m["book"]
                series = raw_series.get((player_lower, stat, book), [])
                # Find earliest and latest line in window.
                first_ts = _parse_ts(m["ts_open"]) if m.get("ts_open") else now
                last_ts = _parse_ts(m["ts_close"]) if m.get("ts_close") else now
                elapsed_min = (last_ts - first_ts) / 60.0
                books_detail.append({
                    "book": book,
                    "display": _BOOK_DISPLAY.get(book, book),
                    "old": m["line_open"],
                    "new": m["line_close"],
                    "delta": round(m["delta"], 2),
                    "delta_minutes": round(elapsed_min, 2),
                    "ts_first": m.get("ts_open", ""),
                    "ts_last": m.get("ts_close", ""),
                })

            # Sort: Pinnacle first, then by elapsed time asc.
            books_detail.sort(key=lambda d: (0 if d["book"] == "pin" else 1, d["delta_minutes"]))

            n_moving = len(books_detail)
            pin_moved = any(d["book"] == "pin" for d in books_detail)

            # Determine minimum books threshold.
            # Confidence logic:
            #   high: pin moved + ≥3 followers within 90s
            #   medium: ≥3 soft books without pin, OR pin + 1-2 followers
            #   low: exactly 2 books
            soft_count = sum(1 for d in books_detail if d["book"] != "pin")
            pin_detail = next((d for d in books_detail if d["book"] == "pin"), None)

            if pin_moved and pin_detail:
                pin_ts = _parse_ts(pin_detail["ts_first"]) if pin_detail["ts_first"] else now
                followers_within_90s = sum(
                    1 for d in books_detail
                    if d["book"] != "pin"
                    and abs(_parse_ts(d["ts_first"]) - pin_ts) <= _PIN_FOLLOWER_WINDOW_SEC
                )
            else:
                followers_within_90s = 0

            if n_moving >= _MIN_BOOKS_MOVING:
                if pin_moved and followers_within_90s >= 2:
                    confidence = "high"
                elif n_moving >= _MIN_BOOKS_MOVING:
                    confidence = "medium"
                else:
                    confidence = "low"
            elif n_moving == 2:
                confidence = "low"
            else:
                continue  # only 0-1 books, not significant

            # Minimum bar: ≥2 books moving, but we emit at "low" for 2.
            # The spec says emit when 3+ books move — enforce that for steam events.
            if n_moving < _MIN_BOOKS_MOVING:
                continue

            # RLM detection: check wagered pct.
            topic = "sharp.steam"
            public_over_pct = _get_public_pct(player_lower, stat)
            if public_over_pct is not None:
                if direction == "up" and public_over_pct <= (1.0 - _RLM_THRESHOLD):
                    # Public heavy UNDER but line moving UP → RLM.
                    topic = "sharp.rlm"
                    confidence = "high"  # RLM is a stronger signal
                elif direction == "down" and public_over_pct >= _RLM_THRESHOLD:
                    # Public heavy OVER but line moving DOWN → RLM.
                    topic = "sharp.rlm"
                    confidence = "high"

            events.append({
                "topic": topic,
                "player": player_name,
                "stat": stat,
                "old_line": old_line,
                "new_line": new_line,
                "direction": direction,
                "n_books_moving": n_moving,
                "pin_moved": pin_moved,
                "books_detail": books_detail,
                "confidence": confidence,
                "public_over_pct": public_over_pct,
                "ts": _now_utc(),
            })

    return events


# ── dedup check ────────────────────────────────────────────────────────────────

# Tracks the last emitted new_line per dedup key — used to detect further movement.
_last_emit_lines: Dict[Tuple, float] = {}


def _should_emit(event: Dict[str, Any]) -> bool:
    """Return True if we should emit this event (dedup check)."""
    k = (event["player"].lower(), event["stat"],
         str(event["new_line"]), event["direction"])
    now = _now_ts()
    last = _last_emit.get(k)
    if last is None:
        return True
    age = now - last
    if age >= _DEDUP_WINDOW_SEC:
        return True
    # Allow re-emit ONLY if line moved further in same direction BEYOND what we last emitted.
    last_emitted_line = _last_emit_lines.get(k)
    if last_emitted_line is None:
        return False  # previously emitted, line unchanged — suppress
    if event["direction"] == "up" and event["new_line"] > last_emitted_line + _MIN_DELTA:
        return True
    if event["direction"] == "down" and event["new_line"] < last_emitted_line - _MIN_DELTA:
        return True
    return False


def _mark_emitted(event: Dict[str, Any]) -> None:
    k = (event["player"].lower(), event["stat"],
         str(event["new_line"]), event["direction"])
    _last_emit[k] = _now_ts()
    _last_emit_lines[k] = event["new_line"]
    _flush_dedup()


# ── persistence ────────────────────────────────────────────────────────────────

def _append_event(event: Dict[str, Any]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_EVENTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


# ── notifications ──────────────────────────────────────────────────────────────

def _notify(event: Dict[str, Any]) -> None:
    """Fire Slack + SMS for the event (non-blocking, errors swallowed)."""
    _post_slack(event)
    if event.get("confidence") == "high":
        body = _format_sms(event)
        _send_sms(body)


# ── single tick ────────────────────────────────────────────────────────────────

async def _tick(loop: asyncio.AbstractEventLoop, date: str,
                verbose: bool = False) -> List[Dict[str, Any]]:
    """Run one detection pass. Returns emitted events."""
    try:
        events = await loop.run_in_executor(None, _compute_steam_events, date)
    except Exception as exc:  # noqa: BLE001
        log.warning("steam_detector _compute_steam_events failed: %s", exc)
        return []

    emitted: List[Dict[str, Any]] = []
    for ev in events:
        if not _should_emit(ev):
            log.debug("steam_detector dedup skip: %s %s %s %s",
                      ev["player"], ev["stat"], ev["new_line"], ev["direction"])
            continue
        _mark_emitted(ev)
        _append_event(ev)
        _notify(ev)

        # Publish to event bus (best-effort; bus may not exist in CLI mode).
        try:
            from src.live.event_bus import get_bus
            bus = get_bus()
            await bus.publish(ev["topic"], ev)
        except Exception:  # noqa: BLE001
            pass

        emitted.append(ev)
        if verbose:
            print(json.dumps(ev, indent=2))
        log.info("steam_detector emitted %s %s %s %s → %s conf=%s",
                 ev["topic"], ev["player"], ev["stat"], ev["old_line"],
                 ev["new_line"], ev["confidence"])

    return emitted


# ── main async loop ────────────────────────────────────────────────────────────

async def run_steam_detector() -> None:
    """Long-running loop. Supervised by task_supervisor in live_v2_app."""
    log.info("steam_detector starting (tick=%ds, window=%dmin)",
             _TICK_INTERVAL_SEC, _WINDOW_MINUTES)
    _restore_last_emit()
    loop = asyncio.get_event_loop()
    while True:
        date = _slate_date()
        await _tick(loop, date, verbose=False)
        await asyncio.sleep(_TICK_INTERVAL_SEC)


# ── CLI entry point ────────────────────────────────────────────────────────────

def _run_tick_once(date: Optional[str] = None, verbose: bool = True) -> List[Dict]:
    """Synchronous wrapper for --tick-once mode."""
    _restore_last_emit()
    if date is None:
        date = _slate_date()
    loop = asyncio.new_event_loop()
    events = loop.run_until_complete(_tick(loop, date, verbose=verbose))
    loop.close()
    return events


# ── backtest helper ────────────────────────────────────────────────────────────

def _backtest_continuation(events: List[Dict], date: str,
                           horizon_min: int = 30) -> Dict[str, Any]:
    """Check what % of emitted events moved further in the same direction
    within `horizon_min` minutes after the event timestamp.

    This uses the same CSV data so it's only meaningful for historical ticks
    where the full day's worth of quotes is already on disk.
    """
    from api._courtvision_odds import _book_csv_paths, _to_float
    import csv as _csv

    # Build (player, stat, book) → sorted [(ts, line)]
    all_series: Dict[Tuple[str, str, str], List[Tuple[float, float]]] = {}
    for path in _book_csv_paths(date):
        try:
            with path.open(newline="", encoding="utf-8") as f:
                for r in _csv.DictReader(f):
                    stat = (r.get("stat") or "").lower()
                    player = (r.get("player_name") or "").strip()
                    line = _to_float(r.get("line"))
                    ts_str = r.get("captured_at") or ""
                    if not player or line is None or not ts_str:
                        continue
                    book = (r.get("book") or path.stem.split("_")[-1]).lower()
                    all_series.setdefault((player.lower(), stat, book), []).append(
                        (_parse_ts(ts_str), line))
        except OSError:
            continue
    for series in all_series.values():
        series.sort()

    continued = 0
    total = 0
    for ev in events:
        player_l = ev["player"].lower()
        stat = ev["stat"]
        ev_ts = _parse_ts(ev["ts"])
        horizon_end = ev_ts + horizon_min * 60
        new_line = ev["new_line"]
        direction = ev["direction"]

        # Collect all quotes from any book in the horizon window.
        future_lines: List[float] = []
        for book_key, series in all_series.items():
            if book_key[0] != player_l or book_key[1] != stat:
                continue
            for ts, line in series:
                if ev_ts < ts <= horizon_end:
                    future_lines.append(line)

        if not future_lines:
            continue
        total += 1
        max_future = max(future_lines)
        min_future = min(future_lines)
        if direction == "up" and max_future > new_line:
            continued += 1
        elif direction == "down" and min_future < new_line:
            continued += 1

    pct = continued / total if total else None
    return {
        "total_evaluable": total,
        "continued": continued,
        "continuation_pct": round(pct * 100, 1) if pct is not None else None,
        "target_pct": 60,
        "pass": pct is not None and pct >= 0.60,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Steam detector")
    parser.add_argument("--tick-once", action="store_true",
                        help="Run one tick and exit (print events)")
    parser.add_argument("--date", default=None,
                        help="Override date (YYYY-MM-DD)")
    parser.add_argument("--backtest", action="store_true",
                        help="Run backtest continuation check after tick-once")
    args = parser.parse_args()

    if args.tick_once:
        date = args.date or _slate_date()
        print(f"Running steam detector tick-once for date={date}")
        events = _run_tick_once(date=date, verbose=True)
        print(f"\n--- {len(events)} event(s) emitted ---")
        if args.backtest and events:
            result = _backtest_continuation(events, date)
            print(f"\nBacktest continuation (30-min horizon):")
            print(json.dumps(result, indent=2))
        # Dedup check: second run should emit 0.
        print("\n--- Dedup check (second run, expect 0 events) ---")
        events2 = _run_tick_once(date=date, verbose=False)
        print(f"Second run emitted {len(events2)} event(s) (expected 0 if any fired above)")
    else:
        asyncio.run(run_steam_detector())
