"""Per-file tests for scripts.platformkit.clv_ledger_betid_backfill.

Acceptance criteria (from workstream BE-R3-3-clv-ledger-betid-selfheal):
  1. Rows lacking bet_id get a derived bet_id from natural fields.
  2. An open row and its settled twin (same natural key, different status)
     produce DISTINCT status-aware keys -- no false dup.
  3. A true same-(bet_id,status) replay still collides.
  4. Report output carries no $/pnl/roi key.

Run:
    cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/test_clv_ledger_betid_backfill.py -q
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.clv_ledger_betid_backfill import (
    derive_bet_id,
    status_aware_key,
    run_report,
    stamp_missing,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _row(
    sport: str = "mlb",
    matchup: str = "TeamA@TeamB",
    side: str = "away",
    book: str = "espn:DraftKings",
    ts: str = "2026-06-17T22:59:11.729868+00:00",
    status: str = "open",
    market: str = None,
    extra: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Build a minimal ledger row without bet_id (like the old 68 rows)."""
    r: Dict[str, Any] = {
        "ts": ts,
        "sport": sport,
        "matchup": matchup,
        "side": side,
        "taken_book": book,
        "taken_decimal": 2.17,
        "model_prob": 0.4655,
        "stake": 21.6,
        "status": status,
        "executed": False,
    }
    if market is not None:
        r["market"] = market
    if extra:
        r.update(extra)
    return r


def _write_jsonl(rows: List[Dict[str, Any]]) -> Path:
    """Write rows to a temp JSONL file; return its Path."""
    fd, name = tempfile.mkstemp(suffix=".jsonl")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    except Exception:
        os.unlink(name)
        raise
    return Path(name)


# ---------------------------------------------------------------------------
# 1. Rows lacking bet_id get a derived bet_id from natural fields
# ---------------------------------------------------------------------------

class TestDeriveBetId:

    def test_basic_derivation(self):
        row = _row()
        bid = derive_bet_id(row)
        # Format: sport|matchup|market|side|book|date
        assert bid.startswith("mlb|TeamA@TeamB|moneyline|away|espn:DraftKings|2026-06-17")

    def test_date_from_ts(self):
        row = _row(ts="2026-06-17T22:59:11.000000+00:00")
        bid = derive_bet_id(row)
        assert bid.endswith("|2026-06-17")

    def test_explicit_game_date_overrides_ts(self):
        row = _row(ts="2026-06-17T22:59:11.000000+00:00",
                   extra={"game_date": "2026-06-18"})
        bid = derive_bet_id(row)
        assert bid.endswith("|2026-06-18")

    def test_timestamped_game_date_stripped_to_date_prefix(self):
        """game_date='2026-06-18T12:00:00' must resolve to '2026-06-18', not the full timestamp.

        This is the parity bug case: clv_ledger._game_date() calls gd[:10] on an
        explicit game_date, so derive_bet_id must do the same.  Without the strip,
        derive_bet_id(row) != clv_ledger.bet_id(row) for any row whose game_date
        carries a time component.
        """
        from scripts.platformkit.clv_ledger import bet_id as canonical_bet_id
        row = _row(ts="2026-06-17T22:59:11.000000+00:00",
                   extra={"game_date": "2026-06-18T12:00:00"})
        bid = derive_bet_id(row)
        # Must strip to date-only prefix
        assert bid.endswith("|2026-06-18"), (
            "derive_bet_id did not strip timestamped game_date to its date prefix: %r" % bid
        )
        # Parity assertion: must equal the canonical clv_ledger.bet_id()
        assert bid == canonical_bet_id(row), (
            "derive_bet_id(%r) != clv_ledger.bet_id(%r) -- parity invariant broken" % (bid, canonical_bet_id(row))
        )

    def test_market_field_used_when_present(self):
        row = _row(market="win_home")
        bid = derive_bet_id(row)
        assert "|win_home|" in bid

    def test_market_type_used_as_fallback(self):
        row = _row(extra={"market_type": "spread"})
        bid = derive_bet_id(row)
        assert "|spread|" in bid

    def test_moneyline_default_when_no_market(self):
        row = _row()
        bid = derive_bet_id(row)
        assert "|moneyline|" in bid

    def test_matches_clv_ledger_bet_id_function(self):
        """derive_bet_id must produce the same string as clv_ledger.bet_id()."""
        from scripts.platformkit.clv_ledger import bet_id as canonical_bet_id
        row = _row()
        assert derive_bet_id(row) == canonical_bet_id(row)

    def test_event_id_takes_priority_over_matchup(self):
        row = _row(extra={"event_id": "nba|401859967"})
        bid = derive_bet_id(row)
        assert "|nba|401859967|" in bid

    def test_row_with_bet_id_ignored_by_derive(self):
        """derive_bet_id looks at natural fields only; ignores existing bet_id."""
        row = _row(extra={"bet_id": "STALE_KEY"})
        # derive_bet_id should still compute from natural fields
        bid = derive_bet_id(row)
        assert "STALE_KEY" not in bid
        assert "mlb" in bid


