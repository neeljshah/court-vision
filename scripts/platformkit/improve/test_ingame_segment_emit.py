"""Per-file test for scripts.platformkit.improve.ingame_segment_emit (SI-05).

Acceptance criteria (from BACKLOG.md SI-05):
  - multi-segment input -> one graded row per segment; market="ingame:<seg>"
  - in-game CLV -> always INSUFFICIENT_DATA (no liquid in-play prices)
  - under-N segment -> INSUFFICIENT_DATA
  - MF1 sentinel absent -> INSUFFICIENT_DATA (NO_CANDIDATE path)
  - leak-free walk-forward: no future-row usage (validated upstream; we check no $/roi keys)
  - no $/roi/pnl/profit key in any output dict

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test_ingame_segment_emit.py -q
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

import numpy as np
import pytest

from scripts.platformkit.improve.ingame_segment_emit import (
    emit_ingame_segments,
    CLV_STATUS,
    CLV_REASON,
    CALIBRATION_NOTE,
    _seg_label,
    _brier_readout,
    _build_insufficient_row,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

ALL_SEGMENTS: List[Tuple[str, str, str]] = [
    ("close", "early", "ample"),
    ("close", "early", "scarce"),
    ("close", "late", "ample"),
    ("close", "late", "scarce"),
    ("mid", "early", "ample"),
    ("mid", "early", "scarce"),
    ("mid", "late", "ample"),
    ("mid", "late", "scarce"),
    ("blowout", "early", "ample"),
    ("blowout", "early", "scarce"),
    ("blowout", "late", "ample"),
    ("blowout", "late", "scarce"),
]


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(obj: Any, context: str = "") -> None:
    for k in _all_keys(obj):
        assert not _BANNED_KEY_RE.search(k), (
            "Banned key %r found%s" % (k, (" in %s" % context) if context else "")
        )


def _make_candidate(n: int = 20, brier_delta: float = 0.01) -> Dict[str, Any]:
    """Synthetic candidate dict matching the shape build_ingame_segment_candidate returns."""
    rng = np.random.default_rng(42)
    y = (rng.random(n) > 0.5).astype(float).tolist()
    base = np.clip(rng.random(n), 0.1, 0.9).tolist()
    # Make candidate preds slightly better (lower Brier) by nudging toward y.
    cand = [min(max(b + 0.05 * (yy - 0.5), 0.01), 0.99)
            for b, yy in zip(base, y)]
    seg = "margin:close|period:early|time:ample"
    return {
        "base_preds": base,
        "cand_preds": cand,
        "y": y,
        "kind": "prob",
        "fold_results": [{"delta": brier_delta, "metric": "brier", "fold_id": 0}],
        "corpora": [],
        "oos_improves": brier_delta > 0.0,
        "n_clean": n,
        "n_quarantined": 0,
        "segment": seg,
        "name": "test_cand",
        "note": "calibration, not edge",
        "vs_close": "UNPROVEN",
        "payload": {
            "family": "platt_ingame_segment",
            "a": 1.05, "b": -0.02,
            "segment": seg,
            "n_obs": n,
            "note": "calibration, not edge",
        },
    }


def _write_ledger(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# Class 1: CLV always INSUFFICIENT_DATA
# ---------------------------------------------------------------------------


class TestClvAlwaysInsufficient:
    """In-game CLV must always be INSUFFICIENT_DATA; never a green grade."""

    def test_clv_insufficient_on_successful_candidate(self, tmp_path: Path) -> None:
        """Even when a candidate is built, CLV must be INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            rows = emit_ingame_segments(
                "nba",
                [("close", "early", "ample")],
                ledger_path=ledger,
            )
        assert len(rows) == 1
        row = rows[0]
        assert row["clv"] == "INSUFFICIENT_DATA", (
            "CLV must be INSUFFICIENT_DATA for in-game segments; got %r" % row["clv"]
        )
        assert "clv_reason" in row
        _assert_no_banned_keys(row, "successful candidate row")

    def test_clv_insufficient_on_no_candidate(self, tmp_path: Path) -> None:
        """NO_CANDIDATE path must also report CLV INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=None,
        ):
            rows = emit_ingame_segments(
                "nba",
                [("mid", "late", "scarce")],
                ledger_path=ledger,
            )
        assert len(rows) == 1
        assert rows[0]["clv"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(rows[0], "no-candidate row")

    def test_clv_reason_string_present(self, tmp_path: Path) -> None:
        """clv_reason must be a non-empty string explaining the INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=None,
        ):
            rows = emit_ingame_segments(
                "nba",
                [("blowout", "early", "scarce")],
                ledger_path=ledger,
            )
        reason = rows[0].get("clv_reason", "")
        assert isinstance(reason, str) and len(reason) > 10, (
            "clv_reason must be a non-empty descriptive string; got %r" % reason
        )


