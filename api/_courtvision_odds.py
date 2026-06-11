"""_courtvision_odds.py — multi-book odds consolidator + public-API helpers.

Reads per-book CSVs at data/lines/<date>_<book>.csv (written by parallel_scraper)
and merges them into one consolidated view grouped by (player, stat, line).

Per-book CSV schema:
    captured_at, book, game_id, player_id, player_name, stat, line,
    over_price, under_price, start_time[, book_selection_id_over, book_selection_id_under]

The optional book_selection_id_over/under columns are written only by DK, FD, and PB
scrapers (v2+). Old CSVs without those columns parse fine — the fields default to "".

Public API:
    consolidate(date)        -> list[ConsolidatedProp]
    consolidate_for_slate(date) -> list[dict]  # grouped-by-(player,stat,line) shape
                                                # matching api._courtvision_data.load_lines_csv
    odds_envelope(date)      -> dict   # the /api/odds/{date}.json response
"""
from __future__ import annotations

import csv
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


def _strip_accents(s: str) -> str:
    """Remove combining diacritics from *s* (NFKD → drop combining marks).

    Mirrors src.data.live._strip_accents so accent-insensitive name matching
    works without importing a module that pulls in heavy ML deps.

    Examples:
        "Nikola Jokić"      → "Nikola Jokic"
        "Luka Dončić"       → "Luka Doncic"
        "Kristaps Porziņģis" → "Kristaps Porzingis"
    """
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


try:
    from api._deeplinks import book_deeplink as _book_deeplink
except ImportError:
    try:
        from _deeplinks import book_deeplink as _book_deeplink
    except ImportError:
        def _book_deeplink(book, prop, side="OVER", stake=10.0):  # type: ignore[misc]
            return {"web_url": "", "app_url": None}

_LINES_DIR = Path(__file__).resolve().parent.parent / "data" / "lines"
_ROSTER_PATH = Path(__file__).resolve().parent.parent / "data" / "players_nba_active.json"
_GAMES_LOOKUP_PATH = Path(__file__).resolve().parent.parent / "data" / "cache" / "games_lookup.json"

# ── Sliding-window CSV discovery (Bug 2 fix) ──────────────────────────────────
# Scrapers write CSVs under TODAY's date (e.g. 2026-05-27_dk.csv) but rows
# inside may reference future start_times (e.g. 2026-05-29T00:40:00Z).
# We read all CSVs from the last 7 days and filter per-row by start_time[:10].
_CSV_LOOKBACK_DAYS = 7

# ── Game-ID alias table (Bug 1 fix) ───────────────────────────────────────────
# DK / PB / KAMBI / oddsapi all use different numeric/hash IDs for the same
# NBA matchup. We resolve any incoming game_id to its canonical
# (away_abbr, home_abbr, start_date) tuple so filtering is matchup-scoped,
# not ID-scoped.
_GAME_ALIAS_CACHE: dict | None = None
_GAME_ALIAS_MTIME: float = 0.0

# ── NBA-roster filter ─────────────────────────────────────────────────────────
# Loaded once per process; empty set = no filtering (safe fallback when file
# is missing or unreadable).
_NBA_PLAYER_SET: set[str] | None = None


def _load_nba_players() -> set[str]:
    """Return de-accented lowercase NBA active-player names.

    Stored as ``_strip_accents(name).lower()`` so ASCII sportsbook names
    ("Nikola Jokic") match accented roster entries ("Nikola Jokić") via the
    same de-accent transform on the book side.  Cached for the process lifetime.
    """
    global _NBA_PLAYER_SET
    if _NBA_PLAYER_SET is None:
        try:
            with _ROSTER_PATH.open(encoding="utf-8") as f:
                _NBA_PLAYER_SET = {
                    _strip_accents(n).lower().strip()
                    for n in json.load(f) if n
                }
        except (OSError, ValueError, TypeError):
            _NBA_PLAYER_SET = set()  # fallback: no filtering
    return _NBA_PLAYER_SET


def reload_nba_roster() -> int:
    """Force-reload the roster from disk. Returns size of the new set.

    Called by the nightly refresh task after scripts/refresh_nba_roster.py
    rewrites players_nba_active.json.
    """
    global _NBA_PLAYER_SET, _ABBREV_INDEX
    _NBA_PLAYER_SET = None
    _ABBREV_INDEX = None
    s = _load_nba_players()
    return len(s)


# ── Abbreviated-name index (Bug 7) ────────────────────────────────────────────
# Keyed by (first_initial_lower, surname_lower) -> list[canonical_full_name_lower]
# Used to resolve "S. Gilgeous-Alexander" -> "shai gilgeous-alexander" when
# exactly ONE roster player matches initial+surname (safe; ties → no mapping).
_ABBREV_INDEX: dict[tuple[str, str], list[str]] | None = None


def _load_abbrev_index() -> dict[tuple[str, str], list[str]]:
    """Build (or return cached) abbreviated-name index from the NBA roster."""
    global _ABBREV_INDEX
    if _ABBREV_INDEX is not None:
        return _ABBREV_INDEX
    roster = _load_nba_players()
    idx: dict[tuple[str, str], list[str]] = defaultdict(list)
    for name in roster:
        parts = name.split()
        if len(parts) >= 2:
            initial = parts[0][0]  # first character of first name, already lowercase
            # Surname = everything after the first token, joined (handles hyphenated).
            surname = " ".join(parts[1:])
            idx[(initial, surname)].append(name)
    _ABBREV_INDEX = dict(idx)
    return _ABBREV_INDEX


def _canonicalize_book_player(player: str) -> str:
    """Return the canonical roster player name for a book's player string.

    Two normalizations (Bug 6 + 7):
      1. Strip a trailing team-disambiguation suffix: "Jaylin Williams (OKC)" ->
         "Jaylin Williams".  DraftKings and some other books append the team
         abbreviation in parentheses to disambiguate common names.
      2. Resolve an abbreviated first name "X. Surname" to the unique canonical
         full name from the roster, e.g. "S. Gilgeous-Alexander" ->
         "shai gilgeous-alexander".  Only maps when EXACTLY ONE roster player
         matches (initial, surname) — if two players share initial+surname we
         keep the string as-is so no wrong-player mapping can occur.

    Returns the transformed name (possibly equal to the input if neither rule
    fires).  The caller must still apply `.lower()` and check roster membership.
    """
    # Rule 1: strip trailing (TEAM) suffix, e.g. "(OKC)" / "(LAL)"
    player = re.sub(r"\s*\([A-Z]{2,4}\)\s*$", "", player).strip()

    # Rule 2: abbreviated first name "X. Rest Of Name"
    abbrev_match = re.match(r"^([A-Za-z])\.\s+(\S.*)$", player)
    if abbrev_match:
        initial = abbrev_match.group(1).lower()
        surname_raw = abbrev_match.group(2).strip().lower()
        idx = _load_abbrev_index()
        candidates = idx.get((initial, surname_raw), [])
        if len(candidates) == 1:
            # Unique match — safe to resolve.  Return the canonical roster form
            # (lowercase, as stored in the index) so the caller's .lower() is
            # a no-op and the roster membership check succeeds.
            return candidates[0]
        # Zero or multiple matches → keep current (possibly stripped) name.

    return player


