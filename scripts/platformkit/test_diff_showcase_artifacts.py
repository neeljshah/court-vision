"""Per-file test for scripts/platformkit/diff_showcase_artifacts.py.

Synthetic artifacts only -- no read of webapp/ or out_segmented/. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/test_diff_showcase_artifacts.py -q
"""
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.diff_showcase_artifacts import (  # noqa: E402
    ARTIFACTS, build_report, diff_artifact, dig, late_cell, main, numeric_leaves,
    render_markdown)


def test_numeric_leaves_walks_dicts_and_lists_and_skips_bools():
    leaves = numeric_leaves({"a": 1, "b": {"c": 2.5}, "d": [{"e": 3}], "f": True,
                             "g": "x", "h": None})
    assert leaves == {"/a": 1.0, "/b/c": 2.5, "/d/0/e": 3.0}


def test_diff_separates_count_moves_from_value_moves():
    before = {"sports": {"mlb": {"n_rows": 78986, "brier": 0.237684}}}
    after = {"sports": {"mlb": {"n_rows": 27351, "brier": 0.201}}}
    d = diff_artifact("x", before, after)
    assert d["n_count_moves"] == 1 and d["n_moved"] == 1
    assert d["count_changes"][0]["path"] == "/sports/mlb/n_rows"
    assert d["count_changes"][0]["delta"] == -51635
    move = d["largest_changes"][0]
    assert move["path"] == "/sports/mlb/brier" and move["delta"] == -0.036684


def test_identical_artifacts_report_no_moves():
    doc = {"sports": {"mlb": {"n": 5, "brier": 0.2}}}
    d = diff_artifact("x", doc, json.loads(json.dumps(doc)))
    assert d["n_moved"] == 0 and d["n_count_moves"] == 0


def test_dig_returns_none_for_a_missing_or_non_numeric_path():
    doc = {"sports": {"mlb": {"brier": 0.2, "label": "model", "flag": True}}}
    assert dig(doc, ("sports", "mlb", "brier")) == 0.2
    assert dig(doc, ("sports", "mlb", "label")) is None
    assert dig(doc, ("sports", "mlb", "flag")) is None
    assert dig(doc, ("sports", "nba", "brier")) is None
    assert dig(None, ("sports",)) is None


def test_late_cell_matches_by_value_not_list_position():
    doc = {"sports": {"mlb": {"buckets": [
        {"time_bucket": "early(inn1-3)", "prob_bucket": ".8-1", "source": "model",
         "n": 10, "mean_p": 0.9, "mean_y": 0.8, "calibration_error": 0.1},
        {"time_bucket": "late(inn7+)", "prob_bucket": ".8-1", "source": "model",
         "n": 99, "mean_p": 0.91, "mean_y": 0.87, "calibration_error": 0.04},
    ]}}}
    cell = late_cell(doc, "mlb", "late(inn7+)", ".8-1", "model")
    assert cell["n"] == 99 and cell["calibration_error"] == 0.04
    assert late_cell(doc, "mlb", "late(inn7+)", ".8-1", "market")["n"] is None
    assert late_cell({}, "mlb", "late(inn7+)", ".8-1", "model")["n"] is None


def _write(d, name, doc):
    (d / (name + ".json")).write_text(json.dumps(doc), encoding="utf-8")


def test_build_report_records_a_missing_side_instead_of_raising(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    before.mkdir()
    after.mkdir()
    _write(before, "murphy_decomposition", {"sports": {"mlb": {"model_prob": {"brier": 0.2}}}})
    report = build_report(before, after)
    assert len(report["artifacts"]) == len(ARTIFACTS)
    murphy = [a for a in report["artifacts"] if a["artifact"] == "murphy_decomposition"][0]
    assert murphy["missing"] == {"before": False, "after": True}
    assert all(h["after"] is None for h in report["headlines"])


def test_end_to_end_writes_ascii_markdown_and_a_json_sibling(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    before.mkdir()
    after.mkdir()
    for d, rows, brier in ((before, 78986, 0.237684), (after, 27351, 0.201)):
        _write(d, "brier_skill_scores", {"sports": {"mlb": {"grains": {"all": {
            "n": rows, "brier_model": brier, "brier_market": 0.206653,
            "brier_clim": 0.248, "base_rate": 0.4563}}}}})
        _write(d, "state_conditioned_calibration", {"sports": {"mlb": {"buckets": [
            {"time_bucket": "late(inn7+)", "prob_bucket": ".8-1", "source": "model",
             "n": rows, "mean_p": 0.9, "mean_y": 0.8, "calibration_error": 0.1}]}}})
    out_md = tmp_path / "diff.md"
    assert main(["--before-dir", str(before), "--after-dir", str(after),
                 "--out-md", str(out_md)]) == 0
    text = out_md.read_text(encoding="ascii")
    assert "Headline figures" in text and "MLB Brier -- model" in text
    assert "0.237684" in text and "0.201000" in text
    # calibration vocabulary: no dollar/return framing, and the disclaimer is present
    for banned in ("ROI", "wager", "$", "edge_claimed=true"):
        assert banned.lower() not in text.lower(), banned
    assert "profit statement" in text and "DIFFERENT POPULATIONS" in text
    report = json.loads(out_md.with_suffix(".json").read_text(encoding="utf-8"))
    assert report["as_of"] == "2026-09-16"
    cell = report["late_inning_high_confidence_cell"]["cells"][0]
    assert cell["before"]["n"] == 78986 and cell["after"]["n"] == 27351
    assert render_markdown(report).isascii()


def test_missing_after_dir_reports_no_data(tmp_path):
    assert main(["--after-dir", str(tmp_path / "nope")]) == 2
