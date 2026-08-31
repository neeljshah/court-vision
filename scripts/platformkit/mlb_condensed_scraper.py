"""Collect direct MLB condensed-game MP4 URLs into a footage-cycle queue."""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Iterable


DEFAULT_URL = "https://www.mlb.com/video/topic/condensed-games"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MP4_RE = re.compile(
    r"https://mlb-cuts-diamond\.mlb\.com/FORGE/"
    r"(?P<year>\d{4})/\d{4}-(?P<month>\d{2})/(?P<day>\d{2})/"
    r"(?P<asset>[A-Za-z0-9_-]+)-asset_[^\"'\\s<>]*?_(?P<variant>16000K|4000K)\.mp4"
)
_TITLE_RE = re.compile(r"(?:title|aria-label)=['\"]([^'\"]+)['\"]", re.IGNORECASE)


def fetch_page(url: str) -> str:
    """Fetch *url* with the lightweight user agent used by this scraper."""
    request = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def extract_mp4_urls(html: str) -> list[dict]:
    """Return direct condensed-game MP4 records found in MLB page HTML."""
    records = []
    for match in _MP4_RE.finditer(html):
        before = html[max(0, match.start() - 300):match.start()]
        titles = _TITLE_RE.findall(before)
        records.append({
            "url": match.group(0),
            "date": "-".join((match.group("year"), match.group("month"), match.group("day"))),
            "variant": match.group("variant"),
            "game_hint": titles[-1].strip() if titles else "",
        })
    return records


def _asset_key(record: dict) -> tuple[str, str]:
    """Return the date and source asset ID that identify one condensed game."""
    filename = record["url"].rsplit("/", 1)[-1]
    return record["date"], filename.split("-asset_", 1)[0]


def build_queue(urls: Iterable[dict], limit: int = 10) -> list[dict]:
    """Deduplicate source records and build direct-download footage jobs."""
    selected: dict[tuple[str, str], dict] = {}
    for record in urls:
        key = _asset_key(record)
        previous = selected.get(key)
        if previous is None or record["variant"] == "4000K":
            selected[key] = record
    queue = []
    for record in list(selected.values())[:limit]:
        _, asset = _asset_key(record)
        queue.append({
            "sport": "baseball",
            "game_id": f"mlb_{record['date']}_{asset[:8]}",
            "url": record["url"],
            "format": "direct",
        })
    return queue


def main() -> None:
    """Fetch the MLB topic page and write a direct-download footage queue."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", type=Path, default=_REPO_ROOT / "data" / "footage_queue_mlb.json")
    parser.add_argument("--variant", choices=("16000K", "4000K"))
    args = parser.parse_args()

    records = extract_mp4_urls(fetch_page(DEFAULT_URL))
    if args.variant:
        records = [record for record in records if record["variant"] == args.variant]
    queue = build_queue(records, limit=args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(queue)} direct MLB footage jobs to {args.out}")


if __name__ == "__main__":
    main()