_BOOK_DISPLAY = {
    "pin": "Pinnacle", "bov": "Bovada", "fd": "FanDuel", "pp": "PrizePicks",
    "dk": "DraftKings", "mgm": "BetMGM", "caesars": "Caesars",
    "betrivers": "BetRivers", "espnbet": "ESPN BET", "pointsbet": "PointsBet",
    "fanatics": "Fanatics", "bet365": "Bet365", "underdog": "Underdog",
    "hardrock": "Hard Rock Bet", "betonline": "BetOnline",
    "dk_inplay": "DraftKings (Live)", "fd_inplay": "FanDuel (Live)",
}
_VALID_STATS = {"pts", "reb", "ast", "fg3m", "stl", "blk", "tov"}
# Bookkey suffixes / fragments to exclude from auto-discovery (synthetic and
# companion files written alongside the real per-book CSVs).
# "_inplay" excluded so fd_inplay/dk_inplay CSVs (written by the WS in-play
# scraper) never leak into the pregame consolidate/consolidate_for_slate views.
# The dedicated _load_inplay_line_history in courtvision_router globs
# "{date}_*inplay*.csv" directly and is unaffected by this list.
_EXCLUDED_BOOK_SUFFIXES = ("_mainline", "_wnba_synthetic", "_inplay")
# Books explicitly excluded from consolidated odds (lines too off-market to
# trust). Bovada posts late and stays wide vs sharp books.
# mgm/caesars/fanatics dropped 2026-05-30: no live scraper (were odds-api only),
# so their CSVs go stale — excluded "for now" until a direct scraper feeds them.
# fd (FanDuel) dropped 2026-06-10: the live-reachable FD endpoint
# (sbapi.nj…/content-managed-page?customPageId=nba) only publishes ONE-SIDED
# "X+" threshold/milestone markets (TO_SCORE_25+_POINTS etc.) — there is NO Under
# side in the response, so under_price is always empty and consolidate_for_slate
# defaults it to a phantom −110. That is a fake two-sided quote at a threshold
# line that doesn't match the consensus mainline, so FanDuel is removed from the
# two-sided consolidator entirely rather than shown as −110-for-everything. DK and
# Pinnacle supply genuine two-sided prices. Re-enable ONLY if a real FD O/U feed
# (paired Over/Under runners at a single mainline) is wired up.
_EXCLUDED_BOOKS = {"bov", "mgm", "caesars", "fanatics", "fd"}


def _book_csv_paths(date: str) -> list[Path]:
    """All per-book CSVs written on `date` that exist on disk.

    Returns only files with the exact `<date>_<book>.csv` prefix.
    Used by line_history and line_moves which need the raw file stream;
    most callers should use _book_csv_paths_window() instead.
    """
    out: list[Path] = []
    prefix = f"{date}_"
    if not _LINES_DIR.exists():
        return out
    for p in _LINES_DIR.iterdir():
        if not p.is_file() or p.suffix != ".csv":
            continue
        name = p.stem
        if not name.startswith(prefix):
            continue
        book = name[len(prefix):]
        if not book:
            continue
        if any(book.endswith(s) for s in _EXCLUDED_BOOK_SUFFIXES):
            continue
        if book in _EXCLUDED_BOOKS:
            continue
        out.append(p)
    return out


def _book_csv_paths_window(date: str) -> list[Path]:
    """CSVs from the last _CSV_LOOKBACK_DAYS that MAY contain rows for `date`.

    Scrapers write under today's filename (e.g. 2026-05-27_dk.csv) for games
    scheduled on future dates (e.g. start_time=2026-05-29). This function
    returns all per-book CSVs from the last 7 days so callers can filter
    per-row by start_time[:10] == date.

    Callers must still filter rows; this returns the broader file set.
    """
    if not _LINES_DIR.exists():
        return []
    try:
        target = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return _book_csv_paths(date)  # fallback for unexpected formats

    seen: dict[str, Path] = {}  # stem -> path; last writer wins per book
    for offset in range(_CSV_LOOKBACK_DAYS):
        d = (target - timedelta(days=offset)).strftime("%Y-%m-%d")
        for p in _book_csv_paths(d):
            # Key by book suffix so we keep only the most-recent file per book.
            book_key = p.stem[len(d) + 1:]  # strip "<date>_"
            if book_key not in seen:
                seen[book_key] = p
    return list(seen.values())


