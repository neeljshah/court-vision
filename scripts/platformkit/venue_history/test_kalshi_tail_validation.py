"""Tests for scripts.platformkit.venue_history.kalshi_tail_validation. Offline, no network."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.venue_history import kalshi_tail_validation as tv


def _write_market(out_dir: Path, ticker: str, result: str, close_time: str,
                   in_window: bool, probs: List[float]) -> None:
    doc = {
        "ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0],
        "series_ticker": "KXMLBGAME", "sport": "mlb",
        "close_time": close_time, "result": result,
        "in_discovery_window": in_window, "n_candles": len(probs),
        "candles": [{"ts": "2026-01-01T00:%02d:00Z" % i, "prob": p, "traded": True}
                    for i, p in enumerate(probs)],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ("%s.jsonl" % ticker)).write_text(json.dumps(doc) + "\n", encoding="utf-8")


def test_provenance_label_present(tmp_path: Path) -> None:
    doc = tv.run_validation(corpus_dir=tmp_path, sport="mlb")
    assert doc["provenance"] == "kalshi_historical_validation"
    assert doc["edge_claimed"] is False


def test_result_yes_no_gives_correct_outcome(tmp_path: Path) -> None:
    """result='yes' -> outcome=1 for every candle in that market's file."""
    _write_market(tmp_path, "KXMLBGAME-26MAY01-AAA", "yes", "2026-05-01T00:00:00Z",
                  in_window=False, probs=[0.55] * 10)
    _write_market(tmp_path, "KXMLBGAME-26MAY02-BBB", "no", "2026-05-02T00:00:00Z",
                  in_window=False, probs=[0.55] * 10)
    for i in range(6):  # pad to MIN_GAMES_BAND for a real CI verdict
        _write_market(tmp_path, "KXMLBGAME-26MAY0%d-P%d" % (3 + i, i),
                      "yes" if i % 2 == 0 else "no", "2026-05-0%dT00:00:00Z" % (3 + i),
                      in_window=False, probs=[0.55] * 10)
    doc = tv.run_validation(corpus_dir=tmp_path, sport="mlb")
    band = doc["pooled_all"]["bands"]["[0.50,0.65)"]
    assert band["n_markets"] == 8
    # 4 yes (incl AAA) / 4 no across 8 markets -> realized rate 0.5
    assert abs(band["realized_rate"] - 0.5) < 1e-6


def test_unresolved_market_never_invents_outcome(tmp_path: Path) -> None:
    """A market with no yes/no result is skipped, never given a fabricated outcome."""
    _write_market(tmp_path, "KXMLBGAME-26MAY01-VOID", "", "2026-05-01T00:00:00Z",
                  in_window=False, probs=[0.5, 0.6])
    doc = tv.run_validation(corpus_dir=tmp_path, sport="mlb")
    assert doc["n_markets_unresolved"] == 1
    assert doc["pooled_all"]["bands"] == {}


def test_discovery_window_exclusion_splits_pooled_vs_independent(tmp_path: Path) -> None:
    """A ticker inside the discovery window appears in pooled_all but NOT in
    excluded_discovery_window -- the two verdicts must never silently merge."""
    for i in range(9):
        _write_market(tmp_path, "KXMLBGAME-26JUN2%d-IN%d" % (i, i), "yes",
                      "2026-06-2%dT00:00:00Z" % i, in_window=True, probs=[0.3] * 5)
    for i in range(9):
        _write_market(tmp_path, "KXMLBGAME-26MAY1%d-OUT%d" % (i, i), "no",
                      "2026-05-1%dT00:00:00Z" % i, in_window=False, probs=[0.3] * 5)
    doc = tv.run_validation(corpus_dir=tmp_path, sport="mlb")
    assert doc["n_markets_in_discovery_window"] == 9
    assert doc["n_markets_excluded_independent"] == 9
    pooled_band = doc["pooled_all"]["bands"]["[0.20,0.35)"]
    excl_band = doc["excluded_discovery_window"]["bands"]["[0.20,0.35)"]
    assert pooled_band["n_markets"] == 18   # both subsets
    assert excl_band["n_markets"] == 9      # only the out-of-window subset
    assert abs(excl_band["realized_rate"] - 0.0) < 1e-6  # all 'no' in the excluded set


def test_insufficient_data_below_min_games(tmp_path: Path) -> None:
    _write_market(tmp_path, "KXMLBGAME-26MAY01-ONE", "yes", "2026-05-01T00:00:00Z",
                  in_window=False, probs=[0.4])
    doc = tv.run_validation(corpus_dir=tmp_path, sport="mlb")
    band = doc["pooled_all"]["bands"]["[0.35,0.50)"]
    assert band["venue_verdict"] == "INSUFFICIENT_DATA"
    assert band["venue_gap_ci95"] is None


def test_write_verdict_roundtrip(tmp_path: Path) -> None:
    doc = tv.run_validation(corpus_dir=tmp_path, sport="mlb")
    out_path = tmp_path / "verdict.json"
    p = tv.write_verdict(doc, out_path=out_path)
    assert p.is_file()
    reloaded = json.loads(p.read_text(encoding="utf-8"))
    assert reloaded["component"] == "kalshi_tail_validation"


def test_empty_corpus_dir_no_crash(tmp_path: Path) -> None:
    doc = tv.run_validation(corpus_dir=tmp_path / "does_not_exist", sport="mlb")
    assert doc["n_markets_scanned"] == 0
    assert doc["pooled_all"]["bands"] == {}
