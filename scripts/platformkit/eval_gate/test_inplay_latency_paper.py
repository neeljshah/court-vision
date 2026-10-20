"""Per-file tests for inplay_latency_paper (3-night fixture, idempotence, word screen)."""
import json
import re
from pathlib import Path

from scripts.platformkit.eval_gate import inplay_latency_paper as ilp

REPO = Path(__file__).resolve().parents[3]


def _ledger(night, p50, p90, p99, n, games):
    rows = [{"sport": "mlb", "game_key": f"{night}-{i}",
             "book_moved_first": {"num": num, "den": den}} for i, (num, den) in enumerate(games)]
    pooled = [{"sport": "mlb", "feed": "statsapi_rest", "games": len(games), "underpowered_games": 0,
               "flagged_games": 0, "book_moved_first": {},
               "receipt_minus_event": {"n": n, "p50": p50, "p90": p90, "p99": p99}},
              {"sport": "nba", "feed": "espn_scoreboard", "games": 2, "underpowered_games": 2,
               "flagged_games": 0, "book_moved_first": {},
               "receipt_minus_event": {"n": 0, "p50": None, "p90": None, "p99": None,
                                       "reason": "NO_EVENTS"}}]
    return {"range": {"first": night, "last": night}, "offset_journal": None,
            "pooled": pooled, "rows": rows}


def _fixture(tmp_path: Path) -> Path:
    lat = tmp_path / "docs/evidence/forward/latency"
    lat.mkdir(parents=True)
    nights = [("2026-10-01", 17.0, 24.0, 30.0, 100, [(5, 10)]),
              ("2026-10-02", 20.0, 28.0, 40.0, 200, [(3, 10), (7, 10)]),
              ("2026-10-04", 18.0, 25.0, 33.5, 150, [(5, 10)])]
    for night, *rest in nights:
        (lat / f"{night}_{night}_latency_ledger.json").write_text(json.dumps(_ledger(night, *rest)))
    m2 = tmp_path / "docs/evidence/forward/model2/m2"
    m2.mkdir(parents=True)
    cells = [{"cls": "live", "segment": "all", "age": "fresh", "sport": "mlb", "n_ticks": 30},
             {"cls": "live", "segment": "all", "age": "stale", "sport": "mlb", "n_ticks": 10},
             {"cls": "live", "segment": "early", "age": "stale", "sport": "mlb", "n_ticks": 999}]
    (m2 / "2026-10-01.json").write_text(json.dumps({"date": "2026-10-01", "cells": cells}))
    papers = tmp_path / "docs/papers"
    papers.mkdir(parents=True)
    (papers / "INPLAY_LATENCY_2026.md").write_text(
        "intro\n<!-- BEGIN GENERATED results -->\nold\n<!-- END GENERATED results -->\nmid\n"
        "<!-- BEGIN GENERATED appendix -->\n<!-- END GENERATED appendix -->\ntail\n")
    return tmp_path


def test_three_night_percentiles_gaps_and_staleness(tmp_path):
    root = _fixture(tmp_path)
    side, results, _ = ilp.build(root, min_nights=3)
    mlb = side["per_sport"]["mlb"]
    assert mlb["verdict"] == "POOLED" and mlb["events_n"] == 450
    assert mlb["p50"] == {"min": 17.0, "median": 18.0, "max": 20.0}
    assert mlb["p99"] == {"min": 30.0, "median": 33.5, "max": 40.0}
    assert mlb["book_moved_first"]["share"] == 0.5 and mlb["book_moved_first"]["games"] == 4
    assert side["per_sport"]["nba"]["verdict"] == "INSUFFICIENT"
    assert side["gap_nights"] == ["2026-10-03"]
    assert side["staleness_15s"]["mlb"] == {"fresh": 30, "stale": 10, "nights": 1, "stale_share": 0.25}
    # default floor of 10 nights refuses to pool a 3-night sport
    assert ilp.build(root)[0]["per_sport"]["mlb"]["verdict"] == "INSUFFICIENT"


def test_regeneration_is_idempotent_and_local(tmp_path):
    root = _fixture(tmp_path)
    assert ilp.main(["--repo-root", str(root)]) == 0
    paper = root / ilp.PAPER
    first = paper.read_text()
    side1 = (root / ilp.SIDECAR).read_text()
    assert first.startswith("intro\n") and "\nmid\n" in first and first.endswith("tail\n")
    assert "old" not in first and "| 2026-10-02 | mlb |" in first
    assert ilp.main(["--repo-root", str(root), "--check"]) == 0
    assert ilp.main(["--repo-root", str(root)]) == 0
    assert paper.read_text() == first and (root / ilp.SIDECAR).read_text() == side1


def test_committed_paper_word_screen():
    text = (REPO / ilp.PAPER).read_text(encoding="utf-8")
    text.encode("ascii")
    banned = r"\$|\bedge\b|\bROI\b|\bprofit|\bdollar|\bP&L\b|\bPnL\b"
    assert not re.search(banned, text, re.I)
    for figure in ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57"):
        assert figure not in text
