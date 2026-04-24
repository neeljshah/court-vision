"""Source registry: available video sources with health tracking."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Dict, List, Optional

COOKIES_PATH = Path(__file__).parents[2] / "data" / "videos" / "youtube_cookies.txt"
YT_ARCHIVE   = Path(__file__).parents[2] / "data" / "ingest" / "yt_archive.txt"


@dataclass
class Source:
    name: str
    priority: int           # lower = higher priority
    partial: bool = False   # True if source produces partial games
    _history: List[bool] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, success: bool) -> None:
        with self._lock:
            self._history.append(success)
            if len(self._history) > 50:
                self._history.pop(0)

    @property
    def health_score(self) -> float:
        with self._lock:
            if not self._history:
                return 0.5
            return sum(self._history) / len(self._history)

    def to_dict(self) -> dict:
        return {"name": self.name, "priority": self.priority,
                "partial": self.partial, "health": round(self.health_score, 3),
                "attempts": len(self._history)}


class SourceRegistry:
    """Registry of all video sources, ordered by priority × health."""

    _instance: ClassVar[Optional["SourceRegistry"]] = None

    def __init__(self) -> None:
        self._sources: Dict[str, Source] = {
            "youtube":       Source("youtube",       priority=1),
            "archive_org":   Source("archive_org",   priority=2),
            "nba_condensed": Source("nba_condensed", priority=3, partial=True),
            "inbox":         Source("inbox",         priority=0),  # local first
        }

    @classmethod
    def get(cls) -> "SourceRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls()   # fresh per call (stateless for tests)

    def by_priority(self) -> List[Source]:
        return sorted(self._sources.values(), key=lambda s: (s.priority, -s.health_score))

    def record(self, source_name: str, success: bool) -> None:
        if source_name in self._sources:
            self._sources[source_name].record(success)

    def get_source(self, name: str) -> Optional[Source]:
        return self._sources.get(name)

    def has_cookies(self) -> bool:
        return COOKIES_PATH.exists()

    def youtube_flags(self) -> List[str]:
        flags = [
            "--extractor-args", "youtube:player_client=android",
            "--download-archive", str(YT_ARCHIVE),
            "--continue",
        ]
        if self.has_cookies():
            flags += ["--cookies", str(COOKIES_PATH)]
        return flags

    def status_dict(self) -> dict:
        return {name: src.to_dict() for name, src in self._sources.items()}
