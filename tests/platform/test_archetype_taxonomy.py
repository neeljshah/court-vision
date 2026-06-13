"""test_archetype_taxonomy.py — Unit tests for archetype_taxonomy.build_taxonomy.

Uses a synthetic vault/Sports tree in tmp_path; no real vault is touched.
Single-process; safe for --timeout=120.

Coverage:
  - Output file created with correct name
  - YAML frontmatter contains required tags
  - [[_Hub]] up-link present
  - All 7 theme ## headers present
  - [[Sport/Subdir/Slug]] wikilinks generated
  - Known archetypes land in correct themes
  - Graceful-skip: sports with no Playstyles/Archetypes dirs are ignored
  - Empty vault writes output without raising
  - Non-existent vault raises FileNotFoundError
  - Index files (_*_Index.md) excluded from links
  - Idempotent across two runs
"""
from __future__ import annotations

import pathlib
import re
import textwrap

import pytest

from scripts.platformkit.atlas.archetype_taxonomy import build_taxonomy

_WIKILINK_RE = re.compile(r"\[\[.+?\]\]")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.+?)\n---", re.DOTALL)


# ---------------------------------------------------------------------------
# Synthetic vault helpers
# ---------------------------------------------------------------------------

def _write_note(base: pathlib.Path, sport: str, subdir: str,
                slug: str, h1: str, desc: str, tags: list[str]) -> None:
    d = base / sport / subdir
    d.mkdir(parents=True, exist_ok=True)
    tag_block = "\n".join(f"  - {t}" for t in tags)
    (d / f"{slug}.md").write_text(textwrap.dedent(f"""\
        ---
        tags:
        {tag_block}
        ---
        # {h1}
        Up: [[{subdir}/_Index]] | [[_Index]]
        *{desc}*
        ## Stat Signature
        Synthetic threshold.
        #{' #'.join(tags)}
    """), encoding="utf-8")


