"""Reject queue entries whose TITLE says they are not this sport.

The football queue held 60 entries of which 41 were not American football: 14
ACC soccer matches, 9 volleyball, a women's basketball tournament game, and 17
press conferences, podcasts and teleconferences. queue_expander accepted them
because it filtered on `duration >= MIN_DURATION_SECONDS` and never looked at
what the video was.

A decode-based content gate exists and is the stronger check, but it costs a
download per candidate and it cannot separate soccer from American football --
both are green fields. Titles are free, are fetched from metadata alone, and on
the observed queue they separate the two classes exactly.

This is deliberately an EXCLUSION rule rather than an inclusion one. "Must
mention football" would reject a genuine NFL game titled
"Giants vs. Jets FULL Preseason Game 2010"; naming the sports and formats we do
NOT want is both safer and easier to audit.

Run: python -m scripts.platformkit.queue_title_filter <queue.json> [--apply]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Other sports, and formats that are talk rather than play.
WRONG_SPORT = ("soccer", "volleyball", "basketball", "baseball", "softball",
               "lacrosse", "hockey", "tennis", "golf")
NOT_A_GAME = ("press conference", "teleconference", "podcast", "panel",
              "coaches", "second acts", "lots to say", "interview",
              "media day", "spring game preview", "top 10", "highlights show")
_EXCLUDE = re.compile(r"\b(%s)\b" % "|".join(WRONG_SPORT + NOT_A_GAME), re.I)


def rejects(title: str) -> str | None:
    """The excluded phrase this title matched, or None to keep it."""
    found = _EXCLUDE.search(title or "")
    return found.group(0) if found else None


def fetch_title(url: str) -> str:
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--no-playlist", "--print", "%(title)s", url],
            capture_output=True, text=True, timeout=90)
        for line in reversed((result.stdout or "").strip().splitlines()):
            if line.strip() and "Deprecated" not in line:
                return line.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def audit(items: list) -> tuple[list, list]:
    """Split queue items into (kept, rejected-with-reason)."""
    urls = [item.get("url", "") for item in items]
    with ThreadPoolExecutor(max_workers=6) as pool:
        titles = list(pool.map(fetch_title, urls))
    kept, dropped = [], []
    for item, title in zip(items, titles):
        if not title:
            kept.append(item)          # fail OPEN: an unreadable title is not evidence
            continue
        reason = rejects(title)
        if reason:
            dropped.append((item, title, reason))
        else:
            kept.append(item)
    return kept, dropped


def main(argv: list) -> int:
    if len(argv) < 2:
        print("usage: queue_title_filter.py <queue.json> [--apply]")
        return 2
    path = Path(argv[1])
    items = json.loads(path.read_text(encoding="utf-8"))
    kept, dropped = audit(items)
    for item, title, reason in dropped:
        print("DROP  %-30s [%s]  %s" % (item.get("game_id"), reason, title[:70]))
    print()
    print("kept %d, dropped %d of %d" % (len(kept), len(dropped), len(items)))
    if "--apply" in argv:
        path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
        print("applied to %s" % path)
    else:
        print("(dry run; pass --apply to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
