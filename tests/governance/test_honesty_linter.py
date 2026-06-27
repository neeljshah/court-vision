"""tests.governance.test_honesty_linter -- the honesty linter blocks fabrications.

A clean report passes; a report containing a retracted number (18.38) with no
retraction marker BLOCKS; a $edge key BLOCKS; a banned claim token BLOCKS; a
banned number inside an explicit retraction context is ALLOWED. The linter is
pure and must never raise. Run ONLY this file (a full pytest run freezes the box):

    python -m pytest tests/governance/test_honesty_linter.py -q
"""
from __future__ import annotations

from governance import honesty_linter as L


# --------------------------------------------------------------------------- #
# Clean input passes.                                                          #
# --------------------------------------------------------------------------- #
def test_clean_report_passes():
    report = {
        "sport": "nba",
        "matchup": "NYK @ SAS",
        "win_prob": 0.5123,
        "brier": 0.214,
        "verdict": "matches the devigged close within noise",
        "provenance": "REAL_MODEL",
    }
    res = L.lint_obj(report)
    assert res["clean"] is True
    assert res["violations"] == []
    assert res["linter_version"] == L.LINTER_VERSION


# --------------------------------------------------------------------------- #
# A retracted number with no retraction marker BLOCKS.                         #
# --------------------------------------------------------------------------- #
def test_retracted_number_blocks():
    res = L.lint_obj({"headline": "pregame ROI was +18.38% this season"})
    assert res["clean"] is False
    kinds = {v["kind"] for v in res["violations"]}
    assert "banned_number" in kinds
    assert any("18.38" in v["detail"] for v in res["violations"])


def test_retracted_number_in_plain_text_blocks():
    res = L.lint_text("we hit 78.11 accuracy in play")
    assert res["clean"] is False
    assert any(v["kind"] == "banned_number" for v in res["violations"])


# --------------------------------------------------------------------------- #
# A $edge key BLOCKS (structural -- the product has no dollar-edge field).     #
# --------------------------------------------------------------------------- #
def test_dollar_edge_key_blocks():
    res = L.lint_obj({"$edge": 12.3, "win_prob": 0.51})
    assert res["clean"] is False
    assert any(v["kind"] == "banned_key" for v in res["violations"])


def test_roi_edge_key_blocks():
    res = L.lint_obj({"markets": [{"roi_edge": 4.0}]})
    assert res["clean"] is False
    assert any(v["kind"] == "banned_key" for v in res["violations"])


# --------------------------------------------------------------------------- #
# A banned claim TOKEN blocks even inside a retraction context.                #
# --------------------------------------------------------------------------- #
def test_banned_token_blocks_even_in_retraction():
    # Retraction framing present, but a "guaranteed profit" claim is never OK.
    res = L.lint_text("retracted note: this is a guaranteed profit lock")
    assert res["clean"] is False
    assert any(v["kind"] == "banned_token" for v in res["violations"])


# --------------------------------------------------------------------------- #
# A banned number inside an explicit retraction context is ALLOWED.           #
# --------------------------------------------------------------------------- #
def test_retracted_number_in_retraction_context_allowed():
    text = ("The +18.38% pregame ROI is a RETRACTED measurement artifact "
            "(see JOB_EVIDENCE_PACKET); never claim it as a live result.")
    res = L.lint_text(text)
    assert res["clean"] is True, res["violations"]


def test_retraction_context_does_not_whitelist_keys():
    # Even with retraction prose, a $edge KEY is structural and still blocks.
    obj = {"note": "retracted artifact do not claim", "$edge": 9.0}
    res = L.lint_obj(obj)
    assert res["clean"] is False
    assert any(v["kind"] == "banned_key" for v in res["violations"])


# --------------------------------------------------------------------------- #
# Embedded-in-longer-number does NOT fire (tolerant matcher).                  #
# --------------------------------------------------------------------------- #
def test_longer_number_does_not_fire():
    res = L.lint_text("the latency was 218.384 ms and ratio 0.1190001")
    assert res["clean"] is True, res["violations"]


# --------------------------------------------------------------------------- #
# Linter is pure and total: never raises, even on hostile input.              #
# --------------------------------------------------------------------------- #
def test_linter_never_raises_on_nested_and_weird_input():
    weird = {"a": [1, 2, {"b": (None, True, "guaranteed")}], 3: "x", None: "+54%"}
    res = L.lint_obj(weird)
    assert isinstance(res["clean"], bool)
    # "+54%" under a non-str key and "guaranteed" both surface.
    kinds = {v["kind"] for v in res["violations"]}
    assert "banned_token" in kinds
    assert "banned_number" in kinds


def test_assert_clean_raises_on_violation_and_passes_when_clean():
    L.assert_clean({"win_prob": 0.5})  # no raise
    raised = False
    try:
        L.assert_clean({"$edge": 1.0})
    except AssertionError:
        raised = True
    assert raised
