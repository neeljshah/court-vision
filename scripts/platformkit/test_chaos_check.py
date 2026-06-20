"""Per-file test for scripts.platformkit.chaos_check (RB-E-1).

Proves the failure matrix lands every cell in an HONEST degraded state under each
injected failure, and -- critically -- that the deliberately green-on-missing
NEGATIVE CONTROL is CAUGHT (the check has teeth). A green-on-missing surface MUST
fail the chaos check.
"""
from __future__ import annotations

from scripts.platformkit import chaos_check as cc


# --------------------------------------------------------------------------- #
# The positive matrix passes: every honest surface is honest under every failure.
# --------------------------------------------------------------------------- #
def test_positive_matrix_all_cells_honest():
    rep = cc.run_matrix()
    assert rep["passed"] is True, rep["failures"]
    # Every surface PROVEN.
    assert all(v == "PROVEN" for v in rep["robustness_manifest"].values())
    # Every cell is honest and carries no $ field.
    for cell in rep["cells"]:
        assert cell["honest"] is True, cell
        assert "$" not in str(cell)


def test_every_mode_exercised_per_surface():
    rep = cc.run_matrix()
    n_surfaces = len(cc.HONEST_SURFACES)
    # 5 modes per surface.
    assert len(rep["cells"]) == n_surfaces * 5
    modes = {c["mode"] for c in rep["cells"]}
    assert modes == {cc.EMPTY_MODE, cc.STALE_MODE, cc.PARTIAL_MODE,
                     cc.CORRUPT_MODE, cc.TIMEOUT_MODE}


# --------------------------------------------------------------------------- #
# NEGATIVE CONTROL -- the teeth. The green-on-missing stub MUST fail the check.
# --------------------------------------------------------------------------- #
def test_negative_control_is_caught():
    rep = cc.run_matrix(include_negative_control=True)
    # The whole matrix must FAIL because of the green-on-missing stub.
    assert rep["passed"] is False
    # The negative-control surface is explicitly marked FAILED.
    assert rep["robustness_manifest"]["green_on_missing_NEGATIVE_CONTROL"] == "FAILED"
    # And the honest surfaces are still PROVEN (the failure is isolated to the stub).
    assert rep["robustness_manifest"]["feed_freshness"] == "PROVEN"
    assert rep["robustness_manifest"]["daemon_readiness"] == "PROVEN"
    # Every failure recorded belongs to the negative control surface.
    assert all(f["surface"] == "green_on_missing_NEGATIVE_CONTROL"
               for f in rep["failures"])
    # The stub returned green under genuine failure modes -> that is the bug caught.
    assert any(f["status"] == "ok" and f["mode"] != "" for f in rep["failures"])


def test_green_on_missing_stub_returns_green():
    # Sanity: the stub really does fabricate green (so the catch above is meaningful).
    for mode in (cc.EMPTY_MODE, cc.STALE_MODE, cc.TIMEOUT_MODE):
        assert cc.green_on_missing_stub(mode) == cc.OK


# --------------------------------------------------------------------------- #
# Per-surface honesty under each failure mode.
# --------------------------------------------------------------------------- #
def test_feed_freshness_never_green_under_failure():
    for mode in (cc.STALE_MODE, cc.EMPTY_MODE, cc.PARTIAL_MODE, cc.CORRUPT_MODE,
                 cc.TIMEOUT_MODE):
        status = cc.feed_freshness_surface(mode)
        assert status != "fresh", (mode, status)
        assert status in cc._HONEST_DEGRADED, (mode, status)


def test_composite_partial_degrades_to_down():
    # One sub-feed up + one down -> the composite is DOWN (monotone-DOWN).
    assert cc.composite_surface(cc.PARTIAL_MODE) == cc.DOWN
    # Empty set -> unavailable, never ok.
    assert cc.composite_surface(cc.EMPTY_MODE) == cc.UNAVAILABLE
    # All ok (control) -> ok.
    assert cc.rollup([cc.OK, cc.OK]) == cc.OK
    assert cc.rollup([cc.OK, cc.STALE]) == cc.DEGRADED
    assert cc.rollup([]) == cc.UNAVAILABLE


def test_daemon_readiness_never_ready_under_failure():
    # Stale heartbeat -> degraded.
    assert cc.daemon_readiness_surface(cc.STALE_MODE) == cc.DEGRADED
    # Absent heartbeat -> degraded.
    assert cc.daemon_readiness_surface(cc.EMPTY_MODE) == cc.DEGRADED
    # Open breaker (hung, reaper tripped) -> down.
    assert cc.daemon_readiness_surface(cc.TIMEOUT_MODE) == cc.DOWN
    # Dead proc -> down.
    assert cc.daemon_readiness_surface(cc.PARTIAL_MODE) == cc.DOWN


def test_run_matrix_never_raises_on_crashing_surface():
    def boom(mode):  # a surface that throws under failure is itself a FAILURE
        raise RuntimeError("kaboom")

    rep = cc.run_matrix({"boom": boom})
    assert rep["passed"] is False
    assert rep["robustness_manifest"]["boom"] == "FAILED"
    assert any("CRASH" in c["status"] for c in rep["cells"])
