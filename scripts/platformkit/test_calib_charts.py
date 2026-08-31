"""Focused synthetic checks for calibration evidence visual rendering."""
import json

from scripts.platformkit.calib_charts import render


def _rows(observed_shift=0.0):
    return [{"n": 30 + index, "mean_predicted_prob": .1 + index * .2,
             "observed_win_freq": min(1.0, .1 + index * .2 + observed_shift),
             "ci_low": max(0.0, index * .2), "ci_high": min(1.0, .2 + index * .2)}
            for index in range(5)]


def test_render_creates_pngs_and_mp4_with_optional_reports(tmp_path):
    reports, output = tmp_path / "reports", tmp_path / "output"
    reports.mkdir()
    (reports / "wp_diagnostics_20260831.json").write_text(json.dumps({
        "reliability": _rows(), "max_loser_wp": {"per_game": [{"max_loser_wp": .3}, {"max_loser_wp": .9}],
        "quantiles": {"50": .6, "90": .84}}}), encoding="utf-8")
    (reports / "wp_oos_20260831.json").write_text(json.dumps({
        "before_reliability": _rows(.12), "after_reliability": _rows(.02)}), encoding="utf-8")
    paths = render(reports, output, "Synthetic fixture. Calibration is not an edge claim.")
    assert {path.name for path in paths} == {"reliability_diagram.png", "max_loser_wp_histogram.png", "oos_isotonic_overlay.png"}
    assert all(path.exists() and path.stat().st_size > 0 for path in paths)
    assert (output / "calibration_audit.mp4").exists()


def test_render_handles_absent_optional_reports(tmp_path):
    reports, output = tmp_path / "reports", tmp_path / "output"
    reports.mkdir()
    (reports / "wp_diagnostics_one.json").write_text(json.dumps({"reliability": _rows()}), encoding="utf-8")
    paths = render(reports, output)
    assert [path.name for path in paths] == ["reliability_diagram.png"]
    assert (output / "calibration_audit.mp4").exists()
