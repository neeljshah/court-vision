"""test_world_model.py — Unit tests for scripts.platformkit.atlas.world_model.

Checks: file created; valid frontmatter; person-free; efficiency/REJECT thesis;
all 4 sports referenced; frontiers/"what would change" section; no forbidden
edge-claim phrases; graceful-skip when meta notes absent; raises on bad dir;
idempotency.  All tests use tmp_path — real vault is never touched.  Py 3.9.
"""
from __future__ import annotations

import pathlib
import re
import textwrap

import pytest

from scripts.platformkit.atlas.world_model import build_world_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _make_graph_stats(base: pathlib.Path) -> None:
    _write(base / "_GraphStats.md", """\
        ---
        tags: [memory-graph, stats, meta]
        generated: 2026-06-13
        ---
        # Memory-Graph Stats
        ## Overview
        | Metric | Value |
        |--------|-------|
        | Total notes | **1261** |
        | Total [[wikilinks]] | 4500 |
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
        | Total candidates tested | **44** |
        | Total REJECT | 44 |
        | Total DEFER | 0 |
        | Total SHIP | 0 |
    """)


def _make_sport_dirs(base: pathlib.Path) -> None:
    for name in ("Tennis", "Soccer", "MLB", "Basketball_NBA"):
        (base / name).mkdir(parents=True, exist_ok=True)


@pytest.fixture()
def full_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    _make_graph_stats(tmp_path)
    _make_signals_hub(tmp_path)
    _make_sport_dirs(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------

class TestOutputFile:
    def test_created_at_correct_path(self, full_vault: pathlib.Path) -> None:
        out = build_world_model(full_vault)
        assert out.exists() and out.name == "_World_Model.md"
        assert out.parent == full_vault

    def test_returns_path_instance(self, full_vault: pathlib.Path) -> None:
        assert isinstance(build_world_model(full_vault), pathlib.Path)

    def test_nonempty(self, full_vault: pathlib.Path) -> None:
        assert len(build_world_model(full_vault).read_text(encoding="utf-8")) > 400


# ---------------------------------------------------------------------------
# Valid frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_opens_with_triple_dashes(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        assert text.startswith("---")

    def test_expected_tags_present(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        for tag in ("world-model", "meta", "cross-sport", "honest"):
            assert tag in text

    def test_generated_date(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        assert re.search(r"generated: 2026-\d{2}-\d{2}", text)

    def test_hub_uplink(self, full_vault: pathlib.Path) -> None:
        assert "[[_Hub]]" in build_world_model(full_vault).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Person-free check
# ---------------------------------------------------------------------------

_KNOWN_ATHLETE_PATTERNS = [
    re.compile(r"\bLeBron\b",      re.I),
    re.compile(r"\bJokic\b",       re.I),
    re.compile(r"\bWembanyama\b",  re.I),
    re.compile(r"\bFederer\b",     re.I),
    re.compile(r"\bDjokovic\b",    re.I),
    re.compile(r"\bMessi\b",       re.I),
    re.compile(r"\bOhtani\b",      re.I),
]


class TestPersonFree:
    def test_no_known_athlete_names(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        for pat in _KNOWN_ATHLETE_PATTERNS:
            assert not pat.search(text), f"Person name {pat.pattern!r} found — must be person-free"

    def test_no_players_section_heading(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        assert "## Players" not in text and "### Players" not in text


# ---------------------------------------------------------------------------
# Efficiency / REJECT thesis
# ---------------------------------------------------------------------------

class TestEfficiencyThesis:
    def test_market_efficient_language(self, full_vault: pathlib.Path) -> None:
        assert "efficient" in build_world_model(full_vault).read_text(encoding="utf-8").lower()

    def test_reject_mentioned(self, full_vault: pathlib.Path) -> None:
        assert "REJECT" in build_world_model(full_vault).read_text(encoding="utf-8")

    def test_thesis_section_heading(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        assert "Core Empirical Thesis" in text or "empirical thesis" in text.lower()

    def test_no_edge_claimed_phrase(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8").lower()
        assert "no edge" in text or "no durable edge" in text


# ---------------------------------------------------------------------------
# All 4 sports referenced
# ---------------------------------------------------------------------------

class TestAllSports:
    @pytest.mark.parametrize("sport", ["Tennis", "Soccer", "MLB", "Basketball"])
    def test_sport_present(self, sport: str, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        assert sport in text or sport.lower() in text

    def test_per_sport_section_exists(self, full_vault: pathlib.Path) -> None:
        assert "Per-Sport Breakdown" in build_world_model(full_vault).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Frontiers / "what would change" section
# ---------------------------------------------------------------------------

class TestFrontiersSection:
    def test_section_present(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        assert "What Would Change" in text or "Frontiers" in text

    def test_clv_or_freshness_mentioned(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        assert "CLV" in text or "Freshness" in text or "freshness" in text

    def test_live_or_ingame_mentioned(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8").lower()
        assert "live" in text or "in-game" in text

    def test_blocked_mentioned(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8")
        assert "DATA" in text or "BLOCKED" in text or "blocked" in text.lower()


# ---------------------------------------------------------------------------
# Forbidden edge-claim language
# ---------------------------------------------------------------------------

_FORBIDDEN = [
    "profitable edge", "+EV proven", "beats the market",
    "+18.38%", "ROI advantage", "guaranteed profit",
]


class TestNoEdgeClaims:
    @pytest.mark.parametrize("phrase", _FORBIDDEN)
    def test_phrase_absent(self, phrase: str, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8").lower()
        assert phrase.lower() not in text

    def test_honest_disclaimer_present(self, full_vault: pathlib.Path) -> None:
        text = build_world_model(full_vault).read_text(encoding="utf-8").lower()
        assert "no edge claimed" in text


# ---------------------------------------------------------------------------
# Graceful-skip / error handling
# ---------------------------------------------------------------------------

class TestGracefulSkipAndErrors:
    def test_empty_vault_no_exception(self, tmp_path: pathlib.Path) -> None:
        assert build_world_model(tmp_path).exists()

    def test_missing_signals_hub_ok(self, tmp_path: pathlib.Path) -> None:
        _make_graph_stats(tmp_path)
        assert build_world_model(tmp_path).exists()

    def test_empty_vault_still_has_thesis(self, tmp_path: pathlib.Path) -> None:
        text = build_world_model(tmp_path).read_text(encoding="utf-8")
        assert "REJECT" in text and "efficient" in text.lower()

    def test_empty_vault_still_has_all_sports(self, tmp_path: pathlib.Path) -> None:
        text = build_world_model(tmp_path).read_text(encoding="utf-8")
        for name in ("Tennis", "Soccer", "MLB", "Basketball"):
            assert name in text

    def test_raises_on_nonexistent_dir(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_world_model(tmp_path / "does_not_exist")


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_run_same_content(self, full_vault: pathlib.Path) -> None:
        def _strip_ts(t: str) -> str:
            return "\n".join(
                l for l in t.splitlines()
                if not l.startswith("*Generated") and "generated:" not in l
            )
        t1 = _strip_ts(build_world_model(full_vault).read_text(encoding="utf-8"))
        t2 = _strip_ts(build_world_model(full_vault).read_text(encoding="utf-8"))
        assert t1 == t2
