"""Per-file tests for scripts.platformkit.clv_ledger_sanity.

Acceptance criteria (be-ledger-sanity-check):
  1. A ledger with a 'test_' row returns status='dirty', synthetic.count >= 1.
  2. A ledger with a game_id='gg' (below MIN_GAME_ID_LEN=3) row returns
       status='dirty', malformed.count >= 1.
  3. A ledger with a duplicate (game|market|side|venue|date|status) key pair
       returns status='dirty', duplicates.count >= 1.
  4. A clean ledger (no synthetic, no malformed, no dups) returns status='clean'.
  5. An empty or missing ledger returns status='INSUFFICIENT_DATA'.
  6. Report carries NO banned $ / pnl / profit / bankroll / roi key anywhere.
  7. settled rows without clv_pct -> honest_clv.settled_without_clv > 0;
       label contains 'INSUFFICIENT_DATA'; does NOT flip status to 'clean'.
  8. honest_note present and contains 'calibration'.
  9. Combined: test_ row + game_id='gg' row + dup pair -> status='dirty' with
       all three nonzero counts.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_sanity.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# ---------------------------------------------------------------------------
# Hermetic import: ensure repo root on sys.path
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.platformkit.clv_ledger_sanity import scan_ledger, scan_assert, purge_ledger

# ---------------------------------------------------------------------------
# Banned $ keys checked in every report
# ---------------------------------------------------------------------------
_BANNED_KEYS = frozenset({
    "pnl", "profit", "bankroll", "roi", "dollars", "total_pnl", "total_stake",
    "paper_roi", "stake", "net_profit", "return",
})


def _assert_no_banned(obj: Any, label: str = "report") -> None:
    """Recursively assert no banned $ key is present in any dict."""
    if isinstance(obj, dict):
        for k in obj:
            assert k.lower() not in _BANNED_KEYS, (
                "Banned $ key %r found in %s" % (k, label)
            )
            _assert_no_banned(obj[k], label + "." + k)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_banned(v, "%s[%d]" % (label, i))


# ---------------------------------------------------------------------------
# Helpers: row builders + ledger writer
# ---------------------------------------------------------------------------

def _clean_row(
    matchup: str = "NYK @ SAS",
    sport: str = "nba",
    side: str = "home",
    market: str = "moneyline",
    book: str = "FanDuel",
    game_date: str = "2026-06-20",
    status: str = "open",
    game_id: str = "401859967",
) -> Dict[str, Any]:
    """Minimal well-formed ledger row with no banned keys."""
    return {
        "sport": sport,
        "matchup": matchup,
        "side": side,
        "market": market,
        "taken_book": book,
        "taken_decimal": 2.05,
        "stake_units": 1.0,
        "status": status,
        "game_date": game_date,
        "game_id": game_id,
        "executed": False,
        "bet_id": "|".join([sport, matchup, market, side, book, game_date]),
    }


def _settled_row_with_clv(**kwargs) -> Dict[str, Any]:
    row = _clean_row(status="settled", **kwargs)
    row["clv_pct"] = 1.5
    row["beat_close"] = True
    return row


def _settled_row_without_clv(**kwargs) -> Dict[str, Any]:
    row = _clean_row(status="settled", **kwargs)
    # clv_pct intentionally absent (no close captured yet)
    return row


def _write_ledger(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# Test 1: synthetic row (sport starts with 'test_') -> dirty
# ---------------------------------------------------------------------------

def test_synthetic_row_makes_dirty(tmp_path: Path) -> None:
    """A row whose sport starts with 'test_' must yield status='dirty'."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _clean_row(sport="test_nba", matchup="A @ B"),
        _clean_row(matchup="C @ D"),   # valid row alongside
    ])
    report = scan_ledger(ledger)
    assert report["status"] == "dirty", "expected dirty, got %r" % report["status"]
    assert report["synthetic"]["count"] >= 1, (
        "synthetic count must be >= 1; got %d" % report["synthetic"]["count"]
    )
    _assert_no_banned(report)


