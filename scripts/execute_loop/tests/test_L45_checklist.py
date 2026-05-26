"""test_L45_checklist.py — Tests for L45_daily_checklist operator workflow.

Coverage:
    test_morning_phase_runs_all_steps       — 5 morning items present
    test_midday_phase_runs_all_steps        — 4 midday items present
    test_postgame_phase_runs_all_steps      — 4 postgame items present
    test_unknown_phase_raises_valueerror    — bad phase → ValueError
    test_missing_module_marks_skip          — L19=None → clv_report SKIP
    test_atomic_write_report                — write_report creates file; os.replace error leaves original
    test_main_cli_exit_code                 — exit 0 on all PASS; exit 1 on any FAIL
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Make sure project root is on sys.path so relative imports resolve
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

# ---------------------------------------------------------------------------
# Import module under test
# ---------------------------------------------------------------------------
import scripts.execute_loop.L45_daily_checklist as L45
from scripts.execute_loop.L45_daily_checklist import (
    ChecklistItem,
    DailyChecklist,
    _atomic_write_text,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pass_item(phase: str = "morning", name: str = "step") -> ChecklistItem:
    return ChecklistItem(
        phase=phase,
        name=name,
        status="PASS",
        detail="ok",
        duration_ms=1,
        timestamp="2026-05-25T00:00:00+00:00",
    )


def _make_fail_item(phase: str = "morning", name: str = "bad_step") -> ChecklistItem:
    return ChecklistItem(
        phase=phase,
        name=name,
        status="FAIL",
        detail="something broke",
        duration_ms=2,
        timestamp="2026-05-25T00:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# Fixtures: stub out heavy modules so tests run without real infrastructure
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def stub_all_deps(monkeypatch):
    """Replace all L-module references in L45 with lightweight stubs.

    Each stub returns sensible pass-through values so phases complete
    without hitting files, network, or heavy imports.
    """
    # ── L44: paper mode ────────────────────────────────────────────────────
    l44_stub = types.SimpleNamespace(is_paper_mode=lambda: True)
    monkeypatch.setattr(L45, "L44", l44_stub)

    # ── L42: production readiness ──────────────────────────────────────────
    fake_report = types.SimpleNamespace(
        summary={"layers": 10, "pass": 30, "fail": 0, "skip": 0, "n_a": 2}
    )
    fake_checker = MagicMock()
    fake_checker.run_all_checks.return_value = fake_report
    fake_ReadinessChecker = MagicMock(return_value=fake_checker)
    l42_stub = types.SimpleNamespace(ReadinessChecker=fake_ReadinessChecker)
    monkeypatch.setattr(L45, "L42", l42_stub)

    # ── L38: health dashboard ──────────────────────────────────────────────
    fake_health_check = types.SimpleNamespace(status="PASS", severity="info")
    fake_health_report = types.SimpleNamespace(
        overall_status="HEALTHY",
        checks=[fake_health_check],
        timestamp="2026-05-25T00:00:00.000000+00:00",
    )
    l38_stub = types.SimpleNamespace(get_latest_health=lambda: fake_health_report)
    monkeypatch.setattr(L45, "L38", l38_stub)

    # ── L07: P&L ledger ───────────────────────────────────────────────────
    l07_stub = types.SimpleNamespace(
        get_open_bets=lambda: [],
        get_pnl_summary=lambda: {"pts": {"total_pnl": 5.0, "total_staked": 100.0}},
        settle_unsettled=lambda: 3,
    )
    monkeypatch.setattr(L45, "L07", l07_stub)

    # ── L41: integration harness ──────────────────────────────────────────
    fake_harness = MagicMock()
    fake_harness.run_end_to_end.return_value = {
        "summary": {"overall": "PASS", "n_pass": 8, "n_fail": 0, "n_skip": 2}
    }
    l41_stub = types.SimpleNamespace(IntegrationHarness=MagicMock(return_value=fake_harness))
    monkeypatch.setattr(L45, "L41", l41_stub)

    # ── L08: drift detector ───────────────────────────────────────────────
    l08_stub = types.SimpleNamespace(
        daily_drift_report=lambda: {"n_drift": 0, "n_warn": 0, "n_ok": 7}
    )
    monkeypatch.setattr(L45, "L08", l08_stub)

    # ── L16: live trader ──────────────────────────────────────────────────
    monkeypatch.setattr(L45, "L16", types.SimpleNamespace(_PAPER_LEDGER=[]))

    # ── L19: CLV calculator ───────────────────────────────────────────────
    l19_stub = types.SimpleNamespace(
        nightly_clv_report=lambda: {"n_bets": 12, "generated_at": "2026-05-25T23:00:00"}
    )
    monkeypatch.setattr(L45, "L19", l19_stub)

    # ── L37: postmortem ───────────────────────────────────────────────────
    l37_stub = types.SimpleNamespace(detect_incidents=lambda window_days=1: [])
    monkeypatch.setattr(L45, "L37", l37_stub)

    # ── L27: tax tracking ─────────────────────────────────────────────────
    l27_stub = types.SimpleNamespace(
        export_1099_ready=lambda year, out_path=None: "/tmp/fake_1099_2026.csv"
    )
    monkeypatch.setattr(L45, "L27", l27_stub)

    yield


# ===========================================================================
# Tests
# ===========================================================================

class TestMorningPhase:
    def test_morning_phase_runs_all_steps(self):
        """Morning phase must produce exactly 5 checklist items with the right names."""
        cl = DailyChecklist("morning")
        items = cl.run()
        assert len(items) == 5, f"Expected 5 items, got {len(items)}"
        names = [i.name for i in items]
        assert "paper_mode_check" in names
        assert "l42_readiness_audit" in names
        assert "l38_health_snapshot" in names
        assert "bankroll_check" in names
        assert "l41_integration_smoke" in names

    def test_morning_all_have_valid_fields(self):
        cl = DailyChecklist("morning")
        items = cl.run()
        for item in items:
            assert item.phase == "morning"
            assert item.status in ("PASS", "FAIL", "WARN", "SKIP")
            assert isinstance(item.duration_ms, int)
            assert item.timestamp  # non-empty ISO string


class TestMiddayPhase:
    def test_midday_phase_runs_all_steps(self):
        """Midday phase must produce exactly 4 checklist items."""
        cl = DailyChecklist("midday")
        items = cl.run()
        assert len(items) == 4, f"Expected 4 items, got {len(items)}"
        names = [i.name for i in items]
        assert "paper_mode_check" in names
        assert "l38_health_snapshot" in names
        assert "drift_check" in names
        assert "open_positions_count" in names


class TestPostgamePhase:
    def test_postgame_phase_runs_all_steps(self):
        """Postgame phase must produce exactly 4 checklist items."""
        cl = DailyChecklist("postgame")
        items = cl.run()
        assert len(items) == 4, f"Expected 4 items, got {len(items)}"
        names = [i.name for i in items]
        assert "settle_pending" in names
        assert "clv_report" in names
        assert "postmortem" in names
        assert "tax_tracking_update" in names


class TestUnknownPhase:
    def test_unknown_phase_raises_valueerror(self):
        """An unrecognised phase must raise ValueError immediately."""
        with pytest.raises(ValueError, match="Unknown phase"):
            DailyChecklist("halftime")


class TestMissingModule:
    def test_missing_module_marks_skip(self, monkeypatch):
        """When L19 is None the clv_report step must be SKIP, not FAIL."""
        monkeypatch.setattr(L45, "L19", None)
        cl = DailyChecklist("postgame")
        items = cl.run()
        clv_item = next((i for i in items if i.name == "clv_report"), None)
        assert clv_item is not None, "clv_report step not found in postgame items"
        assert clv_item.status == "SKIP"
        assert "exception" in clv_item.detail.lower() or "not available" in clv_item.detail.lower()


class TestAtomicWriteReport:
    def test_write_report_creates_file(self, tmp_path):
        """write_report must create the markdown file at the given path."""
        cl = DailyChecklist("morning")
        items = [_make_pass_item("morning", "step_a"), _make_pass_item("morning", "step_b")]
        out = tmp_path / "test_report.md"
        result = cl.write_report(items, path=out)
        assert result == out
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Daily Checklist" in content
        assert "step_a" in content

    def test_atomic_write_error_leaves_original_unchanged(self, tmp_path):
        """If os.replace raises, the original file content is preserved."""
        target = tmp_path / "existing.md"
        original_text = "original content"
        target.write_text(original_text, encoding="utf-8")

        with patch("scripts.execute_loop.L45_daily_checklist.os.replace",
                   side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                _atomic_write_text(target, "new content that should not persist")

        # Original file must still hold the original content
        assert target.read_text(encoding="utf-8") == original_text


class TestMainCliExitCode:
    def test_main_cli_exit_code_zero_on_all_pass(self, tmp_path, monkeypatch):
        """main() must return 0 when all checklist items are PASS/WARN/SKIP."""
        out = tmp_path / "morning.md"
        # All stubs produce PASS — exit code must be 0
        code = main(["morning", "--out", str(out)])
        assert code == 0

    def test_main_cli_exit_code_one_on_fail(self, tmp_path, monkeypatch):
        """main() must return 1 when at least one item is FAIL."""
        # Patch run() on DailyChecklist to inject a FAIL item
        out = tmp_path / "morning_fail.md"

        original_run = DailyChecklist.run

        def _patched_run(self):
            items = original_run(self)
            # Force the first item to FAIL
            items[0] = ChecklistItem(
                phase=items[0].phase,
                name=items[0].name,
                status="FAIL",
                detail="forced failure",
                duration_ms=items[0].duration_ms,
                timestamp=items[0].timestamp,
            )
            return items

        monkeypatch.setattr(DailyChecklist, "run", _patched_run)
        code = main(["morning", "--out", str(out)])
        assert code == 1
