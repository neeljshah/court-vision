"""Per-file tests for tennis_surface_context_claims (synthetic matches frame
-- NO data/ dir in this worktree, so build_all_claims() is exercised via
monkeypatched _load_matches, not the real corpus).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_tennis_surface_context_claims.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import tennis_surface_context_claims as tsc
from scripts.platformkit.intel_validation.claims_validator import validate_claim

_REAL_LOAD_MATCHES = tsc._load_matches  # captured before the autouse fixture patches it


def _mk_matches() -> pd.DataFrame:
    """30 hard + 30 clay matches for P1 (wins all hard, loses all clay) vs a
    rotating cast, plus a few grass/carpet/unknown/old-window rows, so the
    gap floor (>=25 each), the form floor (>=30), and the recent-form window
    filter all exercise real splits."""
    rows = []
    eid = 0
    # P1 dominant on hard (30 wins), weak on clay (30 losses) -- recent-form window
    for i in range(30):
        eid += 1
        rows.append(dict(event_id=eid, date="2024-01-01", tour="ATP", surface="Hard",
                          p1_id=1, p2_id=100 + i, p1_name="P1", p2_name=f"Opp{i}",
                          winner=1, retirement=False))
    for i in range(30):
        eid += 1
        rows.append(dict(event_id=eid, date="2024-02-01", tour="ATP", surface="Clay",
                          p1_id=1, p2_id=200 + i, p1_name="P1", p2_name=f"Opp{i}",
                          winner=2, retirement=False))
    # P1 on grass: 16 matches, wins 12 (grass adaptability floor >=15)
    for i in range(16):
        eid += 1
        rows.append(dict(event_id=eid, date="2024-03-01", tour="ATP", surface="Grass",
                          p1_id=1, p2_id=300 + i, p1_name="P1", p2_name=f"Opp{i}",
                          winner=1 if i < 12 else 2, retirement=False))
    # Carpet/Unknown rows for P1 -- must be excluded entirely
    eid += 1
    rows.append(dict(event_id=eid, date="2024-01-15", tour="ATP", surface="Carpet",
                      p1_id=1, p2_id=999, p1_name="P1", p2_name="OppCarpet",
                      winner=1, retirement=False))
    # Old-window (career-only, pre-2023) hard match for P1 -- excluded from recent_form
    eid += 1
    rows.append(dict(event_id=eid, date="2020-01-01", tour="ATP", surface="Hard",
                      p1_id=1, p2_id=998, p1_name="P1", p2_name="OppOld",
                      winner=1, retirement=False))
    # A retirement-decided match, counted as decided per the declared choice
    eid += 1
    rows.append(dict(event_id=eid, date="2024-04-01", tour="ATP", surface="Hard",
                      p1_id=1, p2_id=997, p1_name="P1", p2_name="OppRet",
                      winner=1, retirement=True))
    # A below-floor WTA player (only 2 matches, entire WTA combo stays empty
    # in this synthetic fixture -- exercises the skip idiom, not partial exclusion)
    rows.append(dict(event_id=eid + 1, date="2024-01-01", tour="WTA", surface="Hard",
                      p1_id=2, p2_id=996, p1_name="W1", p2_name="OppW",
                      winner=1, retirement=False))
    rows.append(dict(event_id=eid + 2, date="2024-01-02", tour="WTA", surface="Clay",
                      p1_id=2, p2_id=995, p1_name="W1", p2_name="OppW2",
                      winner=2, retirement=False))
    # A second ATP player who qualifies for the hard-form floor (30 hard wins)
    # but NOT the clay-gap floor (only 5 clay matches) -- exercises partial
    # per-player floor exclusion inside an otherwise non-empty ranking.
    for i in range(30):
        eid += 3
        rows.append(dict(event_id=eid, date="2024-01-01", tour="ATP", surface="Hard",
                          p1_id=3, p2_id=400 + i, p1_name="P3", p2_name=f"Opp3{i}",
                          winner=1, retirement=False))
    for i in range(5):
        eid += 1
        rows.append(dict(event_id=eid, date="2024-02-01", tour="ATP", surface="Clay",
                          p1_id=3, p2_id=500 + i, p1_name="P3", p2_name=f"Opp3c{i}",
                          winner=2, retirement=False))
    df = pd.DataFrame(rows)
    df["best_of"] = 3
    return df


@pytest.fixture(autouse=True)
def _patch_loader(monkeypatch, tmp_path):
    matches = _mk_matches()
    monkeypatch.setattr(tsc, "_load_matches", lambda: (matches, ["synthetic/matches.parquet"]))
    # REPO_ROOT and _OUT_DIR both repointed at tmp_path so _write_snapshot's
    # relative_to(REPO_ROOT) stays a real subpath (tmp_path is outside the
    # actual repo root, and this worktree has no data/ dir to write into).
    monkeypatch.setattr(tsc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(tsc, "_OUT_DIR", tmp_path)
    yield


def test_winner_values_fail_closed(monkeypatch):
    bad = _mk_matches()
    bad.loc[0, "winner"] = 3
    monkeypatch.setattr(tsc.glob, "glob", lambda pattern: ["fake.parquet"])
    monkeypatch.setattr(tsc.pd, "read_parquet", lambda p: bad)
    with pytest.raises(ValueError, match="unexpected winner values"):
        _REAL_LOAD_MATCHES()


def test_surface_split_and_gap_math():
    claims = tsc.build_all_claims()
    gap = next(c for c in claims
               if c["claim_id"] == "tennis_surface_context_gap_clay_specialists_atp_recent_form")
    hard_gap = next(c for c in claims
                    if c["claim_id"] == "tennis_surface_context_gap_hard_specialists_atp_recent_form")
    # P1: 30 hard matches all won (hard_wr=1.0), 30 clay all lost (clay_wr=0.0)
    # -> clay_minus_hard = -1.0 -> P1 is the TOP hard specialist, not a clay specialist.
    hard_top = hard_gap["ranking"][0]
    assert hard_top["player_id"] == 1
    assert hard_top["value"] == pytest.approx(-1.0)
    assert 1 not in {r["player_id"] for r in gap["ranking"][:1]} or gap["ranking"][0]["value"] <= 0


def test_window_filter_excludes_old_and_carpet():
    claims = tsc.build_all_claims()
    form = next(c for c in claims if c["claim_id"] == "tennis_surface_context_form_hard_atp_recent_form")
    p1_row = next(r for r in form["ranking"] if r["player_id"] == 1)
    # 30 hard wins in-window + the retirement-decided hard win = 31, NOT 32
    # (the pre-2023 hard win is excluded by the recent_form window).
    assert p1_row["hard_n"] == 31
    assert p1_row["value"] == pytest.approx(1.0)


def test_floor_skips_below_floor_player_from_nonempty_ranking():
    claims = tsc.build_all_claims()
    gap = next(c for c in claims
               if c["claim_id"] == "tennis_surface_context_gap_clay_specialists_atp_recent_form")
    ids = {r["player_id"] for r in gap["ranking"]}
    assert 1 in ids   # P1 qualifies both clay_n and hard_n floors
    assert 3 not in ids  # P3 has only 5 clay matches, below the 25-floor -- excluded, not crashed
    assert gap["n_excluded_below_floor"] >= 1


def test_skip_idiom_wholly_empty_combo_never_emitted():
    """W1 (WTA) has only 1 hard + 1 clay match -- every WTA claim in this
    fixture would floor out to an empty ranking; the skip idiom means NONE
    of those claim_ids are emitted at all (never an empty ranking published)."""
    claims = tsc.build_all_claims()
    ids = {c["claim_id"] for c in claims}
    assert not any(cid.endswith("_wta_recent_form") or cid.endswith("_wta_career") for cid in ids)
    assert all(c["ranking"] for c in claims)  # no claim anywhere carries an empty ranking


def test_both_directions_are_distinct_claims():
    claims = tsc.build_all_claims()
    ids = {c["claim_id"] for c in claims}
    assert "tennis_surface_context_gap_clay_specialists_atp_recent_form" in ids
    assert "tennis_surface_context_gap_hard_specialists_atp_recent_form" in ids


def test_grass_adaptability_lower_floor():
    claims = tsc.build_all_claims()
    adapt = next(c for c in claims
                 if c["claim_id"] == "tennis_surface_context_grass_adapt_atp_recent_form")
    p1_row = next(r for r in adapt["ranking"] if r["player_id"] == 1)
    assert p1_row["grass_n"] == 16
    # grass_wr = 12/16 = 0.75; ov_wr pools hard(31)+clay(30)+grass(16)=77 matches,
    # wins = 31+0+12 = 43 -> ov_wr = 43/77
    assert p1_row["value"] == pytest.approx(0.75 - 43 / 77, abs=1e-4)


def test_caveats_present_and_no_edge_claim():
    claims = tsc.build_all_claims()
    for claim in claims:
        assert claim["caveats"]
        blob = str(claim)
        assert "DESCRIPTIVE_ONLY" in blob
        assert "edge_claimed" not in blob or "true" not in blob.lower().split("edge_claimed")[1][:20]


def test_claims_validator_round_trip(monkeypatch):
    import scripts.platformkit.intel_validation.claims_validator as cv
    monkeypatch.setattr(cv, "REPO_ROOT", tsc.REPO_ROOT)  # both point at the same tmp_path
    claims = tsc.build_all_claims()
    for claim in claims:
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_expected_claim_count_after_skip_idiom():
    claims = tsc.build_all_claims()
    # Full grid would be 2 tours x 2 windows x 6 claims (2 gap + 3 form + 1
    # grass) = 24, but the skip idiom drops empty rankings: form_grass floors
    # out in both ATP windows (only 16 grass matches, floor is 30), and every
    # WTA claim floors out (W1 has 1 hard + 1 clay match) -- leaving
    # ATP: 5 claims x 2 windows = 10, WTA: 0.
    assert len(claims) == 10
    ids = {c["claim_id"] for c in claims}
    assert all(cid.startswith("tennis_surface_context_") and "_atp_" in cid for cid in ids)