def test_synthetic_row_bet_id_prefix(tmp_path: Path) -> None:
    """A row whose bet_id starts with 'test_' is also synthetic -> dirty."""
    ledger = tmp_path / "led.jsonl"
    row = _clean_row(matchup="E @ F")
    row["bet_id"] = "test_abc|extra"
    _write_ledger(ledger, [row])
    report = scan_ledger(ledger)
    assert report["status"] == "dirty"
    assert report["synthetic"]["count"] >= 1
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 2: malformed row (game_id too short) -> dirty
# ---------------------------------------------------------------------------

def test_malformed_game_id_makes_dirty(tmp_path: Path) -> None:
    """A row with game_id='gg' (len<3) must yield status='dirty'."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _clean_row(game_id="gg"),    # len=2, below MIN_GAME_ID_LEN=3
        _clean_row(matchup="G @ H"), # valid row alongside
    ])
    report = scan_ledger(ledger)
    assert report["status"] == "dirty", "expected dirty, got %r" % report["status"]
    assert report["malformed"]["count"] >= 1, (
        "malformed count must be >= 1; got %d" % report["malformed"]["count"]
    )
    _assert_no_banned(report)


def test_malformed_missing_required_key(tmp_path: Path) -> None:
    """A row missing the 'side' key is malformed -> dirty."""
    ledger = tmp_path / "led.jsonl"
    row = _clean_row(matchup="I @ J")
    del row["side"]
    _write_ledger(ledger, [row])
    report = scan_ledger(ledger)
    assert report["status"] == "dirty"
    assert report["malformed"]["count"] >= 1
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 3: duplicate (game|market|side|venue|date|status) key pair -> dirty
# ---------------------------------------------------------------------------

def test_dup_key_pair_makes_dirty(tmp_path: Path) -> None:
    """Two rows with the same natural key yield status='dirty'."""
    ledger = tmp_path / "led.jsonl"
    base = _clean_row(matchup="NYK @ SAS", game_id="401859967")
    dup = dict(base)
    dup["taken_decimal"] = 2.10  # different price, same compound key
    _write_ledger(ledger, [base, dup])
    report = scan_ledger(ledger)
    assert report["status"] == "dirty", "expected dirty, got %r" % report["status"]
    assert report["duplicates"]["count"] >= 1, (
        "duplicates count must be >= 1; got %d" % report["duplicates"]["count"]
    )
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 4: clean ledger -> status='clean'
# ---------------------------------------------------------------------------

def test_clean_ledger_returns_clean(tmp_path: Path) -> None:
    """A ledger with no synthetic, malformed, or dup rows returns status='clean'."""
    ledger = tmp_path / "led.jsonl"
    rows = [
        _clean_row(matchup="NYK @ SAS", game_id="401859967"),
        _clean_row(matchup="BOS @ LAL", game_id="401859968", side="away"),
    ]
    _write_ledger(ledger, rows)
    report = scan_ledger(ledger)
    assert report["status"] == "clean", "expected clean, got %r; report=%r" % (
        report["status"], report
    )
    assert report["synthetic"]["count"] == 0
    assert report["malformed"]["count"] == 0
    assert report["duplicates"]["count"] == 0
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 5: empty / missing ledger -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

def test_missing_file_is_insufficient_data(tmp_path: Path) -> None:
    """Non-existent ledger file returns status='INSUFFICIENT_DATA'."""
    ledger = tmp_path / "nonexistent.jsonl"
    report = scan_ledger(ledger)
    assert report["status"] == "INSUFFICIENT_DATA", (
        "expected INSUFFICIENT_DATA, got %r" % report["status"]
    )
    assert report["total_rows"] == 0
    _assert_no_banned(report)


def test_empty_file_is_insufficient_data(tmp_path: Path) -> None:
    """An empty ledger file (0 bytes) returns status='INSUFFICIENT_DATA'."""
    ledger = tmp_path / "empty.jsonl"
    ledger.write_text("", encoding="utf-8")
    report = scan_ledger(ledger)
    assert report["status"] == "INSUFFICIENT_DATA"
    _assert_no_banned(report)


def test_blank_lines_only_is_insufficient_data(tmp_path: Path) -> None:
    """A file with only blank lines (no parseable rows) is INSUFFICIENT_DATA."""
    ledger = tmp_path / "blank.jsonl"
    ledger.write_text("\n\n\n", encoding="utf-8")
    report = scan_ledger(ledger)
    assert report["status"] == "INSUFFICIENT_DATA"
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 6: no $ / pnl / profit key anywhere in the report
# ---------------------------------------------------------------------------

def test_no_banned_keys_in_report(tmp_path: Path) -> None:
    """scan_ledger output must not contain any banned $ / pnl / profit key."""
    ledger = tmp_path / "led.jsonl"
    # Plant a pnl key in a row to ensure the scanner does NOT mirror it out.
    row = _clean_row(matchup="MIA @ CHI", game_id="401859969")
    row["pnl"] = 50.0   # banned -- must not appear in report output
    row["roi"] = 0.05   # banned -- must not appear in report output
    _write_ledger(ledger, [row])
    report = scan_ledger(ledger)
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 7: settled rows without clv_pct -> honest INSUFFICIENT_DATA labelling
# ---------------------------------------------------------------------------

def test_settled_without_clv_labelled_insufficient(tmp_path: Path) -> None:
    """Settled rows missing clv_pct are counted as INSUFFICIENT_DATA, not green."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _settled_row_with_clv(matchup="PHX @ DEN", game_id="401859970"),
        _settled_row_without_clv(matchup="MIL @ CLE", game_id="401859971"),
    ])
    report = scan_ledger(ledger)
    hclv = report["honest_clv"]
    assert hclv["settled_with_clv"] == 1
    assert hclv["settled_without_clv"] == 1
    assert "INSUFFICIENT_DATA" in hclv["no_close_label"], (
        "label must contain 'INSUFFICIENT_DATA'; got %r" % hclv["no_close_label"]
    )
    # settled-without-clv alone must NOT flip status to dirty or clean=False.
    # A ledger that is otherwise clean should still be 'clean'.
    assert report["status"] == "clean", (
        "settled-without-clv alone must not make status dirty; got %r" % report["status"]
    )
    _assert_no_banned(report)


