"""scripts.platformkit.odds_provider.line_store -- PURE readers over line history.

Reads the append-only team-market history written by snapshot.write_quotes
(data/cache/line_history/<sport>/<date>.jsonl) and answers the three questions the
CLV pipeline (grade_paper) and the capture daemon need:

  * get_open(game_key)   -> earliest captured quote per (market_type, side).
  * get_close(game_key)  -> (quotes_by_market_side, is_true_close). is_true_close
                            is True ONLY if a quote was captured within the LOCK
                            WINDOW near tipoff (commence_time) -- a TRUE close
                            (clv_is_proxy=False). Otherwise the last-observed quote
                            is returned with is_true_close=False -- a PROXY
                            (clv_is_proxy=True). We NEVER fabricate a close.
  * get_latest(game_key) -> most recently captured quote per (market_type, side).

GAME_KEY (canonical, documented):
  A game_key is EITHER
    - a raw game_id string (the aggregate event_id), OR
    - a composite "sport|home|away|date" where date is the UTC YYYY-MM-DD of the
      slate (matches the file bucket snapshot uses).
  parse_game_key() accepts either form. A composite key with fewer parts is
  matched on whatever parts are present (sport+date narrows which files we scan;
  home/away match the row). A bare string with no '|' is treated as a game_id.

LOCK WINDOW: a quote captured within DEFAULT_LOCK_WINDOW_MIN minutes BEFORE
commence_time (and not after it) is "at lock" -> a true close. A row without a
commence_time can never be a true close (we cannot prove it was at lock). A
row with captured_at_suspect=True (markets.py's clock-trust guard tripped for
that tick) can ALSO never be at lock -- its own captured_at is not trusted
against commence_time -- so it is PROXY-only, same as a missing commence_time.

All readers return None / empty on missing history and NEVER raise.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; stdlib
only; no network; consistent JSONL shape with snapshot.write_quotes.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_line_store.py -q
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .snapshot import DEFAULT_HISTORY_DIR

logger = logging.getLogger(__name__)

# A quote captured within this many minutes BEFORE tipoff counts as "at lock"
# (a TRUE close). Widely enough to catch a final pre-tip tick; tight enough that
# a stale midday line is not mistaken for a close.
DEFAULT_LOCK_WINDOW_MIN = 30


@dataclass
class GameKey:
    """A parsed game_key. Either game_id is set, or the composite parts are."""

    game_id: Optional[str] = None
    sport: Optional[str] = None
    home: Optional[str] = None
    away: Optional[str] = None
    date: Optional[str] = None


def parse_game_key(game_key: str) -> GameKey:
    """Parse a canonical game_key (game_id OR 'sport|home|away|date'). Never raises."""
    s = str(game_key or "").strip()
    if not s:
        return GameKey()
    if "|" not in s:
        return GameKey(game_id=s)
    parts = [p.strip() for p in s.split("|")]
    # sport|home|away|date, tolerant of missing trailing parts.
    sport = parts[0] or None
    home = parts[1] if len(parts) > 1 and parts[1] else None
    away = parts[2] if len(parts) > 2 and parts[2] else None
    date = parts[3] if len(parts) > 3 and parts[3] else None
    return GameKey(sport=sport, home=home, away=away, date=date)


def _parse_ts(iso_ts: Any) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iter_files(key: GameKey, base: Path) -> List[Path]:
    """History files that could hold *key*'s rows. Narrow by sport+date when known."""
    if not base.exists():
        return []
    if key.sport:
        sport_dir = base / key.sport.lower()
        if not sport_dir.exists():
            return []
        if key.date:
            f = sport_dir / ("%s.jsonl" % key.date)
            return [f] if f.exists() else []
        return sorted(sport_dir.glob("*.jsonl"))
    # No sport hint (bare game_id): scan every sport's files.
    return sorted(base.glob("*/*.jsonl"))


def _row_matches(row: Dict[str, Any], key: GameKey) -> bool:
    """True if a history row belongs to *key*."""
    if key.game_id is not None:
        return str(row.get("game_id", "")) == key.game_id
    if key.home is not None and str(row.get("home", "")) != key.home:
        return False
    if key.away is not None and str(row.get("away", "")) != key.away:
        return False
    if key.sport is not None and str(row.get("sport", "")).lower() != key.sport.lower():
        return False
    return key.home is not None or key.away is not None


def _load_rows(game_key: str, base: Optional[Path]) -> List[Dict[str, Any]]:
    """Every history row for *game_key*, each tagged with a parsed _ts. Never raises."""
    root = Path(base) if base is not None else DEFAULT_HISTORY_DIR
    key = parse_game_key(game_key)
    if key.game_id is None and key.home is None and key.away is None:
        return []
    out: List[Dict[str, Any]] = []
    for f in _iter_files(key, root):
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # tolerate a partial trailing write
                    if not isinstance(row, dict) or not _row_matches(row, key):
                        continue
                    ts = _parse_ts(row.get("captured_at"))
                    if ts is None:
                        continue
                    row["_ts"] = ts
                    out.append(row)
        except OSError:
            continue
    return out


def _ms_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (str(row.get("market_type", "")), str(row.get("side", "")))


def _strip(row: Dict[str, Any]) -> Dict[str, Any]:
    """Drop the internal _ts before handing a row back to a caller."""
    return {k: v for k, v in row.items() if k != "_ts"}


