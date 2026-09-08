"""G316 attempt 2 -- synthetic-construct test for the sealed presence rule,
the region set, the reader and the denominator. One file, per-file run only:

    python -m pytest tests/platformkit/test_g316_scoreboard_clock_liveness.py -q -p no:cacheprovider
"""
import importlib.util
import json
import os
import cv2
import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MOD = os.path.join(ROOT, "scripts", "platformkit", "tracking",
                   "g316_scoreboard_clock_liveness.py")
_spec = importlib.util.spec_from_file_location("g316_liveness", MOD)
g316 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g316)


def _frame_with_bug(clock="5:14", w=1280, h=720):
    """Court-like frame carrying a bottom-centre bug: dark plate, white text."""
    rng = np.random.default_rng(316)
    fr = rng.integers(90, 170, size=(h, w, 3), dtype=np.uint8)
    x0, y0, x1, y1 = int(w * 0.32), int(h * 0.85), int(w * 0.68), int(h * 0.94)
    cv2.rectangle(fr, (x0, y0), (x1, y1), (30, 22, 18), -1)
    cv2.putText(fr, clock, (x0 + 30, y1 - 12), cv2.FONT_HERSHEY_SIMPLEX,
                1.4, (255, 255, 255), 3)
    cv2.putText(fr, "2ND", (x0 + 210, y1 - 12), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, (255, 255, 255), 2)
    return fr


def _frame_without_bug(w=1280, h=720):
    rng = np.random.default_rng(317)
    return rng.integers(90, 170, size=(h, w, 3), dtype=np.uint8)


def _stats(fr):
    bot = g316.crop(fr, g316.REGIONS["BOT"])
    return g316.white_row(bot), g316.edge_row(bot)


def test_presence_rule_fires_on_a_bug_and_not_on_a_bare_frame():
    wr, er = _stats(_frame_with_bug())
    assert g316.is_present(wr, er), (wr, er)
    wr0, er0 = _stats(_frame_without_bug())
    assert not g316.is_present(wr0, er0), (wr0, er0)


def test_sealed_thresholds_and_region_set_are_the_prereg_values():
    assert (g316.PRESENT_WHITE, g316.PRESENT_EDGE) == (0.04, 0.07)
    assert (g316.WHITE_MIN, g316.EDGE_MIN, g316.CONF_MIN) == (200, 40, 0.30)
    assert g316.REGIONS == {
        "TOP": (0.00, 1.00, 0.00, 0.16),
        "BOT": (0.00, 1.00, 0.78, 1.00),
        "BOTLEFT": (0.00, 0.55, 0.78, 1.00),
        "BOTRIGHT": (0.45, 1.00, 0.78, 1.00),
    }


def test_production_parser_reads_the_drawn_clock_from_the_region_text():
    _parse_scoreboard_text = g316.production_parser(ROOT)
    assert _parse_scoreboard_text("2ND 5:14")["game_clock_sec"] == 314.0
    # The declared non-match: a sub-minute broadcast render does not parse.
    assert _parse_scoreboard_text("4TH :06.6")["game_clock_sec"] == -1.0


def test_absent_frame_counts_in_the_denominator_and_not_in_the_numerator():
    recs = [
        {"clip": "c", "skin": "S", "j": 0, "scoreboard_present": True,
         "clock_seconds": 314.0},
        {"clip": "c", "skin": "S", "j": 1, "scoreboard_present": True,
         "clock_seconds": None},
        {"clip": "c", "skin": "S", "j": 2, "scoreboard_present": False,
         "clock_seconds": None},
    ]
    out = g316.summarise(recs, str(TMP))
    s = out["per_skin"]["S"]
    assert (s["sampled"], s["present"], s["rejected"], s["parsed"]) == (3, 2, 1, 1)
    assert s["parsed_clock_rate"] == 0.5 and out["pooled_parsed_clock_rate"] == 0.5
    assert out["bar"] == 0.90


def test_wilson_interval_brackets_the_point_estimate():
    lo, hi = g316.wilson(9, 10)
    assert lo < 0.9 < hi and g316.wilson(0, 0) == (None, None)


def test_record_schema_is_the_full_declared_column_set():
    assert g316.RECORD_KEYS[:6] == ("clip", "skin", "j", "t_sec", "png", "sha256")
    assert "scoreboard_present" in g316.RECORD_KEYS
    assert "parsed_clock" in g316.RECORD_KEYS and "reader" in g316.RECORD_KEYS


@pytest.fixture(autouse=True, scope="module")
def _tmp(tmp_path_factory):
    global TMP
    TMP = tmp_path_factory.mktemp("g316")
    yield