def test_all_settled_have_clv(tmp_path: Path) -> None:
    """When all settled rows have clv_pct, settled_without_clv is 0."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _settled_row_with_clv(matchup="TOR @ OKC", game_id="401859972"),
    ])
    report = scan_ledger(ledger)
    assert report["honest_clv"]["settled_without_clv"] == 0
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 8: honest_note present and contains 'calibration'
# ---------------------------------------------------------------------------

def test_honest_note_present_and_mentions_calibration(tmp_path: Path) -> None:
    """Result must carry a non-empty honest_note that mentions 'calibration'."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [_clean_row(matchup="IND @ ATL", game_id="401859973")])
    report = scan_ledger(ledger)
    assert "honest_note" in report, "honest_note key must be present"
    note = report["honest_note"]
    assert note, "honest_note must not be empty"
    assert "calibration" in note.lower(), (
        "honest_note must mention 'calibration'; got %r" % note
    )
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 9: combined dirty scenario (acceptance gate)
# ---------------------------------------------------------------------------

def test_combined_dirty_all_counts_nonzero(tmp_path: Path) -> None:
    """Combined: test_ row + game_id='gg' row + dup pair -> dirty, all counts >= 1."""
    ledger = tmp_path / "led.jsonl"

    # Row 1: synthetic (sport=test_nba)
    synthetic = _clean_row(sport="test_nba", matchup="X @ Y")

    # Row 2: malformed (game_id too short)
    malformed = _clean_row(matchup="A @ B", game_id="gg")

    # Rows 3 & 4: duplicate natural key pair
    base = _clean_row(matchup="NYK @ SAS", game_id="401859967")
    dup = dict(base)
    dup["taken_decimal"] = 2.20  # different price, same compound key -> dup

    _write_ledger(ledger, [synthetic, malformed, base, dup])
    report = scan_ledger(ledger)

    assert report["status"] == "dirty", (
        "combined dirty ledger must return status='dirty'; got %r" % report["status"]
    )
    assert report["synthetic"]["count"] >= 1, (
        "synthetic count must be >= 1; got %d" % report["synthetic"]["count"]
    )
    assert report["malformed"]["count"] >= 1, (
        "malformed count must be >= 1; got %d" % report["malformed"]["count"]
    )
    assert report["duplicates"]["count"] >= 1, (
        "duplicates count must be >= 1; got %d" % report["duplicates"]["count"]
    )
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 10: status is NEVER 'clean' when synthetic rows are present
# ---------------------------------------------------------------------------

