"""nba_injury_scraper_daemon.py — R22_O8 polling wrapper for the NBA injury scraper.

Polls `nba_injury_report_scraper.scrape_once` every 30 minutes during
NBA hours (12pm-11pm ET == 16-23 UTC and 0-4 UTC the next day, with a
small head-room buffer). Each tick:

  1. Writes a daemon heartbeat (R19_L3 pattern) so the watchdog can
     restart us if we wedge.
  2. Runs the scraper and persists the canonical parquet.
  3. Diffs against the previous tick — for each NEW row whose status is
     OUT and whose player is a top-100 (by season scoring usage) star,
     fires a layered Discord+vault alert.
  4. Outside of NBA hours, sleeps in 60s chunks so SIGINT is responsive
     but we don't burn CPU.

CLI
---
    python scripts/nba_injury_scraper_daemon.py --once       # one tick + exit
    python scripts/nba_injury_scraper_daemon.py --interval-sec 1800
    python scripts/nba_injury_scraper_daemon.py --smoke      # one tick + dump status counts

The daemon is intentionally restartable: all state (last-seen OUT set,
parquet path) lives on disk and can be reconstructed at boot.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date as _date_cls
from datetime import datetime, timezone
from typing import Optional, Set, Tuple

# ── R19_L3 heartbeat import (sys.path bootstrap) ──────────────────────────────
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import nba_injury_report_scraper as scraper  # noqa: E402

# Optional Discord/vault alerts — the daemon must run with or without it.
try:
    from src.alerts.discord_webhook import alert as _alert
except Exception:
    def _alert(*a, **kw):
        return {"discord_sent": False, "file_written": False,
                "vault_appended": False}

# ── logging ───────────────────────────────────────────────────────────────────
_LOG_FMT = "%(asctime)s %(levelname)s [injury_daemon] %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT)
log = logging.getLogger("nba_injury_scraper_daemon")

# ── policy constants ──────────────────────────────────────────────────────────
_DEFAULT_INTERVAL_SEC = 30 * 60                       # 30 min on game days
_HEARTBEAT_NAME       = "nba_injury_scraper_daemon"
_LAST_SEEN_OUT_FILE   = os.path.join(
    PROJECT_DIR, "data", "cache", "nba_injury_daemon_seen_out.json"
)
# 12pm–11pm ET ⇒ 16-04 UTC. We allow polling all 24 hours because off-hours
# are useful during preseason and playoffs (West-coast tip 22:30 ET = 02:30 UTC).
_GAME_WINDOW_UTC_HOURS = set(list(range(16, 24)) + list(range(0, 5)))
_TOP_N_STARS           = 100


# ── star list (top-N by pregame predicted PTS) ────────────────────────────────
def _load_top_star_ids(n: int = _TOP_N_STARS) -> Set[int]:
    """Return {player_id} for the top-N players by mean OOF PTS prediction.

    Falls back to an empty set when the OOF parquet isn't on disk yet —
    the daemon still runs but no alerts fire for the unknown stars.
    """
    oof_path = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
    if not os.path.exists(oof_path):
        return set()
    try:
        import pandas as pd
        oof = pd.read_parquet(oof_path)
    except Exception:
        return set()
    pts = oof[oof["stat"] == "pts"] if "stat" in oof.columns else oof
    if pts.empty or "player_id" not in pts.columns or "oof_pred" not in pts.columns:
        return set()
    means = pts.groupby("player_id")["oof_pred"].mean().nlargest(n)
    return {int(p) for p in means.index.tolist()}


# ── seen-OUT set persistence ──────────────────────────────────────────────────
def _load_seen_out() -> Set[int]:
    """Load the persisted seen-OUT player_id set (resets across days)."""
    if not os.path.exists(_LAST_SEEN_OUT_FILE):
        return set()
    try:
        with open(_LAST_SEEN_OUT_FILE, encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return set()
    today = _date_cls.today().isoformat()
    if payload.get("date") != today:
        return set()                            # day rollover → reset
    return {int(x) for x in payload.get("ids", [])}


def _save_seen_out(ids: Set[int]) -> None:
    os.makedirs(os.path.dirname(_LAST_SEEN_OUT_FILE), exist_ok=True)
    payload = {
        "date":       _date_cls.today().isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ids":        sorted(int(x) for x in ids),
    }
    tmp = _LAST_SEEN_OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, _LAST_SEEN_OUT_FILE)


# ── one-shot tick ─────────────────────────────────────────────────────────────
def run_tick(stars: Optional[Set[int]] = None,
             alert_fn=None,
             scrape_fn=None) -> dict:
    """Execute one scrape + diff + alert cycle. Returns a summary dict.

    Args:
        stars:     {player_id} treated as "star" for alert fan-out. None
                   → re-derive from OOF parquet.
        alert_fn:  Injectable alert function (tests pass a stub recorder).
        scrape_fn: Injectable scraper function (tests pass a stub returning
                   (df, path) without hitting the network).
    """
    alert_fn = alert_fn or _alert
    scrape_fn = scrape_fn or scraper.scrape_once
    stars = stars if stars is not None else _load_top_star_ids()

    df, parquet_path = scrape_fn()
    n_rows = int(len(df))
    n_out = 0
    n_alerts = 0
    new_out_stars = []

    seen_out = _load_seen_out()
    if n_rows > 0 and "status" in df.columns:
        out_df = df[df["status"] == "OUT"]
        n_out = int(len(out_df))
        # IDs may be NaN (player_id unresolved); convert via pandas-aware path.
        cur_out_ids = {int(x) for x in out_df["player_id"].dropna().tolist()}
        new_out = cur_out_ids - seen_out
        for pid in new_out:
            if pid in stars:
                row = out_df[out_df["player_id"] == pid].iloc[0]
                new_out_stars.append({
                    "player_id":   pid,
                    "player_name": str(row["player_name"]),
                    "team":        str(row["team"]),
                    "reason":      str(row.get("reason") or ""),
                })
        # Fire one alert per new OUT star.
        for s in new_out_stars:
            try:
                alert_fn(
                    f"NBA Injury: {s['player_name']} ({s['team']}) — OUT",
                    level="critical",
                    tag="nba_injury_scraper",
                    source="nba_injury_scraper_daemon",
                    body=f"Reason: {s['reason'] or 'unspecified'}",
                    fields=[
                        {"name": "player_id", "value": str(s["player_id"])},
                        {"name": "team",      "value": s["team"]},
                    ],
                )
                n_alerts += 1
            except Exception as exc:  # never break the daemon over an alert
                log.warning("alert dispatch failed: %s", exc)
        # Persist the NEW union back to disk — next tick subtracts this set.
        _save_seen_out(seen_out | cur_out_ids)

    return {
        "n_rows":         n_rows,
        "n_out":          n_out,
        "n_new_out_stars": len(new_out_stars),
        "n_alerts_sent": n_alerts,
        "parquet_path":   parquet_path,
        "new_out_stars":  new_out_stars,
    }


# ── time helpers ──────────────────────────────────────────────────────────────
def _within_game_window(now_utc: Optional[datetime] = None) -> bool:
    """True when current UTC hour is inside the NBA game-day window."""
    now = now_utc or datetime.now(timezone.utc)
    return now.hour in _GAME_WINDOW_UTC_HOURS


# ── main poll loop ────────────────────────────────────────────────────────────
def main(argv: Optional[List[str]] = None) -> int:  # noqa: D401
    ap = argparse.ArgumentParser(description="NBA injury scraper daemon (R22_O8)")
    ap.add_argument("--interval-sec", type=int, default=_DEFAULT_INTERVAL_SEC,
                    help="Poll interval in seconds (default 1800 = 30 min)")
    ap.add_argument("--once", action="store_true",
                    help="Run a single tick then exit (use for cron / smoke).")
    ap.add_argument("--smoke", action="store_true",
                    help="Run once, print status counts, exit 0 even on empty.")
    ap.add_argument("--all-hours", action="store_true",
                    help="Ignore the 12pm–11pm ET window and poll 24/7.")
    args = ap.parse_args(argv)

    _r19_hb(_HEARTBEAT_NAME)
    stars = _load_top_star_ids()
    log.info("loaded %d top-N stars for alert fan-out", len(stars))

    if args.once or args.smoke:
        summary = run_tick(stars=stars)
        log.info("tick summary: %s", json.dumps(
            {k: v for k, v in summary.items() if k != "new_out_stars"}))
        if args.smoke:
            return 0
        return 0 if summary["n_rows"] > 0 else 1

    log.info("daemon starting; interval=%ds  all_hours=%s",
             args.interval_sec, args.all_hours)
    while True:
        _r19_hb(_HEARTBEAT_NAME)
        if args.all_hours or _within_game_window():
            try:
                summary = run_tick(stars=stars)
                log.info("tick: %s", json.dumps(
                    {k: v for k, v in summary.items() if k != "new_out_stars"}))
            except Exception:  # noqa: BLE001 — daemon must not die
                log.exception("scrape iteration crashed")
        else:
            log.info("outside game window (UTC hour=%d) — skipping scrape",
                     datetime.now(timezone.utc).hour)
        # Sleep in 60s chunks so SIGINT is responsive.
        slept = 0
        while slept < args.interval_sec:
            time.sleep(min(60, args.interval_sec - slept))
            slept += 60


if __name__ == "__main__":
    # `List` needed for the argparse signature.
    from typing import List   # noqa: F401
    sys.exit(main())
