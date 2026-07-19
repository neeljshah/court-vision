"""Per-file tests for ask_index.py (spec sec 4, LANE L-D).

Direct unit tests for the module extracted out of ask.py to respect the
<=300 LOC/file rail (test_ask.py already covers the SAME behavior end-to-end
through the public ask() surface -- these tests target index_top_n_lookup /
seek_claim_row directly: metric/window filtering, VERIFIED-only, most-recent
computed_at tie-break, and the "no matching family -> None" contract that
callers rely on to fall back).
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.intel_query import ask_index
from scripts.platformkit.intel_query.claims_index import build_index
from scripts.platformkit.intel_query.families import ParsedQuestion

REPO_ROOT = Path(__file__).resolve().parents[3]


def _ranking_row(claim_id: str, metric: str, window: str, computed_at: str, ranking: list[dict]) -> dict:
    return {
        "claim_id": claim_id, "kind": "ranking",
        "question": f"{metric} leaderboard ({window})?",
        "criteria": {"metric": metric, "window": window, "entity_key": "player_id"},
        "ranking": ranking, "source_files": ["data/fake/source.parquet"],
        "computed_at": computed_at, "n_considered": 100, "n_excluded_below_floor": 5,
        "caveats": ["test caveat"],
    }


def _write_family(claims_dir: Path, family: str, rows: list[dict], verdicts: dict[str, str]) -> None:
    claims_path = claims_dir / f"{family}.jsonl"
    with open(claims_path, "w", encoding="ascii") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    payload = {
        "component": "test", "generated_at": "2026-07-06T00:00:00+00:00",
        "n_claims": len(rows), "n_verified": sum(1 for v in verdicts.values() if v == "VERIFIED"),
        "n_mismatch": 0, "n_unverifiable": 0, "edge_claimed": False,
        "details": [{"claim_id": cid, "verdict": v, "reason": "test"} for cid, v in verdicts.items()],
    }
    (claims_dir / f"{family}_validation.json").write_text(json.dumps(payload), encoding="ascii")


def test_seek_claim_row_reads_correct_line(tmp_path):
    rows = [
        _ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00", [{"rank": 1, "player_id": 1, "value": 10.0}]),
        _ranking_row("a2", "ast", "season", "2026-01-01T00:00:00+00:00", [{"rank": 1, "player_id": 2, "value": 5.0}]),
    ]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED", "a2": "VERIFIED"})
    claims_path = tmp_path / "fam.jsonl"
    with open(claims_path, "rb") as f:
        line1 = f.readline()
    offset2 = len(line1)

    row = ask_index.seek_claim_row(claims_path, offset2)
    assert row["claim_id"] == "a2"


def test_seek_claim_row_returns_none_on_bad_offset(tmp_path):
    _write_family(tmp_path, "fam", [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00", [])],
                   {"a1": "VERIFIED"})
    claims_path = tmp_path / "fam.jsonl"
    row = ask_index.seek_claim_row(claims_path, 99999)
    assert row is None


def test_index_top_n_lookup_returns_none_with_no_families(tmp_path):
    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None


def test_index_top_n_lookup_finds_verified_metric_window_match(tmp_path):
    rows = [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "player_name": "Alpha", "value": 10.0}])]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row is not None
    assert row["claim_id"] == "a1"
    assert row["_producer_source"] is not None


def test_index_top_n_lookup_skips_non_verified(tmp_path):
    rows = [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "value": 10.0}])]
    _write_family(tmp_path, "fam", rows, {"a1": "MISMATCH"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None


def test_index_top_n_lookup_respects_metric_hint_mismatch(tmp_path):
    rows = [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "value": 10.0}])]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["ast"], window_hint="season")
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None


def test_index_top_n_lookup_picks_most_recent_computed_at(tmp_path):
    rows = [
        _ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                      [{"rank": 1, "player_id": 1, "player_name": "Old", "value": 1.0}]),
        _ranking_row("a2", "pts", "season", "2026-02-01T00:00:00+00:00",
                      [{"rank": 1, "player_id": 2, "player_name": "New", "value": 2.0}]),
    ]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED", "a2": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row["claim_id"] == "a2"


def test_index_top_n_lookup_skips_stale_family_without_error(tmp_path):
    rows = [_ranking_row("a1", "pts", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 1, "value": 10.0}])]
    _write_family(tmp_path, "fam", rows, {"a1": "VERIFIED"})
    # No build_index() call -- family is discoverable (jsonl+validation
    # pair exists) but has NO index at all -- is_index_fresh must be False.
    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None


# --- entity-type + metric-synonym gate (routing/metric-matching bug fix) ----

def _team_ranking_row(claim_id: str, metric: str, window: str, computed_at: str) -> dict:
    """Same shape as _ranking_row but entity_key='team' -- the TEAM side of
    the exact collision the reported bug hit (a team claim beating a player
    question when metric_hints came back empty)."""
    return {
        "claim_id": claim_id, "kind": "ranking",
        "question": f"{metric} leaderboard ({window})?",
        "criteria": {"metric": metric, "window": window, "entity_key": "team"},
        "ranking": [{"rank": 1, "team": "CLE", "value": 121.6}],
        "source_files": ["data/fake/source.parquet"],
        "computed_at": computed_at, "n_considered": 30, "n_excluded_below_floor": 0,
        "caveats": ["test caveat"],
    }


def test_extract_metric_synonym_finds_ft_percentage_phrasing():
    assert ask_index.extract_metric_synonym("free throw percentage") == "ft_reliability"
    assert ask_index.extract_metric_synonym("what is his ft%") == "ft_reliability"
    assert ask_index.extract_metric_synonym("no metric words here") is None


def test_extract_metric_synonym_prefers_longest_alias_match():
    # "team free throw percentage" contains "free throw percentage" as a
    # substring -- longest-match must resolve to team_ft_pct, never let the
    # shorter alias shadow the more specific one.
    assert ask_index.extract_metric_synonym("team free throw percentage") == "team_ft_pct"
    assert ask_index.extract_metric_synonym("free throw percentage") == "ft_reliability"


def test_question_entity_type_detects_players_vs_teams():
    assert ask_index.question_entity_type("top 5 nba players by free throw percentage") == "player"
    assert ask_index.question_entity_type("top 5 nba teams by points per game") == "team"
    assert ask_index.question_entity_type("top 5 by points per game") is None  # names neither


def test_entity_key_matches_classifies_team_vs_player_keys():
    assert ask_index.entity_key_matches("team", "team") is True
    assert ask_index.entity_key_matches("team", "player") is False
    assert ask_index.entity_key_matches("player_id", "player") is True
    assert ask_index.entity_key_matches("player_id", "team") is False
    assert ask_index.entity_key_matches(["p1_id", "p2_id"], "player") is True
    assert ask_index.entity_key_matches(["team_lo", "team_hi"], "team") is True
    assert ask_index.entity_key_matches("anything", None) is True  # no entity type named -> no filter


def test_index_top_n_lookup_rejects_team_row_for_a_players_question(tmp_path):
    """The reported bug's exact shape at the index layer: a team-entity
    ranking claim (team_pts_per_game) must never win a question that names
    "players" -- even with empty metric_hints (no alias matched), the
    entity-type gate alone must reject it."""
    rows = [_team_ranking_row("team_a1", "team_pts_per_game", "season", "2026-01-01T00:00:00+00:00")]
    _write_family(tmp_path, "fam", rows, {"team_a1": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(
        family="top_n", top_n=5, metric_hints=[], window_hint=None,
        raw="who are the top 5 nba players by free throw percentage this season",
    )
    assert ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT) is None


def test_index_top_n_lookup_finds_synonym_matched_metric_via_raw(tmp_path):
    """metric_hints is empty (no families.py alias for this phrasing) but
    raw contains a recognized synonym -- the fast path must still find the
    matching player-entity row via extract_metric_synonym."""
    rows = [_ranking_row("ft_a1", "ft_reliability", "season", "2026-01-01T00:00:00+00:00",
                          [{"rank": 1, "player_id": 5, "player_name": "Free Thrower", "value": 0.95}])]
    _write_family(tmp_path, "fam", rows, {"ft_a1": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(
        family="top_n", top_n=5, metric_hints=[], window_hint=None,
        raw="who are the top 5 nba players by free throw percentage this season",
    )
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row is not None
    assert row["claim_id"] == "ft_a1"
    assert row["ranking"][0]["player_name"] == "Free Thrower"


def test_index_top_n_lookup_team_question_still_finds_team_metric(tmp_path):
    """A team phrasing ("top 5 nba teams by points per game") must still
    resolve to the team-entity claim -- the entity-type gate is a filter,
    not a player-only allowlist."""
    rows = [_team_ranking_row("team_a1", "team_pts_per_game", "season", "2026-01-01T00:00:00+00:00")]
    _write_family(tmp_path, "fam", rows, {"team_a1": "VERIFIED"})
    build_index("fam", tmp_path)

    parsed = ParsedQuestion(
        family="top_n", top_n=5, metric_hints=[], window_hint=None,
        raw="top 5 nba teams by team points per game",
    )
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row is not None
    assert row["claim_id"] == "team_a1"


def test_index_top_n_lookup_prefers_higher_validity_tier_over_recency(tmp_path, monkeypatch):
    # Two families answer the same metric/window: fam_low is NEWER but tier-0,
    # fam_t2 is OLDER but T2_PREDICTIVE -- the ladder must win over recency,
    # and recency must still break ties within a tier.
    low = [_ranking_row("a1", "pts", "season", "2026-07-01T00:00:00+00:00",
                        [{"rank": 1, "player_id": 1, "player_name": "Newer", "value": 9.0}])]
    t2 = [_ranking_row("b1", "pts", "season", "2026-01-01T00:00:00+00:00",
                       [{"rank": 1, "player_id": 2, "player_name": "Valid", "value": 8.0}])]
    _write_family(tmp_path, "fam_low", low, {"a1": "VERIFIED"})
    _write_family(tmp_path, "fam_t2", t2, {"b1": "VERIFIED"})
    build_index("fam_low", tmp_path)
    build_index("fam_t2", tmp_path)
    monkeypatch.setattr(ask_index, "_ladder_cache", {"fam_t2": 2, "fam_low": 0})

    parsed = ParsedQuestion(family="top_n", top_n=5, metric_hints=["pts"], window_hint="season")
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row is not None and row["claim_id"] == "b1"  # T2 beats newer T0

    # Same tier -> recency wins (legacy behavior preserved).
    monkeypatch.setattr(ask_index, "_ladder_cache", {"fam_t2": 0, "fam_low": 0})
    row = ask_index.index_top_n_lookup(parsed, tmp_path, REPO_ROOT)
    assert row is not None and row["claim_id"] == "a1"
