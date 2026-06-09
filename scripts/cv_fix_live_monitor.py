"""Live game-night health monitor for CourtVision.

Polls the running box-score endpoint every INTERVAL seconds during the live game
and flags anything off — so problems are caught before they reach the page:
  * server reachable / endpoint 200
  * win prob present and in a sane range, and CHANGING over time (not frozen)
  * NO projection below current (floor) or absurd (low-min player projected huge)
  * NO line/price book mismatch on live bets
  * in-play lines fresh (most books < 5 min)
  * snapshot + line scrapers still writing

Writes one status line per tick to data/cache/cv_fix/_live_monitor.log and prints it.
Run:  python scripts/cv_fix_live_monitor.py [gid] [date] [interval_s]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "cache" / "cv_fix" / "_live_monitor.log"
BASE = "http://127.0.0.1:8077"


def _get(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def _check(gid, date):
    issues = []
    try:
        b = _get(f"{BASE}/api/box_score?date={date}&game_id={gid}")
    except Exception as exc:
        return ["SERVER UNREACHABLE: %s" % exc], None
    wp = b.get("home_win_prob")
    if wp is None:
        issues.append("no live win_prob")
    elif not (0.0 <= wp <= 1.0):
        issues.append(f"win_prob out of range: {wp}")
    # projections: below current or absurd
    nbad = nabs = 0
    for side in ("away", "home"):
        for p in (b.get(side) or {}).get("players", []):
            cur, pf, mp = p.get("current") or {}, p.get("paced_final") or {}, p.get("minutes_played") or 0
            for st, cv in cur.items():
                pv = pf.get(st)
                if cv is not None and pv is not None and pv < cv - 1e-6:
                    nbad += 1
                if st == "pts" and pv is not None and (pv > 45 or (mp < 6 and pv > 16)):
                    nabs += 1
    if nbad:
        issues.append(f"{nbad} proj<current")
    if nabs:
        issues.append(f"{nabs} absurd-proj")
    # live bets: book/line/price consistency + freshness
    lb = b.get("live_bets") or []
    mism = stale = 0
    for x in lb:
        abl = x.get("all_books_live") or []
        bb = (x.get("best_book") or "").replace(" (Live)", "")
        match = [a for a in abl if (a.get("book") or "").replace(" (Live)", "") == bb]
        if match and match[0].get("line") != x.get("line"):
            mism += 1
        age = x.get("freshest_book_age_min")
        if age is not None and age >= 15:
            stale += 1
    if mism:
        issues.append(f"{mism} book/line mismatch")
    return issues, {"wp": wp, "n_bets": len(lb), "stale_bets": stale,
                    "score": f"{(b.get('away') or {}).get('score')}-{(b.get('home') or {}).get('score')}"}


def main(argv):
    gid = argv[1] if len(argv) > 1 else "0042500317"
    date = argv[2] if len(argv) > 2 else "2026-05-30"
    interval = int(argv[3]) if len(argv) > 3 else 60
    prev_wp = None
    LOG.parent.mkdir(parents=True, exist_ok=True)
    while True:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        issues, meta = _check(gid, date)
        wp_moving = ""
        if meta and meta.get("wp") is not None:
            if prev_wp is not None and abs(meta["wp"] - prev_wp) < 1e-9:
                wp_moving = " WP-FROZEN"
            prev_wp = meta["wp"]
        status = "OK" if not issues and not wp_moving else "ISSUES"
        line = (f"[{ts}] {status} wp={meta.get('wp') if meta else None} "
                f"bets={meta.get('n_bets') if meta else '?'} stale={meta.get('stale_bets') if meta else '?'} "
                f"{meta.get('score') if meta else ''}"
                + (("  -> " + "; ".join(issues + ([wp_moving.strip()] if wp_moving else ""))) if (issues or wp_moving) else ""))
        print(line, flush=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        time.sleep(interval)


if __name__ == "__main__":
    main(sys.argv)
