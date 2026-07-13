"""Tests for scripts.platformkit.omni.funnel (P4 screen->family->gate).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_funnel.py -q

Stages A/B are exercised with monkeypatched IFR.run_batch / RR.replicate so
the suite stays fast (real fits/reserve replication are exercised separately,
for real, on a live discovery slice -- see .planning/omni/handoff/
P4_schema.md for that run's evidence). What IS real here: claims_ledger,
claims_intake, native_altitude, and BH (statsmodels) all run for real against
tmp_path.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.omni import claims_ledger as CL
from scripts.platformkit.omni import funnel
from scripts.platformkit.interaction_factory import runner as IFR
from scripts.platformkit.interaction_factory import replicate_reserve as RR


def _row(cid, verdict, p, effect=0.05, outcome="efg", sport="basketball_nba", n=500, corpus="disc"):
    return {"candidate_id": cid, "template_id": "fake_tpl", "sport": sport, "atomic_unit": "x",
            "outcome": outcome, "attr_a": "a", "attr_b": "b", "term": "fa:fb", "k_declared": 3,
            "cum_K": 1, "verdict": verdict, "effect": effect, "p": p, "n": n, "alpha_fwer": 0.02,
            "corpus": corpus, "note": "", "edge_claimed": False, "computed_at": "2026-07-13T00:00:00Z"}


def test_stage_a_kills_junk_and_retains_preds(tmp_path, monkeypatch):
    rows = [_row("cand_junk", IFR.NULL, p=0.8), _row("cand_dead", IFR.NOT_TESTABLE, p=None, effect=None, n=0)]
    monkeypatch.setattr(funnel.IFR, "run_batch", lambda *a, **k: rows)
    out = funnel.stage_a_screen("fake_tpl", 2, "batch1", base_dir=tmp_path, preds_dir=tmp_path / "preds")
    assert len(out) == 2
    for r in out:
        assert r["kill_claim_id"] is not None
        assert (tmp_path / "preds" / "batch1").exists()
        import pathlib
        assert pathlib.Path(r["preds_path"]).is_file()
    df = CL.query(base_dir=tmp_path)
    assert set(df["lifecycle"]) == {"rejected", "screened"}


def test_stage_b_bh_splits_survivors_and_records_overfit_est(tmp_path):
    # 3 screen survivors: 2 genuinely small p, 1 borderline that BH should reject.
    screen_rows = [
        _row("cand_a", IFR.SURVIVES, p=0.0005, effect=0.08),
        _row("cand_b", IFR.SURVIVES, p=0.0009, effect=0.07),
        _row("cand_c", IFR.SURVIVES, p=0.2, effect=0.01),
    ]
    out = funnel.stage_b_family(screen_rows, "batch1", alpha=0.05, base_dir=tmp_path)
    assert len(out) == 3
    verdicts = {r["candidate_id"]: r["family_verdict"] for r in out}
    assert verdicts["cand_a"] == "ACCEPT"
    assert verdicts["cand_c"] == "REJECT"
    assert all(r["prereg_claim_id"] for r in out)
    assert all(r["batch_overfit_est"] is not None for r in out)


def test_acceptance_1_and_2_full_funnel_one_candidate_and_junk_dies(tmp_path, monkeypatch):
    """Acceptance 1: one candidate traverses A->B->C with ledgered verdicts.
    Acceptance 2: a planted junk NULL row dies at A (no family/gate claim)."""
    screen_rows = [_row("cand_survives", IFR.SURVIVES, p=0.0003, effect=0.09),
                   _row("cand_junk", IFR.NULL, p=0.9)]
    monkeypatch.setattr(funnel.IFR, "run_batch", lambda *a, **k: screen_rows)
    monkeypatch.setattr(funnel.RR, "replicate", lambda **k: [
        {"candidate_id": "cand_survives", "verdict": "REPLICATED", "sport": "basketball_nba",
         "template_id": "fake_tpl", "effect": 0.07, "n": 400, "corpus": "reserve_x",
         "discovery_p": 0.0003, "p": 0.01},
    ])
    result = funnel.run_funnel("fake_tpl", 2, "batch_accept12", base_dir=tmp_path, preds_dir=tmp_path / "preds")
    assert len(result["screen"]) == 2
    junk = [r for r in result["screen"] if r["candidate_id"] == "cand_junk"][0]
    assert junk["kill_claim_id"] is not None
    assert "cand_junk" not in {f["candidate_id"] for f in result["family"]}
    assert len(result["gate"]) == 1
    assert result["gate"][0]["gate_status"] == "REPLICATED"
    assert result["gate"][0]["claim_id"] is not None

    df = CL.query(base_dir=tmp_path)
    assert "replicated" in set(df["lifecycle"])
    assert "rejected" in set(df["lifecycle"]) or "screened" in set(df["lifecycle"])


def test_acceptance_3_borrowed_significance_dies_at_gate(tmp_path, monkeypatch):
    """A signal fit to discovery-slice noise clears A (small p by construction)
    and clears B (BH-significant), but the reserve worker's pure verdict_for
    rule flips sign on the independent slice -> KILLED, never accepted."""
    # verdict_for is the real, pure rule the R2 worker uses -- exercise it directly
    # (small synthetic input, no real corpus needed): discovery effect positive,
    # reserve-slice effect negative -> sign flip -> KILLED.
    v = RR.verdict_for(discovery_effect=0.08, fit={"effect": -0.02, "p": 0.9, "n": 300}, alpha=0.02)
    assert v == "KILLED"

    screen_rows = [_row("cand_borrowed", IFR.SURVIVES, p=0.0001, effect=0.08)]
    monkeypatch.setattr(funnel.IFR, "run_batch", lambda *a, **k: screen_rows)
    monkeypatch.setattr(funnel.RR, "replicate", lambda **k: [
        {"candidate_id": "cand_borrowed", "verdict": "KILLED", "sport": "basketball_nba",
         "template_id": "fake_tpl", "effect": -0.02, "n": 300, "corpus": "reserve_x",
         "discovery_p": 0.0001, "p": 0.9},
    ])
    result = funnel.run_funnel("fake_tpl", 1, "batch_borrowed", base_dir=tmp_path, preds_dir=tmp_path / "preds")
    assert result["family"][0]["family_verdict"] == "ACCEPT"  # cleared A+B
    assert result["gate"][0]["gate_status"] == "KILLED"        # died at C
    df = CL.query(base_dir=tmp_path)
    gate_claim = df[df["lifecycle"] == "rejected"]
    assert len(gate_claim) >= 1


def test_acceptance_4_transfer_proposal_enters_stage_a(tmp_path):
    parent = {
        "statement": "tennis rest-x-return (days_since_last_match x bp_saved): near-miss "
                     "(FAILED_REPLICATION_POWER_ANNOTATED, p_disc=.0039 p_repl=.023)",
        "type": "negative",
        "scope": {"sport": "tennis", "regime": "all", "market_families": []},
        "topic": "rest_x_return",
        "lifecycle": "rejected",
        "effect": {"metric": "p", "size": 0.045362, "n": 7340},
    }
    parent_id = CL.add_claim(parent, base_dir=tmp_path)
    parent_claim = {"claim_id": parent_id}

    result = funnel.generate_transfer_proposal(parent_claim, base_dir=tmp_path)
    assert result["verdict"] == "ACCEPTED"
    df = CL.query(base_dir=tmp_path)
    row = df[df["claim_id"] == result["claim_id"]].iloc[0]
    import json
    links = json.loads(row["links_json"])
    assert links["transfer_parents"] == [parent_id]
    assert "momentum" not in row["statement"].lower()