def _load_game_aliases() -> dict:
    """Load games_lookup.json and build a map of game_id -> canonical group.

    Returns {game_id: {"away_abbr", "home_abbr", "start_date", "canonical_ids"}}
    where canonical_ids is the frozenset of all IDs that share the same matchup.
    Cached until the file's mtime changes.
    """
    global _GAME_ALIAS_CACHE, _GAME_ALIAS_MTIME
    if not _GAMES_LOOKUP_PATH.exists():
        return {}
    try:
        mt = _GAMES_LOOKUP_PATH.stat().st_mtime
        if _GAME_ALIAS_CACHE is not None and mt <= _GAME_ALIAS_MTIME:
            return _GAME_ALIAS_CACHE
        with _GAMES_LOOKUP_PATH.open(encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (OSError, ValueError):
        return _GAME_ALIAS_CACHE or {}

    # Group all IDs that share (away_abbr, home_abbr, start_date).
    groups: dict[tuple, list[str]] = defaultdict(list)
    for gid, info in raw.items():
        away = info.get("away_abbr") or ""
        home = info.get("home_abbr") or ""
        st = (info.get("start_time") or "")[:10]
        groups[(away, home, st)].append(gid)

    alias: dict[str, dict] = {}
    for (away, home, st), ids in groups.items():
        id_set = frozenset(ids)
        for gid in ids:
            alias[gid] = {
                "away_abbr": away,
                "home_abbr": home,
                "start_date": st,
                "canonical_ids": id_set,
            }

    _GAME_ALIAS_CACHE = alias
    _GAME_ALIAS_MTIME = mt
    return alias


def resolve_game_id(game_id: str) -> dict:
    """Resolve any sportsbook game_id to its canonical matchup group.

    Returns {"away_abbr", "home_abbr", "start_date", "canonical_ids"} or {}
    when the ID is not in games_lookup.json.
    """
    return _load_game_aliases().get(str(game_id), {})


def _to_int(s) -> int | None:
    if s is None or s == "":
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _to_odds(s) -> int | None:
    """Parse an American-odds cell, rejecting invalid magnitudes (|odds| < 100,
    e.g. a scraped/glitch 0). Returning None here keeps a bad cell out of the
    consolidate/grade pipeline (a 0 would beat every minus-money book in the
    best-price max() and crash the payout division 10000/abs(0)); the `or -110`
    fallback in consolidate_for_slate then substitutes the even-money default."""
    v = _to_int(s)
    return v if (v is None or abs(v) >= 100) else None


def _to_float(s) -> float | None:
    if s is None or s == "":
        return None
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # filter NaN


def _et_date_of_start_time(iso_ts: str) -> str:
    """Convert a UTC start_time to its America/New_York YYYY-MM-DD date.
    Identical helper to api.courtvision_router._et_date_from_iso, kept
    local to avoid a circular import."""
    if not iso_ts or len(iso_ts) < 10:
        return ""
    try:
        try:
            from zoneinfo import ZoneInfo
            _ET = ZoneInfo("America/New_York")
        except Exception:
            _ET = None
        norm = iso_ts.replace("Z", "+00:00")
        # ── CV_DK_FRACSEC_FIX (default ON; set =0 to disable) ──
        # DraftKings start_times carry 7 fractional-second digits
        # ('...:00.0000000Z') which datetime.fromisoformat() rejects in
        # py<3.11, so the parse fails and we fall back to the raw UTC prefix
        # (iso_ts[:10]) — mis-bucketing DK night games to the next ET day
        # (8:30 PM ET tip stored as next-day UTC). Truncate fractional
        # seconds to <=6 digits (microseconds); harmless for 0/3/6-digit
        # inputs. Overridable: CV_DK_FRACSEC_FIX=0 restores the old behavior.
        import os as _os
        if _os.environ.get("CV_DK_FRACSEC_FIX", "1") != "0":
            norm = re.sub(r"(\.\d{6})\d+", r"\1", norm)
        if "+" not in norm[10:] and norm.count("-") < 3:
            norm += "+00:00"
        dt = datetime.fromisoformat(norm).astimezone(timezone.utc)
        if _ET is not None:
            return dt.astimezone(_ET).strftime("%Y-%m-%d")
        return (dt + timedelta(hours=-4)).strftime("%Y-%m-%d")
    except Exception:
        return iso_ts[:10]


def read_book_csv(path: Path, start_date: str | None = None) -> list[dict]:
    """Parse a single <date>_<book>.csv. Yields the *latest* quote per
    (player, stat, line, book) so the line-shop view is freshness-correct.

    When `start_date` is provided (YYYY-MM-DD), only rows whose start_time
    falls on that ET CALENDAR DATE are included. NBA games are scheduled
    in ET; a 7:00 PM ET tip lives as `YYYY-MM-DDT23:00Z`, so filtering
    by UTC date silently misclassifies tonight's game as tomorrow's.
    """
    latest: dict[tuple, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # ── start_time ET-date filter (replaces UTC string prefix) ──
            if start_date is not None:
                row_st = (r.get("start_time") or "").strip()
                if _et_date_of_start_time(row_st) != start_date:
                    continue
            stat = (r.get("stat") or "").lower()
            if stat not in _VALID_STATS:
                continue
            line = _to_float(r.get("line"))
            if line is None:
                continue
            book = (r.get("book") or path.stem.split("_")[-1]).lower()
            # Canonical-book exclusion (chokepoint). A book's rows carry book="fd"
            # even inside companion files like <date>_fd_ws.csv whose FILENAME
            # suffix ("fd_ws") slips past the _book_csv_paths name filter — so we
            # also drop excluded books HERE, by the row's own canonical book key.
            # (FanDuel is excluded: threshold-only, one-sided, no real Under.)
            if (book in _EXCLUDED_BOOKS
                    or (book.endswith("_ws") and book[:-3] in _EXCLUDED_BOOKS)):
                continue
            player = (r.get("player_name") or "").strip()
            if not player:
                continue
            # Bug 6 + 7: canonicalize the book's player name before roster
            # filter and prop_key construction so that:
            #   - "Jaylin Williams (OKC)" → "Jaylin Williams" (team-suffix strip)
            #   - "S. Gilgeous-Alexander" → "shai gilgeous-alexander" (abbrev resolve)
            # _canonicalize_book_player may return a lowercase canonical name
            # (when the abbreviated-name resolver fires) or the stripped/original
            # mixed-case name.  We normalise to lowercase for the roster check.
            player = _canonicalize_book_player(player)
            # Drop non-NBA players (WNBA bleed, etc.) when roster file is present.
            # Roster is stored de-accented; compare using the same transform so
            # ASCII book names ("Nikola Jokic") match accented roster entries
            # ("Nikola Jokić" → "nikola jokic" in the set).
            _roster = _load_nba_players()
            if _roster and _strip_accents(player).lower() not in _roster:
                continue
            key = (_strip_accents(player).lower(), stat, round(line, 2), book)
            existing = latest.get(key)
            captured_at = r.get("captured_at") or ""
            if existing and existing["captured_at"] >= captured_at:
                continue
            latest[key] = {
                "captured_at": captured_at,
                "book": book,
                "player": player,
                "player_id": _to_int(r.get("player_id")),
                "stat": stat,
                "line": line,
                "over_price": _to_odds(r.get("over_price")),
                "under_price": _to_odds(r.get("under_price")),
                "game_id": r.get("game_id") or "",
                "start_time": r.get("start_time") or "",
                # Deeplink selection IDs — DK/FD write bet-slip outcomeIds;
                # BR/PIN/PB write event or outcome IDs used for event-page links.
                # Empty string when column absent (old CSVs / Bovada).
                "selection_id_over": r.get("book_selection_id_over") or "",
                "selection_id_under": r.get("book_selection_id_under") or "",
            }
    return list(latest.values())


_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SEC = 30.0  # 30s — scrapers tick every 10s but CSV reads at that rate
                        # caused 74s page loads in prod (O(files) I/O per request).
                        # 30s is still fresh enough for line-shop display.

# Bug 10 fix — stale pregame quote guard.
# The 7-day lookback window (_book_csv_paths_window) can surface quotes captured
# 24-30 h ago as "current" because the sliding window has no per-row age cap.
# Drop any pregame book quote older than this threshold so stale prices cannot
# reach best_price / EV calculations.  Set to 24 h: catches the documented
# multi-day-stale (24-30 h, scraper-down) case while NEVER dropping a legitimate
# same-day pregame capture (slates are built same-day and books post lines hours-
# to-a-day ahead, so an early-morning quote for a night game must survive). 6 h
# was too tight. Quotes with an unparseable captured_at are kept (safe fallback).
_MAX_PREGAME_QUOTE_AGE_SEC: float = 24 * 3600  # 24 hours

# ── Steam (sharp-money) lookup cache ──────────────────────────────────────────
# steam_events.jsonl is appended by scripts/steam_detector.py whenever 3+ books
# move a (player, stat) line in the same direction within a tight window.
# steam_lookup(date) returns a {(player_lower, stat_lower, line_rounded): event}
# map so other endpoints (e.g. /api/lines/scan) can join steam onto each prop
# without re-reading the file per-row. Cache TTL is short so the badge ages out
# naturally within ~30s of the configured 10-min staleness threshold.
_STEAM_CACHE: dict[tuple, tuple[float, dict]] = {}
_STEAM_CACHE_TTL = 30.0  # seconds
_STEAM_PATH = Path(__file__).resolve().parent.parent / "data" / "cache" / "steam_events.jsonl"


def steam_lookup(date: str) -> dict[tuple, dict]:
    """Return {(player_lower, stat_lower, line_rounded): steam_event_dict}.

    Reads ``data/cache/steam_events.jsonl`` (one JSON object per line, appended
    by the steam-detector job). Keeps events whose ``ts`` is within the last
    hour. Each event is indexed under BOTH its ``old_line`` and ``new_line``
    so that joining onto sportsbook rows works regardless of whether the row
    still shows the pre- or post-move line.

    Each returned value contains::
        {
          "age_sec":   int — seconds since the steam ts
          "direction": "up" | "down" | side string
          "magnitude": numeric — n_books_moving (or |new-old| as fallback)
          "book":      "pin" | "dk" | ... (representative book, prefer pin)
          "from_price": old_line value
          "to_price":   new_line value
          "confidence": "high" | "medium" | "low" | None
          "pin_moved":  bool | None
        }

    Cached for ``_STEAM_CACHE_TTL`` seconds per ``date`` key. Returns ``{}``
    when the jsonl file is missing or unreadable — the caller can treat
    "no steam" as the default state.
    """
    import json as _json
    import time as _time
    from datetime import datetime as _dt

    ck = ("steam_lookup", date)
    ent = _STEAM_CACHE.get(ck)
    if ent and _time.time() - ent[0] < _STEAM_CACHE_TTL:
        return ent[1]

    out: dict[tuple, dict] = {}
    if not _STEAM_PATH.exists():
        _STEAM_CACHE[ck] = (_time.time(), out)
        return out

    now_unix = _time.time()
    cutoff = now_unix - 3600  # keep last hour
    try:
        with _STEAM_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = _json.loads(line)
                except Exception:
                    continue
                ts = e.get("ts") or e.get("timestamp") or e.get("captured_at")
                ts_unix: float | None = None
                if isinstance(ts, (int, float)):
                    ts_unix = float(ts)
                elif isinstance(ts, str):
                    try:
                        ts_unix = _dt.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        ts_unix = None
                if ts_unix is None or ts_unix < cutoff:
                    continue

                player = (e.get("player") or e.get("player_name") or "").lower().strip()
                stat = (e.get("stat") or "").lower().strip()
                if not player or not stat:
                    continue

                old_line = e.get("old_line")
                new_line = e.get("new_line")
                single_line = e.get("line")

                # Magnitude — prefer explicit, else n_books_moving, else |delta|
                magnitude = e.get("magnitude") or e.get("delta") or e.get("n_books_moving")
                if magnitude is None and old_line is not None and new_line is not None:
                    try:
                        magnitude = abs(float(new_line) - float(old_line))
                    except Exception:
                        magnitude = None

                # Representative book — prefer pin if it moved, else first detail book
                book = e.get("book")
                if not book:
                    details = e.get("books_detail") or []
                    if e.get("pin_moved") and any(d.get("book") == "pin" for d in details):
                        book = "pin"
                    elif details:
                        book = details[0].get("book")

                rec = {
                    "age_sec":    int(max(0, now_unix - ts_unix)),
                    "direction":  e.get("direction") or e.get("side"),
                    "magnitude":  magnitude,
                    "book":       book,
                    "from_price": e.get("from_price", old_line),
                    "to_price":   e.get("to_price", new_line),
                    "confidence": e.get("confidence"),
                    "pin_moved":  e.get("pin_moved"),
                    "_ts_unix":   ts_unix,
                }

                # Index under every plausible line value for this event.
                line_vals: list[float] = []
                for lv in (single_line, old_line, new_line):
                    if lv is None:
                        continue
                    try:
                        line_vals.append(round(float(lv), 2))
                    except Exception:
                        continue
                if not line_vals:
                    continue

                for lr in set(line_vals):
                    key = (player, stat, lr)
                    prior = out.get(key)
                    if prior and prior.get("_ts_unix", 0) >= ts_unix:
                        continue
                    out[key] = rec
    except OSError:
        pass

    _STEAM_CACHE[ck] = (_time.time(), out)
    return out


def consolidate(date: str) -> list[dict]:
    """Return all (player, stat, line) props with the per-book ladder attached.

    Cached for 30s per date — covers the burst of requests from /tonight,
    /odds, /arbs, /api/odds/best, etc. all hitting the same date.

    Bug 2 fix — sliding-window file discovery:
    Reads CSVs from the last 7 days and filters rows by start_time[:10]==date.
    This handles scrapers that write today's file (2026-05-27_dk.csv) for
    games scheduled on a future date (start_time=2026-05-29T00:40:00Z).
    Existing callers are unaffected: consolidate('2026-05-27') returns props
    whose start_time date is 2026-05-27, exactly as before.

    Cross-file freshest-wins merge (WS + HTTP additive):
    When both an HTTP scraper file (<date>_dk.csv) and a WebSocket file
    (<date>_dk_ws.csv) exist for the same book, rows for the same
    (player, stat, line, book) are deduplicated across files, keeping
    only the row with the freshest captured_at.  This means a sub-second
    WS quote beats a 20s-old HTTP quote automatically, and if the WS feed
    is down the HTTP quote remains — no "_ws" book key ever leaks into the
    books list because the row's canonical `book` column ("dk"/"fd"/
    "betrivers") is used as the dedup key, not the filename suffix.
    """
    cached = _CACHE.get(date)
    if cached and time.time() - cached[0] < _CACHE_TTL_SEC:
        return cached[1]

    # Two-level structure: prop_key -> book -> freshest book entry dict.
    # Using an intermediate book_latest dict ensures cross-file freshest-wins
    # before we flatten to the final books list.
    grouped: dict[tuple, dict] = {}
    # book_latest[(prop_key, canonical_book)] = (captured_at, book_entry_dict)
    book_latest: dict[tuple, tuple] = {}
    # Graceful-stale-fallback holding pen: freshest age-capped quote per
    # (prop_key, book). Only consulted when the age cap empties the ENTIRE
    # date — never mixed with fresh quotes.
    stale_latest: dict[tuple, tuple] = {}

    for path in _book_csv_paths_window(date):
        for row in read_book_csv(path, start_date=date):
            # Use de-accented-lower as the canonical join key so accented cache
            # names ("Nikola Jokić") and ASCII book names ("Nikola Jokic") both
            # map to the same prop_key ("nikola jokic", stat, line).
            prop_key = (_strip_accents(row["player"]).lower(), row["stat"], round(row["line"], 2))
            base = grouped.setdefault(prop_key, {
                "player": row["player"], "player_id": row["player_id"],
                "stat": row["stat"], "line": row["line"],
                "game_id": row["game_id"], "start_time": row["start_time"],
                "books": [],
            })
            # Build a minimal prop dict for the deeplink generator.
            # Include player so books without event-page IDs can fall back to player search.
            _dl_prop = {
                "game_id": row.get("game_id") or "",
                "player": row.get("player") or "",
                "selection_id_over": row.get("selection_id_over") or "",
                "selection_id_under": row.get("selection_id_under") or "",
            }
            _dl_over  = _book_deeplink(row["book"], _dl_prop, side="OVER")
            _dl_under = _book_deeplink(row["book"], _dl_prop, side="UNDER")
            entry = {
                "book": row["book"], "display": _BOOK_DISPLAY.get(row["book"], row["book"]),
                "over_price": row["over_price"], "under_price": row["under_price"],
                "captured_at": _normalize_ts(row["captured_at"]),
                # Deeplink IDs — DK/FD: bet-slip outcomeIds; BR/PIN/PB: event IDs
                "selection_id_over": row.get("selection_id_over") or "",
                "selection_id_under": row.get("selection_id_under") or "",
                # Pre-built deeplink URLs for the /odds UI
                "deeplink_over_web":  _dl_over["web_url"],
                "deeplink_over_app":  _dl_over["app_url"] or "",
                "deeplink_under_web": _dl_under["web_url"],
                "deeplink_under_app": _dl_under["app_url"] or "",
            }
            # Bug 10 fix — drop stale pregame quotes exceeding _MAX_PREGAME_QUOTE_AGE_SEC.
            # The 7-day lookback window can surface prices captured 24-30 h ago;
            # dropping them here prevents stale quotes reaching best_price/EV.
            # Unparseable captured_at timestamps are kept (safe fallback).
            # Stale quotes are parked in stale_latest (freshest-wins) so the
            # graceful fallback below can resurrect them — tagged lines_stale —
            # when the cap would otherwise empty a date that HAD raw rows.
            _cap_ts = _parse_ts(entry["captured_at"])
            bl_key = (prop_key, row["book"])
            if _cap_ts is not None and (time.time() - _cap_ts) > _MAX_PREGAME_QUOTE_AGE_SEC:
                sp = stale_latest.get(bl_key)
                if sp is None or entry["captured_at"] >= sp[0]:
                    stale_latest[bl_key] = (entry["captured_at"], entry, prop_key)
                continue
            # Cross-file freshest-wins: only keep the freshest captured_at per
            # (prop_key, canonical_book).  This deduplicates HTTP vs WS files
            # for the same book so no duplicate "dk" / "fd" entries appear in
            # the books list — the WS (sub-second) quote wins when fresher.
            #
            # Bug 3 fix — preserve HTTP selection IDs when WS row wins on price:
            # WS files lack book_selection_id_over/under columns (default ""),
            # so when the fresher WS row displaces an older HTTP row that carried
            # non-empty selection IDs, we inherit those IDs into the winner and
            # recompute the deeplink URLs so addToBetslip deep links are kept.
            prior = book_latest.get(bl_key)
            if prior is None or entry["captured_at"] >= prior[0]:
                if prior is not None:
                    prior_entry = prior[1]
                    # Inherit selection IDs from the prior (older) entry when
                    # the incoming winner has empty IDs but prior has non-empty.
                    inherited = False
                    if (not entry["selection_id_over"]
                            and prior_entry.get("selection_id_over")):
                        entry["selection_id_over"] = prior_entry["selection_id_over"]
                        inherited = True
                    if (not entry["selection_id_under"]
                            and prior_entry.get("selection_id_under")):
                        entry["selection_id_under"] = prior_entry["selection_id_under"]
                        inherited = True
                    # Recompute deeplinks so they reflect the inherited IDs.
                    if inherited:
                        _dl_prop2 = {
                            "game_id": row.get("game_id") or "",
                            "player": row.get("player") or "",
                            "selection_id_over": entry["selection_id_over"],
                            "selection_id_under": entry["selection_id_under"],
                        }
                        _dl_over2  = _book_deeplink(row["book"], _dl_prop2, side="OVER")
                        _dl_under2 = _book_deeplink(row["book"], _dl_prop2, side="UNDER")
                        entry["deeplink_over_web"]  = _dl_over2["web_url"]
                        entry["deeplink_over_app"]  = _dl_over2["app_url"] or ""
                        entry["deeplink_under_web"] = _dl_under2["web_url"]
                        entry["deeplink_under_app"] = _dl_under2["app_url"] or ""
                book_latest[bl_key] = (entry["captured_at"], entry, prop_key)

    # ── Graceful stale fallback ───────────────────────────────────────────
    # If the age cap emptied a date that HAD raw rows (e.g. 34-38h-old Finals
    # lines, scraper not re-run on game day), re-include the freshest stale
    # quote per (player, stat, line, book) rather than returning an empty
    # slate. Every prop is tagged lines_stale=True and captured_at is kept
    # untouched so freshest_book_age_min drives the existing "lines stale"
    # pill downstream. Never fires when ANY fresh quote survived the cap.
    lines_stale = False
    if not book_latest and stale_latest:
        book_latest = stale_latest
        lines_stale = True

    # Flatten the freshest-per-book entries back onto each prop's books list.
    for (_prop_key, _book), (_cap, _entry, _pk) in book_latest.items():
        grouped[_pk]["books"].append(_entry)

    out = list(grouped.values())
    for prop in out:
        prop["n_books"] = len(prop["books"])
        prop["books"].sort(key=lambda b: b["book"])
        if lines_stale:
            prop["lines_stale"] = True
    out.sort(key=lambda p: (p["player"], p["stat"], p["line"]))
    _CACHE[date] = (time.time(), out)
    return out


def consolidate_for_slate(date: str) -> list[dict]:
    """Drop-in replacement for load_lines_csv. Same shape it produces:
    one row per (player, stat, line) with `books: [{book, over_odds, under_odds, captured_at}]`.
    `captured_at` is preserved so downstream mainline pickers can prefer
    fresh lines over stale ones. `game_id` is preserved so the pregame
    synthesis can group bets by the line's actual game (otherwise every
    synth bet inherits the recent-slate game_id and the home-page card
    can't find its top edges)."""
    out: list[dict] = []
    for prop in consolidate(date):
        out.append({
            "player": prop["player"], "stat": prop["stat"], "line": prop["line"],
            "opp": "", "venue": "",  # not in scrape CSVs; courtvision_data falls back
            "game_id": prop.get("game_id") or "",
            # True when the stale-fallback served age-capped quotes; consumers
            # must quarantine (stale pill, EV labeled indicative, paper only).
            "lines_stale": bool(prop.get("lines_stale")),
            "books": [{
                "book": _BOOK_DISPLAY.get(b["book"], b["book"]),
                "over_odds": b["over_price"] if b["over_price"] is not None else -110,
                "under_odds": b["under_price"] if b["under_price"] is not None else -110,
                "captured_at": b.get("captured_at") or "",
            } for b in prop["books"] if b["over_price"] or b["under_price"]],
        })
    return [p for p in out if p["books"]]


# Books surfaced in the per-book quote picker (the /api/slate book_quotes
# contract). Keyed by canonical book key -> frontend display name.
# FanDuel removed 2026-06-10: its live feed is threshold-only (one-sided, no
# Under) so it cannot produce a real two-sided per-book quote — see the
# _EXCLUDED_BOOKS note above. Only DK + Pinnacle expose genuine O/U prices.
_QUOTE_BOOKS: dict[str, str] = {
    "dk": "DraftKings", "pin": "Pinnacle",
}


def book_quotes_by_player_stat(date: str) -> dict[tuple, dict]:
    """Return the FRESHEST quote from each DK/FD/Pin book per (player, stat),
    at THAT book's OWN line (lines may differ between books).

    This powers the slate ``book_quotes`` contract — the DK/FD/Pin book picker
    must work even when each book posts a DIFFERENT line than the consensus
    mainline. consolidate() groups by (player, stat, LINE), so a book quoting
    23.5 when the mainline is 24.5 is invisible to a per-line join; here we
    collapse ACROSS lines and keep, per book, the freshest captured_at quote
    (with its own line + over/under American odds).

    Returns::
        {(player_deaccent_lower, stat_lower): {
            "DraftKings": {"line": 24.5, "over": -115, "under": -105,
                           "captured_at": "..."},
            "FanDuel":    {...},
            "Pinnacle":   {...},
        }}

    Books with no quote for a (player, stat) are simply absent. Reuses the
    30s-cached consolidate() so this adds no extra CSV I/O on a warm cache.
    """
    out: dict[tuple, dict] = {}
    for prop in consolidate(date):
        key = (_strip_accents(prop["player"]).lower(), prop["stat"])
        per_book = out.setdefault(key, {})
        line = prop["line"]
        for b in prop["books"]:
            disp = _QUOTE_BOOKS.get(b["book"])
            if disp is None:
                continue  # only DK/FD/Pin in the picker contract
            over = b.get("over_price")
            under = b.get("under_price")
            if over is None and under is None:
                continue
            cap = b.get("captured_at") or ""
            prev = per_book.get(disp)
            # Freshest-wins across lines for this book.
            if prev is not None and (prev.get("captured_at") or "") >= cap:
                continue
            per_book[disp] = {
                "line": line,
                "over": over,
                "under": under,
                "captured_at": cap,
            }
    return out


def summary(date: str) -> dict:
    """One-shot snapshot: counts + freshness for the day. Use for status checks."""
    f = freshness(date)
    props = consolidate(date)
    by_stat: dict[str, int] = defaultdict(int)
    for p in props:
        by_stat[p["stat"]] += 1
    return {
        "date": date,
        "n_props": len(props),
        "n_books": f["n_books"],
        "books": list(f["books"].keys()),
        "n_props_per_stat": dict(by_stat),
        "freshness_by_book": {b: info.get("latest_capture", "")
                              for b, info in f["books"].items()},
    }


def games_index(date: str) -> list[dict]:
    """Distinct games in today's scrape with prop counts + start_time.

    Groups all sportsbook game_ids that map to the same NBA matchup
    (via games_lookup.json) so the index has one entry per real game,
    not one per sportsbook ID. The canonical_game_id is the first ID
    alphabetically among the group; all alias IDs are listed too.

    Post-grouping merge: scrapers that don't expose NBA-canonical game IDs
    (KAMBI hex hashes, etc.) produce groups keyed by their raw ID with
    empty team abbrs. When such a group's start_time matches a resolved
    group on the same date (±5 min), the unresolved group is folded into
    the resolved one so the home page sees one card per real game, not
    one per sportsbook ID flavor.
    """
    props = consolidate(date)
    aliases = _load_game_aliases()
    # Group by canonical matchup key; fall back to raw game_id when not in lookup.
    by_matchup: dict[tuple, dict] = {}
    for p in props:
        gid = p.get("game_id") or "?"
        info = aliases.get(gid, {})
        if info:
            key = (info["away_abbr"], info["home_abbr"], info["start_date"])
        else:
            key = (gid, "", "")
        g = by_matchup.setdefault(key, {
            "start_time": p.get("start_time") or "",
            "n_props": 0,
            "players": set(),
            "game_ids": set(),
        })
        g["n_props"] += 1
        g["players"].add(p["player"])
        g["game_ids"].add(gid)

    # ── merge unresolved groups into resolved ones by start_time ─────
    resolved_by_st: dict[str, tuple] = {}  # start_time_minute -> matchup key
    for (away, home, _), g in by_matchup.items():
        if away and home:  # resolved
            st = (g.get("start_time") or "")[:16]  # minute precision
            if st:
                resolved_by_st.setdefault(st, (away, home, _))
    merged_keys: list[tuple] = []
    for key, g in list(by_matchup.items()):
        away, home, _sd = key
        if home:  # already resolved
            continue
        st_min = (g.get("start_time") or "")[:16]
        if not st_min:
            continue
        target_key = resolved_by_st.get(st_min)
        if target_key is None:
            continue
        target = by_matchup.get(target_key)
        if target is None or target_key == key:
            continue
        target["n_props"] += g["n_props"]
        target["players"] |= g["players"]
        target["game_ids"] |= g["game_ids"]
        merged_keys.append(key)
    for k in merged_keys:
        by_matchup.pop(k, None)

    # ── second pass: merge remaining UNRESOLVED groups with each other ───
    # When games_lookup is stale for the whole slate there are ZERO resolved
    # groups and the fold above is a no-op -> one card per book event id.
    # Player-set overlap is the discriminator (NOT start-minute alone:
    # regular-season slates share tip minutes). Canonical id = a resolved
    # 004... id when any member alias resolves (re-key to the resolved
    # matchup), else the sorted-first id via the ids[0] pick below.
    unresolved_keys = [k for k in by_matchup if not (k[1] or "")]
    absorbed: set = set()
    for i, ka in enumerate(unresolved_keys):
        if ka in absorbed:
            continue
        a = by_matchup.get(ka)
        if not a:
            continue
        for kb in unresolved_keys[i + 1:]:
            if kb in absorbed:
                continue
            b = by_matchup.get(kb)
            if not b:
                continue
            pa = a.get("players") or set()
            pb = b.get("players") or set()
            if not pa or not pb:
                continue
            shared = len(pa & pb)
            union = len(pa | pb)
            if shared >= 3 or (union and shared / union >= 0.3):
                a["n_props"] += b.get("n_props", 0)
                a["players"] |= pb
                a["game_ids"] |= b.get("game_ids", set())
                if not a.get("start_time"):
                    a["start_time"] = b.get("start_time") or ""
                absorbed.add(kb)
        # If any member id resolves in the lookup, adopt the resolved key so
        # the card gets real abbrs (and folds into the resolved group if one
        # already exists for that matchup).
        info = next((aliases[g] for g in sorted(a.get("game_ids") or ())
                     if g in aliases and aliases[g].get("home_abbr")), None)
        if info:
            rk = (info["away_abbr"], info["home_abbr"], info["start_date"])
            if rk != ka:
                tgt = by_matchup.get(rk)
                if tgt is not None:
                    tgt["n_props"] += a.get("n_props", 0)
                    tgt["players"] |= a.get("players") or set()
                    tgt["game_ids"] |= a.get("game_ids") or set()
                    if not tgt.get("start_time"):
                        tgt["start_time"] = a.get("start_time") or ""
                else:
                    by_matchup[rk] = a
                absorbed.add(ka)
    for k in absorbed:
        by_matchup.pop(k, None)

    out = []
    for (away, home, _), g in by_matchup.items():
        ids = sorted(g["game_ids"])
        out.append({
            "game_id": ids[0],  # stable canonical pick
            "game_id_aliases": ids,
            "away_abbr": away or ids[0],
            "home_abbr": home,
            "start_time": g["start_time"],
            "n_props": g["n_props"],
            "n_players": len(g["players"]),
        })
    out.sort(key=lambda r: r["start_time"] or "")
    return out


def _normalize_ts(s: str) -> str:
    """Normalize any ISO-8601 variant to YYYY-MM-DDTHH:MM:SSZ (UTC, with seconds).

    Handles the three formats found in the wild:
      2026-05-28T02:20+00:00       (offset, no seconds)
      2026-05-28T02:21:14          (no offset, has seconds — treated as UTC)
      2026-05-28T02:20             (no offset, no seconds — treated as UTC)
    Returns the input unchanged if it cannot be parsed.
    """
    if not s:
        return s
    try:
        # Normalize the Z suffix so fromisoformat can handle it on Py3.9
        normalized = s.replace("Z", "+00:00")
        # If no offset marker present, assume UTC
        if "+" not in normalized[10:] and normalized.count("-") < 3:
            normalized = normalized + "+00:00"
        dt = datetime.fromisoformat(normalized)
        # Convert to UTC and format without microseconds
        utc = dt.astimezone(timezone.utc)
        return utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, AttributeError):
        return s


def odds_envelope(date: str) -> dict:
    """Shape for /api/odds/{date}.json."""
    props = consolidate(date)
    books_seen = sorted({b["book"] for p in props for b in p["books"]})
    # Per-book freshness: latest captured_at seen in this date's data.
    book_last_seen: dict[str, str] = {}
    for p in props:
        for b in p["books"]:
            ts = b.get("captured_at") or ""
            if not ts:
                continue
            if ts > book_last_seen.get(b["book"], ""):
                book_last_seen[b["book"]] = ts
    return {
        "date": date,
        "generated_at": _normalize_ts(datetime.now(timezone.utc).isoformat()),
        # True when the graceful stale fallback served age-capped quotes.
        "lines_stale": any(p.get("lines_stale") for p in props),
        "n_props": len(props),
        "n_books": len(books_seen),
        "books": [{"id": b, "display": _BOOK_DISPLAY.get(b, b),
                   "last_scrape": _normalize_ts(book_last_seen.get(b, ""))}
                  for b in books_seen],
        "props": props,
    }


def best_price(prop: dict, side: str) -> dict | None:
    """Find the most favorable book on a given side. Higher American odds = better."""
    key = "over_price" if side.upper() == "OVER" else "under_price"
    books = [b for b in prop.get("books", []) if b.get(key) is not None]
    if not books:
        return None
    return max(books, key=lambda b: b[key])


def filter_props(props: Iterable[dict], stat: str | None = None,
                 player: str | None = None) -> list[dict]:
    out = []
    for p in props:
        if stat and p["stat"] != stat.lower():
            continue
        if player and player.lower() not in p["player"].lower():
            continue
        out.append(p)
    return out


def odds_env(date: str, stat: str = "", player: str = "") -> dict:
    """Build the /api/odds/{date}.json envelope with optional filters."""
    env = odds_envelope(date)
    if stat or player:
        env["props"] = filter_props(env["props"], stat=stat or None, player=player or None)
        env["n_props"] = len(env["props"])
    return env


def _american_to_implied(odds: int) -> float:
    """No-vig single-line implied probability from American odds."""
    if odds >= 100:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def line_moves(date: str, window_minutes: int = 60) -> list[dict]:
    """Detect props whose median line moved within `window_minutes` ago.

    Returns rows showing earliest and latest line per (player, stat, book) and
    the delta. Sorted by absolute delta descending. Useful for live-day alerts.
    """
    cutoff_dt = datetime.now(timezone.utc).timestamp() - window_minutes * 60
    # Series of (captured_at, book, player, stat, line) — read all CSV rows
    quotes: dict[tuple, list[tuple]] = defaultdict(list)
    for path in _book_csv_paths(date):
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                stat = (r.get("stat") or "").lower()
                player = (r.get("player_name") or "").strip()
                if not player or stat not in _VALID_STATS:
                    continue
                line = _to_float(r.get("line"))
                ts = r.get("captured_at") or ""
                if line is None or not ts:
                    continue
                book = (r.get("book") or path.stem.split("_")[-1]).lower()
                quotes[(player, stat, book)].append((ts, line))
    out: list[dict] = []
    for (player, stat, book), series in quotes.items():
        series.sort()
        if len(series) < 2:
            continue
        # earliest in-window vs latest
        in_window = [(t, l) for t, l in series
                     if _parse_ts(t) and _parse_ts(t) >= cutoff_dt]
        if len(in_window) < 2:
            continue
        first_ts, first_line = in_window[0]
        last_ts, last_line = in_window[-1]
        if first_line == last_line:
            continue
        out.append({
            "player": player, "stat": stat, "book": book,
            "display": _BOOK_DISPLAY.get(book, book),
            "line_open": first_line, "line_close": last_line,
            "delta": round(last_line - first_line, 2),
            "ts_open": first_ts, "ts_close": last_ts,
        })
    out.sort(key=lambda r: -abs(r["delta"]))
    return out


def _parse_ts(ts: str) -> float | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        try:
            return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc).timestamp()
        except (TypeError, ValueError):
            return None