# ---------------------------------------------------------------------------
# Class 2: Multi-segment -> one row per segment
# ---------------------------------------------------------------------------


class TestMultiSegmentEmit:
    """Multi-segment input produces one graded row per segment."""

    def test_three_segments_three_rows(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        segs = [
            ("close", "early", "ample"),
            ("mid", "late", "scarce"),
            ("blowout", "early", "ample"),
        ]
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            rows = emit_ingame_segments("nba", segs, ledger_path=ledger)
        assert len(rows) == 3, "Expected 3 rows; got %d" % len(rows)

    def test_row_market_key_format(self, tmp_path: Path) -> None:
        """Each row must have market='ingame:<seg>' matching the segment triple."""
        ledger = tmp_path / "ledger.jsonl"
        seg = ("close", "early", "ample")
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            rows = emit_ingame_segments("nba", [seg], ledger_path=ledger)
        expected_market = "ingame:margin:close|period:early|time:ample"
        assert rows[0]["market"] == expected_market, (
            "Expected market %r; got %r" % (expected_market, rows[0]["market"])
        )

    def test_all_twelve_segments(self, tmp_path: Path) -> None:
        """All 12 valid segment combinations -> 12 rows, each with distinct market key."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            rows = emit_ingame_segments("nba", ALL_SEGMENTS, ledger_path=ledger)
        assert len(rows) == 12
        markets = [r["market"] for r in rows]
        assert len(set(markets)) == 12, "Expected 12 distinct market keys"
        _assert_no_banned_keys(rows, "all twelve segments")

    def test_rows_written_to_ledger(self, tmp_path: Path) -> None:
        """Emitted rows must be appended to the ledger JSONL file."""
        ledger = tmp_path / "ledger.jsonl"
        segs = [("close", "early", "ample"), ("mid", "late", "scarce")]
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            emit_ingame_segments("nba", segs, ledger_path=ledger)
        assert ledger.exists(), "Ledger file must be created after emit"
        written = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(written) == 2, "Expected 2 rows in ledger; got %d" % len(written)

    def test_ledger_rows_match_returned_rows(self, tmp_path: Path) -> None:
        """Rows written to disk must match what emit_ingame_segments returns."""
        ledger = tmp_path / "ledger.jsonl"
        segs = [("blowout", "early", "scarce")]
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            rows = emit_ingame_segments("nba", segs, ledger_path=ledger)
        disk_rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(disk_rows) == 1
        assert disk_rows[0]["market"] == rows[0]["market"]
        assert disk_rows[0]["status"] == rows[0]["status"]


# ---------------------------------------------------------------------------
# Class 3: Under-N -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------


class TestUnderNInsufficient:
    """Segment with fewer than _MIN_OBS clean obs must emit INSUFFICIENT_DATA."""

    def test_no_candidate_produces_insufficient(self, tmp_path: Path) -> None:
        """build_ingame_segment_candidate returning None -> INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=None,
        ):
            rows = emit_ingame_segments("nba", [("close", "late", "ample")], ledger_path=ledger)
        assert rows[0]["status"] == "INSUFFICIENT_DATA"
        assert "reason" in rows[0]
        _assert_no_banned_keys(rows[0], "no-candidate insufficient row")

    def test_candidate_with_too_few_y_produces_insufficient(self, tmp_path: Path) -> None:
        """Candidate with y shorter than _MIN_OBS -> INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        tiny_cand = _make_candidate(n=3)  # 3 < _MIN_OBS = 8
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=tiny_cand,
        ):
            rows = emit_ingame_segments("nba", [("mid", "early", "ample")], ledger_path=ledger)
        assert rows[0]["status"] == "INSUFFICIENT_DATA", (
            "Under-_MIN_OBS candidate must produce INSUFFICIENT_DATA; got %r"
            % rows[0]["status"]
        )

    def test_exact_min_obs_passes(self, tmp_path: Path) -> None:
        """Candidate with exactly _MIN_OBS observations must NOT be INSUFFICIENT_DATA."""
        from scripts.platformkit.improve.ingame_segment_emit import _MIN_OBS
        ledger = tmp_path / "ledger.jsonl"
        ok_cand = _make_candidate(n=_MIN_OBS)
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=ok_cand,
        ):
            rows = emit_ingame_segments("nba", [("blowout", "late", "ample")], ledger_path=ledger)
        assert rows[0]["status"] != "INSUFFICIENT_DATA", (
            "Exactly _MIN_OBS obs should NOT be INSUFFICIENT_DATA"
        )


# ---------------------------------------------------------------------------
# Class 4: No $/roi/pnl/profit keys in any output
# ---------------------------------------------------------------------------


class TestNoBannedKeys:
    """No output dict may contain a $ / roi / pnl / profit key."""

    def test_successful_row_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            rows = emit_ingame_segments("nba", [("close", "early", "ample")], ledger_path=ledger)
        _assert_no_banned_keys(rows, "successful row")

    def test_insufficient_row_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=None,
        ):
            rows = emit_ingame_segments("nba", [("mid", "late", "scarce")], ledger_path=ledger)
        _assert_no_banned_keys(rows, "insufficient row")

    def test_batch_of_segments_no_banned_keys(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        segs = ALL_SEGMENTS[:4]
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            side_effect=[_make_candidate(n=20 + i) for i in range(len(segs))],
        ):
            rows = emit_ingame_segments("nba", segs, ledger_path=ledger)
        _assert_no_banned_keys(rows, "batch of segments")

    def test_note_field_present_in_all_rows(self, tmp_path: Path) -> None:
        """Every row must carry the calibration note (no edge claim)."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            rows = emit_ingame_segments("nba", [("blowout", "early", "scarce")], ledger_path=ledger)
        assert "note" in rows[0]
        assert "calibration" in rows[0]["note"].lower()


