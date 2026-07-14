"""tests.platformkit.live_edge.test_validate_job -- AUTO-VALIDATE lane.

Covers: (1) MLB claim-shape classification (TESTED-with-delta -> parsed,
INSUFFICIENT_DATA/unparseable -> skipped); (2) one real tiny-slice cycle
through the actual mlb_grid/mlb_mine/harden pipeline (only the raw tick load
is faked, everything downstream -- dedupe, target-add, reserve split,
situation tagging, DM-clustered scoring -- is the real code); (3) watermark
idempotency: an unchanged GUMBO corpus makes a second cycle a true no-op
(mlb_testable=0, results parquet byte-identical row count).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.live_edge.autoloop import validate_job as vj
from scripts.platformkit.live_edge.mlb_ingame import mlb_grid


def _mlb_claim_row(claim_id: str, lifecycle: str, effect: dict) -> dict:
    scope = {"sport": "mlb", "entity_type": "league", "entity_ids": [],
              "context": {"cell": {"base_state": 0}, "stat": "run_scored_rest_half", "in_game_only": True}}
    return {"claim_id": claim_id, "topic": "mlb_ingame.test", "lifecycle": lifecycle,
            "sport": "mlb", "scope_json": json.dumps(scope), "effect_json": json.dumps(effect)}


def test_classify_mlb_shapes():
    tested = _mlb_claim_row("c1", "proposed", {"verdict": "TESTED", "delta": 0.1, "stat": "run_scored_rest_half",
                                                "n_a": 50, "n_b": 50})
    screened = _mlb_claim_row("c2", "screened", {"verdict": "INSUFFICIENT_DATA"})
    parsed = vj._classify_mlb(pd.Series(tested))
    assert parsed is not None and parsed["stat"] == "run_scored_rest_half" and parsed["delta"] == 0.1
    assert vj._classify_mlb(pd.Series(screened)) is None
    bad = dict(tested)
    bad["scope_json"] = "not json"
    assert vj._classify_mlb(pd.Series(bad)) is None


def _synthetic_ticks() -> pd.DataFrame:
    rows = []
    for i in range(16):
        rows.append({
            "game_pk": 100, "inning": 1 + (i % 9), "half": "Top" if i % 2 == 0 else "Bottom",
            "outs": i % 3, "balls": i % 4, "strikes": i % 3,
            "on_first": bool(i % 2), "on_second": False, "on_third": False,
            "score_home": i // 4, "score_away": i // 5,
            "batter_id": 1000 + (i % 5), "pitcher_id": 2000 + (i % 2),
            "base_state": i % 8, "base_label": str(i % 8),
            "date": "2026-07-07" if i < 12 else "2026-07-08",
        })
    return pd.DataFrame(rows)


@pytest.fixture
def _patched(tmp_path, monkeypatch):
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    gumbo_dir = tmp_path / "gumbo"
    gumbo_dir.mkdir()
    (gumbo_dir / "100.jsonl").write_text('{"game_pk": 100}\n', encoding="ascii")
    autoloop_dir = tmp_path / "autoloop"
    replay_dir = tmp_path / "replay"

    claim_a = _mlb_claim_row("claim_a", "proposed", {"verdict": "TESTED", "delta": 0.1,
                                                       "stat": "run_scored_rest_half", "n_a": 5, "n_b": 5})
    claim_b = _mlb_claim_row("claim_b", "screened", {"verdict": "INSUFFICIENT_DATA"})
    claims_df = pd.DataFrame([claim_a, claim_b])
    claims_path = claims_dir / "claims.parquet"
    claims_df.to_parquet(claims_path, index=False)

    monkeypatch.setattr(vj, "CLAIMS_PATH", claims_path)
    monkeypatch.setattr(vj, "RESULTS_PATH", replay_dir / "full_ledger_results.parquet")
    monkeypatch.setattr(vj, "AUTOLOOP_DIR", autoloop_dir)
    monkeypatch.setattr(vj, "WATERMARK_PATH", autoloop_dir / "watermark.json")
    monkeypatch.setattr(vj, "CYCLE_LOG_PATH", autoloop_dir / "cycle_log.jsonl")
    monkeypatch.setattr(vj, "GUMBO_DIR", gumbo_dir)
    # NBA path disabled for this unit test: POSSESSIONS_PATH pointed at a
    # nonexistent file -> mtime 0.0, never exceeds the 0.0 watermark default.
    monkeypatch.setattr(vj, "POSSESSIONS_PATH", tmp_path / "no_such_possessions.parquet")
    monkeypatch.setattr(mlb_grid, "load_ticks", lambda source=None: _synthetic_ticks())
    return replay_dir / "full_ledger_results.parquet", autoloop_dir / "watermark.json"


def test_one_real_tiny_slice_cycle_then_idempotent(_patched):
    results_path, watermark_path = _patched

    first = vj.run_validate_cycle()
    assert first["picked_up"] == 2          # both mlb claims are unresolved candidates
    assert first["mlb_testable"] == 1       # only claim_a has a TESTED delta+stat shape
    assert first["nba_testable"] == 0
    assert first["tested"] == 1
    assert results_path.exists()
    results = pd.read_parquet(results_path)
    assert len(results) == 1
    assert results.iloc[0]["claim_id"] == "claim_a"
    assert results.iloc[0]["grain"] == "mlb_league"
    # tiny synthetic corpus is far below MIN_ACTIVE=30 -> honest INSUFFICIENT_DATA
    assert results.iloc[0]["verdict"] == "INSUFFICIENT_DATA"
    assert watermark_path.exists()
    wm_after_first = json.loads(watermark_path.read_text(encoding="ascii"))
    assert wm_after_first["mlb_corpus_mtime"] > 0.0

    second = vj.run_validate_cycle()
    # claim_a stayed INSUFFICIENT_DATA (still "unresolved"), but the GUMBO
    # corpus mtime is unchanged since the first run -> mlb_gated is False ->
    # a true no-op, not a wasted rescore.
    assert second["mlb_testable"] == 0
    assert second["tested"] == 0
    results_after_second = pd.read_parquet(results_path)
    assert len(results_after_second) == 1
    assert results_after_second.iloc[0]["claim_id"] == "claim_a"
    wm_after_second = json.loads(watermark_path.read_text(encoding="ascii"))
    assert wm_after_second["mlb_corpus_mtime"] == wm_after_first["mlb_corpus_mtime"]
    assert wm_after_second["last_run_ts"] >= wm_after_first["last_run_ts"]
