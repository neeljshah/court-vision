"""tests/platform/test_ingame_scoreboard.py -- per-file test for the in-game scoreboard.

Covers scripts/platformkit/ingame_scoreboard:
  * build() returns one row per sport; each row is either a measured metric row (sport /
    checkpoint / n / metric / conditional / static / delta / verdict) with FINITE numbers, or a
    graceful `status` row carrying a note -- never a crash, never a fabricated number;
  * with the committed fixture corpus (PROOF_CORPUS_ROOT=tests/fixtures/proof) at least one
    sport produces a real metric row;
  * it DEGRADES gracefully when corpora are missing: every row gets a `status`, _all_non_ok
    detects the all-failed case, and the _NO_CORPUS_BANNER is shown;
  * render_markdown() consumes either row shape without raising.

HONEST framing: in-game conditioning on the realized state is sharper than the static pregame
line by construction -- a live book sees the same state, so this is forecaster QUALITY, not a $
edge. We assert shape + finiteness + graceful degradation, never a $/ROI claim.

OFFLINE: no network, no torch. INVARIANTS: ASCII-only; per-file test only.
Run: python -m pytest tests/platform/test_ingame_scoreboard.py -q
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from scripts.platformkit import ingame_scoreboard as mod

_REPO = Path(mod.__file__).resolve().parents[2]
_FIX_ROOT = _REPO / "tests" / "fixtures" / "proof"
_OK_KEYS = ("sport", "checkpoint", "n", "metric", "conditional", "static", "delta", "verdict")


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _has_all_fixtures() -> bool:
    return all((_FIX_ROOT / s).is_dir() for s in ("nba", "mlb", "soccer", "tennis"))


class TestBuildSchema:
    def test_build_returns_rows_with_expected_shape(self, monkeypatch):
        if _has_all_fixtures():
            monkeypatch.setenv("PROOF_CORPUS_ROOT", str(_FIX_ROOT))
        rows = mod.build()
        assert isinstance(rows, list) and len(rows) == len(mod._ROWS)
        sports = {r.get("sport") for r in rows}
        assert "NBA" in sports
        for r in rows:
            assert isinstance(r, dict) and "sport" in r
            if r.get("status"):
                # degraded row: must explain itself, never carry a fabricated metric
                assert isinstance(r["status"], str) and r["status"]
            else:
                for k in _OK_KEYS:
                    assert k in r, f"missing key {k} in ok row: {r}"
                assert _finite(r["conditional"]) and _finite(r["static"])
                assert _finite(r["delta"])
                assert r["verdict"] in ("WIN", "no-improvement")
                assert abs(r["delta"] - round(r["conditional"] - r["static"], 4)) < 1e-6

    def test_at_least_one_ok_row_on_fixtures(self, monkeypatch):
        if not _has_all_fixtures():
            pytest.skip(f"fixture corpus incomplete under {_FIX_ROOT}")
        monkeypatch.setenv("PROOF_CORPUS_ROOT", str(_FIX_ROOT))
        rows = mod.build()
        ok_rows = [r for r in rows if not r.get("status")]
        assert ok_rows, f"expected >=1 metric row on the fixture corpus, got {rows}"
        # No retracted/edge numbers leak into any why text.
        blob = " ".join(str(r.get("why", "")) for r in rows).lower()
        for bad in ("18.38", "54.57", "8.94", "78.11"):
            assert bad not in blob


class TestRenderMarkdown:
    def test_render_markdown_table_header_and_honesty(self, monkeypatch):
        if _has_all_fixtures():
            monkeypatch.setenv("PROOF_CORPUS_ROOT", str(_FIX_ROOT))
        md = mod.render_markdown(mod.build())
        assert isinstance(md, str)
        assert "In-Game Scoreboard" in md
        assert "| Sport | Checkpoint |" in md
        assert "not a $ edge" in md


class TestGracefulDegradation:
    def test_missing_corpus_yields_status_rows_not_crash(self, monkeypatch, tmp_path):
        for s in ("nba", "mlb", "soccer", "tennis"):
            (tmp_path / s).mkdir(parents=True)
        monkeypatch.setenv("PROOF_CORPUS_ROOT", str(tmp_path))
        rows = mod.build()
        assert isinstance(rows, list) and len(rows) == len(mod._ROWS)
        for r in rows:
            assert r.get("status"), f"expected a degraded status row, got {r}"
            assert "conditional" not in r or not _finite(r.get("conditional"))
        # every row failed to measure -> the all-non-ok detector fires, banner is defined
        assert mod._all_non_ok(rows) is True
        assert "CORPUS NOT PRESENT" in mod._NO_CORPUS_BANNER
        # render still succeeds on the all-degraded table
        md = mod.render_markdown(rows)
        assert isinstance(md, str) and "no_data" in md or "| NBA |" in md

    def test_all_non_ok_detector(self):
        assert mod._all_non_ok([{"sport": "NBA", "status": "error"},
                                {"sport": "MLB", "status": "pending"}]) is True
        assert mod._all_non_ok([{"sport": "NBA", "conditional": 0.16, "static": 0.24,
                                 "delta": -0.08, "verdict": "WIN"},
                                {"sport": "MLB", "status": "error"}]) is False
        assert mod._all_non_ok([]) is False
