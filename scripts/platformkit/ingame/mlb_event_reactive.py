"""scripts.platformkit.ingame.mlb_event_reactive -- MLB EVENT-REACTIVE PRODUCER (lane S6).

WHY THIS EXISTS
---------------
docs/research/organization-sprint/INGAME_CAPABILITY_2026-09-01.md: no sport is
EVENT_REACTIVE, and the reason is not that MLB is slow -- it is that NOTHING ON DISK
CARRIES A SOURCE TIMESTAMP. `inplay_tick_latency.measure_sport` computes lag only when a
row carries `src_ts`, and every existing tick writer emits our own capture clock only
(`ts`, `captured_at`). The event-reactive CONSUMER (`latency_scoreboard.
event_reactive_supported`, two-part gate lag_p90 <= 5.0s AND src_ts coverage >= 95.0%) is
wired and fail-closed; this module is the missing PRODUCER.

WHAT IT EMITS
-------------
One row per DISCRETE MLB event (not per poll pass), derived from the GUMBO payload the
repo already fetches (`gumbo_mlb_poller`, bootstrap + diffPatch):
  pitch          -- playEvents[].isPitch, stable uuid `playId`
  pa_end         -- a completed plate appearance (about.isComplete)
  run_scored     -- about.isScoringPlay on a completed play
  inning_change  -- first play of a new (inning, halfInning)

Row schema (consumer keys FIRST, they are what makes the gate measurable):
  sport, venue          -- latency_scoreboard.build_rows groups on these
  ts                    -- OUR detect wall-clock  (== detect_ts)
  src_ts                -- the FEED's own event wall-clock (== event_ts)
  event_ts, detect_ts, lag_ms, source_artifact, as_of, event_id, event_kind, game_id
`ts`/`src_ts` are deliberate aliases of detect_ts/event_ts so the EXISTING loader works
unmodified. lag_ms = detect_ts - event_ts, in milliseconds, signed and never clamped.

HONEST SCOPE: lag_ms is FEED-DETECTION latency (how long after MLB's own event clock we
observed the event). It is NOT a claim about beating any venue and not a $ edge. The
cross-venue finding in INGAME_CAPABILITY (median_lag 34.0s, the venue ahead of us in
129/135 = 95.6% of matched events) is unchanged by this module. PRIMING: the first pass
for a game seeds the dedupe set WITHOUT emitting, so a game's backlog of historical plays
never lands as fake multi-hour "lag" rows.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no data/registry write; no flag flip;
does not import or modify the book-capture loop, quote_freshness, or any ledger writer.

Per-file test: python -m pytest scripts/platformkit/ingame/test_mlb_event_reactive.py -q
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from scripts.platformkit.ingame import gumbo_mlb_poller as _poller

SPORT = "mlb"
VENUE = "mlb_gumbo"
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = _REPO_ROOT / "data" / "cache" / "event_reactive"
SOURCE_ARTIFACT = "statsapi.mlb.com/api/v1.1/game/%s/feed/live"
_TS_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(_TS_FMT)


def _parse(s: Any) -> Optional[datetime]:
    """Parse a GUMBO ISO timestamp (millisecond or microsecond precision). None on junk."""
    if not isinstance(s, str) or not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _parse_feed_ts(doc: Dict[str, Any]) -> Optional[datetime]:
    """GUMBO metaData.timeStamp ('20260901_231953'), 1s granularity. Measured
    2026-09-01: it tracks the NEWEST EVENT in the payload, NOT the publish instant."""
    meta = doc.get("metaData") if isinstance(doc, dict) else None
    raw = meta.get("timeStamp") if isinstance(meta, dict) else None
    try:
        return datetime.strptime(str(raw), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def extract_events(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Discrete events from one full GUMBO snapshot, oldest first. Never raises."""
    out: List[Dict[str, Any]] = []
    if not isinstance(doc, dict):
        return out
    game_pk = doc.get("gamePk") or (doc.get("gameData", {}) or {}).get("game", {}).get("pk")
    plays = ((doc.get("liveData") or {}).get("plays") or {}).get("allPlays") or []
    seen_halves: Set[str] = set()
    for play in plays:
        if not isinstance(play, dict):
            continue
        about = play.get("about") or {}
        idx = about.get("atBatIndex")
        half_key = "%s:%s" % (about.get("inning"), about.get("halfInning"))
        if half_key not in seen_halves:
            seen_halves.add(half_key)
            out.append({"event_id": "%s:half:%s" % (game_pk, half_key),
                        "event_kind": "inning_change", "game_id": str(game_pk),
                        "event_ts": about.get("startTime")})
        for ev in play.get("playEvents") or []:
            if not isinstance(ev, dict) or not ev.get("isPitch"):
                continue
            out.append({
                "event_id": str(ev.get("playId") or "%s:%s:%s" % (game_pk, idx, ev.get("index"))),
                "event_kind": "pitch", "game_id": str(game_pk),
                # endTime = the moment the pitch RESULT is known; startTime is the fallback
                "event_ts": ev.get("endTime") or ev.get("startTime")})
        if about.get("isComplete"):
            out.append({"event_id": "%s:pa:%s" % (game_pk, idx), "event_kind": "pa_end",
                        "game_id": str(game_pk), "event_ts": about.get("endTime")})
            if about.get("isScoringPlay"):
                out.append({"event_id": "%s:run:%s" % (game_pk, idx), "event_kind": "run_scored",
                            "game_id": str(game_pk), "event_ts": about.get("endTime")})
    return [e for e in out if _parse(e.get("event_ts")) is not None]


