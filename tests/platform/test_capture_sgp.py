"""test_capture_sgp.py — Offline unit tests for scripts/platformkit/capture/capture_sgp.py.

All tests run without network access.  A stub client replaces SgpOddsAPIClient.
All disk writes go to pytest's ``tmp_path`` — real data/lines/ is never touched.
Python 3.9 compatible.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

# ---------------------------------------------------------------------------
# Path wiring
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = ROOT / "scripts" / "platformkit" / "capture"
sys.path.insert(0, str(CAPTURE_DIR))

import ledger_schema as schema  # noqa: E402
import ledger_writer as writer  # noqa: E402
import capture_sgp as cap  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_EVENT_ID = "test_sgp_event_xyz"
_COMMENCE = "2030-01-15T02:00:00Z"
# Pin "now" well before commence so kind=open applies on first run.
_NOW_UTC = datetime.datetime(2030, 1, 14, 20, 0, 0, tzinfo=datetime.timezone.utc)


def _make_event(
    event_id: str = _EVENT_ID,
    commence: str = _COMMENCE,
) -> Dict[str, Any]:
    """Return a minimal synthetic event dict matching the Odds API shape."""
    return {
        "id": event_id,
        "home_team": "New York Knicks",
        "away_team": "San Antonio Spurs",
        "commence_time": commence,
    }


def _make_sgp_bookmakers(
    book: str = "fanduel",
    player_a: str = "Jalen Brunson",
    player_b: str = "Karl-Anthony Towns",
    price_a_over: int = -120,
    price_a_under: int = 100,
    point_a: float = 27.5,
    price_b_over: int = -115,
    price_b_under: int = -105,
    point_b: float = 9.5,
) -> List[Dict[str, Any]]:
    """Return a synthetic bookmakers list for a PTS+REB SGP combo."""
    return [
        {
            "key": book,
            "markets": [
                {
                    "key": "player_points",
                    "outcomes": [
                        {"name": "Over", "description": player_a,
                         "price": price_a_over, "point": point_a},
                        {"name": "Under", "description": player_a,
                         "price": price_a_under, "point": point_a},
                    ],
                },
                {
                    "key": "player_rebounds",
                    "outcomes": [
                        {"name": "Over", "description": player_b,
                         "price": price_b_over, "point": point_b},
                        {"name": "Under", "description": player_b,
                         "price": price_b_under, "point": point_b},
                    ],
                },
            ],
        }
    ]


class _StubClient:
    """Deterministic stub for SgpOddsAPIClient — zero network calls.

    Returns SGP pricing only for the first combo in ``_SGP_PROBE_COMBOS``
    to mirror real API behaviour (most combos return nothing).
    """

    def __init__(
        self,
        events: Optional[List[Dict[str, Any]]] = None,
        sgp_bms: Optional[List[Dict[str, Any]]] = None,
        supported_legs: Optional[Tuple[str, ...]] = None,
    ) -> None:
        self._events = events if events is not None else [_make_event()]
        self._sgp_bms = sgp_bms if sgp_bms is not None else _make_sgp_bookmakers()
        # Only respond to this legs combo — everything else returns [].
        self._supported = set(supported_legs or cap._SGP_PROBE_COMBOS[0])

    def fetch_events(self) -> List[Dict[str, Any]]:
        return self._events

    def fetch_sgp_bookmakers(
        self, event_id: str, legs: Tuple[str, ...]
    ) -> List[Dict[str, Any]]:
        if set(legs) == self._supported:
            return self._sgp_bms
        return []


# ---------------------------------------------------------------------------
# 1. Import test — module must be importable without network or API key.
# ---------------------------------------------------------------------------

def test_import_clean() -> None:
    """Module must import cleanly with no network, no API key."""
    assert cap is not None
    assert hasattr(cap, "run_capture")
    assert hasattr(cap, "classify_kind")
    assert hasattr(cap, "make_sgp_market_tag")


# ---------------------------------------------------------------------------
# 2. Market tag format is correct.
# ---------------------------------------------------------------------------

def test_make_sgp_market_tag_format() -> None:
    """make_sgp_market_tag must produce the expected ledger market string."""
    tag = cap.make_sgp_market_tag(("player_points", "player_rebounds"))
    assert tag == "sgp:player_points+player_rebounds"

    tag3 = cap.make_sgp_market_tag(("player_points", "player_rebounds", "player_assists"))
    assert tag3 == "sgp:player_points+player_rebounds+player_assists"


def test_make_sgp_market_tag_single_leg() -> None:
    """Single-leg SGP tag should also be valid."""
    tag = cap.make_sgp_market_tag(("player_points",))
    assert tag == "sgp:player_points"


def test_make_sgp_market_tag_empty_raises() -> None:
    """Empty legs tuple must raise ValueError."""
    with pytest.raises(ValueError):
        cap.make_sgp_market_tag(())


# ---------------------------------------------------------------------------
# 3. Dry-run: reports rows but writes NOTHING to disk.
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """--dry-run must not touch any file in ledger_root."""
    client = _StubClient()
    stats = cap.run_capture(dry_run=True, ledger_root=tmp_path, client=client,
                            now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    files = list(sport_dir.glob("*.jsonl")) if sport_dir.exists() else []
    assert files == [], f"dry-run wrote files: {files}"

    # Dry-run reports rows it would write (> 0 because stub returns SGP data).
    assert stats["sgp_rows_written"] > 0


# ---------------------------------------------------------------------------
# 4. Live capture writes rows and they pass schema validation.
# ---------------------------------------------------------------------------

def test_live_capture_writes_rows(tmp_path: Path) -> None:
    """Live run must write at least one row to the ledger."""
    client = _StubClient()
    stats = cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                            now_utc=_NOW_UTC)

    assert stats["sgp_rows_written"] > 0

    sport_dir = tmp_path / "nba"
    jsonl_files = list(sport_dir.glob("*.jsonl"))
    assert jsonl_files, "Expected at least one .jsonl file"

    row_count = 0
    for jf in jsonl_files:
        for row in writer.read_all("nba", jf.stem, root=tmp_path):
            schema.validate(row)
            row_count += 1
    assert row_count > 0


# ---------------------------------------------------------------------------
# 5. Idempotency — a second identical run produces ZERO new rows.
# ---------------------------------------------------------------------------

def test_idempotency_zero_duplicates(tmp_path: Path) -> None:
    """Running capture twice with the same data must produce zero duplicate rows."""
    client = _StubClient()

    stats1 = cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                             now_utc=_NOW_UTC)
    rows_run1 = stats1["sgp_rows_written"]
    assert rows_run1 > 0, "First run must write rows"

    stats2 = cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                             now_utc=_NOW_UTC)
    assert stats2["sgp_rows_written"] == 0, (
        f"Second identical run must write 0 new rows, got {stats2['sgp_rows_written']}"
    )
    assert stats2["rows_skipped_duplicate"] == rows_run1, (
        "All rows from run1 must appear as skipped duplicates in run2"
    )


# ---------------------------------------------------------------------------
# 6. No duplicate record keys after two runs.
# ---------------------------------------------------------------------------

def test_ledger_has_no_duplicate_keys_after_two_runs(tmp_path: Path) -> None:
    """The ledger must never contain duplicate (sport,event,market,book,side,kind) keys."""
    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    all_rows: List[dict] = []
    for jf in sport_dir.glob("*.jsonl"):
        all_rows.extend(writer.read_all("nba", jf.stem, root=tmp_path))

    keys = [schema.record_key(r) for r in all_rows]
    assert len(keys) == len(set(keys)), (
        f"Duplicate record keys found: "
        f"{[k for k in keys if keys.count(k) > 1]}"
    )


# ---------------------------------------------------------------------------
# 7. Zero rows — valid outcome when the API exposes no SGP pricing.
# ---------------------------------------------------------------------------

def test_zero_rows_is_valid_outcome(tmp_path: Path) -> None:
    """When all SGP probes return empty bookmakers lists, zero_rows=True is recorded."""

    class _NoSgpClient:
        def fetch_events(self) -> List[Dict[str, Any]]:
            return [_make_event()]

        def fetch_sgp_bookmakers(
            self, event_id: str, legs: Tuple[str, ...]
        ) -> List[Dict[str, Any]]:
            return []  # API exposes no SGP pricing at all.

    stats = cap.run_capture(dry_run=False, ledger_root=tmp_path,
                            client=_NoSgpClient(), now_utc=_NOW_UTC)

    assert stats["sgp_rows_written"] == 0
    assert stats["zero_rows"] is True


# ---------------------------------------------------------------------------
# 8. Market tag is correct in written rows.
# ---------------------------------------------------------------------------

def test_sgp_market_tag_prefix_in_written_rows(tmp_path: Path) -> None:
    """All written rows must have a market field starting with 'sgp:'."""
    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                    now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    for jf in sport_dir.glob("*.jsonl"):
        for row in writer.read_all("nba", jf.stem, root=tmp_path):
            assert row["market"].startswith("sgp:"), (
                f"Market tag missing 'sgp:' prefix: {row['market']!r}"
            )


# ---------------------------------------------------------------------------
# 9. Schema compliance — all required fields present on every written row.
# ---------------------------------------------------------------------------

def test_all_rows_pass_schema_validation(tmp_path: Path) -> None:
    """Every written row must pass the ledger schema validator."""
    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                    now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    row_count = 0
    for jf in sport_dir.glob("*.jsonl"):
        for row in writer.read_all("nba", jf.stem, root=tmp_path):
            schema.validate(row)
            assert row["sport"] == "nba"
            assert row["kind"] in {"open", "move", "close"}
            assert row["source"] == cap._SOURCE
            row_count += 1
    assert row_count > 0


# ---------------------------------------------------------------------------
# 10. kind classification — first observation is ``open``.
# ---------------------------------------------------------------------------

def test_classify_kind_first_seen_is_open() -> None:
    """First-seen (not in seen set) → kind='open'."""
    seen: set = set()
    kind = cap.classify_kind(
        _EVENT_ID, "sgp:player_points+player_rebounds",
        "fanduel", "over:Jalen Brunson:27.5", seen, _COMMENCE,
    )
    assert kind == "open"


# ---------------------------------------------------------------------------
# 11. kind classification — T-5 window → ``close``.
# ---------------------------------------------------------------------------

def test_classify_kind_close_window() -> None:
    """3 minutes before tip → kind='close'."""
    market = "sgp:player_points+player_rebounds"
    seen = {("nba", _EVENT_ID, market, "fanduel", "over:Jalen Brunson:27.5", "open")}
    now_utc = datetime.datetime(2030, 1, 15, 1, 57, 0, tzinfo=datetime.timezone.utc)
    kind = cap.classify_kind(
        _EVENT_ID, market, "fanduel", "over:Jalen Brunson:27.5",
        seen, _COMMENCE, now_utc=now_utc,
    )
    assert kind == "close"


# ---------------------------------------------------------------------------
# 12. kind classification — T-60 window → ``move``.
# ---------------------------------------------------------------------------

def test_classify_kind_move_window() -> None:
    """30 minutes before tip → kind='move'."""
    market = "sgp:player_points+player_rebounds"
    seen = {("nba", _EVENT_ID, market, "fanduel", "over:Jalen Brunson:27.5", "open")}
    now_utc = datetime.datetime(2030, 1, 15, 1, 30, 0, tzinfo=datetime.timezone.utc)
    kind = cap.classify_kind(
        _EVENT_ID, market, "fanduel", "over:Jalen Brunson:27.5",
        seen, _COMMENCE, now_utc=now_utc,
    )
    assert kind == "move"


# ---------------------------------------------------------------------------
# 13. API error during SGP probe — counted, does not crash.
# ---------------------------------------------------------------------------

def test_sgp_api_error_is_counted(tmp_path: Path) -> None:
    """A RuntimeError from fetch_sgp_bookmakers must be counted, not raised."""

    class _FailingClient:
        def fetch_events(self) -> List[Dict[str, Any]]:
            return [_make_event()]

        def fetch_sgp_bookmakers(
            self, event_id: str, legs: Tuple[str, ...]
        ) -> List[Dict[str, Any]]:
            raise RuntimeError("Network down")

    stats = cap.run_capture(dry_run=False, ledger_root=tmp_path,
                            client=_FailingClient(), now_utc=_NOW_UTC)
    expected_errors = len(cap._SGP_PROBE_COMBOS)
    assert stats["sgp_api_errors"] == expected_errors, (
        f"Expected {expected_errors} api_errors, got {stats['sgp_api_errors']}"
    )


# ---------------------------------------------------------------------------
# 14. Empty events list — zero rows, no errors.
# ---------------------------------------------------------------------------

def test_empty_events_no_rows(tmp_path: Path) -> None:
    """If the events endpoint returns nothing, stats must all be zero."""
    client = _StubClient(events=[])
    stats = cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                            now_utc=_NOW_UTC)
    assert stats["sgp_rows_written"] == 0
    assert stats["events_found"] == 0


# ---------------------------------------------------------------------------
# 15. Dry-run default stub produces rows without network.
# ---------------------------------------------------------------------------

def test_dry_run_stub_client_reports_rows(tmp_path: Path) -> None:
    """_DryRunSgpStubClient must produce reportable rows without network."""
    stub = cap._DryRunSgpStubClient()
    stats = cap.run_capture(dry_run=True, ledger_root=tmp_path, client=stub,
                            now_utc=_NOW_UTC)
    assert stats["sgp_rows_written"] > 0
    # Dry-run writes nothing.
    sport_dir = tmp_path / "nba"
    assert not sport_dir.exists() or not list(sport_dir.glob("*.jsonl"))


# ---------------------------------------------------------------------------
# 16. Schema round-trip — write then read and re-validate.
# ---------------------------------------------------------------------------

def test_schema_round_trip(tmp_path: Path) -> None:
    """Rows written to disk must round-trip through JSON and re-validate."""
    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                    now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    re_read_count = 0
    for jf in sport_dir.glob("*.jsonl"):
        for row in writer.read_all("nba", jf.stem, root=tmp_path):
            # Re-validate from the raw parsed dict.
            schema.validate(row)
            # Check every required field has a non-None value.
            for field in schema.REQUIRED_FIELDS:
                assert row.get(field) is not None, (
                    f"Round-trip: field {field!r} is None after read_all"
                )
            re_read_count += 1
    assert re_read_count > 0, "Round-trip found no rows"


# ---------------------------------------------------------------------------
# 17. Source field is always ``odds_api_sgp``.
# ---------------------------------------------------------------------------

def test_source_field_is_sgp(tmp_path: Path) -> None:
    """All written rows must carry source='odds_api_sgp'."""
    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                    now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    for jf in sport_dir.glob("*.jsonl"):
        for row in writer.read_all("nba", jf.stem, root=tmp_path):
            assert row["source"] == "odds_api_sgp", (
                f"Unexpected source: {row['source']!r}"
            )


# ---------------------------------------------------------------------------
# 18. No public-tree artifact — ledger stays under tmp_path.
# ---------------------------------------------------------------------------

def test_no_public_tree_artifact(tmp_path: Path) -> None:
    """Capture must never write to the real data/lines/ tree during tests."""
    real_forward = ROOT / "data" / "lines" / "forward" / "nba"
    real_before = list(real_forward.glob("*.jsonl")) if real_forward.exists() else []

    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client,
                    now_utc=_NOW_UTC)

    real_after = list(real_forward.glob("*.jsonl")) if real_forward.exists() else []
    assert real_before == real_after, "capture_sgp must not write to the real ledger"
