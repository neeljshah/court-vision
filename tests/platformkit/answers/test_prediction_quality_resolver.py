"""Per-file tests: prediction_quality resolver + classifier routing."""
import json

import pytest

from scripts.platformkit.answers import prediction_quality_resolver as pq
from scripts.platformkit.answers.resolver_registry import classify, resolve


@pytest.fixture()
def artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(pq, "_REPO", tmp_path)
    path = tmp_path / pq._ARTIFACT_REL
    path.parent.mkdir(parents=True)
    return path


def test_classifier_routes_quality_not_winprob():
    assert classify("how good are the predictions?") == "prediction_quality"
    assert classify("prediction quality for mlb") == "prediction_quality"
    assert classify("show the oos scoreboard") == "prediction_quality"
    # 2026-07-17 pod coverage-stress defect 2: a sport token inserted mid
    # -phrase ("how good are the WNBA predictions?") defeated the literal
    # "how good are the predictions" string match, so the bare "predict"
    # substring in _PREDICTION_KEYWORDS won first -> prediction_winprob.
    assert classify("how good are the WNBA predictions?") == "prediction_quality"
    assert classify("How good are the predictions for MLB?") == "prediction_quality"
    # bare winprob phrasing still routes to the winprob resolver
    assert classify("predict lakers vs celtics") == "prediction_winprob"


def test_missing_artifact_fails_closed(artifact):
    artifact.unlink(missing_ok=True)
    r = pq.resolve()
    assert r["status"] == "no_data" and "not generated" in r["note"]


def test_blocked_artifact_fails_closed(artifact):
    artifact.write_text(json.dumps(
        {"status": "blocked", "blocked_reason": "no data on box",
         "generated": "2026-07-17T00:00:00"}))
    r = pq.resolve()
    assert r["status"] == "no_data" and "no data on box" in r["note"]


def test_ok_artifact_quoted_verbatim_with_sport_filter(artifact):
    artifact.write_text(json.dumps({
        "status": "ok", "generated": "2026-07-17T00:00:00",
        "eval_gate": {"status": "green", "rc": 0},
        "scoreboard": [
            {"sport": "nba", "metric": "Brier", "value": 0.21},
            {"sport": "mlb", "metric": "Brier", "value": 0.24}],
        "n_sports_scored": 2, "n_sports_validated": 1,
        "note": "calibration, not edge"}))
    r = pq.resolve()
    assert r["status"] == "ok" and len(r["scoreboard"]) == 2
    assert r["eval_gate"]["status"] == "green"
    r_mlb = pq.resolve("mlb")
    assert [row["sport"] for row in r_mlb["scoreboard"]] == ["mlb"]
    r_none = pq.resolve("soccer")
    assert r_none["status"] == "no_data"


def test_registry_dispatch_uses_query_sport(artifact):
    artifact.write_text(json.dumps({
        "status": "ok", "generated": "x", "eval_gate": {},
        "scoreboard": [{"sport": "mlb", "metric": "Brier", "value": 0.24}],
        "n_sports_scored": 1, "n_sports_validated": 0, "note": "n"}))
    r = resolve("prediction quality for mlb")
    assert r["status"] == "ok" and r["scoreboard"][0]["sport"] == "mlb"


def test_sport_in_query_wnba_not_swallowed():
    assert pq.sport_in_query("wnba prediction quality") == "wnba"
    assert pq.sport_in_query("prediction quality") is None
