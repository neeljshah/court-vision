"""test_intelligence_overview.py — Unit tests for intelligence_overview.

Uses a synthetic vault/Sports tree in tmp_path; never touches the real vault.
Single-process; safe for --timeout=120.
"""
from __future__ import annotations

import pathlib
import textwrap

import pytest

from scripts.platformkit.atlas.intelligence_overview import build_intelligence_overview


def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _make_graph_stats(base: pathlib.Path) -> None:
    _write(base / "_GraphStats.md", """\
        ---
        tags: [memory-graph, stats, meta]
        ---
        # Memory-Graph Stats
        ## Overview
        | Metric | Value |
        |--------|-------|
        | Total notes | **42** |
        | Total [[wikilinks]] | 300 |
        ## Per-Sport Note Counts
        | Sport | Total | Archetypes | Matchups | Playstyles | Style_matchups | Scheme_transitions | Home_environment | Scouting | Teams |
        | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
        | FakeSport | 20 | 3 | 10 | 4 | 7 | 0 | 0 | 0 | 3 |
        | OtherSport | 22 | 0 | 15 | 5 | 0 | 3 | 2 | 5 | 2 |
        ## Graph Composition
        | Type | Notes |
        |------|-------|
        | Archetypes | 3 |
    """)


def _make_signals_hub(base: pathlib.Path) -> None:
    _write(base / "_Signals_Hub.md", """\
        ---
        tags: [signals, edge-discovery, meta, honest]
        ---
        # Signals Hub
        Up: [[_Hub]]
        ## Overview
        | Metric | Value |
        |--------|-------|
        | Sports with catalogs | **2** |
        | Total candidates tested | **14** |
        | Total REJECT | 12 |
        | Total DEFER | 2 |
        | Total VARIANCE_ONLY | 0 |
        | Total SHIP | 0 |
    """)


def _make_archetype_taxonomy(base: pathlib.Path) -> None:
    _write(base / "_Archetype_Taxonomy.md", """\
        ---
        tags: [archetype, taxonomy, cross-sport, meta]
        ---
        # Archetype Taxonomy
        Up: [[_Hub]]
        ## Overview
        | Stat | Value |
        |------|-------|
        | Themes defined | **3** |
        ## Aggressive Scorers / High-Tempo Attack
        *Offense-first style.*
        **FakeSport**
        - [[FakeSport/Archetypes/HighScorer]]
        - [[FakeSport/Archetypes/FastBreak]]
        ## Defensive Specialists / Low-Risk
        *Defense-first identity.*
        **OtherSport**
        - [[OtherSport/Playstyles/LowBlock]]
        ## Balanced All-Rounders
        *Near-median profile.*
        **FakeSport**
        - [[FakeSport/Archetypes/Balanced]]
    """)


def _make_sport_dirs(base: pathlib.Path) -> None:
    # FakeSport: has Playstyles/_Playstyles_Index with scheme + teams columns
    _write(base / "FakeSport" / "Playstyles" / "_Playstyles_Index.md", """\
        ---
        sport: fakesport
        ---
        # FakeSport Playstyles
        | Archetype | Teams |
        |-----------|-------|
        | [[Archetypes/HighScorer|High Scorer]] | 12 |
        | [[Archetypes/Balanced|Balanced]] | 5 |
    """)
    # FakeSport: Style_Matchups index (for section-e)
    _write(base / "FakeSport" / "Style_Matchups" / "_Style_Matchups_Index.md", """\
        ---
        sport: fakesport
        ---
        # FakeSport Style Matchups
        ## Key Findings
        - **Best matchup:** HighScorer vs Balanced (7 notes)
    """)
    # OtherSport: Scouting index with key findings
    _write(base / "OtherSport" / "Scouting" / "_Scouting_Index.md", """\
        ---
        sport: othersport
        ---
        # OtherSport Scouting Briefs
        ## Key Findings
        - **Most common:** defender scouting (5 notes)
    """)


@pytest.fixture()
def full_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    _make_graph_stats(tmp_path)
    _make_signals_hub(tmp_path)
    _make_archetype_taxonomy(tmp_path)
    _make_sport_dirs(tmp_path)
    return tmp_path


