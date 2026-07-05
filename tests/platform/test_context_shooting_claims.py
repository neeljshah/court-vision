"""Per-file tests for context_shooting_claims (LANE nba-context-shooting).
Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platform/test_context_shooting_claims.py -q

Acceptance criteria (per LANE brief):
  1. Floor exclusion: below-floor rows are excluded from ranking, honestly
     counted in n_excluded_below_floor, never silently dropped.
  2. Team-excluding-player arithmetic is EXACT on a synthetic frame (hand-
     computed expected values, not just "runs without error").
  3. Every claim carries the validator-contract fields (criteria.formula,
     min_sample, entity_key, source_files, ranking rows with n/value/id).
  4. Every emitted claim independently VERIFIES against claims_validator.py.
  5. No retracted/edge-claim tokens leak into any claim's text.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from domains.basketball_nba import context_shooting_claims as csc
from scripts.platformkit.intel_validation.claims_validator import validate_claim

_BANNED = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "bankroll", "pnl")


def _synthetic_rows() -> pd.DataFrame:
    """Two teams, hand-picked so team-excluding-player arithmetic is exact
    by hand: TeamA = P1(made 40/100) + P2(made 20/100) + P3 filler(made
    40/400) => team total 100/600. P1's team-excluding-P1 = (20+40)/(100+400)
    = 60/500 = 0.12; P1's own pct = 0.40; vs_team_context = 0.40-0.12=0.28.
    TeamB is a single low-volume filler so TeamB players never clear floors.
    Each player gets 2 rows (2 games) so game_id/team grouping is exercised."""
    return pd.DataFrame([
        {"game_id": "g1", "date": pd.Timestamp("2024-11-01"), "season": "2024-25",
         "team": "A", "player_id": 1, "player_name": "P1", "fg3m": 20, "fg3a": 50},
        {"game_id": "g2", "date": pd.Timestamp("2024-11-03"), "season": "2024-25",
         "team": "A", "player_id": 1, "player_name": "P1", "fg3m": 20, "fg3a": 50},
        {"game_id": "g1", "date": pd.Timestamp("2024-11-01"), "season": "2024-25",
         "team": "A", "player_id": 2, "player_name": "P2", "fg3m": 10, "fg3a": 50},
        {"game_id": "g2", "date": pd.Timestamp("2024-11-03"), "season": "2024-25",
         "team": "A", "player_id": 2, "player_name": "P2", "fg3m": 10, "fg3a": 50},
        {"game_id": "g1", "date": pd.Timestamp("2024-11-01"), "season": "2024-25",
         "team": "A", "player_id": 3, "player_name": "P3", "fg3m": 20, "fg3a": 200},
        {"game_id": "g2", "date": pd.Timestamp("2024-11-03"), "season": "2024-25",
         "team": "A", "player_id": 3, "player_name": "P3", "fg3m": 20, "fg3a": 200},
        {"game_id": "g1", "date": pd.Timestamp("2024-11-01"), "season": "2024-25",
         "team": "B", "player_id": 4, "player_name": "P4", "fg3m": 5, "fg3a": 10},
    ])


def _synthetic_rows_with_rest_split() -> pd.DataFrame:
    """Same TeamA/TeamB shape as _synthetic_rows, but every TeamA player has
    a THIRD game one day after g2 (B2B) so build_rest_split_snapshot has
    both a B2B side (g2->g3) and a rest side (g1->g2) to bucket -- exercises
    the full end-to-end producer+validator path for all 3 dimensions at once."""
    base = _synthetic_rows()
    extra = pd.DataFrame([
        {"game_id": "g3", "date": pd.Timestamp("2024-11-04"), "season": "2024-25",
         "team": "A", "player_id": 1, "player_name": "P1", "fg3m": 5, "fg3a": 50},
        {"game_id": "g3", "date": pd.Timestamp("2024-11-04"), "season": "2024-25",
         "team": "A", "player_id": 2, "player_name": "P2", "fg3m": 5, "fg3a": 50},
        {"game_id": "g3", "date": pd.Timestamp("2024-11-04"), "season": "2024-25",
         "team": "A", "player_id": 3, "player_name": "P3", "fg3m": 20, "fg3a": 200},
    ])
    return pd.concat([base, extra], ignore_index=True)


def test_team_excluding_player_arithmetic_is_exact():
    """Hand-computed expected value, per the synthetic frame's docstring:
    P1 team-excluding-P1 pct = 60/500 = 0.12; vs_team_context = 0.40-0.12."""
    snap = csc.build_team_context_snapshot(_synthetic_rows())
    p1 = snap[(snap["player_id"] == 1) & (snap["team"] == "A")].iloc[0]
    assert p1["player_fg3m"] == 40 and p1["player_fg3a"] == 100
    assert p1["team_other_fg3m"] == 60 and p1["team_other_fg3a"] == 500
    assert p1["player_fg3_pct"] == pytest.approx(0.40)
    assert p1["team_other_fg3_pct"] == pytest.approx(0.12)
    assert p1["fg3_pct_vs_team_context"] == pytest.approx(0.28)
    # team share: P1 fg3a=100 of team total fg3a=600 (100+100+400)
    assert p1["fg3a_share_of_team"] == pytest.approx(100 / 600)


def test_team_context_floor_excludes_low_volume_and_counts_honestly(monkeypatch, tmp_path):
    """P4 (team B, fg3a=10) is far below MIN_PLAYER_FG3A=100 and must be
    excluded from the ranking while still counted in n_excluded_below_floor."""
    monkeypatch.setattr(csc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(csc, "_rel", lambda p: str(p))
    rows = _synthetic_rows()
    names = csc._name_lookup(rows)
    claim = csc.build_team_context_claim(rows, names)
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert 4 not in ranked_ids
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying
    assert claim["n_excluded_below_floor"] >= 1


def test_rest_split_b2b_vs_rest_arithmetic():
    """Player with a 1-day gap (B2B) then a 3-day gap (rest): verifies the
    gap classification and the b2b-minus-rest subtraction are both exact."""
    rows = pd.DataFrame([
        {"game_id": "g1", "date": pd.Timestamp("2024-11-01"), "player_id": 9, "fg3m": 10, "fg3a": 30},
        {"game_id": "g2", "date": pd.Timestamp("2024-11-02"), "player_id": 9, "fg3m": 15, "fg3a": 30},  # 1-day gap = B2B
        {"game_id": "g3", "date": pd.Timestamp("2024-11-05"), "player_id": 9, "fg3m": 6, "fg3a": 30},   # 3-day gap = rest
    ])
    snap = csc.build_rest_split_snapshot(rows)
    row = snap[snap["player_id"] == 9].iloc[0]
    assert row["b2b_fg3m"] == 15 and row["b2b_fg3a"] == 30
    assert row["rest_fg3m"] == 6 and row["rest_fg3a"] == 30
    assert row["b2b_fg3_pct"] == pytest.approx(0.5)
    assert row["rest_fg3_pct"] == pytest.approx(0.2)
    assert row["fg3_pct_rest_split"] == pytest.approx(0.3)


def test_rest_split_first_game_has_no_gap_and_is_excluded_both_sides():
    """A player's very first logged game has gap_days=NaN -- must land in
    NEITHER the b2b nor the rest bucket (not misclassified as either)."""
    rows = pd.DataFrame([
        {"game_id": "g1", "date": pd.Timestamp("2024-11-01"), "player_id": 9, "fg3m": 10, "fg3a": 30},
    ])
    snap = csc.build_rest_split_snapshot(rows)
    assert snap.empty  # single row: no prior game -> no gap -> no b2b/rest merge match


def test_real_data_claims_independently_verify_end_to_end(monkeypatch, tmp_path):
    """Regression for an honest catch: a stale validation artifact was once
    found showing nba_fg3_pct_vs_team_context_2024-25 and
    nba_fg3a_share_of_team_2024-25 as MISMATCH with recomputed player_id=1 /
    player_id=3 and values 0.28 / 0.6667 -- numbers traceable EXACTLY to this
    file's own _synthetic_rows() fixture (P1's hand-computed vs_team_context,
    P3's fg3a_share), not to any real player in player_boxscores.parquet.
    Root cause: those numbers could only appear if a synthetic snapshot had
    been written to the REAL data/cache/intel_claims/ snapshot path outside
    pytest's tmp_path isolation, poisoning the validator's independent
    recompute while the claims JSONL itself still carried real rankings.

    This test closes that gap by running the FULL real-data path end to end
    (unlike test_all_claims_independently_verify, which only exercises a
    synthetic frame): real _BOXSCORES is read (never written), only
    _OUT_DIR/_rel are redirected to tmp_path, and every emitted claim is
    independently re-validated AND its on-disk snapshot parquet is read back
    and cross-checked against the claim's own rank-1 row -- the exact
    consistency check that would have caught a snapshot/claim divergence."""
    monkeypatch.setattr(csc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(csc, "_rel", lambda p: str(p))

    claims = csc.build_all_claims()
    assert len(claims) == 3
    for claim in claims:
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"

        # Cross-check: the snapshot parquet actually on disk must agree with
        # the claim's own rank-1 ranking row -- this is what a stale/poisoned
        # snapshot file would fail.
        snap_path = Path(claim["source_files"][0])
        on_disk = pd.read_parquet(snap_path)
        entity_key = claim["criteria"]["entity_key"]
        metric_col = claim["criteria"]["metric"]
        rank1 = min(claim["ranking"], key=lambda r: r["rank"])
        disk_row = on_disk[on_disk[entity_key] == rank1[entity_key]]
        assert not disk_row.empty, (
            f"{claim['claim_id']}: rank-1 {entity_key}={rank1[entity_key]} "
            f"not found in on-disk snapshot {snap_path}"
        )
        assert disk_row.iloc[0][metric_col] == pytest.approx(rank1["value"], abs=1e-4), (
            f"{claim['claim_id']}: claim rank-1 value={rank1['value']} but on-disk "
            f"snapshot {metric_col}={disk_row.iloc[0][metric_col]} -- snapshot/claim divergence"
        )


def test_all_claims_independently_verify(monkeypatch, tmp_path):
    """Full end-to-end: patch _BOXSCORES to a synthetic parquet, patch the
    output dir to tmp_path, build all 3 claims, and confirm each one
    independently VERIFIES against claims_validator.py."""
    box_path = tmp_path / "player_boxscores.parquet"
    _synthetic_rows_with_rest_split().to_parquet(box_path)
    monkeypatch.setattr(csc, "_BOXSCORES", box_path)
    monkeypatch.setattr(csc, "_OUT_DIR", tmp_path)
    # snapshots land outside REPO_ROOT under tmp_path -- _rel()'s relative_to
    # would raise; an ABSOLUTE path in source_files resolves fine too (same
    # as test_claims_validator.py's _make_parquet: REPO_ROOT / abs_path
    # collapses to the absolute path itself on both POSIX and Windows).
    monkeypatch.setattr(csc, "_rel", lambda p: str(p))
    monkeypatch.setattr(csc, "MIN_PLAYER_FG3A", 50)  # lower floors so the tiny synthetic pop survives
    monkeypatch.setattr(csc, "MIN_TEAM_OTHER_FG3A", 50)
    monkeypatch.setattr(csc, "MIN_REST_SIDE_FG3A", 1)

    claims = csc.build_all_claims()
    assert len(claims) == 3
    for claim in claims:
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_validator_contract_fields_present(monkeypatch, tmp_path):
    """Every claim must carry the fields claims_validator.py depends on:
    criteria.formula/min_sample/entity_key/direction, source_files, and
    ranking rows with player_id/value/n."""
    monkeypatch.setattr(csc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(csc, "_rel", lambda p: str(p))
    rows = _synthetic_rows()
    names = csc._name_lookup(rows)
    for claim in (
        csc.build_team_context_claim(rows, names),
        csc.build_team_share_claim(rows, names),
    ):
        assert claim["criteria"]["formula"]
        assert claim["criteria"]["entity_key"] == "player_id"
        assert claim["criteria"]["direction"] in ("asc", "desc")
        assert isinstance(claim["criteria"]["min_sample"], dict) and claim["criteria"]["min_sample"]
        assert len(claim["source_files"]) >= 1
        for row in claim["ranking"]:
            assert {"rank", "player_id", "value", "n"} <= row.keys()


def test_no_edge_language_in_any_claim(monkeypatch, tmp_path):
    monkeypatch.setattr(csc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(csc, "_rel", lambda p: str(p))
    rows = _synthetic_rows()
    names = csc._name_lookup(rows)
    for claim in (
        csc.build_team_context_claim(rows, names),
        csc.build_team_share_claim(rows, names),
    ):
        text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
        for token in _BANNED:
            assert token not in text, f"{claim['claim_id']}: banned token {token!r} found"
        assert "edge claimed" in text, f"{claim['claim_id']}: missing no-edge disclosure"
