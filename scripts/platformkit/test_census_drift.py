"""scripts/platformkit/test_census_drift.py -- per-file tests for census_drift.

Exercises the four verdict paths (OK / DRIFT / MISSING / unverifiable) plus
the comma-brace per-key expansion, against a synthetic census dict + tmp
parquet/jsonl fixtures (no real census.json touched).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_census_drift.py -q
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from scripts.platformkit.census_drift import check_entry, run_check


def _write_parquet(path: str, n_rows: int) -> None:
    pd.DataFrame({"x": range(n_rows)}).to_parquet(path)


def _write_jsonl(path: str, n_lines: int) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i in range(n_lines):
            f.write(json.dumps({"i": i}) + "\n")


def _status(sport, name, source):
    return [r["status"] for r in check_entry(sport, name, source)]


def test_ok_within_tolerance(tmp_path):
    p = tmp_path / "boxscores.parquet"
    _write_parquet(str(p), 4697)
    source = {"path": str(p), "rows": 4697}
    results = list(check_entry("wnba", "player_boxscores", source))
    assert results == [{"entry": "wnba.player_boxscores", "status": "ok", "claimed": 4697, "actual": 4697}]


def test_drift_mismatch(tmp_path):
    p = tmp_path / "claims.jsonl"
    _write_jsonl(str(p), 40)
    source = {"path": str(p), "rows": 60}  # 33% off, well outside 5% tolerance
    (result,) = check_entry("cross_sport_market", "claim_weighting_ledger", source)
    assert result["status"] == "drift"
    assert result["claimed"] == 60 and result["actual"] == 40


def test_missing_path(tmp_path):
    source = {"path": str(tmp_path / "does_not_exist.parquet"), "rows": 100}
    (result,) = check_entry("mlb", "ghost_source", source)
    assert result["status"] == "missing"
    assert result["claimed"] == 100


def test_unverifiable_ambiguous_rows(tmp_path):
    p = tmp_path / "odds.parquet"
    _write_parquet(str(p), 10)
    source = {"path": str(p), "rows": "1.3k-4.8k"}  # a range, not a concrete count
    (result,) = check_entry("nba", "games_odds_linescores", source)
    assert result["status"] == "unverifiable"


def test_unverifiable_missing_fields():
    assert _status("nba", "no_path", {"rows": 5}) == ["unverifiable"]
    assert _status("nba", "no_rows", {"path": "some/path.parquet"}) == ["unverifiable"]


def test_directory_file_count_matches_claim(tmp_path):
    # 4 small jsonl day-files, each with several lines: census claims "4 depth-days"
    # (a FILE count) -- must not be judged only against the summed LINE count.
    d = tmp_path / "depth_history"
    d.mkdir()
    for i in range(4):
        _write_jsonl(str(d / f"day{i}.jsonl"), 20)
    (result,) = check_entry("mlb", "depth_history", {"path": str(d), "rows": "4 depth-days"})
    assert result["status"] == "ok"
    assert result["actual"] == 4


def test_drift_prefers_content_over_file_count(tmp_path):
    # reproduces the kalshi_trades false collapse: a growing corpus (2 date-files,
    # 40k lines summed) is numerically CLOSER to the stale claim by file-count (2)
    # than by content (40000+) -- must report the true content, not "collapsed to 2".
    d = tmp_path / "kalshi_trades"
    d.mkdir()
    _write_jsonl(str(d / "2026-07-09.jsonl"), 15000)
    _write_jsonl(str(d / "2026-07-10.jsonl"), 25000)
    (result,) = check_entry("cross_sport_market", "kalshi_trades", {"path": str(d / "*.jsonl"), "rows": 24567})
    assert result["status"] == "drift"
    assert result["actual"] == 40000  # content, not the file count (2)


def test_directory_file_claim_still_prefers_files(tmp_path):
    # sanity check the other side of the precedence rule: an explicit file-unit
    # claim ("N games"/"N depth-days") still prefers the file count, unaffected.
    d = tmp_path / "depth_history"
    d.mkdir()
    for i in range(4):
        _write_jsonl(str(d / f"day{i}.jsonl"), 500)
    (result,) = check_entry("mlb", "depth_history", {"path": str(d), "rows": "4 depth-days"})
    assert result["status"] == "ok" and result["actual"] == 4


def test_comma_brace_per_key(tmp_path):
    # one key lands OK (number found adjacent to its own token), the other
    # is MISSING outright (2024 file never landed -- the savant_hitcoords case)
    (tmp_path / "savant_2023.parquet").write_bytes(b"")
    _write_parquet(str(tmp_path / "savant_2023.parquet"), 27625)
    template = str(tmp_path / "savant_{2023,2024}.parquet")
    source = {"path": template, "rows": "2023: 27625 rows on disk; 2024: IN PROGRESS"}
    results = list(check_entry("mlb", "savant_hitcoords", source))
    by_entry = {r["entry"]: r for r in results}
    assert by_entry["mlb.savant_hitcoords[2023]"]["status"] == "ok"
    assert by_entry["mlb.savant_hitcoords[2024]"]["status"] == "missing"


def test_run_check_writes_summary(tmp_path):
    ok_parquet = tmp_path / "ok.parquet"
    _write_parquet(str(ok_parquet), 10)
    census = {
        "sports": {
            "nba": {
                "sources": {
                    "clean": {"path": str(ok_parquet), "rows": 10},
                    "ghost": {"path": str(tmp_path / "gone.parquet"), "rows": 5},
                }
            }
        }
    }
    census_path = tmp_path / "census.json"
    out_path = tmp_path / "drift.json"
    census_path.write_text(json.dumps(census), encoding="utf-8")

    out = run_check(str(census_path), str(out_path))

    assert out["n_ok"] == 1
    assert out["n_missing"] == 1
    assert os.path.exists(out_path)
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["n_ok"] == 1 and written["n_missing"] == 1


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
