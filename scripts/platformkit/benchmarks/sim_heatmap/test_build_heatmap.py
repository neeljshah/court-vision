"""Per-file: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/benchmarks/sim_heatmap/test_build_heatmap.py -q

Fast: drives the read-cached path against the real ops JSON already on disk
(no re-fit, matches this repo's heavy-IO-is-CLI-only convention)."""
from scripts.platformkit.benchmarks.sim_heatmap.build_heatmap import (
    _worst, collect_nba, collect_mlb, collect_tennis, collect_soccer, run,
)


def test_worst_picks_max_pit_dev_ignoring_none():
    rows = [{"pit_dev_baseline": 0.05}, {"pit_dev_baseline": 0.20}, {"pit_dev_baseline": None}]
    assert _worst(rows)["pit_dev_baseline"] == 0.20


def test_worst_empty_is_none():
    assert _worst([]) is None


def test_nba_named_regression_anchor_matches_known_p4m2():
    d = collect_nba()
    ra = d["regression_anchors"]["P4|m2"]
    assert ra["pit_dev_v2"] < ra["pit_dev_v3"]  # KNOWN regression: .1292 -> .1403


def test_mlb_inn7_m2_regression_anchor_matches_known():
    d = collect_mlb()
    ra = d["regression_anchors"]["inn7|m2"]
    assert ra["pit_dev_v1"] < ra["pit_dev_v2_bullpen_seam"]  # KNOWN: .0737 -> .1061
    assert ra["regressed_under_v2"] is True


def test_tennis_and_soccer_are_honest_coverage_gaps_not_fake_buckets():
    t = collect_tennis()
    s = collect_soccer()
    assert "coverage_gap" in t and t["coverage_gap"]
    assert "coverage_gap" in s and s["coverage_gap"]
    assert t["buckets"][0]["bucket"].startswith("whole_match")


def test_run_writes_one_json_per_sport_and_a_report(tmp_path, monkeypatch):
    import scripts.platformkit.benchmarks.sim_heatmap.build_heatmap as m
    out_dir = tmp_path / "ops"
    report = tmp_path / "report.md"
    monkeypatch.setattr(m, "OPS", out_dir)
    monkeypatch.setattr(m, "REPORT", report)
    docs = m.run(sports=["nba", "mlb"])
    assert set(docs) == {"nba", "mlb"}
    assert (out_dir / "sim_heatmap_nba.json").exists()
    assert (out_dir / "sim_heatmap_mlb.json").exists()
    assert report.exists()
