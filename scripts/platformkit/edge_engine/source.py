"""edge_engine -- SourceAdapter interface + offline FileSource/MockSource + LiveSource stub.

The intake layer of the information-edge machine: it turns real-world feeds into a stream of
NewsItems, each stamped with captured_at (the vintage floor) BEFORE any LLM touches them. This
generalizes the freshness X1 capture step (which was injury-text-specific) into a sport-blind,
feed-agnostic adapter contract so any new source plugs in without touching the gate/extractor.

DESIGN (mirrors the freshness honesty model):
  - An adapter ONLY captures + stamps raw documents. It does NOT extract facts, does NOT call an
    LLM, and NEVER emits a number that enters a prediction. Extraction (NewsItem -> ExtractedSignal)
    is a separate, validated, vintage-guarded step (schema.to_signal + freshness.as_of_reader).
  - captured_at is stamped by US, deterministically, at capture time. For offline corpora it is
    read from the fixture (so leak-free replays are reproducible); for live feeds it is utcnow().
    The vintage guard later asserts every derived availability_ts predates the line/pred time.
  - The LiveSource is a documented STUB that raises NotImplementedError so CI stays hermetic and
    no secret/network is referenced. Wiring a real feed is a HUMAN-RUN step.

Stdlib only. <=300 LOC. Per-file test: test_source.py.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence

try:  # package import (external callers / `python -m ...`)
    from scripts.platformkit.edge_engine.schema import NewsItem, RawSource, SPORTS  # type: ignore
except ImportError:  # direct-script / per-file-test fallback
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from schema import NewsItem, RawSource, SPORTS  # type: ignore


def utc_now_iso() -> str:
    """Deterministic-shape UTC capture stamp (seconds precision, tz-aware)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalise_captured_at(raw: Optional[str], default: str) -> str:
    """Use the fixture's captured_at if present + valid; else fall back to `default`.

    Never silently invents a time for a row that claims one -- a bad stamp raises so a corrupt
    fixture cannot quietly become a leak.
    """
    if raw in (None, ""):
        return default
    datetime.fromisoformat(str(raw).replace("Z", "+00:00"))  # raises on malformed
    return str(raw)


class SourceAdapter(ABC):
    """The intake contract: yield NewsItems, each already stamped with captured_at.

    Subclasses implement `_raw_records()` -> an iterable of dicts (or pre-built NewsItems). The
    base `items()` enforces the invariants every downstream stage relies on:
      - every item has a non-empty source_id, text, url, and a valid ISO captured_at;
      - sport (if set) is one of SPORTS;
      - captured_at is stamped HERE (not by the extractor), so it is the true vintage floor.
    This keeps the leak guard's job honest: it can trust captured_at because the adapter owns it.
    """

    #: human-readable adapter name (audit / provenance).
    name: str = "source"

    @abstractmethod
    def _raw_records(self) -> Iterable[dict]:
        """Yield raw record dicts. Each MUST carry at least source_id/text/url.

        captured_at is OPTIONAL in the raw record: offline fixtures supply it (reproducible
        replay); live adapters omit it and the base stamps utc_now_iso().
        """
        raise NotImplementedError

    def _default_capture_ts(self) -> str:
        """The captured_at to stamp when a raw record omits one. Live adapters use 'now'."""
        return utc_now_iso()

    def items(self) -> Iterator[NewsItem]:
        """Validated NewsItem stream. The single public read path callers should use."""
        for rec in self._raw_records():
            if isinstance(rec, NewsItem):
                yield self._validated(rec)
                continue
            cap = _normalise_captured_at(rec.get("captured_at"), self._default_capture_ts())
            item = NewsItem(
                source_id=str(rec["source_id"]),
                text=str(rec["text"]),
                url=str(rec.get("url", "")),
                captured_at=cap,
                sport=str(rec.get("sport", "")),
                doc_date=rec.get("doc_date"),
            )
            yield self._validated(item)

    def raw_sources(self) -> List[RawSource]:
        """Provenance rows for everything this adapter yielded (audit / dedupe)."""
        out: List[RawSource] = []
        for it in self.items():
            out.append(RawSource(source_id=it.source_id, url=it.url,
                                  captured_at=it.captured_at))
        return out

    @staticmethod
    def _validated(item: NewsItem) -> NewsItem:
        assert item.source_id, "NewsItem missing source_id"
        assert item.text, "NewsItem missing text"
        assert item.captured_at, "NewsItem missing captured_at (the vintage floor)"
        datetime.fromisoformat(str(item.captured_at).replace("Z", "+00:00"))  # raises on bad ts
        if item.sport:
            assert item.sport in SPORTS, f"bad sport {item.sport}"
        return item


