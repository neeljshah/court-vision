"""tests/test_normalize_lines.py — adapter coverage for cycle-42 normalizer."""
from __future__ import annotations

import argparse
import csv
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.normalize_lines import normalize, write_canonical


def _write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def test_dk_adapter_maps_market_to_canonical_stat(tmp_path):
    src = tmp_path / "dk.csv"
    _write_csv(src,
        ["Player", "Team", "Opponent", "Market", "Line",
         "Over Odds", "Under Odds"],
        [
            ["Nikola Jokic",     "DEN", "LAL", "Points",          "28.5", "-115", "-105"],
            ["Anthony Edwards",  "MIN", "@DEN", "Assists",         "5.5",  "-110", "-110"],
            ["Stephen Curry",    "GSW", "BOS", "3-Pointers Made", "4.5",  "-120", "+100"],
        ],
    )
    out = normalize(str(src))
    assert len(out) == 3
    cols = set(out[0].keys())
    assert {"player", "opp", "venue", "stat", "line",
            "over_odds", "under_odds"}.issubset(cols)

    assert out[0]["player"] == "Nikola Jokic"
    assert out[0]["stat"] == "pts"
    assert out[0]["opp"] == "LAL"
    assert out[0]["venue"] == "home"
    assert out[0]["over_odds"] == -115
    assert out[0]["under_odds"] == -105

    # "@DEN" should flip venue to away and strip the @ from opp
    assert out[1]["opp"] == "DEN"
    assert out[1]["venue"] == "away"
    assert out[1]["stat"] == "ast"

    # "3-Pointers Made" -> "fg3m"; positive odds parse cleanly
    assert out[2]["stat"] == "fg3m"
    assert out[2]["over_odds"] == -120
    assert out[2]["under_odds"] == 100


def test_pp_adapter_defaults_odds_to_minus_110(tmp_path):
    src = tmp_path / "pp.csv"
    _write_csv(src,
        ["Player", "League", "Opp", "Stat Type", "Line"],
        [
            ["Jayson Tatum",   "NBA", "NYK", "Rebounds", "8.5"],
            ["Luka Doncic",    "NBA", "PHX", "Points",   "32.5"],
            ["Giannis Antetokounmpo", "NBA", "MIA", "Turnovers", "3.5"],
        ],
    )
    out = normalize(str(src))
    assert len(out) == 3
    assert all(r["over_odds"] == -110 and r["under_odds"] == -110 for r in out)
    assert out[0]["stat"] == "reb"
    assert out[1]["stat"] == "pts"
    assert out[2]["stat"] == "tov"
    assert out[0]["player"] == "Jayson Tatum"
    assert out[1]["line"] == "32.5"


def test_generic_adapter_with_custom_columns(tmp_path):
    src = tmp_path / "weird.csv"
    _write_csv(src,
        ["Athlete", "Foe", "Side", "PropType", "OU", "OvrPrice", "UndPrice"],
        [
            ["Nikola Jokic",     "LAL", "home", "Points",  "28.5", "-115", "-105"],
            ["Anthony Edwards",  "DEN", "away", "Steals",  "1.5",  "-110", "-110"],
            ["Bam Adebayo",      "BOS", "home", "blocks",  "1.0",  "-120", "+100"],
        ],
    )
    args = argparse.Namespace(
        player_col="Athlete",
        line_col="OU",
        stat_col="PropType",
        opp_col="Foe",
        venue_col="Side",
        over_col="OvrPrice",
        under_col="UndPrice",
    )
    out = normalize(str(src), fmt="generic", args=args)
    assert len(out) == 3
    assert out[0]["player"] == "Nikola Jokic"
    assert out[0]["stat"] == "pts"
    assert out[0]["venue"] == "home"
    assert out[1]["stat"] == "stl"
    assert out[1]["venue"] == "away"
    assert out[2]["stat"] == "blk"
    assert out[2]["under_odds"] == 100


def test_write_canonical_round_trips(tmp_path):
    src = tmp_path / "dk.csv"
    _write_csv(src,
        ["Player", "Team", "Opponent", "Market", "Line",
         "Over Odds", "Under Odds"],
        [["Nikola Jokic", "DEN", "LAL", "Points", "28.5", "-110", "-110"]],
    )
    out_path = tmp_path / "canon.csv"
    write_canonical(str(out_path), normalize(str(src)))
    with open(out_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["stat"] == "pts"
    assert rows[0]["line"] == "28.5"
