"""Keep sport footage queues supplied with plausible full-game broadcasts."""
from __future__ import annotations

import argparse
import json
import re
import os
import subprocess
import tempfile
from itertools import zip_longest
from pathlib import Path
from typing import Iterable


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def is_video_id(value: str) -> bool:
    """True only for real 11-character YouTube video ids.

    --flat-playlist can emit playlist/channel ids (PL..., UC...); queueing those
    produced 'Video unavailable' on every item and stalled every runner.
    """
    return bool(_VIDEO_ID.match(str(value or "").strip()))


FORMAT = "bv*[height>=1080][vcodec^=avc1]+ba/b[height<=720]"
DATA_DIR = Path("data")
TRACKING_DIR = DATA_DIR / "tracking"
COOKIES_FILE = DATA_DIR / "videos" / "youtube_cookies.txt"

# Channels use their playlist tabs so yt-dlp can discover newly published full games.
SOURCES: dict[str, tuple[str, ...]] = {
    "tennis": (
        "https://www.youtube.com/@usopen/playlists",
        "https://www.youtube.com/@rolandgarros/playlists",
        "https://www.youtube.com/@Wimbledon/playlists",
        "https://www.youtube.com/@AustralianOpenTV/playlists",
        "https://www.youtube.com/@WTA/playlists",
    ),
    "wnba": ("https://www.youtube.com/channel/UCyxylYlXhJgXC3llr8MFFdg",),
    "npb": ("https://www.youtube.com/playlist?list=PL_oduM_8vk9KkN1wAaw4xLTOtYTt78Qhu",),
    "kbo": ("https://www.youtube.com/channel/UCoVz66yWHzVsXAFG8WhJK9g",),
    "soccer": ("https://www.youtube.com/playlist?list=PLCGIzmTE4d0jq6wHT2TvSspZ_HLiIx4_y",),
}
MIN_DURATION_SECONDS = {"tennis": 3600, "wnba": 4500, "npb": 4500, "kbo": 4500, "soccer": 5000}


def _queue_path(sport: str) -> Path:
    return DATA_DIR / ("footage_queue_%s.json" % sport)


def _load_queue(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Queue must be a JSON list: %s" % path)
    return items


def _yt_dlp(url: str, field: str) -> list[str]:
    command = ["yt-dlp", "--flat-playlist", "--print", field]
    if COOKIES_FILE.is_file():
        command.extend(["--cookies", str(COOKIES_FILE)])
    command.append(url)
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines()]


def _duration(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _existing_ids(items: Iterable[dict[str, str]]) -> set[str]:
    ids: set[str] = set()
    for item in items:
        game_id = item.get("game_id", "")
        if game_id:
            ids.add(game_id)
        url = item.get("url", "")
        if "v=" in url:
            ids.add(url.split("v=", 1)[1].split("&", 1)[0])
    return ids


def _write_atomic(path: Path, items: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        handle.write(json.dumps(items, indent=2) + "\n")
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def expand_queue(
    sport: str, channel_or_playlist_urls: Iterable[str], target_pending: int = 15
) -> list[dict[str, str]]:
    """Append eligible YouTube videos until the sport queue has target pending items."""
    if sport not in MIN_DURATION_SECONDS:
        raise ValueError("Unsupported sport: %s" % sport)
    if target_pending < 0:
        raise ValueError("target_pending must be non-negative")

    queue_path = _queue_path(sport)
    items = _load_queue(queue_path)
    pending = [item for item in items if not (TRACKING_DIR / item["game_id"]).is_dir()]
    known_ids = _existing_ids(items)
    for url in channel_or_playlist_urls:
        video_ids = _yt_dlp(url, "id")
        durations = _yt_dlp(url, "duration")
        for video_id, duration_text in zip_longest(video_ids, durations, fillvalue=""):
            if not is_video_id(video_id):
                continue  # skips playlist/channel ids from --flat-playlist
            game_id = "%s_%s" % (sport, video_id)
            duration = _duration(duration_text)
            if len(pending) >= target_pending:
                break
            if video_id in known_ids or game_id in known_ids:
                continue
            if (TRACKING_DIR / game_id).is_dir():
                continue
            if duration is not None and duration < MIN_DURATION_SECONDS[sport]:
                continue
            item = {
                "sport": sport,
                "game_id": game_id,
                "url": "https://www.youtube.com/watch?v=%s" % video_id,
                "format": FORMAT,
            }
            items.append(item)
            pending.append(item)
            known_ids.update((video_id, game_id))
        if len(pending) >= target_pending:
            break
    _write_atomic(queue_path, items)
    return items


def main() -> None:
    """Expand selected footage queues from the maintained source table."""
    parser = argparse.ArgumentParser(description="Expand footage queues from YouTube sources")
    parser.add_argument("--sports", default="all", help="Comma-separated sports or all")
    parser.add_argument("--target", type=int, default=15)
    args = parser.parse_args()
    sports = tuple(SOURCES) if args.sports == "all" else tuple(args.sports.split(","))
    for sport in sports:
        if sport not in SOURCES:
            raise ValueError("Unsupported sport: %s" % sport)
        entries = expand_queue(sport, SOURCES[sport], args.target)
        print("sport=%s queue_items=%d" % (sport, len(entries)))


if __name__ == "__main__":
    main()
