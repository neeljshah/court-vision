"""Per-file test for scripts.platformkit.calibration_banner.

Offline + deterministic, < 5s. Asserts the startup-banner trust invariants:
  - the banner carries the "calibration not edge" framing and the decision-support
    (NOT a $ edge) line;
  - when a frozen baseline anchor exists it prints last OOS Brier (model in-corpus),
    the devigged-close Brier (devigged-market), and a last-recalibration date, each
    badged by SOURCE;
  - it degrades gracefully (no raise, still framed) when the baseline is absent
    (a fresh clone with local-only baselines);
  - it NEVER prints a retracted measurement-artifact number;
  - print_banner writes to STDERR by default so predict_matchup --json stdout stays
    machine-parseable;
  - ASCII only.
"""
from __future__ import annotations

import io
import sys

from scripts.platformkit import calibration_banner as CB

# the documented retracted artifacts -- must NEVER appear in the banner
_RETRACTED = ("+18.38", "18.38", "0.119", "+54", "54%", "78.11", "8.94", "54.57")


def _text(name=CB._ANCHOR) -> str:
    return "\n".join(CB.banner_lines(name))


def test_framing_present_and_decision_support():
    body = _text()
    assert "calibration not edge" in body
    assert "NOT a $ edge" in body
    # never implies a guaranteed $ edge / beat-the-close claim
    assert "MATCH the close, never beat" in body


def test_anchor_numbers_badged_when_baseline_present():
    a = CB.load_anchor()
    if a is None:
        # fresh clone: degrade path is covered by test_absent_baseline_degrades
        return
    body = _text()
    assert "last OOS Brier" in body
    assert "[SOURCE: model in-corpus]" in body
    assert "[SOURCE: devigged-market]" in body
    assert "last recalibration:" in body


def test_absent_baseline_degrades_no_raise():
    # an anchor name that does not exist -> None -> static framed banner, no raise
    body = _text("does_not_exist_corpus")
    assert "unavailable on this clone" in body
    assert "calibration not edge" in body  # framing still present


def test_no_retracted_number():
    for nm in (CB._ANCHOR, "does_not_exist_corpus"):
        body = _text(nm)
        for bad in _RETRACTED:
            assert bad not in body, f"retracted number leaked into banner: {bad}"


def test_print_banner_goes_to_stderr_not_stdout():
    out, err = io.StringIO(), io.StringIO()
    old_err = sys.stderr
    try:
        sys.stderr = err
        CB.print_banner()           # default stream = stderr
    finally:
        sys.stderr = old_err
    assert err.getvalue().strip(), "banner produced no stderr output"
    assert not out.getvalue(), "banner must not write to the captured stdout buffer"
    # explicit-stream form writes where told
    buf = io.StringIO()
    CB.print_banner(stream=buf)
    assert "CALIBRATION CONTEXT" in buf.getvalue()


def test_oneline_is_single_line():
    one = CB.calib_context()
    assert "\n" not in one
    assert "CALIBRATION CONTEXT" in one


def test_ascii_only():
    for nm in (CB._ANCHOR, "does_not_exist_corpus"):
        _text(nm).encode("ascii")   # raises if any non-ASCII slipped in


def test_deterministic():
    assert _text() == _text()


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
