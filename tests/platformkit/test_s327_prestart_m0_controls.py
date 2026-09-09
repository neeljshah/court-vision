"""Additive S327 attempt-2 controls for team-agreement-only joins."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from scripts.platformkit.ingame.prestart_m0_controls import collision_census, dedupe_by_event_key, permute_dates
from scripts.platformkit.ingame.prestart_m0_table import _write, build_table, state_events


def _events():
    return state_events([
        {"game_id": "e0", "home_team": "AAA", "away_team": "BBB", "date": "2026-01-01"},
        {"game_id": "e1", "home_team": "CCC", "away_team": "DDD", "date": "2026-01-02"},
        {"game_id": "e2", "home_team": "EEE", "away_team": "FFF", "date": "2026-01-03"},
        {"game_id": "e3", "home_team": "GGG", "away_team": "HHH", "date": "2026-01-04"},
        {"game_id": "e4", "home_team": "III", "away_team": "JJJ", "date": "2026-01-05"},
        {"game_id": "e5", "home_team": "KKK", "away_team": "LLL", "date": "2026-01-06"},
    ], "mlb")


def test_seeded_date_control_kills_team_agreement_joins():
    quotes = [
        {"date": "2026-01-01", "home": "AAA", "away": "BBB", "ts": 1, "prob": 0.51},
        {"date": "2026-01-02", "home": "CCC", "away": "DDD", "ts": 2, "prob": 0.52},
        {"date": "2026-01-03", "home": "EEE", "away": "FFF", "ts": 3, "prob": 0.53},
    ]
    real, _ = build_table(_events(), quotes, "mlb", allow_proxy=True, require_team_agreement=True)
    control, _ = build_table(permute_dates(_events()), quotes, "mlb", allow_proxy=True, require_team_agreement=True)
    assert sum(row["kind"] != "NONE" for row in real) == 3
    assert sum(row["kind"] != "NONE" for row in control) == 0


def test_strict_mode_does_not_let_event_id_bypass_shuffled_date():
    event = state_events([{"game_id": "stable", "home_team": "AAA", "away_team": "BBB", "date": "2026-01-01"}], "mlb")
    quote = {"event_id": "stable", "date": "2026-01-02", "home": "AAA", "away": "BBB", "ts": 1, "prob": 0.5}
    rows, _ = build_table(event, [quote], "mlb", allow_proxy=True, require_team_agreement=True)
    assert rows[0]["kind"] == "NONE"


def test_collision_count_includes_three_later_unreachable_events():
    events = state_events([
        {"game_id": f"e{index}", "home_team": "AAA", "away_team": f"B{index}", "date": "2026-02-01"}
        for index in range(4)
    ], "mlb")
    assert collision_census(events)["resolved_kept_first_bydateteam"] == 3


def test_dedupe_keeps_one_event_per_key():
    kept, raw_count = dedupe_by_event_key([{"event_key": "x"}, {"event_key": "x"}, {"event_key": "y"}])
    assert raw_count == 3
    assert [event["event_key"] for event in kept] == ["x", "y"]


def test_output_kind_counts_equal_census_counts(tmp_path, capsys):
    """Guard against serialized-output/census divergence: reread the written parquet's
    kind column (the SERIALISED join_census input) and compare it to an independently
    built in-memory Counter over the same build_table() construct, not a copy of itself."""
    rows, _ = build_table(_events()[:2], [{"date": "2026-01-01", "home": "AAA", "away": "BBB", "ts": 1, "prob": 0.5}], "mlb", allow_proxy=True, require_team_agreement=True)
    in_memory_census = Counter(row["kind"] for row in rows)
    output_path = tmp_path / "s327_output_equals_census.parquet"
    _write(rows, output_path)
    serialised_output = Counter(pd.read_parquet(output_path, columns=["kind"])["kind"])
    assert serialised_output == in_memory_census
    print("OUTPUT_EQUALS_CENSUS", dict(sorted(serialised_output.items())))
    assert "OUTPUT_EQUALS_CENSUS" in capsys.readouterr().out
