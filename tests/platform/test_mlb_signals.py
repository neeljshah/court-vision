"""tests/platform/test_mlb_signals.py — Gate-candidate signal tests for domains.mlb.

Verifies:
  - Each signal returns None when required ctx.extra keys are missing.
  - Each signal returns correct clipped values when keys are present.
  - Clip boundaries are enforced (rest diff +9 → +3; streak diff +2 → +0.5).
  - MLBH2HSeasonSignal returns None when h2h_n < 6.
  - hypothesis() fields: target=="winprob", scope=="pregame",
    expected_verdict=="REJECT", non-empty statement and rationale.
  - ALL_SIGNALS has exactly 3 entries, all Signal subclasses with distinct names.
  - AST forbidden-import check: no domains.* (except domains.mlb.signals itself)
    and no src.* except src.loop.signal in the signals module source.
"""
from __future__ import annotations

import ast
import datetime as _dt
import pathlib

import pytest

from src.loop.signal import AsOfContext, Signal
from domains.mlb.signals import (
    ALL_SIGNALS,
    MLBH2HSeasonSignal,
    MLBRestAdvantageSignal,
    MLBStreakFormSignal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(**extra) -> AsOfContext:
    """Build a minimal AsOfContext with the given extra keys."""
    return AsOfContext(
        decision_time=_dt.datetime(2026, 4, 15, 12, 0, 0),
        extra=dict(extra),
    )


# ---------------------------------------------------------------------------
# MLBRestAdvantageSignal
# ---------------------------------------------------------------------------

class TestMLBRestAdvantageSignal:
    sig = MLBRestAdvantageSignal()

    def test_none_when_rest_home_missing(self):
        ctx = _ctx(rest_days_away=1)
        assert self.sig.build(ctx) is None

    def test_none_when_rest_away_missing(self):
        ctx = _ctx(rest_days_home=2)
        assert self.sig.build(ctx) is None

    def test_none_when_both_missing(self):
        assert self.sig.build(_ctx()) is None

    def test_correct_value(self):
        ctx = _ctx(rest_days_home=2, rest_days_away=1)
        result = self.sig.build(ctx)
        assert result == pytest.approx(1.0)

    def test_clip_positive(self):
        # diff = +9 → should clip to +3
        ctx = _ctx(rest_days_home=10, rest_days_away=1)
        assert self.sig.build(ctx) == pytest.approx(3.0)

    def test_clip_negative(self):
        # diff = -9 → should clip to -3
        ctx = _ctx(rest_days_home=1, rest_days_away=10)
        assert self.sig.build(ctx) == pytest.approx(-3.0)

    def test_zero_diff(self):
        ctx = _ctx(rest_days_home=1, rest_days_away=1)
        assert self.sig.build(ctx) == pytest.approx(0.0)

    def test_at_positive_boundary(self):
        # diff = exactly +3 → should remain +3
        ctx = _ctx(rest_days_home=4, rest_days_away=1)
        assert self.sig.build(ctx) == pytest.approx(3.0)

    def test_at_negative_boundary(self):
        # diff = exactly -3 → should remain -3
        ctx = _ctx(rest_days_home=1, rest_days_away=4)
        assert self.sig.build(ctx) == pytest.approx(-3.0)

    def test_hypothesis_fields(self):
        h = self.sig.hypothesis()
        assert h.target == "winprob"
        assert h.scope == "pregame"
        assert h.expected_verdict == "REJECT"
        assert h.statement.strip()
        assert h.rationale.strip()
        assert h.name == self.sig.name


# ---------------------------------------------------------------------------
# MLBStreakFormSignal
# ---------------------------------------------------------------------------

class TestMLBStreakFormSignal:
    sig = MLBStreakFormSignal()

    def test_none_when_recent_win10_missing(self):
        ctx = _ctx(p_home_elo=0.52)
        assert self.sig.build(ctx) is None

    def test_none_when_p_home_elo_missing(self):
        ctx = _ctx(recent_win10=0.6)
        assert self.sig.build(ctx) is None

    def test_none_when_recent_win10_is_none(self):
        # adapter sets recent_win10=None when < 10 prior games are available
        ctx = _ctx(recent_win10=None, p_home_elo=0.52)
        assert self.sig.build(ctx) is None

    def test_none_when_both_missing(self):
        assert self.sig.build(_ctx()) is None

    def test_correct_value(self):
        ctx = _ctx(recent_win10=0.7, p_home_elo=0.52)
        result = self.sig.build(ctx)
        assert result == pytest.approx(0.18)

    def test_clip_positive(self):
        # diff = +2.0 → should clip to +0.5
        ctx = _ctx(recent_win10=1.0, p_home_elo=0.0)
        assert self.sig.build(ctx) == pytest.approx(0.5)

    def test_clip_negative(self):
        # diff = -2.0 → should clip to -0.5
        ctx = _ctx(recent_win10=0.0, p_home_elo=1.0)
        assert self.sig.build(ctx) == pytest.approx(-0.5)

    def test_zero_diff(self):
        ctx = _ctx(recent_win10=0.55, p_home_elo=0.55)
        assert self.sig.build(ctx) == pytest.approx(0.0)

    def test_at_positive_boundary(self):
        # diff = exactly +0.5 → should remain +0.5
        ctx = _ctx(recent_win10=1.0, p_home_elo=0.5)
        assert self.sig.build(ctx) == pytest.approx(0.5)

    def test_hypothesis_fields(self):
        h = self.sig.hypothesis()
        assert h.target == "winprob"
        assert h.scope == "pregame"
        assert h.expected_verdict == "REJECT"
        assert h.statement.strip()
        assert h.rationale.strip()
        assert h.name == self.sig.name


# ---------------------------------------------------------------------------
# MLBH2HSeasonSignal
# ---------------------------------------------------------------------------

class TestMLBH2HSeasonSignal:
    sig = MLBH2HSeasonSignal()

    def test_none_when_h2h_rate_missing(self):
        ctx = _ctx(h2h_n=8, p_home_elo=0.52)
        assert self.sig.build(ctx) is None

    def test_none_when_h2h_n_missing(self):
        ctx = _ctx(h2h_rate=0.6, p_home_elo=0.52)
        assert self.sig.build(ctx) is None

    def test_none_when_p_home_elo_missing(self):
        ctx = _ctx(h2h_rate=0.6, h2h_n=8)
        assert self.sig.build(ctx) is None

    def test_none_when_all_missing(self):
        assert self.sig.build(_ctx()) is None

    def test_none_when_h2h_n_zero(self):
        ctx = _ctx(h2h_rate=0.6, h2h_n=0, p_home_elo=0.52)
        assert self.sig.build(ctx) is None

    def test_none_when_h2h_n_one(self):
        ctx = _ctx(h2h_rate=0.6, h2h_n=1, p_home_elo=0.52)
        assert self.sig.build(ctx) is None

    def test_none_when_h2h_n_five(self):
        # h2h_n=5 is below threshold of 6 → None
        ctx = _ctx(h2h_rate=0.6, h2h_n=5, p_home_elo=0.52)
        assert self.sig.build(ctx) is None

    def test_accepts_at_threshold_six(self):
        # h2h_n=6 is exactly at threshold → should compute
        ctx = _ctx(h2h_rate=0.7, h2h_n=6, p_home_elo=0.52)
        result = self.sig.build(ctx)
        assert result == pytest.approx(0.18)

    def test_correct_value(self):
        ctx = _ctx(h2h_rate=0.6, h2h_n=10, p_home_elo=0.52)
        assert self.sig.build(ctx) == pytest.approx(0.08)

    def test_clip_positive(self):
        # diff = +2.0 → should clip to +0.5
        ctx = _ctx(h2h_rate=1.0, h2h_n=12, p_home_elo=0.0)
        assert self.sig.build(ctx) == pytest.approx(0.5)

    def test_clip_negative(self):
        # diff = -2.0 → should clip to -0.5
        ctx = _ctx(h2h_rate=0.0, h2h_n=12, p_home_elo=1.0)
        assert self.sig.build(ctx) == pytest.approx(-0.5)

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
        assert MLBRestAdvantageSignal in classes
        assert MLBStreakFormSignal in classes
        assert MLBH2HSeasonSignal in classes

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
    """Parse domains/mlb/signals.py with AST and assert import discipline."""

    SIGNALS_FILE = (
        pathlib.Path(__file__).parent.parent.parent
        / "domains" / "mlb" / "signals.py"
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

    def test_no_domains_soccer(self):
        for mod in self._collect_imports():
            assert not mod.startswith("domains.soccer"), f"Forbidden import: {mod}"

    def test_no_domains_tennis(self):
        for mod in self._collect_imports():
            assert not mod.startswith("domains.tennis"), f"Forbidden import: {mod}"

    def test_no_src_except_loop_signal(self):
        for mod in self._collect_imports():
            if mod.startswith("src."):
                assert mod == "src.loop.signal", (
                    f"Forbidden src import: {mod} (only src.loop.signal allowed)"
                )

    def test_no_domains_mlb_config(self):
        for mod in self._collect_imports():
            assert mod != "domains.mlb.config", (
                "Forbidden import: domains.mlb.config (signals are pure ctx.extra logic)"
            )

    def test_soccer_string_absent(self):
        source = self.SIGNALS_FILE.read_text(encoding="utf-8")
        assert "soccer" not in source.lower(), (
            "String 'soccer' found in domains/mlb/signals.py"
        )

    def test_tennis_string_absent(self):
        source = self.SIGNALS_FILE.read_text(encoding="utf-8")
        assert "tennis" not in source.lower(), (
            "String 'tennis' found in domains/mlb/signals.py"
        )
