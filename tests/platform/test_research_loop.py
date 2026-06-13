"""tests.platform.test_research_loop — Tests for the offline research pipeline.

Verifies that run_research_loop:
  1. Produces a ledger with expected findings when catalog reports are present.
  2. Writes a research note with honest all-REJECT / market-efficient framing
     and no edge-claim language.
  3. Is idempotent (re-running does not duplicate ledger rows).
  4. Gracefully skips when no catalog report files exist.
  5. The written markdown note contains required honest disclaimers.

All I/O uses tmp_path — no real vault or data/research directories are touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the research harness module folder is importable without installing.
_ROOT = Path(__file__).resolve().parents[2]
_HARNESS = _ROOT / "scripts" / "research_harness"
if str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))

from research_loop import run_research_loop  # noqa: E402
from research_ledger import Ledger, ResearchFinding  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic catalog fixture helpers
# ---------------------------------------------------------------------------

_CATALOG_ROWS = """\
# _Catalog_Tennis.md — synthetic fixture

| family | expected | actual | notes | n | clv | reason |
|--------|----------|--------|-------|---|-----|--------|
| tennis_abs_rest_diff | REJECT | REJECT | null shuffle | 30616 | 0.0 | p=0.174 below threshold |
| tennis_elo_gap_magnitude | REJECT | REJECT | null shuffle | 30616 | 0.0 | p=1.000 no signal |
| tennis_surf_diff_abs | DEFER | DEFER | notes | 8000 | 0.0 | insufficient OOS |
"""

_CATALOG_ROWS_SOCCER = """\
# _Catalog_Soccer.md — synthetic fixture

| family | expected | actual | notes | n | clv | reason |
|--------|----------|--------|-------|---|-----|--------|
| soccer_over_under_poisson | REJECT | REJECT | null shuffle | 12000 | 0.0 | market efficient |
"""


def _write_fake_catalog(tmp_vault: Path) -> None:
    """Write synthetic _Catalog*.md files into a fake vault/Sports structure."""
    tennis_sig = tmp_vault / "Tennis" / "Signals"
    tennis_sig.mkdir(parents=True, exist_ok=True)
    (tennis_sig / "_Catalog_Tennis.md").write_text(_CATALOG_ROWS, encoding="utf-8")

    soccer_sig = tmp_vault / "Soccer" / "Signals"
    soccer_sig.mkdir(parents=True, exist_ok=True)
    (soccer_sig / "_Catalog_Soccer.md").write_text(_CATALOG_ROWS_SOCCER, encoding="utf-8")


# ---------------------------------------------------------------------------
# Edge-claim phrases that must NOT appear in the research note.
# Note: "edge" appears legitimately in "no edge is claimed" (honest framing);
# we only forbid phrases that positively assert a profitable edge exists.
# ---------------------------------------------------------------------------
_EDGE_WORDS = (
    "profitable", "profitability", "arbitrage",
    "winning strategy", "guaranteed",
    "positive edge", "betting edge", "proven edge",
)


def test_loop_produces_expected_findings(tmp_path: Path) -> None:
    """With synthetic catalog files the ledger must contain exactly the parsed rows."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    ledger_path = tmp_path / "findings.jsonl"

    result = run_research_loop(
        ledger_path=ledger_path,
        vault_root=vault,
        out_md=tmp_path / "research.md",
        dry_run=False,
        verbose=False,
    )

    # The three synthetic REJECT/DEFER rows should have been ingested.
    assert result["n_total"] >= 3, (
        f"Expected ≥3 findings; got {result['n_total']}"
    )
    # All parseable rows come from the fixture — n_ingested equals n_total on
    # a fresh ledger.
    assert result["n_ingested"] == result["n_total"]

    ledger = Ledger(path=ledger_path)
    findings = ledger.all_findings()
    families = {f.family for f in findings}
    assert "tennis_abs_rest_diff" in families
    assert "tennis_elo_gap_magnitude" in families
    assert "soccer_over_under_poisson" in families


