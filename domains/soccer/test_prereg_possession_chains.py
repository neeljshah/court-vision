"""Per-file test for prereg_possession_chains.py -- synthetic possession-level
events, hand-computed xg-per-possession/counter-share math, strength-control
sensitivity on a confounded toy, and verdict rules (incl NOT_TESTABLE).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_prereg_possession_chains.py -q
"""
from __future__ import annotations

import json

from domains.soccer import prereg_possession_chains as pc


def _events(rows):
    """rows: list of (possession_id, team_id, team_name, play_pattern, shot_xg_or_None)."""
    out = []
    for poss, tid, tname, pattern, xg in rows:
        out.append({
            "possession": poss, "possession_team": {"id": tid, "name": tname},
            "play_pattern": {"name": pattern}, "team": {"id": tid},
            "type": {"name": "Pass"},
        })
        if xg is not None:
            out.append({
                "possession": poss, "possession_team": {"id": tid, "name": tname},
                "play_pattern": {"name": pattern}, "team": {"id": tid},
                "type": {"name": "Shot"}, "shot": {"statsbomb_xg": xg},
            })
    return out


def _write_match(tmp_path, match_id, rows, date="2020-06-01"):
    (tmp_path / f"{match_id}.json").write_text(json.dumps(_events(rows)), encoding="utf-8")
    return {"home_team": {"home_team_id": rows[0][1]}, "away_team": {"away_team_id": 999},
            "home_score": 1, "away_score": 0, "match_date": date}


def test_pattern_group_bucketing():
    assert pc._pattern_group("From Counter") == "counter"
    assert pc._pattern_group("Regular Play") == "regular"
    assert pc._pattern_group("From Corner") == "set_piece_derived"
    assert pc._pattern_group("From Kick Off") == "set_piece_derived"


def test_shotless_possession_counts_as_zero_not_dropped(tmp_path):
    lookup = {1: _write_match(tmp_path, 1, [(1, 10, "A", "Regular Play", None)])}
    df = pc.build_possessions(events_dir=tmp_path, match_lookup=lookup)
    assert len(df) == 1
    assert df.iloc[0]["xg"] == 0.0


def test_possession_xg_sums_shots_in_that_possession(tmp_path):
    # one possession with two shots -> xg is the sum, not the last/first
    events = [
        {"possession": 1, "possession_team": {"id": 10, "name": "A"},
         "play_pattern": {"name": "From Counter"}, "team": {"id": 10}, "type": {"name": "Pass"}},
        {"possession": 1, "possession_team": {"id": 10, "name": "A"},
         "play_pattern": {"name": "From Counter"}, "team": {"id": 10},
         "type": {"name": "Shot"}, "shot": {"statsbomb_xg": 0.10}},
        {"possession": 1, "possession_team": {"id": 10, "name": "A"},
         "play_pattern": {"name": "From Counter"}, "team": {"id": 10},
         "type": {"name": "Shot"}, "shot": {"statsbomb_xg": 0.30}},
    ]
    (tmp_path / "1.json").write_text(json.dumps(events), encoding="utf-8")
    lookup = {1: {"home_team": {"home_team_id": 10}, "away_team": {"away_team_id": 999},
                  "home_score": 1, "away_score": 0, "match_date": "2020-06-01"}}
    df = pc.build_possessions(events_dir=tmp_path, match_lookup=lookup)
    assert len(df) == 1
    assert abs(df.iloc[0]["xg"] - 0.40) < 1e-9


def _confounded_toy():
    """Team A (strong, xg=0.5 CONSTANT regardless of pattern) plays mostly
    counters (6-of-8 possessions); team B (weak, xg=0.02 constant) plays
    mostly regular play (6-of-8). is_counter has WITHIN-team variation for
    both teams (not collinear with team_id), but pooled it correlates with
    team strength -- raw is_counter picks that up, while the team-FE control
    (xg is exactly constant within each team) should collapse it to ~0."""
    lookup, events_by_match = {}, {}
    for m in range(1, 41):
        rows = []
        for p in range(6):
            rows.append((p, 10, "A", "From Counter", 0.5))
        for p in range(6, 8):
            rows.append((p, 10, "A", "Regular Play", 0.5))
        for p in range(8, 10):
            rows.append((p, 20, "B", "From Counter", 0.02))
        for p in range(10, 16):
            rows.append((p, 20, "B", "Regular Play", 0.02))
        events_by_match[m] = _events(rows)
        lookup[m] = {"home_team": {"home_team_id": 10}, "away_team": {"away_team_id": 20},
                     "home_score": 1, "away_score": 0, "match_date": "2020-06-01"}
    return lookup, events_by_match


def _write_events_dir(tmp_path, events_by_match):
    for mid, events in events_by_match.items():
        (tmp_path / f"{mid}.json").write_text(json.dumps(events), encoding="utf-8")


def test_strength_control_changes_estimate_on_confounded_toy(tmp_path):
    lookup, events_by_match = _confounded_toy()
    _write_events_dir(tmp_path, events_by_match)
    df = pc.build_possessions(events_dir=tmp_path, match_lookup=lookup)
    sub = pc._h1_subset(df)
    fit = pc.fit_h1(sub)
    assert fit is not None
    # raw is_counter effect is inflated by team A's strength; controlled (team
    # FE partials out A vs B entirely) collapses toward zero on this toy where
    # xg is CONSTANT within each team regardless of pattern.
    assert fit["effect_raw"] > 0.1
    assert abs(fit["effect_controlled"]) < 1e-6


def test_fit_h1_none_on_empty_not_testable():
    import pandas as pd
    empty = pd.DataFrame(columns=["xg", "is_counter", "team_id", "match_id"])
    assert pc.fit_h1(empty) is None


def test_replication_row_verdicts():
    hit_a = {"effect_controlled": 0.01, "p_controlled": 0.001}
    hit_b = {"effect_controlled": 0.02, "p_controlled": 0.01}
    miss = {"effect_controlled": -0.01, "p_controlled": 0.001}
    null = {"effect_controlled": 0.01, "p_controlled": 0.9}
    assert pc._replication_row(hit_a, hit_b)["verdict"] == "REPLICATED"
    assert pc._replication_row(hit_a, miss)["verdict"] == "FAILED_REPLICATION"
    assert pc._replication_row(hit_a, null)["verdict"] == "FAILED_REPLICATION"
    assert pc._replication_row(None, hit_b)["verdict"] == "NOT_TESTABLE"


def test_ledger_row_edge_claimed_false_and_not_testable_on_none():
    row = pc._ledger_row("full_corpus", None)
    assert row["verdict"] == "NOT_TESTABLE"
    assert row["edge_claimed"] is False
    row2 = pc._ledger_row("full_corpus", {"n": 100, "effect_controlled": 0.01, "p_controlled": 0.001,
                                           "effect_raw": 0.02, "p_raw": 0.001})
    assert row2["verdict"] == "SURVIVES_PREREG"
    assert row2["edge_claimed"] is False


def test_ranking_claim_min_sample_floor_and_edge_claimed(tmp_path):
    lookup, events_by_match = _confounded_toy()
    _write_events_dir(tmp_path, events_by_match)
    df = pc.build_possessions(events_dir=tmp_path, match_lookup=lookup)
    # both teams appear in 40 matches -- clears a 30-match floor
    pc.MIN_MATCHES_PER_TEAM = 30
    claims = pc.build_claims(df, out_dir=tmp_path)
    assert len(claims) == 2
    for claim in claims:
        assert claim["edge_claimed"] is False
        assert len(claim["ranking"]) >= 1
