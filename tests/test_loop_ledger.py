"""tests/test_loop_ledger.py -- unit tests for src.loop.ledger.

Tests cover:
  - record_signal: correct schema, dedup, DEFER not deduplicated
  - record_atlas:  correct schema, null signal fields
  - load_all:      empty file, multi-entry round-trip
  - already_tested: non-DEFER gate, DEFER transparent
  - apply_fdr:     BH procedure correctness + in-place rewrite
  - supersession_chain: single entry, linear chain, missing name
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path (required when running from repo root).
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.loop.atlas import AtlasArtifact, CVSlot
from src.loop.signal import GateResult, Verdict
import src.loop.ledger as ledger


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_gate_result(
    name: str = "usage_seesaw",
    verdict: Verdict = Verdict.SHIP,
    *,
    wf_folds: list | None = None,
    p_value: float | None = 0.01,
    null_delta: float = 0.011,
    ablation_delta: float = -0.009,
    clv: float = 0.62,
) -> GateResult:
    return GateResult(
        signal_name=name,
        verdict=verdict,
        reason="test",
        wf_folds=wf_folds if wf_folds is not None else [-0.012, -0.008, -0.015, -0.004],
        wf_all_improve=True,
        null_delta=null_delta,
        null_pass=True,
        ablation_delta=ablation_delta,
        ablation_pass=True,
        calibration_ok=True,
        clv=clv,
        clv_pass=True,
        p_value=p_value,
        fdr_pass=True,
        metrics={"extra": 1},
    )


def _make_artifact(
    section: str = "shot_profile",
    entity: str = "player",
    entity_id: int = 1628983,
    as_of: str = "2026-05-30",
) -> AtlasArtifact:
    return AtlasArtifact(
        section=section,
        entity=entity,
        entity_id=entity_id,
        value=0.42,
        sub_fields={"rim_freq": 0.42, "mid_freq": 0.15},
        provenance={"source": "pbp", "n": 40, "confidence": "high"},
        confidence="high",
        as_of=as_of,
        cv_fields={"defender_distance_dist": CVSlot(name="defender_distance_dist",
                                                    dtype="dist", unit="ft",
                                                    description="dist dist", value=None)},
    )


# ---------------------------------------------------------------------------
# 1. record_signal
# ---------------------------------------------------------------------------

def test_record_signal_returns_correct_id(tmp_path):
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result()
    eid = ledger.record_signal(gr, target="pts", path=p)
    assert eid.startswith("signal:usage_seesaw:")
    assert "2026" in eid or eid.count(":") == 2   # format check


def test_record_signal_schema_round_trip(tmp_path):
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="rim_rate", p_value=0.03)
    eid = ledger.record_signal(gr, target="fg3m", path=p)

    entries = ledger.load_all(p)
    assert len(entries) == 1
    e = entries[0]
    assert e["id"] == eid
    assert e["kind"] == "signal"
    assert e["name"] == "rim_rate"
    assert e["target"] == "fg3m"
    assert e["entity"] is None
    assert e["verdict"] == "SHIP"
    assert e["wf_folds"] == [-0.012, -0.008, -0.015, -0.004]
    assert e["wf_all_improve"] is True
    assert math.isclose(e["p_value"], 0.03)
    assert e["supersedes"] is None
    assert isinstance(e["metrics"], dict)


def test_record_signal_dedup_same_name_same_date(tmp_path):
    """Second non-DEFER call for same (name, date) should be a no-op."""
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="seesaw")
    id1 = ledger.record_signal(gr, target="pts", path=p)
    gr2 = _make_gate_result(name="seesaw", verdict=Verdict.REJECT)
    id2 = ledger.record_signal(gr2, target="pts", path=p)
    # same id returned (deduped)
    assert id1 == id2
    # only one entry in file
    entries = ledger.load_all(p)
    assert len(entries) == 1
    assert entries[0]["verdict"] == "SHIP"


def test_record_signal_defer_not_deduped(tmp_path):
    """DEFER entries are always appended (hypothesis may be re-queued)."""
    p = tmp_path / "ledger.jsonl"
    gr_defer = _make_gate_result(name="low_cov", verdict=Verdict.DEFER, p_value=None)
    ledger.record_signal(gr_defer, target="reb", path=p)
    ledger.record_signal(gr_defer, target="reb", path=p)
    entries = ledger.load_all(p)
    assert len(entries) == 2


def test_record_signal_with_supersedes(tmp_path):
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="rim_v2")
    old_id = "signal:rim_v1:2026-05-01"
    eid = ledger.record_signal(gr, target="pts", supersedes=old_id, path=p)
    e = ledger.load_all(p)[0]
    assert e["supersedes"] == old_id


# ---------------------------------------------------------------------------
# 2. record_atlas
# ---------------------------------------------------------------------------

def test_record_atlas_schema(tmp_path):
    p = tmp_path / "ledger.jsonl"
    art = _make_artifact()
    eid = ledger.record_atlas(art, verdict="SHIP", reason="face-valid", path=p)
    assert eid.startswith("atlas:shot_profile:")
    e = ledger.load_all(p)[0]
    assert e["kind"] == "atlas"
    assert e["entity"] == "player"
    assert e["target"] is None
    assert e["wf_folds"] == []
    assert e["null_delta"] is None
    assert e["p_value"] is None
    assert e["verdict"] == "SHIP"
    assert e["reason"] == "face-valid"


def test_record_atlas_uses_artifact_as_of(tmp_path):
    p = tmp_path / "ledger.jsonl"
    art = _make_artifact(as_of="2026-05-15")
    eid = ledger.record_atlas(art, verdict="REJECT", path=p)
    e = ledger.load_all(p)[0]
    assert e["date"] == "2026-05-15"
    assert eid == f"atlas:shot_profile:2026-05-15"


# ---------------------------------------------------------------------------
# 3. load_all
# ---------------------------------------------------------------------------

def test_load_all_empty_returns_empty_list(tmp_path):
    p = tmp_path / "ledger.jsonl"
    assert ledger.load_all(p) == []


def test_load_all_missing_file_returns_empty_list(tmp_path):
    p = tmp_path / "nonexistent.jsonl"
    assert ledger.load_all(p) == []


def test_load_all_multiple_entries(tmp_path):
    p = tmp_path / "ledger.jsonl"
    for name, tgt in [("sig_a", "pts"), ("sig_b", "reb"), ("sig_c", "ast")]:
        gr = _make_gate_result(name=name)
        ledger.record_signal(gr, target=tgt, path=p)
    entries = ledger.load_all(p)
    assert len(entries) == 3
    names = {e["name"] for e in entries}
    assert names == {"sig_a", "sig_b", "sig_c"}


# ---------------------------------------------------------------------------
# 4. already_tested
# ---------------------------------------------------------------------------

def test_already_tested_false_for_empty_ledger(tmp_path):
    p = tmp_path / "ledger.jsonl"
    assert ledger.already_tested("anything", path=p) is False


def test_already_tested_true_after_ship(tmp_path):
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="my_sig", verdict=Verdict.SHIP)
    ledger.record_signal(gr, target="pts", path=p)
    assert ledger.already_tested("my_sig", kind="signal", path=p) is True


def test_already_tested_true_after_reject(tmp_path):
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="bad_sig", verdict=Verdict.REJECT)
    ledger.record_signal(gr, target="pts", path=p)
    assert ledger.already_tested("bad_sig", path=p) is True


def test_already_tested_false_for_defer_only(tmp_path):
    """A DEFER-only entry does NOT block re-testing."""
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="wait_sig", verdict=Verdict.DEFER, p_value=None)
    ledger.record_signal(gr, target="blk", path=p)
    assert ledger.already_tested("wait_sig", path=p) is False


def test_already_tested_kind_namespaced(tmp_path):
    """A signal entry does not block an atlas entry with the same name."""
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="shot_profile", verdict=Verdict.SHIP)
    ledger.record_signal(gr, target="pts", path=p)
    # atlas 'shot_profile' should still be untested
    assert ledger.already_tested("shot_profile", kind="atlas", path=p) is False
    assert ledger.already_tested("shot_profile", kind="signal", path=p) is True


# ---------------------------------------------------------------------------
# 5. apply_fdr
# ---------------------------------------------------------------------------

def _write_entries_with_pvalues(path: Path, pvalues: list[float | None]) -> list[str]:
    """Write synthetic ledger entries; return list of ids."""
    ids = []
    for i, pv in enumerate(pvalues):
        name = f"sig_{i}"
        gr = _make_gate_result(name=name, p_value=pv)
        eid = ledger.record_signal(gr, target="pts", path=path)
        ids.append(eid)
    return ids


def test_apply_fdr_empty_ledger(tmp_path):
    p = tmp_path / "ledger.jsonl"
    result = ledger.apply_fdr(q=0.10, path=p)
    assert result == {}


def test_apply_fdr_all_significant(tmp_path):
    """Three tiny p-values should all pass at q=0.10."""
    p = tmp_path / "ledger.jsonl"
    _write_entries_with_pvalues(p, [0.001, 0.002, 0.003])
    result = ledger.apply_fdr(q=0.10, path=p)
    assert all(result.values()), f"Expected all True, got {result}"


def test_apply_fdr_none_significant(tmp_path):
    """Three large p-values should all fail."""
    p = tmp_path / "ledger.jsonl"
    _write_entries_with_pvalues(p, [0.5, 0.6, 0.7])
    result = ledger.apply_fdr(q=0.10, path=p)
    assert not any(result.values()), f"Expected all False, got {result}"


def test_apply_fdr_mixed(tmp_path):
    """Classic BH example: with q=0.05, m=6, p=[0.001,0.004,0.019,0.05,0.79,0.95].
    BH thresholds: 1/6*0.05=0.0083, 2/6=0.0167, 3/6=0.025, 4/6=0.0333, 5/6=0.0417, 6/6=0.05.
    Sorted: 0.001<=0.0083 pass, 0.004<=0.0167 pass, 0.019<=0.025 pass, 0.05<=0.0333 fail.
    Max passing rank = 3. So ranks 1,2,3 pass (p=0.001,0.004,0.019) and 4,5,6 fail."""
    p = tmp_path / "ledger.jsonl"
    _write_entries_with_pvalues(p, [0.001, 0.004, 0.019, 0.05, 0.79, 0.95])
    result = ledger.apply_fdr(q=0.05, path=p)
    passing = sum(1 for v in result.values() if v)
    failing = sum(1 for v in result.values() if not v)
    assert passing == 3, f"Expected 3 pass, got {passing}: {result}"
    assert failing == 3, f"Expected 3 fail, got {failing}: {result}"


def test_apply_fdr_rewrites_ledger(tmp_path):
    """fdr_pass flags must be persisted to the ledger file."""
    p = tmp_path / "ledger.jsonl"
    _write_entries_with_pvalues(p, [0.001, 0.9])
    ledger.apply_fdr(q=0.10, path=p)
    entries = ledger.load_all(p)
    fdr_flags = {e["id"]: e["fdr_pass"] for e in entries}
    # at least one True and one False
    assert True in fdr_flags.values()
    assert False in fdr_flags.values()


def test_apply_fdr_skips_null_pvalue_entries(tmp_path):
    """Entries without p_value (e.g. atlas records) must be excluded from BH."""
    p = tmp_path / "ledger.jsonl"
    # one atlas entry (no p_value)
    art = _make_artifact()
    ledger.record_atlas(art, verdict="SHIP", path=p)
    # one signal entry with p_value
    gr = _make_gate_result(name="sig_x", p_value=0.01)
    eid = ledger.record_signal(gr, target="pts", path=p)
    result = ledger.apply_fdr(q=0.10, path=p)
    # only the signal entry appears in result
    assert eid in result
    assert len(result) == 1


# ---------------------------------------------------------------------------
# 6. supersession_chain
# ---------------------------------------------------------------------------

def test_supersession_chain_empty(tmp_path):
    p = tmp_path / "ledger.jsonl"
    assert ledger.supersession_chain("never_tested", path=p) == []


def test_supersession_chain_single(tmp_path):
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="solo")
    eid = ledger.record_signal(gr, target="pts", path=p)
    chain = ledger.supersession_chain("solo", path=p)
    assert chain == [eid]


def test_supersession_chain_linear(tmp_path):
    """v1 -> v2 -> v3 chain should return [v1_id, v2_id, v3_id]."""
    p = tmp_path / "ledger.jsonl"
    # manually write 3 linked entries
    import datetime as dt
    id_v1 = "signal:rim_rate:2026-05-01"
    id_v2 = "signal:rim_rate:2026-05-15"
    id_v3 = "signal:rim_rate:2026-05-30"
    entries = [
        {"id": id_v1, "kind": "signal", "name": "rim_rate", "target": "pts",
         "entity": None, "verdict": "SHIP", "reason": "", "wf_folds": [],
         "wf_all_improve": False, "null_delta": None, "ablation_delta": None,
         "calibration_ok": None, "clv": None, "p_value": None, "fdr_pass": None,
         "date": "2026-05-01", "supersedes": None, "metrics": {}},
        {"id": id_v2, "kind": "signal", "name": "rim_rate", "target": "pts",
         "entity": None, "verdict": "SHIP", "reason": "", "wf_folds": [],
         "wf_all_improve": False, "null_delta": None, "ablation_delta": None,
         "calibration_ok": None, "clv": None, "p_value": None, "fdr_pass": None,
         "date": "2026-05-15", "supersedes": id_v1, "metrics": {}},
        {"id": id_v3, "kind": "signal", "name": "rim_rate", "target": "pts",
         "entity": None, "verdict": "SHIP", "reason": "", "wf_folds": [],
         "wf_all_improve": False, "null_delta": None, "ablation_delta": None,
         "calibration_ok": None, "clv": None, "p_value": None, "fdr_pass": None,
         "date": "2026-05-30", "supersedes": id_v2, "metrics": {}},
    ]
    with p.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")

    chain = ledger.supersession_chain("rim_rate", path=p)
    assert chain == [id_v1, id_v2, id_v3], f"Got {chain}"


def test_supersession_chain_kind_scoped(tmp_path):
    """signal and atlas chains for same name are independent."""
    p = tmp_path / "ledger.jsonl"
    gr = _make_gate_result(name="my_section", verdict=Verdict.SHIP)
    sig_id = ledger.record_signal(gr, target="pts", path=p)
    art = _make_artifact(section="my_section")
    atl_id = ledger.record_atlas(art, verdict="SHIP", path=p)

    sig_chain = ledger.supersession_chain("my_section", kind="signal", path=p)
    atl_chain = ledger.supersession_chain("my_section", kind="atlas", path=p)
    assert sig_chain == [sig_id]
    assert atl_chain == [atl_id]
    assert sig_chain != atl_chain
