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
    table = load_family_features("fake_pair_team", claims_dir)
    entity_key, values = table[("net_rating_on_per48", "season_2024_25_nba_lineup_corpus")]
    assert entity_key == "team"
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
    table = load_family_features("fake_pair_no_team", claims_dir)
    assert table == {}   # pair-keyed w/o team_id never gets stored -- no aggregation to fall back to


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


def test_mixed_entity_key_family_resolves_each_metric_independently(tmp_path):
    """The actual bug this fix closes: nba_fit_ingredient_claims mixes a
    player-keyed metric with a team_posgroup-keyed one in the SAME family.
    Both must resolve correctly in one run_family call -- neither one's
    entity_key may leak onto the other."""
    rows = [
        {
            "criteria": {"metric": "usage_pct", "window": "season_2024_25",
                         "entity_key": "pid"},
            "ranking": [{"pid": 1, "value": 0.30}, {"pid": 2, "value": 0.20},
                        {"pid": 3, "value": 0.10}],
        },
        {
            "criteria": {"metric": "vacancy_share", "window": "season_2024_25",
                         "entity_key": "team_posgroup"},
            "ranking": [
                {"team_posgroup": "ATL|GUARD", "value": 0.9},
                {"team_posgroup": "ATL|BIG", "value": 0.1},
                {"team_posgroup": "BOS|GUARD", "value": 0.5},
            ],
        },
    ]
    claims_dir = _write_family(tmp_path, "fake_mixed_key", rows)
    table = load_family_features("fake_mixed_key", claims_dir)
    ek_usage, _ = table[("usage_pct", "season_2024_25")]
    ek_vacancy, _ = table[("vacancy_share", "season_2024_25")]
    assert ek_usage == "pid"
    assert ek_vacancy == "team_posgroup"

    results = run_family("nba", "fake_mixed_key", claims_dir)
    by_metric = {r.metric: r for r in results}
    assert set(by_metric) == {"usage_pct", "vacancy_share"}
    # usage_pct is player-keyed on synthetic ids with no real roster --
    # UNTESTABLE (zero coverage), not misrouted through the team path.
    assert by_metric["usage_pct"].entity_mapping == "player_minwt_prior_season"
    # vacancy_share's composite team_posgroup key must aggregate to team
    # (ATL's GUARD/BIG segments mean to 0.5), not fall through to UNTESTABLE.
    assert by_metric["vacancy_share"].entity_mapping == "composite_team_mean"
    assert by_metric["vacancy_share"].verdict in {"NULL", "MATTERS_PROVISIONAL"}


def test_composite_key_without_team_prefix_is_clean_untestable(tmp_path):
    """A composite entity id whose first '|' segment is NOT a real team code
    (e.g. a player-scoped composite) must resolve to a clean UNTESTABLE, never
    silently drop to zero entities without saying why."""
    rows = [{
        "criteria": {"metric": "some_metric", "window": "season_2024_25",
                     "entity_key": "player_posgroup"},
        "ranking": [{"player_posgroup": "99999|GUARD", "value": 1.0}],
    }]
    claims_dir = _write_family(tmp_path, "fake_composite_no_team", rows)
    results = run_family("nba", "fake_composite_no_team", claims_dir)
    assert len(results) == 1
    assert results[0].verdict == "UNTESTABLE"
    assert "no team mapping for entity_key=player_posgroup" in " ".join(results[0].caveats)


def test_real_lineup_families_are_genuinely_tested():
    """The lineup families now carry a season_2024_25 window (prior-season
    unlock), so the gate must genuinely test them for eval season 2025-26:
    team-mapped (numeric NBA ids remapped to tricodes), a real verdict, and
    real feature coverage -- never the old all-fdiff=0 fake NULL."""
    for family in ("nba_on_off_claims", "nba_gravity_proxy_claims",
                   "nba_lineup_spacing_claims", "nba_lineup_synergy_claims"):
        results = run_family("nba", family)
        assert results, family
        for r in results:
            assert r.verdict in {"NULL", "MATTERS_PROVISIONAL"}, (family, r)
            assert r.entity_mapping == "team", (family, r)
            caveats = " ".join(r.caveats).lower()
            assert "unhashable" not in caveats, family
            # all 30 teams clear the floor in the first three families, so any
            # missing-entity caveat there means the id->tricode bridge broke.
            # synergy's 100-min lineup floor genuinely leaves a few teams with
            # zero qualifying lineups (partial coverage is real, not a bug).
            if family != "nba_lineup_synergy_claims":
                assert "games had an entity missing" not in caveats, (family, r.caveats)


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
