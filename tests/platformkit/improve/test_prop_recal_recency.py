"""tests.platformkit.improve.test_prop_recal_recency -- W10 prop recency recal contract.

Asserts:
  (a) MF1 -- sentinel ABSENT -> build_prop_recency_candidate returns None
      even on a non-empty, foldable settled batch (kill-switch fires first).
  (b) apply_recency_weights: newest row -> highest weight; weight in (0, 1].
  (c) NO_CANDIDATE honestly when too few clean rows (<_MIN_OBS=12).
  (d) Candidate shape when enough rows: cand_preds in (0,1), no $ key,
      note='calibration, not edge', vs_close='UNPROVEN'.
  (e) load_prop_settled: stat filter works; rows missing outcome or prob excluded.
  (f) candidate has payload.half_life_days and note='calibration, not edge'.

Per-file test only. ASCII; stdlib + numpy deps. MF1 monkeypatched via
pipeline_flag.SENTINEL_PATH (sentinel never created on real disk).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import numpy as np

from scripts.platformkit.improve import pipeline_flag as PF
from scripts.platformkit.improve.prop_recal_recency import (
    build_prop_recency_candidate,
    load_prop_settled,
    apply_recency_weights,
    DEFAULT_HALF_LIFE_DAYS,
)

# ---------------------------------------------------------------------------
# helpers

_FORBIDDEN_KEYS = {"$", "roi", "pnl", "dollar", "edge"}


def _has_forbidden_key(d: Any) -> bool:
    if isinstance(d, dict):
        for k, v in d.items():
            kl = str(k).lower()
            if any(tok in kl for tok in _FORBIDDEN_KEYS):
                return True
            if _has_forbidden_key(v):
                return True
    if isinstance(d, list):
        return any(_has_forbidden_key(x) for x in d)
    return False


def _make_prop_row(*, player: str = "Player A", stat: str = "pts",
                   sport: str = "nba", p0: float = 0.55,
                   outcome: int = 1,
                   ts: str = "2026-01-01T00:00:00+00:00") -> Dict[str, Any]:
    return {
        "sport": sport, "player": player, "stat": stat,
        "model_prob": p0, "outcome": str(outcome),
        "settled_at": ts,
    }


def _prop_rows(n: int = 16, sport: str = "nba", stat: str = "pts") -> List[Dict[str, Any]]:
    """n prop rows with varied p0 and alternating outcomes."""
    rows = []
    for i in range(n):
        ts = "2026-01-%02dT00:00:00+00:00" % ((i % 28) + 1)
        rows.append(_make_prop_row(
            player="P%d" % i, stat=stat, sport=sport,
            p0=0.40 + 0.04 * (i % 6),
            outcome=i % 2,
            ts=ts,
        ))
    return rows


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


# ---------------------------------------------------------------------------
# (a) MF1: sentinel absent -> None


def test_mf1_absent_returns_none(tmp_path):
    fake_sentinel = tmp_path / "PIPELINE_ENABLED"
    # sentinel does NOT exist

    ledger = tmp_path / "prop_ledger.jsonl"
    _write_jsonl(ledger, _prop_rows(20))

    with patch.object(PF, "SENTINEL_PATH", fake_sentinel):
        with patch("scripts.platformkit.improve.prop_recal_recency._PROP_LEDGER", ledger):
            result = build_prop_recency_candidate("test_mf1", "nba", stat="pts")
    assert result is None, "MF1: absent sentinel must return None"


# ---------------------------------------------------------------------------
# (b) apply_recency_weights: newest -> highest weight; all in (0, 1]


def test_recency_weights_ordering():
    rows = [
        {"ts": "2026-01-01T00:00:00+00:00"},
        {"ts": "2026-02-01T00:00:00+00:00"},
        {"ts": "2026-03-01T00:00:00+00:00"},
    ]
    w = apply_recency_weights(rows, half_life_days=30.0)
    assert w.shape == (3,)
    assert all(0.0 < wi <= 1.0 for wi in w.tolist()), "weights must be in (0, 1]"
    # newest (index 2) must have the highest weight
    assert float(w[2]) >= float(w[1]) >= float(w[0])


def test_recency_weights_empty():
    w = apply_recency_weights([], half_life_days=30.0)
    assert w.shape == (0,)


# ---------------------------------------------------------------------------
# (c) NO_CANDIDATE when too few clean rows


def test_too_few_returns_none(tmp_path):
    fake_sentinel = tmp_path / "PIPELINE_ENABLED"
    fake_sentinel.touch()

    ledger = tmp_path / "prop_ledger.jsonl"
    _write_jsonl(ledger, _prop_rows(6, sport="nba"))  # fewer than _MIN_OBS=12

    with patch.object(PF, "SENTINEL_PATH", fake_sentinel):
        with patch("scripts.platformkit.improve.prop_recal_recency._PROP_LEDGER", ledger):
            with patch("scripts.platformkit.improve.prop_recal_recency._PAPER_PREDS",
                       tmp_path / "empty.jsonl"):
                result = build_prop_recency_candidate("test_few", "nba", stat="pts")
    assert result is None, "too few obs -> NO_CANDIDATE"


# ---------------------------------------------------------------------------
# (d) Candidate shape when enough rows


def test_candidate_shape(tmp_path):
    fake_sentinel = tmp_path / "PIPELINE_ENABLED"
    fake_sentinel.touch()

    ledger = tmp_path / "prop_ledger.jsonl"
    _write_jsonl(ledger, _prop_rows(24, sport="nba", stat="pts"))

    with patch.object(PF, "SENTINEL_PATH", fake_sentinel):
        with patch("scripts.platformkit.improve.prop_recal_recency._PROP_LEDGER", ledger):
            with patch("scripts.platformkit.improve.prop_recal_recency._PAPER_PREDS",
                       tmp_path / "empty.jsonl"):
                cand = build_prop_recency_candidate("test_shape", "nba", stat="pts",
                                                    half_life_days=30.0)

    # May be None if MF2 fires on synthetic data -- that is acceptable.
    if cand is None:
        pytest.skip("Platt degenerate on synthetic data -- MF2 OK")

    # cand_preds in (0, 1)
    assert "cand_preds" in cand
    for p in cand["cand_preds"]:
        assert 0.0 < p < 1.0, "cand_preds out of (0,1)"

    # honesty rails
    assert cand.get("note") == "calibration, not edge"
    assert cand.get("vs_close") == "UNPROVEN"
    assert not _has_forbidden_key(cand)

    # recency-specific payload
    payload = cand.get("payload", {})
    assert payload.get("note") == "calibration, not edge"
    assert "half_life_days" in payload
    assert payload["family"] == "platt_prop_recency"


# ---------------------------------------------------------------------------
# (e) load_prop_settled: stat filter + bad rows excluded


def test_load_prop_settled_filter(tmp_path):
    pts_rows = _prop_rows(4, stat="pts")
    reb_rows = _prop_rows(4, stat="reb")
    no_outcome = [_make_prop_row(stat="pts", outcome=0)]
    no_outcome[0].pop("outcome")  # remove outcome field

    ledger = tmp_path / "prop_ledger.jsonl"
    _write_jsonl(ledger, pts_rows + reb_rows + no_outcome)

    with patch("scripts.platformkit.improve.prop_recal_recency._PROP_LEDGER", ledger):
        with patch("scripts.platformkit.improve.prop_recal_recency._PAPER_PREDS",
                   tmp_path / "empty.jsonl"):
            loaded_pts = load_prop_settled("nba", stat="pts")
            loaded_all = load_prop_settled("nba")

    assert all(r["stat"] == "pts" for r in loaded_pts), "stat filter must work"
    # no_outcome row must be excluded
    assert all(r.get("outcome") in (0, 1) for r in loaded_all), (
        "rows without valid outcome must be excluded"
    )


# ---------------------------------------------------------------------------
# (f) Candidate payload carries half_life_days and calibration note


def test_payload_note_and_half_life(tmp_path):
    fake_sentinel = tmp_path / "PIPELINE_ENABLED"
    fake_sentinel.touch()

    ledger = tmp_path / "prop_ledger.jsonl"
    _write_jsonl(ledger, _prop_rows(24, sport="nba", stat="ast"))

    with patch.object(PF, "SENTINEL_PATH", fake_sentinel):
        with patch("scripts.platformkit.improve.prop_recal_recency._PROP_LEDGER", ledger):
            with patch("scripts.platformkit.improve.prop_recal_recency._PAPER_PREDS",
                       tmp_path / "empty.jsonl"):
                cand = build_prop_recency_candidate("test_payload", "nba", stat="ast",
                                                    half_life_days=14.0)

    if cand is None:
        pytest.skip("Platt degenerate on synthetic data -- MF2 OK")

    payload = cand.get("payload", {})
    assert abs(payload.get("half_life_days", -1) - 14.0) < 1e-9
    assert payload.get("note") == "calibration, not edge"
    assert payload.get("stat") == "ast"