def test_loop_verdicts_are_reject_or_defer(tmp_path: Path) -> None:
    """All synthetic findings must be REJECT or DEFER — never an unearned SHIP."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    ledger_path = tmp_path / "findings.jsonl"

    run_research_loop(
        ledger_path=ledger_path,
        vault_root=vault,
        out_md=tmp_path / "research.md",
        dry_run=False,
        verbose=False,
    )

    ledger = Ledger(path=ledger_path)
    for f in ledger.all_findings():
        assert f.verdict in {"REJECT", "DEFER", "SHIP"}, (
            f"Unexpected verdict {f.verdict!r} for {f.family}"
        )
    # Specifically: none of the SYNTHETIC rows should be SHIP
    families_ship = {f.family for f in ledger.all_findings() if f.verdict == "SHIP"}
    assert not families_ship, f"No SHIP expected from synthetic fixtures; got {families_ship}"


def test_research_note_honest_framing(tmp_path: Path) -> None:
    """The written markdown must contain the market-efficient / no-edge disclaimer."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    out_md = tmp_path / "research.md"

    run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=out_md,
        dry_run=False,
        verbose=False,
    )

    content = out_md.read_text(encoding="utf-8").lower()
    assert "no edge is claimed" in content, "Research note must state no edge is claimed"
    assert "market efficient" in content or "market efficiency" in content, (
        "Research note must reference market efficiency"
    )
    assert "reject" in content, "Research note must highlight REJECT verdicts"


def test_research_note_no_edge_claim_language(tmp_path: Path) -> None:
    """The written markdown must not contain edge-claim language."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    out_md = tmp_path / "research.md"

    run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=out_md,
        dry_run=False,
        verbose=False,
    )

    content = out_md.read_text(encoding="utf-8").lower()
    for word in _EDGE_WORDS:
        assert word not in content, (
            f"Research note contains forbidden edge-claim phrase: {word!r}"
        )


def test_loop_is_idempotent(tmp_path: Path) -> None:
    """Running the loop twice must not duplicate ledger rows."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    ledger_path = tmp_path / "findings.jsonl"
    out_md = tmp_path / "research.md"
    kwargs = dict(
        ledger_path=ledger_path,
        vault_root=vault,
        out_md=out_md,
        dry_run=False,
        verbose=False,
    )

    result_first = run_research_loop(**kwargs)
    n_after_first = result_first["n_total"]

    result_second = run_research_loop(**kwargs)
    n_after_second = result_second["n_total"]

    assert n_after_second == n_after_first, (
        f"Idempotency violated: first run={n_after_first}, second run={n_after_second}"
    )
    # Second run should have appended 0 new findings
    assert result_second["n_ingested"] == 0, (
        f"Second run should have ingested 0 new rows, got {result_second['n_ingested']}"
    )


def test_graceful_skip_when_no_catalog_reports(tmp_path: Path) -> None:
    """When vault/Sports does not exist the loop must complete without error."""
    empty_vault = tmp_path / "nonexistent_vault"  # does not exist
    ledger_path = tmp_path / "findings.jsonl"

    result = run_research_loop(
        ledger_path=ledger_path,
        vault_root=empty_vault,
        out_md=tmp_path / "research.md",
        dry_run=False,
        verbose=False,
    )

    assert result["skipped_no_data"] is True
    assert result["n_ingested"] == 0
    assert result["n_total"] == 0


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """dry_run=True must not write the ledger or the markdown note."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    ledger_path = tmp_path / "findings.jsonl"
    out_md = tmp_path / "research.md"

    run_research_loop(
        ledger_path=ledger_path,
        vault_root=vault,
        out_md=out_md,
        dry_run=True,
        verbose=False,
    )

    # Ledger may be created (Ledger.__init__ touches it) but should have 0 rows
    if ledger_path.exists():
        ledger = Ledger(path=ledger_path)
        assert ledger.summarize()["total"] == 0, (
            "dry_run must not append to ledger"
        )
    # Markdown output must NOT be written in dry-run mode
    assert not out_md.exists(), "dry_run must not write the markdown note"


def test_result_contains_coverage_summary(tmp_path: Path) -> None:
    """The return dict must include a non-empty coverage_summary string."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)

    result = run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=tmp_path / "research.md",
        dry_run=False,
        verbose=False,
    )

    assert "coverage_summary" in result
    assert isinstance(result["coverage_summary"], str)
    assert len(result["coverage_summary"]) > 0
    # Must not contain edge claims
    summary_lower = result["coverage_summary"].lower()
    for word in _EDGE_WORDS:
        assert word not in summary_lower, (
            f"coverage_summary contains forbidden word: {word!r}"
        )


def test_result_contains_verdict_summary(tmp_path: Path) -> None:
    """The return dict must include a verdict_summary with all three verdict keys."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)

    result = run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=tmp_path / "research.md",
        dry_run=False,
        verbose=False,
    )

    vs = result["verdict_summary"]
    assert "REJECT" in vs
    assert "DEFER" in vs
    assert "SHIP" in vs
    # From synthetic fixture: 2 REJECT (tennis) + 1 REJECT (soccer) + 1 DEFER
    assert vs["REJECT"] >= 3
    assert vs["DEFER"] >= 1


# ---------------------------------------------------------------------------
# BeliefStore integration tests
# ---------------------------------------------------------------------------


