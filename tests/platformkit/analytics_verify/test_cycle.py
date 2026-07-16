"""Per-file test for scripts.platformkit.analytics_verify.cycle.

Monkeypatches each producer entrypoint so the test never touches real ledgers;
proves run_cycle() isolates a producer error, writes an atomic digest with the
signals block, and that scan_finder_candidates() reads underlying artifacts
from tmp_path fixtures without crashing when files are absent.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/analytics_verify/test_cycle.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.analytics_verify import cycle as C


def test_run_cycle_isolates_producer_error_and_writes_digest(tmp_path, monkeypatch):
    out = tmp_path / "digest.json"
    monkeypatch.setattr(C, "OUT_PATH", out)
    monkeypatch.setattr(C, "_run_sentinel", lambda: {"overall": "VERIFIED", "n_verified": 2,
                                                       "n_discrepant": 1, "n_stale": 0,
                                                       "n_uncheckable": 0})
    monkeypatch.setattr(C, "_run_regrader", lambda: {"n_eligible": 5, "n_decayed": 2,
                                                       "insufficient_cards": 0,
                                                       "survival": {"7d": 0.8}})

    def _boom():
        raise RuntimeError("contradiction store missing")

    monkeypatch.setattr(C, "_run_contradiction", _boom)
    monkeypatch.setattr(C, "_run_attribution", lambda: {"settled_bets": 0, "rows_appended": 0})

    digest = C.run_cycle()

    assert out.exists()
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["edge_claimed"] is False
    assert digest["producers"]["contradiction"]["status"] == "error"
    assert digest["producers"]["sentinel"]["status"] == "ok"
    assert digest["signals"]["n_decayed_cards"] == 2
    assert digest["signals"]["n_discrepant_stats"] == 1
    # contradiction errored -> its summary contributes nothing, never a crash
    assert digest["signals"]["n_contradiction_conflicts"] == 0


def test_scan_finder_candidates_empty_when_artifacts_absent(tmp_path, monkeypatch):
    from scripts.platformkit.analytics_verify import regrader as R
    from scripts.platformkit.analytics_verify import sentinel as S

    monkeypatch.setattr(R, "SURVIVAL_JSON", tmp_path / "no_survival.json")
    monkeypatch.setattr(S, "OUT_PATH", tmp_path / "no_sentinel.json")
    monkeypatch.setattr(C, "_ROOT", tmp_path)

    cands = C.scan_finder_candidates()
    assert cands == []


def test_scan_finder_candidates_maps_decayed_and_discrepant(tmp_path, monkeypatch):
    from scripts.platformkit.analytics_verify import regrader as R
    from scripts.platformkit.analytics_verify import sentinel as S

    survival = tmp_path / "survival.json"
    survival.write_text(json.dumps({"decayed_cards": [{"card_id": "abc123", "reason": "sign-flip"}]}),
                         encoding="utf-8")
    monkeypatch.setattr(R, "SURVIVAL_JSON", survival)

    sent_report = tmp_path / "sentinel.json"
    sent_report.write_text(json.dumps({"checks": [{"name": "grade_summary.wins",
                                                     "verdict": "DISCREPANT"}]}),
                            encoding="utf-8")
    monkeypatch.setattr(S, "OUT_PATH", sent_report)
    monkeypatch.setattr(C, "_ROOT", tmp_path)

    cands = C.scan_finder_candidates()
    cats = {c["category"] for c in cands}
    assert "DECAYED_CLAIM" in cats
    assert "DISCREPANT_STAT" in cats
