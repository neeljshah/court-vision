"""Per-file tests for greenlight_trust_honesty (E-SPEC/F-SPEC).

All artifact reads/writes are rooted at a pytest tmp_path fixture via the
`root=` override -- never touches real data/. See
docs/research/depth-program/GREENLIGHT_UNCAP_SPEC_2026-07-05.md TEST PLAN.
"""
from __future__ import annotations

import json
import os
import time

from scripts.platformkit.econ import greenlight_trust_honesty as _mod
from scripts.platformkit.econ.greenlight_trust_honesty import (
    channel_trust_status, cv_honesty_status)

_MIN_N = 500  # governance.policy.MIN_SETTLED_N (mirrored here for fixture only)
_MIN_COV = 90.0  # governance.policy.MIN_TRUE_CLOSE_FRAC * 100


def _ops(root):
    p = os.path.join(str(root), "data", "frontend", "ops")
    os.makedirs(p, exist_ok=True)
    return p


def _write(root, name, obj):
    with open(os.path.join(_ops(root), name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def _write_reject_ledger(root, n_lines=5):
    path = os.path.join(str(root), "data", "frontend", "reject_ledger.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for i in range(n_lines):
            fh.write(json.dumps({"ts": "2026-01-0%d" % (i + 1), "verdict": "REJECT"}) + "\n")


def _eq_cell(n=600, cov=95.0, ci=(0.1, 2.0)):
    return {
        "n_measurable": n, "true_close_coverage_pct": cov,
        "same_venue": {"same_venue": {"clv_ci95": list(ci)}},
    }


def _green_fixture(root, channel="paper_ingame", sport="mlb"):
    """Full all-GREEN fixture for channel_trust_status: fresh artifacts, strong
    numbers, GENUINE_VARIANCE reconciler, no adverse segments, in-game MATCH."""
    _write(root, "execution_quality.json",
           {"channel_cells": {"%s|%s" % (sport, channel): _eq_cell()}})
    _write(root, "clv_reconcile_%s.json" % channel,
           {"verdict": "GENUINE_VARIANCE -- ok", "z_wins": 0.5, "z_units": 0.3})
    _write(root, "ingame_segment_trust.json", {"adverse": [], "trusted": ["I1"]})
    _write(root, "ingame_segment_trust_multi.json",
           {"per_sport": {sport: {"adverse": [], "trusted": []}}})
    _write(root, "ingame_clv_verdict.json",
           {"sports": [{"sport": sport, "verdict": "MATCH", "n_markets": 40}]})
    _write_reject_ledger(root)
    rows = [{"sport": sport, "channel": channel}]
    return rows


def _honesty_fixture(root):
    """All-pass F-SPEC fixture (reject_ledger bootstrap; prereg w/ pinned
    fields + sha256 matching the compute_sha of the object). Also writes the
    three cited artifacts F-check-1/2 now read (execution_quality,
    clv_scoreboard, ingame_clv_verdict) so the fixture stays all-pass under
    the extended freshness gate + edge_claimed check."""
    from scripts.platformkit.l4.prereg_sha_stamp import compute_sha
    _write(root, "ingame_segment_trust.json", {"edge_claimed": False, "adverse": []})
    _write(root, "ingame_segment_trust_multi.json",
           {"edge_claimed": False, "measurement_only": True})
    _write(root, "execution_quality.json", {"cells": {}})
    _write(root, "clv_scoreboard.json", {"rows": []})
    _write(root, "ingame_clv_verdict.json",
           {"edge_claimed": False, "sports": [{"sport": "mlb", "verdict": "MATCH", "n_markets": 40}]})
    prereg = {
        "pre_registered_at": "2026-07-04T16:33:48Z",
        "floors": {"min_games": 30}, "planted_null": "mandatory",
        "fail_action": "SCOUTING_ONLY", "edge_claimed": False,
    }
    prereg["sha256"] = compute_sha(prereg)
    _write(root, "l4_gate_prereg.json", prereg)
    _write_reject_ledger(root)


# ---------------------------------------------------------------------------
# E-SPEC
# ---------------------------------------------------------------------------


def test_channel_trust_green_path(tmp_path):
    rows = _green_fixture(tmp_path)
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "GREEN", res["reasons"]


def test_amber_tier_never_green(tmp_path):
    rows = _green_fixture(tmp_path)
    # n in [60, 500) with everything else perfect -> AMBER, not GREEN (R-a lock).
    _write(tmp_path, "execution_quality.json",
           {"channel_cells": {"mlb|paper_ingame": _eq_cell(n=200, cov=95.0)}})
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "AMBER"

    # coverage in [60, 90) with everything else perfect -> AMBER too.
    _write(tmp_path, "execution_quality.json",
           {"channel_cells": {"mlb|paper_ingame": _eq_cell(n=600, cov=75.0)}})
    res2 = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res2["status"] == "AMBER"


def test_floors_come_from_governance_policy(tmp_path, monkeypatch):
    rows = _green_fixture(tmp_path)
    # n=600 clears the REAL floor (500) -> GREEN.
    res_before = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res_before["status"] == "GREEN"
    # Monkeypatch the floor to a sentinel ABOVE 600 -> now n=600 must fail the
    # (now higher) floor and cap at AMBER. Proves the floor is IMPORTED, not
    # a hardcoded literal in this module.
    monkeypatch.setattr(_mod._pol, "MIN_SETTLED_N", 10_000)
    res_after = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res_after["status"] == "AMBER"
    assert res_before["status"] != res_after["status"]


def test_sla_seconds_come_from_real_freshness_table(tmp_path, monkeypatch):
    # R-d: SLA seconds must be READ from the real freshness_sla.TABLE at check
    # time, never a literal in this module. Prove it by shrinking the real
    # execution_quality SLA to near-zero and confirming a fresh-but-not-
    # instant file now reads stale through _sla_table's remap.
    from scripts.platformkit.autonomy import freshness_sla as _sla
    orig = _sla.TABLE["execution_quality"]
    monkeypatch.setitem(_sla.TABLE, "execution_quality",
                         _sla.SlaEntry(orig.path, 0.001))
    rows = _green_fixture(tmp_path)
    time.sleep(0.02)
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("execution_quality" in r for r in res["reasons"])


def test_missing_artifact_is_red(tmp_path):
    rows = _green_fixture(tmp_path)
    for fn in ("execution_quality.json", "clv_reconcile_paper_ingame.json",
               "ingame_segment_trust.json", "ingame_clv_verdict.json"):
        path = os.path.join(_ops(tmp_path), fn)
        os.remove(path)
        res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
        assert res["status"] == "RED", "expected RED with %s missing, got %s (%s)" % (
            fn, res["status"], res["reasons"])
        # restore for the next iteration
        _green_fixture(tmp_path)


def test_stale_artifact_is_red(tmp_path):
    rows = _green_fixture(tmp_path)
    path = os.path.join(_ops(tmp_path), "execution_quality.json")
    # execution_quality SLA is 93600s (26h); backdate mtime well past that.
    old = time.time() - 200_000
    os.utime(path, (old, old))
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("stale" in r for r in res["reasons"])


def test_adverse_segment_forces_red(tmp_path):
    rows = _green_fixture(tmp_path)
    _write(tmp_path, "ingame_segment_trust.json", {"adverse": ["I3"], "trusted": []})
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "RED"
    assert "segment_adverse" in res["reasons"]


def test_not_applicable_caps_amber(tmp_path):
    rows = _green_fixture(tmp_path)
    _write(tmp_path, "clv_reconcile_paper_ingame.json",
           {"verdict": "INSUFFICIENT_DATA -- only 3 measurable bets",
            "z_wins": None, "z_units": None})
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "AMBER"
    assert any(r.startswith("reconcile_not_applicable") for r in res["reasons"])


def test_reconciler_suspect_close_forces_red(tmp_path):
    rows = _green_fixture(tmp_path)
    _write(tmp_path, "clv_reconcile_paper_ingame.json",
           {"verdict": "SUSPECT_CLOSE -- duplicate closes", "z_wins": 0.1, "z_units": 0.1})
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "RED"


def test_same_venue_clv_ci_adverse_is_red(tmp_path):
    rows = _green_fixture(tmp_path)
    _write(tmp_path, "execution_quality.json",
           {"channel_cells": {"mlb|paper_ingame": _eq_cell(ci=(-3.0, -0.5))}})
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "RED"
    assert "same_venue_clv_ci_adverse" in res["reasons"]


def test_ingame_verdict_behind_forces_red(tmp_path):
    rows = _green_fixture(tmp_path)
    _write(tmp_path, "ingame_clv_verdict.json",
           {"sports": [{"sport": "mlb", "verdict": "BEHIND", "n_markets": 40}]})
    res = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res["status"] == "RED"
    assert "ingame_clv_verdict_behind" in res["reasons"]


def test_no_sport_is_red(tmp_path):
    res = channel_trust_status("paper_ingame", [{"channel": "paper_ingame"}], root=str(tmp_path))
    assert res["status"] == "RED"
    assert res["reasons"] == ["no_sport"]


def test_non_ingame_channel_skips_ingame_verdict_check(tmp_path):
    # moneyline is not an in-game channel: even a missing/absent
    # ingame_clv_verdict.json must not affect its status.
    rows = _green_fixture(tmp_path, channel="moneyline")
    os.remove(os.path.join(_ops(tmp_path), "ingame_clv_verdict.json"))
    res = channel_trust_status("moneyline", rows, root=str(tmp_path))
    assert res["status"] == "GREEN", res["reasons"]


# ---------------------------------------------------------------------------
# F-SPEC
# ---------------------------------------------------------------------------


def test_honesty_all_pass_is_not_refuted(tmp_path):
    _honesty_fixture(tmp_path)
    res = cv_honesty_status({"note": "clean report"}, root=str(tmp_path))
    assert res["status"] == "NOT_REFUTED", res["failures"]


def test_honesty_retracted_number_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    poisoned = {"note": "in-play accuracy was +18.38% last week"}
    res = cv_honesty_status(poisoned, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("retracted_numbers_scan" in f for f in res["failures"])


def test_retracted_number_in_cited_ingame_clv_verdict_forces_red(tmp_path):
    # Reproduction (Opus re-review finding 1): a clean report but a retracted
    # number planted in a CITED ops artifact (not the report dict itself) must
    # still RED -- F-check-1 must scan every cited artifact, not just report.
    _honesty_fixture(tmp_path)
    _write(tmp_path, "ingame_clv_verdict.json",
           {"edge_claimed": False, "note": "in-play accuracy hit 78.11 last month",
            "sports": [{"sport": "mlb", "verdict": "MATCH", "n_markets": 40}]})
    res = cv_honesty_status({"note": "clean report"}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("retracted_numbers_scan" in f for f in res["failures"])


def test_retracted_number_in_cited_execution_quality_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    _write(tmp_path, "execution_quality.json", {"cells": {}, "note": "pregame ROI was +18.38%"})
    res = cv_honesty_status({"note": "clean report"}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("retracted_numbers_scan" in f for f in res["failures"])


def test_retracted_number_in_cited_clv_scoreboard_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    _write(tmp_path, "clv_scoreboard.json", {"rows": [], "note": "54.57 was the old figure"})
    res = cv_honesty_status({"note": "clean report"}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("retracted_numbers_scan" in f for f in res["failures"])
    assert any("retracted_numbers_scan" in f for f in res["failures"])


def test_reject_ledger_shrink_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    # First call bootstraps the watermark at n_lines=5.
    res0 = cv_honesty_status({}, root=str(tmp_path))
    assert res0["status"] == "NOT_REFUTED"
    # Shrink the ledger to 3 lines -> RED.
    _write_reject_ledger(tmp_path, n_lines=3)
    res1 = cv_honesty_status({}, root=str(tmp_path))
    assert res1["status"] == "RED"
    assert any("reject_ledger_monotonic" in f for f in res1["failures"])


def test_reject_ledger_rewrite_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    res0 = cv_honesty_status({}, root=str(tmp_path))
    assert res0["status"] == "NOT_REFUTED"
    # Same line count, DIFFERENT content -> prefix sha mismatch -> RED.
    ledger_path = os.path.join(str(tmp_path), "data", "frontend", "reject_ledger.jsonl")
    with open(ledger_path, "w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({"ts": "REWRITTEN", "verdict": "REJECT", "i": i}) + "\n")
    res1 = cv_honesty_status({}, root=str(tmp_path))
    assert res1["status"] == "RED"
    assert any("reject_ledger_monotonic" in f for f in res1["failures"])


def test_reject_ledger_bootstrap_on_first_run(tmp_path):
    _honesty_fixture(tmp_path)
    watermark = os.path.join(str(tmp_path), "data", "cache", "greenlight",
                              "reject_ledger_watermark.jsonl")
    assert not os.path.exists(watermark)
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "NOT_REFUTED"
    assert os.path.exists(watermark)


def test_sha_pending_is_amber(tmp_path):
    _honesty_fixture(tmp_path)
    prereg_path = os.path.join(_ops(tmp_path), "l4_gate_prereg.json")
    with open(prereg_path, "r", encoding="utf-8") as fh:
        prereg = json.load(fh)
    prereg.pop("sha256")
    with open(prereg_path, "w", encoding="utf-8") as fh:
        json.dump(prereg, fh)
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "AMBER"
    assert res["failures"] == []  # zero FAILs -- sha_pending is NOT_APPLICABLE, not a fail


def test_sha_mismatch_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    prereg_path = os.path.join(_ops(tmp_path), "l4_gate_prereg.json")
    with open(prereg_path, "r", encoding="utf-8") as fh:
        prereg = json.load(fh)
    prereg["sha256"] = "deadbeef" * 8
    with open(prereg_path, "w", encoding="utf-8") as fh:
        json.dump(prereg, fh)
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("sha_mismatch" in f for f in res["failures"])


def test_prereg_snapshot_mismatch_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    res0 = cv_honesty_status({}, root=str(tmp_path))
    assert res0["status"] == "NOT_REFUTED"  # first run snapshots
    # Now mutate a PINNED field post-hoc (goalpost move).
    prereg_path = os.path.join(_ops(tmp_path), "l4_gate_prereg.json")
    with open(prereg_path, "r", encoding="utf-8") as fh:
        prereg = json.load(fh)
    prereg["floors"] = {"min_games": 5}  # loosened after the fact
    from scripts.platformkit.l4.prereg_sha_stamp import compute_sha
    prereg["sha256"] = compute_sha(prereg)
    with open(prereg_path, "w", encoding="utf-8") as fh:
        json.dump(prereg, fh)
    res1 = cv_honesty_status({}, root=str(tmp_path))
    assert res1["status"] == "RED"
    assert any("snapshot_mismatch" in f for f in res1["failures"])


def test_edge_claimed_true_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    _write(tmp_path, "ingame_segment_trust.json", {"edge_claimed": True, "adverse": []})
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("edge_claimed_false" in f for f in res["failures"])


def test_ingame_clv_verdict_edge_claimed_true_forces_red(tmp_path):
    # Reproduction (Opus re-review finding 2): F-check-2 skipped
    # ingame_clv_verdict.json -- a cited verdict artifact -- entirely.
    _honesty_fixture(tmp_path)
    _write(tmp_path, "ingame_clv_verdict.json",
           {"edge_claimed": True, "sports": [{"sport": "mlb", "verdict": "MATCH", "n_markets": 40}]})
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("edge_claimed_false" in f for f in res["failures"])


def test_ingame_clv_verdict_missing_edge_claimed_field_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    _write(tmp_path, "ingame_clv_verdict.json",
           {"sports": [{"sport": "mlb", "verdict": "MATCH", "n_markets": 40}]})
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("edge_claimed_false" in f for f in res["failures"])


def test_flag_flipped_forces_red(tmp_path):
    _honesty_fixture(tmp_path)
    _write(tmp_path, "ingame_segment_trust_multi.json",
           {"edge_claimed": False, "measurement_only": True, "flag_flipped": True})
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("proposal_only_integrity" in f for f in res["failures"])


def test_stale_honesty_artifact_is_red(tmp_path):
    _honesty_fixture(tmp_path)
    path = os.path.join(_ops(tmp_path), "ingame_segment_trust.json")
    old = time.time() - 200_000  # past the 93600s (26h) SLA
    os.utime(path, (old, old))
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("freshness" in f for f in res["failures"])


def test_stale_execution_quality_forces_f_red(tmp_path):
    # Finding 1's freshness-gate extension: execution_quality/clv_scoreboard/
    # ingame_clv_verdict are now cited-artifact freshness keys too -- a stale
    # execution_quality.json must RED the F status per the spec RED clause.
    _honesty_fixture(tmp_path)
    path = os.path.join(_ops(tmp_path), "execution_quality.json")
    old = time.time() - 200_000  # past the 93600s (26h) SLA
    os.utime(path, (old, old))
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("freshness:execution_quality" in f for f in res["failures"])


def test_missing_execution_quality_forces_f_red(tmp_path):
    _honesty_fixture(tmp_path)
    os.remove(os.path.join(_ops(tmp_path), "execution_quality.json"))
    res = cv_honesty_status({}, root=str(tmp_path))
    assert res["status"] == "RED"
    assert any("freshness:execution_quality" in f for f in res["failures"])


# ---------------------------------------------------------------------------
# ANTI-FAKE (charter-mandated): status is DERIVED from reads, never a constant.
# ---------------------------------------------------------------------------


def test_hardcoded_green_is_impossible(tmp_path, monkeypatch):
    rows = [{"sport": "mlb", "channel": "paper_ingame"}]

    # (1) monkeypatch EVERY artifact reader to raise -> status RED, never GREEN.
    def _raise(_path):
        raise OSError("simulated artifact-reader failure")
    monkeypatch.setattr(_mod, "_read_json", _raise)
    res_e = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res_e["status"] == "RED"
    res_f = cv_honesty_status({}, root=str(tmp_path))
    assert res_f["status"] == "RED"
    monkeypatch.undo()

    # (2) monkeypatch every artifact reader to return empty -> also never GREEN.
    monkeypatch.setattr(_mod, "_read_json", lambda _path: None)
    res_e2 = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res_e2["status"] != "GREEN"
    res_f2 = cv_honesty_status({}, root=str(tmp_path))
    assert res_f2["status"] != "NOT_REFUTED"
    monkeypatch.undo()

    # (3) empty root, no monkeypatch at all: nothing exists -> RED either way.
    res_e3 = channel_trust_status("paper_ingame", rows, root=str(tmp_path))
    assert res_e3["status"] == "RED"
    res_f3 = cv_honesty_status({}, root=str(tmp_path))
    assert res_f3["status"] == "RED"

    # (4) build an all-GREEN/NOT_REFUTED fixture, then tamper EACH input in
    # turn; status must degrade away from GREEN/NOT_REFUTED every time --
    # proves status is DERIVED from reads, never a constant return.
    root = tmp_path / "tamper"
    root.mkdir()
    _green_fixture(root)
    assert channel_trust_status("paper_ingame", rows, root=str(root))["status"] == "GREEN"

    for fn, poison in (
        ("execution_quality.json", {"cells": {}}),
        ("clv_reconcile_paper_ingame.json", {"verdict": "SUSPECT_CLOSE -- bad", "z_wins": 9}),
        ("ingame_segment_trust.json", {"adverse": ["I1"], "trusted": []}),
        ("ingame_clv_verdict.json", {"sports": [{"sport": "mlb", "verdict": "BEHIND"}]}),
    ):
        _green_fixture(root)  # reset to baseline
        _write(root, fn, poison)
        degraded = channel_trust_status("paper_ingame", rows, root=str(root))
        assert degraded["status"] != "GREEN", "tampering %s did not degrade status" % fn

    _honesty_fixture(root)
    assert cv_honesty_status({}, root=str(root))["status"] == "NOT_REFUTED"
    ledger_path = os.path.join(str(root), "data", "frontend", "reject_ledger.jsonl")
    os.remove(ledger_path)
    assert cv_honesty_status({}, root=str(root))["status"] != "NOT_REFUTED"
