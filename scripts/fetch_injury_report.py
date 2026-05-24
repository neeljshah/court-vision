"""fetch_injury_report.py — pull the NBA Official Injury Report PDF and parse it.

The NBA publishes a structured PDF injury report several times per day at:

    https://official.nba.com/wp-content/uploads/sites/4/YYYY/MM/Injury-Report-YYYY-MM-DD_HHPM.pdf

Common publish slots are 01PM, 05PM, 08PM (each successive PDF is the latest
authoritative snapshot, supersedes the prior one). We try latest-first and
walk backward on 404 to grab the freshest report.

Why this matters
----------------
The prediction stack (prop_pergame + WinProb) is at architecture/feature
ceiling. Live injury state — and especially the rolling questionable /
out / probable status of teammates — is the highest-ROI remaining data
lever (~ -1% MAE across stats, +1pp WinProb). The model today has zero
"is this player questionable / is a teammate out tonight" signal at
inference time.

This script is the *raw data layer* only — it produces a normalized JSON
snapshot. Wiring the resulting JSON into FEATURE_COLS is a separate
cycle; do not touch prop_pergame.py or win_probability.py here.

Output
------
* Raw PDF cached at data/cache/injuries/Injury-Report-YYYY-MM-DD_HHPM.pdf
* Parsed JSON at data/injuries_YYYY-MM-DD.json with shape:

    {
      "date": "2026-05-24",
      "source_pdf": "Injury-Report-2026-05-24_05PM.pdf",
      "fetched_at": "2026-05-24T17:32:11",
      "players": [
        {"team": "LAL", "name": "LeBron James",
         "status": "QUESTIONABLE", "reason": "Foot; Soreness"},
        ...
      ]
    }

Usage
-----
    python scripts/fetch_injury_report.py                # today
    python scripts/fetch_injury_report.py --date 2026-05-24
    python scripts/fetch_injury_report.py --date 2026-05-24 --time 05PM
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date as _date_cls
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Publish slots in latest-first order. The latest snapshot supersedes
# earlier ones, so we walk from 08PM backward to find the freshest PDF.
_TIME_SLOTS: Tuple[str, ...] = ("08PM", "05PM", "01PM")

# Canonical status tokens the parser recognizes. Order matters for the
# regex split: list LONGER tokens first ("NOT WITH TEAM" before "OUT")
# so partial matches do not steal the line.
_STATUS_TOKENS: Tuple[str, ...] = (
    "NOT WITH TEAM",
    "AVAILABLE",
    "QUESTIONABLE",
    "DOUBTFUL",
    "PROBABLE",
    "OUT",
)

_STATUS_REGEX = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _STATUS_TOKENS) + r")\b"
)

# Map the NBA's full team names (as they appear on the PDF) to the
# 3-letter abbreviation the rest of the system uses everywhere.
_TEAM_ABBR: Dict[str, str] = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


def build_pdf_url(d: _date_cls, time_slot: str) -> str:
    """Construct the canonical NBA injury report PDF URL.

    Parameters
    ----------
    d
        Target date (the report's "as of" date, not necessarily today).
    time_slot
        Publish slot like "01PM", "05PM", "08PM". Case sensitive — the
        NBA's CDN paths use uppercase letters.

    Returns
    -------
    str
        Fully-qualified https URL to the PDF on official.nba.com.
    """
    return (
        f"https://official.nba.com/wp-content/uploads/sites/4/"
        f"{d.year:04d}/{d.month:02d}/"
        f"Injury-Report-{d.year:04d}-{d.month:02d}-{d.day:02d}_{time_slot}.pdf"
    )


def build_pdf_filename(d: _date_cls, time_slot: str) -> str:
    """Return just the bare PDF filename (no directories)."""
    return f"Injury-Report-{d.year:04d}-{d.month:02d}-{d.day:02d}_{time_slot}.pdf"


def fetch_pdf_bytes(
    d: _date_cls,
    cache_dir: str,
    time_slot: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout: int = 30,
) -> Optional[Tuple[bytes, str]]:
    """Download the latest available injury PDF for the given date.

    Walks `_TIME_SLOTS` latest-first; first 200 wins. Returns the PDF
    bytes plus the slot string that actually resolved, so the caller
    can record `source_pdf` in the JSON output.

    Parameters
    ----------
    d
        Target date.
    cache_dir
        Directory where the raw PDF should be saved on success. Created
        on demand.
    time_slot
        If supplied, ONLY this slot is attempted (no walk-back). Useful
        for tests and for re-fetching a specific snapshot.
    session
        Optional requests.Session for connection reuse + test injection.
    timeout
        Per-request HTTP timeout in seconds.

    Returns
    -------
    tuple[bytes, str] | None
        (pdf_bytes, slot_string) on success. None if every candidate
        URL returned a non-200 (typical when the day has no report).
    """
    sess = session or requests.Session()
    slots: Tuple[str, ...] = (time_slot,) if time_slot else _TIME_SLOTS

    # The NBA's S3 bucket rejects requests without a browser-like UA
    # (returns 403 AccessDenied). A regular browser header makes it
    # pass-through. Tests inject a `_FakeSession` so this header is
    # only attached when we're using the default real session.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
        "Referer": "https://official.nba.com/nba-injury-report/",
    }

    os.makedirs(cache_dir, exist_ok=True)
    for slot in slots:
        url = build_pdf_url(d, slot)
        try:
            # The fake session in tests doesn't take headers — pass them
            # only when the caller didn't inject one.
            if session is None:
                resp = sess.get(url, timeout=timeout, headers=headers)
            else:
                resp = sess.get(url, timeout=timeout)
        except requests.RequestException as e:
            print(f"  [warn] {slot} request failed: {e}")
            continue
        if resp.status_code == 200 and resp.content[:4] == b"%PDF":
            cache_path = os.path.join(cache_dir, build_pdf_filename(d, slot))
            with open(cache_path, "wb") as f:
                f.write(resp.content)
            print(f"  [ok] fetched {slot} ({len(resp.content):,} bytes) -> {cache_path}")
            return resp.content, slot
        else:
            print(f"  [miss] {slot} HTTP {resp.status_code}")
    return None


def _extract_text(pdf_bytes: bytes) -> str:
    """Run pdfplumber over the PDF bytes and concatenate every page's text.

    Isolated so tests can monkey-patch this with a stub returning a
    canned text block (no need to ship a real binary fixture).
    """
    import io
    import pdfplumber

    parts: List[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            parts.append(txt)
    return "\n".join(parts)


def parse_injury_text(text: str) -> List[Dict[str, str]]:
    """Convert the raw extracted PDF text into structured player records.

    The NBA's PDF layout is loose: each player row mixes a team column,
    optional game-time/matchup columns, a "Player Name" field (typed
    "Last, First"), a status token, and a free-form reason. The renderer
    sometimes splits a logical row across two physical lines. Rather
    than fight pdfplumber's column inference, we scan line-by-line for
    a status token and snap to the surrounding fragments.

    The parser is permissive on purpose — false positives on missing
    teams / weird formatting are acceptable; the downstream feature
    builder will dedupe and validate.
    """
    players: List[Dict[str, str]] = []
    current_team: str = ""
    # Match "Last, First" name pattern. Allow apostrophes, hyphens,
    # periods, and an optional Jr./Sr./II/III/IV suffix.
    name_re = re.compile(
        r"([A-Z][A-Za-z'\-\.]+(?:\s+[A-Z][A-Za-z'\-\.]+)*),\s+"
        r"([A-Z][A-Za-z'\-\.]+(?:\s+[A-Z][A-Za-z'\-\.]+)*"
        r"(?:\s+(?:Jr\.|Sr\.|II|III|IV))?)"
    )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Track the running team header — full team names sometimes
        # appear on their own line above their player block, sometimes
        # repeated on every player row. Either way, we keep the most
        # recently seen team as `current_team`.
        for full_name, abbr in _TEAM_ABBR.items():
            if full_name in line:
                current_team = abbr
                break

        m = _STATUS_REGEX.search(line)
        if not m:
            continue
        status = m.group(1)

        # Everything before the status token typically holds
        # ... team / matchup / "Last, First" ... The reason follows.
        before = line[: m.start()].strip()
        after = line[m.end():].strip()

        # Inline team override — if the line itself names a team, prefer
        # that over the running header (handles single-line per-row PDFs).
        # We also STRIP the team name from `before` so the name regex
        # does not get distracted by tokens like "Lakers" or "Warriors"
        # adjacent to "Last, First".
        line_team = current_team
        scrubbed = before
        for full_name, abbr in _TEAM_ABBR.items():
            if full_name in before:
                line_team = abbr
                scrubbed = scrubbed.replace(full_name, " ")
        scrubbed = re.sub(r"\s+", " ", scrubbed).strip()

        name_match = name_re.search(scrubbed)
        if not name_match:
            # Skip header rows like "Player Name Current Status Reason"
            # and any malformed orphan lines.
            continue
        last, first = name_match.group(1), name_match.group(2)
        name = f"{first} {last}"

        players.append({
            "team": line_team,
            "name": name,
            "status": status,
            "reason": after or "",
        })
    return players


def fetch_and_parse(
    target_date: _date_cls,
    project_dir: str = PROJECT_DIR,
    time_slot: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> Optional[str]:
    """End-to-end: fetch latest PDF, parse it, write JSON. Returns JSON path.

    Returns None if no PDF was found for the date (caller should treat
    as a non-fatal "no report today" condition).
    """
    cache_dir = os.path.join(project_dir, "data", "cache", "injuries")
    result = fetch_pdf_bytes(target_date, cache_dir, time_slot=time_slot, session=session)
    if result is None:
        print(f"  [no-report] no injury PDF found for {target_date.isoformat()}")
        return None
    pdf_bytes, slot = result

    text = _extract_text(pdf_bytes)
    players = parse_injury_text(text)
    print(f"  [parse] extracted {len(players)} player rows")

    out_path = os.path.join(
        project_dir, "data", f"injuries_{target_date.isoformat()}.json"
    )
    payload = {
        "date": target_date.isoformat(),
        "source_pdf": build_pdf_filename(target_date, slot),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "players": players,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  [write] {out_path}")
    return out_path


def _parse_date_arg(s: Optional[str]) -> _date_cls:
    if not s:
        return datetime.now().date()
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", help="YYYY-MM-DD (defaults to today)")
    ap.add_argument("--time", help="Force a specific publish slot, e.g. 05PM")
    args = ap.parse_args()

    d = _parse_date_arg(args.date)
    print(f"NBA injury report fetch for {d.isoformat()}"
          f"{' (' + args.time + ')' if args.time else ''}")
    out = fetch_and_parse(d, time_slot=args.time)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
