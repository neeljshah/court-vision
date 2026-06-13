"""test_self_forecast.py — Unit tests for self_forecast.py.
Covers: Brier vs hand value; well-calibrated/overconfident detection; JSONL
round-trip + dedup; graceful-empty; no edge-claim language.  No edge claimed.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research_harness.self_forecast import (  # noqa: E402
    ForecastStore, SelfForecast, auto_pre_register, grade,
)


# ---------------------------------------------------------------------------
# Stubs + helpers
# ---------------------------------------------------------------------------

@dataclass
class _Finding:
    sport: str; family: str; hypothesis: str; verdict: str  # noqa: E702


@dataclass
class _Belief:
    sport: str; family: str; posterior_mean: float  # noqa: E702


class _StubBeliefStore:
    def __init__(self, beliefs: List[_Belief]) -> None:
        self._beliefs = beliefs
    def all_beliefs(self) -> List[_Belief]:
        return self._beliefs


def _fc(p: float, family: str = "fam", hypothesis: str = "h",
        sport: str = "nba", dated: str = "2026-06-13") -> SelfForecast:
    return SelfForecast(sport=sport, family=family, hypothesis=hypothesis,
                        p_ship=p, dated=dated)


def _fd(verdict: str, family: str = "fam", hypothesis: str = "h",
        sport: str = "nba") -> _Finding:
    return _Finding(sport=sport, family=family, hypothesis=hypothesis, verdict=verdict)


def _many(p: float, N: int, verdict: str) -> tuple:
    fcs = [_fc(p, family=f"f{i}", hypothesis=f"h{i}") for i in range(N)]
    fds = [_fd(verdict, family=f"f{i}", hypothesis=f"h{i}") for i in range(N)]
    return fcs, fds


# ---------------------------------------------------------------------------
# 1. Brier score vs hand-calculated values
# ---------------------------------------------------------------------------

def test_brier_single_reject() -> None:
    """P=0.2, REJECT => (0.2)^2 = 0.04."""
    r = grade([_fc(0.2)], [_fd("REJECT")])
    assert r.n_graded == 1
    assert math.isclose(r.brier_score, 0.04, abs_tol=1e-9)


def test_brier_two_forecasts() -> None:
    """P=0.3 REJECT + P=0.7 SHIP => ((0.3)^2+(0.3)^2)/2 = 0.09."""
    fcs = [_fc(0.3, family="f1", hypothesis="h1"), _fc(0.7, family="f2", hypothesis="h2")]
    fds = [_fd("REJECT", family="f1", hypothesis="h1"),
           _fd("SHIP",   family="f2", hypothesis="h2")]
    r = grade(fcs, fds)
    assert r.n_graded == 2
    assert math.isclose(r.brier_score, 0.09, abs_tol=1e-9)


def test_brier_perfect_ship() -> None:
    assert math.isclose(grade([_fc(1.0)], [_fd("SHIP")]).brier_score, 0.0, abs_tol=1e-9)


def test_brier_worst_case() -> None:
    assert math.isclose(grade([_fc(1.0)], [_fd("REJECT")]).brier_score, 1.0, abs_tol=1e-9)


def test_brier_zero_p_all_reject_is_zero() -> None:
    fcs, fds = _many(0.0, 5, "REJECT")
    r = grade(fcs, fds)
    assert math.isclose(r.brier_score, 0.0, abs_tol=1e-9)
    assert r.is_well_calibrated and not r.is_overconfident


# ---------------------------------------------------------------------------
# 2. Well-calibrated: low P(ship) + all-REJECT (honest-market case)
# ---------------------------------------------------------------------------

def test_well_calibrated_at_boundary_gap() -> None:
    """P=0.05, osr=0.0, gap=0.05 => is_well_calibrated=True (boundary inclusive).
    Predicting ~0 on an all-REJECT slate is correctly calibrated."""
    fcs, fds = _many(0.05, 10, "REJECT")
    r = grade(fcs, fds)
    assert math.isclose(r.brier_score, 0.0025, abs_tol=1e-9)
    assert r.is_well_calibrated
    assert not r.is_overconfident
    assert r.observed_ship_rate == 0.0


def test_well_calibrated_threshold_with_one_ship() -> None:
    """mean_p=0.15, osr=0.10 (1 SHIP out of 10) => gap=0.05, well-calibrated."""
    fcs = [_fc(0.15, family=f"f{i}", hypothesis=f"h{i}") for i in range(10)]
    fds = ([_fd("SHIP", family="f0", hypothesis="h0")]
           + [_fd("REJECT", family=f"f{i}", hypothesis=f"h{i}") for i in range(1, 10)])
    assert grade(fcs, fds).is_well_calibrated


# ---------------------------------------------------------------------------
# 3. Overconfident: high P(ship) + all REJECT
# ---------------------------------------------------------------------------

def test_overconfident_high_p_all_reject() -> None:
    """P=0.9 + all REJECT => Brier=0.81, is_overconfident=True."""
    fcs, fds = _many(0.9, 6, "REJECT")
    r = grade(fcs, fds)
    assert math.isclose(r.brier_score, 0.81, abs_tol=1e-9)
    assert r.is_overconfident
    assert not r.is_well_calibrated
    assert r.observed_ship_rate == 0.0


def test_overconfident_at_gap_006() -> None:
    """mean_p=0.16, osr=0.10 => gap=0.06 => is_overconfident=True."""
    fcs = [_fc(0.16, family=f"f{i}", hypothesis=f"h{i}") for i in range(10)]
    fds = ([_fd("SHIP", family="f0", hypothesis="h0")]
           + [_fd("REJECT", family=f"f{i}", hypothesis=f"h{i}") for i in range(1, 10)])
    assert grade(fcs, fds).is_overconfident


# ---------------------------------------------------------------------------
# 4. JSONL round-trip + dedup
# ---------------------------------------------------------------------------

def test_jsonl_roundtrip(tmp_path: Path) -> None:
    store = ForecastStore(path=tmp_path / "f.jsonl")
    store.append(_fc(0.12, family="f1", hypothesis="h1"))
    store.append(_fc(0.08, family="f2", hypothesis="h2"))
    store2 = ForecastStore(path=tmp_path / "f.jsonl")
    fcs = {f.family: f for f in store2.all_forecasts()}
    assert math.isclose(fcs["f1"].p_ship, 0.12, abs_tol=1e-9)
    assert math.isclose(fcs["f2"].p_ship, 0.08, abs_tol=1e-9)


def test_dedup_same_key(tmp_path: Path) -> None:
    store = ForecastStore(path=tmp_path / "f.jsonl")
    fc = _fc(0.1, family="dup", hypothesis="dup_h")
    assert store.append(fc) is True
    assert store.append(fc) is False
    assert len(store.all_forecasts()) == 1
    lines = [l for l in (tmp_path / "f.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 1


def test_dedup_survives_reload(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    store = ForecastStore(path=path)
    fc = _fc(0.1, family="dup", hypothesis="dup_h")
    store.append(fc)
    assert ForecastStore(path=path).append(fc) is False
    assert len([l for l in path.read_text().splitlines() if l.strip()]) == 1


def test_different_hypothesis_both_written(tmp_path: Path) -> None:
    store = ForecastStore(path=tmp_path / "f.jsonl")
    store.append(SelfForecast("nba", "fam", "A", p_ship=0.1, dated="2026-06-13"))
    store.append(SelfForecast("nba", "fam", "B", p_ship=0.2, dated="2026-06-13"))
    assert len(store.all_forecasts()) == 2


def test_jsonl_raw_keys(tmp_path: Path) -> None:
    store = ForecastStore(path=tmp_path / "f.jsonl")
    store.append(_fc(0.05))
    row = json.loads((tmp_path / "f.jsonl").read_text().strip())
    for key in ("sport", "family", "hypothesis", "p_ship", "dated"):
        assert key in row


# ---------------------------------------------------------------------------
# 5. Graceful if no data
# ---------------------------------------------------------------------------

def test_grade_empty() -> None:
    r = grade([], [])
    assert r.n_graded == 0 and r.n_unresolved == 0 and math.isnan(r.brier_score)


def test_grade_no_verdicts_yet() -> None:
    fcs = [_fc(0.1, family=f"f{i}", hypothesis=f"h{i}") for i in range(3)]
    r = grade(fcs, [])
    assert r.n_graded == 0 and r.n_unresolved == 3 and math.isnan(r.brier_score)


def test_empty_store(tmp_path: Path) -> None:
    assert ForecastStore(path=tmp_path / "f.jsonl").all_forecasts() == []


# ---------------------------------------------------------------------------
# 6. No edge-claim language in notes
# ---------------------------------------------------------------------------

_FORBIDDEN = ["edge found", "betting edge", "outperform", "beat the market",
              "positive roi", "+roi", "alpha found"]


def _clean(note: str) -> bool:
    lo = note.lower()
    return not any(ph in lo for ph in _FORBIDDEN)


def test_well_calibrated_note_no_edge_claim() -> None:
    fcs, fds = _many(0.05, 5, "REJECT")
    r = grade(fcs, fds)
    assert _clean(r.note) and "No edge is claimed" in r.note


def test_overconfident_note_no_edge_claim() -> None:
    fcs, fds = _many(0.9, 4, "REJECT")
    assert _clean(grade(fcs, fds).note)


# ---------------------------------------------------------------------------
# 7. SelfForecast validation
# ---------------------------------------------------------------------------

def test_p_ship_out_of_range() -> None:
    with pytest.raises(ValueError, match="p_ship"):
        SelfForecast("nba", "f", "h", p_ship=1.1)
    with pytest.raises(ValueError, match="p_ship"):
        SelfForecast("nba", "f", "h", p_ship=-0.01)


def test_empty_hypothesis_raises() -> None:
    with pytest.raises(ValueError, match="hypothesis"):
        SelfForecast("nba", "f", "   ", p_ship=0.1)


def test_boundary_p_ship_ok() -> None:
    assert SelfForecast("nba", "f", "h", p_ship=0.0).p_ship == 0.0
    assert SelfForecast("nba", "f", "h", p_ship=1.0).p_ship == 1.0


# ---------------------------------------------------------------------------
# 8. Partial resolution + DEFER
# ---------------------------------------------------------------------------

def test_partial_resolution(tmp_path: Path) -> None:
    """3 forecasts; 2 resolved, 1 unresolved; Brier=0.01."""
    fcs = [_fc(0.1, family=f"f{i}", hypothesis=f"h{i}") for i in range(3)]
    fds = [_fd("REJECT", family="f0", hypothesis="h0"),
           _fd("REJECT", family="f1", hypothesis="h1")]
    r = grade(fcs, fds)
    assert r.n_graded == 2 and r.n_unresolved == 1
    assert math.isclose(r.brier_score, 0.01, abs_tol=1e-9)


def test_defer_is_non_ship() -> None:
    """DEFER => outcome=0; Brier = (0.5)^2 = 0.25."""
    r = grade([_fc(0.5)], [_fd("DEFER")])
    assert math.isclose(r.brier_score, 0.25, abs_tol=1e-9)
    assert r.observed_ship_rate == 0.0


# ---------------------------------------------------------------------------
# 9. auto_pre_register
# ---------------------------------------------------------------------------

def test_auto_pre_register_creates(tmp_path: Path) -> None:
    beliefs = [_Belief("nba", "fam_a", 0.11), _Belief("tennis", "fam_b", 0.09)]
    fc_store = ForecastStore(path=tmp_path / "f.jsonl")
    n = auto_pre_register(_StubBeliefStore(beliefs), fc_store, dated="2026-06-13")
    assert n == 2
    fcs = {f.family: f for f in fc_store.all_forecasts()}
    assert math.isclose(fcs["fam_a"].p_ship, 0.11, abs_tol=1e-9)
    assert math.isclose(fcs["fam_b"].p_ship, 0.09, abs_tol=1e-9)


def test_auto_pre_register_dedup(tmp_path: Path) -> None:
    beliefs = [_Belief("nba", "fam_a", 0.11)]
    fc_store = ForecastStore(path=tmp_path / "f.jsonl")
    n1 = auto_pre_register(_StubBeliefStore(beliefs), fc_store, dated="2026-06-13")
    n2 = auto_pre_register(_StubBeliefStore(beliefs), fc_store, dated="2026-06-13")
    assert n1 == 1 and n2 == 0
    assert len(fc_store.all_forecasts()) == 1
