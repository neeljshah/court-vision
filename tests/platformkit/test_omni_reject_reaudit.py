"""Tests for scripts.platformkit.omni.reject_reaudit (S8.1 REJECT re-audit lane).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_reject_reaudit.py -q
"""
from __future__ import annotations

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import reject_reaudit as rr


def _seed_originals(tmp_path):
    """Seed a synthetic ledger with 2 registry-origin + 1 test_log-origin
    rejected claim, mirroring what claims_backfill actually produces."""
    registry_claim = {
        "statement": "opp_def_matchup on a_pts (oos_rel below threshold)",
        "type": "negative",
        "scope": {"sport": "nba", "entity_type": "player-game", "regime": "2025-26"},
        "topic": "a_pts", "lifecycle": "rejected",
        "provenance": {"created_by_lane": "p2_backfill"},
    }
    registry_claim2 = {
        "statement": "minutes_kitchensink on a_min (oos_rel below threshold)",
        "type": "negative",
        "scope": {"sport": "nba", "entity_type": "player-game", "regime": "2025-26"},
        "topic": "a_min", "lifecycle": "rejected",
        "provenance": {"created_by_lane": "p2_backfill"},
    }
    test_log_claim = {
        "statement": "fam_score_null | garbage+is_clutch over state5",
        "type": "negative",
        "scope": {"sport": "nba", "entity_type": "family", "regime": "2025-26"},
        "topic": "fam_score_state", "lifecycle": "rejected",
        "provenance": {"created_by_lane": "p2_backfill"},
    }
    ids = [cl.add_claim(c, base_dir=tmp_path) for c in (registry_claim, registry_claim2, test_log_claim)]
    return ids


def test_enumerate_originals_finds_expected_split(tmp_path):
    _seed_originals(tmp_path)
    originals = rr.enumerate_originals(base_dir=tmp_path)
    assert len(originals) == 3
    assert sum(1 for o in originals if o["source"] == "registry") == 2
    assert sum(1 for o in originals if o["source"] == "test_log") == 1
    names = {o["signal_name"] for o in originals}
    assert names == {"opp_def_matchup", "minutes_kitchensink", "fam_score_null"}


def test_dedupe_by_signal_name_drops_repeats():
    originals = [
        {"signal_name": "a", "grain": "g", "target": "t", "source": "registry", "claim_id": "1"},
        {"signal_name": "a", "grain": "g", "target": "t", "source": "registry", "claim_id": "1dup"},
        {"signal_name": "b", "grain": "g", "target": "t", "source": "registry", "claim_id": "2"},
    ]
    deduped, n_dropped = rr.dedupe_by_signal_name(originals)
    assert len(deduped) == 2
    assert n_dropped == 1


def test_not_testable_finer_path_ledgered(tmp_path):
    parent_id, _, _ = _seed_originals(tmp_path)
    contract = rr.NA.build_contract(
        signal_name="opp_def_matchup", sport="nba", native_observable="shot_quality",
        metric="crps", baseline_model="none (no row-level re-score performed)",
        market_families=["props.pts"], regime_scope="all", corpus="discovery",
    )
    verdict_info = {"verdict": "NOT_TESTABLE", "reason": "no row-level corpus", "n": None}
    claim_id = rr.ledger_verdict(contract, "props.pts", verdict_info, parent_id, base_dir=tmp_path)

    df = cl.query(sport="nba", base_dir=tmp_path)
    row = df[df["claim_id"] == claim_id].iloc[0]
    assert row["lifecycle"] == "screened"
    links = row["links_json"]
    assert parent_id in links


def test_synthetic_flip_ledgered_with_parent_link(tmp_path):
    parent_id, _, _ = _seed_originals(tmp_path)
    contract = rr.NA.build_contract(
        signal_name="opp_def_matchup", sport="nba", native_observable="shot_quality",
        metric="crps", baseline_model="existing gate baseline",
        market_families=["props.pts"], regime_scope="all", corpus="discovery",
    )
    verdict_info = {"verdict": "ACCEPT", "delta": 0.02, "ci_low": 0.0, "ci_high": 0.04, "n": 300}
    claim_id = rr.ledger_verdict(contract, "props.pts", verdict_info, parent_id, base_dir=tmp_path)

    df = cl.query(sport="nba", base_dir=tmp_path)
    row = df[df["claim_id"] == claim_id].iloc[0]
    assert row["lifecycle"] == "accepted"
    assert row["type"] == "effect"
    assert parent_id in row["links_json"]


def test_benjamini_hochberg_known_example():
    # textbook BH example: p=[0.01,0.02,0.03,0.5], alpha=0.05 -> first 3 survive
    pvalues = [0.01, 0.02, 0.03, 0.5]
    result = rr.benjamini_hochberg(pvalues, alpha=0.05)
    assert result["n"] == 4
    assert result["survivors"] == [0, 1, 2]
    assert result["batch_overfit_est"] == round(0.05 * 3, 4)


def test_benjamini_hochberg_empty_batch():
    result = rr.benjamini_hochberg([])
    assert result == {"n": 0, "survivors": [], "batch_overfit_est": 0.0}


def test_run_reaudit_end_to_end(tmp_path):
    _seed_originals(tmp_path)
    out_dir = tmp_path / "reaudit_out"
    summary = rr.run_reaudit(claims_base_dir=tmp_path, out_dir=out_dir)
    assert summary["n_originals"] == 3
    assert summary["n_registry"] == 2
    assert summary["n_test_log"] == 1
    assert summary["n_flips"] == 0
    assert summary["n_not_testable_finer"] == 3
    assert (out_dir / "summary.json").is_file()
    assert (out_dir / "reaudit_detail.parquet").is_file()