def freshness(date: str) -> dict:
    """Per-book CSV mtime + latest captured_at + row count.

    Uses _book_csv_paths_window so future-date games (stored under today's
    scrape-date filename) are counted correctly.

    WS files (<date>_dk_ws.csv) are folded into their canonical book ("dk")
    so the freshness report shows one entry per real book, preferring the
    freshest captured_at across HTTP and WS files.
    """
    out: dict[str, dict] = {}
    for path in _book_csv_paths_window(date):
        raw_book = path.stem.split("_", 1)[-1].lower()  # strip date prefix
        # Strip _ws suffix so WS files fold into the canonical book name.
        book = raw_book[:-3] if raw_book.endswith("_ws") else raw_book
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime,
                                            tz=timezone.utc).isoformat()
        except OSError:
            mtime = None
        latest_capture = ""
        n_rows = 0
        try:
            with path.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    row_st = (r.get("start_time") or "").strip()
                    # Match on the ET CALENDAR DATE, not the raw UTC prefix.
                    # A 7:10 PM ET tip is stored as YYYY-MM-DDT00:10Z (next UTC
                    # day), so a naive startswith(date) silently reports 0 rows
                    # for tonight's slate — diverging from consolidate(), which
                    # uses _et_date_of_start_time. Keep the two in lockstep.
                    if _et_date_of_start_time(row_st) != date:
                        continue
                    n_rows += 1
                    ts = r.get("captured_at") or ""
                    if ts > latest_capture:
                        latest_capture = ts
        except OSError:
            pass
        if n_rows == 0:
            continue  # no rows for this date in this file — skip from report
        # Merge WS file into the same canonical book entry rather than
        # overwriting — keep the freshest latest_capture and sum n_rows so
        # the status report reflects both HTTP and WS data combined.
        existing = out.get(book)
        if existing is None:
            out[book] = {
                "display": _BOOK_DISPLAY.get(book, book),
                "csv_path": str(path.relative_to(path.parent.parent)),
                "csv_mtime_utc": mtime,
                "n_rows": n_rows,
                "latest_capture": latest_capture,
            }
        else:
            existing["n_rows"] += n_rows
            if latest_capture > existing["latest_capture"]:
                existing["latest_capture"] = latest_capture
            if mtime and (not existing["csv_mtime_utc"]
                          or mtime > existing["csv_mtime_utc"]):
                existing["csv_mtime_utc"] = mtime
    return {"date": date, "n_books": len(out), "books": out}


