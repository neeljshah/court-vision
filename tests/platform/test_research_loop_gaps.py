"""tests.platform.test_research_loop_gaps — Gap-observer integration tests.

Verifies the additive gap_observer integration in run_research_loop / render_writeup:
  1. run_research_loop result contains a "top_gaps" key with ranked RankedGap objects.
  2. render_writeup appends "Highest-Value Next Questions" when gaps are supplied,
     carrying honest UNTESTED!=opportunity framing and NO edge-claim language.
  3. Section is ABSENT when gaps=None / [] (backward-compatible).
  4. Gap ranking is deterministic across repeated calls with identical inputs.

All I/O uses tmp_path — no real vault or data/research directories are touched.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_HARNESS = _ROOT / "scripts" / "research_harness"
if str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))

from research_loop import run_research_loop  # noqa: E402
from research_writeup import render_writeup  # noqa: E402
from research_ledger import Ledger, ResearchFinding  # noqa: E402
from gap_observer import RankedGap  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic catalog fixture helpers
# ---------------------------------------------------------------------------

_CATALOG_ROWS = """\
# _Catalog_Tennis.md — synthetic fixture

| family | expected | actual | notes | n | clv | reason |
|--------|----------|--------|-------|---|-----|--------|
| tennis_abs_rest_diff | REJECT | REJECT | null shuffle | 30616 | 0.0 | p=0.174 |
| tennis_elo_gap_magnitude | REJECT | REJECT | null shuffle | 30616 | 0.0 | p=1.000 |
| tennis_surf_diff_abs | DEFER | DEFER | notes | 8000 | 0.0 | insufficient OOS |
"""

_CATALOG_ROWS_SOCCER = """\
# _Catalog_Soccer.md — synthetic fixture

| family | expected | actual | notes | n | clv | reason |
|--------|----------|--------|-------|---|-----|--------|
| soccer_over_under_poisson | REJECT | REJECT | null shuffle | 12000 | 0.0 | efficient |
"""


def _write_fake_catalog(tmp_vault: Path) -> None:
    for sport, rows in (("Tennis", _CATALOG_ROWS), ("Soccer", _CATALOG_ROWS_SOCCER)):
        sig = tmp_vault / sport / "Signals"
        sig.mkdir(parents=True, exist_ok=True)
        (sig / f"_Catalog_{sport}.md").write_text(rows, encoding="utf-8")


def _run(tmp_path: Path, **kw) -> dict:
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    return run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=tmp_path / "research.md",
        dry_run=False,
        verbose=False,
        **kw,
    )


# ---------------------------------------------------------------------------
# Forbidden / required phrases
# ---------------------------------------------------------------------------
_EDGE_WORDS = (
    "profitable", "profitability", "arbitrage",
    "winning strategy", "guaranteed",
    "positive edge", "betting edge", "proven edge",
)
_REQUIRED_HONEST = (
    "untested != opportunity",
    "markets are efficient",
    "no edge is claimed",
)

# ---------------------------------------------------------------------------
# Minimal synthetic RankedGap objects for writeup unit tests
# ---------------------------------------------------------------------------


def _fake_gaps() -> List[RankedGap]:
    def _gap(rank, sport, family, score):
        return RankedGap(
            rank=rank, sport=sport, family=family, score=score,
            coverage_gap_weight=1.0, prior_uncertainty=0.405,
            data_penalty=1.0, settled_discount=1.0,
            verdict_history=[],
            rationale=f"score={score:.4f} | (UNTESTED)",
            what_would_settle_it="Run gate on >=2 corpora, FDR p<0.05.",
        )
    return [_gap(1, "tennis", "serve_speed_diff", 0.405),
            _gap(2, "soccer", "xg_differential", 0.364)]


# ---------------------------------------------------------------------------
# Tests — run_research_loop returns ranked gaps
# ---------------------------------------------------------------------------


def test_loop_top_gaps_key_and_type(tmp_path: Path) -> None:
    """result must have 'top_gaps' as a non-empty list of RankedGap objects."""
    result = _run(tmp_path)
    assert "top_gaps" in result, "result dict must contain 'top_gaps'"
    gaps = result["top_gaps"]
    assert isinstance(gaps, list), f"top_gaps must be list, got {type(gaps)}"
    assert len(gaps) > 0, "top_gaps must be non-empty when ledger has findings"
    for g in gaps:
        assert isinstance(g, RankedGap), f"element must be RankedGap, got {type(g)}"


def test_loop_top_gaps_n_caps_results(tmp_path: Path) -> None:
    """top_gaps_n=2 must return at most 2 gaps."""
    result = _run(tmp_path, top_gaps_n=2)
    assert len(result["top_gaps"]) <= 2


def test_loop_top_gaps_ordering(tmp_path: Path) -> None:
    """Gaps must be rank-ascending and score-descending."""
    gaps: List[RankedGap] = _run(tmp_path)["top_gaps"]
    ranks = [g.rank for g in gaps]
    scores = [g.score for g in gaps]
    assert ranks == list(range(1, len(ranks) + 1)), f"ranks not 1-based ascending: {ranks}"
    assert scores == sorted(scores, reverse=True), f"scores not descending: {scores}"


def test_gap_ranking_is_deterministic(tmp_path: Path) -> None:
    """Two identical runs must produce identical gap rankings."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    kw = dict(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=tmp_path / "research.md",
        dry_run=False, verbose=False,
    )
    gaps_a = run_research_loop(**kw)["top_gaps"]
    gaps_b = run_research_loop(**kw)["top_gaps"]

    assert len(gaps_a) == len(gaps_b), "gap count changed across runs"
    for ga, gb in zip(gaps_a, gaps_b):
        assert ga.rank == gb.rank
        assert ga.sport == gb.sport
        assert ga.family == gb.family
        assert abs(ga.score - gb.score) < 1e-9, f"score drifted: {ga.score} vs {gb.score}"


