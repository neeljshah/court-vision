"""Per-file test for Track B3 bet_map: mapping correctness on known claims +
coverage matrix shape on a small slice. Run: python -m pytest
tests/platformkit/live_edge/test_bet_map.py -q"""
import pandas as pd

from scripts.platformkit.live_edge.bet_map import bet_map, coverage


def test_resolve_observable_full_reuses_claim_impact_first():
    # native observable path (claim_impact resolves it directly)
    assert bet_map.resolve_observable_full("minutes_dist") == "minutes_dist"
    # claim_impact fallback vocab path (foul topic -> minutes_dist)
    assert bet_map.resolve_observable_full("high_foul_vs_low_foul") == "minutes_dist"


def test_resolve_observable_full_extra_vocab_for_ledger_topics_claim_impact_misses():
    assert bet_map.resolve_observable_full("tails.nba.points") == "tail_risk"
    assert bet_map.resolve_observable_full("player_cell.player_period") == "player_context"
    assert bet_map.resolve_observable_full("situation.full_grid_team") == "team_situation"
    assert bet_map.resolve_observable_full("situation.lineup_unit") == "team_situation"
    # note: most synergy.* topics already match claim_impact's own
    # possession_outcome vocab (with_without_teammate/star_sits/era_control),
    # and opponent.opp_def_tercile.* already matches its shot_quality vocab --
    # both fall through to claim_impact, never reaching bet_map's extra vocab.
    assert bet_map.resolve_observable_full("opponent.opp_def_tercile.pts") == "shot_quality"
    assert bet_map.resolve_observable_full("totally_unknown_topic_xyz") == "unmapped"


def test_families_for_observable_covers_new_and_existing():
    fams = bet_map.families_for_observable("tail_risk")
    assert "props.pts" in fams and "race_to_x" in fams
    fams2 = bet_map.families_for_observable("minutes_dist")
    assert "props.reb" in fams2  # claim_impact's own map, unedited


def test_bet_fanout_explodes_one_claim_per_family(monkeypatch, tmp_path):
    fake = pd.DataFrame([
        {"claim_id": "c1", "lifecycle": "screened", "sport": "nba",
         "entity_ids_flat": "p1", "topic": "tails.nba.points"},
        {"claim_id": "c2", "lifecycle": "accepted", "sport": "nba",
         "entity_ids_flat": "", "topic": "totally_unknown_topic_xyz"},
    ])
    monkeypatch.setattr(bet_map.cl, "query", lambda **kw: fake)
    out = bet_map.bet_fanout(sport="nba")
    c1_rows = out[out["claim_id"] == "c1"]
    assert len(c1_rows) == len(bet_map.families_for_observable("tail_risk"))
    assert set(c1_rows["market_family"]) == set(bet_map.families_for_observable("tail_risk"))
    c2_rows = out[out["claim_id"] == "c2"]
    assert len(c2_rows) == 1 and c2_rows.iloc[0]["market_family"] == ""


def test_coverage_matrix_shape_on_fake_slice(monkeypatch):
    fake = pd.DataFrame([
        {"claim_id": "c1", "lifecycle": "screened", "sport": "nba",
         "entity_ids_flat": "p1", "topic": "tails.nba.points"},
    ])
    monkeypatch.setattr(bet_map.cl, "query", lambda **kw: fake)
    matrix = coverage.coverage_matrix(sport="nba")
    assert set(matrix["market_family"]) == set(bet_map.ALL_MARKET_SHAPES)
    covered_families = set(matrix[matrix["covered"]]["market_family"])
    assert covered_families == set(bet_map.families_for_observable("tail_risk"))
    # every other shape must be honestly uncovered on this tiny slice
    assert (matrix["covered"].sum()) == len(bet_map.families_for_observable("tail_risk"))