@pytest.fixture()
def minimal_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Sport dirs only; no meta notes — tests graceful-skip."""
    _make_sport_dirs(tmp_path)
    return tmp_path


class TestOutputFile:
    def test_created(self, full_vault: pathlib.Path) -> None:
        out = build_intelligence_overview(full_vault)
        assert out.exists() and out.name == "_Intelligence_Overview.md"
        assert out.parent == full_vault

    def test_returns_path(self, full_vault: pathlib.Path) -> None:
        assert isinstance(build_intelligence_overview(full_vault), pathlib.Path)


class TestFrontmatter:
    def test_tags(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        for tag in ("intelligence", "overview", "meta"):
            assert tag in text

    def test_generated_date(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "generated: 2026-" in text


class TestSections:
    def test_section_a_sports_present(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "Per-Sport Coverage" in text
        assert "FakeSport" in text and "OtherSport" in text

    def test_section_a_note_counts(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "20" in text and "22" in text

    def test_section_b_themes(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "Cross-Sport Archetype Themes" in text
        assert "Aggressive Scorers" in text
        assert "Balanced All-Rounders" in text

    def test_section_b_link_counts(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        # Aggressive Scorers has 2 wikilinks in the synthetic taxonomy
        assert "| Aggressive Scorers / High-Tempo Attack | 2 |" in text

    def test_section_c_signals(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "Edge-Search Honest Readout" in text
        assert "14" in text  # total candidates
        assert "NO edge is claimed" in text
        assert "Markets are efficient" in text

    def test_section_d_trends(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "Top Style-Trend by Sport" in text
        assert "FakeSport" in text

    def test_hub_uplink(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "[[_Hub]]" in text

    def test_source_notes_section(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        for link in ("[[_GraphStats]]", "[[_Signals_Hub]]", "[[_Archetype_Taxonomy]]"):
            assert link in text


class TestTacticalDimensions:
    def test_section_e_present(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "Tactical Intelligence Dimensions" in text

    def test_style_matchups_count_present(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        # FakeSport has 7 style_matchups; OtherSport has 0 → shown as —
        assert "7" in text
        assert "—" in text

    def test_scouting_count_present(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        # OtherSport has 5 scouting notes
        assert "5" in text

    def test_headline_findings_present(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "Headline Findings" in text
        assert "Style_Matchups" in text
        assert "Scouting" in text

    def test_headline_content_from_index(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        # Headline extracted from FakeSport style_matchups index
        assert "HighScorer vs Balanced" in text or "Best matchup" in text

    def test_scheme_transitions_absent_shown_as_dash(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        # FakeSport has 0 scheme_transitions
        assert "—" in text

    def test_no_edge_language_in_tactical(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        for phrase in ("betting edge", "proven edge", "+18.38%"):
            assert phrase not in text

    def test_tactical_missing_meta_graceful(self, minimal_vault: pathlib.Path) -> None:
        # minimal_vault has no _GraphStats → tactical section shows unavailable
        text = build_intelligence_overview(minimal_vault).read_text(encoding="utf-8")
        assert "Tactical Intelligence Dimensions" in text


class TestGracefulSkip:
    def test_missing_meta_notes_no_exception(self, minimal_vault: pathlib.Path) -> None:
        out = build_intelligence_overview(minimal_vault)
        assert out.exists()

    def test_missing_meta_notes_fallback(self, minimal_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(minimal_vault).read_text(encoding="utf-8")
        assert "unavailable" in text.lower() or "Coverage" in text

    def test_empty_vault_no_exception(self, tmp_path: pathlib.Path) -> None:
        out = build_intelligence_overview(tmp_path)
        assert out.exists()

    def test_missing_sport_trend_graceful(self, full_vault: pathlib.Path) -> None:
        # OtherSport has no Playstyles index
        out = build_intelligence_overview(full_vault)
        assert out.exists()

    def test_partial_meta_only_graph_stats(self, tmp_path: pathlib.Path) -> None:
        _make_graph_stats(tmp_path)
        _make_sport_dirs(tmp_path)
        text = build_intelligence_overview(tmp_path).read_text(encoding="utf-8")
        assert "Per-Sport Coverage" in text


class TestNoEdgeClaims:
    def test_forbidden_phrases_absent(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        for phrase in ("+18.38%", "proven edge", "betting edge", "ROI advantage"):
            assert phrase not in text

    def test_honest_framing_present(self, full_vault: pathlib.Path) -> None:
        text = build_intelligence_overview(full_vault).read_text(encoding="utf-8")
        assert "REJECT" in text
        assert "No edge claimed" in text or "NO edge" in text


class TestErrors:
    def test_raises_on_nonexistent_dir(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_intelligence_overview(tmp_path / "does_not_exist")


class TestIdempotency:
    def test_second_run_same_body(self, full_vault: pathlib.Path) -> None:
        def _strip_ts(text: str) -> str:
            return "\n".join(
                l for l in text.splitlines()
                if not l.startswith("*Generated") and "generated:" not in l
            )
        t1 = _strip_ts(build_intelligence_overview(full_vault).read_text(encoding="utf-8"))
        t2 = _strip_ts(build_intelligence_overview(full_vault).read_text(encoding="utf-8"))
        assert t1 == t2
