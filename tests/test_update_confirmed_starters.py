"""tests for scripts/update_confirmed_starters.py (cycle 88d).

Exercises the pure update_row() atom plus the CSV pipeline on a
synthetic predictions ledger -- no nba_api / network calls.
"""
from __future__ import annotations

import csv
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.update_confirmed_starters import (  # noqa: E402
    update_row,
    update_predictions_csv,
    _name_key,
)


# -- fixtures ---------------------------------------------------------------

def _row(**overrides):
    base = {
        "date":           "2026-05-24",
        "game_id":        "0022500001",
        "player_id":      "203999",
        "player":         "Nikola Jokic",
        "team":           "DEN",
        "opp":            "LAL",
        "venue":          "home",
        "stat":           "PTS",
        "pred":           "27.8000",
        "lineup_status":  "Projected",
        "lineup_class":   "starter",
        "play_pct":       "100",
        "injury_status":  "",
    }
    base.update(overrides)
    return base


# -- update_row -------------------------------------------------------------

def test_promotion_bench_to_starter():
    """Projected bench player who appears in the official confirmed 5 ->
    lineup_class flips to 'starter' and any [TAG] is stripped."""
    row = _row(player="Christian Braun [BENCH]", lineup_class="bench")
    confirmed = {"DEN": {_name_key("Christian Braun"),
                          _name_key("Nikola Jokic")}}
    out = update_row(row, confirmed)
    assert out["lineup_class"] == "starter"
    assert out["player"] == "Christian Braun"


def test_demotion_starter_to_bench():
    """Projected starter NOT in the official 5 -> demoted to bench."""
    row = _row(player="Russell Westbrook", team="DEN", lineup_class="starter")
    confirmed = {"DEN": {_name_key("Nikola Jokic"),
                          _name_key("Jamal Murray"),
                          _name_key("Aaron Gordon"),
                          _name_key("Michael Porter Jr."),
                          _name_key("Christian Braun")}}
    out = update_row(row, confirmed)
    assert out["lineup_class"] == "bench"


def test_unchanged_starter_stays():
    """Confirmed starter already classed as starter -> no class change."""
    row = _row(player="Nikola Jokic", team="DEN", lineup_class="starter",
               lineup_status="Confirmed")
    confirmed = {"DEN": {_name_key("Nikola Jokic")}}
    out = update_row(row, confirmed)
    assert out["lineup_class"] == "starter"
    assert out["lineup_status"] == "Confirmed"
    assert out["player"] == "Nikola Jokic"


def test_status_bumps_projected_to_confirmed():
    """Same player, no class change, but rotowire hardened the status badge."""
    row = _row(player="Jamal Murray", team="DEN",
               lineup_class="starter", lineup_status="Projected")
    confirmed = {}   # confirmed feed hasn't dropped yet
    lineups = {_name_key("Jamal Murray"): "Confirmed"}
    out = update_row(row, confirmed, lineups_status_by_name=lineups)
    assert out["lineup_status"] == "Confirmed"
    assert out["lineup_class"] == "starter"   # unchanged


def test_diacritic_insensitive_match():
    """Stored name with diacritics matches a confirmed-5 entry without."""
    row = _row(player="Nikola Jokic", team="DEN", lineup_class="bench")
    confirmed = {"DEN": {_name_key("Nikola Jokic")}}  # "jokic" with accent normalised
    out = update_row(row, confirmed)
    assert out["lineup_class"] == "starter"


def test_no_confirmed_feed_holds_class_steady():
    """When the confirmed dict is empty for the team, class is left as-is
    even if status bumps."""
    row = _row(player="Jamal Murray", lineup_class="bench",
               lineup_status="Projected")
    out = update_row(row, {}, lineups_status_by_name={
        _name_key("Jamal Murray"): "Confirmed",
    })
    assert out["lineup_class"] == "bench"
    assert out["lineup_status"] == "Confirmed"


def test_status_never_downgrades():
    """A row already marked Confirmed must not regress to Expected."""
    row = _row(player="Jamal Murray", lineup_status="Confirmed")
    out = update_row(row, {}, lineups_status_by_name={
        _name_key("Jamal Murray"): "Expected",
    })
    assert out["lineup_status"] == "Confirmed"


# -- CSV pipeline -----------------------------------------------------------

def test_update_predictions_csv_counters(tmp_path):
    """End-to-end on a synthetic CSV exercises both promotion + demotion
    paths and verifies the summary counters."""
    in_path = tmp_path / "preds.csv"
    out_path = tmp_path / "preds.updated.csv"
    rows = [
        _row(player="Nikola Jokic", team="DEN", lineup_class="starter"),
        _row(player="Russell Westbrook", team="DEN", lineup_class="starter",
             stat="AST", pred="6.1000"),
        _row(player="Christian Braun [BENCH]", team="DEN",
             lineup_class="bench", stat="PTS", pred="11.2000"),
    ]
    fieldnames = list(rows[0].keys())
    with open(in_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    confirmed = {"DEN": {_name_key("Nikola Jokic"),
                          _name_key("Christian Braun")}}

    n, promoted, demoted = update_predictions_csv(
        str(in_path), str(out_path), confirmed,
    )
    assert n == 3
    assert promoted == 1
    assert demoted == 1

    with open(out_path, encoding="utf-8") as fh:
        result = list(csv.DictReader(fh))
    classes = {r["player"]: r["lineup_class"] for r in result}
    assert classes["Nikola Jokic"] == "starter"
    assert classes["Russell Westbrook"] == "bench"
    assert classes["Christian Braun"] == "starter"   # tag stripped on promote


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
