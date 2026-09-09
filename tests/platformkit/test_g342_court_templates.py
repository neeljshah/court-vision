"""Focused checks for G342's rule-value templates and conservative selector (fix 1b)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.court_templates.template_select import _distance, select_template
from scripts.platformkit.court_templates.templates import load_template, render, segments

# Every numeric field of every template, checked against the cited rule (fix 1b correction:
# wnba corner_sideline_offset 4.0 -> 3.0 = 36 in per WNBA Rule 1; ncaa corner_sideline_offset
# derived from the cited 21 ft 7.375 in basket-to-corner distance -- see ncaa.json's
# corner_sideline_offset_note for the formula).
_EXPECTED_FIELDS = {
    "nba": {"native_unit": "ft", "length": 94.0, "width": 50.0, "center_circle_radius": 6.0, "lane_width": 16.0,
            "lane_depth": 19.0, "free_throw_circle_radius": 6.0, "three_arc_radius": 23.75,
            "corner_sideline_offset": 3.0, "restricted_radius": 4.0, "basket_offset": 4.0, "basket_center_ft": 5.25, "line_thickness": 0.1666666667},
    "wnba": {"native_unit": "ft", "length": 94.0, "width": 50.0, "center_circle_radius": 6.0, "lane_width": 16.0,
             "lane_depth": 19.0, "free_throw_circle_radius": 6.0, "three_arc_radius": 22.1458333333,
             "corner_sideline_offset": 3.0, "restricted_radius": 4.0, "basket_offset": 4.0, "basket_center_ft": 5.25, "line_thickness": 0.1666666667},
    "fiba": {"native_unit": "m", "length": 28.0, "width": 15.0, "center_circle_radius": 1.8, "lane_width": 4.9,
             "lane_depth": 5.8, "free_throw_circle_radius": 1.8, "three_arc_radius": 6.75,
             "corner_sideline_offset": 0.9, "restricted_radius": 1.30, "basket_offset": 1.2, "basket_center_ft": 5.167322835, "line_thickness": 0.05},
    "ncaa": {"native_unit": "ft", "length": 94.0, "width": 50.0, "center_circle_radius": 6.0, "lane_width": 12.0,
             "lane_depth": 19.0, "free_throw_circle_radius": 6.0, "three_arc_radius": 22.1458333333,
             "corner_sideline_offset": 3.385416667, "restricted_radius": 4.0, "basket_offset": 4.0, "basket_center_ft": 5.25, "line_thickness": 0.1666666667},
}


def test_cited_native_rule_values_and_render() -> None:
    H = np.array(((10.0, 0, 0), (0, 10.0, 0), (0, 0, 1)), dtype=np.float32)
    for league, expected in _EXPECTED_FIELDS.items():
        template = load_template(league)
        for field, value in expected.items():
            assert template[field] == value, f"{league}.{field}: {template[field]!r} != cited {value!r}"
        assert template["source_url"].startswith("https://") and template["accessed_date"] == "2026-09-08"
        assert render(template, H, (1280, 720)).any()
        assert {item["semantic_id"] for item in segments(template)} >= {"SIDELINE", "BASELINE", "CENTRE", "LANE_L", "LANE_R", "FT_CIRCLE", "ARC_3", "CORNER_3", "RA", "CIRCLE"}


def test_fiba_source_url_and_rule_value_are_official() -> None:
    fiba = load_template("fiba")
    assert fiba["source_title"] == "FIBA Official Basketball Rules 2024, Rule 2.5.7"
    assert fiba["source_url"].endswith("official-rules-2024-v10a.pdf")
    assert fiba["source_url_status"].startswith("VERIFIED")


def test_distance_is_symmetric() -> None:
    """template_select._distance must combine both directed distances (verifier: probe d(a,b)=50, d(b,a)=0)."""
    a = np.array([[0.0, 0.0]], dtype=np.float32)
    b = np.array([[0.0, 0.0], [50.0, 0.0]], dtype=np.float32)
    assert _distance(a, b) == _distance(b, a)
    rng = np.random.default_rng(0)
    x, y = rng.uniform(-100, 100, (7, 2)).astype(np.float32), rng.uniform(-100, 100, (5, 2)).astype(np.float32)
    assert _distance(x, y) == _distance(y, x)


def test_selector_prefers_true_template_and_rejects_quadrilateral() -> None:
    templates = {name: load_template(name) for name in ("nba", "wnba", "fiba", "ncaa")}
    H = np.array(((8.0, 0, 100), (0, 8.0, 100), (0, 0, 1)), dtype=np.float32)
    observed = [{"semantic_id": x["semantic_id"], "family": x["family"], "points": x["points"] @ H[:2, :2].T + H[:2, 2]} for x in segments(templates["nba"])]
    frames = [{"shot_id": f"shot-{index // 3}", "segments": observed} for index in range(6)]
    result = select_template(frames, templates, {name: [H] * 6 for name in templates})
    assert result["winner"] == "nba" and result["bootstrap_wins"] == 100
    with pytest.raises(AssertionError, match="quadrilateral"):
        select_template([{ "shot_id": f"q{n // 3}", "segments": [x for x in observed if x["semantic_id"] in {"SIDELINE", "BASELINE"}]} for n in range(6)], templates, {name: [H] * 6 for name in templates})


def test_runner_decision_path_uses_select_template_gate(monkeypatch) -> None:
    """The confusion-matrix decision must call the sealed select_template gate, not a bypass (B10/Q1/Q3 fix)."""
    import scripts.platformkit.court_templates.g342_synthetic_run as runner

    calls: list[list[dict]] = []
    real_select = runner.select_template

    def spy(frames, templates, homographies, **kwargs):
        calls.append(frames)
        return real_select(frames, templates, homographies, **kwargs)

    def fast_refit(rng, template, observed, n=1):  # skip the 50-candidate search: this test checks wiring, not accuracy
        return runner._sample_H(rng, template["feet"]["length"], template["feet"]["width"])

    monkeypatch.setattr(runner, "select_template", spy)
    monkeypatch.setattr(runner, "_best_refit", fast_refit)

    confusion, separation, archive, observed_archive, decisions = runner.run(n=10)
    assert calls, "select_template (the sealed gate) was never called by the decision path"
    validation_ids = [item["semantic_id"] for index, item in enumerate(segments(load_template("nba"))) if index % 2]
    for frames in calls:
        assert len(frames) >= 5
        assert len({f["shot_id"] for f in frames}) >= 2
        assert [item["semantic_id"] for item in frames[0]["segments"]] == validation_ids
    assert len(archive) == 4 * 10 * 2 * 4  # true_templates x frames x arms x scored_templates
    assert observed_archive and decisions


def test_prereg_seal_reads_file_and_normalizes_crlf() -> None:
    path = Path("docs/evidence/tracking/g342_court_templates_2026-09-08.prereg.md")
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    above, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert hashlib.sha256(above.encode()).hexdigest() == seal.strip()


def test_fix1b_prereg_seal_reads_file_and_normalizes_crlf() -> None:
    path = Path("docs/evidence/tracking/g342_prereg_fix1b_2026-09-08.md")
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    above, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert hashlib.sha256(above.encode()).hexdigest() == seal.strip()


def test_fix1c_prereg_seal_reads_file_and_normalizes_crlf() -> None:
    path = Path("docs/evidence/tracking/g342_prereg_fix1c_2026-09-08.md")
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    above, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert hashlib.sha256(above.encode()).hexdigest() == seal.strip()
