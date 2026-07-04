"""Per-file tests for tail_hypothesis_ledger_2024plus (the Lane-4 sibling
module that builds the polymarket_2024plus_{nba,mlb} corpus rows). Uses the
same tiny fake read_json/absent_row helpers a caller would pass in -- never
touches real data/, never imports the parent ledger module's globals.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_tail_hypothesis_ledger_2024plus.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.ingame import tail_hypothesis_ledger_2024plus as mod

HYPOTHESES = [
    {"id": "H1_longshot_underpriced", "band": "[0.10,0.20)", "direction": "VENUE_UNDERPRICES"},
    {"id": "H2_midfav_overpriced", "band": "[0.65,0.80)", "direction": "VENUE_OVERPRICES"},
]


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _absent_row(hyp_id, corpus, provenance, sport, path):
    return {
        "hypothesis": hyp_id, "corpus": corpus, "provenance": provenance,
        "sport": sport, "n_games": None, "status": "ABSENT",
        "verdict": None, "key_numbers": {}, "caveats": ["file not found: %s" % path],
    }


def _doc(h1_verdict="CALIBRATED"):
    return {
        "bands": {
            "[0.10,0.20)": {"pooled": {"n_games": 226, "mean_market": 0.1547,
                                        "realized_rate": 0.1338, "venue_gap": -0.0209,
                                        "venue_gap_ci95": [-0.0946, 0.0781],
                                        "venue_verdict": h1_verdict}},
            "[0.65,0.80)": {"pooled": {"n_games": 230, "mean_market": 0.7198,
                                        "realized_rate": 0.6769, "venue_gap": -0.0429,
                                        "venue_gap_ci95": [-0.1561, 0.0648],
                                        "venue_verdict": "CALIBRATED"}},
        },
        "note": "independent multi-season historical validation",
    }


def _write(path: Path, doc: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_present_file_yields_two_rows_labeled_by_sport(tmp_path):
    _write(tmp_path / "data" / "venue_history" / "polymarket" / "nba_2024plus_tail_validation.json", _doc())
    rows = mod.rows_polymarket_2024plus("nba", repo_root=tmp_path, hypotheses=HYPOTHESES,
                                         read_json=_read_json, absent_row=_absent_row)
    assert len(rows) == 2
    assert all(r["corpus"] == "polymarket_2024plus_nba" for r in rows)
    assert all(r["sport"] == "nba" for r in rows)
    assert all(r["status"] == "PRESENT" for r in rows)
    h1 = next(r for r in rows if r["hypothesis"] == "H1_longshot_underpriced")
    assert h1["n_games"] == 226
    assert h1["verdict"] == "CALIBRATED"
    assert h1["key_numbers"]["venue_gap"] == -0.0209


def test_missing_file_yields_absent_rows(tmp_path):
    rows = mod.rows_polymarket_2024plus("mlb", repo_root=tmp_path, hypotheses=HYPOTHESES,
                                         read_json=_read_json, absent_row=_absent_row)
    assert len(rows) == 2
    assert all(r["status"] == "ABSENT" for r in rows)
    assert all(r["corpus"] == "polymarket_2024plus_mlb" for r in rows)


def test_missing_band_within_present_doc_yields_absent_row(tmp_path):
    doc = _doc()
    del doc["bands"]["[0.10,0.20)"]
    _write(tmp_path / "data" / "venue_history" / "polymarket" / "nba_2024plus_tail_validation.json", doc)
    rows = mod.rows_polymarket_2024plus("nba", repo_root=tmp_path, hypotheses=HYPOTHESES,
                                         read_json=_read_json, absent_row=_absent_row)
    h1 = next(r for r in rows if r["hypothesis"] == "H1_longshot_underpriced")
    assert h1["status"] == "ABSENT"
    h2 = next(r for r in rows if r["hypothesis"] == "H2_midfav_overpriced")
    assert h2["status"] == "PRESENT"


def test_h1_all_calibrated_true_when_every_historical_corpus_calibrated():
    rows = [
        {"hypothesis": "H1_longshot_underpriced", "status": "PRESENT",
         "corpus": "polymarket_2023", "verdict": "VENUE_UNDERPRICES"},  # thin pocket, excluded
        {"hypothesis": "H1_longshot_underpriced", "status": "PRESENT",
         "corpus": "kalshi_historical", "verdict": "CALIBRATED"},
        {"hypothesis": "H1_longshot_underpriced", "status": "PRESENT",
         "corpus": "polymarket_2024plus_nba", "verdict": "CALIBRATED"},
        {"hypothesis": "H1_longshot_underpriced", "status": "PRESENT",
         "corpus": "polymarket_2024plus_mlb", "verdict": "CALIBRATED"},
    ]
    assert mod.h1_all_calibrated_outside_thin_pm2023(rows) is True


def test_h1_all_calibrated_false_when_one_corpus_not_calibrated():
    rows = [
        {"hypothesis": "H1_longshot_underpriced", "status": "PRESENT",
         "corpus": "kalshi_historical", "verdict": "VENUE_UNDERPRICES"},
        {"hypothesis": "H1_longshot_underpriced", "status": "PRESENT",
         "corpus": "polymarket_2024plus_nba", "verdict": "CALIBRATED"},
    ]
    assert mod.h1_all_calibrated_outside_thin_pm2023(rows) is False


def test_h1_all_calibrated_false_when_nothing_to_check():
    """No PRESENT historical-validation H1 rows at all -- must not silently
    report True (that would fabricate a synthesis update from zero evidence)."""
    rows = [
        {"hypothesis": "H1_longshot_underpriced", "status": "ABSENT",
         "corpus": "kalshi_historical", "verdict": None},
    ]
    assert mod.h1_all_calibrated_outside_thin_pm2023(rows) is False


def test_h1_check_ignores_h2_rows_and_forward_gate_rows():
    rows = [
        {"hypothesis": "H2_midfav_overpriced", "status": "PRESENT",
         "corpus": "kalshi_historical", "verdict": "VENUE_OVERPRICES"},  # H2, ignored
        {"hypothesis": "H1_longshot_underpriced", "status": "PRESENT",
         "corpus": "forward_gates", "verdict": "INSUFFICIENT_FORWARD"},  # not historical, ignored
        {"hypothesis": "H1_longshot_underpriced", "status": "PRESENT",
         "corpus": "kalshi_historical", "verdict": "CALIBRATED"},
    ]
    assert mod.h1_all_calibrated_outside_thin_pm2023(rows) is True
