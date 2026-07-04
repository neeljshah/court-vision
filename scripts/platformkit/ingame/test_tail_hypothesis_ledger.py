"""Per-file tests for tail_hypothesis_ledger (composer over fixture artifact
sets -- present AND absent files). Never touches real data/ -- monkeypatches
_REPO_ROOT to a tmp_path tree built per test.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_tail_hypothesis_ledger.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import tail_hypothesis_ledger as led


def _write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _mlb_scan_doc():
    return {
        "bands": {
            "[0.10,0.20)": {"n_games": 42, "n_ticks": 2225, "mean_market": 0.1486,
                             "realized_rate": 0.2746, "venue_gap": 0.126,
                             "venue_gap_ci95": [-0.07, 0.32], "venue_verdict": "CALIBRATED"},
            "[0.65,0.80)": {"n_games": 63, "n_ticks": 2971, "mean_market": 0.7223,
                             "realized_rate": 0.5439, "venue_gap": -0.1784,
                             "venue_gap_ci95": [-0.33, -0.017], "venue_verdict": "VENUE_OVERPRICES"},
        },
        "n_games_resolved": 95,
    }


def _mlb_gate_doc():
    return {
        "hypotheses": [
            {"id": "H1_longshot_underpriced",
             "discovery_band_reference_only": {"venue_verdict": "CALIBRATED"}},
            {"id": "H2_midfav_overpriced",
             "discovery_band_reference_only": {"venue_verdict": "CALIBRATED"}},
        ],
        "n_forward_games": 5,
        "pre_registered_at": "2026-07-03T00:00:00Z",
    }


def _forward_gate_doc(sport, verdict1="INSUFFICIENT_FORWARD", verdict2="INSUFFICIENT_FORWARD"):
    return {
        "sport": sport,
        "pre_registered_at": "2026-07-04T00:00:00Z",
        "n_forward_games": 3,
        "hypotheses": [
            {"id": "H1_longshot_underpriced", "forward_verdict": verdict1,
             "forward_band": {"n_games": 3, "mean_market": 0.15, "realized_rate": 0.76,
                               "venue_gap": 0.61, "delta_brier": -0.19, "n_ticks": 89}},
            {"id": "H2_midfav_overpriced", "forward_verdict": verdict2,
             "forward_band": {"n_games": 3, "mean_market": 0.70, "realized_rate": 1.0,
                               "venue_gap": 0.30, "delta_brier": 0.018, "n_ticks": 488}},
        ],
    }


def _pm_doc():
    return {
        "note": "independent multi-season historical validation",
        "bands": {
            "[0.10,0.20)": {"pooled": {"n_games": 14, "mean_market": 0.155,
                                        "realized_rate": 0.5228, "venue_gap": 0.3678,
                                        "venue_gap_ci95": [0.017, 0.7036],
                                        "venue_verdict": "VENUE_UNDERPRICES"}},
            "[0.65,0.80)": {"pooled": {"n_games": 138, "mean_market": 0.7153,
                                        "realized_rate": 0.6754, "venue_gap": -0.0399,
                                        "venue_gap_ci95": [-0.1816, 0.0693],
                                        "venue_verdict": "CALIBRATED"}},
        },
    }


def _kalshi_hist_doc():
    return {
        "note": "historical Kalshi candle corpus",
        "excluded_discovery_window": {
            "bands": {
                "[0.10,0.20)": {"n_markets": 455, "mean_venue_price": 0.144,
                                 "realized_rate": 0.1368, "venue_gap": -0.0072,
                                 "venue_verdict": "CALIBRATED"},
                "[0.65,0.80)": {"n_markets": 598, "mean_venue_price": 0.688,
                                 "realized_rate": 0.7481, "venue_gap": 0.0601,
                                 "venue_verdict": "CALIBRATED"},
            }
        },
    }


def _build_full_repo(tmp_path):
    ops = tmp_path / "data" / "frontend" / "ops"
    _write(ops / "ingame_tail_scan.json", _mlb_scan_doc())
    _write(tmp_path / "data" / "domains" / "mlb" / "ingame_tail_verdict.json", _mlb_gate_doc())
    for sport in led.FORWARD_GATE_SPORTS:
        if sport == "mlb":
            continue
        _write(tmp_path / "data" / "domains" / sport / "ingame_tail_verdict.json",
               _forward_gate_doc(sport))
    _write(tmp_path / "data" / "venue_history" / "polymarket" / "mlb_tail_validation.json", _pm_doc())
    _write(tmp_path / "data" / "venue_history" / "kalshi" / "mlb_tail_validation.json",
           _kalshi_hist_doc())
    return tmp_path


def test_all_present_composes_expected_row_count(tmp_path, monkeypatch):
    _build_full_repo(tmp_path)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    doc = led.build_ledger()
    # 2 hyps x (1 discovery corpus + 11 forward-gate sports + 1 pm + 1 kalshi) = 28
    assert doc["n_rows"] == 28
    assert doc["n_absent"] == 0
    assert doc["n_present"] == 28


def test_missing_files_yield_absent_rows_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)  # empty tree -- nothing exists
    doc = led.build_ledger()
    assert doc["n_rows"] == 28
    assert doc["n_present"] == 0
    assert doc["n_absent"] == 28
    assert all(r["status"] == "ABSENT" for r in doc["rows"])
    assert all(r["verdict"] is None for r in doc["rows"])


def test_partial_present_mix_of_absent_and_present(tmp_path, monkeypatch):
    # Only wire up the MLB discovery scan + one forward gate; everything else absent.
    ops = tmp_path / "data" / "frontend" / "ops"
    _write(ops / "ingame_tail_scan.json", _mlb_scan_doc())
    _write(tmp_path / "data" / "domains" / "mlb" / "ingame_tail_verdict.json", _mlb_gate_doc())
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    doc = led.build_ledger()
    kalshi_disc_rows = [r for r in doc["rows"] if r["corpus"] == "kalshi_discovery_2026"]
    assert all(r["status"] == "PRESENT" for r in kalshi_disc_rows)
    assert kalshi_disc_rows[0]["verdict"] == "CALIBRATED"
    pm_rows = [r for r in doc["rows"] if r["corpus"] == "polymarket_2023"]
    assert all(r["status"] == "ABSENT" for r in pm_rows)


def test_kalshi_historical_uses_excluded_discovery_window_not_pooled_all(tmp_path, monkeypatch):
    """Binding provenance rule: kalshi historical rows must read the honest
    independent subset (excluded_discovery_window), never pooled_all which
    overlaps the live discovery corpus."""
    doc_with_pooled_all = _kalshi_hist_doc()
    doc_with_pooled_all["pooled_all"] = {
        "bands": {"[0.10,0.20)": {"n_markets": 9999, "venue_verdict": "VENUE_OVERPRICES"}}
    }
    _write(tmp_path / "data" / "venue_history" / "kalshi" / "mlb_tail_validation.json",
           doc_with_pooled_all)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    d = led.build_ledger()
    row = next(r for r in d["rows"] if r["corpus"] == "kalshi_historical"
               and r["hypothesis"] == "H1_longshot_underpriced")
    assert row["n_games"] == 455  # from excluded_discovery_window, not 9999
    assert row["verdict"] == "CALIBRATED"


def test_synthesis_block_is_fixed_text(tmp_path, monkeypatch):
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    doc = led.build_ledger()
    assert doc["synthesis"] == led._SYNTHESIS
    assert "H2 midfav overpriced" in doc["synthesis"]
    assert "No edge claimed" in doc["synthesis"]


def test_edge_claimed_always_false(tmp_path, monkeypatch):
    _build_full_repo(tmp_path)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    assert led.build_ledger()["edge_claimed"] is False


def test_write_ledger_writes_valid_json(tmp_path, monkeypatch):
    _build_full_repo(tmp_path)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    out = tmp_path / "out" / "tail_hypothesis_ledger.json"
    written = led.write_ledger(out_path=out)
    assert written == out
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["n_rows"] == 28


def test_polymarket_reads_pooled_not_halves(tmp_path, monkeypatch):
    """Polymarket doc nests pooled + halves under each band; the ledger must
    read 'pooled' only, never a half."""
    doc = _pm_doc()
    doc["bands"]["[0.65,0.80)"]["halves"] = {
        "half_0": {"n_games": 68, "venue_verdict": "VENUE_UNDERPRICES"},
    }
    _write(tmp_path / "data" / "venue_history" / "polymarket" / "mlb_tail_validation.json", doc)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    d = led.build_ledger()
    row = next(r for r in d["rows"] if r["corpus"] == "polymarket_2023"
               and r["hypothesis"] == "H2_midfav_overpriced")
    assert row["n_games"] == 138
    assert row["verdict"] == "CALIBRATED"
