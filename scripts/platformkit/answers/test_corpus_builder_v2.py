"""Per-file test for scripts.platformkit.answers.corpus_builder_v2.

Fixture-first: a synthetic repo root with one tiny artifact per family, so the
per-family row counts, the source_file/caveat contract, the refusal family, and
byte-stable regeneration are all proven without touching the real corpus.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/answers/test_corpus_builder_v2.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.answers import corpus_builder_v2 as B

# Expected rows per family for the fixture below (see _make_root).
EXPECTED = {
    "wp_calibration_audit": 8,   # 2 headline pairs + 2 bins + 1 oos sport x 2
    "market_lag": 7,             # study 2 + window calib 2 + replay 2 + 1 sport
    "signal_lift": 6,            # 2 screens x 2 + ensemble 2
    "signal_foundry_ledger": 4,  # 2 distinct signals x 2
    "tracking_quality": 2,       # 1 report x 2
    "regime_calibration": 4,     # 2 headline + 2 buckets
    "refusal": len(B.REFUSAL_PROMPTS),
}


def _w(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="ascii")


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    ab = tmp_path / "data" / "ab_reports"
    _w(ab / "wp_diagnostics_20260101T000000Z.json", {
        "generated_at": "20260101T000000Z", "tick_count": 500,
        "isotonic_check": {"brier_before": 0.24, "brier_after": 0.22, "delta": 0.02},
        "max_loser_wp": {"above_0_8": 3, "above_0_9": 1,
                         "per_game": [{"game": "G1", "max_loser_wp": 0.7}]},
        "reliability": [
            {"bin": "0.0-0.1", "flag": True, "gap": 0.21, "mean_predicted_prob": 0.05,
             "n": 100, "observed_win_freq": 0.26, "status": "OK"},
            {"bin": "0.9-1.0", "flag": False, "gap": 0.01, "mean_predicted_prob": 0.95,
             "n": 120, "observed_win_freq": 0.96, "status": "OK"},
        ],
    })
    _w(ab / "wp_oos_20260101T000000Z.json", {"sports": {"KXMLBGAME": {
        "tick_count": 400,
        "walk_forward_isotonic": {"fold_count": 2, "folds": [
            {"fold": 1, "brier_before": 0.23, "brier_after": 0.22},
            {"fold": 2, "brier_before": 0.21, "brier_after": 0.20}]}}}})
    _w(ab / "market_lag_study.json", {
        "generated_at": "2026-01-01", "horizon_ticks": 10, "threshold_fraction": 0.7,
        "summaries": [{"event_size": "1-run", "events": 12, "sport": "all", "series": {
            "market_prob": {"lag_seconds": {"median": 33.0, "p75": 175.0},
                            "lag_ticks": {"median": 2.0, "p75": 6.0},
                            "lagged_events": 7, "usable_events": 12}}}]})
    _w(ab / "lag_window_calibration.json", {
        "window_seconds": 180.0, "bootstrap_iterations": 500, "bootstrap_seed": 20260831,
        "summaries": [{"sport": "mlb", "brier_model_window": 0.2337,
                       "brier_market_window": 0.1870, "delta": -0.0466,
                       "window_delta_ci_90": [-0.064, -0.028],
                       "n_events": 1872, "n_ticks": 14618}]})
    _w(ab / "window_strategy_replay.json", {
        "spec": {"window_s": 159.0, "threshold": 0.05},
        "honest_verdict": {"status": "NEGATIVE", "finding": "model LOSES in-window",
                           "edge_claim": False, "live_arming": "DISARMED",
                           "benchmark_purpose": "flip before arming"},
        "by_sport": {"mlb": {"entry_brier": 0.2358, "market_brier": 0.1888,
                             "n_entries": 1664, "n_events": 1872}}})
    _w(ab / "novel_metric_lift.json", {
        "target": "next-game minutes", "rows_evaluated": 25699,
        "screens": {
            "b2b_speed_drop": {"mae_base": 5.88, "mae_candidate": 5.82, "delta": -0.06,
                               "folds": [1, 2, 3, 4], "verdict": "FLAT"},
            "all_four": {"mae_base": 5.88, "mae_candidate": 5.78, "delta": -0.10,
                         "folds": [1, 2, 3, 4], "verdict": "FLAT"}}})
    _w(ab / "signal_ensemble.json", {
        "target": "next-game minutes", "rows_evaluated": 25699, "verdict": "IMPROVED",
        "mae_base": 5.88, "mae_ensemble": 5.75, "delta": -0.13,
        "folds": [1, 2, 3, 4], "base_columns": ["a", "b"], "weak_columns": ["c"]})
    _w(ab / "foundry_ledger.jsonl", "\n".join(json.dumps(r) for r in [
        {"ts": "2026-08-31T22:48:15Z", "signal": "load_speed_elasticity", "sport": "nba",
         "n_trials_total": 1, "grade": "FLAT", "lift": 0.005, "z": 1.09},
        {"ts": "2026-08-31T22:58:15Z", "signal": "load_speed_elasticity", "sport": "nba",
         "n_trials_total": 2, "grade": "FLAT", "lift": 0.004, "z": 0.90},
        {"ts": "2026-08-31T23:08:15Z", "signal": "b2b_speed_drop", "sport": "nba",
         "n_trials_total": 3, "grade": "FLAT", "lift": 0.002, "z": 0.40}]) + "\n")
    _w(tmp_path / "data" / "tracking_reports" / "tennis" / "t1.json", {
        "sport": "tennis", "n_frames": 4224, "coverage_pct": 1.0, "det_per_frame": 2.0,
        "median_track_len": 4224.0, "ball_valid_pct": 0.0, "jump_p95": 40.17,
        "oob_pct": 0.0, "passed": False, "failures": ["ball_valid 0.00 < 0.2"]})
    _w(ab / "regime_calibration.json", {
        "global_reliability": 0.139, "tick_count": 164621, "min_n": 200, "buckets": [
            {"bucket": "month=06|confidence=T1", "reliability": 0.164,
             "global_reliability": 0.139, "reliability_gap": 0.025, "z_score": 24.4,
             "n": 22673, "status": "SIGNIFICANT"},
            {"bucket": "month=07|confidence=T3", "reliability": 0.141,
             "global_reliability": 0.139, "reliability_gap": 0.002, "z_score": 1.1,
             "n": 9000, "status": "OK"}]})
    _w(tmp_path / B.RULE_REL, "# No edge claims\n")
    return tmp_path


def test_counts_per_family(root: Path):
    assert B.summarize(B.build(root)) == EXPECTED


def test_every_entry_carries_source_and_caveat(root: Path):
    for entry in B.build(root):
        assert set(entry) == {"question", "intent", "answer", "source_file",
                              "caveat", "generated_at"}
        rel = entry["source_file"]
        assert rel and not rel.startswith("/") and ":" not in rel  # repo-relative
        assert (root / rel).exists()
        assert entry["caveat"] == B.CAVEATS[entry["intent"]]
        assert rel in entry["answer"] and entry["question"] and entry["generated_at"]
        assert entry["answer"].isascii() and entry["question"].isascii()


def test_refusal_family_cites_the_rule(root: Path):
    refusals = [e for e in B.build(root) if e["intent"] == "refusal"]
    assert len(refusals) == len(B.REFUSAL_PROMPTS)
    for entry in refusals:
        assert entry["answer"].startswith("REFUSED.")
        assert B.RULE_REL in entry["answer"]
        assert entry["source_file"] == B.RULE_REL


def test_answers_are_filled_from_the_artifact(root: Path):
    joined = " ".join(e["answer"] for e in B.build(root))
    assert "0.2400" in joined and "0.2200" in joined      # isotonic before/after
    assert "median_lag_seconds 33.0" in joined            # market lag median seconds
    assert "model LOSES in-window" in joined              # verbatim honest_verdict
    assert "n_trials_total 3" in joined                   # newest foundry row per signal
    assert "month=06|confidence=T1" in joined             # regime bucket label


def test_regeneration_is_byte_stable(root: Path):
    out = root / B.OUT_REL
    first = B.write(B.build(root), out).read_bytes()
    second = B.write(B.build(root), out).read_bytes()
    assert first == second and first.count(b"\n") == sum(EXPECTED.values())


def test_missing_artifacts_yield_only_refusals(tmp_path: Path):
    _w(tmp_path / B.RULE_REL, "# No edge claims\n")
    assert B.summarize(B.build(tmp_path)) == {"refusal": len(B.REFUSAL_PROMPTS)}
