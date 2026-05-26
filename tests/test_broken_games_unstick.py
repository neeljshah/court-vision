"""
test_broken_games_unstick.py — Regression tests for two bugs that crashed 4-6 games.

BUG A (games 0022301148, 0022301147, 0022301149, 0022301158):
  _summarize_possession raised TypeError when a buf entry had shot_clock_est=""
  instead of a float.  Fixed by adding _to_float() coercion before min().

BUG B (_resolved_name_dynamic — triage report):
  The triage report identified a missing-frame_idx arg for a method named
  `_resolved_name_dynamic` at line 2561.  That method does NOT exist in the
  current codebase (commit d7614a8e).  The only resolver method is
  `_resolve_team_names(self, game_id, color_labels)`, whose call site at line
  2651 passes exactly the required arguments.  Test 4 verifies this signature
  contract so any future rename or signature change is caught immediately.

  Games 0022301156 / 0022301161 may have crashed on a different error in a
  prior version that was already fixed before d7614a8e; their stuck-marker files
  should be cleared and reprocessed to confirm.
"""

from __future__ import annotations

import inspect
import sys
import os
import types

import pytest

# ---------------------------------------------------------------------------
# Module import (skip entire file cleanly if heavy deps are not installed)
# ---------------------------------------------------------------------------
UP = pytest.importorskip(
    "src.pipeline.unified_pipeline",
    reason="src.pipeline.unified_pipeline not importable (missing deps — skip on local dev)",
)
UnifiedPipeline = UP.UnifiedPipeline


# ---------------------------------------------------------------------------
# Helpers — build a minimal possession buffer row
# ---------------------------------------------------------------------------

def _make_buf_entry(shot_clock_est=24.0, **kwargs):
    """Return a minimal buf dict suitable for _summarize_possession."""
    base = {
        "frame":            0,
        "spacing":          0.0,
        "isolation":        0.0,
        "vtb":              0.0,
        "drive":            0,
        "shot_event":       False,
        "fast_break":       False,
        "poss_type":        "half_court",
        "play_type":        "half_court",
        "paint_touches":    0,
        "off_ball_distance": 0.0,
        "shot_clock_est":   shot_clock_est,
        "handler_zone":     None,
    }
    base.update(kwargs)
    return base


def _call_summarize(buf):
    """Call _summarize_possession with minimal required args (no real pipeline needed).

    _summarize_possession is a @staticmethod — no self parameter.
    Signature: (pid, team, start_f, end_f, buf, fps, ...)
    """
    return UnifiedPipeline._summarize_possession(
        pid=1,
        team="home",
        start_f=0,
        end_f=len(buf) - 1,
        buf=buf,
        fps=30.0,
        game_id="0000000000",
        lineup_id=0,
        transition_frames=None,
        offensive_rebound_poss=False,
    )


# ---------------------------------------------------------------------------
# BUG A Tests
# ---------------------------------------------------------------------------

class TestSummarizePossessionShotClockEst:
    """Regression tests for the shot_clock_est str/float TypeError (Bug A)."""

    def test_handles_empty_string_shot_clock_est(self):
        """Single buf entry with shot_clock_est='' must not raise TypeError.

        Before the fix, min() compared '' < float and raised:
          TypeError: '<' not supported between instances of 'str' and 'float'
        After the fix, '' is coerced to 24.0 (default) and no error is raised.
        """
        buf = [_make_buf_entry(shot_clock_est="")]
        result = _call_summarize(buf)
        assert isinstance(result, dict), "Expected a dict result"
        assert "min_shot_clock_est" in result, "min_shot_clock_est must be in output"
        # When all entries have "" the default 24.0 must be returned
        assert result["min_shot_clock_est"] == 24.0

    def test_handles_mixed_types(self):
        """Buffer with mix of '', None, 24, 0.0, 12.5 — min over numeric subset only."""
        buf = [
            _make_buf_entry(shot_clock_est=""),   # coerces to 24.0
            _make_buf_entry(shot_clock_est=None),  # coerces to 24.0
            _make_buf_entry(shot_clock_est=24),    # int → 24.0
            _make_buf_entry(shot_clock_est=0.0),   # valid float
            _make_buf_entry(shot_clock_est=12.5),  # valid float
        ]
        result = _call_summarize(buf)
        assert isinstance(result, dict)
        # Numeric values: 24.0, 24.0, 24.0, 0.0, 12.5 → min is 0.0
        assert result["min_shot_clock_est"] == pytest.approx(0.0, abs=0.1)

    def test_all_empty_returns_default_24(self):
        """When ALL buf entries have shot_clock_est='', result must be 24.0."""
        buf = [_make_buf_entry(shot_clock_est="") for _ in range(5)]
        result = _call_summarize(buf)
        assert isinstance(result, dict)
        assert result["min_shot_clock_est"] == pytest.approx(24.0, abs=0.1), (
            f"Expected 24.0 (default) but got {result['min_shot_clock_est']}"
        )


# ---------------------------------------------------------------------------
# BUG B Test — resolve_team_names signature contract
# ---------------------------------------------------------------------------

class TestResolverSignatureContract:
    """Verify the team-name resolver method signature matches its call site.

    The triage report named this `_resolved_name_dynamic`, but that method does
    not exist in commit d7614a8e.  The actual method is `_resolve_team_names`.
    This test pins its signature so a future rename/signature change fails loudly.
    """

    def test_resolve_team_names_signature_matches_callers(self):
        """_resolve_team_names must accept (self, game_id, color_labels).

        Call site in run() at line 2651:
            _team_map = self._resolve_team_names(self.game_id, _color_labels)
        That passes 2 positional args after self.  The method signature must
        have exactly those 2 required positional parameters.
        """
        assert hasattr(UnifiedPipeline, "_resolve_team_names"), (
            "_resolve_team_names not found on UnifiedPipeline — method was renamed "
            "or removed; update the call site in run() and this test accordingly."
        )
        sig = inspect.signature(UnifiedPipeline._resolve_team_names)
        params = [
            name
            for name, p in sig.parameters.items()
            if name != "self" and p.default is inspect.Parameter.empty
        ]
        assert len(params) == 2, (
            f"_resolve_team_names expected 2 required params (game_id, color_labels), "
            f"got {len(params)}: {params}"
        )
        assert params[0] == "game_id", (
            f"First param should be 'game_id', got '{params[0]}'"
        )
        assert params[1] == "color_labels", (
            f"Second param should be 'color_labels', got '{params[1]}'"
        )
