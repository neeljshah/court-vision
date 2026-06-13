"""tests.platform.test_gap_observer — GapObserver unit tests (synthetic inputs only).

No real corpora, ledger files, or belief stores loaded.  Asserts: deterministic
ordering; higher uncertainty/gap → higher rank; REJECT families rank lower;
honest framing (no edge-claim language, HONEST_PREAMBLE present); empty inputs ok.
"""
from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import pytest

from scripts.research_harness.gap_observer import (
    HONEST_PREAMBLE,
    format_gaps,
    rank_gaps,
)


# --- Synthetic stubs --------------------------------------------------------

@dataclass
class _FakeCandidate:
    sport: str
    name: str

@dataclass
class _FakeCoverageResult:
    sport: str
    candidates: List[_FakeCandidate] = field(default_factory=list)
    tested_set: Set[str] = field(default_factory=set)

    @property
    def n_enumerated(self) -> int:
        return len(self.candidates)

    @property
    def n_tested(self) -> int:
        return len(self.tested_set)

@dataclass
class _FakeFinding:
    sport: str
    family: str
    verdict: str
    dated: str = "2026-01-01"
    hypothesis: str = "synthetic"
    evidence: dict = field(default_factory=dict)

class _FakeBeliefStore:
    def __init__(self, ci_map: Optional[Dict] = None) -> None:
        self._ci = ci_map or {}
        self._default = (0.003, 0.408)

    def credible_interval(self, sport: str, family: str) -> Tuple[float, float]:
        return self._ci.get((sport, family), self._default)


# --- Helper -----------------------------------------------------------------

def _make_enum(sport: str, n_total: int, n_tested: int, prefix: str = "c") -> dict:
    cands = [_FakeCandidate(sport=sport, name=f"{prefix}_{i}") for i in range(n_total)]
    tested = {c.name for c in cands[:n_tested]}
    cr = _FakeCoverageResult(sport=sport, candidates=cands, tested_set=tested)
    return {sport: cr}

# --- Edge cases / empty inputs ----------------------------------------------

def test_empty_inputs_returns_empty() -> None:
    assert rank_gaps() == []

def test_empty_dicts_returns_empty() -> None:
    assert rank_gaps(enumerator_results={}, findings=[], belief_store=None) == []

def test_all_tested_shows_only_ledger_families() -> None:
    enum = _make_enum("tennis", n_total=5, n_tested=5, prefix="t")
    findings = [_FakeFinding(sport="tennis", family="ledger_only", verdict="REJECT")]
    result = rank_gaps(enumerator_results=enum, findings=findings)
    families = [g.family for g in result]
    assert "ledger_only" in families
    for i in range(5):
        assert f"t_{i}" not in families

def test_no_crash_belief_store_none() -> None:
    enum = _make_enum("soccer", n_total=3, n_tested=1, prefix="s")
    result = rank_gaps(enumerator_results=enum, belief_store=None)
    assert len(result) == 2

# --- Determinism ------------------------------------------------------------

def test_ranking_is_deterministic() -> None:
    enum = _make_enum("mlb", n_total=10, n_tested=3, prefix="m")
    findings = [_FakeFinding(sport="mlb", family="m_5", verdict="REJECT")]
    r1 = [g.family for g in rank_gaps(enumerator_results=enum, findings=findings)]
    r2 = [g.family for g in rank_gaps(enumerator_results=enum, findings=findings)]
    assert r1 == r2

# --- Higher uncertainty → higher rank ---------------------------------------

def test_higher_ci_width_ranks_higher() -> None:
    enum = {
        "tennis": _FakeCoverageResult(
            sport="tennis",
            candidates=[
                _FakeCandidate(sport="tennis", name="fam_wide"),
                _FakeCandidate(sport="tennis", name="fam_narrow"),
            ],
            tested_set=set(),
        )
    }
    store = _FakeBeliefStore({
        ("tennis", "fam_wide"): (0.05, 0.95),
        ("tennis", "fam_narrow"): (0.40, 0.50),
    })
    result = rank_gaps(enumerator_results=enum, belief_store=store)
    assert result[0].family == "fam_wide"

def test_larger_coverage_gap_ranks_higher() -> None:
    enum = {
        "sport_a": _FakeCoverageResult(
            sport="sport_a",
            candidates=[_FakeCandidate(sport="sport_a", name=f"a_{i}") for i in range(10)],
            tested_set={f"a_{i}" for i in range(9)},   # 10% gap
        ),
        "sport_b": _FakeCoverageResult(
            sport="sport_b",
            candidates=[_FakeCandidate(sport="sport_b", name=f"b_{i}") for i in range(10)],
            tested_set={f"b_{i}" for i in range(1)},   # 90% gap
        ),
    }
    result = rank_gaps(enumerator_results=enum, belief_store=_FakeBeliefStore())
    sport_a_rank = next(g.rank for g in result if g.sport == "sport_a")
    first_sport_b_rank = next(g.rank for g in result if g.sport == "sport_b")
    assert first_sport_b_rank < sport_a_rank

# --- REJECT discount --------------------------------------------------------

def test_rejected_ranks_below_untested() -> None:
    sport = "mlb"
    enum = {
        sport: _FakeCoverageResult(
            sport=sport,
            candidates=[
                _FakeCandidate(sport=sport, name="rejected_fam"),
                _FakeCandidate(sport=sport, name="fresh_fam"),
            ],
            tested_set=set(),
        )
    }
    findings = [_FakeFinding(sport=sport, family="rejected_fam", verdict="REJECT")]
    result = rank_gaps(enumerator_results=enum, findings=findings)
    by = {g.family: g for g in result}
    assert "rejected_fam" in by  # still listed for completeness
    assert by["fresh_fam"].rank < by["rejected_fam"].rank

