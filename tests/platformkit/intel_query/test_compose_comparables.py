"""Per-file test: python -m pytest tests/platformkit/intel_query/test_compose_comparables.py -q

Tiny fixture parquet, loaded through the REAL shared profiles/ask.load_profiles
memo (monkeypatched PROFILES_DIR + cache reset -- tmp_path only, never real
data/cache/profiles) -> deterministic nearest neighbor; missing entity ->
no_data; thin shared-attribute intersection -> refused.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_query.compose_comparables import compose_comparables
from scripts.platformkit.profiles import ask as _profiles

ATTRS = ["a1", "a2", "a3", "a4", "a5", "a6"]
SPORT = "nba"  # must be a real profiles/ask.SPORTS entry -- load_profiles skips unknown sports


@pytest.fixture(autouse=True)
def _isolated_profiles_dir(tmp_path, monkeypatch):
    # tmp_path fixture only -- never load the real multi-GB profiles store.
    monkeypatch.setattr(_profiles, "PROFILES_DIR", str(tmp_path))
    monkeypatch.setattr(_profiles, "_CACHE_KEY", None)
    monkeypatch.setattr(_profiles, "_CACHE_DF", None)
    return tmp_path


def _row(eid, name, attr, pct):
    return {"entity_id": eid, "entity_name": name, "window": "season_2025_26",
            "attribute": attr, "percentile": pct}


def _write_profiles(tmp_path, rows) -> None:
    df = pd.DataFrame(rows)
    df.to_parquet(tmp_path / f"{SPORT}_player_profiles.parquet")


def _make_profiles(tmp_path) -> None:
    rows = []
    # A (target): [10,20,30,40,50,60] across a1..a6
    for attr, pct in zip(ATTRS, [10, 20, 30, 40, 50, 60]):
        rows.append(_row(1, "Player A", attr, pct))
    # B: close to A (delta=2 on every shared attr) -- the expected nearest neighbor
    for attr, pct in zip(ATTRS, [12, 22, 32, 42, 52, 62]):
        rows.append(_row(2, "Player B", attr, pct))
    # C: far from A (mirrored values)
    for attr, pct in zip(ATTRS, [90, 80, 70, 60, 50, 40]):
        rows.append(_row(3, "Player C", attr, pct))
    # D: only 3 attrs shared with A -- below the default floor of 5, must be excluded
    for attr, pct in zip(ATTRS[:3], [10, 20, 30]):
        rows.append(_row(4, "Player D", attr, pct))
    _write_profiles(tmp_path, rows)
    # E: a TEAM-kind entity (separate file -- load_profiles derives kind from
    # the filename, not a per-row column) sharing Player A's name/attrs --
    # must never leak into the player KNN via compose_comparables' kind filter.
    team_rows = [_row(5, "Team E", attr, pct) for attr, pct in
                 zip(ATTRS, [10, 20, 30, 40, 50, 60])]
    pd.DataFrame(team_rows).to_parquet(tmp_path / f"{SPORT}_team_profiles.parquet")


def test_deterministic_nearest_neighbor(tmp_path):
    _make_profiles(tmp_path)
    result = compose_comparables(SPORT, "Player A", k=2)
    assert result["status"] == "ok"
    assert result["entity_id"] == 1
    neighbors = result["neighbors"]
    # B (dist RMS=2) must rank ahead of C (far); D never appears (below floor); E (team) never appears
    assert [n["entity_id"] for n in neighbors] == [2, 3]
    assert neighbors[0]["distance"] == 2.0
    assert neighbors[0]["n_attrs"] == 6
    assert all(n["entity_id"] not in (4, 5) for n in neighbors)


def test_missing_entity_is_no_data(tmp_path):
    _make_profiles(tmp_path)
    result = compose_comparables(SPORT, "Nobody Here")
    assert result["status"] == "no_data"
    assert result["category"] == "player_comparables"


def test_thin_intersection_is_refused(tmp_path):
    # Only A and D exist -- D shares just 3 attrs with A, below the floor of 5.
    rows = []
    for attr, pct in zip(ATTRS, [10, 20, 30, 40, 50, 60]):
        rows.append(_row(1, "Player A", attr, pct))
    for attr, pct in zip(ATTRS[:3], [10, 20, 30]):
        rows.append(_row(4, "Player D", attr, pct))
    _write_profiles(tmp_path, rows)

    result = compose_comparables(SPORT, "Player A")
    assert result["status"] == "refused"
    assert "floor" in result["note"] or "intersection" in result["note"]


def test_no_data_when_parquet_absent(tmp_path):
    result = compose_comparables(SPORT, "Player A")
    assert result["status"] == "no_data"


def test_string_entity_id_does_not_crash(tmp_path):
    """P0 fix (docs/research/resolver_coverage_2026_07_17.md gap 1): slug-id
    sports (tennis, and presumably soccer) must not crash on int(entity_id)
    -- entity_id is whatever type the parquet's own column holds."""
    rows = []
    for attr, pct in zip(ATTRS, [10, 20, 30, 40, 50, 60]):
        rows.append(_row("federer_r", "Roger Federer", attr, pct))
    for attr, pct in zip(ATTRS, [12, 22, 32, 42, 52, 62]):
        rows.append(_row("agassi_a", "Andre Agassi", attr, pct))
    pd.DataFrame(rows).to_parquet(tmp_path / "tennis_player_profiles.parquet")

    result = compose_comparables("tennis", "Roger Federer", k=1)
    assert result["status"] == "ok"
    assert result["entity_id"] == "federer_r"
    assert result["neighbors"][0]["entity_id"] == "agassi_a"


def test_nickname_resolves_via_shared_matcher(tmp_path):
    """gap 3: comparables used a narrower exact/substring-only matcher than
    the rest of the registry -- "Steph Curry" must resolve to "Stephen Curry"
    the same way scouting_report's shared fuzzy matcher already does."""
    rows = []
    for attr, pct in zip(ATTRS, [10, 20, 30, 40, 50, 60]):
        rows.append(_row(1, "Stephen Curry", attr, pct))
    for attr, pct in zip(ATTRS, [12, 22, 32, 42, 52, 62]):
        rows.append(_row(2, "Klay Thompson", attr, pct))
    _write_profiles(tmp_path, rows)

    result = compose_comparables(SPORT, "Steph Curry", k=1)
    assert result["status"] == "ok"
    assert result["entity_id"] == 1
    assert result["player"] == "Stephen Curry"
