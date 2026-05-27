"""
parse_rotowire_lineups.py — Parse RotoWire daily NBA lineups HTML cache.

Reads:  data/cache/rotowire_lineups.html  (snapshot scraped daily)
Writes: data/cache/rotowire_lineups_parsed.json

Output schema:
    {
        "as_of_date": "YYYY-MM-DD",
        "teams": {
            "OKC": [
                {
                    "player_name": "Shai Gilgeous-Alexander",
                    "position":    "PG",
                    "status":      "C" | "Q" | "OUT" | "GTD" | null,
                    "is_starter":  true,
                    "lineup_order": 0
                },
                ...
            ],
            ...
        }
    }

NOTE: this is a daily snapshot — overwritten each day. Use ONLY for live
predictions (current slate). Do NOT use as a training feature: the cache
file at training time will not reflect historical lineups.

Usage:
    python scripts/parse_rotowire_lineups.py
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from typing import Optional

from bs4 import BeautifulSoup

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH  = os.path.join(_ROOT, "data", "cache", "rotowire_lineups.html")
_OUT_PATH   = os.path.join(_ROOT, "data", "cache", "rotowire_lineups_parsed.json")


# Map RotoWire's injury-label text to a normalized status code.
#   no <span class="lineup__inj">    -> "C"   (confirmed/expected starter)
#   "Ques" / "GTD"                   -> "Q"   (game-time decision)
#   "Out"  / "OFS" / "Doubtful"      -> "OUT"
_STATUS_MAP = {
    "ques": "Q",
    "gtd":  "GTD",
    "out":  "OUT",
    "ofs":  "OUT",
    "doubt": "OUT",
}


def _norm_status(raw: Optional[str]) -> Optional[str]:
    """Map a RotoWire injury tag like 'Ques'/'OFS'/'Out' to C/Q/OUT/GTD."""
    if not raw:
        return "C"
    key = raw.strip().lower()
    for prefix, code in _STATUS_MAP.items():
        if key.startswith(prefix):
            return code
    return raw.strip().upper()[:6] or None


def _extract_game_date(soup: BeautifulSoup) -> str:
    """Pull the slate date out of <main data-gamedate="YYYY-MM-DD">.

    Fallbacks: parse 'Starting lineups for May 26, 2026' header → today.
    """
    main = soup.find("main", attrs={"data-gamedate": True})
    if main and main.get("data-gamedate"):
        return main["data-gamedate"]

    header = soup.find(class_="page-title__secondary")
    if header:
        m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", header.get_text())
        if m:
            try:
                return _dt.datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass

    return _dt.date.today().isoformat()


def _parse_team_list(ul_tag, team_abbrev: str) -> list[dict]:
    """Walk a <ul class="lineup__list ..."> producing starter+bench rows.

    The first 5 <li class="lineup__player ..."> tags are the projected
    starters (in PG/SG/SF/PF/C order). Any later players sit under the
    "MAY NOT PLAY" subtitle and are bench/inactives.
    """
    players: list[dict] = []
    seen_bench_header = False
    starter_count = 0

    for li in ul_tag.find_all("li", recursive=False):
        cls = " ".join(li.get("class", []))

        # The "MAY NOT PLAY" pseudo-li flips us into bench mode.
        if "lineup__title" in cls:
            seen_bench_header = True
            continue

        if "lineup__player" not in cls:
            continue

        pos_tag  = li.find("div", class_="lineup__pos")
        name_tag = li.find("a")
        inj_tag  = li.find("span", class_="lineup__inj")

        if not name_tag:
            continue

        # Prefer the anchor's `title` attribute — it carries the full name,
        # while inner text is often abbreviated like "S. Gilgeous-Alexander".
        full_name = (name_tag.get("title") or name_tag.get_text(strip=True) or "").strip()
        if not full_name:
            continue

        is_starter = (not seen_bench_header) and starter_count < 5
        if is_starter:
            starter_count += 1

        players.append({
            "player_name":  full_name,
            "position":     (pos_tag.get_text(strip=True) if pos_tag else "") or None,
            "status":       _norm_status(inj_tag.get_text(strip=True) if inj_tag else None),
            "is_starter":   is_starter,
            "lineup_order": (starter_count - 1) if is_starter else -1,
        })

    return players


def parse_lineups_html(html_path: str = _HTML_PATH) -> dict:
    """Parse the local RotoWire HTML cache → date + per-team rosters dict."""
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"rotowire HTML not found: {html_path}")

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")
    as_of_date = _extract_game_date(soup)

    teams_out: dict[str, list[dict]] = {}

    # Iterate over the real game cards. Skip the "is-tools" / "is-picks"
    # promo cards which also share the .lineup class but have no teams.
    for card in soup.find_all("div", class_="lineup is-nba"):
        card_cls = " ".join(card.get("class", []))
        if "is-tools" in card_cls or "is-picks" in card_cls:
            continue

        abbrs = [a.get_text(strip=True) for a in card.select(".lineup__teams .lineup__abbr")]
        if len(abbrs) < 2:
            continue
        visit_abbr, home_abbr = abbrs[0], abbrs[1]

        visit_ul = card.find("ul", class_=re.compile(r"\blineup__list\b.*\bis-visit\b"))
        home_ul  = card.find("ul", class_=re.compile(r"\blineup__list\b.*\bis-home\b"))

        if visit_ul:
            teams_out.setdefault(visit_abbr, []).extend(
                _parse_team_list(visit_ul, visit_abbr)
            )
        if home_ul:
            teams_out.setdefault(home_abbr, []).extend(
                _parse_team_list(home_ul, home_abbr)
            )

    return {"as_of_date": as_of_date, "teams": teams_out}


def main() -> int:
    parsed = parse_lineups_html()
    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    teams = parsed["teams"]
    n_games  = len(teams) // 2
    n_teams  = len(teams)
    n_players = sum(len(v) for v in teams.values())
    n_starters = sum(1 for plist in teams.values() for p in plist if p["is_starter"])

    print(f"[rotowire-parse] as_of_date = {parsed['as_of_date']}")
    print(f"[rotowire-parse] games={n_games}  teams={n_teams}  players={n_players}  starters={n_starters}")
    print(f"[rotowire-parse] wrote {_OUT_PATH}")
    print()
    print("Sample (first 3 teams):")
    for abbrev, plist in list(teams.items())[:3]:
        print(f"  {abbrev}:")
        for p in plist[:6]:
            tag = "*" if p["is_starter"] else " "
            try:
                print(f"    {tag} [{p['position'] or '?':>2}] {p['player_name']:<28} status={p['status']}")
            except UnicodeEncodeError:
                safe = p["player_name"].encode("ascii", "replace").decode()
                print(f"    {tag} [{p['position'] or '?':>2}] {safe:<28} status={p['status']}")

    # Spot-check well-known starters
    print()
    print("Spot-checks:")
    checks = [
        ("OKC", "Shai Gilgeous-Alexander"),
        ("DEN", "Nikola Jokic"),
        ("DEN", "Nikola Jokić"),
        ("BOS", "Jayson Tatum"),
        ("LAL", "LeBron James"),
    ]
    hits = 0
    for team, who in checks:
        plist = teams.get(team, [])
        found = next(
            (p for p in plist if p["player_name"].lower().replace("ć", "c") == who.lower().replace("ć", "c")),
            None,
        )
        who_safe = who.encode("ascii", "replace").decode()
        if found and found["is_starter"]:
            print(f"  OK  {team:<3} {who_safe:<28} is_starter=True")
            hits += 1
        elif found:
            print(f"  --  {team:<3} {who_safe:<28} present but not flagged starter (status={found['status']})")
        else:
            print(f"  --  {team:<3} {who_safe:<28} NOT present in slate")

    print(f"\nSpot-check hits: {hits}/{len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
