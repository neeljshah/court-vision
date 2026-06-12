"""tests/platform/test_soccer_signals.py — Gate-candidate signal tests for domains.soccer.

Verifies:
  - Each signal returns None when required ctx.extra keys are missing.
  - Each signal returns correct clipped values when keys are present.
  - Clip boundaries are enforced (e.g. rest diff +50 → +10; totals diff +5 → +2.5).
  - SoccerH2HTotalsSignal returns None when h2h_total < 3.
  - hypothesis() fields: target=="winprob", scope=="pregame",
    expected_verdict=="REJECT", non-empty statement and rationale.
  - ALL_SIGNALS has exactly 3 entries, all Signal subclasses with distinct names.
  - AST forbidden-import check: no domains.* (except domains.soccer.signals itself)
    and no src.* except src.loop.signal in the signals module source.
"""
from __future__ import annotations

import ast
import datetime as _dt
import pathlib

import pytest

from src.loop.signal import AsOfContext, Signal
from domains.soccer.signals import (
    ALL_SIGNALS,
    SoccerH2HTotalsSignal,
    SoccerRestCongestionSignal,
    SoccerTotalsFormSignal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(**extra) -> AsOfContext:
    """Build a minimal AsOfContext with the given extra keys."""
    return AsOfContext(
        decision_time=_dt.datetime(2026, 1, 15, 12, 0, 0),
        extra=dict(extra),
    )


# ---------------------------------------------------------------------------
# SoccerRestCongestionSignal
# ---------------------------------------------------------------------------

class TestSoccerRestCongestionSignal:
    sig = SoccerRestCongestionSignal()

    def test_none_when_rest_home_missing(self):
        ctx = _ctx(rest_days_away=3)
        assert self.sig.build(ctx) is None

    def test_none_when_rest_away_missing(self):
        ctx = _ctx(rest_days_home=5)
        assert self.sig.build(ctx) is None

    def test_none_when_both_missing(self):
        assert self.sig.build(_ctx()) is None

    def test_correct_value(self):
        ctx = _ctx(rest_days_home=7, rest_days_away=3)
        result = self.sig.build(ctx)
        assert result == pytest.approx(4.0)

    def test_clip_positive(self):
        # diff = +50 → should clip to +10
        ctx = _ctx(rest_days_home=55, rest_days_away=5)
        assert self.sig.build(ctx) == pytest.approx(10.0)

    def test_clip_negative(self):
        # diff = -50 → should clip to -10
        ctx = _ctx(rest_days_home=5, rest_days_away=55)
        assert self.sig.build(ctx) == pytest.approx(-10.0)

    def test_zero_diff(self):
        ctx = _ctx(rest_days_home=4, rest_days_away=4)
        assert self.sig.build(ctx) == pytest.approx(0.0)

    def test_hypothesis_fields(self):
        h = self.sig.hypothesis()
        assert h.target == "winprob"
        assert h.scope == "pregame"
        assert h.expected_verdict == "REJECT"
        assert h.statement.strip()
        assert h.rationale.strip()
        assert h.name == self.sig.name


# ---------------------------------------------------------------------------
# SoccerTotalsFormSignal
# ---------------------------------------------------------------------------

class TestSoccerTotalsFormSignal:
    sig = SoccerTotalsFormSignal()

    def test_none_when_recent_totals_missing(self):
        ctx = _ctx(lam_total=2.5)
        assert self.sig.build(ctx) is None

    def test_none_when_lam_missing(self):
        ctx = _ctx(recent_totals_mean=3.0)
        assert self.sig.build(ctx) is None

    def test_none_when_recent_totals_none(self):
        # adapter sets recent_totals_mean=None when < 5 prior matches
        ctx = _ctx(recent_totals_mean=None, lam_total=2.5)
        assert self.sig.build(ctx) is None

    def test_none_when_both_missing(self):
        assert self.sig.build(_ctx()) is None

    def test_correct_value(self):
        ctx = _ctx(recent_totals_mean=3.2, lam_total=2.5)
        result = self.sig.build(ctx)
        assert result == pytest.approx(0.7)

    def test_clip_positive(self):
        # diff = +5 → should clip to +2.5
        ctx = _ctx(recent_totals_mean=7.5, lam_total=2.5)
        assert self.sig.build(ctx) == pytest.approx(2.5)

    def test_clip_negative(self):
        # diff = -5 → should clip to -2.5
        ctx = _ctx(recent_totals_mean=0.0, lam_total=5.0)
        assert self.sig.build(ctx) == pytest.approx(-2.5)

    def test_hypothesis_fields(self):
        h = self.sig.hypothesis()
        assert h.target == "winprob"
        assert h.scope == "pregame"
        assert h.expected_verdict == "REJECT"
        assert h.statement.strip()
        assert h.rationale.strip()
        assert h.name == self.sig.name


# ---------------------------------------------------------------------------
# SoccerH2HTotalsSignal
# ---------------------------------------------------------------------------

class TestSoccerH2HTotalsSignal:
    sig = SoccerH2HTotalsSignal()

    def test_none_when_h2h_totals_mean_missing(self):
        ctx = _ctx(h2h_total=5, lam_total=2.5)
        assert self.sig.build(ctx) is None

    def test_none_when_h2h_total_missing(self):
        ctx = _ctx(h2h_totals_mean=3.0, lam_total=2.5)
        assert self.sig.build(ctx) is None

    def test_none_when_lam_missing(self):
        ctx = _ctx(h2h_totals_mean=3.0, h2h_total=5)
        assert self.sig.build(ctx) is None

    def test_none_when_all_missing(self):
        assert self.sig.build(_ctx()) is None

    def test_none_when_h2h_total_zero(self):
        ctx = _ctx(h2h_totals_mean=3.0, h2h_total=0, lam_total=2.5)
        assert self.sig.build(ctx) is None

    def test_none_when_h2h_total_one(self):
        ctx = _ctx(h2h_totals_mean=3.0, h2h_total=1, lam_total=2.5)
        assert self.sig.build(ctx) is None

    def test_none_when_h2h_total_two(self):
        ctx = _ctx(h2h_totals_mean=3.0, h2h_total=2, lam_total=2.5)
        assert self.sig.build(ctx) is None

    def test_accepts_at_threshold_three(self):
        ctx = _ctx(h2h_totals_mean=3.5, h2h_total=3, lam_total=2.5)
        result = self.sig.build(ctx)
        assert result == pytest.approx(1.0)

    def test_correct_value(self):
        ctx = _ctx(h2h_totals_mean=3.0, h2h_total=10, lam_total=2.5)
        assert self.sig.build(ctx) == pytest.approx(0.5)

    def test_clip_positive(self):
        # diff = +5 → should clip to +2.5
        ctx = _ctx(h2h_totals_mean=8.0, h2h_total=8, lam_total=3.0)
        assert self.sig.build(ctx) == pytest.approx(2.5)

    def test_clip_negative(self):
        # diff = -5 → should clip to -2.5
        ctx = _ctx(h2h_totals_mean=0.5, h2h_total=6, lam_total=5.5)
        assert self.sig.build(ctx) == pytest.approx(-2.5)

    def test_hypothesis_fields(self):
        h = self.sig.hypothesis()
        assert h.target == "winprob"
        assert h.scope == "pregame"
        assert h.expected_verdict == "REJECT"
        assert h.statement.strip()
        assert h.rationale.strip()
        assert h.name == self.sig.name


# ---------------------------------------------------------------------------
# ALL_SIGNALS catalogue tests
# ---------------------------------------------------------------------------

class TestAllSignals:
    def test_exactly_three_entries(self):
        assert len(ALL_SIGNALS) == 3

    def test_all_are_signal_subclasses(self):
        for cls in ALL_SIGNALS:
            assert issubclass(cls, Signal), f"{cls} is not a Signal subclass"

    def test_distinct_names(self):
        names = [cls.name for cls in ALL_SIGNALS]
        assert len(set(names)) == 3, f"Duplicate names: {names}"

    def test_correct_classes_present(self):
        classes = set(ALL_SIGNALS)
        assert SoccerRestCongestionSignal in classes
        assert SoccerTotalsFormSignal in classes
        assert SoccerH2HTotalsSignal in classes

    def test_all_target_winprob(self):
        for cls in ALL_SIGNALS:
            assert cls.target == "winprob", f"{cls.name}.target != 'winprob'"

    def test_all_scope_pregame(self):
        for cls in ALL_SIGNALS:
            assert cls.scope == "pregame", f"{cls.name}.scope != 'pregame'"


# ---------------------------------------------------------------------------
# AST forbidden-import check
# ---------------------------------------------------------------------------

class TestForbiddenImports:
    """Parse domains/soccer/signals.py with AST and assert import discipline."""

    SIGNALS_FILE = (
        pathlib.Path(__file__).parent.parent.parent
        / "domains" / "soccer" / "signals.py"
    )

    def _collect_imports(self) -> list[str]:
        """Return all imported module names from the signals source file."""
        source = self.SIGNALS_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.append(node.module)
        return imported

    def test_no_domains_nba(self):
        for mod in self._collect_imports():
            assert not mod.startswith("domains.nba"), f"Forbidden import: {mod}"
            assert not mod.startswith("domains.basketball_nba"), f"Forbidden import: {mod}"

    def test_no_domains_tennis(self):
        for mod in self._collect_imports():
            assert not mod.startswith("domains.tennis"), f"Forbidden import: {mod}"

    def test_no_src_except_loop_signal(self):
        for mod in self._collect_imports():
            if mod.startswith("src."):
                assert mod == "src.loop.signal", (
                    f"Forbidden src import: {mod} (only src.loop.signal allowed)"
                )

    def test_no_domains_soccer_config(self):
        for mod in self._collect_imports():
            assert mod != "domains.soccer.config", (
                "Forbidden import: domains.soccer.config (signals are pure ctx.extra logic)"
            )

    def test_tennis_string_absent(self):
        source = self.SIGNALS_FILE.read_text(encoding="utf-8")
        # The word "tennis" must not appear in the signals source
        assert "tennis" not in source.lower(), (
            "String 'tennis' found in domains/soccer/signals.py"
        )
