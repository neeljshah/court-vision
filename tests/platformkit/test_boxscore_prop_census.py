"""Tests for the read-only boxscore prop census."""

import json
from pathlib import Path

from scripts.platformkit.boxscore_prop_census import census_jsonl_store, census_nba_store


def _record(day: int, market_prob: float | None) -> dict[str, object]:
    return {
        "prop_player": f"player-{day}",
        "prop_stat": "points",
        "ts": f"2026-01-{day:02d}T00:00:00",
        "market_prob": market_prob,
    }


def _write_records(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def test_mixed_market_prices_drive_calibration_verdict(tmp_path: Path) -> None:
    """Mixed null and real market prices determine the cluster eligibility verdict."""
    fixture_dir = tmp_path / "mixed_market_price_fixture"
    fixture_dir.mkdir()
    scorable_path = fixture_dir / "scorable.jsonl"
    unscorable_path = fixture_dir / "unscorable.jsonl"
    _write_records(scorable_path, [_record(day, 0.5) for day in range(1, 31)] + [_record(31, None)])
    _write_records(unscorable_path, [_record(1, 0.5), _record(2, None), _record(3, None)])

    scorable = census_jsonl_store("fixture", scorable_path)
    unscorable = census_jsonl_store("fixture", unscorable_path)

    assert scorable["source_count"] == 31
    assert scorable["real_market_price_source_count"] == 30
    assert scorable["real_market_price_cluster_count"] == 30
    assert scorable["market_price_null_count"] == 1
    assert scorable["market_price_null_share"] == 1 / 31
    assert scorable["verdict"] == "SCORABLE"
    assert unscorable["source_count"] == 3
    assert unscorable["real_market_price_source_count"] == 1
    assert unscorable["real_market_price_cluster_count"] == 1
    assert unscorable["verdict"] == "NOT SCORABLE"
    assert unscorable["blocking_count"] == "real_market_price_cluster_count=1; requires >=30"


def test_nba_payload_writes_the_required_tidy_columns(tmp_path: Path) -> None:
    """One payload is flattened while its file remains the game-cluster unit."""
    source_dir = tmp_path / "closing_props"
    source_dir.mkdir()
    payload = {
        "commence_time": "2026-02-03T00:00:00Z",
        "bookmakers": [
            {
                "key": "fixture_book",
                "last_update": "2026-02-02T22:00:00Z",
                "markets": [
                    {
                        "key": "player_points",
                        "last_update": "2026-02-02T23:00:00Z",
                        "outcomes": [
                            {"description": "fixture player", "name": "Over", "point": 20.5, "price": -110},
                            {"description": "fixture player", "name": "Under", "point": 20.5, "price": -110},
                        ],
                    }
                ],
            }
        ],
    }
    (source_dir / "fixture_game.json").write_text(json.dumps(payload), encoding="utf-8")
    tidy_path = tmp_path / "nba_tidy.jsonl"

    result = census_nba_store(source_dir, tidy_path)
    rows = [json.loads(line) for line in tidy_path.read_text(encoding="utf-8").splitlines()]

    assert result["source_count"] == 1
    assert result["tidy_row_count"] == 2
    assert result["real_market_price_cluster_count"] == 1
    assert result["real_market_price_cluster_denominator"] == 1
    assert result["real_market_price_cluster_basis"] == "closing_props JSON file"
    assert result["market_price_null_count"] == 0
    assert rows == [
        {
            "game": "fixture_game",
            "player": "fixture player",
            "outcome_name": "Over",
            "stat": "player_points",
            "line": 20.5,
            "price": -110,
            "book": "fixture_book",
            "timestamp": "2026-02-02T23:00:00Z",
        },
        {
            "game": "fixture_game",
            "player": "fixture player",
            "outcome_name": "Under",
            "stat": "player_points",
            "line": 20.5,
            "price": -110,
            "book": "fixture_book",
            "timestamp": "2026-02-02T23:00:00Z",
        },
    ]