def _pick_per_market_side(rows: List[Dict[str, Any]], *, latest: bool
                          ) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """earliest (open) or latest quote per (market_type, side). Empty -> {}."""
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        k = _ms_key(row)
        cur = best.get(k)
        if cur is None:
            best[k] = row
            continue
        if latest:
            if row["_ts"] >= cur["_ts"]:
                best[k] = row
        elif row["_ts"] < cur["_ts"]:
            best[k] = row
    return {k: _strip(v) for k, v in best.items()}


def get_open(game_key: str, *, base: Optional[Path] = None
             ) -> Optional[Dict[Tuple[str, str], Dict[str, Any]]]:
    """EARLIEST captured quote per (market_type, side) for *game_key*.

    Returns {(market_type, side): row} or None when no history exists. Never raises.
    """
    rows = _load_rows(game_key, base)
    if not rows:
        return None
    return _pick_per_market_side(rows, latest=False)


def get_latest(game_key: str, *, base: Optional[Path] = None
               ) -> Optional[Dict[Tuple[str, str], Dict[str, Any]]]:
    """MOST RECENT captured quote per (market_type, side). None on no history."""
    rows = _load_rows(game_key, base)
    if not rows:
        return None
    return _pick_per_market_side(rows, latest=True)


def get_latest_batch(sport: str, game_ids: Any, *, base: Optional[Path] = None
                     ) -> Dict[str, Dict[Tuple[str, str], Dict[str, Any]]]:
    """MOST RECENT quote per (market_type, side) for MANY game_ids in ONE pass.

    Like calling get_latest() once per bare game_id, but scans the sport's files a
    SINGLE time instead of once-per-game -- bare-id get_latest() (no sport hint)
    re-globs+re-parses EVERY sport's files per game (O(games x corpus) -> a
    full-slate board hang). This is O(corpus): one pass, indexed by game_id.
    Returns {game_id: {(market_type, side): row}}, games with no history absent.
    Pure on-disk read, no network; never raises."""
    want = {str(g) for g in (game_ids or [])}
    root = Path(base) if base is not None else DEFAULT_HISTORY_DIR
    sport_dir = root / str(sport).lower()
    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    if want and sport_dir.exists():
        for f in sorted(sport_dir.glob("*.jsonl")):
            try:
                with f.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        gid = str(row.get("game_id", "")) if isinstance(row, dict) else ""
                        if gid not in want:
                            continue
                        ts = _parse_ts(row.get("captured_at"))
                        if ts is None:
                            continue
                        row["_ts"] = ts
                        k = (gid, str(row.get("market_type", "")), str(row.get("side", "")))
                        cur = best.get(k)
                        if cur is None or ts >= cur["_ts"]:
                            best[k] = row
            except OSError:
                continue
    out: Dict[str, Dict[Tuple[str, str], Dict[str, Any]]] = {}
    for (gid, mtype, side), row in best.items():
        out.setdefault(gid, {})[(mtype, side)] = _strip(row)
    return out


def _within_lock(row: Dict[str, Any], window_min: int) -> bool:
    """True iff *row* was captured within window_min minutes BEFORE its tipoff.

    A row stamped captured_at_suspect=True (markets.py's clock-trust guard --
    its captured_at disagreed with the poller's own wall-clock by more than
    CAPTURED_AT_SUSPECT_WINDOW_SEC at capture time, e.g. an NTP step / VM
    resume mid-poll) can NEVER be "at lock": we cannot trust ITS captured_at
    against commence_time, so it is PROXY-only -- it may still surface as the
    last-observed close in get_close(), but it is never promoted to a TRUE
    close.
    """
    if row.get("captured_at_suspect"):
        return False
    commence = _parse_ts(row.get("commence_time"))
    if commence is None:
        return False
    captured = row.get("_ts")
    if captured is None:
        return False
    # at-lock: in [tip - window, tip]; not after tip (a post-tip price is live, not a close).
    return (commence - timedelta(minutes=window_min)) <= captured <= commence


def get_close(game_key: str, *, base: Optional[Path] = None,
              lock_window_min: int = DEFAULT_LOCK_WINDOW_MIN
              ) -> Optional[Tuple[Dict[Tuple[str, str], Dict[str, Any]], bool]]:
    """The closing quote per (market_type, side) and whether it is a TRUE close.

    Returns (quotes_by_market_side, is_true_close) or None on no history.
      * is_true_close=True  -> for EVERY market/side returned, the chosen quote was
        captured within the lock window before tip (clv_is_proxy=False).
      * is_true_close=False -> at least one market/side has no at-lock quote, so the
        LAST-OBSERVED quote is returned as a PROXY (clv_is_proxy=True).
    We never fabricate a close; a missing history yields None. Never raises.
    """
    rows = _load_rows(game_key, base)
    if not rows:
        return None
    by_ms: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        by_ms.setdefault(_ms_key(row), []).append(row)
    closes: Dict[Tuple[str, str], Dict[str, Any]] = {}
    all_true = True
    for k, group in by_ms.items():
        group.sort(key=lambda r: r["_ts"])
        at_lock = [r for r in group if _within_lock(r, lock_window_min)]
        if at_lock:
            closes[k] = _strip(at_lock[-1])  # latest at-lock quote = the close
        else:
            closes[k] = _strip(group[-1])    # last-observed = a proxy
            all_true = False
    return closes, all_true


__all__ = [
    "DEFAULT_LOCK_WINDOW_MIN",
    "GameKey",
    "parse_game_key",
    "get_open",
    "get_close",
    "get_latest",
    "get_latest_batch",
]
