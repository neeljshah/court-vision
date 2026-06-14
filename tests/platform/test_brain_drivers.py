"""Tests for scripts.platformkit.brain_drivers — the per-sport "what wins" builder.

Hermetic: injects SYNTHETIC post-mortem DataFrames (never reads real parquet) and
asserts the rendered markdown:
  (a) is built per sport with correct counts / ranking;
  (b) carries the honest banner and descriptive/leak note;
  (c) is person-free (no Players/ or Teams/ links);
  (d) passes the REAL no-edge audit (scan_text == []);
  (e) [NEW] contains the densified "Why it wins" + "Model implication" sections;
  (f) [NEW] contains >=3 [[wikilinks]] per driver note linking to sibling nodes;
  (g) [NEW] _WhatWins links to each driver note in the ranked table;
  (h) [NEW] MLB/Soccer driver notes contain archetype wikilinks; NBA/Tennis do not.
"""
from __future__ import annotations
import re

import pandas as pd

from scripts.platformkit.brain_drivers import build_drivers, _slug
from scripts.platformkit.brain_audit import scan_text


# ---------------------------------------------------------------------------
# Synthetic post-mortem fixtures
# ---------------------------------------------------------------------------

def _nba_pm() -> pd.DataFrame:
    return pd.DataFrame({
        "decided_by": (["SHOOTING"] * 6 + ["REBOUNDING"] * 3 + ["TURNOVERS"] * 2
                       + ["FREE_THROWS"] + ["BALANCED"]),
        "margin": [10, 8, 12, 6, 9, 11, 7, 5, 6, 4, 3, 2, 1],
        "contrib_shooting": [3.0] * 13,
    })


def _mlb_pm() -> pd.DataFrame:
    return pd.DataFrame({
        "decided_by": ["BIG_INNING"] * 5 + ["BLOWOUT"] * 2 + ["SP_DUEL"] * 2 + ["ROUTINE"],
        "margin": [3, 2, 4, 5, 1, 9, 8, 1, 2, 3],
        "total_runs": [9, 7, 8, 10, 6, 14, 12, 3, 4, 7],
    })


def _soccer_pm() -> pd.DataFrame:
    return pd.DataFrame({
        "decided_by": (["FINISHING_VARIANCE"] * 4 + ["TERRITORIAL_CONTROL"] * 3
                       + ["ROUTINE"] * 2 + ["RED_CARD_SWING"]),
        "sot_diff": [2, 3, 1, 4, 5, 6, 3, 1, 2, 4],
    })


def _tennis_pm() -> pd.DataFrame:
    return pd.DataFrame({
        "decided_by": (["BLOWOUT"] * 4 + ["TIEBREAK_SWING"] * 3
                       + ["ROUTINE"] * 2 + ["THREE_SET_GRIND"]),
        "n_breaks": [4, 5, 4, 6, 1, 2, 1, 2, 3, 3],
    })


# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------

def test_builds_each_injected_sport(tmp_path):
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()},
                        organized_root=tmp_path, write=True)
    assert set(k for k in rep if not k.startswith("_")) == {"NBA", "MLB"}
    assert rep["NBA"]["n_games"] == 13
    assert rep["MLB"]["n_games"] == 10
    assert rep["NBA"]["top"][0] == "SHOOTING"
    assert rep["MLB"]["top"][0] == "BIG_INNING"
    assert (tmp_path / "NBA" / "_WhatWins.md").is_file()
    assert (tmp_path / "MLB" / "_WhatWins.md").is_file()
    assert (tmp_path / "NBA" / "Drivers" / "shooting.md").is_file()


def test_missing_sport_skipped_honestly():
    rep = build_drivers(injected={"NBA": _nba_pm()}, write=False)
    assert rep["NBA"]["n_games"] == 13
    assert all(k in ("NBA", "_note") for k in rep)


def test_no_decided_by_column_skipped():
    bad = pd.DataFrame({"margin": [1, 2, 3]})
    rep = build_drivers(injected={"NBA": bad}, write=False)
    assert rep["NBA"]["skipped"] == "no decided_by column"


def test_rendered_markdown_has_honest_banner_and_leak_note():
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        ww = rep[sport]["whatwins_md"]
        assert "no edge claimed" in ww.lower()
        assert "not a market edge" in ww.lower()
        assert "descriptive" in ww.lower()
        assert "as-of" in ww.lower()
        for md in rep[sport]["driver_md"].values():
            assert "no edge claimed" in md.lower()
            assert "must not be used as a model feature" in md.lower()


def test_person_free():
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        text = rep[sport]["whatwins_md"] + "".join(rep[sport]["driver_md"].values())
        assert "Players" not in text
        assert "Teams/" not in text


def test_rendered_markdown_passes_real_no_edge_audit():
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        assert scan_text(rep[sport]["whatwins_md"]) == []
        for md in rep[sport]["driver_md"].values():
            assert scan_text(md) == []


def test_slug():
    assert _slug("BIG_INNING") == "big_inning"
    assert _slug("Three Set") == "three_set"


