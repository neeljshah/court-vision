"""tests for scripts.platformkit.intel_validation.claims_validator -- an
independent recomputation of ranking claims against parquet source files.

Core deliverable: a claim with a PLANTED ERROR (wrong rank order, wrong
value, AND a smuggled min_sample floor violation) must be caught as
MISMATCH. A validator that cannot catch a planted error is worthless.

Run ONLY this file:
    python -m pytest tests/platformkit/intel_validation/test_claims_validator.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.intel_validation.claims_validator import (  # noqa: E402
    validate_claim,
    validate_claims_file,
    write_summary,
)


def _make_parquet(tmp_path: Path, name: str, rows: list[dict]) -> str:
    """Writes a synthetic mini-parquet under tmp_path and returns a
    repo-relative-looking path resolvable by the validator (we monkeypatch
    REPO_ROOT-relative loading by writing an absolute path claim instead --
    simplest: source_files store an absolute path string, which
    _load_source_frame resolves via REPO_ROOT / rel; on Windows an absolute
    path joined with REPO_ROOT via Path.__truediv__ still resolves to the
    absolute path itself, so this works cross-platform)."""
    df = pd.DataFrame(rows)
    p = tmp_path / name
    df.to_parquet(p)
    return str(p)


def _base_players() -> list[dict]:
    return [
        {"player_id": "101", "player_name": "Alpha", "fg3_pct": 0.45, "fg3a": 300},
        {"player_id": "102", "player_name": "Bravo", "fg3_pct": 0.40, "fg3a": 250},
        {"player_id": "103", "player_name": "Charlie", "fg3_pct": 0.38, "fg3a": 200},
        {"player_id": "104", "player_name": "Delta", "fg3_pct": 0.50, "fg3a": 20},  # below floor
    ]


def _correct_claim(source_path: str) -> dict:
    return {
        "claim_id": "top3_fg3pct",
        "kind": "ranking",
        "question": "Who leads the league in 3pt%?",
        "criteria": {
            "metric": "fg3_pct",
            "formula": "fg3_pct",
            "window": "season",
            "min_sample": {"fg3a": 100},
            "direction": "desc",
        },
        "ranking": [
            {"rank": 1, "player_id": "101", "player_name": "Alpha", "value": 0.45, "n": 300},
            {"rank": 2, "player_id": "102", "player_name": "Bravo", "value": 0.40, "n": 250},
            {"rank": 3, "player_id": "103", "player_name": "Charlie", "value": 0.38, "n": 200},
        ],
        "source_files": [source_path],
        "computed_at": "2026-07-04T00:00:00+00:00",
        "n_considered": 3,
        "n_excluded_below_floor": 1,
        "caveats": [],
    }


def test_correct_claim_is_verified(tmp_path):
    src = _make_parquet(tmp_path, "shooting.parquet", _base_players())
    claim = _correct_claim(src)
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_planted_error_wrong_rank_order_is_mismatch(tmp_path):
    src = _make_parquet(tmp_path, "shooting.parquet", _base_players())
    claim = _correct_claim(src)
    # PLANT: swap rank 1 and rank 2 -- Bravo claimed as #1 leader despite lower pct.
    claim["ranking"][0] = {"rank": 1, "player_id": "102", "player_name": "Bravo", "value": 0.40, "n": 250}
    claim["ranking"][1] = {"rank": 2, "player_id": "101", "player_name": "Alpha", "value": 0.45, "n": 300}
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"
    assert verdict.first_divergence is not None
    assert verdict.first_divergence["rank"] == 1


def test_planted_error_wrong_value_is_mismatch(tmp_path):
    src = _make_parquet(tmp_path, "shooting.parquet", _base_players())
    claim = _correct_claim(src)
    # PLANT: inflate rank 1's claimed value beyond tolerance.
    claim["ranking"][0]["value"] = 0.99
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"
    assert "value" in verdict.reason


def test_planted_error_floor_violation_smuggled_in_is_mismatch(tmp_path):
    src = _make_parquet(tmp_path, "shooting.parquet", _base_players())
    claim = _correct_claim(src)
    # PLANT: smuggle Delta (fg3a=20, below the min_sample floor of 100) into
    # the ranking as a false #1, with a value that matches the real data so
    # only the floor check catches it.
    claim["ranking"] = [
        {"rank": 1, "player_id": "104", "player_name": "Delta", "value": 0.50, "n": 20},
        {"rank": 2, "player_id": "101", "player_name": "Alpha", "value": 0.45, "n": 300},
        {"rank": 3, "player_id": "102", "player_name": "Bravo", "value": 0.40, "n": 250},
    ]
    verdict = validate_claim(claim)
    # Delta is excluded by the floor entirely, so recomputed pool has only 3
    # rows (101,102,103) and rank 1 in the recomputed pool is Alpha, not
    # Delta -- this is caught as a player_id mismatch at rank 1.
    assert verdict.verdict == "MISMATCH"
    assert verdict.first_divergence["rank"] == 1


def test_missing_source_file_is_unverifiable(tmp_path):
    claim = _correct_claim(str(tmp_path / "does_not_exist.parquet"))
    verdict = validate_claim(claim)
    assert verdict.verdict == "UNVERIFIABLE"
    assert "source file missing" in verdict.reason


def test_missing_formula_is_unverifiable(tmp_path):
    src = _make_parquet(tmp_path, "shooting.parquet", _base_players())
    claim = _correct_claim(src)
    del claim["criteria"]["formula"]
    verdict = validate_claim(claim)
    assert verdict.verdict == "UNVERIFIABLE"


def test_unsafe_formula_rejected_as_unverifiable(tmp_path):
    src = _make_parquet(tmp_path, "shooting.parquet", _base_players())
    claim = _correct_claim(src)
    claim["criteria"]["formula"] = "__import__('os').system('echo pwned')"
    verdict = validate_claim(claim)
    assert verdict.verdict == "UNVERIFIABLE"


def test_derived_formula_verified(tmp_path):
    """A formula that's a real arithmetic expression over two columns,
    not just a bare column reference."""
    rows = [
        {"player_id": "1", "player_name": "A", "pts": 30.0, "reb": 10.0, "gp": 60},
        {"player_id": "2", "player_name": "B", "pts": 20.0, "reb": 5.0, "gp": 55},
    ]
    src = _make_parquet(tmp_path, "combo.parquet", rows)
    claim = {
        "claim_id": "pts_plus_reb",
        "kind": "ranking",
        "question": "Who has the highest pts+reb?",
        "criteria": {
            "metric": "pts_plus_reb",
            "formula": "pts + reb",
            "window": "season",
            "min_sample": {"gp": 10},
            "direction": "desc",
        },
        "ranking": [
            {"rank": 1, "player_id": "1", "player_name": "A", "value": 40.0, "n": 60},
            {"rank": 2, "player_id": "2", "player_name": "B", "value": 25.0, "n": 55},
        ],
        "source_files": [src],
        "computed_at": "2026-07-04T00:00:00+00:00",
        "n_considered": 2,
        "n_excluded_below_floor": 0,
        "caveats": [],
    }
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def _pergame_rows() -> list[dict]:
    """RAW per-game rows (contract-extension path): floors reference DERIVED
    per-player columns (games) that only exist after the declared aggregation."""
    rows = []
    for g, pts in enumerate([10, 10, 20, 30]):  # player 11: last-2 = 20,30 -> ppg 25
        rows.append({"player_id": "11", "game_id": f"a{g}", "date": f"2026-01-0{g + 1}",
                     "season": "2025-26", "pts": pts})
    rows.append({"player_id": "22", "game_id": "b0", "date": "2026-01-01",
                 "season": "2025-26", "pts": 40})  # 1 game -> below games>=2 floor
    for g in range(3):  # player 33: ppg 10 in any window
        rows.append({"player_id": "33", "game_id": f"c{g}", "date": f"2026-01-0{g + 1}",
                     "season": "2025-26", "pts": 10})
    return rows


def _aggregate_claim(source_path: str) -> dict:
    return {
        "claim_id": "ppg_last2",
        "kind": "ranking",
        "question": "Top scorers per game over their last 2 games?",
        "criteria": {
            "metric": "ppg",
            "formula": "sum(pts)/count_distinct(game_id)",
            "window": "last_2",
            "window_spec": {"kind": "last_n_games", "n": 2, "order_by": "date",
                            "season": None, "season_col": None},
            "aggregate": {"group_by": "player_id",
                          "derived": {"games": "count_distinct(game_id)"}},
            "min_sample": {"games": 2},
            "direction": "desc",
            "value_precision": 4,
        },
        "ranking": [
            {"rank": 1, "player_id": "11", "player_name": "Ace", "value": 25.0, "n": 2},
            {"rank": 2, "player_id": "33", "player_name": "Cal", "value": 10.0, "n": 2},
        ],
        "source_files": [source_path],
        "computed_at": "2026-07-04T00:00:00+00:00",
        "n_considered": 3,
        "n_excluded_below_floor": 1,
        "caveats": [],
    }


def test_aggregate_window_claim_with_derived_floor_verifies(tmp_path):
    """Contract-extension path: window_spec (last_n_games) + aggregate.derived
    floor column (games) recomputed from RAW rows, then floors + ranking."""
    src = _make_parquet(tmp_path, "pergame.parquet", _pergame_rows())
    verdict = validate_claim(_aggregate_claim(src))
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_planted_wrong_aggregation_is_mismatch(tmp_path):
    """PLANT: value computed over the WHOLE season (mean ppg 17.5) instead of
    the declared last-2-games window (25.0) -- must be caught."""
    src = _make_parquet(tmp_path, "pergame.parquet", _pergame_rows())
    claim = _aggregate_claim(src)
    claim["ranking"][0]["value"] = 17.5  # 70 pts / 4 games, wrong window
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"
    assert "value" in verdict.reason


def test_planted_below_derived_floor_player_is_mismatch(tmp_path):
    """PLANT: smuggle player 22 (games=1, below the DERIVED games>=2 floor)
    into rank 1 with his true ppg -- only the derived-floor recompute
    excludes him, so rank 1 must recompute as a different player."""
    src = _make_parquet(tmp_path, "pergame.parquet", _pergame_rows())
    claim = _aggregate_claim(src)
    claim["ranking"] = [
        {"rank": 1, "player_id": "22", "player_name": "Bo", "value": 40.0, "n": 1},
        {"rank": 2, "player_id": "11", "player_name": "Ace", "value": 25.0, "n": 2},
    ]
    claim["n_excluded_below_floor"] = 0
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"
    assert verdict.first_divergence["rank"] == 1


def test_validate_claims_file_and_summary_shape(tmp_path):
    src = _make_parquet(tmp_path, "shooting.parquet", _base_players())
    good = _correct_claim(src)
    bad = _correct_claim(src)
    bad["claim_id"] = "top3_fg3pct_planted"
    bad["ranking"][0]["value"] = 0.99

    claims_path = tmp_path / "claims.jsonl"
    with open(claims_path, "w", encoding="ascii") as f:
        f.write(json.dumps(good) + "\n")
        f.write(json.dumps(bad) + "\n")
        f.write(json.dumps({**_correct_claim("missing.parquet"), "claim_id": "missing_src"}) + "\n")

    summary = validate_claims_file(claims_path)
    assert summary.n_claims == 3
    assert summary.n_verified == 1
    assert summary.n_mismatch == 1
    assert summary.n_unverifiable == 1
    assert summary.edge_claimed is False

    out_path = tmp_path / "out.json"
    write_summary(summary, out_path)
    payload = json.loads(out_path.read_text(encoding="ascii"))
    assert payload["component"] == "intel_claims_validation"
    assert payload["n_claims"] == 3
    assert payload["edge_claimed"] is False
    assert len(payload["details"]) == 3