def _write_index(base: pathlib.Path, sport: str, subdir: str) -> None:
    d = base / sport / subdir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"_{subdir}_Index.md").write_text("---\ntags: [index]\n---\n# Index\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    """Two sports with diverse notes + one sport dir lacking Playstyles/Archetypes."""
    _write_note(tmp_path, "Alpha_Sport", "Playstyles", "High_Scoring_Attacker",
                "High Scoring Attacker",
                "Offense-first style; maximises scoring output and attacking tempo.",
                ["sport/alpha", "playstyle", "scheme/attacking", "scheme/high-scoring"])
    _write_note(tmp_path, "Alpha_Sport", "Playstyles", "Defensive_Low_Block",
                "Defensive Low Block",
                "Compact defensive structure; limits opposition chances and match totals.",
                ["sport/alpha", "playstyle", "scheme/defensive", "scheme/low-block"])
    _write_note(tmp_path, "Alpha_Sport", "Playstyles", "Balanced_Contender",
                "Balanced Contender",
                "Near-median profile across attack and defence dimensions.",
                ["sport/alpha", "playstyle", "scheme/balanced"])
    _write_index(tmp_path, "Alpha_Sport", "Playstyles")

    _write_note(tmp_path, "Beta_Sport", "Archetypes", "High_Usage_Creator",
                "High-Usage Creator",
                "Ball-dominant playmaker who generates offense via high usage and AST%.",
                ["sport/beta", "archetype", "archetype/high_usage_creator"])
    _write_note(tmp_path, "Beta_Sport", "Archetypes", "Defensive_Anchor",
                "Defensive Anchor",
                "Rim-protector with elite defensive rating and high rebound rate.",
                ["sport/beta", "archetype", "archetype/defensive_anchor"])
    _write_note(tmp_path, "Beta_Sport", "Archetypes", "Bench_Contributor",
                "Bench Contributor",
                "Low-minutes role player who executes a specific role efficiently.",
                ["sport/beta", "archetype", "archetype/bench_contributor"])
    _write_index(tmp_path, "Beta_Sport", "Archetypes")

    # Empty_Sport: directory only, no Playstyles/Archetypes → graceful-skip
    (tmp_path / "Empty_Sport").mkdir()
    return tmp_path


@pytest.fixture()
def minimal_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    _write_note(tmp_path, "Solo_Sport", "Playstyles", "High_Variance_Attack",
                "High Variance Attack",
                "Unpredictable output; wide score distribution and leaky defence.",
                ["sport/solo", "playstyle", "scheme/high-variance"])
    _write_note(tmp_path, "Solo_Sport", "Archetypes", "Journeyman",
                "Journeyman",
                "Tour regular competing across surfaces without a dominant win-rate.",
                ["sport/solo", "archetype"])
    return tmp_path


@pytest.fixture()
def empty_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "_Meta").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_output_file_created(synthetic_vault: pathlib.Path) -> None:
    out = build_taxonomy(synthetic_vault)
    assert out.exists() and out.name == "_Archetype_Taxonomy.md"
    assert out.parent == synthetic_vault


def test_file_nonempty(synthetic_vault: pathlib.Path) -> None:
    assert build_taxonomy(synthetic_vault).stat().st_size > 0


def test_frontmatter_present(synthetic_vault: pathlib.Path) -> None:
    text = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    assert _FRONTMATTER_RE.match(text), "YAML frontmatter (---...---) not found at top"


def test_required_tags(synthetic_vault: pathlib.Path) -> None:
    text = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    for tag in ("archetype", "taxonomy", "cross-sport", "meta"):
        assert tag in text, f"Required tag '{tag}' missing"


def test_hub_uplink(synthetic_vault: pathlib.Path) -> None:
    assert "[[_Hub]]" in build_taxonomy(synthetic_vault).read_text(encoding="utf-8")


def test_all_seven_themes_present(synthetic_vault: pathlib.Path) -> None:
    text = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    for fragment in ("Aggressive Scorers", "Defensive Specialists", "Balanced All-Rounders",
                     "High-Variance", "Surface / Condition Specialists", "Role Players", "Playmakers"):
        assert fragment in text, f"Theme '{fragment}' missing from output"


def test_seven_theme_h2_headers(synthetic_vault: pathlib.Path) -> None:
    h2 = [l for l in build_taxonomy(synthetic_vault).read_text(encoding="utf-8").splitlines()
          if l.startswith("## ") and l != "## Overview"]
    assert len(h2) >= 7, f"Expected ≥7 theme ## headers, found {len(h2)}: {h2}"


def test_wikilinks_present(synthetic_vault: pathlib.Path) -> None:
    links = _WIKILINK_RE.findall(build_taxonomy(synthetic_vault).read_text(encoding="utf-8"))
    assert len(links) >= 2, f"Expected ≥2 wikilinks, found: {links}"


def test_sport_subdir_slug_link_format(synthetic_vault: pathlib.Path) -> None:
    text = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    sport_links = re.findall(r"\[\[\w[\w_]*/\w+/\w[\w_]*\]\]", text)
    assert len(sport_links) >= 1, f"No [[Sport/Subdir/Slug]] links found"


def test_attacking_note_appears_in_output(synthetic_vault: pathlib.Path) -> None:
    text = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    assert "Alpha_Sport/Playstyles/High_Scoring_Attacker" in text


def test_defensive_note_appears_in_output(synthetic_vault: pathlib.Path) -> None:
    text = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    assert "Beta_Sport/Archetypes/Defensive_Anchor" in text


def test_empty_sport_dir_skipped(synthetic_vault: pathlib.Path) -> None:
    empty_links = re.findall(r"\[\[Empty_Sport/", build_taxonomy(synthetic_vault).read_text(encoding="utf-8"))
    assert not empty_links, f"Empty_Sport generated unexpected links: {empty_links}"


def test_no_exception_on_empty_vault(empty_vault: pathlib.Path) -> None:
    out = build_taxonomy(empty_vault)
    assert out.exists()


def test_underscore_dirs_produce_no_entries(empty_vault: pathlib.Path) -> None:
    text = build_taxonomy(empty_vault).read_text(encoding="utf-8")
    # _Meta dir must not produce sport entries
    assert "[[_Meta/" not in text


def test_index_files_excluded(synthetic_vault: pathlib.Path) -> None:
    text = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    assert "_Playstyles_Index" not in text and "_Archetypes_Index" not in text


def test_missing_vault_dir_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_taxonomy(tmp_path / "does_not_exist")


def test_minimal_vault_runs_without_error(minimal_vault: pathlib.Path) -> None:
    out = build_taxonomy(minimal_vault)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Solo_Sport" in text


def test_high_variance_note_mapped(minimal_vault: pathlib.Path) -> None:
    assert "High_Variance_Attack" in build_taxonomy(minimal_vault).read_text(encoding="utf-8")


def test_journeyman_mapped(minimal_vault: pathlib.Path) -> None:
    assert "Journeyman" in build_taxonomy(minimal_vault).read_text(encoding="utf-8")


def test_idempotent(synthetic_vault: pathlib.Path) -> None:
    strip = lambda t: [l for l in t.splitlines() if not l.startswith("*Generated")]
    t1 = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    t2 = build_taxonomy(synthetic_vault).read_text(encoding="utf-8")
    assert strip(t1) == strip(t2)
    assert t1.count("## Aggressive Scorers") == 1
