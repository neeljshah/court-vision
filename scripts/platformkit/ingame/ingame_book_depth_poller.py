"""scripts.platformkit.ingame.ingame_book_depth_poller -- LANE 3 depth poller entrypoint.

Split out of ingame_book_depth.py (which would otherwise exceed the 300 LOC cap)
so the discover+snapshot+sidecar-append orchestration and the bounded serve loop
+ CLI have their own small home. See ingame_book_depth.py's module docstring for
the full LANE 3 spec (venues, canonical row shape, stale_quote_flag rationale,
WIRE SPEC). This file OWNS the poller loop; snapshot builders live in
ingame_book_depth.py (snapshot_kalshi_market / snapshot_polymarket_token) and the
venue-specific fetch/parse live in ingame_book_depth_kalshi.py /
ingame_book_depth_poly.py.

Per-market snapshots are appended to data/cache/book_depth/<venue>/<date>.jsonl
via an atomic-enough (append-mode, best-effort) JSONL writer. Bounded per sport
(max_active_per_sport) so one wide sport cannot dominate a tick; bounded
overall (serve_bounded's duration_sec) so a live run always stops.

Kalshi trade tape (2026-07-09, execution-profile lane): _kd.snapshot_market
already fetches the trades endpoint for last_trade_ts/trades_last_5m recency;
it now also returns the normalized, watermark-deduped trades on two TRANSIENT
row keys ("_new_trades"/"_trade_watermark"). poll_kalshi_depth pops both off
before writing the depth row (its on-disk shape is unchanged) and appends each
new trade as its own line to the PARALLEL sidecar
data/cache/book_depth/kalshi_trades/<date>.jsonl -- same venue-subdir +
date-sharded jsonl convention as the depth sidecars, via the same
_sidecar_path/_append_jsonl helpers. Per-ticker watermark threads through
poll_once's *state* dict (mirrors kalshi_prev) so a repeated poll never
re-persists an already-seen trade.

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only;
stdlib + repo-internal only. No pip installs. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth_poller.py -q
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame import ingame_book_depth as _bd
from scripts.platformkit.ingame import ingame_book_depth_retention as _retention
from scripts.platformkit.odds_provider.http_cache import http_get_json
from scripts.platformkit.odds_provider.kalshi_series_spec import series_for
from scripts.platformkit.odds_provider.transport import resilient_get_json

logger = logging.getLogger(__name__)

HttpGet = Callable[[str], Any]


def _sidecar_path(venue: str, sidecar_dir: Optional[Path], now_dt: datetime) -> Path:
    base = Path(sidecar_dir) if sidecar_dir is not None else _bd.DEFAULT_SIDECAR_DIR
    return base / venue / ("%s.jsonl" % now_dt.strftime("%Y-%m-%d"))


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    """Best-effort append-only JSONL write. Never raises (a write failure never
    sinks the poll)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="ascii", errors="backslashreplace") as fh:
            fh.write(json.dumps(row, ensure_ascii=True))
            fh.write("\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_book_depth_poller sidecar write failed %s: %s", path, exc)


def _live_kalshi_tickers(sport: str, *, http: HttpGet, limit_per_series: int = 200) -> List[str]:
    """Discover currently-open Kalshi tickers for *sport* (READ-ONLY reuse of
    kalshi_series_spec.series_for; a bare /markets?series_ticker=...&status=open
    listing, mirroring inplay_kalshi's own discovery call). limit_per_series
    defaults to 200, SAME as inplay_kalshi.fetch_inplay's discovery call (one
    request per series either way) -- a small page here was the root cause of
    the live-day coverage gap (book_depth_livegap_diagnosis.md): a busy
    sport/series can have far more than a handful of markets open at once.
    Never raises."""
    out: List[str] = []
    for series, _market_type in series_for(sport):
        params = {"series_ticker": series, "status": "open", "limit": limit_per_series}
        url = "%s/markets?%s" % (_bd.KALSHI_BASE, urllib.parse.urlencode(params))
        try:
            body = http(url)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ingame_book_depth_poller discovery failed %s/%s: %s", sport, series, exc)
            continue
        markets = body.get("markets") if isinstance(body, dict) else None
        if not isinstance(markets, list):
            continue
        for m in markets:
            if isinstance(m, dict) and m.get("ticker"):
                out.append(str(m["ticker"]))
    return out


