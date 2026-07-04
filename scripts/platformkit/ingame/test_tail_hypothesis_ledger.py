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


def _pm_2024plus_doc(n_games_h1=226, verdict_h1="CALIBRATED"):
    return {
        "note": "independent multi-season historical validation of 2024plus corpus",
        "bands": {
            "[0.10,0.20)": {"pooled": {"n_games": n_games_h1, "mean_market": 0.1547,
                                        "realized_rate": 0.1338, "venue_gap": -0.0209,
                                        "venue_gap_ci95": [-0.0946, 0.0781],
                                        "venue_verdict": verdict_h1}},
            "[0.65,0.80)": {"pooled": {"n_games": 230, "mean_market": 0.7198,
                                        "realized_rate": 0.6769, "venue_gap": -0.0429,
                                        "venue_gap_ci95": [-0.1561, 0.0648],
                                        "venue_verdict": "CALIBRATED"}},
        },
    }


def _build_full_repo(tmp_path, with_2024plus=False):
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
    if with_2024plus:
        _write(tmp_path / "data" / "venue_history" / "polymarket" / "nba_2024plus_tail_validation.json",
               _pm_2024plus_doc())
        _write(tmp_path / "data" / "venue_history" / "polymarket" / "mlb_2024plus_tail_validation.json",
               _pm_2024plus_doc())
    return tmp_path


def test_all_present_composes_expected_row_count(tmp_path, monkeypatch):
    _build_full_repo(tmp_path, with_2024plus=True)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    doc = led.build_ledger()
    # 2 hyps x (1 discovery corpus + 11 forward-gate sports + 1 pm + 1 kalshi
    # + 1 pm_2024plus_nba + 1 pm_2024plus_mlb) = 32
    assert doc["n_rows"] == 32
    assert doc["n_absent"] == 0
    assert doc["n_present"] == 32


def test_missing_files_yield_absent_rows_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)  # empty tree -- nothing exists
    doc = led.build_ledger()
    assert doc["n_rows"] == 32
    assert doc["n_present"] == 0
    assert doc["n_absent"] == 32
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
    _build_full_repo(tmp_path, with_2024plus=True)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    out = tmp_path / "out" / "tail_hypothesis_ledger.json"
    written = led.write_ledger(out_path=out)
    assert written == out
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["n_rows"] == 32


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


# --- LANE 4: polymarket_2024plus_{nba,mlb} corpus rows -----------------------

def test_2024plus_rows_present_and_labeled(tmp_path, monkeypatch):
    _write(tmp_path / "data" / "venue_history" / "polymarket" / "nba_2024plus_tail_validation.json",
           _pm_2024plus_doc())
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    d = led.build_ledger()
    rows = [r for r in d["rows"] if r["corpus"] == "polymarket_2024plus_nba"]
    assert len(rows) == 2
    assert all(r["status"] == "PRESENT" for r in rows)
    assert all(r["sport"] == "nba" for r in rows)
    h1 = next(r for r in rows if r["hypothesis"] == "H1_longshot_underpriced")
    assert h1["verdict"] == "CALIBRATED"
    assert h1["n_games"] == 226
    mlb_rows = [r for r in d["rows"] if r["corpus"] == "polymarket_2024plus_mlb"]
    assert all(r["status"] == "ABSENT" for r in mlb_rows)  # file not written in this test


def test_2024plus_absent_file_yields_absent_row_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)  # nothing written
    d = led.build_ledger()
    rows = [r for r in d["rows"]
            if r["corpus"] in ("polymarket_2024plus_nba", "polymarket_2024plus_mlb")]
    assert len(rows) == 4
    assert all(r["status"] == "ABSENT" for r in rows)
    assert all(r["verdict"] is None for r in rows)


def test_synthesis_gets_h1_update_when_all_historical_corpora_calibrated(tmp_path, monkeypatch):
    """The pre-registered conditional: when polymarket_2023 H2 (n=138, already
    CALIBRATED in the fixture) plus kalshi_historical (both bands CALIBRATED)
    plus both new 2024plus corpora (CALIBRATED) all read CALIBRATED for H1
    outside the thin PM-2023 pocket, the ledger appends the Fable-authored
    H1 synthesis line verbatim, additive to (not replacing) the H2 sentence."""
    _build_full_repo(tmp_path, with_2024plus=True)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    d = led.build_ledger()
    assert d["synthesis"] == led._SYNTHESIS + " " + led._SYNTHESIS_H1_UPDATE
    assert "H1 evidence after 6 corpora" in d["synthesis"]
    assert "only the PM-MLB-2023 pocket (n=14) is significant" in d["synthesis"]
    assert "H2 midfav overpriced" in d["synthesis"]  # original H2 line preserved


def test_synthesis_no_h1_update_when_a_historical_corpus_not_calibrated(tmp_path, monkeypatch):
    """If any independent historical corpus (outside the thin PM-2023 pocket)
    reads something other than CALIBRATED for H1, the additive line must NOT
    be appended -- the conditional is honest, not decorative."""
    _build_full_repo(tmp_path, with_2024plus=True)
    # flip the kalshi historical H1 excluded-window verdict away from CALIBRATED
    bad_kalshi = _kalshi_hist_doc()
    bad_kalshi["excluded_discovery_window"]["bands"]["[0.10,0.20)"]["venue_verdict"] = "VENUE_UNDERPRICES"
    _write(tmp_path / "data" / "venue_history" / "kalshi" / "mlb_tail_validation.json", bad_kalshi)
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    d = led.build_ledger()
    assert d["synthesis"] == led._SYNTHESIS
    assert "H1 evidence after 6 corpora" not in d["synthesis"]


def test_corpora_list_includes_2024plus(tmp_path, monkeypatch):
    monkeypatch.setattr(led, "_REPO_ROOT", tmp_path)
    d = led.build_ledger()
    assert "polymarket_2024plus_nba" in d["corpora"]
    assert "polymarket_2024plus_mlb" in d["corpora"]
    assert len(d["corpora"]) == 6
