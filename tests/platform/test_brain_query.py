"""Tests for scripts.platformkit.brain_query — retrieval seam over the Obsidian brain.

Fixture brain in tmp_path; no real vault touched.  Pure stdlib; no pandas/pyarrow.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.platformkit.brain_query import (
    BrainHit,
    _NO_NUMBER_CONTRACT,
    brain_query,
    is_number_free,
    prior_verdicts,
)


# ── Fixture ───────────────────────────────────────────────────────────────────

def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_brain(root: Path) -> None:
    _w(root / "Archetypes" / "rim_runner.md",
       "---\narchetype: \"Rim Runner\"\nas_of: \"2026-06-01\"\n---\n"
       "# Rim Runner\n\n## Statistical Fingerprint\n\n"
       "| Metric | Median |\n|---|---|\n| Usage rate | 12.4% |\n| Paint share | 71.2% |\n\n"
       "**Role:** interior finisher\n**Prevalence:** common (nba)\n")
    _w(root / "Archetypes" / "big_server.md",
       "---\narchetype: \"Big Server\"\nsport: tennis\n---\n# Big Server\n\n"
       "Relies on dominant first-serve.\n\n**Serve pct:** 68%\n**Ace rate:** high\n")
    _w(root / "Teams" / "NYK" / "_Team.md",
       "---\ntags: [team, hub]\n---\n# NYK — Roster\n- Jalen Brunson — Primary Initiator\n")
    _w(root / "Teams" / "NYK" / "1628973_jalen_brunson.md",
       "<!-- PLAYSTYLE-EXPORT v1 -->\n# Jalen Brunson\n\n"
       "**Team:** [[NYK]] · **Archetype:** Primary Initiator / Lead Guard\n\n"
       "**Usage:** high\n**Isolation rate:** top-10\n")
    _w(root / "Schemes" / "drop_coverage.md",
       "---\nscheme: DROP COVERAGE\nslug: drop_coverage\n---\n# DROP COVERAGE — Scheme Hub\n\n"
       "The big sags below the screen in pick-and-roll.\n\n"
       "| Feature | Avg Delta |\n|---------|----------|\n| potential_assists | +0.618 |\n")
    _w(root / "Trends" / "rim_attack_trend.md",
       "# Rim Attack Trend 2025-26\n\nRising prevalence of rim-runner archetypes.\n\n"
       "**Trend direction:** increasing\n**Sport:** nba\n")
    _w(root / "_Index" / "_World_Model.md",
       "# _World_Model\n\nMarkets are EFFICIENT; every tested signal REJECTS.\n"
       "No edge claimed.\nedge_claimed: False\n\n| Sport | Verdict |\n|---|---|\n"
       "| nba | REJECT |\n| tennis | REJECT |\n")


# ── Tests: brain_query ────────────────────────────────────────────────────────

class TestBrainQuery:

    def test_returns_hits_for_relevant_query(self, tmp_path):
        """(1) Relevant query returns non-empty ranked BrainHit list."""
        root = tmp_path / "brain"
        _make_brain(root)
        hits = brain_query("rim runner paint", root=root)
        assert len(hits) >= 1
        assert any("Rim Runner" in h.title or "rim" in h.title.lower() for h in hits)

    def test_sport_filter(self, tmp_path):
        """(2a) sport filter excludes non-matching notes."""
        root = tmp_path / "brain"
        _make_brain(root)
        hits = brain_query("big server", sport="tennis", root=root)
        for h in hits:
            assert h.sport in ("tennis", ""), f"Got sport '{h.sport}' in tennis-filtered results"
        hits_nba = brain_query("rim runner", sport="nba", root=root)
        assert not any(h.sport == "tennis" for h in hits_nba)

    def test_kind_filter(self, tmp_path):
        """(2b) kind filter keeps only matching kind."""
        root = tmp_path / "brain"
        _make_brain(root)
        hits = brain_query("coverage", kind="scheme", root=root)
        assert hits  # at least drop_coverage
        for h in hits:
            assert h.kind == "scheme", f"Expected kind=scheme, got '{h.kind}'"

    def test_provenance_and_number_free(self, tmp_path):
        """(3) Every hit has non-empty provenance starting 'brain:' and is_number_free."""
        root = tmp_path / "brain"
        _make_brain(root)
        hits = brain_query("archetype scheme rim", root=root, top_k=20)
        assert hits
        for h in hits:
            assert h.provenance, f"Empty provenance: {h.title}"
            assert h.provenance.startswith("brain:"), f"Bad provenance: {h.provenance!r}"
            assert is_number_free(h), (
                f"Number-contract violation in '{h.title}': sig={h.stat_signature}"
            )

    def test_top_k_respected(self, tmp_path):
        """Returns at most top_k hits."""
        root = tmp_path / "brain"
        _make_brain(root)
        hits = brain_query("the", root=root, top_k=2)
        assert len(hits) <= 2

    def test_stat_signature_populated(self, tmp_path):
        """(7) stat_signature is populated from note stat lines."""
        root = tmp_path / "brain"
        _make_brain(root)
        hits = brain_query("rim runner paint share", root=root, top_k=10)
        rim = [h for h in hits if "Rim Runner" in h.title or "rim_runner" in h.title.lower()]
        assert rim, "Expected Rim Runner hit"
        assert len(rim[0].stat_signature) >= 1

    def test_missing_root_returns_empty(self, tmp_path):
        """(5) Explicitly passed missing root returns []."""
        hits = brain_query("anything", root=tmp_path / "does_not_exist")
        assert hits == []

    def test_empty_directory_returns_empty(self, tmp_path):
        """(10) Existing but empty directory returns []."""
        empty = tmp_path / "empty"
        empty.mkdir()
        assert brain_query("anything", root=empty) == []

    def test_deterministic(self, tmp_path):
        """Same query twice produces identical ordering."""
        root = tmp_path / "brain"
        _make_brain(root)
        a = brain_query("drop coverage rim paint", root=root, top_k=10)
        b = brain_query("drop coverage rim paint", root=root, top_k=10)
        assert [h.path for h in a] == [h.path for h in b]

    def test_unreadable_note_skipped(self, tmp_path, monkeypatch):
        """Gracefully skips unreadable notes without raising."""
        root = tmp_path / "brain"
        _make_brain(root)
        import scripts.platformkit.brain_query as bq
        orig = bq.Path.read_text

        def flaky(self, *a, **k):
            if "rim_runner" in self.name:
                raise OSError("boom")
            return orig(self, *a, **k)

        monkeypatch.setattr(bq.Path, "read_text", flaky)
        hits = brain_query("rim runner", root=root)
        assert isinstance(hits, list)


# ── Tests: prior_verdicts ─────────────────────────────────────────────────────

class TestPriorVerdicts:

    def test_edge_claimed_false(self, tmp_path):
        """(4) Always returns edge_claimed: False."""
        root = tmp_path / "brain"
        _make_brain(root)
        assert prior_verdicts(root=root)["edge_claimed"] is False

    def test_required_keys(self, tmp_path):
        root = tmp_path / "brain"
        _make_brain(root)
        v = prior_verdicts(root=root)
        assert {"edge_claimed", "market_efficiency", "tested_signals"} <= v.keys()

    def test_market_efficiency(self, tmp_path):
        root = tmp_path / "brain"
        _make_brain(root)
        assert prior_verdicts(root=root)["market_efficiency"] == "efficient"

    def test_tested_signals_reject(self, tmp_path):
        root = tmp_path / "brain"
        _make_brain(root)
        assert prior_verdicts(root=root)["tested_signals"] == "REJECT"

    def test_defaults_no_world_model(self, tmp_path):
        """(8) Falls back to conservative defaults when no world-model note present."""
        empty = tmp_path / "no_wm"
        empty.mkdir()
        (empty / "other.md").write_text("# Other\nsome content.", encoding="utf-8")
        v = prior_verdicts(root=empty)
        assert v["edge_claimed"] is False
        assert v["market_efficiency"] == "efficient"

    def test_missing_root_defaults(self, tmp_path):
        """(5-variant) Missing root returns conservative defaults."""
        v = prior_verdicts(root=tmp_path / "absent")
        assert v["edge_claimed"] is False


# ── Tests: is_number_free ─────────────────────────────────────────────────────

class TestIsNumberFree:

    def test_clean_hit_passes(self):
        hit = BrainHit(
            sport="nba", kind="archetype", title="3D Wing",
            path="/vault/3_d_wing.md",
            stat_signature={"Usage rate": "13.7%", "Paint share": "26.4%"},
            prevalence=0.45, excerpt="The connective tissue of modern rosters.",
            provenance="brain:Archetypes/3_d_wing.md",
        )
        assert is_number_free(hit)

    def test_forbidden_keyword_in_stat_sig_fails(self):
        """(9) stat_signature key 'edge' triggers the contract guard."""
        hit = BrainHit(
            sport="nba", kind="archetype", title="Bad Hit",
            path="/vault/bad.md",
            stat_signature={"edge": "claimed"},
            prevalence=0.3, excerpt="neutral prose.",
            provenance="brain:bad.md",
        )
        assert not is_number_free(hit)

    def test_forbidden_keyword_in_title_fails(self):
        """A hit with 'probability' in the title fails."""
        hit = BrainHit(
            sport="nba", kind="reference", title="Win Probability Edge Report",
            path="/vault/bad2.md", stat_signature={},
            prevalence=0.1, excerpt="neutral.",
            provenance="brain:bad2.md",
        )
        assert not is_number_free(hit)

    def test_world_model_excerpt_allowed(self, tmp_path):
        """_World_Model note prose saying 'no edge' does NOT trigger the guard."""
        root = tmp_path / "brain"
        _make_brain(root)
        hits = brain_query("world model efficient", root=root, top_k=20)
        wm = [h for h in hits if "_World_Model" in h.title or "world_model" in h.title.lower()]
        # If returned, it must pass is_number_free (excerpt not checked)
        for h in wm:
            assert is_number_free(h), f"World-model hit failed number-free check: {h.title}"


# ── Module contract ───────────────────────────────────────────────────────────

def test_no_number_contract_constant():
    """(6) _NO_NUMBER_CONTRACT is a non-empty documentation string."""
    assert isinstance(_NO_NUMBER_CONTRACT, str) and len(_NO_NUMBER_CONTRACT) > 20


def test_module_importable():
    """All public symbols import cleanly."""
    from scripts.platformkit import brain_query as bq  # noqa: F401
    assert all(callable(getattr(bq, s)) for s in ("brain_query", "prior_verdicts", "is_number_free"))
    assert hasattr(bq, "_NO_NUMBER_CONTRACT")


# ── Regression: absolute root under a repo dir named like a sport ──────────────

def test_sport_inferred_from_root_relative_path(tmp_path):
    """Regression: a root whose ABSOLUTE path contains a sport substring (e.g. the
    repo dir 'nba-ai-system') must NOT leak that sport into every note's inference.
    Sport is inferred from the ROOT-RELATIVE path only.
    """
    # Root nested under a parent literally containing the 'nba' substring.
    root = tmp_path / "nba-ai-system" / "vault" / "_Organized"
    _w(root / "Tennis" / "Archetypes" / "big_server.md",
       "# Big Server\n\nDominant first serve.\n\n**Serve pct:** 68%\n")
    _w(root / "Soccer" / "Archetypes" / "high_press.md",
       "# High Press\n\nAggressive forward pressing.\n\n**PPDA:** low\n")
    _w(root / "MLB" / "Archetypes" / "power_bats.md",
       "# Power Run-Scoring\n\nHigh slugging offense.\n\n**ISO:** high\n")

    # Each sport's note must infer ITS OWN sport, not 'nba' from the parent dir.
    tennis = brain_query("serve archetype", sport="tennis", root=root, top_k=10)
    assert tennis, "tennis note not found under nba-* root (abs-root sport leak)"
    assert all(h.sport == "tennis" for h in tennis)

    soccer = brain_query("press archetype", sport="soccer", root=root, top_k=10)
    assert soccer and all(h.sport == "soccer" for h in soccer)

    # And an nba-filtered query must NOT return the tennis/soccer/mlb notes.
    nba = brain_query("archetype", sport="nba", root=root, top_k=10)
    assert all(h.sport in ("nba", "") for h in nba)