def consolidate_csv(date: str, stat: str | None = None,
                    player: str | None = None) -> str:
    """Render consolidated odds as a CSV string (one row per (player, stat, line, book))."""
    import io
    props = consolidate(date)
    if stat:
        props = [p for p in props if p["stat"] == stat.lower()]
    if player:
        player_l = player.lower()
        props = [p for p in props if player_l in p["player"].lower()]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "player", "stat", "line", "book", "over_price",
                "under_price", "captured_at"])
    for p in props:
        for b in p["books"]:
            w.writerow([date, p["player"], p["stat"], p["line"], b["book"],
                        b.get("over_price") or "", b.get("under_price") or "",
                        b.get("captured_at") or ""])
    return buf.getvalue()


_ARB_MAX_AGE_SEC = 300          # drop entire prop if all books stale (5 min)
_ARB_TIGHT_SEC   = 30           # both books within 30s → "tight"
_ARB_LOOSE_SEC   = 90           # both books within 90s → "loose"; >90s → "stale"


def _arb_quality(ts_a: str, ts_b: str) -> str:
    """Return "tight" / "loose" / "stale" based on capture-time gap between two books."""
    t_a, t_b = _parse_ts(ts_a), _parse_ts(ts_b)
    if t_a is None or t_b is None:
        return "stale"
    gap = abs(t_a - t_b)
    if gap <= _ARB_TIGHT_SEC:
        return "tight"
    if gap <= _ARB_LOOSE_SEC:
        return "loose"
    return "stale"


