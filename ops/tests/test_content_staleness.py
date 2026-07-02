"""ops.tests.test_content_staleness -- stuck-empty vs honest-empty soft signal.

Proves the conservative content-staleness signal:
  * NEVER flags an honest-empty surface (status != "ok") -- no false-red.
  * Flags ONLY an input-present-yet-empty surface (status == "ok") that has
    persisted past the grace window.
  * Is purely additive: it returns notes only and does NOT touch the supervisor
    liveness/readiness rollup.

Per-file run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest ops/tests/test_content_staleness.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ops import content_staleness as cs


def _write_surface(
    base: Path,
    sport: str,
    *,
    status: str,
    generated_at: Optional[str],
    predictions: int = 0,
    markets: int = 0,
) -> None:
    d = base / sport
    d.mkdir(parents=True, exist_ok=True)
    surface: Dict[str, Any] = {
        "sport": sport,
        "status": status,
        "predictions": [{"x": i} for i in range(predictions)],
        "markets": [{"y": i} for i in range(markets)],
    }
    if generated_at is not None:
        surface["generated_at"] = generated_at
    (d / "latest.json").write_text(json.dumps(surface), encoding="utf-8")


# A fixed "now" (a 2026 epoch) and an old generated_at far before it.
_NOW = 1_782_000_000.0              # ~2026-06-20 UTC
_OLD_ISO = "2000-01-01T00:00:00Z"   # far in the past -> age >> grace


class TestHonestEmptyNeverFlagged:
    """The core safety property: honest-empty must NEVER read DEGRADED."""

    def test_status_unavailable_empty_is_honest_not_stuck(self, tmp_path):
        """status=unavailable + empty (offseason NBA) -> honest_empty, NO note."""
        _write_surface(tmp_path, "nba", status="unavailable",
                       generated_at=_OLD_ISO, predictions=0, markets=0)
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path)
        assert out["stuck"] == []
        assert out["notes"] == []
        assert "nba" in out["honest_empty"]

    def test_status_unknown_empty_is_honest_not_stuck(self, tmp_path):
        """A surface with no status field + empty -> honest_empty, never stuck."""
        _write_surface(tmp_path, "tennis", status="",
                       generated_at=_OLD_ISO, predictions=0, markets=0)
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path)
        assert out["stuck"] == []
        assert out["notes"] == []
        assert "tennis" in out["honest_empty"]

    def test_real_world_offseason_snapshot_no_false_red(self, tmp_path):
        """Mirror today's real tree: nba/tennis unavailable-empty, mlb/soccer ok.
        Must yield ZERO stuck rows / notes (no false-red on the live stack)."""
        _write_surface(tmp_path, "nba", status="unavailable",
                       generated_at=_OLD_ISO, predictions=0, markets=0)
        _write_surface(tmp_path, "tennis", status="unavailable",
                       generated_at=_OLD_ISO, predictions=0, markets=0)
        _write_surface(tmp_path, "mlb", status="ok",
                       generated_at=_OLD_ISO, predictions=1, markets=2)
        _write_surface(tmp_path, "soccer", status="ok",
                       generated_at=_OLD_ISO, predictions=10, markets=22)
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path)
        assert out["stuck"] == []
        assert out["notes"] == []
        assert sorted(out["honest_empty"]) == ["nba", "tennis"]
        # all four were inspected
        assert sorted(out["checked"]) == ["mlb", "nba", "soccer", "tennis"]


class TestStuckEmptyIsFlagged:
    """status=ok + empty + persisted -> a DEGRADED-level note."""

    def test_ok_but_empty_and_old_is_stuck(self, tmp_path):
        """status=ok (input present) yet empty for > grace -> stuck note."""
        _write_surface(tmp_path, "mlb", status="ok",
                       generated_at=_OLD_ISO, predictions=0, markets=0)
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path)
        assert len(out["stuck"]) == 1
        assert out["stuck"][0]["sport"] == "mlb"
        assert any("mlb" in n for n in out["notes"])
        assert "DEGRADED" in out["notes"][0]

    def test_ok_but_empty_but_fresh_is_not_yet_stuck(self, tmp_path):
        """status=ok + empty but generated_at is RECENT -> within grace, NOT flagged.
        A single mid-write / between-cycle read must not trip a false note."""
        recent_iso = "2000-01-01T00:00:00Z"
        # now == surface time -> age 0 < grace -> not stuck
        _write_surface(tmp_path, "mlb", status="ok",
                       generated_at=recent_iso, predictions=0, markets=0)
        fresh_now = cs._parse_iso(recent_iso)  # age == 0
        out = cs.content_signals(now=fresh_now, surfaces_dir=tmp_path)
        assert out["stuck"] == []
        assert out["notes"] == []

    def test_grace_boundary(self, tmp_path):
        """age exactly == grace_sec triggers (>= grace), just under does not."""
        base_ts = cs._parse_iso(_OLD_ISO)
        _write_surface(tmp_path, "mlb", status="ok",
                       generated_at=_OLD_ISO, predictions=0, markets=0)
        grace = 100.0
        # age == grace -> stuck
        out_eq = cs.content_signals(now=base_ts + grace, surfaces_dir=tmp_path,
                                    grace_sec=grace)
        assert len(out_eq["stuck"]) == 1
        # age just under grace -> not stuck
        out_lt = cs.content_signals(now=base_ts + grace - 1.0, surfaces_dir=tmp_path,
                                    grace_sec=grace)
        assert out_lt["stuck"] == []


class TestHasOutputIsHealthy:
    """A surface with output is healthy regardless of status/age."""

    def test_ok_with_predictions_is_healthy(self, tmp_path):
        _write_surface(tmp_path, "soccer", status="ok",
                       generated_at=_OLD_ISO, predictions=5, markets=10)
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path)
        assert out["stuck"] == []
        assert out["honest_empty"] == []
        assert "soccer" in out["checked"]

    def test_markets_only_is_healthy(self, tmp_path):
        """Output counts if EITHER predictions OR markets is non-empty."""
        _write_surface(tmp_path, "soccer", status="ok",
                       generated_at=_OLD_ISO, predictions=0, markets=3)
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path)
        assert out["stuck"] == []


class TestRobustness:
    """Never raises; unreadable / missing surfaces make no claim."""

    def test_missing_dir_no_raise(self, tmp_path):
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path / "nope")
        assert out["stuck"] == []
        assert out["checked"] == []

    def test_corrupt_surface_makes_no_claim(self, tmp_path):
        d = tmp_path / "mlb"
        d.mkdir(parents=True, exist_ok=True)
        (d / "latest.json").write_text("{not json", encoding="utf-8")
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path)
        assert out["stuck"] == []
        assert "mlb" not in out["checked"]  # unreadable -> no claim

    def test_returns_expected_keys(self, tmp_path):
        out = cs.content_signals(now=_NOW, surfaces_dir=tmp_path)
        for k in ("checked", "stuck", "honest_empty", "notes"):
            assert k in out
