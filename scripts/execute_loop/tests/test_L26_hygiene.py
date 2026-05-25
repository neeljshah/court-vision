"""Tests for scripts/execute_loop/L26_account_hygiene.py.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L26_hygiene.py -v
"""
from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path; stub heavy / missing imports
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub modules that may not exist in the test environment
for _mod in (
    "scripts.execute_loop.L22_alerting",
    "scripts.execute_loop.L18_bankroll_manager",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

import scripts.execute_loop.L26_account_hygiene as L26  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_NOW = datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _bet(
    book: str = "dk",
    minutes_ago: float = 30.0,
    ip: str = "local",
    odds: float = -110.0,
    edge: float = 3.0,
    stake: float = 50.0,
    max_single_bet: float | None = None,
    lock_minutes_after: float | None = None,
) -> dict:
    placed = _NOW - timedelta(minutes=minutes_ago)
    b: dict = {
        "book": book,
        "placed_at_iso": _iso(placed),
        "ip": ip,
        "odds": odds,
        "model_edge_pp": edge,
        "stake": stake,
    }
    if max_single_bet is not None:
        b["max_single_bet"] = max_single_bet
    if lock_minutes_after is not None:
        b["lock_time"] = _iso(placed + timedelta(minutes=lock_minutes_after))
    return b


# ---------------------------------------------------------------------------
# 1. check_submission_pace — 9 bets in last hour → WARN + throttle 480
# ---------------------------------------------------------------------------
class TestCheckSubmissionPace:
    def test_nine_bets_warn(self):
        bets = [_bet(minutes_ago=m, book="dk") for m in range(1, 10)]  # 9 bets in last hour
        result = L26.check_submission_pace("dk", bets)
        assert result.throttle_seconds_recommended == 480
        assert result.status == "WARN"
        assert result.n_bets_today >= 9
        assert result.current_pace_per_hour == pytest.approx(9.0)

    def test_eleven_bets_fail(self):
        """Test 6: >10 bets last hour → FAIL."""
        bets = [_bet(minutes_ago=m, book="fd") for m in range(1, 12)]  # 11 bets
        result = L26.check_submission_pace("fd", bets)
        assert result.current_pace_per_hour == pytest.approx(11.0)
        assert result.throttle_seconds_recommended == 480
        # Status is derived by daily_hygiene_report, but direct pace check exposes raw count
        # The BetPace throttle_seconds_recommended == 480 for both WARN and FAIL triggers

    def test_few_bets_pass(self):
        bets = [_bet(minutes_ago=m, book="dk") for m in range(1, 6)]  # 5 bets
        result = L26.check_submission_pace("dk", bets)
        assert result.throttle_seconds_recommended == 0
        assert result.current_pace_per_hour == pytest.approx(5.0)

    def test_different_book_ignored(self):
        bets = [_bet(minutes_ago=m, book="fd") for m in range(1, 12)]
        result = L26.check_submission_pace("dk", bets)
        assert result.current_pace_per_hour == pytest.approx(0.0)
        assert result.throttle_seconds_recommended == 0

    def test_stale_bets_not_counted(self):
        # 5 bets over an hour old, 3 fresh
        old = [_bet(minutes_ago=90, book="dk") for _ in range(5)]
        fresh = [_bet(minutes_ago=10, book="dk") for _ in range(3)]
        result = L26.check_submission_pace("dk", old + fresh)
        assert result.current_pace_per_hour == pytest.approx(3.0)

    def test_exact_ten_bets_warn(self):
        bets = [_bet(minutes_ago=m, book="dk") for m in range(1, 11)]  # exactly 10
        result = L26.check_submission_pace("dk", bets)
        assert result.throttle_seconds_recommended == 480

    def test_max_bets_per_hour_default(self):
        result = L26.check_submission_pace("dk", [])
        assert result.max_bets_per_hour == 10


# ---------------------------------------------------------------------------
# 2. check_ip_consistency — all "local" IPs → PASS
# ---------------------------------------------------------------------------
class TestCheckIpConsistency:
    def test_all_local_pass(self):
        """Test 2: all 'local' IPs → PASS."""
        bets = [_bet(ip="local") for _ in range(10)]
        result = L26.check_ip_consistency(bets)
        assert result.status == "PASS"
        assert result.check_name == "ip_consistency"

    def test_two_ips_pass(self):
        bets = [_bet(ip="1.2.3.4"), _bet(ip="5.6.7.8")]
        result = L26.check_ip_consistency(bets)
        assert result.status == "PASS"

    def test_three_ips_warn(self):
        bets = [_bet(ip=f"10.0.0.{i}") for i in range(1, 4)]
        result = L26.check_ip_consistency(bets)
        assert result.status == "WARN"
        assert "multi-IP" in result.details or "distinct IP" in result.details

    def test_no_bets_pass(self):
        result = L26.check_ip_consistency([])
        assert result.status == "PASS"
        assert "no recent" in result.details

    def test_missing_ip_field_defaults_local(self):
        # Bets without "ip" key all default to "local" → 1 distinct IP
        bets = [{"book": "dk", "placed_at_iso": _iso(_NOW)} for _ in range(5)]
        result = L26.check_ip_consistency(bets)
        assert result.status == "PASS"


# ---------------------------------------------------------------------------
# 3. check_pattern_flags — 10 max-stake bets → WARN for max_stake_repetition
# ---------------------------------------------------------------------------
class TestCheckPatternFlags:
    def test_max_stake_repetition_warn(self):
        """Test 3: 10 max-stake bets → WARN entry."""
        bets = [_bet(stake=100.0, max_single_bet=100.0) for _ in range(10)]
        results = L26.check_pattern_flags(bets)
        names = [r.check_name for r in results]
        statuses = [r.status for r in results]
        assert "max_stake_repetition" in names
        idx = names.index("max_stake_repetition")
        assert statuses[idx] == "WARN"

    def test_max_stake_below_threshold_pass(self):
        # Only 4 max-stake bets → no WARN
        bets = (
            [_bet(stake=100.0, max_single_bet=100.0) for _ in range(4)]
            + [_bet(stake=50.0) for _ in range(6)]
        )
        results = L26.check_pattern_flags(bets)
        names = [r.check_name for r in results]
        assert "max_stake_repetition" not in names

    def test_sharp_ev_pattern_warn(self):
        # 18 of 20 bets at -110 with positive edge → ≥80%
        bets = [_bet(odds=-110, edge=5.0) for _ in range(18)] + [_bet(odds=-200, edge=0.0) for _ in range(2)]
        results = L26.check_pattern_flags(bets)
        names = [r.check_name for r in results]
        assert "sharp_ev_pattern" in names
        idx = names.index("sharp_ev_pattern")
        assert results[idx].status == "WARN"

    def test_sharp_ev_below_threshold_no_warn(self):
        # Only 60% at -110 → no flag
        bets = [_bet(odds=-110, edge=5.0) for _ in range(12)] + [_bet(odds=-200, edge=0.0) for _ in range(8)]
        results = L26.check_pattern_flags(bets)
        names = [r.check_name for r in results]
        assert "sharp_ev_pattern" not in names

    def test_news_trading_warn(self):
        # 3 bets placed 1 minute before lock
        near_lock = [_bet(lock_minutes_after=1.0) for _ in range(3)]
        far = [_bet(lock_minutes_after=30.0) for _ in range(7)]
        results = L26.check_pattern_flags(near_lock + far)
        names = [r.check_name for r in results]
        assert "news_trading_pattern" in names

    def test_no_bets_single_pass(self):
        results = L26.check_pattern_flags([])
        assert len(results) == 1
        assert results[0].status == "PASS"

    def test_clean_bets_all_pass(self):
        bets = [_bet(odds=-150, edge=2.0, stake=30.0, lock_minutes_after=60.0) for _ in range(10)]
        results = L26.check_pattern_flags(bets)
        statuses = {r.status for r in results}
        assert "WARN" not in statuses
        assert "FAIL" not in statuses


# ---------------------------------------------------------------------------
# 4. recommend_deposit_schedule — ≥3 distinct days, no round amounts, no dupes
# ---------------------------------------------------------------------------
class TestRecommendDepositSchedule:
    def test_distinct_days_and_books(self):
        """Test 4: ≥3 distinct days, non-round amounts, no duplicate (book, day)."""
        schedule = L26.recommend_deposit_schedule({"dk": 5000, "fd": 3000})
        assert len(schedule) >= 3

        # At least 3 distinct days
        days = [e["date"] for e in schedule]
        assert len(set(days)) >= 3

        # No round amounts (multiples of 10)
        for entry in schedule:
            assert entry["amount"] % 10 != 0, f"Round amount: {entry['amount']}"

        # No duplicate (book, date) pairs
        pairs = [(e["book"], e["date"]) for e in schedule]
        assert len(pairs) == len(set(pairs))

    def test_correct_books_present(self):
        schedule = L26.recommend_deposit_schedule({"bet365": 2000})
        books = {e["book"] for e in schedule}
        assert "bet365" in books

    def test_empty_targets(self):
        schedule = L26.recommend_deposit_schedule({})
        assert schedule == []

    def test_amounts_positive(self):
        schedule = L26.recommend_deposit_schedule({"dk": 1000})
        for entry in schedule:
            assert entry["amount"] > 0


# ---------------------------------------------------------------------------
# 5. Empty recent_bets → daily_hygiene_report returns no_data
# ---------------------------------------------------------------------------
class TestDailyHygieneReport:
    def test_empty_bets_no_data(self, tmp_path, monkeypatch):
        """Test 5: Empty recent_bets → {"status": "no_data", "checks": []}."""
        monkeypatch.setattr(L26, "_LEDGER_DIR", tmp_path)
        result = L26.daily_hygiene_report(recent_bets=[])
        assert result["status"] == "no_data"
        assert result["checks"] == []

    def test_report_written_to_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L26, "_LEDGER_DIR", tmp_path)
        bets = [_bet(minutes_ago=m, book="dk") for m in range(1, 5)]
        L26.daily_hygiene_report(recent_bets=bets)
        from datetime import datetime, timezone as tz
        today_str = datetime.now(tz=tz.utc).strftime("%Y-%m-%d")
        report_file = tmp_path / f"hygiene_report_{today_str}.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text())
        assert "checks" in data
        assert "status" in data

    def test_overall_status_warn_on_ip_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L26, "_LEDGER_DIR", tmp_path)
        bets = [_bet(ip=f"10.0.0.{i}") for i in range(1, 5)]  # 4 distinct IPs → WARN
        result = L26.daily_hygiene_report(recent_bets=bets)
        assert result["status"] in ("WARN", "FAIL")

    def test_report_includes_recommendations(self, tmp_path, monkeypatch):
        monkeypatch.setattr(L26, "_LEDGER_DIR", tmp_path)
        bets = [_bet(minutes_ago=m) for m in range(1, 4)]
        result = L26.daily_hygiene_report(recent_bets=bets, bankroll_targets={"dk": 3000})
        assert "recommendations" in result
        assert len(result["recommendations"]) > 0

    def test_no_data_when_bets_none_and_ledger_missing(self, tmp_path, monkeypatch):
        """When ledger files are absent and recent_bets is None, return no_data."""
        monkeypatch.setattr(L26, "_LEDGER_DIR", tmp_path)
        monkeypatch.setattr(L26, "_BETS_FILE", tmp_path / "nonexistent.parquet")
        monkeypatch.setattr(L26, "_BETS_CSV", tmp_path / "nonexistent.csv")
        result = L26.daily_hygiene_report(recent_bets=None)
        assert result["status"] == "no_data"


# ---------------------------------------------------------------------------
# 6. >10 bets last hour → status FAIL at the report level
# ---------------------------------------------------------------------------
class TestFailStatus:
    def test_eleven_bets_report_fail(self, tmp_path, monkeypatch):
        """Test 6: >10 bets in last hour → report overall status FAIL."""
        monkeypatch.setattr(L26, "_LEDGER_DIR", tmp_path)
        bets = [_bet(minutes_ago=m, book="dk") for m in range(1, 13)]  # 12 bets
        result = L26.daily_hygiene_report(recent_bets=bets)
        assert result["status"] == "FAIL"

    def test_pace_check_fail_details(self):
        bets = [_bet(minutes_ago=m, book="dk") for m in range(1, 12)]  # 11 bets
        pace = L26.check_submission_pace("dk", bets)
        assert pace.current_pace_per_hour > 10
        assert pace.throttle_seconds_recommended == 480