def build_rows(doc: Dict[str, Any], detect_ts: Optional[datetime] = None,
               seen: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Consumer-schema rows for the events in `doc` not already in `seen` (mutated)."""
    det = detect_ts or _now()
    det_s = _iso(det)
    seen = seen if seen is not None else set()
    feed = _parse_feed_ts(doc)
    rows: List[Dict[str, Any]] = []
    for ev in extract_events(doc):
        if ev["event_id"] in seen:
            continue
        seen.add(ev["event_id"])
        ets = _parse(ev["event_ts"])
        rows.append({
            "sport": SPORT, "venue": VENUE, "game_id": ev["game_id"],
            "ts": det_s, "src_ts": _iso(ets),        # <- the keys the consumer reads
            "detect_ts": det_s, "event_ts": _iso(ets),
            "lag_ms": int(round((det - ets).total_seconds() * 1000.0)),
            # NOT a publish-vs-poll split (feed_stamp_delta_ms is ~0 by construction, see
            # _parse_feed_ts): observe_lag_ms bundles server staleness AND our poll wait.
            "feed_ts": _iso(feed) if feed else None,
            "feed_stamp_delta_ms": int(round((feed - ets).total_seconds() * 1000.0)) if feed else None,
            "observe_lag_ms": int(round((det - feed).total_seconds() * 1000.0)) if feed else None,
            "event_id": ev["event_id"], "event_kind": ev["event_kind"],
            "source_artifact": SOURCE_ARTIFACT % ev["game_id"], "as_of": det_s,
        })
    return rows


def _game_path(out_dir: Path, game_id: str) -> Path:
    return Path(out_dir) / SPORT / ("%s.jsonl" % game_id)


def seen_ids(out_dir: Path, game_id: str) -> Set[str]:
    """event_ids already on disk for a game -- makes a replay/restart idempotent."""
    out: Set[str] = set()
    try:
        with open(_game_path(out_dir, game_id), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.add(str(json.loads(line)["event_id"]))
                except (ValueError, KeyError, TypeError):
                    continue  # a torn/partial trailing line is skipped, never fatal
    except OSError:
        return out
    return out


def append_rows(rows: Iterable[Dict[str, Any]], out_dir: Path = DEFAULT_OUT_DIR) -> int:
    """Append-only write, one os-level write() per game per pass.
    ponytail: single-writer atomicity (O_APPEND + one write); add a lock if a second
    producer process is ever pointed at the same store."""
    by_game: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_game.setdefault(str(r.get("game_id")), []).append(r)
    n = 0
    for game_id, grp in by_game.items():
        path = _game_path(out_dir, game_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = "".join(json.dumps(r, sort_keys=True) + "\n" for r in grp)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(blob)
        n += len(grp)
    return n


def _pct(vals: List[float], pct: float) -> Optional[float]:
    if not vals:
        return None
    return round(sorted(vals)[min(int(pct * len(vals)), len(vals) - 1)], 2)


def summarize(out_dir: Path = DEFAULT_OUT_DIR, last_n: int = 1000) -> Dict[str, Any]:
    """p50/p90 lag_ms over the last N rows of the store. Never raises."""
    rows: List[Dict[str, Any]] = []
    base = Path(out_dir) / SPORT
    files = sorted(base.glob("*.jsonl")) if base.is_dir() else []
    for path in files:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        except (OSError, ValueError):
            continue
    rows = [r for r in rows if isinstance(r, dict) and isinstance(r.get("lag_ms"), (int, float))]
    rows.sort(key=lambda r: str(r.get("detect_ts", "")))
    tail = rows[-max(1, int(last_n)):]
    lags = [float(r["lag_ms"]) for r in tail]
    kinds: Dict[str, int] = {}
    for r in tail:
        kinds[str(r.get("event_kind"))] = kinds.get(str(r.get("event_kind")), 0) + 1
    feed_lags = [float(r["feed_stamp_delta_ms"]) for r in tail
                 if isinstance(r.get("feed_stamp_delta_ms"), (int, float))]
    poll_lags = [float(r["observe_lag_ms"]) for r in tail
                 if isinstance(r.get("observe_lag_ms"), (int, float))]
    return {"component": "mlb_event_reactive", "n_rows": len(tail), "n_rows_total": len(rows),
            "lag_ms_p50": _pct(lags, 0.50), "lag_ms_p90": _pct(lags, 0.90),
            "lag_ms_max": max(lags) if lags else None, "by_kind": kinds,
            "feed_stamp_delta_ms_p50": _pct(feed_lags, 0.50), "feed_stamp_delta_ms_p90": _pct(feed_lags, 0.90),
            "observe_lag_ms_p50": _pct(poll_lags, 0.50), "observe_lag_ms_p90": _pct(poll_lags, 0.90),
            "n_games": len(files), "store": str(base), "edge_claimed": False,
            "note": "lag_ms = our detect clock minus the MLB feed's own event clock; "
                    "feed-detection latency only, not a venue or $ edge claim"}


def run_live(window_sec: float, out_dir: Path = DEFAULT_OUT_DIR,
             cadence_sec: Optional[float] = None,
             fetch_fn: Any = _poller._http_get_json,
             sleep_fn: Any = time.sleep, date_str: Optional[str] = None) -> Dict[str, Any]:
    """Poll every live game for window_sec at the feed's own cadence, emitting event rows.

    Reuses gumbo_mlb_poller's bootstrap/diffPatch machinery unmodified, and keeps its
    poller state IN MEMORY (never touches the production poller's state file, so this can
    run beside the m37 runner without racing it)."""
    cadence = _poller.live_cadence_sec() if cadence_sec is None else max(5.0, float(cadence_sec))
    pace = _poller.live_pace_sec()
    games = [g["game_pk"] for g in _poller.list_live_game_pks(date_str, fetch_fn=fetch_fn)
             if g.get("game_pk") is not None]
    state: Dict[str, Any] = {}
    seen: Dict[str, Set[str]] = {str(g): seen_ids(out_dir, str(g)) for g in games}
    primed: Set[str] = set()
    rep: Dict[str, Any] = {"n_games": len(games), "n_rows": 0, "n_passes": 0, "errors": []}
    deadline = time.time() + float(window_sec)
    while time.time() < deadline:
        nxt = time.time() + cadence
        for i, gp in enumerate(games):
            if i > 0:
                sleep_fn(pace)
            key = str(gp)
            try:
                _poller.poll_one_game(gp, state, fetch_fn=fetch_fn)
                det = _now()
                doc = (state.get(key) or {}).get("snapshot")
                if not isinstance(doc, dict):
                    continue
                if key not in primed:  # seed dedupe from the backlog, emit nothing
                    primed.add(key)
                    build_rows(doc, det, seen.setdefault(key, set()))
                    continue
                rep["n_rows"] += append_rows(build_rows(doc, det, seen[key]), out_dir)
            except Exception as exc:  # noqa: BLE001 -- one bad game never kills the window
                rep["errors"].append("%s: %s" % (gp, exc))
        rep["n_passes"] += 1
        sleep_fn(max(0.0, min(nxt - time.time(), deadline - time.time())))
    return rep


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="MLB event-reactive producer")
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--cadence", type=float, default=None)
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    a = ap.parse_args()
    out = Path(a.out_dir)
    if not a.summary_only:
        rep = run_live(a.minutes * 60.0, out_dir=out, cadence_sec=a.cadence)
        print("run_live | games=%s passes=%s rows=%s errors=%s"
              % (rep["n_games"], rep["n_passes"], rep["n_rows"], len(rep["errors"])))
    s = summarize(out)
    print("lag_ms p50=%s p90=%s max=%s n=%s games=%s"
          % (s["lag_ms_p50"], s["lag_ms_p90"], s["lag_ms_max"], s["n_rows"], s["n_games"]))
    print("  feed_stamp_delta p50=%s p90=%s | observe_lag p50=%s p90=%s"
          % (s["feed_stamp_delta_ms_p50"], s["feed_stamp_delta_ms_p90"],
             s["observe_lag_ms_p50"], s["observe_lag_ms_p90"]))
    print("by_kind=%s" % json.dumps(s["by_kind"], sort_keys=True))
    print("store=%s" % s["store"])


if __name__ == "__main__":
    main()
