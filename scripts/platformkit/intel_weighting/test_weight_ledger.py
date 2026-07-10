"""Per-file test for weight_ledger. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/intel_weighting/test_weight_ledger.py -q
"""
from __future__ import annotations

from scripts.platformkit.intel_weighting import weight_ledger as wl
from scripts.platformkit.intel_weighting.relevance_gate import GateResult


def _g(family="fam_a", metric="m1", delta=0.01, verdict="NULL_LOCAL") -> GateResult:
    return GateResult(family=family, sport="nba", metric=metric, entity_mapping="team",
                       n_games=100, brier_base=0.24, brier_cond=0.23, delta=delta,
                       delta_trunc80=delta, dm_p=0.5, verdict=verdict, caveats=[])


def test_append_then_read_round_trips_and_never_claims_edge(tmp_path):
    ledger = tmp_path / "claim_weights.jsonl"
    wl.append_results([_g()], ledger=ledger)
    rows = wl.read_ledger(ledger)
    assert len(rows) == 1
    assert rows[0]["edge_claimed"] is False
    assert rows[0]["family"] == "fam_a" and rows[0]["metric"] == "m1"


def test_rerun_upserts_by_key_instead_of_duplicating(tmp_path):
    """Failure mode: if the (family, metric, method) key logic breaks, a
    daily re-run of the same gate would silently pile up duplicate/stale rows
    instead of replacing the prior verdict -- corrupting anything downstream
    that assumes one row per key."""
    ledger = tmp_path / "claim_weights.jsonl"
    wl.append_results([_g(delta=0.01, verdict="NULL_LOCAL")], ledger=ledger)
    wl.append_results([_g(delta=0.09, verdict="CONFIRMED_LOCAL")], ledger=ledger)
    rows = wl.read_ledger(ledger)
    assert len(rows) == 1
    assert rows[0]["delta"] == 0.09 and rows[0]["verdict"] == "CONFIRMED_LOCAL"


def test_different_families_coexist_and_method_scopes_key(tmp_path):
    ledger = tmp_path / "claim_weights.jsonl"
    wl.append_results([_g(family="fam_a")], ledger=ledger, method="gate_v1")
    wl.append_results([_g(family="fam_a")], ledger=ledger, method="gate_v2")
    rows = wl.read_ledger(ledger)
    assert len(rows) == 2
    assert {r["method"] for r in rows} == {"gate_v1", "gate_v2"}
