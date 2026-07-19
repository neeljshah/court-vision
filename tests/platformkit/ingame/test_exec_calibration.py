"""Per-file test: exec_calibration (execution-calibration measurement, Kalshi paper in-play).

cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_exec_calibration.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame import exec_calibration as m


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_spread_cost_null_safe_skip():
    rows = [{"exec_gate": {"spread_bp": 10.0}}, {"exec_gate": {}}, {"no_gate": True}, {}]
    d = m.spread_cost(rows)
    assert d["n"] == 1
    assert d["median"] == 10.0


def test_quote_staleness_percentiles():
    rows = [{"placement_latency_ms": v} for v in [10, 20, 30, 40, 100]]
    d = m.quote_staleness(rows)
    assert d["n"] == 5
    assert d["median"] == 30
    assert d["max"] == 100
    assert d["p90"] is not None


def test_adverse_selection_home_side_negative_when_market_drops(tmp_path):
    grade_dir = tmp_path / "grade"
    grade_rows = [
        {"ts": "2026-07-19T00:00:00+00:00", "market_prob": 0.60},
        {"ts": "2026-07-19T00:10:00+00:00", "market_prob": 0.40},  # >5min later, dropped
    ]
    _write_jsonl(grade_dir / "mlb" / "G1.jsonl", grade_rows)
    ledger_rows = [{
        "ts": "2026-07-19T00:00:00+00:00", "sport": "mlb", "game_id": "G1", "side": "home",
        "taken_decimal": 2.0, "channel": "paper_ingame",
    }]
    out = m.adverse_selection(ledger_rows, grade_dir)
    assert out["mlb"]["n"] == 1
    # fill_p = 0.5, post_p = 0.40 -> adverse_move = -0.10 (moved against home)
    assert out["mlb"]["mean"] < 0


def test_adverse_selection_away_side_sign_flip(tmp_path):
    grade_dir = tmp_path / "grade"
    grade_rows = [
        {"ts": "2026-07-19T00:00:00+00:00", "market_prob": 0.60},
        {"ts": "2026-07-19T00:10:00+00:00", "market_prob": 0.80},  # home prob rose -> away side hurt
    ]
    _write_jsonl(grade_dir / "mlb" / "G2.jsonl", grade_rows)
    ledger_rows = [{
        "ts": "2026-07-19T00:00:00+00:00", "sport": "mlb", "game_id": "G2", "side": "away",
        "taken_decimal": 2.0, "channel": "paper_ingame",
    }]
    out = m.adverse_selection(ledger_rows, grade_dir)
    assert out["mlb"]["n"] == 1
    # away frame: fill_p = 1-0.5=0.5, post_p = 1-0.80=0.20 -> adverse_move = -0.30
    assert out["mlb"]["mean"] < 0


def test_adverse_selection_skips_non_paper_ingame_and_missing_grade(tmp_path):
    grade_dir = tmp_path / "grade"
    ledger_rows = [
        {"ts": "2026-07-19T00:00:00+00:00", "sport": "mlb", "game_id": "GX", "side": "home",
         "taken_decimal": 2.0, "channel": "paper"},  # wrong channel
        {"ts": "2026-07-19T00:00:00+00:00", "sport": "mlb", "game_id": "MISSING", "side": "home",
         "taken_decimal": 2.0, "channel": "paper_ingame"},  # no grade file
    ]
    out = m.adverse_selection(ledger_rows, grade_dir)
    assert out == {}


def test_divergence_warning_fires_on_large_gap():
    rows = [
        {"model_prob": 0.2636, "taken_decimal": 1.0 / 0.035, "bet_id": "det_laa"},
        {"model_prob": 0.55, "taken_decimal": 2.0},  # small divergence, no warning
    ]
    out = m.divergence_and_warnings(rows)
    assert out["dist"]["n"] == 2
    assert len(out["warnings"]) == 1
    assert out["warnings"][0]["bet_id"] == "det_laa"
    assert out["warnings"][0]["divergence"] > 0.15


def test_declared_thresholds_insufficient_n():
    th = m.declared_thresholds(5, {"p90": 500.0}, {}, [], [])
    assert th["insufficient_n"] is True
    assert th["max_divergence"] == m.MAX_DIVERGENCE_CAP
    assert th["max_staleness_ms"] is None
    assert th["label"] == "declared_from_measurement_2026_07_19"


def test_declared_thresholds_sufficient_n_uses_p95_and_staleness():
    flagged = [0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.12, 0.14, 0.30, 0.40]
    th = m.declared_thresholds(20, {"p90": 250.0}, {}, flagged, [])
    assert th["insufficient_n"] is False
    assert th["max_divergence"] <= m.MAX_DIVERGENCE_CAP
    assert th["max_staleness_ms"] == 250.0


def test_compute_end_to_end_and_write_report(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    grade_dir = tmp_path / "grade"
    _write_jsonl(grade_dir / "mlb" / "G1.jsonl", [
        {"ts": "2026-07-19T00:00:00+00:00", "market_prob": 0.60},
        {"ts": "2026-07-19T00:10:00+00:00", "market_prob": 0.55},
    ])
    _write_jsonl(ledger_path, [{
        "ts": "2026-07-19T00:00:00+00:00", "sport": "mlb", "game_id": "G1", "side": "home",
        "taken_decimal": 2.0, "model_prob": 0.9, "channel": "paper_ingame",
        "placement_latency_ms": 50.0, "exec_gate": {"spread_bp": 5.0},
        "bet_id": "b1",
    }])
    result = m.compute(ledger=ledger_path, grade_dir=grade_dir)
    assert result["n_bets"] == 1
    assert result["edge_claimed"] is False
    assert result["units"] if "units" in result else True  # units not asserted, honest_note is
    assert "honest_note" in result
    assert result["declared_thresholds"]["insufficient_n"] is True  # n_bets=1 < 10

    out_path = tmp_path / "out" / "exec_calibration.json"
    written = m.write_report(out_path=out_path, ledger=ledger_path, grade_dir=grade_dir)
    assert out_path.is_file()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["n_bets"] == written["n_bets"] == 1


def test_compute_missing_ledger_never_raises(tmp_path):
    result = m.compute(ledger=tmp_path / "nope.jsonl", grade_dir=tmp_path / "nope_dir")
    assert result["n_bets"] == 0
    assert result["edge_claimed"] is False
    assert result["declared_thresholds"]["insufficient_n"] is True
