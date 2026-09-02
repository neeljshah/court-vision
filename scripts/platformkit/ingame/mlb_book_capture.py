"""Dense, measurement-only Kalshi MLB book capture for the POD.

Every venue request uses ``KalshiRateGovernor``'s existing ``depth_capture``
caller.  The module has no CLI: local authoring cannot accidentally start a
live loop.  Live archive writes require both POD environment flags; all other
calls write beneath the scratch tree.  Primary sources to re-fetch and archive:
https://docs.kalshi.com/getting_started/rate_limits
https://help.kalshi.com/en/articles/13823805-fees
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Iterable, List, Optional

from scripts.platformkit.ingame import game_pk_bridge_live as _bridge
from scripts.platformkit.ingame import gumbo_mlb_poller as _gumbo
from scripts.platformkit.odds_provider.kalshi_rate_governor import (
    before_request, get_governor, report_429,
)

_ROOT = Path(__file__).resolve().parents[3]
LIVE_ARCHIVE = _ROOT / "data" / "cache" / "ingame_books" / "mlb"
SCRATCH_ARCHIVE = _ROOT / "data" / "cache" / "ingame_books" / "_scratch" / "mlb"
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
TARGET_CADENCE_SEC = 5.0
MAX_CADENCE_SEC = 60.0
IDLE_CHECK_SEC = 30.0
BRIDGE_TTL_SEC_DEFAULT = 600.0  # ids are fixed for a game's lifetime; env CV_MLB_BRIDGE_TTL_SEC
PRE_REGISTERED_UNIT = 1.0  # contracts; fixed at authoring, never tuned from capture data
MIN_SNAPSHOTS = 200
MAX_FETCH_CONCURRENCY = 4  # ponytail: upgrade to 8 after the pod 30-pass evidence


def _iso(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def live_archive_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    """True only for the explicitly designated POD writer."""
    values = env if env is not None else os.environ
    return values.get("CV_CAPTURE_POD") == "1" and values.get("CV_MLB_BOOK_ARCHIVE_LIVE") == "1"


def archive_path(now: datetime, env: Optional[Dict[str, str]] = None) -> Path:
    """Date-sharded live path on the POD, scratch path everywhere else."""
    root = LIVE_ARCHIVE if live_archive_enabled(env) else SCRATCH_ARCHIVE
    return root / (now.strftime("%Y-%m-%d") + ".jsonl")


def _append(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="ascii", errors="backslashreplace") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def _levels(body: Any) -> Dict[str, List[List[Any]]]:
    """Return the complete raw price/size ladders; malformed sides become []."""
    book = body.get("orderbook_fp") if isinstance(body, dict) else None
    if not isinstance(book, dict):
        return {"yes": [], "no": []}
    out: Dict[str, List[List[Any]]] = {}
    for source, target in (("yes_dollars", "yes"), ("no_dollars", "no")):
        levels = book.get(source)
        out[target] = [list(x) for x in levels if isinstance(x, (list, tuple)) and len(x) >= 2] if isinstance(levels, list) else []
    return out


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def top_of_book_depth(levels: Dict[str, List[List[Any]]]) -> Optional[float]:
    """Combined displayed size at the best YES bid and best NO bid."""
    yes, no = levels.get("yes", []), levels.get("no", [])
    if not yes or not no:
        return None
    sizes = (_number(yes[-1][1]), _number(no[-1][1]))
    return None if None in sizes else float(sizes[0] + sizes[1])


def cell_table(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pre-registered per-game TRADEABLE_PAPER cell; records, never tunes."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("record_type") != "snapshot" or row.get("game_pk") is None:
            continue
        bucket = grouped.setdefault(str(row["game_pk"]), {"ts": set(), "depths": []})
        # One PASS is one snapshot even though it now writes one row per market
        # side -- counting rows would halve the pre-registered MIN_SNAPSHOTS bar.
        bucket["ts"].add(row.get("capture_ts"))
        depth = row.get("top_of_book_depth")
        if isinstance(depth, (int, float)):
            bucket["depths"].append(float(depth))
    out = []
    threshold = 5.0 * PRE_REGISTERED_UNIT
    for game_pk, bucket in sorted(grouped.items()):
        depths = bucket["depths"]
        ordered = sorted(depths)
        median = ordered[len(ordered) // 2] if ordered else None
        n = len(bucket["ts"])
        out.append({"game_pk": game_pk, "inplay_snapshots": n,
                    "median_top_of_book_depth": median,
                    "pre_registered_unit": PRE_REGISTERED_UNIT,
                    "depth_threshold": threshold,
                    "cell": "TRADEABLE_PAPER" if n >= MIN_SNAPSHOTS and median is not None and median >= threshold else "NOT_YET"})
    return out


class GovernedClient:
    """The only HTTP path: existing governor before every request, 429 reported."""

    def __init__(self, opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        self.governor = get_governor("depth_capture")
        self.opener = opener
        self.n_429 = 0
        self._governor_lock = Lock()

    def get(self, url: str) -> Optional[Any]:
        with self._governor_lock:
            before_request(self.governor, "mlb", n_active_sports=1)
        try:
            with self.opener(urllib.request.Request(url), timeout=15.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                with self._governor_lock:
                    self.n_429 += 1
                    report_429(self.governor)
            return None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None


def bridge_ttl_sec(env: Optional[Dict[str, str]] = None) -> float:
    values = env if env is not None else os.environ
    try:
        return float(values.get("CV_MLB_BRIDGE_TTL_SEC", BRIDGE_TTL_SEC_DEFAULT))
    except (TypeError, ValueError):
        return BRIDGE_TTL_SEC_DEFAULT


def resolve_market_tickers(client: GovernedClient, date_str: str, state: Dict[str, Any],
                           clock: Callable[[], float] = time.monotonic) -> Dict[str, Dict[str, Any]]:
    """game_pk -> {event_ticker, tickers}. THE one place capture resolves tickers.

    The bridge is the sole id source and it costs ~5.5s per build, so it is held
    for CV_MLB_BRIDGE_TTL_SEC (default 600s) rather than rebuilt every pass --
    a game's Kalshi ids do not change once its event is open.  Only per-side
    MARKET tickers are returned; the event stem has no orderbook (see
    game_pk_bridge_live._fetch_kalshi_markets)."""
    cached = state.get("bridge_cache")
    now = clock()
    if isinstance(cached, dict) and cached.get("date") == date_str \
            and now - cached.get("ts", 0.0) < bridge_ttl_sec():
        return cached["by_game_pk"]
    by_game_pk = {str(r.game_pk): {"event_ticker": r.kalshi_ticker_stem,
                                   "tickers": list(r.kalshi_market_tickers)}
                  for r in _bridge.build_bridge(date_str, http=client.get)}
    state["bridge_cache"] = {"date": date_str, "ts": now, "by_game_pk": by_game_pk}
    return by_game_pk


def live_gumbo_games(client: GovernedClient, date_str: str, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Use the established GUMBO path, then its unambiguous gamePk/ticker bridge."""
    games = _gumbo.list_live_game_pks(date_str, fetch_fn=client.get)
    state["n_live_games"] = len(games)
    if not games:
        return []  # no Kalshi discovery or orderbook calls outside a live window
    bridge = resolve_market_tickers(client, date_str, state)
    poller_state = state.setdefault("gumbo", {})
    out = []
    for game in games:
        game_pk = game.get("game_pk")
        ids = bridge.get(str(game_pk)) or {}
        if game_pk is None or not ids.get("tickers"):
            continue
        tick = _gumbo.poll_one_game(int(game_pk), poller_state, fetch_fn=client.get)
        if isinstance(tick, dict) and tick:
            out.append({"game_pk": str(game_pk), "event_ticker": ids.get("event_ticker"),
                        "tickers": list(ids["tickers"]), "game_state": tick})
    return out


