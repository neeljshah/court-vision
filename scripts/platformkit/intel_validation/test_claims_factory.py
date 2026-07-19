"""Per-file tests for claims_factory (LANE L-A, CLAIMS_FACTORY_SPEC_2026-07-06.md
sec 6). Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/intel_validation/test_claims_factory.py -q

Acceptance criteria (per spec sec 6, scoped to LANE L-A's ownership --
parity/anti-fake-tamper tests for validate_claims_file_batched live in
test_claims_validator.py, lane L-B):
  1. tmp-grid end-to-end emit: every claim has every contract field, and
     independently VERIFIES against claims_validator.validate_claim.
  2. Floor exclusion counts: below-floor entities are excluded from ranking,
     honestly counted in n_excluded_below_floor, never silently dropped.
  3. claim_id stability: identical grid + identical source -> byte-identical
     claim_ids across two regens (values may differ only if source moves).
  4. Missing-floor fail-closed: a family declaring a window TYPE with no
     floors[type] entry raises FactoryError, writes NO artifact.
  5. Honesty lint-trip abort: a claim carrying a banned retracted-number
     token or edge_claimed=True aborts the whole regen, no jsonl written.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_factory as cf
from scripts.platformkit.intel_validation.claims_validator import validate_claim

_N_GAMES = 12  # per player, clears every floor below


def _synthetic_boxscore_rows() -> pd.DataFrame:
    """3 players x _N_GAMES games x 2 seasons-worth split, home/away alternating.
    Hand-picked constant pts=10/fga=10 per game so pts_per_game is exact and
    trivially checkable (10.0) without any rounding-noise ambiguity."""
    rows = []
    for pid, name in ((1, "Alice"), (2, "Bob"), (3, "Cara")):
        for g in range(_N_GAMES):
            rows.append({
                "game_id": f"g{pid}_{g}",
                "season": "2024-25" if g < _N_GAMES - 2 else "2025-26",
                "player_id": pid,
                "player_name": name,
                "is_home": g % 2,
                "pts": 10,
                "fga": 10,
            })
    return pd.DataFrame(rows)


def _tiny_grid(source_path: str) -> dict:
    return {
        "sport": "test_sport",
        "families": [{
            "family": "test_fam",
            "source": source_path,
            "grain": "per_game",
            "entity_key": "player_id",
            "entity_name_col": "player_name",
            "dims": [{"metric": "pts_per_game", "agg": {"num": "sum(pts)", "den": "count(game_id)"}}],
            "windows": [
                {"name": "season_2024_25", "filter": {"season": "2024-25"}},
                {"name": "career_to_date", "filter": {}},
            ],
            "context_splits": [{"name": "home", "col": "is_home", "eq": 1}],
            "floors": {
                "season": {"game_id": 5},
                "career": {"game_id": 5},
                "split": {"game_id": 2},
            },
        }],
    }


@pytest.fixture
def grid_and_out(tmp_path):
    src = tmp_path / "box.parquet"
    _synthetic_boxscore_rows().to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    return grid, tmp_path / "out"


def test_end_to_end_emit_every_claim_independently_verifies(grid_and_out):
    grid, out_dir = grid_and_out
    res = cf.generate_family("test_sport", "test_fam", grid, out_dir)
    assert res["n_claims"] > 0

    jsonl_path = out_dir / "test_fam.jsonl"
    lines = jsonl_path.read_text(encoding="ascii").strip().split("\n")
    assert len(lines) == res["n_claims"]

    required_fields = {
        "claim_id", "kind", "criteria", "ranking", "source_files", "computed_at",
        "n_considered", "n_excluded_below_floor", "edge_claimed", "caveats",
    }
    for line in lines:
        claim = json.loads(line)
        assert required_fields <= claim.keys()
        assert claim["edge_claimed"] is False
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_pts_per_game_value_is_exact_synthetic(tmp_path):
    """10 pts / 10 fga per game constant -> pts_per_game must recompute to
    exactly 10.0, not just 'runs without error'."""
    src = tmp_path / "box.parquet"
    _synthetic_boxscore_rows().to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    res = cf.generate_family("test_sport", "test_fam", grid, tmp_path / "out")
    lines = (tmp_path / "out" / "test_fam.jsonl").read_text(encoding="ascii").strip().split("\n")
    claim = json.loads(lines[0])
    for row in claim["ranking"]:
        assert row["value"] == pytest.approx(10.0)


def test_floor_exclusion_counted_never_silently_dropped(tmp_path):
    """Give player 3 only 1 HOME game (below the split floor of 2, game_id
    ends in an odd number since is_home = g % 2) so it is excluded from the
    home split while still being counted in n_excluded_below_floor."""
    rows = _synthetic_boxscore_rows()
    p3_home_ids = rows.loc[(rows["player_id"] == 3) & (rows["is_home"] == 1), "game_id"]
    keep_one = p3_home_ids.iloc[0]
    drop_ids = set(p3_home_ids) - {keep_one}
    rows = rows[~rows["game_id"].isin(drop_ids)]
    src = tmp_path / "box.parquet"
    rows.to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    res = cf.generate_family("test_sport", "test_fam", grid, tmp_path / "out")
    assert res["n_excluded_below_floor"] > 0

    lines = (tmp_path / "out" / "test_fam.jsonl").read_text(encoding="ascii").strip().split("\n")
    home_claims = [json.loads(line) for line in lines if line and "home" in json.loads(line)["criteria"]["window"]]
    assert home_claims
    for claim in home_claims:
        ranked_ids = {row["player_id"] for row in claim["ranking"]}
        assert claim["n_considered"] == len(ranked_ids) + claim["n_excluded_below_floor"]


def test_claim_id_stable_across_two_regens(grid_and_out):
    grid, out_dir = grid_and_out
    res1 = cf.generate_family("test_sport", "test_fam", grid, out_dir / "run1")
    res2 = cf.generate_family("test_sport", "test_fam", grid, out_dir / "run2")

    ids1 = sorted(json.loads(line)["claim_id"] for line in
                   (out_dir / "run1" / "test_fam.jsonl").read_text(encoding="ascii").strip().split("\n"))
    ids2 = sorted(json.loads(line)["claim_id"] for line in
                   (out_dir / "run2" / "test_fam.jsonl").read_text(encoding="ascii").strip().split("\n"))
    assert ids1 == ids2
    assert len(ids1) == res1["n_claims"] == res2["n_claims"]


def test_claim_id_shape_is_family_entity_metric_window(grid_and_out):
    grid, out_dir = grid_and_out
    cf.generate_family("test_sport", "test_fam", grid, out_dir)
    lines = (out_dir / "test_fam.jsonl").read_text(encoding="ascii").strip().split("\n")
    claim = json.loads(lines[0])
    parts = claim["claim_id"].split("__")
    assert len(parts) == 4
    assert parts[0] == "test_fam"
    assert parts[2] == "pts_per_game"


def test_missing_floor_fails_closed_no_artifact_written(tmp_path):
    """A family declaring a career_to_date window (TYPE='career') with NO
    floors['career'] entry must raise FactoryError and write NOTHING."""
    src = tmp_path / "box.parquet"
    _synthetic_boxscore_rows().to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    del grid["families"][0]["floors"]["career"]
    out_dir = tmp_path / "out"

    with pytest.raises(cf.FactoryError):
        cf.generate_family("test_sport", "test_fam", grid, out_dir)
    assert not (out_dir / "test_fam.jsonl").exists()


def test_missing_split_floor_fails_closed(tmp_path):
    src = tmp_path / "box.parquet"
    _synthetic_boxscore_rows().to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    del grid["families"][0]["floors"]["split"]
    out_dir = tmp_path / "out"

    with pytest.raises(cf.FactoryError):
        cf.generate_family("test_sport", "test_fam", grid, out_dir)
    assert not (out_dir / "test_fam.jsonl").exists()


def test_honesty_lint_trip_aborts_no_artifact_written(tmp_path, monkeypatch):
    """Force a banned CLAIM TOKEN (never whitelisted, unlike a banned number
    in retraction framing -- governance/policy.py RETRACTION_MARKERS) into
    every claim's caveats and confirm the whole regen aborts, no jsonl
    written."""
    src = tmp_path / "box.parquet"
    _synthetic_boxscore_rows().to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    out_dir = tmp_path / "out"

    real_build = cf._build_dim_claim

    def poisoned_build(*args, **kwargs):
        claim = real_build(*args, **kwargs)
        claim["caveats"].append("this ranking is a guaranteed profit signal")
        return claim

    monkeypatch.setattr(cf, "_build_dim_claim", poisoned_build)
    with pytest.raises(cf.FactoryError, match="honesty lint"):
        cf.generate_family("test_sport", "test_fam", grid, out_dir)
    assert not (out_dir / "test_fam.jsonl").exists()


def test_edge_claimed_true_aborts_no_artifact_written(tmp_path, monkeypatch):
    src = tmp_path / "box.parquet"
    _synthetic_boxscore_rows().to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    out_dir = tmp_path / "out"

    real_build = cf._build_dim_claim

    def poisoned_build(*args, **kwargs):
        claim = real_build(*args, **kwargs)
        claim["edge_claimed"] = True
        return claim

    monkeypatch.setattr(cf, "_build_dim_claim", poisoned_build)
    with pytest.raises(cf.FactoryError, match="edge_claimed"):
        cf.generate_family("test_sport", "test_fam", grid, out_dir)
    assert not (out_dir / "test_fam.jsonl").exists()


def test_no_snapshot_written_when_window_slice_empty(tmp_path):
    """A window whose filter matches zero rows (e.g. a season absent from
    this source) must be silently skipped, not crash or emit an empty claim."""
    src = tmp_path / "box.parquet"
    _synthetic_boxscore_rows().to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    grid["families"][0]["windows"].append({"name": "season_1999_00", "filter": {"season": "1999-00"}})
    out_dir = tmp_path / "out"
    res = cf.generate_family("test_sport", "test_fam", grid, out_dir)
    lines = (out_dir / "test_fam.jsonl").read_text(encoding="ascii").strip().split("\n")
    for line in lines:
        assert "1999" not in json.loads(line)["criteria"]["window"]


def test_generate_family_unknown_family_raises(grid_and_out):
    grid, out_dir = grid_and_out
    with pytest.raises(cf.FactoryError):
        cf.generate_family("test_sport", "nonexistent_family", grid, out_dir)


def test_zero_denominator_excluded_never_emits_nan(tmp_path):
    """A ratio dim (ast_to_tov-shaped: num=sum(ast), den=sum(tov)) must
    exclude a zero-turnover player instead of emitting NaN/inf -- honestly
    counted in n_excluded_below_floor, same idiom as a below-floor exclusion.
    Regression test for the 442-row NaN class (player_id=0, sum(tov)=0)."""
    rows = _synthetic_boxscore_rows()
    rows["ast"] = 5
    rows["tov"] = rows["player_id"].map({1: 2, 2: 2, 3: 0})  # player 3: zero TOV all season

    grid = _tiny_grid(str(tmp_path / "box.parquet").replace("\\", "/"))
    grid["families"][0]["dims"] = [{"metric": "ast_to_tov", "agg": {"num": "sum(ast)", "den": "sum(tov)"}}]
    rows.to_parquet(tmp_path / "box.parquet")

    out_dir = tmp_path / "out"
    res = cf.generate_family("test_sport", "test_fam", grid, out_dir)
    assert res["n_excluded_below_floor"] > 0

    lines = (out_dir / "test_fam.jsonl").read_text(encoding="ascii").strip().split("\n")
    for line in lines:
        claim = json.loads(line)
        ranked_ids = {row["player_id"] for row in claim["ranking"]}
        assert 3 not in ranked_ids, "zero-tov player 3 must be excluded, not ranked"
        for row in claim["ranking"]:
            v = row["value"]
            assert v == v, f"{claim['claim_id']}: NaN value emitted"  # v==v is False iff NaN
            assert v not in (float("inf"), float("-inf")), f"{claim['claim_id']}: inf value emitted"
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_tennis_family_tied_values_break_by_entity_key_asc(tmp_path):
    """Regression for the tennis_p1_match_context / tennis_p2_match_context
    MISMATCH class (2026-07-19, 395/1312 mismatches on pod): two entities
    with an EXACT tied value must rank in entity_key ASC order and must
    independently VERIFY against claims_validator.validate_claim, which
    applies this same tie-break only when claim_id.startswith('tennis_')
    (claims_validator.py:192-209). Player 20 and player 10 both average
    exactly 10.0 pts/game -- without the tie-break fix, plain
    sort_values(ascending=False) has undefined order across the tie and can
    disagree with the validator's stable (value, entity_key ASC) recompute."""
    rows = _synthetic_boxscore_rows()
    rows["player_id"] = rows["player_id"].map({1: 20, 2: 10, 3: 30})
    src = tmp_path / "box.parquet"
    rows.to_parquet(src)
    grid = _tiny_grid(str(src).replace("\\", "/"))
    grid["families"][0]["family"] = "tennis_test_fam"

    res = cf.generate_family("test_sport", "tennis_test_fam", grid, tmp_path / "out")
    lines = (tmp_path / "out" / "tennis_test_fam.jsonl").read_text(encoding="ascii").strip().split("\n")
    career_claims = [json.loads(line) for line in lines if line and json.loads(line)["criteria"]["window"] == "career_to_date"]
    assert career_claims

    claim = career_claims[0]
    tied = [row for row in claim["ranking"] if row["value"] == pytest.approx(10.0)]
    tied_ids = [row["player_id"] for row in tied]
    assert set(tied_ids) >= {10, 20}, f"expected tied players 10,20 in ranking, got {tied_ids}"
    # entity_key ASC among the tied block -> 10 must be ranked ahead of 20.
    assert tied_ids.index(10) < tied_ids.index(20)

    for row_claim in career_claims:
        verdict = validate_claim(row_claim)
        assert verdict.verdict == "VERIFIED", f"{row_claim['claim_id']}: {verdict.reason}"


def test_no_edge_language_in_any_claim(grid_and_out):
    _BANNED = ("18.38", "0.119", "+54", "78.11", "8.94", "54.57", "roi", "bankroll", "pnl")
    grid, out_dir = grid_and_out
    cf.generate_family("test_sport", "test_fam", grid, out_dir)
    lines = (out_dir / "test_fam.jsonl").read_text(encoding="ascii").strip().split("\n")
    for line in lines:
        claim = json.loads(line)
        text = (" ".join(claim["caveats"]) + claim["question"]).lower()
        for token in _BANNED:
            assert token not in text, f"{claim['claim_id']}: banned token {token!r} found"
        assert claim["edge_claimed"] is False