def test_status_never_clean_when_synthetic(tmp_path: Path) -> None:
    """Even a single synthetic row must prevent status='clean'."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [_clean_row(sport="test_mlb", matchup="K @ L")])
    report = scan_ledger(ledger)
    assert report["status"] != "clean", (
        "status must not be 'clean' when a synthetic row is present"
    )
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Test 11: total_rows count is correct
# ---------------------------------------------------------------------------

def test_total_rows_count(tmp_path: Path) -> None:
    """total_rows must equal the number of parseable rows in the ledger."""
    ledger = tmp_path / "led.jsonl"
    rows = [
        _clean_row(matchup="M @ N", game_id="401859974"),
        _clean_row(matchup="O @ P", game_id="401859975", side="away"),
        _clean_row(matchup="Q @ R", game_id="401859976"),
    ]
    _write_ledger(ledger, rows)
    report = scan_ledger(ledger)
    assert report["total_rows"] == 3, (
        "expected 3 total_rows; got %d" % report["total_rows"]
    )
    _assert_no_banned(report)


# ---------------------------------------------------------------------------
# Tests for scan_assert (CI assertion -- read-only, raises on dirty)
# ---------------------------------------------------------------------------


def test_scan_assert_passes_on_clean_ledger(tmp_path: Path) -> None:
    """scan_assert must pass silently when ledger is clean."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [_clean_row(matchup="S @ T", game_id="401859980")])
    # Should NOT raise:
    scan_assert(ledger)


def test_scan_assert_raises_on_synthetic_row(tmp_path: Path) -> None:
    """scan_assert must raise AssertionError when a synthetic row is present."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [_clean_row(sport="test_nba", matchup="U @ V")])
    with pytest.raises(AssertionError) as exc_info:
        scan_assert(ledger)
    msg = str(exc_info.value)
    assert "DIRTY" in msg, "error message must mention DIRTY; got %r" % msg
    assert "synthetic" in msg.lower(), "error must name synthetic count"


def test_scan_assert_raises_on_malformed_row(tmp_path: Path) -> None:
    """scan_assert must raise AssertionError when a malformed row is present."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [_clean_row(game_id="gg")])
    with pytest.raises(AssertionError):
        scan_assert(ledger)


def test_scan_assert_raises_on_missing_ledger(tmp_path: Path) -> None:
    """scan_assert must raise AssertionError when ledger is missing (INSUFFICIENT_DATA)."""
    ledger = tmp_path / "nonexistent.jsonl"
    with pytest.raises(AssertionError) as exc_info:
        scan_assert(ledger)
    assert "INSUFFICIENT_DATA" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tests for purge_ledger (guarded purge -- explicit CLI only)
# ---------------------------------------------------------------------------


