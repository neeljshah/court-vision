"""
cv_fix_register_book_ids.py — collapse duplicate game cards.

The direct book scrapers (draftkings_scraper, betrivers_scraper, pinnacle, fd, ...)
each tag lines with their OWN native event id as game_id. games_lookup.json only
knows the NBA gid + odds-api hash, so those book-native ids don't group -> the home
page shows one card per book id (duplicates) and clicking a book-id card can't resolve
to the projected box.

Fix: for every distinct game_id in today's data/lines/<date>_<book>.csv that is NOT
already in games_lookup, match it to the canonical NBA game by start_time (minute
precision) and register an alias entry (same home/away/start_time). _load_game_aliases
then groups them all into one matchup; games_index emits ONE card whose canonical id
sorts first (the NBA gid 00425... starts with '0').

Run before/at game time (idempotent):
    python scripts/cv_fix_register_book_ids.py --date 2026-05-30
"""
from __future__ import annotations
import argparse, csv, glob, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOKUP = os.path.join(ROOT, "data", "cache", "games_lookup.json")
LINES_DIR = os.path.join(ROOT, "data", "lines")


def run_once(date: str) -> int:
    lookup = json.load(open(LOOKUP, encoding="utf-8"))

    # Canonical NBA games (home/away set, official source preferred), indexed by
    # start_time DATE (books disagree on the tip minute: 00:00/00:05/00:10).
    canon_by_date: dict[str, list] = {}
    canon_all = []
    for gid, info in lookup.items():
        if info.get("home_abbr") and info.get("away_abbr") and info.get("start_time") \
           and info.get("_source") != "book_alias":
            canon_by_date.setdefault(info["start_time"][:10], []).append(info)
            canon_all.append(info)

    def _match(st: str):
        """Match a book line's start_time to a canonical NBA game."""
        if st:
            cands = canon_by_date.get(st[:10], [])
            if len(cands) == 1:
                return cands[0]
            if cands:  # multiple games that date -> nearest tip minute
                return min(cands, key=lambda c: abs(
                    int((c["start_time"][11:13] or 0)) * 60 + int(c["start_time"][14:16] or 0)
                    - (int(st[11:13] or 0) * 60 + int(st[14:16] or 0))))
        # empty/garbage start_time -> assign the lone game of the slate if unique
        return canon_all[0] if len(canon_all) == 1 else None

    existing = set(lookup.keys())
    added = 0
    seen = set()
    for path in glob.glob(os.path.join(LINES_DIR, f"{date}_*.csv")):
        if path.endswith(".stale") or "_mainline" in path:
            continue
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                rdr = csv.DictReader(fh)
                for row in rdr:
                    gid = (row.get("game_id") or "").strip()
                    st = (row.get("start_time") or "").strip()
                    if not gid or gid in existing or gid in seen:
                        continue
                    seen.add(gid)
                    canon = _match(st)
                    if not canon:
                        print(f"  [skip] {gid}: no NBA game match for start_time '{st[:16]}'")
                        continue
                    lookup[gid] = {
                        "home_abbr": canon["home_abbr"], "away_abbr": canon["away_abbr"],
                        "home_name": canon.get("home_name", ""), "away_name": canon.get("away_name", ""),
                        "start_time": canon["start_time"],
                        "label": canon.get("label", ""),
                        "_source": "book_alias",
                    }
                    added += 1
                    print(f"  + {gid} -> {canon['away_abbr']} @ {canon['home_abbr']} ({canon['start_time']})")
        except Exception as e:
            print(f"  [warn] {os.path.basename(path)}: {e!r}")

    if added:
        json.dump(lookup, open(LOOKUP, "w", encoding="utf-8"), indent=1)
    print(f"[register_book_ids] registered {added} new book game_ids; lookup now {len(lookup)} entries.")
    return added


def main():
    import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="NBA line-file date prefix YYYY-MM-DD")
    ap.add_argument("--loop", action="store_true", help="run forever, re-registering new book ids")
    ap.add_argument("--interval", type=int, default=60, help="loop interval seconds")
    args = ap.parse_args()
    if not args.loop:
        run_once(args.date)
        return
    print(f"[register_book_ids] loop mode every {args.interval}s for {args.date}")
    while True:
        try:
            run_once(args.date)
        except Exception as e:
            print(f"[register_book_ids] error: {e!r}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
