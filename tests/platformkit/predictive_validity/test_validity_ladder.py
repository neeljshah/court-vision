"""Per-file tests for scripts.platformkit.predictive_validity.validity_ladder --
SYNTHETIC fixtures only (tmp_path); never touches real data/cache artifacts.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/predictive_validity/test_validity_ladder.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.predictive_validity import validity_ladder as vl


def _write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="ascii")


def _t0_doc():
    return {"n_verified": 1, "n_mismatch": 0, "generated_at": "2026-07-19T00:00:00+00:00"}


def _absence_doc(name, verdict="VALID_SIGNAL"):
    return {"as_of": "2026-07-19T00:00:00+00:00",
            "indexes": {name: {"rho": -0.5, "ci": {"lo": -0.6, "hi": -0.4}, "n": 200, "verdict": verdict}}}


def _predictive_doc(verdict="PREDICTIVE_VERIFIED"):
    return {"verdict": verdict, "mean_rho_metric": 0.3, "n_folds": 6,
            "generated_at": "2026-07-19T00:00:00+00:00"}


def test_t0_only_when_no_criterion_or_predictive(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    _write(tmp_path / "fake_validation.json", _t0_doc())
    cfg = {"validation_file": "fake_validation.json", "absence_key": None,
           "offense_key": None, "predictive_file": None}
    out = vl.compose_index("fake_index", cfg, None, None)
    assert out["tier"] == vl.T0
    assert out["caveat"] == vl._T0_CAVEAT
    assert len(out["receipts"]) == 1


def test_missing_everything_falls_back_to_t0_descriptive(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    cfg = {"validation_file": "nope.json", "absence_key": None,
           "offense_key": None, "predictive_file": None}
    out = vl.compose_index("ghost_index", cfg, None, None)
    assert out["tier"] == vl.T0
    assert out["receipts"] == []
    assert "no independent validity receipt" in out["caveat"]


def test_index_present_in_absence_swing_gets_t1(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    _write(tmp_path / "fake_validation.json", _t0_doc())
    cfg = {"validation_file": "fake_validation.json", "absence_key": "fake_index",
           "offense_key": None, "predictive_file": None}
    out = vl.compose_index("fake_index", cfg, _absence_doc("fake_index"), None)
    assert out["tier"] == vl.T1
    tiers_in_receipts = {r["tier"] for r in out["receipts"]}
    assert tiers_in_receipts == {vl.T0, vl.T1}


def test_weak_or_null_absence_verdict_does_not_grant_t1(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    _write(tmp_path / "fake_validation.json", _t0_doc())
    cfg = {"validation_file": "fake_validation.json", "absence_key": "fake_index",
           "offense_key": None, "predictive_file": None}
    out = vl.compose_index("fake_index", cfg, _absence_doc("fake_index", verdict="WEAK_OR_NULL"), None)
    assert out["tier"] == vl.T0


def test_t2_predictive_beats_t1_beats_t0(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    monkeypatch.setattr(vl, "PREDICTIVE_DIR", tmp_path)
    _write(tmp_path / "fake_validation.json", _t0_doc())
    _write(tmp_path / "fake_pred.json", _predictive_doc())
    cfg = {"validation_file": "fake_validation.json", "absence_key": "fake_index",
           "offense_key": None, "predictive_file": "fake_pred.json"}
    out = vl.compose_index("fake_index", cfg, _absence_doc("fake_index"), None)
    assert out["tier"] == vl.T2
    tiers_in_receipts = {r["tier"] for r in out["receipts"]}
    assert tiers_in_receipts == {vl.T0, vl.T1, vl.T2}


def test_predictive_descriptive_only_does_not_grant_t2(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    monkeypatch.setattr(vl, "PREDICTIVE_DIR", tmp_path)
    _write(tmp_path / "fake_validation.json", _t0_doc())
    _write(tmp_path / "fake_pred.json", _predictive_doc(verdict="DESCRIPTIVE_ONLY"))
    cfg = {"validation_file": "fake_validation.json", "absence_key": None,
           "offense_key": None, "predictive_file": "fake_pred.json"}
    out = vl.compose_index("fake_index", cfg, None, None)
    assert out["tier"] == vl.T0


def test_offense_swing_missing_artifact_tiers_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    _write(tmp_path / "fake_validation.json", _t0_doc())
    cfg = {"validation_file": "fake_validation.json", "absence_key": None,
           "offense_key": "fake_offense_index", "predictive_file": None}
    out = vl.compose_index("fake_offense_index", cfg, None, offense_doc=None)
    assert out["tier"] == vl.T0


def test_offense_swing_present_grants_t1(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    _write(tmp_path / "fake_validation.json", _t0_doc())
    cfg = {"validation_file": "fake_validation.json", "absence_key": None,
           "offense_key": "fake_offense_index", "predictive_file": None}
    out = vl.compose_index("fake_offense_index", cfg, None, _absence_doc("fake_offense_index"))
    assert out["tier"] == vl.T1


def test_ladder_caveat_missing_artifact(tmp_path):
    path = tmp_path / "nope.json"
    assert "no validity ladder receipt" in vl.ladder_caveat("anything", path=path)


def test_ladder_caveat_missing_index_entry(tmp_path):
    path = tmp_path / "ladder.json"
    _write(path, {"as_of": "x", "indexes": {"other_index": {"tier": vl.T0, "caveat": "c"}}})
    assert "no validity ladder receipt" in vl.ladder_caveat("missing_index", path=path)


def test_ladder_caveat_present(tmp_path):
    path = tmp_path / "ladder.json"
    _write(path, {"as_of": "2026-07-19", "indexes": {
        "fake_index": {"tier": vl.T1, "caveat": "T1_CRITERION: absence_swing_criterion -- rho=-0.5"}}})
    out = vl.ladder_caveat("fake_index", path=path)
    assert "T1_CRITERION" in out
    assert "2026-07-19" in out


def test_write_and_reread_artifact(tmp_path):
    doc = {"as_of": "x", "indexes": {"a": {"tier": vl.T0, "receipts": [], "caveat": "c"}},
           "honest_note": "n", "edge_claimed": False}
    path = tmp_path / "validity_ladder.json"
    out_path = vl.write_artifact(doc, path=path)
    reread = json.loads(open(out_path, encoding="ascii").read())
    assert reread["edge_claimed"] is False
    assert reread["indexes"]["a"]["tier"] == vl.T0


def test_build_ladder_covers_full_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(vl, "VALIDATION_DIR", tmp_path)
    monkeypatch.setattr(vl, "PREDICTIVE_DIR", tmp_path)
    monkeypatch.setattr(vl, "ABSENCE_SWING_PATH", tmp_path / "absence.json")
    monkeypatch.setattr(vl, "ABSENCE_SWING_OFFENSE_PATH", tmp_path / "offense.json")
    doc = vl.build_ladder()
    assert set(doc["indexes"].keys()) == set(vl.REGISTRY.keys())
    assert doc["edge_claimed"] is False
    for entry in doc["indexes"].values():
        assert entry["tier"] == vl.T0  # no fixtures present -> honest floor