def poll_kalshi_depth(sports: List[str], *, http: HttpGet = resilient_get_json,
                      sidecar_dir: Optional[Path] = None,
                      now: Optional[Callable[[], datetime]] = None,
                      max_markets_per_sport: int = 100,
                      prev_by_ticker: Optional[Dict[str, Dict[str, Any]]] = None,
                      trade_watermark_by_ticker: Optional[Dict[str, str]] = None,
                      active_by_sport: Optional[Dict[str, List[str]]] = None,
                      miss_counts: Optional[Dict[str, int]] = None,
                      max_active_per_sport: int = 60, max_misses: int = 3,
                      ) -> Dict[str, Any]:
    """Discover + snapshot Kalshi depth across *sports*' open in-play tickers,
    appending each row to its date-sharded sidecar. Never raises: a per-market
    failure is skipped.

    STICKY RETENTION (2026-07-11 fix, gap zeta item 3; made DATE-AWARE
    2026-07-15, see book_depth_livegap_diagnosis.md): discovery is a bare
    /markets?status=open page with no guaranteed close_time sort, so a busy
    slate can push a ticker off the top-N window well before it settles.
    *active_by_sport* keeps every discovered ticker STICKY across polls until
    its OWN snapshot fails *max_misses* times (market genuinely closed),
    bounded by max_active_per_sport. On overflow, ingame_book_depth_retention.
    evict_over_cap sacrifices FUTURE-dated tickers (>1 day out) first, so a
    market stays tracked through its own game day regardless of how many
    further-out markets Kalshi has since opened -- previously blind-FIFO
    eviction dropped same-day tickers first since Kalshi opens them earliest
    (measured gap up to ~44h). A caller that does not thread active_by_sport
    (e.g. existing tests) is unaffected: the list starts empty and becomes
    this tick's (max_markets_per_sport-capped) discovery.

    Also persists the trades tape's actual prices (already fetched inside
    snapshot_kalshi_market for recency -- no extra request) to the parallel
    kalshi_trades sidecar, watermarked per ticker via *trade_watermark_by_ticker*
    so a repeated poll never re-writes an already-seen trade."""
    now_dt = (now() if now is not None else datetime.now(timezone.utc))
    prev_by_ticker = prev_by_ticker if prev_by_ticker is not None else {}
    trade_watermark_by_ticker = trade_watermark_by_ticker if trade_watermark_by_ticker is not None else {}
    active_by_sport = active_by_sport if active_by_sport is not None else {}
    miss_counts = miss_counts if miss_counts is not None else {}
    n_snapshotted = n_stale = n_trades = 0
    rows: List[Dict[str, Any]] = []
    for sport in sports:
        discovered = _retention.live_first(_live_kalshi_tickers(sport, http=http),
                                           now_dt, max_markets_per_sport)
        active = active_by_sport.setdefault(sport, [])
        # sticky tickers from a PRIOR tick that this tick's discovery page didn't
        # re-list -- appended (not merged in) so discovered's own count/order is
        # untouched (preserves existing single-tick callers' exact behavior).
        sticky_only = [t for t in active if t not in discovered]
        tickers = discovered + sticky_only
        for t in discovered:
            if t not in active:
                active.append(t)
            miss_counts[t] = 0  # rediscovered this tick -- reset any miss streak
        _retention.evict_over_cap(active, max_active_per_sport, now_dt)
        for ticker in tickers:
            row = _bd.snapshot_kalshi_market(ticker, http=http, now_dt=now_dt,
                                             prev=prev_by_ticker.get(ticker),
                                             trade_watermark=trade_watermark_by_ticker.get(ticker))
            if row is None:
                miss_counts[ticker] = miss_counts.get(ticker, 0) + 1
                if miss_counts[ticker] >= max_misses:
                    active.remove(ticker)
                    miss_counts.pop(ticker, None)
                continue
            new_trades = row.pop("_new_trades", [])
            next_watermark = row.pop("_trade_watermark", None)
            if next_watermark:
                trade_watermark_by_ticker[ticker] = next_watermark
            row["sport"] = sport
            prev_by_ticker[ticker] = row
            _append_jsonl(_sidecar_path("kalshi", sidecar_dir, now_dt), row)
            n_snapshotted += 1
            n_stale += int(bool(row.get("stale_quote_flag")))
            for trade in new_trades:
                trade_row = dict(trade)
                trade_row.update({"ts": row["ts"], "ticker": ticker, "sport": sport})
                _append_jsonl(_sidecar_path("kalshi_trades", sidecar_dir, now_dt), trade_row)
                n_trades += 1
            rows.append(row)
    return {"n_snapshotted": n_snapshotted, "n_stale": n_stale, "n_trades": n_trades,
            "rows": rows, "venue": "kalshi", "as_of": _bd._now_iso()}


def poll_polymarket_depth(slugs: List[str], *, http: HttpGet = http_get_json,
                          sidecar_dir: Optional[Path] = None,
                          now: Optional[Callable[[], datetime]] = None,
                          token_cache: Optional[Dict[str, str]] = None,
                          prev_by_token: Optional[Dict[str, Dict[str, Any]]] = None
                          ) -> Dict[str, Any]:
    """Snapshot Polymarket depth for each event *slugs* (resolve-once token cache
    threaded in by the caller so a repeated poll never re-resolves a known slug).
    Never raises: a per-slug failure is skipped."""
    now_dt = (now() if now is not None else datetime.now(timezone.utc))
    token_cache = token_cache if token_cache is not None else {}
    prev_by_token = prev_by_token if prev_by_token is not None else {}
    n_snapshotted = n_stale = 0
    rows: List[Dict[str, Any]] = []
    for slug in slugs:
        token = token_cache.get(slug)
        if token is None:
            token = _bd.resolve_polymarket_token(slug, http=http)
            if token is None:
                continue
            token_cache[slug] = token
        row = _bd.snapshot_polymarket_token(token, http=http, now_dt=now_dt,
                                            prev=prev_by_token.get(token))
        if row is None:
            continue
        row["slug"] = slug
        prev_by_token[token] = row
        _append_jsonl(_sidecar_path("polymarket", sidecar_dir, now_dt), row)
        n_snapshotted += 1
        n_stale += int(bool(row.get("stale_quote_flag")))
        rows.append(row)
    return {"n_snapshotted": n_snapshotted, "n_stale": n_stale, "rows": rows,
            "venue": "polymarket", "as_of": _bd._now_iso()}