def cross_book_spread(date: str, min_spread_pp: float = 2.0,
                      max_age_sec: float = _ARB_MAX_AGE_SEC) -> list[dict]:
    """Props where books differ on implied prob — line shop / arb opportunities.

    Returns rows sorted by spread descending. `min_spread_pp` is the min
    spread in percentage points between best and worst book on either side.

    Arb quality tiers (added to each row):
        "tight"  — best-over and best-under books captured within 30 s of each other
        "loose"  — within 90 s
        "stale"  — >90 s gap; displayed but not recommended for betting
    Only rows with is_arb=True carry an arb_quality field.
    """
    props = consolidate(date)
    now_ts = time.time()
    out: list[dict] = []
    for p in props:
        if p["n_books"] < 2:
            continue
        all_books = p["books"]

        # Drop entire prop if all captures are older than max_age_sec.
        book_ts = [_parse_ts(b.get("captured_at") or "") for b in all_books]
        fresh_ts = [t for t in book_ts if t is not None]
        if not fresh_ts or (now_ts - max(fresh_ts)) > max_age_sec:
            continue

        # Only include books whose capture is within max_age_sec of the most-recent.
        max_book_ts = max(fresh_ts)
        fresh_books = [
            b for b, t in zip(all_books, book_ts)
            if t is not None and (max_book_ts - t) <= max_age_sec
        ]
        if len(fresh_books) < 2:
            continue

        over_books  = [b for b in fresh_books if b["over_price"]  is not None]
        under_books = [b for b in fresh_books if b["under_price"] is not None]
        over_implieds  = [_american_to_implied(b["over_price"])  for b in over_books]
        under_implieds = [_american_to_implied(b["under_price"]) for b in under_books]
        over_spread  = (max(over_implieds)  - min(over_implieds))  * 100 if len(over_implieds)  >= 2 else 0
        under_spread = (max(under_implieds) - min(under_implieds)) * 100 if len(under_implieds) >= 2 else 0
        max_spread = max(over_spread, under_spread)
        if max_spread < min_spread_pp:
            continue

        # Two-way arb: require BOTH sides have a price on at least one book each.
        # best implied = min implied prob (highest odds) per side.
        best_over_b  = min(over_books,  key=lambda b: _american_to_implied(b["over_price"]))  if over_books  else None
        best_under_b = min(under_books, key=lambda b: _american_to_implied(b["under_price"])) if under_books else None
        best_over_implied  = _american_to_implied(best_over_b["over_price"])   if best_over_b  else None
        best_under_implied = _american_to_implied(best_under_b["under_price"]) if best_under_b else None

        arb_sum = (best_over_implied + best_under_implied) * 100 \
                  if (best_over_implied is not None and best_under_implied is not None) else None

        # Bug 9 fix: compute arb_quality BEFORE setting is_arb so that we can
        # require the two legs to be within the tight/loose window.  The /spread
        # endpoint was displaying is_arb=True for over/under legs captured up to
        # _ARB_MAX_AGE_SEC (300s) apart — a stale mismatch that produces false
        # arb signals.  Now is_arb=True only when arb_sum<100 AND the leg
        # captures are "tight" or "loose" (both within 90s of each other).
        # The displayed spread numbers and arb_sum_pct are unchanged.
        _pre_arb_quality: str | None = None
        if (arb_sum is not None and arb_sum < 100.0
                and best_over_b is not None and best_under_b is not None):
            _pre_arb_quality = _arb_quality(
                best_over_b.get("captured_at") or "",
                best_under_b.get("captured_at") or "",
            )
        is_arb = (_pre_arb_quality in {"tight", "loose"})

        row: dict = {
            "player": p["player"], "stat": p["stat"], "line": p["line"],
            "n_books": p["n_books"], "over_spread_pp": round(over_spread, 2),
            "under_spread_pp": round(under_spread, 2),
            "arb_sum_pct": round(arb_sum, 2) if arb_sum is not None else None,
            "is_arb": is_arb, "books": all_books,
        }
        if is_arb and best_over_b is not None and best_under_b is not None:
            row["arb_quality"] = _pre_arb_quality
            row["arb_best_over_book"]  = best_over_b["book"]
            row["arb_best_under_book"] = best_under_b["book"]
        out.append(row)
    out.sort(key=lambda r: -max(r["over_spread_pp"], r["under_spread_pp"]))
    return out


