"""diff_timing_artifacts must read every headline off the published pair and never
by list index.

Run: python -m pytest tests/platformkit/test_diff_timing_artifacts.py -q
"""
import json

from scripts.platformkit import diff_timing_artifacts as dta


def _write(dirpath, name, doc):
    (dirpath / (name + ".json")).write_text(json.dumps(doc), encoding="utf-8")


def test_threshold_and_result_rows_are_selected_by_value(tmp_path):
    """Reordering the lists must not change a single reported figure."""
    forward = {"sports": {"mlb": {"n_games_usable": 174, "thresholds": [
        {"threshold": 2, "decided_frac_of_games": 0.7471, "decided_clock_median": 5.0},
        {"threshold": 5, "decided_frac_of_games": 0.3161, "decided_clock_median": 6.0}]}}}
    reversed_doc = {"sports": {"mlb": {"n_games_usable": 174, "thresholds": list(
        reversed(forward["sports"]["mlb"]["thresholds"]))}}}
    for doc in (forward, reversed_doc):
        assert dta._threshold(doc, "mlb", 5)["decided_clock_median"] == 6.0
        assert dta._threshold(doc, "mlb", 2)["decided_frac_of_games"] == 0.7471
    assert dta._threshold(forward, "mlb", 4) == {}

    lcf = {"results": [{"sport": "soccer_intl", "live_clock_fraction": 0.5994},
                       {"sport": "mlb", "live_clock_fraction": 0.7368}]}
    assert dta._lcf(lcf, "mlb")["live_clock_fraction"] == 0.7368
    assert dta._lcf(lcf, "tennis") == {}


def test_ticks_sums_checkpoints_and_tolerates_a_missing_sport():
    doc = {"checkpoints": {"mlb": {"1": {"n": 3589}, "2": {"n": 2803}}}}
    assert dta._ticks(doc, "mlb") == 6392.0
    assert dta._ticks(doc, "soccer_intl") is None
    assert dta._ticks({}, "mlb") is None


def test_report_flags_a_missing_side_instead_of_crashing(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    _write(before, "blowout_dynamics", {"sports": {"mlb": {"n_games_usable": 178}}})
    _write(after, "blowout_dynamics", {"sports": {"mlb": {"n_games_usable": 174}}})
    report = dta.build_report(before, after)
    by_name = {row["artifact"]: row for row in report["artifacts"]}
    assert by_name["blowout_dynamics"]["n_count_moves"] == 0  # n_games_usable is not a count key
    assert by_name["comeback_atlas"]["missing"] == {"before": True, "after": True}
    headline = next(h for h in report["headlines"] if h["label"] == "MLB games usable")
    assert (headline["before"], headline["after"], headline["delta"]) == (178.0, 174.0, -4.0)
    assert next(h for h in report["headlines"] if h["label"] == "MLB MFP mean")["delta"] is None
    assert "Live-Clock Fraction" in dta.render_markdown(report)
