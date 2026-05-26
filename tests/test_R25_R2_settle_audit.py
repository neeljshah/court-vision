"""tests/test_R25_R2_settle_audit.py — R25_R2 settlement audit guards.

Covers:
  1. magnitude_bin classification
  2. probe categorise() — synthetic-only ASD + DNP split
  3. _load_full_box_player — present, missing player, missing file
  4. auto_settle_daemon.settle_game falls back to full-box (no false void)
  5. void_dnp_settles dry-run safety (no ledger mutation)
  6. void_dnp_settles idempotency (re-running dry-run = same plan)
  7. probe persists JSON with expected schema
"""
from __future__ import annotations

import json
import os
import sys
import shutil
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.auto_settle_daemon import (
    _load_full_box_player, settle_game, _match_player,
)
from scripts.improve_loop.probe_R25_R2_settle_disagreement_audit import (
    magnitude_bin, categorise,
)
from scripts.void_dnp_settles import run as void_run, classify, find_dnp_candidates
from scripts.reconcile_settlements import load_ledger


# --------------------------------------------------------------------------- #
# Tiny fixtures: hand-crafted ledger + quarter_box + full_box.                #
# --------------------------------------------------------------------------- #
@pytest.fixture
def tmp_dirs(tmp_path):
    qb = tmp_path / "qb"
    qb.mkdir()
    fb = tmp_path / "fb"
    fb.mkdir()
    return qb, fb


def _write_qb(qb, game_id, period, players):
    fn = qb / f"{game_id}_q{period}.json"
    fn.write_text(json.dumps({
        "game_id": game_id, "period": period,
        "players": players, "teams": [],
    }))
    return fn


def _write_full_box(fb, game_id, players):
    fn = fb / f"boxscore_{game_id}.json"
    fn.write_text(json.dumps({"game_id": game_id, "players": players}))
    return fn


# --------------------------------------------------------------------------- #
# 1. magnitude_bin classification                                             #
# --------------------------------------------------------------------------- #
def test_magnitude_bin_classifies_correctly():
    assert magnitude_bin(0.0)      == "<=0.5 (rounding)"
    assert magnitude_bin(0.5)      == "<=0.5 (rounding)"
    assert magnitude_bin(-0.5)     == "<=0.5 (rounding)"
    assert magnitude_bin(1.5)      == "0.5-2 (small)"
    assert magnitude_bin(-2.0)     == "0.5-2 (small)"
    assert magnitude_bin(3.0)      == "2-5 (medium)"
    assert magnitude_bin(-5.0)     == "2-5 (medium)"
    assert magnitude_bin(10.0)     == ">5 (large)"
    assert magnitude_bin(None)     == "unknown"


# --------------------------------------------------------------------------- #
# 2. _load_full_box_player: present, missing player, missing file             #
# --------------------------------------------------------------------------- #
def test_load_full_box_player_present(tmp_dirs):
    _, fb = tmp_dirs
    _write_full_box(fb, "0022400999", [
        {"player_id": 1234, "player_name": "Test Player",
         "team_abbreviation": "BOS", "pts": 12, "reb": 5, "ast": 3,
         "fg3m": 2, "stl": 1, "blk": 0, "to": 2},
    ])
    bet = {"player": "Test Player", "player_id": 1234}
    row = _load_full_box_player("0022400999", bet, fb)
    assert row is not None
    assert row["pts"] == 12.0
    assert row["reb"] == 5.0
    assert row["tov"] == 2.0  # 'to' -> 'tov' map
    assert row["player_id"] == 1234


def test_load_full_box_player_missing_player(tmp_dirs):
    _, fb = tmp_dirs
    _write_full_box(fb, "0022400999", [
        {"player_id": 1234, "player_name": "Someone Else",
         "team_abbreviation": "BOS", "pts": 0},
    ])
    bet = {"player": "Missing Guy", "player_id": 9999}
    assert _load_full_box_player("0022400999", bet, fb) is None


def test_load_full_box_player_missing_file(tmp_dirs):
    _, fb = tmp_dirs
    # No file written.
    bet = {"player": "Whoever", "player_id": 1}
    assert _load_full_box_player("0022400000", bet, fb) is None