def best_book_envelope(date: str) -> dict:
    """One row per (player, stat, line) with the best book per side highlighted."""
    props = consolidate(date)
    out = []
    for p in props:
        bo = best_price(p, "OVER")
        bu = best_price(p, "UNDER")
        out.append({
            "player": p["player"], "stat": p["stat"], "line": p["line"],
            "n_books": p["n_books"],
            "best_over": {"book": bo["display"], "price": bo["over_price"]} if bo else None,
            "best_under": {"book": bu["display"], "price": bu["under_price"]} if bu else None,
        })
    return {"date": date, "n_props": len(out), "props": out}


def line_history(date: str, player: str, stat: str) -> list[dict]:
    """All quotes for one (player, stat) across the day — every captured_at row.

    Returns rows sorted by captured_at, useful for plotting line movement.
    """
    player_l, stat_l = player.lower(), stat.lower()
    rows: list[dict] = []
    for path in _book_csv_paths(date):
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("player_name") or "").lower() != player_l:
                    continue
                if (r.get("stat") or "").lower() != stat_l:
                    continue
                rows.append({
                    "captured_at": r.get("captured_at"),
                    "book": (r.get("book") or path.stem.split("_")[-1]).lower(),
                    "line": _to_float(r.get("line")),
                    "over_price": _to_int(r.get("over_price")),
                    "under_price": _to_int(r.get("under_price")),
                })
    rows.sort(key=lambda r: (r["captured_at"] or "", r["book"]))
    return rows
