"""forward_capture -- the ODDS FEED intake contract (OddsFeed + MockFeed + RealFeed stub).

This is the live-tape analogue of edge_engine/source.py (which captures unstructured NEWS).
Where SourceAdapter yields NewsItems, an OddsFeed yields OddsSnapshots: one timestamped
(book, market, sport, game_id, side, price) quote, stamped with captured_at AT POLL TIME.
The archive (archive.py) then accrues these forward into the real movement corpus, and clv.py
grades a logged prediction's CLV vs the devigged close -- but ONLY when the prediction's pred_ts
strictly precedes the captured line move (vintage-strict via freshness.assert_vintage).

DESIGN (mirrors the freshness/edge_engine honesty model exactly):
  - A feed ONLY captures + stamps quotes. It computes NO devig, NO edge, NO probability, and
    NEVER authors a number that enters a prediction. Devigging is shin.shin_devig downstream;
    CLV is clv.py downstream; both are deterministic and vintage-guarded.
  - captured_at is stamped by US at poll time. For the MockFeed it is read from the fixture (so
    archive idempotency + CLV vintage tests are reproducible); for a real feed it is utcnow(),
    the vintage floor -- a quote can never be back-dated below when we actually saw it.
  - The RealFeed is a DOCUMENTED, ENV-GATED STUB that raises NotImplementedError. It references
    NO secret and makes NO network call, so CI stays hermetic. Wiring a real feed (the_odds_api
    or a book tape) is a HUMAN-RUN step. This RECORDS data; it CLAIMS no edge.

Stdlib only. <=300 LOC. Per-file test: tests/test_capture.py.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

try:  # package import (external callers / `python -m ...`)
    from scripts.platformkit.forward_capture.schema import OddsSnapshot  # type: ignore
except ImportError:  # direct-script / per-file-test fallback (sibling schema.py)
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from schema import OddsSnapshot  # type: ignore
    except ImportError:  # schema.py authored by a sibling task; minimal local shim for tests
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class OddsSnapshot:  # type: ignore[no-redef]
            """Local shim mirroring forward_capture/schema.OddsSnapshot.

            Present ONLY so this module + its per-file test run hermetically before the
            sibling schema.py lands. The real schema.py is the single source of truth; when
            it is importable the shim is never used. Fields + order match the spec exactly.
            """

            book: str
            market: str
            sport: str
            game_id: str
            side: str
            price: float
            captured_at: str

            def as_dict(self) -> dict:
                return {
                    "book": self.book, "market": self.market, "sport": self.sport,
                    "game_id": self.game_id, "side": self.side,
                    "price": float(self.price), "captured_at": self.captured_at,
                }


# the_odds_api / book-tape feed is ON only when this env var holds a real key (human-run).
REAL_FEED_ENV = "FORWARD_CAPTURE_ODDS_API_KEY"


def utc_now_iso() -> str:
    """Deterministic-shape UTC capture stamp (seconds precision, tz-aware) -- the vintage floor."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _assert_iso(ts: str) -> str:
    """Raise on a malformed captured_at so a corrupt feed cannot quietly become a leak."""
    datetime.fromisoformat(str(ts).replace("Z", "+00:00"))  # raises on malformed
    return str(ts)


class OddsFeed(ABC):
    """The intake contract: poll() -> a list of OddsSnapshots, each already stamped captured_at.

    Subclasses implement `_raw_quotes()` -> an iterable of dicts (or pre-built OddsSnapshots).
    The base `poll()` enforces the invariants the archive + CLV grader rely on:
      - every snapshot carries non-empty book/market/sport/game_id/side, a numeric price, and a
        valid ISO captured_at (the vintage floor, stamped HERE not downstream);
      - price is coerced to float once, at the boundary, so the archive never stores a string.
    A feed NEVER devigs, NEVER computes an edge, and NEVER emits a probability.
    """

    #: human-readable feed name (audit / provenance).
    name: str = "feed"

    @abstractmethod
    def _raw_quotes(self) -> Iterable[dict]:
        """Yield raw quote dicts. Each MUST carry book/market/sport/game_id/side/price.

        captured_at is OPTIONAL in the raw quote: fixtures supply it (reproducible archive +
        CLV tests); a live feed omits it and the base stamps utc_now_iso() at poll time.
        """
        raise NotImplementedError

    def _default_capture_ts(self) -> str:
        """The captured_at to stamp when a raw quote omits one. Live feeds use 'now'."""
        return utc_now_iso()

    def poll(self) -> List[OddsSnapshot]:
        """Validated OddsSnapshot list -- the single public read path callers + the runner use."""
        out: List[OddsSnapshot] = []
        for q in self._raw_quotes():
            if isinstance(q, OddsSnapshot):
                out.append(self._validated(q))
                continue
            cap = q.get("captured_at") or self._default_capture_ts()
            snap = OddsSnapshot(
                book=str(q["book"]),
                market=str(q["market"]),
                sport=str(q["sport"]),
                game_id=str(q["game_id"]),
                side=str(q["side"]),
                price=float(q["price"]),
                captured_at=_assert_iso(cap),
            )
            out.append(self._validated(snap))
        return out

    @staticmethod
    def _validated(snap: OddsSnapshot) -> OddsSnapshot:
        for field_name in ("book", "market", "sport", "game_id", "side"):
            assert getattr(snap, field_name), f"OddsSnapshot missing {field_name}"
        assert isinstance(snap.price, float), "OddsSnapshot price must be float"
        assert snap.price > 1.0, "decimal price must be > 1 (devig-able quote)"
        assert snap.captured_at, "OddsSnapshot missing captured_at (the vintage floor)"
        _assert_iso(snap.captured_at)
        return snap


