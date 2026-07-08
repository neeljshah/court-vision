"""claim_features tests -- pair-keyed entity_key (list) families.

Before this fix, any family whose criteria.entity_key was a list (e.g.
['player_id','team_id'] for nba_on_off_claims/nba_gravity_proxy_claims, or
['team_id','lineup_key'] for nba_lineup_spacing_claims) crashed
load_family_features with `TypeError: unhashable type: 'list'` at the bare
`r.get(ekey)` call. These tests cover the fix: team-mappable pairs aggregate
to a team mean and flow through the ordinary entity_key=='team' gate path;
non-team-mappable pairs resolve to a clean marker and an UNTESTABLE verdict,
never a raise.
"""
from __future__ import annotations

import json

from scripts.platformkit.intel_weighting.claim_features import load_family_features
from scripts.platformkit.intel_weighting.relevance_gate import run_family


def _write_family(tmp_path, name, rows):
    path = tmp_path / f"{name}.jsonl"
    with open(path, "w", encoding="ascii") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return tmp_path


def test_pair_with_team_id_aggregates_to_team_mean(tmp_path):
    """entity_key=['player_id','team_id'] (nba_on_off/gravity_proxy shape):
    two players on the same team must average, not crash on dict.get(list)."""
    rows = [{
        "criteria": {"metric": "net_rating_on_per48", "window": "season_2024_25_nba_lineup_corpus",
                     "entity_key": ["player_id", "team_id"]},
        "ranking": [
            {"player_id": 1, "team_id": 100, "value": 10.0},
            {"player_id": 2, "team_id": 100, "value": 20.0},
            {"player_id": 3, "team_id": 200, "value": 5.0},
        ],
    }]
    claims_dir = _write_family(tmp_path, "fake_pair_team", rows)
    entity_key, table = load_family_features("fake_pair_team", claims_dir)
    assert entity_key == "team"
    values = table[("net_rating_on_per48", "season_2024_25_nba_lineup_corpus")]
    assert values == {"100": 15.0, "200": 5.0}   # mean(10,20)=15 for team 100


def test_pair_without_team_id_resolves_to_clean_marker(tmp_path):
    """entity_key=['player_id','lineup_key'] has no team_id -- must resolve to
    a hashable 'pair_no_team:...' marker and an empty table, never raise."""
    rows = [{
        "criteria": {"metric": "x", "window": "season_2024_25_nba_lineup_corpus",
                     "entity_key": ["player_id", "lineup_key"]},
        "ranking": [{"player_id": 1, "lineup_key": "a,b,c", "value": 1.0}],
    }]
    claims_dir = _write_family(tmp_path, "fake_pair_no_team", rows)
    entity_key, table = load_family_features("fake_pair_no_team", claims_dir)
    assert entity_key == "pair_no_team:player_id,lineup_key"
    assert table == {}


def test_pair_without_team_id_flows_to_clean_untestable_via_gate(tmp_path):
    """The gate's existing catch-all dispatch must turn the marker into a
    clean UNTESTABLE row -- no exception, no 'unhashable' anywhere."""
    rows = [{
        "criteria": {"metric": "x", "window": "season_2024_25_nba_lineup_corpus",
                     "entity_key": ["player_id", "lineup_key"]},
        "ranking": [{"player_id": 1, "lineup_key": "a,b,c", "value": 1.0}],
    }]
    claims_dir = _write_family(tmp_path, "fake_pair_no_team2", rows)
    results = run_family("nba", "fake_pair_no_team2", claims_dir)
    assert len(results) == 1
    assert results[0].verdict == "UNTESTABLE"
    assert "unhashable" not in " ".join(results[0].caveats).lower()


def test_pair_with_team_id_flows_to_team_path_via_gate(tmp_path):
    """A team-mappable pair family with a genuine prior-season window must
    dispatch through the normal entity_key=='team' gate path (no raise)."""
    rows = [{
        "criteria": {"metric": "net_rating_on_per48", "window": "season_2024_25_nba_lineup_corpus",
                     "entity_key": ["player_id", "team_id"]},
        "ranking": [
            {"player_id": 1, "team_id": 100, "value": 10.0},
            {"player_id": 2, "team_id": 100, "value": 20.0},
        ],
    }]
    claims_dir = _write_family(tmp_path, "fake_pair_team2", rows)
    results = run_family("nba", "fake_pair_team2", claims_dir)
    assert len(results) == 1
    assert results[0].entity_mapping == "team"


def test_real_lineup_families_no_longer_crash():
    """The actual 2025-26-vintage lineup families: current-season-only window
    means an empty prior-season table -- correctly UNTESTABLE, not a crash."""
    for family in ("nba_on_off_claims", "nba_gravity_proxy_claims", "nba_lineup_spacing_claims"):
        results = run_family("nba", family)
        assert all(r.verdict == "UNTESTABLE" for r in results), (family, results)
        assert all("unhashable" not in " ".join(r.caveats).lower() for r in results), family


if __name__ == "__main__":  # tiny manual run without pytest
    import tempfile
    from pathlib import Path
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            if fn.__code__.co_argcount == 1:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"OK {name}")
    print("all claim_features tests passed")
