"""Per-file test for scoreboard_history (tmp_path only)."""
import json

from scripts.platformkit.scoreboard_history import append_rows


def _src(tmp_path, gen="2026-07-09T00:00:00Z"):
    p = tmp_path / "src.json"
    p.write_text(json.dumps({
        "generated_at": gen,
        "calibration_scoreboard": {"per_sport": [
            {"sport": "nba", "n": 100, "baseline_brier": 0.22,
             "improved_brier": 0.21, "baseline_ece": 0.03,
             "improved_ece": 0.02, "method": "wf_logistic"},
        ]},
    }), encoding="utf-8")
    return p


def test_append_and_idempotent(tmp_path):
    src = _src(tmp_path)
    hist = tmp_path / "hist.jsonl"
    r1 = append_rows(source_path=src, history_path=hist)
    assert r1["appended"] == 1
    r2 = append_rows(source_path=src, history_path=hist)
    assert r2["appended"] == 0
    rows = [json.loads(l) for l in hist.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["sport"] == "nba"
    assert rows[0]["model_tag"] == "wf_logistic"


def test_new_generation_appends(tmp_path):
    hist = tmp_path / "hist.jsonl"
    append_rows(source_path=_src(tmp_path), history_path=hist)
    r = append_rows(source_path=_src(tmp_path, gen="2026-07-10T00:00:00Z"),
                    history_path=hist)
    assert r["appended"] == 1


def test_missing_source(tmp_path):
    r = append_rows(source_path=tmp_path / "nope.json",
                    history_path=tmp_path / "h.jsonl")
    assert r["status"] == "no_source"