# ---------------------------------------------------------------------------
# NEW: densified-content assertions
# ---------------------------------------------------------------------------

def _count_wikilinks(text: str) -> int:
    """Count [[...]] wikilink occurrences."""
    return len(re.findall(r"\[\[", text))


def test_driver_notes_contain_densified_sections():
    """Each driver note must have 'Why it wins' and 'Model implication' headings."""
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        for label, md in rep[sport]["driver_md"].items():
            assert "## Why it wins" in md, f"{sport}/{label} missing 'Why it wins'"
            assert "## Model implication" in md, f"{sport}/{label} missing 'Model implication'"


def test_driver_notes_have_minimum_wikilinks():
    """Every driver note must contain >=3 [[wikilinks]] to sibling nodes."""
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        for label, md in rep[sport]["driver_md"].items():
            n = _count_wikilinks(md)
            assert n >= 3, f"{sport}/{label} has only {n} wikilinks (need >=3)"


def test_driver_notes_link_to_sibling_nodes():
    """Driver notes must link to _WhatWins, _Mechanisms, and _Index."""
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        for label, md in rep[sport]["driver_md"].items():
            assert "_WhatWins" in md, f"{sport}/{label} missing _WhatWins link"
            assert "_Mechanisms" in md, f"{sport}/{label} missing _Mechanisms link"
            assert "_Index" in md, f"{sport}/{label} missing _Index link"


def test_whatwins_links_to_driver_notes():
    """_WhatWins ranked table must link to each driver note via [[Drivers/<slug>|...]]."""
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        ww = rep[sport]["whatwins_md"]
        for label in rep[sport]["top"]:
            slug = _slug(label)
            assert f"[[Drivers/{slug}" in ww, (
                f"{sport}/_WhatWins.md missing link [[Drivers/{slug}...]] for '{label}'")


def test_whatwins_contains_sibling_links():
    """_WhatWins must link to _Mechanisms and _Index."""
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        ww = rep[sport]["whatwins_md"]
        assert "_Mechanisms" in ww, f"{sport}/_WhatWins.md missing _Mechanisms link"
        assert "_Index" in ww, f"{sport}/_WhatWins.md missing _Index link"
        n = _count_wikilinks(ww)
        # At least: one per row driver + _Mechanisms + _Index
        assert n >= len(rep[sport]["top"]) + 2, (
            f"{sport}/_WhatWins.md has only {n} wikilinks")


def test_mlb_driver_notes_contain_archetype_link():
    """MLB driver notes must link to the Pitcher Archetypes computed index."""
    rep = build_drivers(injected={"MLB": _mlb_pm()}, write=False)
    for label, md in rep["MLB"]["driver_md"].items():
        assert "_Computed_Index" in md, f"MLB/{label} missing archetype _Computed_Index link"


def test_nba_driver_notes_have_no_archetype_link():
    """NBA has no archetypes — driver notes must NOT contain _Computed_Index."""
    rep = build_drivers(injected={"NBA": _nba_pm()}, write=False)
    for label, md in rep["NBA"]["driver_md"].items():
        assert "_Computed_Index" not in md, f"NBA/{label} should not have archetype link"


def test_soccer_and_tennis_densified_sections(tmp_path):
    """Soccer and Tennis driver notes also get Why/Implication and >=3 wikilinks."""
    rep = build_drivers(
        injected={"Soccer": _soccer_pm(), "Tennis": _tennis_pm()},
        organized_root=tmp_path, write=True)
    for sport in ("Soccer", "Tennis"):
        for label, md in rep[sport]["driver_md"].items():
            assert "## Why it wins" in md, f"{sport}/{label} missing 'Why it wins'"
            assert "## Model implication" in md, f"{sport}/{label} missing 'Model implication'"
            assert _count_wikilinks(md) >= 3, f"{sport}/{label} <3 wikilinks"
        assert (tmp_path / sport / "_WhatWins.md").is_file()
        assert (tmp_path / sport / "Drivers").is_dir()


def test_soccer_driver_notes_contain_archetype_link():
    """Soccer driver notes must link to Team Style Archetypes computed index."""
    rep = build_drivers(injected={"Soccer": _soccer_pm()}, write=False)
    for label, md in rep["Soccer"]["driver_md"].items():
        assert "_Computed_Index" in md, f"Soccer/{label} missing archetype link"


def test_no_edge_tokens_across_all_sports():
    """All four sports must pass the no-edge audit (scan_text == [])."""
    rep = build_drivers(
        injected={"NBA": _nba_pm(), "MLB": _mlb_pm(),
                  "Soccer": _soccer_pm(), "Tennis": _tennis_pm()},
        write=False)
    for sport in ("NBA", "MLB", "Soccer", "Tennis"):
        assert scan_text(rep[sport]["whatwins_md"]) == [], f"{sport} _WhatWins failed audit"
        for label, md in rep[sport]["driver_md"].items():
            assert scan_text(md) == [], f"{sport}/{label} failed no-edge audit"
