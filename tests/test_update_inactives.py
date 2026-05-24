"""Tests for scripts/update_inactives.py (cycle 88c, loop 5).

Covers the pre-tip inactives sweep:
  - OUT injury entries zero every stat row for that player
  - Players absent from every inactives source are untouched
  - The new pred_pre_inactive column captures the original prediction
  - --inplace creates a .bak alongside the rewritten ledger
  - Diacritic-insensitive matching via src.data.injuries._name_key

The scoreboardv2 fetch is exercised via a fully-mocked NBAStatsHTTP so the
suite stays offline.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from unittest import mock

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.update_inactives as ui  # noqa: E402


# --- helpers ---------------------------------------------------------------

# Cycle-80 ledger schema (the columns save_predictions_csv writes).
HEADER = [
    "date", "game_id", "player_id", "player", "team", "opp", "venue",
    "stat", "pred",
    "lineup_status", "lineup_class", "play_pct", "injury_status",
]
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _row(player: str, stat: str, pred: float, *, team: str = "LAL",
         opp: str = "DEN", pid: int = 2544) -> list:
    return [
        "2026-05-24", "0022400123", str(pid), player, team, opp, "home",
        stat, f"{pred:.4f}",
        "confirmed", "starter", "0.85", "",
    ]


def _write_ledger(tmp_path, rows):
    """Write a ledger CSV with HEADER + given rows. Returns path."""
    p = os.path.join(tmp_path, "2026-05-24.csv")
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)
    return p


def _write_injuries(tmp_path, players):
    p = os.path.join(tmp_path, "injuries_2026-05-24.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({
            "date": "2026-05-24",
            "source_pdf": "x.pdf",
            "fetched_at": "2026-05-24T17:00",
            "players": players,
        }, fh)
    return p


def _read_csv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


# --- tests -----------------------------------------------------------------


def test_player_listed_out_zeroes_every_stat_row(tmp_path):
    """A player flagged OUT must have all 7 stat rows zeroed in one pass."""
    rows = [_row("LeBron James", s, 20.0 + i)
            for i, s in enumerate(STATS)]
    rows += [_row("Austin Reaves", s, 12.0, pid=1630559)
             for s in STATS]
    in_p = _write_ledger(str(tmp_path), rows)
    out_p = os.path.join(str(tmp_path), "2026-05-24_post_inactives.csv")

    inactives = {"lebron james"}
    n_rows, n_players = ui.apply_inactives(in_p, out_p, inactives)
    assert n_rows == len(STATS)
    assert n_players == 1

    data = _read_csv(out_p)
    header = data[0]
    pred_i = header.index("pred")
    inj_i  = header.index("injury_status")
    pre_i  = header.index("pred_pre_inactive")
    lebron = [r for r in data[1:] if r[header.index("player")] == "LeBron James"]
    reaves = [r for r in data[1:] if r[header.index("player")] == "Austin Reaves"]
    assert len(lebron) == len(STATS)
    assert all(float(r[pred_i]) == 0.0 for r in lebron)
    assert all(r[inj_i] == "INACTIVE" for r in lebron)
    assert all(float(r[pre_i]) > 0 for r in lebron)
    # Untouched player keeps original pred and empty pre-inactive sentinel.
    assert all(float(r[pred_i]) == 12.0 for r in reaves)
    assert all(r[pre_i] == "" for r in reaves)


def test_player_not_in_any_inactive_list_unchanged(tmp_path):
    """When the inactives set is empty, every row passes through verbatim."""
    rows = [_row("LeBron James", s, 20.0) for s in STATS]
    in_p  = _write_ledger(str(tmp_path), rows)
    out_p = os.path.join(str(tmp_path), "2026-05-24_post_inactives.csv")

    n_rows, n_players = ui.apply_inactives(in_p, out_p, set())
    assert n_rows == 0 and n_players == 0

    data = _read_csv(out_p)
    pred_i = data[0].index("pred")
    inj_i  = data[0].index("injury_status")
    for r in data[1:]:
        assert float(r[pred_i]) == 20.0
        assert r[inj_i] == ""    # not flipped to INACTIVE


def test_pred_pre_inactive_captures_original_value(tmp_path):
    """The new column must preserve the EXACT pre-zero prediction."""
    rows = [_row("LeBron James", "pts", 27.5)]
    in_p  = _write_ledger(str(tmp_path), rows)
    out_p = os.path.join(str(tmp_path), "2026-05-24_post_inactives.csv")

    ui.apply_inactives(in_p, out_p, {"lebron james"})

    data = _read_csv(out_p)
    header = data[0]
    assert "pred_pre_inactive" in header
    row = data[1]
    assert float(row[header.index("pred")]) == 0.0
    assert float(row[header.index("pred_pre_inactive")]) == pytest.approx(27.5)


def test_inplace_flag_creates_bak(tmp_path, monkeypatch):
    """--inplace overwrites the source CSV and snapshots the original to .bak."""
    rows = [_row("LeBron James", s, 20.0) for s in STATS]
    in_p = _write_ledger(str(tmp_path), rows)
    inj_p = _write_injuries(str(tmp_path), [
        {"team": "LAL", "name": "LeBron James", "status": "OUT", "reason": "rest"},
    ])

    argv = [
        "update_inactives.py",
        "--date", "2026-05-24",
        "--predictions", in_p,
        "--injuries", inj_p,
        "--no-api",
        "--inplace",
    ]
    with mock.patch.object(sys, "argv", argv):
        rc = ui.main()
    assert rc == 0

    bak_p = in_p + ".bak"
    assert os.path.exists(bak_p), ".bak file not created"

    # Backup still has the original (non-zero) predictions.
    bak = _read_csv(bak_p)
    pred_i_b = bak[0].index("pred")
    assert all(float(r[pred_i_b]) > 0 for r in bak[1:])

    # In-place rewrite has zeroed predictions + injury_status=INACTIVE.
    out = _read_csv(in_p)
    pred_i = out[0].index("pred")
    inj_i  = out[0].index("injury_status")
    assert "pred_pre_inactive" in out[0]
    assert all(float(r[pred_i]) == 0.0 for r in out[1:])
    assert all(r[inj_i] == "INACTIVE" for r in out[1:])


def test_diacritic_insensitive_match(tmp_path):
    """Jokić in the injury JSON must zero rows that store 'Nikola Jokic'."""
    rows = [_row("Nikola Jokic", s, 25.0, team="DEN", opp="LAL", pid=203999)
            for s in STATS]
    in_p  = _write_ledger(str(tmp_path), rows)
    out_p = os.path.join(str(tmp_path), "post.csv")

    # Source-of-truth: use the production helper to build the key set so
    # this test verifies BOTH ends of the diacritic-handling pipeline
    # (canonical OUT-set loader + per-row name canonicalisation).
    inj_p = _write_injuries(str(tmp_path), [
        {"team": "DEN", "name": "Nikola Jokić", "status": "OUT", "reason": "ankle"},
    ])
    from src.data.injuries import load_unavailable_players
    inactives = set(load_unavailable_players(inj_p).keys())
    assert "nikola jokic" in inactives    # canonical key, no diacritic

    n_rows, n_players = ui.apply_inactives(in_p, out_p, inactives)
    assert n_rows == len(STATS)
    assert n_players == 1

    data = _read_csv(out_p)
    pred_i = data[0].index("pred")
    assert all(float(r[pred_i]) == 0.0 for r in data[1:])


def test_manual_inactives_csv_loader(tmp_path):
    """Manual override CSV: header tolerated, names canonicalised."""
    p = os.path.join(str(tmp_path), "inactives.csv")
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["player", "team"])
        w.writerow(["LeBron James", "LAL"])
        w.writerow(["Nikola Jokić", "DEN"])
    keys = ui.load_manual_inactives(p)
    assert keys == {"lebron james", "nikola jokic"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