def poll_once(*, sports: Optional[List[str]] = None,
             polymarket_slugs: Optional[List[str]] = None,
             sidecar_dir: Optional[Path] = None,
             kalshi_http: HttpGet = resilient_get_json,
             poly_http: HttpGet = http_get_json,
             now: Optional[Callable[[], datetime]] = None,
             state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """ONE bounded poll across both venues. *state* threads prev-snapshot maps +
    the Polymarket token cache across repeated calls (poller entrypoint owns
    it); a fresh call with state=None starts cold (no staleness on first tick).
    Never raises -- degrades to empty per-venue summaries."""
    st = state if state is not None else {}
    st.setdefault("kalshi_prev", {})
    st.setdefault("kalshi_trade_watermarks", {})
    st.setdefault("kalshi_active", {})
    st.setdefault("kalshi_misses", {})
    st.setdefault("poly_prev", {})
    st.setdefault("poly_tokens", {})
    k_summary = poll_kalshi_depth(sports or [], http=kalshi_http, sidecar_dir=sidecar_dir,
                                  now=now, prev_by_ticker=st["kalshi_prev"],
                                  trade_watermark_by_ticker=st["kalshi_trade_watermarks"],
                                  active_by_sport=st["kalshi_active"],
                                  miss_counts=st["kalshi_misses"])
    p_summary = poll_polymarket_depth(polymarket_slugs or [], http=poly_http,
                                      sidecar_dir=sidecar_dir, now=now,
                                      token_cache=st["poly_tokens"], prev_by_token=st["poly_prev"])
    return {"kalshi": k_summary, "polymarket": p_summary, "state": st}


def serve_bounded(*, sports: Optional[List[str]] = None,
                  polymarket_slugs: Optional[List[str]] = None,
                  interval_sec: float = 7.0, duration_sec: float = 120.0,
                  sidecar_dir: Optional[Path] = None,
                  clock: Optional[Callable[[float], None]] = None,
                  time_fn: Optional[Callable[[], float]] = None) -> Dict[str, Any]:
    """Poll on *interval_sec* pacing for a BOUNDED *duration_sec* window (default
    2min). Returns a run summary. *clock*/*time_fn* injectable for tests so the
    tested path never sleeps for real. Never raises across ticks."""
    sleep = clock if clock is not None else time.sleep
    tnow = time_fn if time_fn is not None else time.time
    state: Dict[str, Any] = {}
    start = tnow()
    n_ticks = total_snap = total_stale = 0
    while (tnow() - start) < duration_sec:
        try:
            hb = poll_once(sports=sports, polymarket_slugs=polymarket_slugs,
                          sidecar_dir=sidecar_dir, state=state)
            total_snap += hb["kalshi"]["n_snapshotted"] + hb["polymarket"]["n_snapshotted"]
            total_stale += hb["kalshi"]["n_stale"] + hb["polymarket"]["n_stale"]
        except Exception as exc:  # noqa: BLE001 -- one bad tick never stops the run
            logger.warning("ingame_book_depth_poller serve_bounded tick error: %s", exc)
        n_ticks += 1
        if (tnow() - start) >= duration_sec:
            break
        try:
            sleep(interval_sec)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingame_book_depth_poller serve_bounded sleep error: %s", exc)
    return {"n_ticks": n_ticks, "n_snapshotted": total_snap, "n_stale": total_stale,
           "measurement_only": True}


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: bounded run over given sports (default mlb,wnba) + optional --slugs."""
    import argparse
    ap = argparse.ArgumentParser(prog="ingame_book_depth_poller")
    ap.add_argument("--sports", default="mlb,wnba", help="comma sports")
    ap.add_argument("--slugs", default="", help="comma polymarket event slugs")
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--interval", type=float, default=7.0)
    args = ap.parse_args(argv)
    sports = [s.strip() for s in args.sports.split(",") if s.strip()]
    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
    summary = serve_bounded(sports=sports, polymarket_slugs=slugs,
                            interval_sec=args.interval, duration_sec=args.duration)
    print("ingame_book_depth_poller: %d ticks, %d snapshots, %d stale-flagged; measurement-only." % (
        summary["n_ticks"], summary["n_snapshotted"], summary["n_stale"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["poll_kalshi_depth", "poll_polymarket_depth", "poll_once", "serve_bounded", "main"]