def capture_once(*, client: Optional[GovernedClient] = None, date_str: Optional[str] = None,
                 now: Optional[datetime] = None, state: Optional[Dict[str, Any]] = None,
                 live_games_fn: Callable[[GovernedClient, str, Dict[str, Any]], List[Dict[str, Any]]] = live_gumbo_games,
                 output: Optional[Path] = None, max_concurrency: int = MAX_FETCH_CONCURRENCY) -> Dict[str, Any]:
    """Capture one full ladder per currently live, unambiguously bridged MLB game."""
    client = client or GovernedClient()
    state = state if state is not None else {}
    now = now or datetime.now(timezone.utc)
    date_str = date_str or now.strftime("%Y-%m-%d")
    prior_429 = client.n_429
    rows: List[Dict[str, Any]] = []
    fetches = [(game, str(ticker)) for game in live_games_fn(client, date_str, state)
               for ticker in (game.get("tickers") or []) if ticker]

    def fetch(item: Any) -> Any:
        game, ticker = item
        url = KALSHI_BASE + "/markets/" + urllib.parse.quote(ticker, safe="") + "/orderbook"
        try:
            return game, ticker, client.get(url), None
        except Exception as exc:  # a custom client must not erase one request from the pass
            return game, ticker, None, type(exc).__name__

    with ThreadPoolExecutor(max_workers=max(1, int(max_concurrency))) as executor:
        fetched = list(executor.map(fetch, fetches))
    for game, ticker, body, error in fetched:
        if body is None:
            rows.append({"record_type": "fetch_error", "venue": "kalshi", "sport": "mlb",
                         "game_pk": str(game.get("game_pk")), "ticker": ticker,
                         "event_ticker": game.get("event_ticker"), "capture_ts": _iso(now),
                         "error": error or "fetch_failed",
                         "derived_age_ceiling_sec": state.get("cadence_sec", TARGET_CADENCE_SEC)})
            continue
        levels = _levels(body)
        if not levels["yes"] and not levels["no"]:
            continue
        rows.append({"record_type": "snapshot", "venue": "kalshi", "sport": "mlb",
                     "game_pk": str(game.get("game_pk")), "ticker": ticker,
                     "event_ticker": game.get("event_ticker"),
                     "src_ts": game.get("game_state", {}).get("ts"), "capture_ts": _iso(now),
                     "game_state": game.get("game_state", {}), "yes_ladder": levels["yes"],
                     "no_ladder": levels["no"], "top_of_book_depth": top_of_book_depth(levels),
                     "derived_age_ceiling_sec": state.get("cadence_sec", TARGET_CADENCE_SEC)})
    n_429 = client.n_429 - prior_429
    cadence = float(state.get("cadence_sec", TARGET_CADENCE_SEC))
    if n_429:
        cadence = min(MAX_CADENCE_SEC, max(TARGET_CADENCE_SEC * 2.0, cadence * 2.0))
        state["cadence_sec"] = cadence
        rows.append({"record_type": "pressure", "capture_ts": _iso(now), "n_429": n_429,
                     "cadence_sec": cadence, "derived_age_ceiling_sec": cadence})
    else:
        state.setdefault("cadence_sec", TARGET_CADENCE_SEC)
    snapshot_history = state.setdefault("snapshots", [])
    snapshot_history.extend(row for row in rows if row.get("record_type") == "snapshot")
    destination = output or archive_path(now)
    for row in rows:
        _append(destination, row)
    return {"path": str(destination), "rows": rows, "cell_table": cell_table(snapshot_history),
            "cadence_sec": state["cadence_sec"], "n_429": n_429}


