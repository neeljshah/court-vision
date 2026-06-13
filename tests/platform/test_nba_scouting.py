"""tests.platform.test_nba_scouting — Tests for NBA scouting-synthesis generator.

Uses a tiny synthetic vault tree (a couple of Archetypes + a Trends overview).
No real parquets or network calls needed.

Run with:
    python -m pytest tests/platform/test_nba_scouting.py -q --timeout=120
"""
from __future__ import annotations

import pathlib
import re
import textwrap

import pytest

from domains.basketball_nba.memory_atlas_scouting import build_scouting

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_NAME_RE = re.compile(
    r"\b(jokic|embiid|doncic|lebron|curry|durant|wembanyama|brunson)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Synthetic vault notes
# ---------------------------------------------------------------------------

_ARCH_HIGH_USAGE = textwrap.dedent("""\
    ---
    tags:
      - sport/nba
      - archetype
    ---

    # High-Usage Creator

    [[Archetypes/_Archetypes_Index|Archetypes Index]] | [[_Index]]

    ## STYLE

    Ball-dominant guards/wings who generate offense for themselves and teammates via high usage + high AST%.

    ## SIGNATURE (Classification Thresholds)

    - **usage%**: >= 0.22
    - **ast%**: >= 0.20
    - **position**: Guard or Guard-Forward

    ## POPULATION

    - **Players fitting this archetype:** 59
    - **Typical position(s):** Guard / Forward / Forward-Guard

    #sport/nba #archetype #archetype/high_usage_creator
""")

_ARCH_3_AND_D = textwrap.dedent("""\
    ---
    tags:
      - sport/nba
      - archetype
    ---

    # 3-and-D Wing

    [[Archetypes/_Archetypes_Index|Archetypes Index]] | [[_Index]]

    ## STYLE

    Perimeter forwards who thrive as off-ball shooters and individual defenders.

    ## SIGNATURE (Classification Thresholds)

    - **usage%**: < 0.19
    - **ts%**: >= 0.55
    - **def_rtg**: <= 112

    ## POPULATION

    - **Players fitting this archetype:** 22
    - **Typical position(s):** Forward / Guard-Forward / Forward-Guard

    #sport/nba #archetype #archetype/three_and_d
""")

_TRENDS_OVERVIEW = textwrap.dedent("""\
    ---
    tags:
      - sport/nba
      - atlas/trends
    ---

    # NBA Archetype-Season Trends

    [[Archetypes/_Archetypes_Index|Archetypes]] | [[_Index]]

    ## Key Trend Findings

    - **3-and-D Wing** share rose 1.3pp.

    ## Archetype Share by Season (%)

    | Archetype | 2022-23 | 2024-25 | Δ first→last |
    | --- | --- | --- | --- |
    | High-Usage Creator | 10.9% | 11.4% | +0.5pp |
    | 3-and-D Wing | 3.4% | 4.7% | +1.3pp |

    ## League Efficiency by Season (team median)

    | Season | Off Rtg | Def Rtg | Net Rtg | Pace | eFG% |
    |--------|---------|---------|---------|------|------|
    | 2022-23 | 114.2 | 113.6 | 0.7 | 99.6 | 0.548 |
    | 2024-25 | 114.3 | 113.7 | 0.5 | 99.6 | 0.549 |

    #sport/nba #atlas/trends #archetype
""")

_ARCH_DEF_ANCHOR = textwrap.dedent("""\
    ---
    tags:
      - sport/nba
      - archetype
    ---

    # Defensive Anchor

    [[Archetypes/_Archetypes_Index|Archetypes Index]] | [[_Index]]

    ## STYLE

    Bigs who protect the rim and clean the glass.

    ## SIGNATURE (Classification Thresholds)

    - **position**: Center
    - **def_rtg**: <= 110
    - **reb%**: >= 0.10

    ## POPULATION

    - **Players fitting this archetype:** 30
    - **Typical position(s):** Center / Center-Forward

    #sport/nba #archetype
""")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def synthetic_vault(tmp_path: pathlib.Path) -> pathlib.Path:
    nba_root = tmp_path / "vault" / "Sports" / "Basketball_NBA"
    arch_dir = nba_root / "Archetypes"
    arch_dir.mkdir(parents=True)
    (nba_root / "Trends").mkdir(parents=True)
    (arch_dir / "High_Usage_Creator.md").write_text(_ARCH_HIGH_USAGE, encoding="utf-8")
    (arch_dir / "3_and_D_Wing.md").write_text(_ARCH_3_AND_D, encoding="utf-8")
    (nba_root / "Trends" / "_Trends_Overview.md").write_text(_TRENDS_OVERVIEW, encoding="utf-8")
    return nba_root


@pytest.fixture()
def scouting_out(tmp_path: pathlib.Path, synthetic_vault: pathlib.Path) -> list[pathlib.Path]:
    return build_scouting(out_dir=tmp_path / "Scouting", vault_nba_dir=synthetic_vault)


def _profile(paths: list[pathlib.Path], fragment: str) -> pathlib.Path:
    for p in paths:
        if fragment in p.name:
            return p
    pytest.skip(f"Profile '{fragment}' not found")


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

def test_returns_nonempty_list(scouting_out: list[pathlib.Path]) -> None:
    assert len(scouting_out) >= 1

def test_all_paths_exist(scouting_out: list[pathlib.Path]) -> None:
    for p in scouting_out:
        assert p.exists()

def test_index_written(scouting_out: list[pathlib.Path]) -> None:
    assert any(p.name == "_Scouting_Index.md" for p in scouting_out)

def test_two_profiles_from_two_archetypes(scouting_out: list[pathlib.Path]) -> None:
    profiles = [p for p in scouting_out if not p.name.startswith("_")]
    assert len(profiles) == 2

# ---------------------------------------------------------------------------
# Profile content
# ---------------------------------------------------------------------------

def test_signature_thresholds_present(scouting_out: list[pathlib.Path]) -> None:
    text = _profile(scouting_out, "High_Usage_Creator").read_text(encoding="utf-8")
    assert "0.22" in text and "0.20" in text

def test_style_present(scouting_out: list[pathlib.Path]) -> None:
    text = _profile(scouting_out, "High_Usage_Creator").read_text(encoding="utf-8")
    assert "ball-dominant" in text.lower() or "high usage" in text.lower()

def test_population_present(scouting_out: list[pathlib.Path]) -> None:
    text = _profile(scouting_out, "3_and_D_Wing").read_text(encoding="utf-8")
    assert "22" in text

def test_trend_data_synthesised(scouting_out: list[pathlib.Path]) -> None:
    text = _profile(scouting_out, "High_Usage_Creator").read_text(encoding="utf-8")
    assert "10.9" in text and "11.4" in text

def test_direction_label_present(scouting_out: list[pathlib.Path]) -> None:
    text = _profile(scouting_out, "3_and_D_Wing").read_text(encoding="utf-8")
    assert "Rising" in text

# ---------------------------------------------------------------------------
# Wikilink conventions
# ---------------------------------------------------------------------------

def test_wikilinks_are_bare_stem(scouting_out: list[pathlib.Path]) -> None:
    for p in scouting_out:
        for m in _WIKILINK_RE.finditer(p.read_text(encoding="utf-8")):
            target = m.group(1)
            assert "/" not in target, f"{p.name}: path separator in [[{target}]]"
            assert not target.endswith(".md"), f"{p.name}: .md suffix in [[{target}]]"

def test_profiles_link_to_archetypes_index(scouting_out: list[pathlib.Path]) -> None:
    for p in [q for q in scouting_out if not q.name.startswith("_")]:
        assert "_Archetypes_Index" in p.read_text(encoding="utf-8"), f"{p.name} missing _Archetypes_Index link"

def test_profiles_link_to_trends_overview(scouting_out: list[pathlib.Path]) -> None:
    for p in [q for q in scouting_out if not q.name.startswith("_")]:
        assert "_Trends_Overview" in p.read_text(encoding="utf-8"), f"{p.name} missing _Trends_Overview link"

def test_index_contains_both_archetypes(scouting_out: list[pathlib.Path]) -> None:
    idx = next(p for p in scouting_out if p.name == "_Scouting_Index.md")
    text = idx.read_text(encoding="utf-8")
    assert "High_Usage_Creator" in text and "3_and_D_Wing" in text

# ---------------------------------------------------------------------------
# No player names
# ---------------------------------------------------------------------------

def test_no_player_names_in_any_output(scouting_out: list[pathlib.Path]) -> None:
    for p in scouting_out:
        m = _NAME_RE.search(p.read_text(encoding="utf-8"))
        assert m is None, f"{p.name}: found player name '{m.group()}'"

# ---------------------------------------------------------------------------
# Graceful / edge cases
# ---------------------------------------------------------------------------

def test_missing_trends_does_not_raise(tmp_path: pathlib.Path) -> None:
    nba_root = tmp_path / "vault" / "Sports" / "Basketball_NBA"
    (nba_root / "Archetypes").mkdir(parents=True)
    (nba_root / "Archetypes" / "Defensive_Anchor.md").write_text(_ARCH_DEF_ANCHOR, encoding="utf-8")
    paths = build_scouting(out_dir=tmp_path / "Scouting_notrend", vault_nba_dir=nba_root)
    assert any(p.name == "Defensive_Anchor.md" for p in paths)

def test_empty_vault_returns_index(tmp_path: pathlib.Path) -> None:
    nba_root = tmp_path / "vault" / "Sports" / "Basketball_NBA"
    (nba_root / "Archetypes").mkdir(parents=True)
    paths = build_scouting(out_dir=tmp_path / "Scouting_empty", vault_nba_dir=nba_root)
    assert any(p.name == "_Scouting_Index.md" for p in paths)

def test_idempotent_double_run(tmp_path: pathlib.Path, synthetic_vault: pathlib.Path) -> None:
    out = tmp_path / "Scouting_idem"
    first = {p.name for p in build_scouting(out_dir=out, vault_nba_dir=synthetic_vault)}
    second = {p.name for p in build_scouting(out_dir=out, vault_nba_dir=synthetic_vault)}
    assert first == second
