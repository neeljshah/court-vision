"""Per-file tests for scripts.platformkit.reject_ledger (the signal graveyard).

Isolated: every test points the ledger at a tmp_path file, so the real
data/frontend/reject_ledger.jsonl is never touched. stdlib + pytest only.
Run: python -m pytest scripts/platformkit/test_reject_ledger.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.platformkit import reject_ledger as RL


def _iso(days_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_record_and_lookup_latest_wins(tmp_path):
    led = tmp_path / "rej.jsonl"
    RL.record("nba", "pace_delta", "REJECT", "efficient", ledger_path=led, ts=_iso(5))
    RL.record("nba", "pace_delta", "SHIP", "survived", ledger_path=led, ts=_iso(1))
    rec = RL.lookup("nba", "pace_delta", ledger_path=led)
    assert rec is not None and rec["verdict"] == "SHIP"  # latest ts wins
    assert RL.lookup("nba", "never_seen", ledger_path=led) is None


def test_is_known_reject_true_false_and_stale(tmp_path):
    led = tmp_path / "rej.jsonl"
    RL.record("nba", "dead_sig", "REJECT", ledger_path=led, ts=_iso(10))
    RL.record("nba", "live_sig", "SHIP", ledger_path=led, ts=_iso(10))
    assert RL.is_known_reject("nba", "dead_sig", ledger_path=led) is True
    assert RL.is_known_reject("nba", "live_sig", ledger_path=led) is False
    assert RL.is_known_reject("nba", "unknown", ledger_path=led) is False
    # stale: a 10-day-old reject is revisitable under a 7-day freshness window.
    assert RL.is_known_reject("nba", "dead_sig", stale_after_days=7, ledger_path=led) is False
    assert RL.is_known_reject("nba", "dead_sig", stale_after_days=30, ledger_path=led) is True


def test_sport_and_corpus_scoping(tmp_path):
    led = tmp_path / "rej.jsonl"
    RL.record("mlb", "park_factor", "REJECT", corpus="A", ledger_path=led, ts=_iso(3))
    RL.record("mlb", "park_factor", "SHIP", corpus="B", ledger_path=led, ts=_iso(2))
    # corpus-scoped lookup isolates the two corpora.
    assert RL.lookup("mlb", "park_factor", corpus="A", ledger_path=led)["verdict"] == "REJECT"
    assert RL.is_known_reject("mlb", "park_factor", corpus="A", ledger_path=led) is True
    assert RL.is_known_reject("mlb", "park_factor", corpus="B", ledger_path=led) is False
    # different sport is never matched.
    assert RL.lookup("nba", "park_factor", ledger_path=led) is None


def test_record_proof_verdicts_maps_run_v3_rows(tmp_path):
    led = tmp_path / "rej.jsonl"
    rows = [
        {"signal": "sig_a", "actual": "REJECT", "reason": "null not beaten",
         "p_value": 0.42, "wf_all_improve": False, "passed_expected": True},
        {"signal": "sig_b", "actual": "DEFER", "reason": "thin data", "p_value": 0.9},
        {"name": "sig_c", "verdict": "ACCEPT", "reason": "rare ship"},  # alt field names
        {"reason": "no name -> skipped"},
    ]
    out = RL.record_proof_verdicts("soccer", rows, corpus="data/domains/soccer", ledger_path=led)
    assert len(out) == 3  # the nameless row is skipped
    a = RL.lookup("soccer", "sig_a", ledger_path=led)
    assert a["verdict"] == "REJECT" and a["metrics"]["p_value"] == 0.42
    assert a["corpus"] == "data/domains/soccer" and a["source"] == "signal_proof"
    grave = {r["signal"] for r in RL.graveyard("soccer", ledger_path=led)}
    assert grave == {"sig_a", "sig_b"}  # ACCEPT (sig_c) is not a graveyard member


def test_graveyard_resurrection(tmp_path):
    led = tmp_path / "rej.jsonl"
    # A signal rejected, then later SHIPs on more data -> leaves the graveyard.
    RL.record("tennis", "serve_hold", "REJECT", ledger_path=led, ts=_iso(9))
    RL.record("tennis", "serve_hold", "SHIP", ledger_path=led, ts=_iso(1))
    assert RL.graveyard("tennis", ledger_path=led) == []


def test_ingest_improve_ledger_only_rejects_and_idempotent(tmp_path):
    led = tmp_path / "rej.jsonl"
    imp = tmp_path / "improve.jsonl"
    with imp.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"sport": "nba", "ts": _iso(2), "verdict": "REJECT",
                             "reason": "recal regressed", "delta_brier": -0.01}) + "\n")
        fh.write(json.dumps({"sport": "nba", "ts": _iso(1), "verdict": "SHIP"}) + "\n")
        fh.write(json.dumps({"sport": "mlb", "ts": _iso(1), "verdict": "HOLD"}) + "\n")
    n1 = RL.ingest_improve_ledger(improve_path=imp, ledger_path=led)
    n2 = RL.ingest_improve_ledger(improve_path=imp, ledger_path=led)  # idempotent
    assert n1 == 1 and n2 == 0
    rows = RL.load(source="recal_ratchet", ledger_path=led)
    assert len(rows) == 1 and rows[0]["signal"] == "recalibrator"


def test_format_graveyard_ascii_and_empty(tmp_path):
    led = tmp_path / "rej.jsonl"
    assert "graveyard empty" in RL.format_graveyard(RL.graveyard(ledger_path=led))
    RL.record("nba", "x", "REJECT", "r", ledger_path=led)
    txt = RL.format_graveyard(RL.graveyard(ledger_path=led))
    assert "GRAVEYARD" in txt and txt.isascii()


def test_ingest_discovered_ledger_rejects_only_and_idempotent(tmp_path):
    led = tmp_path / "rej.jsonl"
    disc = tmp_path / "discovered.jsonl"
    with disc.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"name": "pts__div__reb", "family_key": "div:pts:reb",
                             "target": "pts", "kind": "binary", "verdict": "REJECT",
                             "screen_score": 0.12, "wf_all_improve": False,
                             "null_z": 0.3, "date": "2026-06-09"}) + "\n")
        fh.write(json.dumps({"name": "good_one", "verdict": "ACCEPT",
                             "target": "ast", "date": "2026-06-09"}) + "\n")
        fh.write(json.dumps({"verdict": "REJECT", "date": "2026-06-09"}) + "\n")  # no name
    n1 = RL.ingest_discovered_ledger(discovered_path=disc, ledger_path=led, sport="nba")
    n2 = RL.ingest_discovered_ledger(discovered_path=disc, ledger_path=led, sport="nba")
    assert n1 == 1 and n2 == 0  # ACCEPT + nameless excluded; idempotent re-ingest
    rec = RL.lookup("nba", "pts__div__reb", ledger_path=led)
    assert rec["source"] == "signal_discovery" and rec["metrics"]["family_key"] == "div:pts:reb"
    assert {r["signal"] for r in RL.graveyard("nba", ledger_path=led)} == {"pts__div__reb"}