def test_settled_discount_values() -> None:
    enum = {
        "tennis": _FakeCoverageResult(
            sport="tennis",
            candidates=[
                _FakeCandidate(sport="tennis", name="rej"),
                _FakeCandidate(sport="tennis", name="fresh"),
            ],
            tested_set=set(),
        )
    }
    findings = [_FakeFinding(sport="tennis", family="rej", verdict="REJECT")]
    by = {g.family: g for g in rank_gaps(enumerator_results=enum, findings=findings)}
    assert by["rej"].settled_discount == pytest.approx(0.20)
    assert by["fresh"].settled_discount == pytest.approx(1.0)

def test_defer_data_penalty() -> None:
    enum = {
        "soccer": _FakeCoverageResult(
            sport="soccer",
            candidates=[_FakeCandidate(sport="soccer", name="deferred_fam")],
            tested_set=set(),
        )
    }
    findings = [_FakeFinding(sport="soccer", family="deferred_fam", verdict="DEFER")]
    result = rank_gaps(enumerator_results=enum, findings=findings)
    assert len(result) == 1
    g = result[0]
    assert g.data_penalty == pytest.approx(0.5)
    assert g.settled_discount == pytest.approx(1.0)

# --- Honest framing — no edge-claim language --------------------------------

_EDGE_PATTERNS = [
    _re.compile(r"\bedge\b"),
    _re.compile(r"\bprofit\b"),
    _re.compile(r"\balpha\b"),
    _re.compile(r"beat the market"),
    _re.compile(r"positive expected value"),
    _re.compile(r"positive ev\b"),
    _re.compile(r"\+ev\b"),
]

def test_honest_preamble_in_format_output() -> None:
    enum = _make_enum("tennis", n_total=5, n_tested=2, prefix="p")
    out = format_gaps(rank_gaps(enumerator_results=enum))
    assert "UNTESTED != opportunity" in out
    assert "markets efficient" in out.lower()

def test_no_edge_claim_in_rationale() -> None:
    enum = _make_enum("mlb", n_total=8, n_tested=2, prefix="q")
    for g in rank_gaps(enumerator_results=enum):
        combined = (g.rationale + " " + g.what_would_settle_it).lower()
        for pat in _EDGE_PATTERNS:
            assert not pat.search(combined), (
                f"Edge-claim {pat.pattern!r} in {g.family}: {combined[:200]}"
            )

def test_honest_note_is_preamble() -> None:
    enum = _make_enum("soccer", n_total=4, n_tested=1, prefix="r")
    for g in rank_gaps(enumerator_results=enum):
        assert g.honest_note == HONEST_PREAMBLE

def test_format_output_says_expected_reject() -> None:
    enum = _make_enum("tennis", n_total=3, n_tested=0, prefix="x")
    out = format_gaps(rank_gaps(enumerator_results=enum))
    assert "REJECT" in out
    assert "markets efficient" in out.lower()

# --- top_n and rank attribute -----------------------------------------------

def test_top_n_limits_output() -> None:
    enum = _make_enum("mlb", n_total=20, n_tested=0, prefix="n")
    assert len(rank_gaps(enumerator_results=enum, top_n=5)) == 5

def test_rank_attribute_sequential() -> None:
    enum = _make_enum("tennis", n_total=6, n_tested=0, prefix="seq")
    gaps = rank_gaps(enumerator_results=enum)
    assert [g.rank for g in gaps] == list(range(1, len(gaps) + 1))

def test_format_gaps_top_n_slice() -> None:
    enum = _make_enum("soccer", n_total=8, n_tested=0, prefix="fg")
    out = format_gaps(rank_gaps(enumerator_results=enum), top_n=3)
    assert out.count("Rank #") == 3

# --- Scores non-negative ----------------------------------------------------

def test_scores_non_negative() -> None:
    enum = _make_enum("mlb", n_total=10, n_tested=3, prefix="sc")
    findings = [
        _FakeFinding(sport="mlb", family="sc_5", verdict="REJECT"),
        _FakeFinding(sport="mlb", family="sc_6", verdict="DEFER"),
    ]
    for g in rank_gaps(enumerator_results=enum, findings=findings):
        assert g.score >= 0.0

# --- Multi-sport ------------------------------------------------------------

def test_multi_sport_large_gap_dominates() -> None:
    enum = {
        "tennis": _FakeCoverageResult(
            sport="tennis",
            candidates=[_FakeCandidate(sport="tennis", name=f"t_{i}") for i in range(10)],
            tested_set={f"t_{i}" for i in range(5)},   # 50% gap
        ),
        "mlb": _FakeCoverageResult(
            sport="mlb",
            candidates=[_FakeCandidate(sport="mlb", name=f"m_{i}") for i in range(10)],
            tested_set={f"m_{i}" for i in range(2)},   # 80% gap
        ),
    }
    gaps = rank_gaps(enumerator_results=enum, belief_store=None)
    top5 = [g.sport for g in gaps[:5]]
    assert top5.count("mlb") > top5.count("tennis")

# --- Ledger-only families ---------------------------------------------------

def test_ledger_only_family_included() -> None:
    findings = [_FakeFinding(sport="nba", family="ledger_only", verdict="DEFER")]
    assert any(g.family == "ledger_only" for g in rank_gaps(findings=findings))

def test_ledger_only_reject_ranked_below_defer() -> None:
    findings = [
        _FakeFinding(sport="nba", family="settled_fam", verdict="REJECT"),
        _FakeFinding(sport="nba", family="deferred_fam", verdict="DEFER"),
    ]
    by = {g.family: g for g in rank_gaps(findings=findings)}
    assert by["settled_fam"].score < by["deferred_fam"].score
