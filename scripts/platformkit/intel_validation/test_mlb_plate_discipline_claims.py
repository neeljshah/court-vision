"""Per-file tests for mlb_plate_discipline_claims (lane
mlb-plate-discipline). Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_mlb_plate_discipline_claims.py -q

Acceptance criteria:
  1. build_zone_rows derives in_zone correctly (zone 1-9 -> 1, 11-14 -> 0)
     and drops zone-null pitches without imputing.
  2. The emitted zone_rate claim independently re-verifies against the
     REAL on-disk statcast corpus via claims_validator.py.
  3. No retracted/edge-claim tokens leak into caveats; closed-class guard
     text is present.
  4. build_blocked_report() honestly reports all 3 requested-but-absent
     dimensions (pitcher_whiff_rate/batter_chase_rate/batter_whiff_rate),
     never silently omitting them.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import mlb_plate_discipline_claims as pd_claims
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_statcast() -> pd.DataFrame:
    """Pitcher 111: 4 in-zone (zone 1,5,9,4) + 2 out-of-zone (11,14) pitches.
    Pitcher 222: 1 in-zone (3) + 1 zone-null pitch (must be dropped, not
    imputed as either in- or out-of-zone)."""
    rows = [
        (111, 1.0), (111, 5.0), (111, 9.0), (111, 4.0),
        (111, 11.0), (111, 14.0),
        (222, 3.0), (222, None),
    ]
    return pd.DataFrame(rows, columns=["pitcher", "zone"])


def _fixture_gamelogs() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [111, 222],
        "player": ["Fixture Pitcher A", "Fixture Pitcher B"],
    })


def _patch_paths(tmp_path, monkeypatch):
    sc_path = tmp_path / "statcast.parquet"
    _fixture_statcast().to_parquet(sc_path)
    gl_path = tmp_path / "gamelogs.parquet"
    _fixture_gamelogs().to_parquet(gl_path)
    monkeypatch.setattr(pd_claims, "_STATCAST_PATHS", (sc_path,))
    monkeypatch.setattr(pd_claims, "_GAMELOGS", gl_path)
    monkeypatch.setattr(pd_claims, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(pd_claims, "_ZONE_SNAPSHOT_OUT", tmp_path / "zone_rows.parquet")
    monkeypatch.setattr(pd_claims, "REPO_ROOT", tmp_path.parent)  # .relative_to(REPO_ROOT) resolves under tmp_path


def test_build_zone_rows_derives_in_zone_and_drops_nulls(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    out_path, name_df = pd_claims.build_zone_rows(pd_claims._STATCAST_PATHS)
    raw = pd.read_parquet(out_path)
    # 8 fixture rows, 1 zone-null dropped -> 7 rows survive.
    assert len(raw) == 7
    p111 = raw[raw["player_id"] == 111]
    assert len(p111) == 6
    assert p111["in_zone"].sum() == 4  # zones 1,5,9,4 in-zone; 11,14 out
    p222 = raw[raw["player_id"] == 222]
    assert len(p222) == 1  # the null-zone row must be dropped, not imputed
    assert p222["in_zone"].iloc[0] == 1  # zone=3 is in-zone
    assert dict(zip(name_df["player_id"], name_df["player_name"]))[111] == "Fixture Pitcher A"


def test_build_zone_rate_claim_computes_correct_ratio(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(pd_claims, "MIN_PITCHES_PITCHER", 1)
    pd_claims.build_zone_rows(pd_claims._STATCAST_PATHS)
    name_lookup = {111: "Fixture Pitcher A", 222: "Fixture Pitcher B"}
    claim = pd_claims.build_zone_rate_claim(name_lookup)
    assert claim["n_considered"] == 2
    assert claim["n_excluded_below_floor"] == 0
    ranking_by_id = {r["player_id"]: r for r in claim["ranking"]}
    assert ranking_by_id[222]["value"] == 1.0  # 1/1 in-zone
    # claim rounds to value_precision=4 decimals -- compare at that precision.
    assert abs(ranking_by_id[111]["value"] - round(4 / 6, 4)) < 1e-9
    # zone_rate=1.0 (pitcher 222) ranks above 4/6 (pitcher 111) under desc direction.
    assert claim["ranking"][0]["player_id"] == 222


def test_build_zone_rate_claim_applies_min_sample_floor(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(pd_claims, "MIN_PITCHES_PITCHER", 5)
    pd_claims.build_zone_rows(pd_claims._STATCAST_PATHS)
    name_lookup = {111: "Fixture Pitcher A", 222: "Fixture Pitcher B"}
    claim = pd_claims.build_zone_rate_claim(name_lookup)
    # pitcher 111 has 6 pitches (qualifies), pitcher 222 has 1 (excluded).
    assert claim["n_considered"] == 2
    assert claim["n_excluded_below_floor"] == 1
    assert len(claim["ranking"]) == 1
    assert claim["ranking"][0]["player_id"] == 111


def test_real_mlb_plate_discipline_claim_independently_verifies():
    """Cross-module check against the REAL on-disk statcast corpus --
    proves the emitted claim is independently reproducible by
    claims_validator, not just self-consistent."""
    claims = pd_claims.build_all_claims()
    assert len(claims) == 1
    for claim in claims:
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_claims_carry_closed_class_guard_and_no_edge_language():
    claims = pd_claims.build_all_claims()
    banned = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "bankroll", "pnl")
    for claim in claims:
        text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
        for token in banned:
            assert token not in text, f"{claim['claim_id']}: banned token {token!r} found"
        assert "not a validated predictor" in text
        assert "market/$ edge claimed" in text


def test_blocked_report_honestly_lists_all_three_absent_dimensions():
    blocked = pd_claims.build_blocked_report()
    assert blocked["status"] == "CORPUS_ABSENT"
    dims = {d["dimension"] for d in blocked["blocked_dimensions"]}
    assert dims == {"pitcher_whiff_rate", "batter_chase_rate", "batter_whiff_rate"}
    for d in blocked["blocked_dimensions"]:
        assert "CORPUS_ABSENT" in d["reason"]
    assert "description" in blocked["evidence"]
    assert "182124" in blocked["evidence"]