# --------------------------------------------------------------------------- #
# 3. settle_game uses full-box fallback before voiding (R25_R2 fix)           #
# --------------------------------------------------------------------------- #
def test_settle_game_falls_back_to_full_box(tmp_dirs, monkeypatch):
    """If the player is missing from quarter_box but present in full box,
    the daemon must NOT void; it must settle against full-box totals."""
    qb, fb = tmp_dirs
    gid = "0022400999"
    # quarter_box has *other* players only.
    _write_qb(qb, gid, 1, [{"player_id": 5555, "player_name": "Other Guy",
                              "team_abbreviation": "LAL", "pts": 10,
                              "reb": 0, "ast": 0, "fg3m": 0, "stl": 0,
                              "blk": 0, "to": 0}])
    _write_qb(qb, gid, 2, [])
    _write_qb(qb, gid, 3, [])
    _write_qb(qb, gid, 4, [])
    # full box DOES include our garbage-time player.
    _write_full_box(fb, gid, [
        {"player_id": 1234, "player_name": "Garbage Time Guy",
         "team_abbreviation": "BOS", "pts": 2, "reb": 0, "ast": 0,
         "fg3m": 0, "stl": 0, "blk": 0, "to": 0},
        {"player_id": 5555, "player_name": "Other Guy",
         "team_abbreviation": "LAL", "pts": 10, "reb": 0, "ast": 0,
         "fg3m": 0, "stl": 0, "blk": 0, "to": 0},
    ])

    # Monkeypatch DEFAULT_FULL_BOX_DIR module-level.
    import scripts.auto_settle_daemon as asd
    monkeypatch.setattr(asd, "DEFAULT_FULL_BOX_DIR", fb)

    bet = {"bet_id": "bet1", "game_id": gid, "player": "Garbage Time Guy",
           "player_id": 1234, "stat": "pts"}

    result = settle_game(gid, qb_dir=qb, dry_run=True,
                          open_bets_by_game={gid: [bet]})
    # Should be SETTLED (via full-box fallback), not VOIDED.
    assert len(result["voided"]) == 0
    assert len(result["settled"]) == 1
    assert result["settled"][0]["actual_stat"] == 2.0


def test_settle_game_voids_when_truly_dnp(tmp_dirs, monkeypatch):
    """Both qb and full box missing the player -> void."""
    qb, fb = tmp_dirs
    gid = "0022400998"
    _write_qb(qb, gid, 1, [{"player_id": 5555, "player_name": "Other Guy",
                              "team_abbreviation": "LAL", "pts": 10,
                              "reb": 0, "ast": 0, "fg3m": 0, "stl": 0,
                              "blk": 0, "to": 0}])
    _write_full_box(fb, gid, [
        {"player_id": 5555, "player_name": "Other Guy",
         "team_abbreviation": "LAL", "pts": 10, "reb": 0, "ast": 0,
         "fg3m": 0, "stl": 0, "blk": 0, "to": 0},
    ])
    import scripts.auto_settle_daemon as asd
    monkeypatch.setattr(asd, "DEFAULT_FULL_BOX_DIR", fb)

    bet = {"bet_id": "bet2", "game_id": gid, "player": "True DNP Guy",
           "player_id": 7777, "stat": "pts"}
    result = settle_game(gid, qb_dir=qb, dry_run=True,
                          open_bets_by_game={gid: [bet]})
    assert len(result["voided"]) == 1
    assert result["voided"][0]["reason"] == "dnp_dryrun"


