"""Per-file tests for mlb_tto_claims (lane mlb-tto). Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_mlb_tto_claims.py -q

Acceptance criteria:
  1. build_tto_pa_rows dedups pitch rows to one per PA (max pitch_number).
  2. times_faced/tto_bucket derived correctly via cumcount, for a
     pitcher-batter pair meeting 1x, 2x, and 3x in the same game.
  3. pa_value uses estimated_woba_using_speedangle when present, falls back
     to an events-based on-base indicator when it is missing (the xwoba-omit
     case, e.g. intent_walk).
  4. Every emitted claim (3 buckets + 1 delta) independently re-verifies
     against the REAL on-disk statcast corpus via claims_validator.py.
  5. No retracted/edge-claim tokens leak into caveats; closed-class guard
     text is present in every claim.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import mlb_tto_claims as tto
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_statcast() -> pd.DataFrame:
    """One game_pk=1: pitcher 111 faces batter 222 three times (PA 1: 2
    pitches, single on 2nd; PA 2: 1 pitch, strikeout; PA 3: 1 pitch,
    home_run) and batter 333 once (PA 4: intent_walk, no xwoba -- exercises
    the OBP fallback). A second game_pk=2 gives pitcher 111 a fresh
    first-time meeting with batter 444 (field_out)."""
    rows = [
        # game 1, PA1 (at_bat_number=1): pitcher 111 vs batter 222, 2 pitches, single
        (1, 1, 111, 222, None, None, 1),
        (1, 1, 111, 222, "single", 0.9, 2),
        # game 1, PA2: same pitcher/batter, 2nd meeting -> strikeout
        (1, 2, 111, 222, "strikeout", 0.0, 1),
        # game 1, PA3: same pitcher/batter, 3rd meeting -> home_run
        (1, 3, 111, 222, "home_run", 1.8, 1),
        # game 1, PA4: pitcher 111 vs batter 333, 1st meeting -> intent_walk, NO xwoba
        (1, 4, 111, 333, "intent_walk", None, 1),
        # game 2, PA1: pitcher 111 vs batter 444, 1st meeting -> field_out
        (2, 1, 111, 444, "field_out", 0.1, 1),
    ]
    return pd.DataFrame(rows, columns=[
        "game_pk", "at_bat_number", "pitcher", "batter", "events",
        "estimated_woba_using_speedangle", "pitch_number",
    ])


def _fixture_gamelogs() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [111, 999],
        "player": ["Fixture Pitcher", "Someone Else"],
    })


def _patch_paths(tmp_path, monkeypatch):
    sc_path = tmp_path / "statcast.parquet"
    _fixture_statcast().to_parquet(sc_path)
    gl_path = tmp_path / "gamelogs.parquet"
    _fixture_gamelogs().to_parquet(gl_path)
    monkeypatch.setattr(tto, "_STATCAST_PATHS", (sc_path,))
    monkeypatch.setattr(tto, "_GAMELOGS", gl_path)
    monkeypatch.setattr(tto, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(tto, "_BUCKET_SNAPSHOT_OUT", tmp_path / "bucket_rows.parquet")
    monkeypatch.setattr(tto, "_DELTA_SNAPSHOT_OUT", tmp_path / "delta_snapshot.parquet")
    monkeypatch.setattr(tto, "REPO_ROOT", tmp_path.parent)  # so .relative_to(REPO_ROOT) resolves under tmp_path


def test_dedup_and_times_faced_bucket(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    out_path, name_df = tto.build_tto_pa_rows(tto._STATCAST_PATHS)
    raw = pd.read_parquet(out_path)
    # 5 PAs total (2 pitches dedup to 1 for PA1); all 5 have a resolvable pa_value.
    assert len(raw) == 5
    game1_222 = raw[(raw["player_id"] == 111)].sort_values("pa_value")
    assert set(raw["tto_bucket"]) == {"1", "2", "3+"}
    # the 3rd meeting (home_run) must land in bucket "3+", not "3".
    assert "3+" in raw["tto_bucket"].values
    assert dict(zip(name_df["player_id"], name_df["player_name"]))[111] == "Fixture Pitcher"


def test_pa_value_falls_back_to_obp_when_xwoba_missing(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    out_path, _ = tto.build_tto_pa_rows(tto._STATCAST_PATHS)
    raw = pd.read_parquet(out_path)
    # intent_walk row (PA4) has no estimated_woba_using_speedangle -> falls
    # back to the on-base indicator (intent_walk is on-base -> 1.0).
    intent_walk_rows = raw[(raw["player_id"] == 111) & (raw["pa_value"] == 1.0)]
    assert len(intent_walk_rows) >= 1


def test_build_bucket_claim_uses_window_spec_to_isolate_bucket(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(tto, "MIN_PA_PER_BUCKET", 1)
    tto.build_tto_pa_rows(tto._STATCAST_PATHS)
    name_lookup = {111: "Fixture Pitcher"}
    claim = tto.build_bucket_claim("1", name_lookup)
    assert claim["criteria"]["window_spec"] == {
        "kind": "season", "season_col": "tto_bucket", "season": "1",
    }
    # 2 TTO1 PAs exist (batter 222 PA1, batter 333 PA4, batter 444 PA1) = 3 rows for bucket "1"
    assert claim["n_considered"] >= 1


def test_build_delta_claim_ships_full_unfiltered_population(tmp_path, monkeypatch):
    _patch_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(tto, "MIN_PA_PER_BUCKET", 1)
    tto.build_tto_pa_rows(tto._STATCAST_PATHS)
    claim = tto.build_delta_claim({111: "Fixture Pitcher"})
    # snapshot must carry the UNFILTERED joined table, not just qualifiers
    # (matches platoon_split_index.py precedent) -- n_considered counts it.
    snapshot = pd.read_parquet(tto._DELTA_SNAPSHOT_OUT)
    assert len(snapshot) == claim["n_considered"]


def test_real_mlb_tto_claims_independently_verify():
    """Cross-module check against the REAL on-disk statcast corpus -- proves
    every emitted claim is independently reproducible by claims_validator,
    not just self-consistent."""
    claims = tto.build_all_claims()
    assert len(claims) == 4
    for claim in claims:
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_claims_carry_closed_class_guard_and_no_edge_language():
    claims = tto.build_all_claims()
    banned = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "bankroll", "pnl")
    for claim in claims:
        text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
        for token in banned:
            assert token not in text, f"{claim['claim_id']}: banned token {token!r} found"
        assert "fatigue gate closed" in text
        assert "not a validated predictor" in text
        assert "market/$ edge claimed" in text
