"""Tests for scripts.platformkit.brain_drivers — the per-sport "what wins" builder.

Hermetic: injects SYNTHETIC post-mortem DataFrames (never reads real parquet) and
asserts the rendered markdown (a) is built per sport, (b) carries the honest banner
and the descriptive/leak note, (c) is person-free, and (d) passes the REAL no-edge
audit (scan_text == [] — W96 lesson: assert against the real audit, not a token list).
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.brain_drivers import build_drivers, _slug
from scripts.platformkit.brain_audit import scan_text


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


def test_builds_each_injected_sport(tmp_path):
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()},
                        organized_root=tmp_path, write=True)
    # only injected sports built; others skipped (hermetic — no real parquet read)
    assert set(k for k in rep if not k.startswith("_")) == {"NBA", "MLB"}
    assert rep["NBA"]["n_games"] == 13
    assert rep["MLB"]["n_games"] == 10
    # ranked by frequency: SHOOTING dominant for NBA, BIG_INNING for MLB
    assert rep["NBA"]["top"][0] == "SHOOTING"
    assert rep["MLB"]["top"][0] == "BIG_INNING"
    # files written
    assert (tmp_path / "NBA" / "_WhatWins.md").is_file()
    assert (tmp_path / "MLB" / "_WhatWins.md").is_file()
    assert (tmp_path / "NBA" / "Drivers" / "shooting.md").is_file()


def test_missing_sport_skipped_honestly():
    # inject only NBA -> MLB/Soccer/Tennis are skipped, not read from disk
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
        assert "descriptive" in ww.lower()           # leak/descriptive note present
        assert "as-of" in ww.lower()                 # names the leak-free companion
        for md in rep[sport]["driver_md"].values():
            assert "no edge claimed" in md.lower()
            assert "must not be used as a model feature" in md.lower()


def test_person_free():
    # synthetic frames carry no names; assert no team/player name nodes leak in.
    rep = build_drivers(injected={"NBA": _nba_pm(), "MLB": _mlb_pm()}, write=False)
    for sport in ("NBA", "MLB"):
        text = rep[sport]["whatwins_md"] + "".join(rep[sport]["driver_md"].values())
        # person-free: drivers are categories, not names; no '[[<digits>_' player node
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