# ---------------------------------------------------------------------------
# Tests — render_writeup gaps section
# ---------------------------------------------------------------------------


def test_writeup_includes_gaps_section() -> None:
    """render_writeup with gaps must include 'Highest-Value Next Questions'."""
    # Pass an empty list directly (render_writeup accepts list or Ledger)
    md = render_writeup([], generated_by="test", gaps=_fake_gaps())
    assert "Highest-Value Next Questions" in md


def test_writeup_gaps_honest_framing_and_no_edge_claims() -> None:
    """Gaps section must carry honest framing and no edge-claim language."""
    md = render_writeup([], generated_by="test", gaps=_fake_gaps()).lower()

    for phrase in _REQUIRED_HONEST:
        assert phrase in md, f"missing required honest phrase: {phrase!r}"
    for word in _EDGE_WORDS:
        assert word not in md, f"forbidden edge-claim phrase found: {word!r}"


def test_writeup_gaps_lists_families() -> None:
    """Gaps section must include each gap's family name."""
    gaps = _fake_gaps()
    md = render_writeup([], generated_by="test", gaps=gaps)
    for g in gaps:
        assert g.family in md, f"family {g.family!r} missing from writeup"


# ---------------------------------------------------------------------------
# Tests — backward compatibility: section absent when no gaps supplied
# ---------------------------------------------------------------------------


def test_writeup_no_gaps_section_when_none_or_empty(tmp_path: Path) -> None:
    """gaps=None (default) and gaps=[] must not add the next-questions section."""
    ledger = Ledger(path=tmp_path / "findings.jsonl")
    ledger.append(ResearchFinding(
        sport="tennis", family="rest_diff",
        hypothesis="rest gap predicts outcome",
        verdict="REJECT", evidence={"n": 100},
        what_would_change_my_mind="Second corpus.",
        dated="2025-01-01",
    ))
    header = "Highest-Value Next Questions"
    assert header not in render_writeup(ledger, generated_by="test")
    assert header not in render_writeup(ledger, generated_by="test", gaps=None)
    assert header not in render_writeup(ledger, generated_by="test", gaps=[])


# ---------------------------------------------------------------------------
# Tests — end-to-end written markdown
# ---------------------------------------------------------------------------


def test_e2e_written_markdown_contains_gaps_section(tmp_path: Path) -> None:
    """End-to-end: written markdown must include next-questions section with
    honest framing and no edge-claim language."""
    result = _run(tmp_path)
    out_md = result["out_md"]
    assert out_md is not None and out_md.exists()

    content = out_md.read_text(encoding="utf-8")
    gaps = result["top_gaps"]

    if gaps:
        assert "Highest-Value Next Questions" in content
        cl = content.lower()
        for phrase in _REQUIRED_HONEST:
            assert phrase in cl, f"missing honest phrase: {phrase!r}"
        for word in _EDGE_WORDS:
            assert word not in cl, f"forbidden edge-claim in e2e markdown: {word!r}"
