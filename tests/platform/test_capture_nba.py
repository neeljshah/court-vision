"""test_capture_nba.py — Offline unit tests for scripts/platformkit/capture/capture_nba.py.

All tests run without network access.  A stub client replaces OddsAPIClient.
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
import capture_nba as cap  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_GAME_ID = "test_event_abc123"
# Commence time is a fixed far-future UTC tip-off for all tests.
# Tests that need time-window classification inject now_utc relative to this.
_COMMENCE = "2030-01-15T02:00:00Z"
# Pinned "now" used for deterministic kind classification in all live-run tests.
# Must be well before _COMMENCE so the game hasn't started yet.
_NOW_UTC = datetime.datetime(2030, 1, 14, 20, 0, 0, tzinfo=datetime.timezone.utc)


def _make_game(
    game_id: str = _GAME_ID,
    commence: str = _COMMENCE,
) -> Dict[str, Any]:
    """Return a minimal raw game dict matching The Odds API shape."""
    return {
        "id": game_id,
        "home_team": "New York Knicks",
        "away_team": "San Antonio Spurs",
        "commence_time": commence,
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "New York Knicks", "price": -110, "point": -2.5},
                            {"name": "San Antonio Spurs", "price": -110, "point": 2.5},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": -110, "point": 215.5},
                            {"name": "Under", "price": -110, "point": 215.5},
                        ],
                    },
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "New York Knicks", "price": -130},
                            {"name": "San Antonio Spurs", "price": 110},
                        ],
                    },
                ],
            }
        ],
    }


def _make_prop_bookmakers(
    player: str = "Jalen Brunson",
    market: str = "player_points",
    book: str = "draftkings",
    over_price: int = -115,
    under_price: int = -105,
    point: float = 27.5,
) -> List[Dict[str, Any]]:
    return [
        {
            "key": book,
            "markets": [
                {
                    "key": market,
                    "outcomes": [
                        {"name": "Over", "description": player, "price": over_price, "point": point},
                        {"name": "Under", "description": player, "price": under_price, "point": point},
                    ],
                }
            ],
        }
    ]


class _StubClient:
    """Deterministic stub for OddsAPIClient — zero network calls."""

    def __init__(
        self,
        games: Optional[List[Dict[str, Any]]] = None,
        props: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._games = games if games is not None else [_make_game()]
        self._props = props if props is not None else _make_prop_bookmakers()

    def fetch_games(self) -> List[Dict[str, Any]]:
        return self._games

    def fetch_props(self, event_id: str, market: str) -> List[Dict[str, Any]]:
        return self._props


# ---------------------------------------------------------------------------
# 1. Import test — capture_nba.py must import cleanly with no network.
# ---------------------------------------------------------------------------

def test_import_clean() -> None:
    """Module must be importable without network or API key."""
    assert cap is not None
    assert hasattr(cap, "run_capture")
    assert hasattr(cap, "classify_kind")


# ---------------------------------------------------------------------------
# 2. Dry-run test — runs offline and reports counts, writes NOTHING.
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """--dry-run must not touch any file in ledger_root."""
    client = _StubClient()
    stats = cap.run_capture(dry_run=True, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)

    # Ledger dir must be empty (or non-existent).
    sport_dir = tmp_path / "nba"
    files = list(sport_dir.glob("*.jsonl")) if sport_dir.exists() else []
    assert files == [], f"dry-run wrote files: {files}"

    # But it still reports rows_written > 0 (what it WOULD write).
    assert stats["rows_written"] > 0, "dry-run should report rows it would write"
    assert stats["games_found"] > 0


# ---------------------------------------------------------------------------
# 3. Live capture writes rows to the ledger.
# ---------------------------------------------------------------------------

def test_live_capture_writes_rows(tmp_path: Path) -> None:
    """Live run must write at least one row to the ledger."""
    client = _StubClient()
    stats = cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)

    assert stats["rows_written"] > 0

    # At least one JSONL file must exist under nba/.
    sport_dir = tmp_path / "nba"
    jsonl_files = list(sport_dir.glob("*.jsonl"))
    assert jsonl_files, "Expected at least one .jsonl file"

    # Every row must pass schema validation.
    for jf in jsonl_files:
        for row in writer.read_all("nba", jf.stem, root=tmp_path):
            schema.validate(row)


# ---------------------------------------------------------------------------
# 4. Idempotency — a second identical run produces ZERO new rows.
# ---------------------------------------------------------------------------

def test_idempotency_zero_duplicates(tmp_path: Path) -> None:
    """Running capture twice on the same data must produce zero duplicate rows."""
    client = _StubClient()

    stats1 = cap.run_capture(
        dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC
    )
    rows_run1 = stats1["rows_written"]
    assert rows_run1 > 0, "First run must write rows"

    stats2 = cap.run_capture(
        dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC
    )
    assert stats2["rows_written"] == 0, (
        f"Second identical run must write 0 rows, got {stats2['rows_written']}"
    )
    assert stats2["rows_skipped_duplicate"] == rows_run1, (
        "All rows from run1 must appear as skipped duplicates in run2"
    )


# ---------------------------------------------------------------------------
# 5. Record keys are unique after two runs.
# ---------------------------------------------------------------------------

def test_ledger_has_no_duplicate_keys_after_two_runs(tmp_path: Path) -> None:
    """The ledger file must have no duplicate (sport,event,market,book,side,kind) keys."""
    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    all_rows = []
    for jf in sport_dir.glob("*.jsonl"):
        all_rows.extend(writer.read_all("nba", jf.stem, root=tmp_path))

    keys = [schema.record_key(r) for r in all_rows]
    assert len(keys) == len(set(keys)), (
        f"Duplicate record keys found after 2 runs: "
        f"{[k for k in keys if keys.count(k) > 1]}"
    )


# ---------------------------------------------------------------------------
# 6. kind classification — first observation is ``open``.
# ---------------------------------------------------------------------------

def test_classify_kind_first_seen_is_open() -> None:
    seen: set = set()
    kind = cap.classify_kind(
        _GAME_ID, "spread", "draftkings", "new york knicks:-2.5",
        seen, _COMMENCE,
    )
    assert kind == "open"


# ---------------------------------------------------------------------------
# 7. kind classification — within T-5 window is ``close``.
# ---------------------------------------------------------------------------

def test_classify_kind_close_window() -> None:
    # Pre-populate seen_open so we're past the opener.
    seen = {("nba", _GAME_ID, "spread", "draftkings", "new york knicks:-2.5", "open")}
    # 3 minutes before tip (_COMMENCE = 2030-01-15T02:00:00Z).
    now_utc = datetime.datetime(2030, 1, 15, 1, 57, 0, tzinfo=datetime.timezone.utc)

    kind = cap.classify_kind(
        _GAME_ID, "spread", "draftkings", "new york knicks:-2.5",
        seen, _COMMENCE, now_utc=now_utc,
    )
    assert kind == "close"


# ---------------------------------------------------------------------------
# 8. kind classification — within T-60 window is ``move``.
# ---------------------------------------------------------------------------

def test_classify_kind_move_window() -> None:
    seen = {("nba", _GAME_ID, "spread", "draftkings", "new york knicks:-2.5", "open")}
    # 30 minutes before tip (_COMMENCE = 2030-01-15T02:00:00Z).
    now_utc = datetime.datetime(2030, 1, 15, 1, 30, 0, tzinfo=datetime.timezone.utc)

    kind = cap.classify_kind(
        _GAME_ID, "spread", "draftkings", "new york knicks:-2.5",
        seen, _COMMENCE, now_utc=now_utc,
    )
    assert kind == "move"


# ---------------------------------------------------------------------------
# 9. Prop markets — all 7 prop market names are captured.
# ---------------------------------------------------------------------------

def test_all_7_prop_markets_captured(tmp_path: Path) -> None:
    """Verify every prop market in cap._PROP_MARKETS has at least one row written."""
    captured_markets: set = set()

    class _MultiPropClient:
        def fetch_games(self) -> List[Dict[str, Any]]:
            return [_make_game()]

        def fetch_props(self, event_id: str, market: str) -> List[Dict[str, Any]]:
            return _make_prop_bookmakers(market=market)

    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=_MultiPropClient(), now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    for jf in sport_dir.glob("*.jsonl"):
        for row in writer.read_all("nba", jf.stem, root=tmp_path):
            captured_markets.add(row["market"])

    for mkt in cap._PROP_MARKETS:
        assert mkt in captured_markets, f"Missing prop market: {mkt}"


# ---------------------------------------------------------------------------
# 10. Schema compliance — every row written has all required fields.
# ---------------------------------------------------------------------------

def test_all_rows_pass_schema_validation(tmp_path: Path) -> None:
    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)

    sport_dir = tmp_path / "nba"
    row_count = 0
    for jf in sport_dir.glob("*.jsonl"):
        for row in writer.read_all("nba", jf.stem, root=tmp_path):
            schema.validate(row)  # raises on any violation
            assert row["sport"] == "nba"
            assert row["kind"] in {"open", "move", "close"}
            assert row["source"] == cap._SOURCE
            row_count += 1
    assert row_count > 0


# ---------------------------------------------------------------------------
# 11. Empty games list — zero rows, no errors.
# ---------------------------------------------------------------------------

def test_empty_games_no_rows(tmp_path: Path) -> None:
    client = _StubClient(games=[], props=[])
    stats = cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)
    assert stats["rows_written"] == 0
    assert stats["games_found"] == 0


# ---------------------------------------------------------------------------
# 12. Prop API error — captured in stats, does not crash.
# ---------------------------------------------------------------------------

def test_prop_api_error_is_counted(tmp_path: Path) -> None:
    class _FailingPropClient:
        def fetch_games(self) -> List[Dict[str, Any]]:
            return [_make_game()]

        def fetch_props(self, event_id: str, market: str) -> List[Dict[str, Any]]:
            raise RuntimeError("Network down")

    stats = cap.run_capture(
        dry_run=False, ledger_root=tmp_path, client=_FailingPropClient(), now_utc=_NOW_UTC
    )
    assert stats["prop_api_errors"] == len(cap._PROP_MARKETS)
    # Mainline rows still written.
    assert stats["rows_written"] > 0


# ---------------------------------------------------------------------------
# 13. Dry-run stub client — offline default stub produces rows.
# ---------------------------------------------------------------------------

def test_dry_run_stub_client_reports_rows(tmp_path: Path) -> None:
    """_DryRunStubClient must produce reportable rows without network."""
    stub = cap._DryRunStubClient()
    stats = cap.run_capture(dry_run=True, ledger_root=tmp_path, client=stub, now_utc=_NOW_UTC)
    assert stats["rows_written"] > 0
    # But nothing on disk.
    sport_dir = tmp_path / "nba"
    assert not sport_dir.exists() or not list(sport_dir.glob("*.jsonl"))


# ---------------------------------------------------------------------------
# 14. Mainline row builder yields correct ledger market names.
# ---------------------------------------------------------------------------

def test_mainline_market_names_mapped(tmp_path: Path) -> None:
    game = _make_game()
    ts = "2026-06-11T20:00:00Z"
    rows = list(cap._build_mainline_rows(game, ts, set()))
    markets_found = {r["market"] for r in rows}
    assert "spread" in markets_found
    assert "total" in markets_found
    assert "moneyline" in markets_found


# ---------------------------------------------------------------------------
# 15. No public-tree artifact — ledger stays under tmp_path.
# ---------------------------------------------------------------------------

def test_no_public_tree_artifact(tmp_path: Path) -> None:
    """Confirm rows land under tmp_path, not under the real data/ tree."""
    real_forward = ROOT / "data" / "lines" / "forward" / "nba"
    # Record real file count before.
    real_before = list(real_forward.glob("*.jsonl")) if real_forward.exists() else []

    client = _StubClient()
    cap.run_capture(dry_run=False, ledger_root=tmp_path, client=client, now_utc=_NOW_UTC)

    real_after = list(real_forward.glob("*.jsonl")) if real_forward.exists() else []
    assert real_before == real_after, "Capture must not write to the real ledger"
