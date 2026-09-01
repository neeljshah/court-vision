"""Per-file test for answers.calibration_resolver -- fixture artifacts in tmp,
one assertion set per intent, plus the three fail-closed paths (no_data /
not_supported / refused) and the "model trails the market" honesty rail.

Run: python -m pytest scripts/platformkit/answers/test_calibration_resolver.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.answers import calibration_resolver as cr

# Shapes mirror the real artifacts on disk (data/ab_reports/, read 2026-08-31);
# values are small stand-ins so the test never depends on a regenerated report.
_DIAG = {
    "generated_at": "20260831T204320Z",
    "tick_count": 1000,
    "isotonic_check": {"brier_before": 0.24, "brier_after": 0.22, "delta": 0.02},
    "reliability": [
        {"bin": "0.0-0.1", "mean_predicted_prob": 0.05, "observed_win_freq": 0.27,
         "gap": 0.22, "n": 400, "status": "OK"},
        {"bin": "0.4-0.5", "mean_predicted_prob": 0.45, "observed_win_freq": 0.44,
         "gap": -0.01, "n": 300, "status": "OK"},
        {"bin": "0.9-1.0", "mean_predicted_prob": 0.95, "observed_win_freq": 0.67,
         "gap": -0.28, "n": 300, "status": "OK"},
    ],
}
_OOS = {
    "generated_at": "20260831T205014Z",
    "sports": {"KXMLBGAME": {"tick_count": 900, "walk_forward_isotonic": {
        "fold_count": 2, "note": "ONLY OOS DELTAS COUNT",
        "pooled": {"brier_before": 0.236, "brier_after": 0.228, "delta": 0.008,
                   "test_ticks": 900},
        "folds": [{"fold": 1, "delta": 0.004}, {"fold": 2, "delta": 0.012}]}}},
}
_LAG_WINDOW = {
    "generated_at": "2026-08-31T22:01:21+00:00", "window_seconds": 180.0,
    "summaries": [{"sport": "mlb", "brier_model_window": 0.2337,
                   "brier_market_window": 0.1870, "delta": -0.0466,
                   "n_ticks": 14618, "n_events": 1872}],
}
_LAG_STUDY = {
    "generated_at": "2026-08-31T21:49:42+00:00", "horizon_ticks": 10,
    "threshold_fraction": 0.7, "events": [{"game": "G1"}],
    "summaries": [{"sport": "mlb", "event_size": "all", "events": 1872,
                   "series": {"market_prob": {"lag_ticks": {"median": 2.0}}}}],
}
_REGIME = {
    "generated_at": "2026-09-01T00:13:42+00:00", "tick_count": 1000, "min_n": 200,
    "global_reliability": 0.139,
    "buckets": [{"bucket": "month=06|confidence=T1", "reliability_gap": 0.025,
                 "n": 500, "status": "SIGNIFICANT"},
                {"bucket": "month=07|confidence=T3", "reliability_gap": -0.004,
                 "n": 500, "status": "NS"}],
}
_SERIES = {
    "generated_at": "20260831T204953Z",
    "raw_probability_fields": ["close_prob", "market_prob", "model_prob"],
    "series": {"model_prob": {"overall": {"n_games": 268,
                                          "sports_breakdown": {"mlb": 227}},
                              "by_sport": {"mlb": {"n_games": 227}}}},
}
_REPLAY = {
    "generated_at": "2026-08-31T22:31:39+00:00",
    "spec": {"window_s": 159.0, "horizon_ticks": 10},
    "by_sport": {"mlb": {"sport": "mlb", "entry_brier": 0.2358,
                         "market_brier": 0.1888, "n_entries": 1664}},
    "calibration_oos": {"mlb": {"pooled": {"delta": 0.0082}}},
    "honest_verdict": {"edge_claim": False,
                       "finding": "lag_window_calibration: current model LOSES in-window"},
}


@pytest.fixture()
def reports(tmp_path: Path) -> Path:
    d = tmp_path / "ab_reports"
    d.mkdir()
    # an OLDER diagnostics file must lose to the newer one
    (d / "wp_diagnostics_20260101T000000Z.json").write_text(
        json.dumps({"generated_at": "20260101T000000Z", "tick_count": 1,
                    "reliability": [{"bin": "0.0-0.1", "mean_predicted_prob": 0.05,
                                     "observed_win_freq": 0.05, "gap": 0.0, "n": 1}]}),
        encoding="utf-8")
    for name, payload in [("wp_diagnostics_20260831T204320Z.json", _DIAG),
                          ("wp_oos_20260831T205014Z.json", _OOS),
                          ("wp_series_audit_20260831T204953Z.json", _SERIES),
                          ("lag_window_calibration.json", _LAG_WINDOW),
                          ("market_lag_study.json", _LAG_STUDY),
                          ("window_strategy_replay.json", _REPLAY),
                          ("regime_calibration.json", _REGIME)]:
        (d / name).write_text(json.dumps(payload), encoding="utf-8")
    return d


def test_overall_quotes_newest_diagnostics(reports: Path) -> None:
    e = cr.resolve("how calibrated is the in-game model", reports_dir=reports)
    assert e["status"] == "ok" and e["intent"] == "overall"
    assert e["source_artifact"] == "data/ab_reports/wp_diagnostics_20260831T204320Z.json"
    assert e["as_of"] == "20260831T204320Z" and e["tick_count"] == 1000
    assert e["worst_bin"]["bin"] == "0.9-1.0" and e["max_abs_reliability_gap"] == 0.28
    assert "0.9-1.0" in e["verdict"]


def test_overconfidence_flags_the_extremes(reports: Path) -> None:
    e = cr.resolve("where is the model overconfident", reports_dir=reports)
    assert e["status"] == "ok" and e["intent"] == "overconfidence"
    # 0.0-0.1 (pred 0.05 vs obs 0.27) and 0.9-1.0 (0.95 vs 0.67) are overconfident;
    # 0.4-0.5 (0.45 vs 0.44) is not -- it predicts CLOSER to 0.5 than observed.
    assert e["n_bins_overconfident"] == 2 and e["n_bins_total"] == 3
    assert [r["bin"] for r in e["overconfident_bins"]] == ["0.9-1.0", "0.0-0.1"]


def test_isotonic_reports_walk_forward_pooled_delta(reports: Path) -> None:
    e = cr.resolve("did isotonic help", sport="mlb", reports_dir=reports)
    assert e["status"] == "ok" and e["intent"] == "isotonic"
    assert e["source_artifact"] == "data/ab_reports/wp_oos_20260831T205014Z.json"
    assert e["by_series"]["KXMLBGAME"]["pooled"]["delta"] == 0.008
    assert "IMPROVED" in e["verdict"]


def test_reliability_bins_returned_verbatim(reports: Path) -> None:
    e = cr.resolve("what is the reliability by bin", reports_dir=reports)
    assert e["status"] == "ok" and e["intent"] == "reliability_bins"
    assert e["reliability"] == _DIAG["reliability"]


def test_market_window_says_trails_plainly(reports: Path) -> None:
    e = cr.resolve("how does the model compare to the market in-window", reports_dir=reports)
    assert e["status"] == "ok" and e["intent"] == "market_window"
    assert e["source_artifact"] == "data/ab_reports/lag_window_calibration.json"
    assert "TRAILS" in e["verdict"] and "0.2337" in e["verdict"]


def test_replay_quotes_the_artifacts_own_honest_verdict(reports: Path) -> None:
    e = cr.resolve("what did the window strategy replay show", reports_dir=reports)
    assert e["status"] == "ok" and "TRAILS the market" in e["verdict"]
    assert e["honest_verdict"]["edge_claim"] is False


def test_regime_and_lag_and_coverage_intents(reports: Path) -> None:
    reg = cr.resolve("which regimes break down", reports_dir=reports)
    assert reg["status"] == "ok" and reg["n_significant"] == 1
    assert reg["worst_buckets"][0]["bucket"] == "month=06|confidence=T1"
    lag = cr.resolve("how laggy is the market after a scoring event", reports_dir=reports)
    assert lag["status"] == "ok" and lag["intent"] == "market_lag"
    assert lag["source_artifact"] == "data/ab_reports/market_lag_study.json"
    cov = cr.resolve("how much data is behind this", reports_dir=reports)
    assert cov["status"] == "ok" and cov["model_prob_overall"]["n_games"] == 268


def test_missing_artifact_is_no_data(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    e = cr.resolve("how calibrated is the in-game model", reports_dir=empty)
    assert e["status"] == "no_data" and "wp_diagnostics_*.json" in e["source_artifact"]


def test_unparseable_artifact_is_no_data(reports: Path) -> None:
    (reports / "regime_calibration.json").write_text("{not json", encoding="utf-8")
    e = cr.resolve("which regimes break down", reports_dir=reports)
    assert e["status"] == "no_data" and "unreadable" in e["note"]


def test_unknown_sport_is_no_data_not_an_invented_answer(reports: Path) -> None:
    e = cr.resolve("did isotonic help", sport="nba", reports_dir=reports)
    assert e["status"] == "no_data" and "isotonic" in e["note"]


def test_edge_seeking_question_is_refused(reports: Path) -> None:
    for q in ["what is the ROI of the in-game model",
              "is there an edge in-window", "how much profit does the model make"]:
        e = cr.resolve(q, reports_dir=reports)
        assert e["status"] == "refused"
        assert e["source_artifact"] == ".claude/rules/no-edge-claims.md"


def test_unrecognised_question_is_not_supported(reports: Path) -> None:
    e = cr.resolve("who wins tonight", reports_dir=reports)
    assert e["status"] == "not_supported" and e["intent"] is None


def test_no_absolute_path_leaks_into_any_envelope(reports: Path) -> None:
    for q in ["how calibrated is the in-game model", "did isotonic help",
              "what is the reliability by bin", "how much data is behind this"]:
        blob = json.dumps(cr.resolve(q, reports_dir=reports), default=str)
        assert ":\\" not in blob and "/home/" not in blob