def test_purge_dry_run_does_not_mutate(tmp_path: Path) -> None:
    """purge_ledger with dry_run=True must NOT modify the ledger file."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _clean_row(sport="test_nba", matchup="W @ X"),
        _clean_row(matchup="Y @ Z", game_id="401859981"),
    ])
    mtime_before = ledger.stat().st_mtime
    result = purge_ledger(ledger, dry_run=True)
    assert ledger.stat().st_mtime == mtime_before, "dry_run must not modify the file"
    assert result["status"] == "dry_run"
    assert result["dry_run"] is True
    assert result["rows_removed"] == 1, "must identify 1 synthetic row to remove"
    assert result["rows_kept"] == 1
    assert result["backup_path"] is None, "dry_run must not create a backup"
    _assert_no_banned(result)


def test_purge_default_is_dry_run() -> None:
    """purge_ledger() must default to dry_run=True (safe by default)."""
    import inspect
    sig = inspect.signature(purge_ledger)
    default = sig.parameters["dry_run"].default
    assert default is True, "dry_run must default to True; got %r" % default


def test_purge_removes_synthetic_keeps_real(tmp_path: Path) -> None:
    """purge_ledger dry_run=False removes synthetic rows; real rows survive."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _clean_row(sport="test_nba", matchup="A @ B"),
        _clean_row(matchup="C @ D", game_id="401859982"),
        _clean_row(matchup="E @ F", game_id="401859983", side="away"),
    ])
    result = purge_ledger(ledger, dry_run=False)
    assert result["status"] == "purged"
    assert result["rows_removed"] == 1
    assert result["rows_kept"] == 2
    assert result["backup_path"] is not None, "backup must be created"
    assert Path(result["backup_path"]).exists(), "backup file must exist on disk"
    after = scan_ledger(ledger)
    assert after["status"] == "clean", "ledger must be clean after purge"
    assert after["total_rows"] == 2
    _assert_no_banned(result)


