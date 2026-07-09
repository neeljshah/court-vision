"""scripts.platformkit.data_frontier.understat_xg -- understat.com match-level xG
(frontier census rank 5). The census's earlier probe (this session, before this
lane) found a "SCRAPABLE_POLITE" match-page blob and did not check robots.txt for
this specific host. A fresh check done as step 0 of THIS lane found:

    https://understat.com/robots.txt -> "User-agent: *\\nDisallow: /"

...a full-site disallow, added/changed since the earlier probe (a re-probe of the
match/league pages this session also shows the embedded JSON.parse data blob is
gone from server-rendered HTML now -- the site appears to have moved data loading
client-side). Politeness is a BINDING rail in this repo (see the census's own
mission statement + the task's HARD RAILS): a full Disallow: / means this source
is CLOSED, not merely inconvenient. This module does NOT scrape understat.

It still: (1) does the robots check live (so a future re-probe can catch the gate
lifting), (2) keeps a correctness-tested parser for the hex-escaped JSON.parse
blob format, gated behind the robots check so it can never fire against the real
site while blocked, (3) writes an honest status artifact instead of a data pull.

This is an honest REJECT, not a failure -- per the no-edge-claims discipline,
a confirmed-closed source is a successful finding, not a gap to route around.

CLI: python -m scripts.platformkit.data_frontier.understat_xg
"""
from __future__ import annotations

import argparse
import codecs
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from scripts.platformkit.data_frontier._politeness import atomic_write_text, log_line

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "cache" / "understat"
_STATUS_FP = _OUT_DIR / "status.json"
_LOG_FP = _REPO / "data" / "cache" / "logs" / "understat_pull.log"
_ROBOTS_URL = "https://understat.com/robots.txt"
_HDR = {"User-Agent": "Mozilla/5.0 (research; robots-compliance check)"}

TARGET_LEAGUE_SEASONS = [
    ("EPL", 2023), ("EPL", 2024),
    ("La_liga", 2023), ("La_liga", 2024),
    ("Bundesliga", 2023), ("Bundesliga", 2024),
    ("Serie_A", 2023), ("Serie_A", 2024),
]

_BLOB_RE = re.compile(r"JSON\.parse\('(.+?)'\)")


def check_robots(fetcher=None) -> Dict[str, object]:
    """Fetch robots.txt and decide if User-agent: * disallows the whole site
    ('Disallow: /' with no path suffix). Fail-closed: any fetch error -> BLOCKED
    (never assume open on ambiguity)."""
    get = fetcher or requests.get
    try:
        r = get(_ROBOTS_URL, headers=_HDR, timeout=20)
    except requests.RequestException as exc:
        return {"allowed": False, "reason": f"robots.txt fetch failed: {exc}"}
    if r.status_code != 200:
        return {"allowed": False, "reason": f"robots.txt HTTP {r.status_code}"}
    text = r.text if hasattr(r, "text") else r.content.decode("utf-8", "replace")
    star_block_disallow_all = bool(
        re.search(r"User-agent:\s*\*\s*\n\s*Disallow:\s*/\s*(\n|$)", text, re.IGNORECASE)
    )
    return {"allowed": not star_block_disallow_all, "reason": text.strip()[:500]}


def parse_blob(html: str) -> Optional[List[Dict[str, Any]]]:
    """Unescape one JSON.parse('\\x..') blob and return the decoded object/list.
    Pure function, no network -- exercised directly in tests against a synthetic
    blob since the real site is currently robots-blocked."""
    m = _BLOB_RE.search(html)
    if not m:
        return None
    raw = m.group(1)
    decoded = codecs.decode(raw, "unicode_escape").encode("latin-1").decode("utf-8")
    return json.loads(decoded)


def pull(fetcher=None) -> Dict[str, object]:
    gate = check_robots(fetcher=fetcher)
    if not gate["allowed"]:
        status = {
            "verdict": "BLOCKED_ROBOTS",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "robots_evidence": gate["reason"],
            "target_league_seasons": TARGET_LEAGUE_SEASONS,
            "note": "Full-site Disallow: / for User-agent: *. Not scraped. "
                    "Parser logic (parse_blob) is present and unit-tested but "
                    "never invoked against the live host while this gate holds.",
        }
        atomic_write_text(_STATUS_FP, json.dumps(status, indent=2))
        log_line(_LOG_FP, f"BLOCKED_ROBOTS {gate['reason'][:120]}")
        return status

    # Gate open: not reachable from this codebase today (no fetch path below
    # this line is exercised against the real site) -- left honestly unbuilt
    # rather than guessed at, per the "don't build past a confirmed gap" rail.
    status = {"verdict": "GATE_OPEN_UNIMPLEMENTED",
              "note": "robots.txt now permits understat.com; the league/match "
                      "page fetch+parse loop was not built because the gate was "
                      "closed for this entire lane -- build it when re-probed open."}
    atomic_write_text(_STATUS_FP, json.dumps(status, indent=2))
    log_line(_LOG_FP, "GATE_OPEN_UNIMPLEMENTED")
    return status


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="understat.com match xG (robots-gated).")
    ap.parse_args(argv)
    res = pull()
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["check_robots", "parse_blob", "pull", "main", "TARGET_LEAGUE_SEASONS"]
