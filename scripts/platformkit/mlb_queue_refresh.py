"""Refresh the small MLB direct-download queue."""
import argparse
import json
from pathlib import Path

from scripts.platformkit.mlb_condensed_scraper import (
    DEFAULT_URL, build_queue, extract_mp4_urls, fetch_page,
)


def refresh(url=DEFAULT_URL, out=Path("data/footage_queue_mlb.json")):
    """Fetch, merge, and cap pending MLB jobs; return the added count."""
    path = Path(out)
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        old = []
    old = old if isinstance(old, list) else []
    new = build_queue(extract_mp4_urls(fetch_page(url)), limit=10)
    seen = {item.get("game_id") for item in old}
    added = [item for item in new if item.get("game_id") not in seen]
    merged = old + added
    fixed = [item for item in merged if item.get("status") not in (None, "pending")]
    pending = [item for item in merged if item.get("status") in (None, "pending")]
    merged = fixed + pending[:10]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return len([item for item in added if item in pending[:10]])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", type=Path, default=Path("data/footage_queue_mlb.json"))
    args = parser.parse_args()
    print(f"Added {refresh(args.url, args.out)} MLB queue items")


if __name__ == "__main__":
    main()