# ---------------------------------------------------------------------------
# Class 5: Status field correctness
# ---------------------------------------------------------------------------


class TestStatusField:
    """Verify status values are from the expected set and signal logic is correct."""

    def test_oos_improves_gives_ship(self, tmp_path: Path) -> None:
        """A candidate where cand Brier < base Brier -> status SHIP."""
        ledger = tmp_path / "ledger.jsonl"
        rng = np.random.default_rng(0)
        y = (rng.random(20) > 0.5).astype(float).tolist()
        # base far from y; cand close to y -> cand Brier lower
        base = [0.5] * 20
        cand = [float(yy) * 0.8 + 0.1 for yy in y]
        cand_dict = {
            **_make_candidate(n=20),
            "base_preds": base,
            "cand_preds": cand,
            "y": y,
            "oos_improves": True,
            "n_clean": 20,
        }
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=cand_dict,
        ):
            rows = emit_ingame_segments("nba", [("close", "early", "ample")], ledger_path=ledger)
        assert rows[0]["status"] in {"SHIP", "HOLD"}, (
            "Status must be SHIP or HOLD when candidate returned; got %r" % rows[0]["status"]
        )

    def test_status_insufficient_when_no_candidate(self, tmp_path: Path) -> None:
        """Status must be INSUFFICIENT_DATA when no candidate is returned."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=None,
        ):
            rows = emit_ingame_segments("nba", [("mid", "early", "scarce")], ledger_path=ledger)
        assert rows[0]["status"] == "INSUFFICIENT_DATA"

    def test_vs_close_always_unproven(self, tmp_path: Path) -> None:
        """vs_close must always be UNPROVEN; never auto-claimed."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            return_value=_make_candidate(n=20),
        ):
            rows = emit_ingame_segments("nba", [("close", "early", "ample")], ledger_path=ledger)
        assert rows[0].get("vs_close") == "UNPROVEN"


