"""Tests for scripts.platformkit.brain_mechanisms — the factor-interaction layer.

Hermetic: injects SYNTHETIC post-mortem DataFrames (never reads real parquet) and
asserts that the rendered mechanism notes:
  (a) are built per sport with the expected slugs
  (b) carry the honest banner and calibration / no-edge framing
  (c) are person-free (no player/team names, no edge tokens)
  (d) pass the REAL no-edge audit (scan_text == [] per file — W96 pattern)
  (e) are skipped honestly for missing parquets
  (f) contain >=5 resolving [[wikilinks]] per note (densification requirement)
  (g) contain the densified sections: How it works, Archetype implications,
      Model-structure implication
  (h) index contains the sport cross-links (_WhatWins, Drivers, Archetypes, _Index)
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.brain_mechanisms import build_mechanisms
from scripts.platformkit.brain_audit import scan_text


# ── synthetic post-mortem fixtures ──────────────────────────────────────────

def _nba_pm() -> pd.DataFrame:
    """Minimal NBA post-mortem with pace + decided_by + margin."""
    n = 60
    import numpy as np  # noqa: PLC0415
    rng = np.random.default_rng(42)
    decided = (["SHOOTING"] * 30 + ["REBOUNDING"] * 12 + ["TURNOVERS"] * 10
               + ["FREE_THROWS"] * 5 + ["BALANCED"] * 3)
    pace = rng.uniform(94, 108, n).tolist()
    margin = rng.normal(3, 10, n).tolist()
    return pd.DataFrame({
        "decided_by": decided,
        "pace": pace,
        "margin": margin,
        "home_efg": rng.uniform(0.50, 0.58, n).tolist(),
        "away_efg": rng.uniform(0.49, 0.57, n).tolist(),
        "home_oreb_pct": rng.uniform(0.20, 0.35, n).tolist(),
        "away_oreb_pct": rng.uniform(0.20, 0.35, n).tolist(),
    })


def _mlb_pm() -> pd.DataFrame:
    """Minimal MLB post-mortem with sp_hand_matchup + decided_by + total_runs."""
    n = 80
    import numpy as np  # noqa: PLC0415
    rng = np.random.default_rng(7)
    decided = (["BIG_INNING"] * 55 + ["BLOWOUT"] * 10 + ["SP_DUEL"] * 10
               + ["ROUTINE"] * 5)
    matchup = (["RR"] * 32 + ["LL"] * 16 + ["RL"] * 16 + ["LR"] * 16)
    total_runs = rng.integers(2, 16, n).tolist()
    return pd.DataFrame({
        "decided_by": decided,
        "sp_hand_matchup": matchup,
        "total_runs": total_runs,
        "home_big_inning_share": rng.uniform(0.30, 0.75, n).tolist(),
        "margin": rng.integers(1, 10, n).tolist(),
    })


def _soccer_pm() -> pd.DataFrame:
    """Minimal soccer post-mortem with red_flags + ht_flip + decided_by."""
    n = 100
    import numpy as np  # noqa: PLC0415
    rng = np.random.default_rng(3)
    decided = (["ROUTINE"] * 36 + ["FINISHING_VARIANCE"] * 21
               + ["TERRITORIAL_CONTROL"] * 17 + ["RED_CARD_SWING"] * 12
               + ["HT_COLLAPSE"] * 5 + ["DOMINANT_BUT_DREW"] * 5
               + ["HT_COMEBACK"] * 4)
    red_flags = [True] * 12 + [False] * 88
    ht_flip = [True] * 15 + [False] * 85
    return pd.DataFrame({
        "decided_by": decided,
        "red_flags": red_flags,
        "ht_flip": ht_flip,
        "sot_diff": rng.normal(0, 3, n).tolist(),
        "finishing_residual_home": rng.normal(0, 1, n).tolist(),
        "finishing_residual_away": rng.normal(0, 1, n).tolist(),
    })


def _tennis_pm() -> pd.DataFrame:
    """Minimal tennis post-mortem with surface + decided_by + match stats."""
    n = 120
    import numpy as np  # noqa: PLC0415
    rng = np.random.default_rng(11)
    decided = (["BLOWOUT"] * 35 + ["BP_CONVERSION_EDGE"] * 26
               + ["BROKE_LATE"] * 18 + ["ROUTINE"] * 12
               + ["THREE_SET_GRIND"] * 12 + ["TIEBREAK_SWING"] * 10
               + ["SURFACE_MISMATCH"] * 5 + ["RETIREMENT"] * 2)
    surface = ["Hard"] * 55 + ["Clay"] * 40 + ["Grass"] * 25
    return pd.DataFrame({
        "decided_by": decided,
        "surface": surface,
        "p1_aces": rng.uniform(3, 14, n).tolist(),
        "p2_aces": rng.uniform(3, 14, n).tolist(),
        "p1_bp_conv_pct": rng.uniform(0.30, 0.55, n).tolist(),
        "p2_bp_conv_pct": rng.uniform(0.30, 0.55, n).tolist(),
        "n_tiebreaks": rng.integers(0, 3, n).tolist(),
        "n_breaks": rng.integers(1, 8, n).tolist(),
        "minutes": rng.uniform(50, 200, n).tolist(),
    })


# ── tests ─────────────────────────────────────────────────────────────────────

def test_builds_each_injected_sport(tmp_path):
    injected = {
        "NBA": _nba_pm(),
        "MLB": _mlb_pm(),
        "Soccer": _soccer_pm(),
        "Tennis": _tennis_pm(),
    }
    rep = build_mechanisms(injected=injected, organized_root=tmp_path, write=True)
    sports = {k for k in rep if not k.startswith("_")}
    assert sports == {"NBA", "MLB", "Soccer", "Tennis"}
    for sport in sports:
        assert rep[sport]["n_mechanisms"] >= 1


def test_mechanisms_files_written(tmp_path):
    injected = {"NBA": _nba_pm(), "MLB": _mlb_pm()}
    build_mechanisms(injected=injected, organized_root=tmp_path, write=True)
    nba_dir = tmp_path / "NBA" / "Mechanisms"
    assert nba_dir.is_dir()
    slugs = {p.stem for p in nba_dir.glob("*.md")}
    assert "_Mechanisms" in slugs  # index written
    assert len(slugs) >= 3  # index + at least 2 mechanism files

    mlb_dir = tmp_path / "MLB" / "Mechanisms"
    assert mlb_dir.is_dir()
    assert (mlb_dir / "_Mechanisms.md").is_file()


def test_missing_sport_skipped_honestly():
    """With only NBA injected, MLB/Soccer/Tennis are never read from disk."""
    rep = build_mechanisms(injected={"NBA": _nba_pm()}, write=False)
    sports = {k for k in rep if not k.startswith("_")}
    assert sports == {"NBA"}
    assert rep["NBA"]["n_mechanisms"] >= 1


def test_no_decided_by_column_skipped():
    bad = pd.DataFrame({"pace": [100.0, 98.0, 102.0]})
    rep = build_mechanisms(injected={"NBA": bad}, write=False)
    assert rep["NBA"]["skipped"] == "no decided_by column"


def test_honest_banner_present():
    rep = build_mechanisms(injected={"NBA": _nba_pm(), "Soccer": _soccer_pm()},
                           write=False)
    for sport in ("NBA", "Soccer"):
        idx_md = rep[sport]["index_md"]
        assert "no edge claimed" in idx_md.lower()
        assert "not a market edge" in idx_md.lower()
        for md in rep[sport]["rendered"].values():
            assert "no edge claimed" in md.lower()
            assert "not a market edge" in md.lower()


def test_descriptive_and_calibration_framing():
    """Each rendered file must reference calibration + descriptive framing."""
    rep = build_mechanisms(injected={"NBA": _nba_pm()}, write=False)
    for md in rep["NBA"]["rendered"].values():
        lower = md.lower()
        # calibration or leak-free framing present
        assert "calibration" in lower or "leak-free" in lower
        # post-mortems are descriptive
        assert "descriptive" in lower or "realized" in lower


def test_person_free():
    """Mechanism notes must not reference player or team nodes."""
    rep = build_mechanisms(
        injected={"NBA": _nba_pm(), "MLB": _mlb_pm(),
                  "Soccer": _soccer_pm(), "Tennis": _tennis_pm()},
        write=False,
    )
    for sport in ("NBA", "MLB", "Soccer", "Tennis"):
        all_text = rep[sport]["index_md"] + "".join(
            rep[sport]["rendered"].values())
        assert "Players/" not in all_text
        assert "Teams/" not in all_text


def test_rendered_markdown_passes_real_no_edge_audit():
    """W96 lesson: assert against the REAL audit, not a hand-maintained list."""
    rep = build_mechanisms(
        injected={"NBA": _nba_pm(), "MLB": _mlb_pm(),
                  "Soccer": _soccer_pm(), "Tennis": _tennis_pm()},
        write=False,
    )
    for sport in ("NBA", "MLB", "Soccer", "Tennis"):
        hits = scan_text(rep[sport]["index_md"])
        assert hits == [], f"{sport} _Mechanisms.md flagged: {hits}"
        for slug, md in rep[sport]["rendered"].items():
            hits = scan_text(md)
            assert hits == [], f"{sport}/{slug}.md flagged: {hits}"


def test_index_contains_all_slugs():
    rep = build_mechanisms(injected={"Tennis": _tennis_pm()}, write=False)
    idx = rep["Tennis"]["index_md"]
    for slug in rep["Tennis"]["slugs"]:
        assert slug in idx, f"slug '{slug}' missing from Tennis index"


def test_write_false_no_files(tmp_path):
    """write=False must not produce any files."""
    build_mechanisms(injected={"NBA": _nba_pm()},
                     organized_root=tmp_path, write=False)
    assert not (tmp_path / "NBA").exists()


# ── densification tests (new requirements) ───────────────────────────────────

import re as _re

_WL_RE = _re.compile(r"\[\[([^\]]+)\]\]")
_REQUIRED_NOTE_LINKS = ["_Mechanisms", "_WhatWins", "Drivers", "Archetypes/_Archetypes_Index", "_Index"]
_REQUIRED_SECTIONS = ["## How it works", "## Archetype / style implications",
                      "## Model-structure implication", "## Empirical conditional frequencies", "## Links"]
_REQUIRED_IDX_LINKS = ["_WhatWins", "Drivers", "Archetypes/_Archetypes_Index", "_Index"]
_ALL_SPORTS = {"NBA": _nba_pm, "MLB": _mlb_pm, "Soccer": _soccer_pm, "Tennis": _tennis_pm}


def _rep_all():
    return build_mechanisms(injected={s: f() for s, f in _ALL_SPORTS.items()}, write=False)


def _all_rendered(rep):
    return [(sp, slug, md) for sp, info in rep.items()
            if not sp.startswith("_") and "skipped" not in info
            for slug, md in info["rendered"].items()]


def test_wikilink_count_per_note():
    """Each mechanism note must contain >= 5 resolving [[wikilinks]]."""
    for sport, slug, md in _all_rendered(_rep_all()):
        links = _WL_RE.findall(md)
        assert len(links) >= 5, f"{sport}/{slug}.md: only {len(links)} wikilinks (need >=5): {links}"


def test_required_cross_links_in_notes():
    """Each mechanism note must link to _Mechanisms, _WhatWins, Drivers, Archetypes, _Index."""
    for sport, slug, md in _all_rendered(_rep_all()):
        found = " ".join(_WL_RE.findall(md))
        for target in _REQUIRED_NOTE_LINKS:
            assert target in found, f"{sport}/{slug}.md missing wikilink to '{target}'"


def test_densified_sections_present():
    """Each mechanism note must contain all required section headers."""
    for sport, slug, md in _all_rendered(_rep_all()):
        for section in _REQUIRED_SECTIONS:
            assert section in md, f"{sport}/{slug}.md missing section '{section}'"


def test_archetype_section_has_favors_and_suppresses():
    """Archetype section must have **Favors**: and **Suppresses**: labels."""
    for sport, slug, md in _all_rendered(_rep_all()):
        assert "**Favors**:" in md, f"{sport}/{slug}.md missing '**Favors**:'"
        assert "**Suppresses**:" in md, f"{sport}/{slug}.md missing '**Suppresses**:'"


def test_model_structure_implication_non_empty():
    """Model-structure implication section must contain real calibration text (not just '—')."""
    for sport, slug, md in _all_rendered(_rep_all()):
        idx = md.find("## Model-structure implication")
        assert idx != -1, f"{sport}/{slug}.md missing model-structure section"
        snippet = md[idx:idx + 300]
        real_lines = [l.strip() for l in snippet.split("\n")[1:4] if l.strip() not in ("", "—")]
        assert real_lines, f"{sport}/{slug}.md model-structure section is empty or just '—'"


def test_index_contains_required_cross_links():
    """_Mechanisms.md index must contain all required cross-links."""
    rep = build_mechanisms(injected={"NBA": _nba_pm(), "Soccer": _soccer_pm()}, write=False)
    for sport in ("NBA", "Soccer"):
        found = " ".join(_WL_RE.findall(rep[sport]["index_md"]))
        for target in _REQUIRED_IDX_LINKS:
            assert target in found, f"{sport}/_Mechanisms.md missing cross-link to '{target}'"


def test_no_proper_names_in_mechanisms():
    """Mechanism notes and index must not reference Players/ or Teams/ vault paths."""
    rep = _rep_all()
    for sport, slug, md in _all_rendered(rep):
        assert "Players/" not in md and "Teams/" not in md, \
            f"{sport}/{slug}.md contains person/team vault reference"
    for sport in _ALL_SPORTS:
        idx = rep[sport]["index_md"]
        assert "Players/" not in idx and "Teams/" not in idx, \
            f"{sport}/_Mechanisms.md index contains person/team vault reference"