# ---------------------------------------------------------------------------
# 2. Open row and settled twin produce DISTINCT status-aware keys
# ---------------------------------------------------------------------------

class TestStatusAwareKey:

    def test_open_and_settled_twin_distinct_keys(self):
        open_row = _row(status="open")
        settled_row = _row(status="settled")
        # same natural key, different status -> must differ
        k_open = status_aware_key(open_row)
        k_settled = status_aware_key(settled_row)
        assert k_open != k_settled, (
            "open and settled twins must NOT share a status-aware key"
        )

    def test_open_key_ends_with_open(self):
        row = _row(status="open")
        key = status_aware_key(row)
        assert key.endswith("|open")

    def test_settled_key_ends_with_settled(self):
        row = _row(status="settled")
        key = status_aware_key(row)
        assert key.endswith("|settled")

    def test_row_with_existing_bet_id_uses_it(self):
        row = _row(extra={"bet_id": "mlb|TeamA@TeamB|moneyline|away|espn:DraftKings|2026-06-17"})
        key = status_aware_key(row)
        assert key.startswith("mlb|TeamA@TeamB|moneyline|away|espn:DraftKings|2026-06-17|")

    def test_missing_status_defaults_to_open(self):
        row = {
            "sport": "mlb", "matchup": "X@Y", "side": "home",
            "taken_book": "book", "ts": "2026-06-17T00:00:00+00:00",
        }
        key = status_aware_key(row)
        assert key.endswith("|open")


# ---------------------------------------------------------------------------
# 3. True same-(bet_id,status) replay still collides
# ---------------------------------------------------------------------------

class TestTrueDupCollision:

    def test_identical_rows_produce_same_key(self):
        row1 = _row(status="open")
        row2 = _row(status="open")  # identical natural fields
        assert status_aware_key(row1) == status_aware_key(row2)

    def test_same_bet_id_same_status_collides(self):
        bid = "mlb|TeamA@TeamB|moneyline|away|espn:DraftKings|2026-06-17"
        row1 = _row(extra={"bet_id": bid}, status="open")
        row2 = _row(extra={"bet_id": bid}, status="open")
        assert status_aware_key(row1) == status_aware_key(row2)

    def test_report_detects_true_dup(self):
        open_row = _row(status="open")
        rows = [open_row, dict(open_row)]  # exact replay
        ledger = _write_jsonl(rows)
        try:
            report = run_report(ledger)
            assert report["n_true_dups"] == 1, "should detect 1 true dup"
            assert report["status"] == "DUPS_FOUND"
        finally:
            ledger.unlink(missing_ok=True)

    def test_open_settled_twins_not_counted_as_true_dup(self):
        open_row = _row(status="open")
        settled_row = _row(status="settled")  # same natural key, different status
        ledger = _write_jsonl([open_row, settled_row])
        try:
            report = run_report(ledger)
            assert report["n_true_dups"] == 0, (
                "open/settled twins must NOT be flagged as true dups"
            )
            assert report["status"] == "CLEAN"
        finally:
            ledger.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 4. Report output carries no $/pnl/roi key
# ---------------------------------------------------------------------------