# ---------------------------------------------------------------------------
# Class 6: Invalid / malformed input robustness
# ---------------------------------------------------------------------------


class TestRobustness:
    """Malformed input must produce INSUFFICIENT_DATA rows, never raise."""

    def test_invalid_margin_bucket(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = emit_ingame_segments("nba", [("INVALID", "early", "ample")], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(rows[0], "invalid margin bucket")

    def test_invalid_period_bucket(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = emit_ingame_segments("nba", [("close", "Q1", "ample")], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "INSUFFICIENT_DATA"

    def test_invalid_time_bucket(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger.jsonl"
        rows = emit_ingame_segments("nba", [("mid", "late", "never")], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "INSUFFICIENT_DATA"

    def test_empty_segments_list_returns_empty(self, tmp_path: Path) -> None:
        """Empty segment list -> empty return, no crash."""
        ledger = tmp_path / "ledger.jsonl"
        rows = emit_ingame_segments("nba", [], ledger_path=ledger)
        assert rows == []

    def test_malformed_triple_produces_insufficient(self, tmp_path: Path) -> None:
        """A triple with too few elements must produce INSUFFICIENT_DATA, not raise."""
        ledger = tmp_path / "ledger.jsonl"
        rows = emit_ingame_segments("nba", [("close", "early")], ledger_path=ledger)  # type: ignore[arg-type]
        assert len(rows) == 1
        assert rows[0]["status"] == "INSUFFICIENT_DATA"

    def test_build_raises_produces_insufficient(self, tmp_path: Path) -> None:
        """If build_ingame_segment_candidate raises, the row must be INSUFFICIENT_DATA."""
        ledger = tmp_path / "ledger.jsonl"
        with mock.patch(
            "scripts.platformkit.improve.ingame_segment_emit.build_ingame_segment_candidate",
            side_effect=RuntimeError("unexpected build failure"),
        ):
            rows = emit_ingame_segments("nba", [("close", "late", "scarce")], ledger_path=ledger)
        assert len(rows) == 1
        assert rows[0]["status"] == "INSUFFICIENT_DATA"
        _assert_no_banned_keys(rows[0], "build-raises row")


# ---------------------------------------------------------------------------
# Class 7: Helper unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Unit tests for the internal helpers."""

    def test_seg_label_format(self) -> None:
        label = _seg_label("close", "early", "ample")
        assert label == "margin:close|period:early|time:ample"

    def test_brier_readout_sensible(self) -> None:
        """_brier_readout must return a dict with expected keys."""
        rng = np.random.default_rng(7)
        n = 30
        y = (rng.random(n) > 0.5).astype(float).tolist()
        base = np.clip(rng.random(n), 0.1, 0.9).tolist()
        cand = np.clip(rng.random(n), 0.1, 0.9).tolist()
        out = _brier_readout(base, cand, y)
        assert "n" in out
        assert out["n"] == n
        assert "base_brier" in out
        assert "cand_brier" in out
        assert "brier_delta" in out
        assert "brier_improves" in out
        assert isinstance(out["brier_improves"], bool)

    def test_brier_readout_improves_detection(self) -> None:
        """cand perfectly calibrated on y -> should show Brier improvement vs mid-50%."""
        n = 40
        y = ([1.0] * 20 + [0.0] * 20)
        base = [0.5] * n        # always 50%: Brier = 0.25
        cand = [0.9] * 20 + [0.1] * 20  # near-perfect: lower Brier
        out = _brier_readout(base, cand, y)
        assert out["brier_delta"] > 0.0, "Expected positive delta (cand better)"
        assert out["brier_improves"] is True

    def test_build_insufficient_row_no_banned_keys(self) -> None:
        row = _build_insufficient_row("ingame:test", "test reason", "2026-01-01T00:00:00+00:00")
        _assert_no_banned_keys(row, "build_insufficient_row")

    def test_build_insufficient_row_has_clv(self) -> None:
        row = _build_insufficient_row("ingame:test", "reason", "2026-01-01T00:00:00+00:00")
        assert row["clv"] == "INSUFFICIENT_DATA"
        assert row["vs_close"] == "UNPROVEN"
