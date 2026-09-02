"""Keep sport footage queues supplied with gated plausible broadcasts."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from itertools import zip_longest
from pathlib import Path
from typing import Iterable

from scripts.platformkit import queue_content_gate


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
FORMAT = "bv*[height>=1080][vcodec^=avc1]+ba/b[height<=720]"
SOURCE_SCAN_LIMIT = 100
DATA_DIR = Path("data")
TRACKING_DIR = DATA_DIR / "tracking"
COOKIES_FILE = DATA_DIR / "videos" / "youtube_cookies.txt"
SOURCES: dict[str, tuple[str, ...]] = {
    "tennis": ("https://www.youtube.com/@Wimbledon", "https://www.youtube.com/@WTA/videos", "https://www.youtube.com/@AustralianOpen", "https://www.youtube.com/channel/UCXbboag48Qlr78zzz6SkzkQ"),
    "wnba": ("https://www.youtube.com/channel/UCyxylYlXhJgXC3llr8MFFdg", "https://www.youtube.com/channel/UCuf89_9rUWA57uhOo4RVBJQ", "https://www.youtube.com/channel/UCENzOltnQs6-YrP9YB0Dj2A"),
    "npb": ("https://www.youtube.com/playlist?list=PL_oduM_8vk9KkN1wAaw4xLTOtYTt78Qhu", "https://www.youtube.com/channel/UCzXRQAqRTc5t3BJ98MAT9eA"),
    "kbo": ("https://www.youtube.com/channel/UCoVz66yWHzVsXAFG8WhJK9g", "https://www.youtube.com/channel/UCuVEzujV3dz-TMPLRu8xftA", "https://www.youtube.com/channel/UCpQFL32AhVo1KP_dOH_jVGw"),
    "soccer": ("https://www.youtube.com/playlist?list=PLCGIzmTE4d0jq6wHT2TvSspZ_HLiIx4_y", "https://www.youtube.com/channel/UC14UlmYlSNiQCBe9Eookf_A", "https://www.youtube.com/channel/UCChcWqwYXCEs657MQ00qVWA"),
    "football": ("https://www.youtube.com/channel/UCDVYQ4Zhbm3S2dlz7P1GBDg", "https://www.youtube.com/channel/UC60q_WUDde_NK-ze3frvtiA", "https://www.youtube.com/channel/UC0hy7TcR1gGD8nQBqrF2FaA", "https://www.youtube.com/channel/UCLnfOCTbfqMy_3ah8OmTHEQ"),
    "mlb": ("https://www.youtube.com/channel/UCoLrcjPV5PbUrUyXq5mjc_A", "https://www.youtube.com/channel/UCbQ07z3YBi8RUc6nBxJhg2Q", "https://www.youtube.com/channel/UCO5KCH3BmO44_hAoG0o0CEQ"),
    "nhl": ("https://www.youtube.com/channel/UCqFMzb-4AUf6WAIbl132QKA", "https://www.youtube.com/channel/UCVhibwHk4WKw4leUt6JfRLg", "https://www.youtube.com/channel/UCXu8ydY_RcF0LetIBpJwbQQ"),
    "ncaa_basketball": ("https://www.youtube.com/channel/UCKjEtnnXEHsXE9IvCb92V7g", "https://www.youtube.com/channel/UC0hy7TcR1gGD8nQBqrF2FaA"),
    "cricket": ("https://www.youtube.com/channel/UCz1D0n02BR3t51KuBOPmfTQ", "https://www.youtube.com/channel/UC2MHTOXktfTK26aDKyQs3cQ", "https://www.youtube.com/channel/UCt2JXOLNxqry7B_4rRZME3Q", "https://www.youtube.com/channel/UCv5-1Ypl3Adf4uGaR_H0mlg"),
    "handball": ("https://www.youtube.com/channel/UCTl3QQTvqHFjurroKxexy2Q", "https://www.youtube.com/channel/UCxw1sC_Ksoa1vguE53HCSIg"),
    "volleyball": ("https://www.youtube.com/channel/UCYbbpwosQ0a2d3ygPpruJ1w", "https://www.youtube.com/channel/UCNMg6XDhRZI2QzL4pWOvP_w", "https://www.youtube.com/channel/UC0hy7TcR1gGD8nQBqrF2FaA"),
}
MIN_DURATION_SECONDS = {"tennis": 3600, "wnba": 4500, "npb": 4500, "kbo": 4500,
    "soccer": 5000, "football": 2400, "mlb": 7200, "nhl": 3600,
    "ncaa_basketball": 3600, "cricket": 6000, "handball": 3600, "volleyball": 3000}


def is_video_id(value: str) -> bool:
    """True only for real 11-character YouTube IDs."""
    return bool(_VIDEO_ID.match(str(value or "").strip()))


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
    command = ["yt-dlp", "--flat-playlist", "--playlist-end", str(SOURCE_SCAN_LIMIT),
               "--print", field]
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
        ids.add(str(item.get("game_id") or ""))
        url = str(item.get("url") or "")
        if "v=" in url:
            ids.add(url.split("v=", 1)[1].split("&", 1)[0])
    return ids


def _write_atomic(path: Path, items: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     delete=False, suffix=".tmp") as handle:
        handle.write(json.dumps(items, indent=2) + "\n")
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def _candidate_items(sport: str, urls: Iterable[str], known_ids: set[str]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for url in urls:
        for video_id, duration_text in zip_longest(_yt_dlp(url, "id"), _yt_dlp(url, "duration"), fillvalue=""):
            if not is_video_id(video_id) or video_id in known_ids:
                continue
            if (TRACKING_DIR / (sport + "_" + video_id)).is_dir():
                continue
            duration = _duration(duration_text)
            if duration is None or duration < MIN_DURATION_SECONDS[sport]:
                continue
            candidates.append({"sport": sport, "game_id": sport + "_" + video_id,
                               "url": "https://www.youtube.com/watch?v=" + video_id,
                               "format": FORMAT})
            known_ids.add(video_id)
    return candidates


def _gate_queue_items(sport: str, items: list[dict[str, str]]) -> list[dict[str, str]]:
    """The one shared gate for legacy and newly discovered items."""
    return queue_content_gate.gate_items(items, sport, COOKIES_FILE)


def expand_queue(sport: str, channel_or_playlist_urls: Iterable[str], target_pending: int = 15) -> list[dict[str, str]]:
    """Regate every queue item, then append enough newly gated items to meet target."""
    if sport not in MIN_DURATION_SECONDS:
        raise ValueError("Unsupported sport: %s" % sport)
    if target_pending < 0:
        raise ValueError("target_pending must be non-negative")
    queue_path = _queue_path(sport)
    items = _gate_queue_items(sport, _load_queue(queue_path))
    pending = [item for item in items if not (TRACKING_DIR / item["game_id"]).is_dir()]
    known_ids = _existing_ids(items)
    if len(pending) < target_pending:
        candidates = _candidate_items(sport, channel_or_playlist_urls, known_ids)
        items.extend(_gate_queue_items(sport, candidates[:target_pending - len(pending)]))
    _write_atomic(queue_path, items)
    return items


def main() -> None:
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
