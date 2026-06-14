"""Tests for scripts.platformkit.brain_keystats — win-vs-loss box-stat separation.

Hermetic: builds a tiny synthetic ESPN box parquet in tmp (a few games, 2 teams,
win/loss derivable from the score columns) and asserts the rendered _KeyStats.md:
  (a) is written with a ranked separation table (stat | mean(win) | mean(loss) | d);
  (b) carries the honest descriptive/no-edge banner and passes the REAL no-edge audit;
  (c) resolves [[wikilinks]] to _WhatWins and _Index;
  (d) is person-free (no team ABBR / player proper-name NODES; only aggregate stats);
  (e) notes small-n honestly when the parquet is sparse;
  (f) is idempotent (re-run -> byte-identical) and skips a missing sport gracefully.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.brain_keystats import (
    build_keystats, _slug, _stat_columns, _separations, _to_team_games,
)
from scripts.platformkit.brain_audit import scan_text


# ---------------------------------------------------------------------------
# Synthetic ESPN-shaped box frame: a clean, recoverable win/loss separation.
# Home team scores more (and has higher bat_hits) in most games -> hits separates.
# ---------------------------------------------------------------------------

def _mlb_box() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": [f"g{i}" for i in range(8)],
        "home_abbr": ["AAA"] * 8,
        "away_abbr": ["BBB"] * 8,
        "home_score": [5, 6, 4, 7, 3, 8, 5, 6],
        "away_score": [2, 1, 3, 0, 4, 2, 1, 3],
        # winner (mostly home) has more hits -> strong positive separation
        "home_bat_hits": [10, 11, 9, 12, 6, 13, 10, 11],
        "away_bat_hits": [5, 4, 8, 3, 9, 5, 4, 7],
        # pitching strikeouts: winner slightly higher
        "home_pit_strikeouts": [8, 9, 7, 10, 5, 9, 8, 8],
        "away_pit_strikeouts": [6, 5, 7, 4, 8, 6, 5, 6],
        # an identity-ish column that must NOT be treated as a stat
        "status": ["STATUS_FINAL"] * 8,
        "venue": ["Park"] * 8,
    })


def _write_parquet(droot, df: pd.DataFrame) -> None:
    pq = droot / "data" / "domains" / "mlb" / "espn_boxscores.parquet"
    pq.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(pq, index=False)


# ---------------------------------------------------------------------------
# Pure-helper unit tests
# ---------------------------------------------------------------------------

def test_slug():
    assert _slug("bat_hits") == "bat_hits"
    assert _slug("Two Words") == "two_words"


def test_stat_columns_pairs_only_and_excludes_identity():
    cols = ["home_score", "away_score", "home_bat_hits", "away_bat_hits",
            "home_only_col", "status", "event_id"]
    stats = _stat_columns(cols)
    assert "bat_hits" in stats
    assert "score" not in stats          # identity, excluded
    assert "only_col" not in stats       # not paired (no away_)


def test_to_team_games_doubles_rows_and_derives_win():
    long = _to_team_games(_mlb_box(), ["bat_hits"])
    # 8 games -> 16 team-games, all decided (no ties)
    assert len(long) == 16
    assert set(long["won"].unique()) <= {0.0, 1.0}
    # wins should have higher mean hits than losses (by construction)
    assert long[long["won"] == 1.0]["bat_hits"].mean() > \
        long[long["won"] == 0.0]["bat_hits"].mean()


def test_separations_ranked_by_abs_descending():
    long = _to_team_games(_mlb_box(), ["bat_hits", "pit_strikeouts"])
    rows = _separations(long, ["bat_hits", "pit_strikeouts"])
    assert rows, "expected at least one computable separation"
    abss = [r["abs"] for r in rows]
    assert abss == sorted(abss, reverse=True)
    # bat_hits is engineered to be the strongest separator
    assert rows[0]["stat"] == "bat_hits"
    assert rows[0]["separation"] > 0       # higher in wins


# ---------------------------------------------------------------------------
# End-to-end write tests via the real parquet I/O path
# ---------------------------------------------------------------------------

def test_writes_keystats_with_ranked_table(tmp_path):
    droot = tmp_path / "repo"
    out = tmp_path / "out"
    _write_parquet(droot, _mlb_box())
    rep = build_keystats(organized_root=out, data_root=droot, write=True)

    assert rep["n_sports"] == 1
    # missing NBA / Soccer parquets skipped honestly
    assert rep["by_sport"]["NBA"]["skipped"] == "missing parquet"
    assert rep["by_sport"]["Soccer"]["skipped"] == "missing parquet"

    note = out / "MLB" / "_KeyStats.md"
    assert note.is_file()
    text = note.read_text(encoding="utf-8")
    # ranked table header present
    assert "mean(win)" in text and "mean(loss)" in text and "separation" in text.lower()
    # the engineered top separator appears in the table
    assert "`bat_hits`" in text
    # a ranked row "| 1 |" exists
    assert "| 1 |" in text


def test_keystats_resolving_wikilinks(tmp_path):
    droot = tmp_path / "repo"
    out = tmp_path / "out"
    _write_parquet(droot, _mlb_box())
    build_keystats(organized_root=out, data_root=droot, write=True)
    text = (out / "MLB" / "_KeyStats.md").read_text(encoding="utf-8")
    # sibling notes live at the sport root, so these resolve
    assert "[[_WhatWins" in text
    assert "[[_Index" in text


def test_keystats_person_free_no_team_or_player_nodes(tmp_path):
    droot = tmp_path / "repo"
    out = tmp_path / "out"
    _write_parquet(droot, _mlb_box())
    build_keystats(organized_root=out, data_root=droot, write=True)
    text = (out / "MLB" / "_KeyStats.md").read_text(encoding="utf-8")
    # team ABBRs from the parquet must NOT be written as nodes or names
    assert "AAA" not in text and "BBB" not in text
    # no per-team / per-player wikilinks
    assert "[[Teams/" not in text
    assert "[[Players/" not in text
    assert "/Players" not in text


def test_keystats_no_edge_tokens(tmp_path):
    droot = tmp_path / "repo"
    out = tmp_path / "out"
    _write_parquet(droot, _mlb_box())
    build_keystats(organized_root=out, data_root=droot, write=True)
    text = (out / "MLB" / "_KeyStats.md").read_text(encoding="utf-8")
    assert scan_text(text) == []
    assert "no edge claimed" in text.lower()
    assert "markets efficient" in text.lower()
    assert "calibration is not edge" in text.lower()


def test_keystats_small_n_caveat_present(tmp_path):
    droot = tmp_path / "repo"
    out = tmp_path / "out"
    _write_parquet(droot, _mlb_box())   # 8 games / 16 team-games -> sparse
    rep = build_keystats(organized_root=out, data_root=droot, write=True)
    assert rep["by_sport"]["MLB"]["small_n"] is True
    text = (out / "MLB" / "_KeyStats.md").read_text(encoding="utf-8")
    assert "indicative only" in text.lower()


def test_keystats_idempotent(tmp_path):
    droot = tmp_path / "repo"
    out = tmp_path / "out"
    _write_parquet(droot, _mlb_box())
    build_keystats(organized_root=out, data_root=droot, write=True)
    first = (out / "MLB" / "_KeyStats.md").read_text(encoding="utf-8")
    build_keystats(organized_root=out, data_root=droot, write=True)
    second = (out / "MLB" / "_KeyStats.md").read_text(encoding="utf-8")
    assert first == second


def test_missing_all_parquets_returns_empty_gracefully(tmp_path):
    rep = build_keystats(organized_root=tmp_path / "out",
                         data_root=tmp_path / "empty", write=True)
    assert rep["n_sports"] == 0
    assert all("skipped" in v for v in rep["by_sport"].values())
    assert "no edge claimed" in rep["_note"].lower()


def test_injected_frame_bypasses_io(tmp_path):
    out = tmp_path / "out"
    rep = build_keystats(organized_root=out, injected={"MLB": _mlb_box()}, write=True)
    assert rep["n_sports"] == 1
    assert (out / "MLB" / "_KeyStats.md").is_file()
    # only the injected sport is considered
    assert set(rep["by_sport"]) == {"MLB"}
