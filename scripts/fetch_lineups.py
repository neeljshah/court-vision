"""fetch_lineups.py — projected starting lineups from rotowire.com.

Cycle 46's predict_player.py starter check uses BoxScoreTraditionalV2 per
game (one nba_api call per recent game per player — slow + rate-limited).
A daily lineups feed gives a much faster + more current signal: who's
actually starting tonight (Confirmed / Expected / Projected).

Source: https://www.rotowire.com/basketball/nba-lineups.php (free, no auth,
respect a 1.5s rate limit between fetches per their robots policy).

Output (data/lineups_<date>.json):
    {
        "date": "YYYY-MM-DD",
        "fetched_at": "ISO-8601",
        "games": [
            {
                "home_team": "OKC", "away_team": "DEN",
                "home_lineup": {"status": "Expected", "starters": [
                    {"pos": "PG", "name": "Shai Gilgeous-Alexander",
                     "play_pct": 100, "injury": null},
                    ...
                ]},
                "away_lineup": {...}
            },
            ...
        ]
    }

The starters list is in canonical PG/SG/SF/PF/C order. play_pct comes from
rotowire's `is-pct-play-N` class (their confidence the player will play).
injury is the abbreviation from `<span class="lineup__inj">...</span>` or null.

Run:
    python scripts/fetch_lineups.py
    python scripts/fetch_lineups.py --date 2026-05-24
    python scripts/fetch_lineups.py --out /tmp/lineups.json
    python scripts/fetch_lineups.py --dry-run    # parse cached HTML only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, date as _date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ROTOWIRE_URL = "https://www.rotowire.com/basketball/nba-lineups.php"
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/120.0.0.0 Safari/537.36")
_CACHE_TTL_SECS = 15 * 60         # 15 min — rotowire updates ~5-10x per hour
_HTML_CACHE_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                                  "rotowire_lineups.html")


def fetch_html(force: bool = False) -> str:
    """Fetch the HTML with cache + TTL. Returns body string."""
    if not force and os.path.exists(_HTML_CACHE_PATH):
        age = time.time() - os.path.getmtime(_HTML_CACHE_PATH)
        if age < _CACHE_TTL_SECS:
            with open(_HTML_CACHE_PATH, encoding="utf-8") as fh:
                return fh.read()
    req = urllib.request.Request(_ROTOWIRE_URL, headers={"User-Agent": _USER_AGENT})
    body = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
    os.makedirs(os.path.dirname(_HTML_CACHE_PATH), exist_ok=True)
    with open(_HTML_CACHE_PATH, "w", encoding="utf-8") as fh:
        fh.write(body)
    return body


# ── parsers ──────────────────────────────────────────────────────────────────

# A lineup block is a <ul class="lineup__list is-visit|is-home"> with
# status header + ≤5 starter <li>s. Capture the whole UL and parse inside.
_LIST_RE = re.compile(
    r'<ul class="lineup__list ([^"]+)">(.*?)</ul>', re.DOTALL)
# Pulls a starter <li>: position, name, play_pct, optional injury tag.
# Anchored to </li> so the optional injury group can't span <li> boundaries
# (the previous version was eating PG, SG, SF into a single "PG with injury" match
# when one of the trio carried a <span class="lineup__inj">).
_PLAYER_RE = re.compile(
    r'<li class="lineup__player is-pct-play-(\d+)[^"]*?"[^>]*>\s*'
    r'<div class="lineup__pos"[^>]*>([A-Z]+)</div>\s*'
    r'<a title="([^"]+)"[^>]*>[^<]+</a>'
    r'(?:[^<]*<span class="lineup__inj">([^<]+)</span>)?'
    r'\s*</li>',
    re.DOTALL)
# Status header (Expected / Projected / Confirmed)
_STATUS_RE = re.compile(
    r'<li class="lineup__status is-(\w+)">\s*<div[^>]*></div>\s*([\w ]+)Lineup',
    re.DOTALL)
# Team abbrev — pulled from the "data-team" attribute on a sibling button.
_TEAM_RE = re.compile(r'data-team="([A-Z]{2,3})"\s+data-nickname="[^"]+"\s+'
                       r'data-home="([01])"')


def parse_one_list(list_html: str) -> Dict:
    """Parse one <ul class='lineup__list ...'> block into a lineup dict.

    Rotowire puts BOTH starters and a "MAY NOT PLAY" sub-list inside the
    same <ul> — separated by a `<li class="lineup__title">MAY NOT PLAY</li>`
    marker. We only want the starters, so we truncate at the marker.
    """
    status = "Unknown"
    sm = _STATUS_RE.search(list_html)
    if sm:
        status = sm.group(2).strip()
    # Truncate at the "MAY NOT PLAY" marker so the regex doesn't pull in
    # benched players (their position labels are "F" / "G" / "C" — generic,
    # not the canonical PG/SG/SF/PF/C used for starters).
    cut = re.search(r'<li class="lineup__title[^"]*"[^>]*>\s*MAY NOT PLAY',
                     list_html, re.IGNORECASE)
    starters_html = list_html[:cut.start()] if cut else list_html
    starters = []
    for pm in _PLAYER_RE.finditer(starters_html):
        play_pct, pos, name, injury = pm.groups()
        starters.append({
            "pos":      pos,
            "name":     name.strip(),
            "play_pct": int(play_pct),
            "injury":   (injury.strip() if injury else None),
        })
    team_match = _TEAM_RE.search(list_html)
    team = team_match.group(1) if team_match else ""
    return {"team": team, "status": status, "starters": starters}


def parse_html(body: str) -> List[Dict]:
    """Parse the full rotowire HTML body into a list of game dicts.

    Each game has home_team / away_team / home_lineup / away_lineup.
    Robust against rotowire's occasional half-rendered or stub blocks
    (a lineup with 0 starters is skipped).
    """
    games: List[Dict] = []
    lists: List[Dict] = []
    for lm in _LIST_RE.finditer(body):
        flag = lm.group(1)                # "is-visit" | "is-home"
        ul = lm.group(0)
        parsed = parse_one_list(ul)
        if not parsed["starters"]:
            continue                       # stub / placeholder list
        parsed["side"] = "away" if "is-visit" in flag else "home"
        lists.append(parsed)
    # Pair: rotowire prints visit then home per game card, in document order.
    i = 0
    while i + 1 < len(lists):
        a, b = lists[i], lists[i + 1]
        if a["side"] == "away" and b["side"] == "home":
            games.append({
                "away_team": a["team"], "home_team": b["team"],
                "away_lineup": {"status": a["status"], "starters": a["starters"]},
                "home_lineup": {"status": b["status"], "starters": b["starters"]},
            })
            i += 2
        else:
            i += 1               # skip orphan
    return games


def write_payload(games: List[Dict], date_str: str, out_path: str) -> int:
    """Write the payload JSON. Returns total starter count across all games."""
    payload = {
        "date":       date_str,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "source":     _ROTOWIRE_URL,
        "games":      games,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return sum(len(g["away_lineup"]["starters"]) + len(g["home_lineup"]["starters"])
               for g in games)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="Stamp the JSON with this date (default: today). "
                         "Doesn't change which games rotowire returns — that's always 'tonight'.")
    ap.add_argument("--out", default=None,
                    help="Output path (default: data/lineups_<date>.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse cached HTML only; don't fetch or write JSON.")
    ap.add_argument("--force", action="store_true",
                    help="Bypass the 15-min HTML cache TTL.")
    args = ap.parse_args()

    if args.dry_run and not os.path.exists(_HTML_CACHE_PATH):
        print("[fetch_lineups] --dry-run requested but no cached HTML; aborting.")
        return 1
    body = fetch_html(force=args.force) if not args.dry_run else \
           open(_HTML_CACHE_PATH, encoding="utf-8").read()
    games = parse_html(body)
    if not games:
        print("[fetch_lineups] 0 games parsed — page format may have changed.")
        return 1

    date_str = args.date or _date.today().isoformat()
    out = args.out or os.path.join(PROJECT_DIR, "data",
                                     f"lineups_{date_str}.json")
    if args.dry_run:
        print(f"[fetch_lineups] dry-run: parsed {len(games)} game(s) from cached HTML.")
        for g in games[:3]:
            print(f"  {g['away_team']} @ {g['home_team']}  "
                  f"({g['away_lineup']['status']} / {g['home_lineup']['status']})")
        return 0
    n = write_payload(games, date_str, out)
    print(f"[fetch_lineups] {len(games)} games, {n} starters -> {out}")
    for g in games:
        a, h = g["away_team"], g["home_team"]
        print(f"  {a} @ {h}  away={g['away_lineup']['status']} "
              f"({len(g['away_lineup']['starters'])} starters)  "
              f"home={g['home_lineup']['status']} "
              f"({len(g['home_lineup']['starters'])} starters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