def test_purge_removes_malformed_keeps_real(tmp_path: Path) -> None:
    """purge_ledger dry_run=False removes malformed rows; real rows survive."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _clean_row(game_id="gg"),                        # malformed: too short
        _clean_row(matchup="G @ H", game_id="401859984"),
    ])
    result = purge_ledger(ledger, dry_run=False)
    assert result["rows_removed"] == 1
    assert result["rows_kept"] == 1
    after = scan_ledger(ledger)
    assert after["status"] == "clean"
    _assert_no_banned(result)


def test_purge_does_not_remove_duplicates(tmp_path: Path) -> None:
    """purge_ledger must NOT remove duplicate rows (ambiguous -- manual resolution)."""
    ledger = tmp_path / "led.jsonl"
    base = _clean_row(matchup="NYK @ SAS", game_id="401859985")
    dup = dict(base)
    dup["taken_decimal"] = 2.20
    _write_ledger(ledger, [base, dup])
    result = purge_ledger(ledger, dry_run=False)
    assert result["rows_removed"] == 0, (
        "purge must not remove duplicate rows; rows_removed=%d" % result["rows_removed"]
    )
    assert result["rows_kept"] == 2
    assert result["backup_path"] is None, "no backup when nothing removed"
    _assert_no_banned(result)


def test_purge_no_banned_keys_in_result(tmp_path: Path) -> None:
    """purge_ledger result must carry no $ / pnl / profit key."""
    ledger = tmp_path / "led.jsonl"
    row = _clean_row(matchup="I @ J", game_id="401859986")
    row["pnl"] = 10.0
    _write_ledger(ledger, [row])
    result = purge_ledger(ledger, dry_run=True)
    _assert_no_banned(result)


def test_purge_missing_ledger_returns_insufficient(tmp_path: Path) -> None:
    """purge_ledger on a missing file returns INSUFFICIENT_DATA without crashing."""
    result = purge_ledger(tmp_path / "nonexistent.jsonl", dry_run=False)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["rows_removed"] == 0
    _assert_no_banned(result)


def test_purge_backup_contains_original_rows(tmp_path: Path) -> None:
    """The .bak file from purge_ledger must contain ALL original rows (pre-purge)."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _clean_row(sport="test_nba", matchup="K @ L"),
        _clean_row(matchup="M @ N", game_id="401859987"),
    ])
    result = purge_ledger(ledger, dry_run=False)
    bak_rows = [
        json.loads(ln)
        for ln in Path(result["backup_path"]).read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(bak_rows) == 2, "backup must preserve all 2 original rows; got %d" % len(bak_rows)


# ---------------------------------------------------------------------------
# Tests for governance integration shape (non-blocking reported-line contract)
# These validate that scan_ledger output is consumable as a reported line
# in run_governance.ledger_health WITHOUT gating ok-ness.
# ---------------------------------------------------------------------------

_GOVERNANCE_SHAPE_KEYS = frozenset({
    "status", "total_rows", "synthetic", "malformed", "duplicates",
    "honest_clv", "honest_note",
})


def test_scan_ledger_shape_has_required_keys(tmp_path: Path) -> None:
    """scan_ledger must return all keys needed by the governance reported line."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [_clean_row(matchup="AHH @ ZZZ", game_id="401999001")])
    report = scan_ledger(ledger)
    missing = _GOVERNANCE_SHAPE_KEYS - set(report.keys())
    assert not missing, "scan_ledger missing keys for governance: %r" % missing
    _assert_no_banned(report)


def test_scan_ledger_readonly_no_side_effects(tmp_path: Path) -> None:
    """scan_ledger must not create, modify, or delete any file (pure read-only)."""
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _clean_row(sport="test_tennis", matchup="P @ Q"),
        _clean_row(matchup="R @ S", game_id="401999002"),
    ])
    mtime_before = ledger.stat().st_mtime
    size_before = ledger.stat().st_size
    files_before = sorted(str(f) for f in tmp_path.iterdir())

    scan_ledger(ledger)

    assert ledger.stat().st_mtime == mtime_before, "scan_ledger must not modify the ledger"
    assert ledger.stat().st_size == size_before, "scan_ledger must not change ledger size"
    files_after = sorted(str(f) for f in tmp_path.iterdir())
    assert files_before == files_after, "scan_ledger must not create or delete files"


def test_scan_ledger_dirty_does_not_block_governance(tmp_path: Path) -> None:
    """A dirty ledger report must be consumable as a non-blocking warning.

    Concretely: the report has a 'status' key; the caller (governance) can
    inspect it without raising; and 'dirty' != gating (the caller decides).
    This test simulates what _run_ledger_health in run_governance does.
    """
    ledger = tmp_path / "led.jsonl"
    _write_ledger(ledger, [
        _clean_row(sport="test_nba", matchup="T @ U"),  # synthetic -> dirty
        _clean_row(game_id="gg"),                        # malformed -> dirty
    ])
    report = scan_ledger(ledger)
    # Governance consumes these fields as the reported line:
    assert "status" in report
    assert "synthetic" in report
    assert "malformed" in report
    assert "duplicates" in report
    assert "honest_clv" in report
    # Status is dirty but the report itself is not an exception / does not raise
    assert report["status"] == "dirty"
    # synthetic and malformed sub-counts must both be >= 1
    assert report["synthetic"]["count"] >= 1
    assert report["malformed"]["count"] >= 1
    _assert_no_banned(report)


def test_scan_ledger_insufficient_data_shape(tmp_path: Path) -> None:
    """Missing ledger returns INSUFFICIENT_DATA with all expected keys present."""
    ledger = tmp_path / "no_such_file.jsonl"
    report = scan_ledger(ledger)
    assert report["status"] == "INSUFFICIENT_DATA"
    # All governance shape keys must be present even for INSUFFICIENT_DATA
    for key in _GOVERNANCE_SHAPE_KEYS:
        assert key in report, "INSUFFICIENT_DATA report missing key: %r" % key
    _assert_no_banned(report)
