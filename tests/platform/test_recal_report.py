"""tests/platform/test_recal_report.py — Tests for scripts/platformkit/recal_report.py.

CALIBRATION != EDGE.  Tests a RELIABILITY report only.  No edge claims permitted.

Categories:
1. build_report returns raw + recal_ece per sport with required keys.
2. recal_ece <= raw_ece for a miscalibrated input.
3. format_report contains the honesty note.
4. No edge-claim language in output.
5. live_path always False.
6. Absent corpus produces SKIP row; appears in formatted output.
7. Soccer standalone note present.
8. Real-corpus tests (skip when absent).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.recal_report import SPORTS, build_report, format_report  # noqa: E402
from scripts.platformkit.recalibration import measure_recal  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORBIDDEN = [
    "has an edge", "profitable strategy", "guaranteed profit",
    "positive roi", "guaranteed return", "beats the market",
]

_DATA_FILES = {
    "tennis": _REPO_ROOT / "data" / "domains" / "tennis" / "matches.parquet",
    "mlb":    _REPO_ROOT / "data" / "domains" / "mlb" / "games.parquet",
    "soccer": _REPO_ROOT / "data" / "domains" / "soccer" / "matches.parquet",
}


def _no_edge(text: str) -> None:
    lo = text.lower()
    for phrase in _FORBIDDEN:
        assert phrase not in lo, f"Edge-claim '{phrase}' in: {text[:200]}"


def _corpus_available(sport: str) -> bool:
    p = _DATA_FILES.get(sport)
    return p is not None and p.exists()


def _fake(sport: str, raw: float, rec: float, n: int = 400) -> dict:
    """Build a dict that mirrors measure_sport_recal output."""
    return {
        "sport": sport, "n": n,
        "raw_ece": raw, "recal_ece": rec, "delta": raw - rec,
        "note": "calibration != edge: better-calibrated probabilities do NOT imply "
                "beating the market close or a positive expected value",
    }


def _fake_all() -> dict:
    return {
        "tennis": _fake("tennis", 0.04,  0.035),
        "mlb":    _fake("mlb",    0.007, 0.006),
        "soccer": _fake("soccer", 0.107, 0.008),
    }


def _build_with_fakes(sports=None):
    fakes = _fake_all()
    with patch(
        "scripts.platformkit.recal_report.measure_sport_recal",
        side_effect=lambda sport, **_kw: fakes[sport],
    ):
        return build_report(sports=sports)


# ---------------------------------------------------------------------------
# 1. build_report returns required keys per sport
# ---------------------------------------------------------------------------

def test_build_report_returns_three_rows() -> None:
    rows = _build_with_fakes()
    assert len(rows) == 3


def test_build_report_required_keys() -> None:
    rows = _build_with_fakes()
    required = {"sport", "n", "raw_ece", "recal_ece", "delta",
                "live_path", "note", "skipped", "error"}
    for row in rows:
        assert required <= row.keys(), (
            f"{row.get('sport')}: missing keys {required - row.keys()}"
        )


def test_build_report_finite_eces() -> None:
    for row in _build_with_fakes():
        assert np.isfinite(float(row["raw_ece"]))
        assert np.isfinite(float(row["recal_ece"]))


# ---------------------------------------------------------------------------
# 2. recal_ece <= raw_ece for miscalibrated input
# ---------------------------------------------------------------------------

def test_recal_ece_le_raw_ece_miscalibrated_direct() -> None:
    """measure_recal on severely miscalibrated data: recal_ece must not exceed raw_ece."""
    rng = np.random.default_rng(0)
    probs = rng.uniform(0.8, 1.0, 600)
    outcomes = np.zeros(600)
    r = measure_recal(probs, outcomes, min_history=30)
    assert r["recal_ece"] <= r["raw_ece"] + 1e-9


def test_build_report_delta_positive_miscalibrated() -> None:
    fake = _fake("soccer", raw=0.107, rec=0.008)
    with patch("scripts.platformkit.recal_report.measure_sport_recal",
               return_value=fake):
        rows = build_report(sports=["soccer"])
    assert float(rows[0]["delta"]) > 0


# ---------------------------------------------------------------------------
# 3. format_report contains honesty note
# ---------------------------------------------------------------------------

def test_format_report_honesty_note_present() -> None:
    report = format_report(_build_with_fakes())
    lo = report.lower()
    assert "calibration != edge" in lo or "calibration != edge" in report
    assert "no edge claimed" in lo
    assert "not in the live prediction path" in lo


# ---------------------------------------------------------------------------
# 4. No edge-claim language
# ---------------------------------------------------------------------------

def test_format_report_no_edge_claims() -> None:
    _no_edge(format_report(_build_with_fakes()))


def test_rows_note_no_edge_claims() -> None:
    for row in _build_with_fakes():
        _no_edge(str(row.get("note", "")))


# ---------------------------------------------------------------------------
# 5. live_path always False
# ---------------------------------------------------------------------------

def test_live_path_always_false() -> None:
    for row in _build_with_fakes():
        assert row["live_path"] is False, (
            f"{row['sport']}: live_path must be False"
        )


# ---------------------------------------------------------------------------
# 6. Absent corpus → SKIP row; appears in formatted output
# ---------------------------------------------------------------------------

def _absent_result(sport: str) -> dict:
    return {
        "sport": sport, "n": 0,
        "raw_ece": float("nan"), "recal_ece": float("nan"),
        "delta": float("nan"),
        "error": "Corpus absent: no such file",
        "note": "calibration != edge",
    }


def test_absent_corpus_skipped_true() -> None:
    with patch("scripts.platformkit.recal_report.measure_sport_recal",
               return_value=_absent_result("soccer")):
        rows = build_report(sports=["soccer"])
    assert rows[0]["skipped"] is True
    assert rows[0]["n"] == 0


def test_skip_row_appears_in_report() -> None:
    with patch("scripts.platformkit.recal_report.measure_sport_recal",
               return_value=_absent_result("soccer")):
        rows = build_report(sports=["soccer"])
    assert "SKIP" in format_report(rows)


# ---------------------------------------------------------------------------
# 7. Soccer standalone note present in formatted output
# ---------------------------------------------------------------------------

def test_format_report_soccer_standalone_note() -> None:
    report = format_report(_build_with_fakes())
    lo = report.lower()
    assert "standalone" in lo or "not wired" in lo, (
        "Report must note soccer recalibration is standalone / not wired"
    )


# ---------------------------------------------------------------------------
# 8. Real-corpus tests — skip when absent (CI-safe)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sport", SPORTS)
def test_real_corpus_finite_eces(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    rows = build_report(sports=[sport])
    row = rows[0]
    assert not row["skipped"], f"Unexpected skip: {row['error']}"
    assert np.isfinite(float(row["raw_ece"])) and float(row["raw_ece"]) >= 0
    assert np.isfinite(float(row["recal_ece"])) and float(row["recal_ece"]) >= 0


@pytest.mark.parametrize("sport", SPORTS)
def test_real_corpus_no_edge_claims(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    _no_edge(format_report(build_report(sports=[sport])))


@pytest.mark.parametrize("sport", SPORTS)
def test_real_corpus_recal_le_raw(sport: str) -> None:
    if not _corpus_available(sport):
        pytest.skip(f"{sport} corpus absent")
    row = build_report(sports=[sport])[0]
    if sport == "soccer":
        assert float(row["recal_ece"]) < float(row["raw_ece"]), (
            f"soccer recal_ece={row['recal_ece']:.4f} not < raw_ece={row['raw_ece']:.4f}"
        )
    else:
        assert float(row["delta"]) >= -0.01, (
            f"{sport}: delta={float(row['delta']):.4f} below tolerance"
        )