# --------------------------------------------------------------------------- #
# 4. void_dnp_settles dry-run safety + idempotency                            #
# --------------------------------------------------------------------------- #
def test_void_dnp_settles_dry_run_does_not_mutate_ledger(tmp_path, monkeypatch):
    """dry-run must never modify the ledger."""
    import csv as _csv
    qb = tmp_path / "qb"; qb.mkdir()
    fb = tmp_path / "fb"; fb.mkdir()
    gid = "0022400997"
    # QB has one player only (not our bet's player).
    _write_qb(qb, gid, 1, [{"player_id": 5555, "player_name": "Other Guy",
                              "team_abbreviation": "LAL", "pts": 10,
                              "reb": 0, "ast": 0, "fg3m": 0, "stl": 0,
                              "blk": 0, "to": 0}])
    # full box ALSO missing -> truly DNP candidate.
    _write_full_box(fb, gid, [
        {"player_id": 5555, "player_name": "Other Guy",
         "team_abbreviation": "LAL", "pts": 10, "reb": 0, "ast": 0,
         "fg3m": 0, "stl": 0, "blk": 0, "to": 0},
    ])
    ledger_path = tmp_path / "ledger.csv"
    fields = ["bet_id", "game_id", "player", "player_id", "stat", "line",
              "side", "status", "actual_stat", "placed_at"]
    with open(ledger_path, "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerow({"bet_id": "x1", "game_id": gid,
                     "player": "Truly DNP Guy", "player_id": "9999",
                     "stat": "pts", "line": "2.5", "side": "UNDER",
                     "status": "won", "actual_stat": "0",
                     "placed_at": "2025-01-01T00:00:00"})

    before_bytes = ledger_path.read_bytes()
    rpt = void_run(ledger_path=ledger_path, qb_dir=qb, full_box_dir=fb,
                    commit=False)
    after_bytes = ledger_path.read_bytes()
    assert before_bytes == after_bytes   # never mutated
    assert rpt["dry_run"] is True
    assert rpt["n_truly_dnp"] == 1
    assert rpt["n_voided"] == 0
    assert rpt["ledger_backup"] is None


def test_void_dnp_settles_idempotent_dry_run(tmp_path):
    """Two dry-runs in a row produce identical truly_dnp counts."""
    import csv as _csv
    qb = tmp_path / "qb"; qb.mkdir()
    fb = tmp_path / "fb"; fb.mkdir()
    gid = "0022400996"
    _write_qb(qb, gid, 1, [{"player_id": 5555, "player_name": "Other Guy",
                              "team_abbreviation": "LAL", "pts": 10,
                              "reb": 0, "ast": 0, "fg3m": 0, "stl": 0,
                              "blk": 0, "to": 0}])
    _write_full_box(fb, gid, [
        {"player_id": 5555, "player_name": "Other Guy",
         "team_abbreviation": "LAL", "pts": 10, "reb": 0, "ast": 0,
         "fg3m": 0, "stl": 0, "blk": 0, "to": 0},
    ])
    ledger_path = tmp_path / "ledger.csv"
    fields = ["bet_id", "game_id", "player", "player_id", "stat", "line",
              "side", "status", "actual_stat", "placed_at"]
    with open(ledger_path, "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for i in range(3):
            w.writerow({"bet_id": f"x{i}", "game_id": gid,
                         "player": "Truly DNP Guy", "player_id": "9999",
                         "stat": "pts", "line": "2.5", "side": "UNDER",
                         "status": "won", "actual_stat": "0",
                         "placed_at": "2025-01-01T00:00:00"})
    rpt1 = void_run(ledger_path=ledger_path, qb_dir=qb, full_box_dir=fb, commit=False)
    rpt2 = void_run(ledger_path=ledger_path, qb_dir=qb, full_box_dir=fb, commit=False)
    assert rpt1["n_truly_dnp"] == rpt2["n_truly_dnp"] == 3
    assert rpt1["n_player_did_play"] == rpt2["n_player_did_play"] == 0


# --------------------------------------------------------------------------- #
# 5. probe categorise() produces expected schema                              #
# --------------------------------------------------------------------------- #
def test_probe_categorise_returns_schema(tmp_path):
    import csv as _csv
    qb = tmp_path / "qb"; qb.mkdir()
    fb = tmp_path / "fb"; fb.mkdir()
    # Empty inputs -> probe still returns full schema with zero counts.
    ledger_path = tmp_path / "ledger.csv"
    fields = ["bet_id", "game_id", "player", "player_id", "stat", "line",
              "side", "status", "actual_stat", "placed_at"]
    with open(ledger_path, "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
    rows = load_ledger(ledger_path)
    report = categorise(rows, qb, fb)
    expected_keys = {
        "as_of", "ledger_path", "n_settled_rows",
        "n_actual_stat_disagreement", "n_player_dnp_but_settled",
        "asd_by_stat", "asd_by_synthetic", "asd_by_magnitude",
        "asd_by_month", "asd_by_sign", "asd_unique_games", "asd_top_games",
        "dnp_did_play", "dnp_truly", "top_failure_mode", "root_cause",
        "n_real_bugs", "n_data_artifacts", "fix_applied",
    }
    assert expected_keys.issubset(report.keys())
    assert report["n_settled_rows"] == 0
    assert report["n_actual_stat_disagreement"] == 0
    assert report["n_player_dnp_but_settled"] == 0
