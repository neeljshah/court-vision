"""tests.governance.test_provenance -- number + fill provenance honesty gates.

A REAL_MODEL number passes; a FILLED number shown as REAL (not flagged) is
flagged; tag() auto-flags FILLED/UNKNOWN; a percentile-filled feature lacking
FILLED provenance is caught by the fill gate. The checks are pure and never
raise. Run ONLY this file (a full pytest run freezes the box):

    python -m pytest tests/governance/test_provenance.py -q
"""
from __future__ import annotations

from governance import number_provenance as NP
from governance import fill_provenance as FP
from governance.policy import Provenance


# --------------------------------------------------------------------------- #
# number_provenance.tag                                                        #
# --------------------------------------------------------------------------- #
def test_tag_real_model_is_presentable_and_unflagged():
    cell = NP.tag(0.512, Provenance.REAL_MODEL)
    assert cell["provenance"] == "REAL_MODEL"
    assert cell["flagged"] is False
    assert cell["presentable"] is True


def test_tag_filled_is_auto_flagged():
    cell = NP.tag(0.5, Provenance.FILLED)
    assert cell["flagged"] is True
    assert cell["presentable"] is False


def test_tag_unknown_is_auto_flagged():
    cell = NP.tag(1.0, Provenance.UNKNOWN)
    assert cell["flagged"] is True


# --------------------------------------------------------------------------- #
# assert_provenance                                                           #
# --------------------------------------------------------------------------- #
def test_real_model_report_passes():
    report = {
        "win_prob": NP.tag(0.51, Provenance.REAL_MODEL),
        "close": NP.tag(0.49, Provenance.CAPTURED_MARKET),
        "ev": NP.tag(0.02, Provenance.DERIVED),
    }
    res = NP.assert_provenance(report)
    assert res["ok"] is True, res["violations"]


def test_filled_presented_as_real_is_flagged():
    # A FILLED number shown as real (no flag) must be caught.
    bad = {"q4_pace": {"value": 99.1, "provenance": "FILLED"}}
    res = NP.assert_provenance(bad)
    assert res["ok"] is False
    assert any(v["kind"] == "filled_presented_as_real"
               for v in res["violations"])


def test_filled_but_flagged_is_ok():
    ok = {"q4_pace": {"value": 99.1, "provenance": "FILLED", "flagged": True}}
    res = NP.assert_provenance(ok)
    assert res["ok"] is True, res["violations"]


def test_unknown_provenance_string_is_unsafe():
    bad = {"x": {"value": 1.0, "provenance": "MAGIC"}}
    res = NP.assert_provenance(bad)
    assert res["ok"] is False
    assert any(v["kind"] == "unknown_provenance" for v in res["violations"])


def test_assert_provenance_never_raises_on_weird_input():
    res = NP.assert_provenance({"a": [None, True, {3: "x"}]})
    assert isinstance(res["ok"], bool)


def test_is_presentable():
    assert NP.is_presentable(Provenance.REAL_MODEL)
    assert not NP.is_presentable(Provenance.FILLED)
    assert not NP.is_presentable(Provenance.UNKNOWN)


# --------------------------------------------------------------------------- #
# fill_provenance -- the percentile-fill-defeats-signals lesson.              #
# --------------------------------------------------------------------------- #
def test_percentile_filled_feature_not_flagged_blocks():
    # A 'live' per-quarter feature that was percentile-filled but presented as
    # observed (no FILLED provenance) must be caught.
    bad = {"scoreboard_period": {"value": 4, "fill_method": "percentile_fill"}}
    res = FP.assert_fills_flagged(bad)
    assert res["ok"] is False
    assert any(v["kind"] == "fill_not_flagged" for v in res["violations"])


def test_boolean_fill_marker_blocks():
    bad = {"feat": {"value": 1.0, "imputed": True}}
    res = FP.assert_fills_flagged(bad)
    assert res["ok"] is False


def test_fill_flagged_with_filled_provenance_is_ok():
    ok = {"feat": FP.flag_fill(1.0, method="percentile_fill")}
    res = FP.assert_fills_flagged(ok)
    assert res["ok"] is True, res["violations"]
    assert ok["feat"]["provenance"] == "FILLED"
    assert ok["feat"]["presentable"] is False


def test_observed_value_passes():
    ok = {"feat": {"value": 1.0, "provenance": "REAL_MODEL"}}
    res = FP.assert_fills_flagged(ok)
    assert res["ok"] is True, res["violations"]


def test_is_filled_cell_detection():
    assert FP.is_filled_cell({"value": 1, "provenance": "FILLED"})
    assert FP.is_filled_cell({"value": 1, "last_observed": True})
    assert FP.is_filled_cell({"value": 1, "source": "last_observed proxy"})
    assert not FP.is_filled_cell({"value": 1, "provenance": "REAL_MODEL"})
    assert not FP.is_filled_cell(42)


def test_fill_check_never_raises():
    res = FP.assert_fills_flagged({"a": [1, 2, {"b": None}], 7: "z"})
    assert isinstance(res["ok"], bool)