class MockSource(SourceAdapter):
    """In-memory adapter for offline tests. Pass raw dicts or NewsItems directly.

    Lets a test exercise the full intake -> extraction -> gate path with zero IO and a fixed
    captured_at, so leak-free behaviour is asserted deterministically.
    """

    name = "mock"

    def __init__(self, records: Sequence[dict], default_captured_at: Optional[str] = None):
        self._records = list(records)
        self._default = default_captured_at or "2026-01-15T09:00:00+00:00"

    def _default_capture_ts(self) -> str:
        return self._default

    def _raw_records(self) -> Iterable[dict]:
        return iter(self._records)


class FileSource(SourceAdapter):
    """Offline corpus adapter: reads a JSON or JSONL fixture of raw records.

    The leak-free REPLAY path. Each fixture row must carry source_id/text/url and SHOULD carry
    its own captured_at (so the recorded vintage is reproduced exactly); rows missing one are
    stamped at load with default_captured_at, never with live 'now', to keep replays hermetic.

    JSON  : a top-level list of record dicts, or {"items": [...]}.
    JSONL : one record dict per line (blank lines ignored).
    """

    name = "file"

    def __init__(self, path: str, default_captured_at: str = "1970-01-01T00:00:00+00:00"):
        self.path = Path(path)
        self._default = default_captured_at

    def _default_capture_ts(self) -> str:
        return self._default

    def _raw_records(self) -> Iterable[dict]:
        assert self.path.exists(), f"fixture not found: {self.path}"
        text = self.path.read_text(encoding="utf-8")
        if self.path.suffix == ".jsonl":
            for line in text.splitlines():
                line = line.strip()
                if line:
                    yield json.loads(line)
            return
        obj = json.loads(text)
        rows = obj["items"] if isinstance(obj, dict) and "items" in obj else obj
        assert isinstance(rows, list), "JSON fixture must be a list or {'items': [...]}"
        for rec in rows:
            yield rec


class LiveSource(SourceAdapter):
    """STUB for a real live feed (beat-reporter X stream, presser transcripts, weather API, ...).

    DELIBERATELY NOT IMPLEMENTED so CI is hermetic and no secret/network is referenced. Wiring a
    real feed is a HUMAN-RUN step. The contract a live implementation MUST honour:

      - poll/stream the feed; for each new document build a raw record with source_id/text/url;
      - stamp captured_at = utc_now_iso() AT CAPTURE (the vintage floor; never back-date it);
      - do NOT extract facts and do NOT call an LLM here -- that is the separate, vintage-guarded
        extraction step (schema.to_signal); this layer only captures + stamps;
      - dedupe by source_id so a re-poll never re-emits (and never rewrites an earlier
        captured_at -- the first sighting is the leak floor);
      - on any availability_ts derived later, the freshness vintage guard asserts it predates the
        line/pred time, so a fact captured after the move is correctly dropped as hindsight.

    The shapes (NewsItem/RawSource) are identical to the offline adapters, so a live feed is a
    drop-in replacement for FileSource in the intake -> extraction -> gate pipeline.
    """

    name = "live"

    def __init__(self, feed: str = ""):
        self.feed = feed

    def _default_capture_ts(self) -> str:
        return utc_now_iso()

    def _raw_records(self) -> Iterable[dict]:
        raise NotImplementedError(
            "LiveSource is a HUMAN-RUN step: wire the real feed (poll/stream), stamp "
            "captured_at=utc_now_iso() at capture, dedupe by source_id, and DO NOT extract "
            "facts or call an LLM here. The STUB exists so CI stays hermetic and the intake "
            "layer never authors a number that enters a prediction."
        )
