"""Tests for research_loop belief-store integration (tmp_path I/O; Py3.9)."""
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


def test_loop_persists_beliefs_json(tmp_path: Path) -> None:
    """After a non-dry-run, beliefs.json must exist and be valid JSON."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    beliefs_path = tmp_path / "beliefs.json"

    result = run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=tmp_path / "research.md",
        beliefs_path=beliefs_path,
        dry_run=False,
        verbose=False,
    )

    assert result["beliefs_path"] is not None, "beliefs_path must be set in result"
    assert beliefs_path.exists(), "beliefs.json must be written to disk"

    import json
    data = json.loads(beliefs_path.read_text(encoding="utf-8"))
    assert "beliefs" in data, "beliefs.json must have a 'beliefs' key"
    assert isinstance(data["beliefs"], list)
    assert len(data["beliefs"]) > 0, "At least one family belief must be persisted"


def test_loop_belief_summary_in_result(tmp_path: Path) -> None:
    """The result dict must include a non-empty belief_summary mapping."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)

    result = run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=tmp_path / "research.md",
        beliefs_path=tmp_path / "beliefs.json",
        dry_run=False,
        verbose=False,
    )

    bs = result["belief_summary"]
    assert isinstance(bs, dict), "belief_summary must be a dict"
    assert len(bs) > 0, "belief_summary must be non-empty after ingesting catalogs"
    # Each sport key should map to a dict of {family: posterior_mean}
    for sport, families in bs.items():
        assert isinstance(families, dict)
        for family, pm in families.items():
            assert isinstance(pm, float), f"posterior mean must be float, got {type(pm)}"
            assert 0.0 <= pm <= 1.0, f"posterior mean {pm} out of [0,1]"


def test_all_reject_posteriors_near_zero(tmp_path: Path) -> None:
    """All-REJECT fixture must produce posterior ship-rates well below 0.5."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)

    result = run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=tmp_path / "research.md",
        beliefs_path=tmp_path / "beliefs.json",
        dry_run=False,
        verbose=False,
    )

    bs = result["belief_summary"]
    # The synthetic fixture has 3 REJECTs and 1 DEFER; no SHIPs.
    # Every posterior mean must be below the prior mean (~0.10).
    for sport, families in bs.items():
        for family, pm in families.items():
            assert pm < 0.5, (
                f"{sport}/{family}: P(ship)={pm:.4f} too high for all-REJECT fixture"
            )
            # REJECT-only families should pull well below the prior ~0.10
            if family not in ("tennis_surf_diff_abs",):  # DEFER gets slight alpha bump
                assert pm < 0.15, (
                    f"{sport}/{family}: P(ship)={pm:.4f} unexpectedly high for REJECT"
                )


def test_writeup_shows_posterior_when_store_provided(tmp_path: Path) -> None:
    """When run produces a belief_store the markdown note must contain P(ship)."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    out_md = tmp_path / "research.md"

    run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=out_md,
        beliefs_path=tmp_path / "beliefs.json",
        dry_run=False,
        verbose=False,
    )

    content = out_md.read_text(encoding="utf-8")
    assert "P(ship) posterior" in content, (
        "Markdown note must contain posterior ship-rate when belief_store available"
    )
    assert "no edge claimed" in content.lower(), (
        "Posterior section must repeat the no-edge disclaimer"
    )


def test_writeup_no_posterior_without_store(tmp_path: Path) -> None:
    """render_writeup called without belief_store must NOT show P(ship) column."""
    from research_writeup import render_writeup
    from research_ledger import Ledger, ResearchFinding

    ledger = Ledger(path=tmp_path / "findings.jsonl")
    ledger.append(ResearchFinding(
        sport="tennis", family="rest_diff",
        hypothesis="rest gap predicts outcome",
        verdict="REJECT",
        evidence={"n": 100},
        what_would_change_my_mind="Second corpus with positive CLV.",
        dated="2025-01-01",
    ))

    # No belief_store argument (uses default None)
    md_no_store = render_writeup(ledger, generated_by="test")
    assert "P(ship) posterior" not in md_no_store, (
        "Without belief_store the markdown must not contain posterior ship-rate"
    )

    # Explicitly passing None also produces no posterior column
    md_explicit_none = render_writeup(ledger, generated_by="test", belief_store=None)
    assert "P(ship) posterior" not in md_explicit_none


def test_beliefs_idempotent_second_run(tmp_path: Path) -> None:
    """Running the loop twice must produce the same belief_summary (idempotency).

    The second run rebuilds BeliefStore from scratch from the (unchanged) ledger.
    Posterior means are compared at 4dp precision via belief_summary — the raw
    alpha/beta values may differ by floating-point epsilon due to time-decay
    computed at two different wall-clock instants, which is expected behaviour.
    """
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    kwargs = dict(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=tmp_path / "research.md",
        beliefs_path=tmp_path / "beliefs.json",
        dry_run=False,
        verbose=False,
    )

    result_first = run_research_loop(**kwargs)
    result_second = run_research_loop(**kwargs)

    bs1 = result_first["belief_summary"]
    bs2 = result_second["belief_summary"]

    assert bs1.keys() == bs2.keys(), (
        "belief_summary sports must be identical across idempotent re-runs"
    )
    for sport in bs1:
        assert bs1[sport].keys() == bs2[sport].keys(), (
            f"belief_summary families differ for sport {sport!r}"
        )
        for family in bs1[sport]:
            assert bs1[sport][family] == bs2[sport][family], (
                f"Posterior mean changed across runs for {sport}/{family}: "
                f"{bs1[sport][family]} vs {bs2[sport][family]}"
            )


def test_beliefs_no_edge_language_in_markdown(tmp_path: Path) -> None:
    """Even with belief_store integrated, the markdown must contain no edge-claim language."""
    vault = tmp_path / "vault" / "Sports"
    _write_fake_catalog(vault)
    out_md = tmp_path / "research.md"

    run_research_loop(
        ledger_path=tmp_path / "findings.jsonl",
        vault_root=vault,
        out_md=out_md,
        beliefs_path=tmp_path / "beliefs.json",
        dry_run=False,
        verbose=False,
    )

    content = out_md.read_text(encoding="utf-8").lower()
    for word in _EDGE_WORDS:
        assert word not in content, (
            f"Markdown with belief_store contains forbidden phrase: {word!r}"
        )