class MockFeed(OddsFeed):
    """In-memory, DETERMINISTIC feed for tests + the runner's DRY RUN.

    Pass raw quote dicts (or OddsSnapshots) directly. With fixture-supplied captured_at the
    output is byte-stable across runs, so archive idempotency and CLV vintage behaviour are
    asserted deterministically with zero IO and zero network.
    """

    name = "mock"

    def __init__(self, quotes: Sequence[dict], default_captured_at: Optional[str] = None):
        self._quotes = list(quotes)
        self._default = default_captured_at or "2026-01-15T17:00:00+00:00"

    def _default_capture_ts(self) -> str:
        return self._default

    def _raw_quotes(self) -> Iterable[dict]:
        return iter(self._quotes)


class FileFeed(OddsFeed):
    """Offline corpus feed: replays a JSON / JSONL fixture of raw quote dicts.

    The leak-free REPLAY path (mirrors edge_engine FileSource). Each fixture row must carry
    book/market/sport/game_id/side/price and SHOULD carry its own captured_at so the recorded
    vintage is reproduced exactly; a row missing one is stamped with default_captured_at at
    load -- NEVER with live 'now' -- to keep replays hermetic.

    JSON  : a top-level list of quote dicts, or {"quotes": [...]}.
    JSONL : one quote dict per line (blank lines ignored).
    """

    name = "file"

    def __init__(self, path: str, default_captured_at: str = "1970-01-01T00:00:00+00:00"):
        self.path = Path(path)
        self._default = default_captured_at

    def _default_capture_ts(self) -> str:
        return self._default

    def _raw_quotes(self) -> Iterable[dict]:
        assert self.path.exists(), f"fixture not found: {self.path}"
        text = self.path.read_text(encoding="utf-8")
        if self.path.suffix == ".jsonl":
            for line in text.splitlines():
                line = line.strip()
                if line:
                    yield json.loads(line)
            return
        obj = json.loads(text)
        rows = obj["quotes"] if isinstance(obj, dict) and "quotes" in obj else obj
        assert isinstance(rows, list), "JSON fixture must be a list or {'quotes': [...]}"
        for q in rows:
            yield q


class RealFeed(OddsFeed):
    """STUB for a real odds tape (the_odds_api, or a sportsbook line tape) -- ENV-GATED, NO CALL.

    DELIBERATELY NOT IMPLEMENTED so CI is hermetic: it references NO secret and makes NO network
    call. The key is read from the environment (FORWARD_CAPTURE_ODDS_API_KEY), never hardcoded,
    and is NOT used here -- poll() raises before any request. Wiring the real feed is a HUMAN-RUN
    step. The contract a real implementation MUST honour:

      - poll the_odds_api (or read the book tape) for each tracked game/market;
      - for each quote build a raw dict with book/market/sport/game_id/side/price (DECIMAL odds);
      - stamp captured_at = utc_now_iso() AT POLL TIME (the vintage floor; NEVER back-date it);
      - do NOT devig, do NOT compute an edge, do NOT emit a probability here -- archive.py stores
        the raw quotes and clv.py (reusing eval_gate/shin) devigs the close downstream;
      - the archive dedupes on (game_id, book, market, captured_at) so a re-poll never doubles a
        row; the FIRST sighting at a captured_at is the immutable record.

    OddsSnapshot is identical to the offline feeds, so a real feed is a drop-in replacement for
    MockFeed/FileFeed in run_capture.py. This RECORDS the movement corpus; it CLAIMS no edge.
    """

    name = "real"

    def __init__(self, api_key_env: str = REAL_FEED_ENV):
        self.api_key_env = api_key_env
        # Read presence ONLY (never log/return the value); used solely by has_real_feed().
        self._key_present = bool(os.environ.get(api_key_env))

    @property
    def configured(self) -> bool:
        """True iff the env key is present. Does NOT expose or use the key's value."""
        return self._key_present

    def _default_capture_ts(self) -> str:
        return utc_now_iso()

    def _raw_quotes(self) -> Iterable[dict]:
        raise NotImplementedError(
            "RealFeed is a HUMAN-RUN step: set %s in the environment, then implement poll() to "
            "fetch the_odds_api / a book tape, stamp captured_at=utc_now_iso() AT POLL TIME, "
            "and DO NOT devig / compute an edge / emit a probability here. The STUB exists so CI "
            "stays hermetic (no secret in code, no live call) and the intake layer never authors "
            "a number that enters a prediction." % self.api_key_env
        )


def has_real_feed(api_key_env: str = REAL_FEED_ENV) -> bool:
    """True iff a real odds-feed key is present in the environment (the 'clock is real' switch).

    run_capture.py uses this to decide between the real clock and the MockFeed DRY RUN. It checks
    PRESENCE only and never returns / logs the key value.
    """
    return bool(os.environ.get(api_key_env))


def build_feed(quotes: Optional[Sequence[dict]] = None,
               api_key_env: str = REAL_FEED_ENV) -> OddsFeed:
    """Select the feed the runner should use.

    If a real key is present -> RealFeed (whose poll() raises until a human wires it). Otherwise
    -> a deterministic MockFeed over `quotes` (DRY RUN). The selection NEVER reads the key value;
    it only branches on presence, so no secret is touched here.
    """
    if has_real_feed(api_key_env):
        return RealFeed(api_key_env=api_key_env)
    return MockFeed(list(quotes or []))