def run_pod_capture(*, stop: Callable[[], bool], sleep: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic,
                    output: Optional[Path] = None) -> Dict[str, Any]:
    """POD-only loop. It refuses to start unless the POD owns the live archive.

    DEADLINE PACING (2026-09-01): each tick sleeps only the RESIDUAL between its own
    start and start+period, so the achieved period is max(period, pass_duration) rather
    than period + pass_duration.  A pass that overruns its period simply starts the next
    one immediately -- no pile-up and no accumulated drift debt, because every deadline
    is anchored on that tick's own start, not on a running counter.
    Each tick appends ONE additive ``record_type='cadence'`` row to the SAME archive
    file (no second metrics file) carrying the measured wall latency and the achieved
    start-to-start cadence; that row is this loop's only liveness evidence when a slate
    yields zero snapshots.  Returns the last tick's cadence row."""
    if not live_archive_enabled():
        raise RuntimeError("live MLB archive requires CV_CAPTURE_POD=1 and CV_MLB_BOOK_ARCHIVE_LIVE=1")
    client: Any = GovernedClient()
    state: Dict[str, Any] = {}
    prev_start: Optional[float] = None
    beat: Dict[str, Any] = {}
    while not stop():
        started = clock()
        result = capture_once(client=client, state=state, output=output)
        period = float(state.get("cadence_sec", TARGET_CADENCE_SEC)) if state.get("n_live_games") else IDLE_CHECK_SEC
        beat = {"record_type": "cadence", "capture_ts": _iso(),
                "tick_latency_sec": round(clock() - started, 3),
                "achieved_cadence_sec": None if prev_start is None else round(started - prev_start, 3),
                "target_cadence_sec": period,
                "n_live_games": int(state.get("n_live_games") or 0),
                "n_snapshot_rows": sum(1 for r in result["rows"] if r.get("record_type") == "snapshot")}
        _append(Path(result["path"]), beat)
        prev_start = started
        sleep(max(0.0, started + period - clock()))
    return beat


__all__ = ["GovernedClient", "TARGET_CADENCE_SEC", "PRE_REGISTERED_UNIT", "archive_path",
           "bridge_ttl_sec", "capture_once", "cell_table", "live_archive_enabled",
           "resolve_market_tickers", "run_pod_capture", "top_of_book_depth"]