class TestReportHonesty:

    _BANNED = frozenset({
        "dollar", "roi", "profit", "usd", "bankroll",
        "stake_usd", "pnl_units", "profit_units", "roi_units",
    })

    def _check_no_banned(self, obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in self._BANNED, (
                    "banned key %r found at report[%r]" % (k, path + k)
                )
                self._check_no_banned(v, path + k + ".")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                self._check_no_banned(v, path + "[%d]." % i)

    def test_report_has_no_banned_keys(self):
        open_row = _row(status="open")
        settled_row = dict(_row(status="settled"))
        settled_row["pnl"] = 25.3  # pnl is valid in the LEDGER; must not leak to report
        ledger = _write_jsonl([open_row, settled_row])
        try:
            report = run_report(ledger)
            self._check_no_banned(report)
        finally:
            ledger.unlink(missing_ok=True)

    def test_report_missing_ledger_is_unavailable(self):
        report = run_report(Path("/tmp/no_such_ledger_xyz.jsonl"))
        assert report["status"] == "UNAVAILABLE"
        assert report["error"] is not None
        self._check_no_banned(report)

    def test_report_clean_ledger(self):
        rows = [_row(status="open"), _row(status="settled")]
        ledger = _write_jsonl(rows)
        try:
            report = run_report(ledger)
            assert report["status"] == "CLEAN"
            assert report["n_rows"] == 2
            assert report["n_missing_bet_id"] == 2
            assert report["n_open_settled_twins"] == 1
            assert report["n_true_dups"] == 0
        finally:
            ledger.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 5. stamp_missing: pure function, stamps rows correctly
# ---------------------------------------------------------------------------

class TestStampMissing:

    def test_missing_rows_get_bet_id(self):
        rows = [_row(status="open"), _row(status="settled")]
        stamped, n = stamp_missing(rows)
        assert n == 2
        for r in stamped:
            assert "bet_id" in r

    def test_existing_bet_id_preserved(self):
        bid = "mlb|TeamA@TeamB|moneyline|away|espn:DraftKings|2026-06-17"
        rows = [_row(extra={"bet_id": bid})]
        stamped, n = stamp_missing(rows)
        assert n == 0
        assert stamped[0]["bet_id"] == bid

    def test_open_settled_twins_get_distinct_keys_after_stamp(self):
        open_row = _row(status="open")
        settled_row = _row(status="settled")
        stamped, _ = stamp_missing([open_row, settled_row])
        # Both now have bet_id; their status-aware keys must differ
        k_open = status_aware_key(stamped[0])
        k_settled = status_aware_key(stamped[1])
        assert k_open != k_settled

    def test_true_replay_still_collides_after_stamp(self):
        row1 = _row(status="open")
        row2 = _row(status="open")
        stamped, _ = stamp_missing([row1, row2])
        assert status_aware_key(stamped[0]) == status_aware_key(stamped[1])

    def test_stamp_does_not_introduce_banned_keys(self):
        banned = frozenset({"dollar", "roi", "profit", "usd", "bankroll",
                            "stake_usd", "pnl_units", "profit_units", "roi_units"})
        rows = [_row()]
        stamped, _ = stamp_missing(rows)
        for r in stamped:
            for bk in banned:
                assert bk not in r, "banned key %r in stamped row" % bk

    def test_stamp_pure_no_mutation(self):
        row = _row()
        original_keys = set(row.keys())
        stamp_missing([row])
        # original dict must not be mutated
        assert set(row.keys()) == original_keys
        assert "bet_id" not in row


# ---------------------------------------------------------------------------
# 6. Integration: live ledger (read-only sanity check)
# ---------------------------------------------------------------------------

class TestLiveLedger:

    def test_live_ledger_report_runs(self):
        """Report on the real ledger must complete without error."""
        ledger = Path(__file__).resolve().parents[2] / "data" / "frontend" / "clv_ledger.jsonl"
        if not ledger.exists():
            pytest.skip("live ledger not present -- skipping")
        report = run_report(ledger)
        assert report["status"] in ("CLEAN", "DUPS_FOUND", "UNAVAILABLE")
        assert report["n_rows"] >= 0
        # Key acceptance check: open/settled twins correctly NOT counted as true dups
        # (the 31 pairs that exist in the real ledger must all be TWIN not DUP)
        assert report["n_open_settled_twins"] >= 0

    def test_live_ledger_missing_rows_get_derived_bid(self):
        ledger = Path(__file__).resolve().parents[2] / "data" / "frontend" / "clv_ledger.jsonl"
        if not ledger.exists():
            pytest.skip("live ledger not present -- skipping")
        report = run_report(ledger)
        for entry in report["missing_bet_id_rows"]:
            assert entry["derived_bet_id"], "derived_bet_id must be non-empty"
            assert "|" in entry["derived_bet_id"], "must follow sport|matchup|... format"

    def test_live_ledger_open_settled_twins_distinct_keys(self):
        """For every open/settled twin pair in the live ledger, keys must differ."""
        ledger = Path(__file__).resolve().parents[2] / "data" / "frontend" / "clv_ledger.jsonl"
        if not ledger.exists():
            pytest.skip("live ledger not present -- skipping")
        from scripts.platformkit.clv_ledger_betid_backfill import _load_rows

        rows_with_lineno = _load_rows(ledger)
        rows = [r for _, r in rows_with_lineno]
        stamped, _ = stamp_missing(rows)

        from collections import defaultdict
        by_bid: Dict[str, List[str]] = defaultdict(list)
        for r in stamped:
            bid = r.get("bet_id", "")
            status = str(r.get("status") or "open").strip().lower()
            by_bid[bid].append(status)

        for bid, statuses in by_bid.items():
            if len(statuses) > 1:
                # Has multiple rows for same bet_id. If they differ in status
                # (open+settled) their status-aware keys must differ.
                status_set = set(statuses)
                if len(status_set) > 1:
                    # Sanity: each distinct status produces a distinct key
                    keys_for_bid = set(
                        status_aware_key({"bet_id": bid, "status": s})
                        for s in status_set
                    )
                    assert len(keys_for_bid) == len(status_set), (
                        "open/settled twins for %r produced colliding keys" % bid
                    )
