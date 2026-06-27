"""tests.platformkit.improve.test_candidate_enum -- A4 enumerator + family contract.

Asserts:
  (1) candidate_id is DETERMINISTIC (same idea -> same id across calls) and UNIQUE
      (distinct signatures -> distinct ids; no collisions across the enumerated stream).
  (2) the VALIDATOR rejects a spec carrying a $ / retracted number (+18.38, 0.119, +54,
      78.11, 8.94, 54.57); a rejected spec is NEVER enumerated.
  (3) MF4 -- the enumerator NEVER returns a candidate that bypasses
      recalibrator.build_candidate: build_candidates routes EVERY spec through the choke,
      builds nothing itself, and with the sentinel ABSENT returns [] (NO_CANDIDATE).
  (+) dedup: a tried candidate_id is never re-rolled; coverage widens monotonically.
  (+) no $/pnl/roi/edge key anywhere in an emitted spec dict.

Per-file test only (full pytest freezes the box). ASCII; stdlib deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import candidate_families as CF  # noqa: E402
from scripts.platformkit.improve import candidate_enum as CE  # noqa: E402
from scripts.platformkit.improve import pipeline_flag as PF  # noqa: E402


# --------------------------------------------------------------------------- (1) id
def test_candidate_id_is_deterministic():
    a = CF.candidate_id("recal_variant", "nba", "win_prob", "recal=platt")
    b = CF.candidate_id("recal_variant", "nba", "win_prob", "recal=platt")
    assert a == b  # same idea -> same id across calls (stable across restarts)
    assert a.startswith("cand_")


def test_candidate_id_is_unique_across_distinct_signatures():
    ids = [s.candidate_id for s in CF.all_specs("nba")]
    assert len(ids) == len(set(ids))  # no collisions in the enumerated stream
    # a distinct signature yields a distinct id
    p = CF.candidate_id("ingame_interaction", "nba", "win_prob", "ingame=margin:close")
    q = CF.candidate_id("ingame_interaction", "nba", "win_prob", "ingame=margin:mid")
    assert p != q


def test_enumerated_ids_unique_and_stable():
    s1 = CE.enumerate_specs("nba", tried_ids=set())
    s2 = CE.enumerate_specs("nba", tried_ids=set())
    ids1 = [s.candidate_id for s in s1]
    ids2 = [s.candidate_id for s in s2]
    assert ids1 == ids2  # deterministic order + ids
    assert len(ids1) == len(set(ids1))  # unique within the stream
    assert len(ids1) > 0


# --------------------------------------------------------------------------- (2) $ guard
def test_validator_rejects_dollar_token():
    with pytest.raises(ValueError):
        CF.assert_no_dollar("this has a $ sign")
    with pytest.raises(ValueError):
        CF.assert_no_dollar("claims ROI of 5")
    with pytest.raises(ValueError):
        CF.assert_no_dollar("a 12% edge")


@pytest.mark.parametrize("num", ["+18.38", "0.119", "+54", "78.11", "8.94", "54.57"])
def test_validator_rejects_each_retracted_number(num):
    with pytest.raises(ValueError):
        CF.assert_no_dollar("rationale mentions %s here" % num)


def test_validate_spec_rejects_retracted_rationale():
    bad = CF.CandidateSpec(
        family=CF.FAMILY_RECAL, sport="nba", target="win_prob", scope="pregame",
        signature="recal=platt", rationale="delivered +18.38 on the close")
    with pytest.raises(ValueError):
        CF.validate_spec(bad)


def test_validate_spec_rejects_dollar_param_key():
    bad = CF.CandidateSpec(
        family=CF.FAMILY_RECAL, sport="nba", target="win_prob", scope="pregame",
        signature="recal=platt", params={"roi_field": 1.0})
    with pytest.raises(ValueError):
        CF.validate_spec(bad)


def test_validator_does_not_false_trip_on_innocuous_numbers():
    # a value near a retracted token but not the token itself must pass
    CF.assert_no_dollar("margin bucket 118.380 obs 5457")  # no standalone retracted tok
    CF.assert_no_dollar("period late time scarce")


def test_emitted_spec_dict_has_no_dollar_keys():
    for spec in CF.all_specs("nba"):
        d = spec.to_dict()

        def _walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    kl = str(k).lower()
                    assert not any(t in kl for t in ("roi", "pnl", "dollar", "edge", "$")), \
                        "forbidden key %s" % k
                    _walk(v)
            elif isinstance(obj, (list, tuple)):
                for v in obj:
                    _walk(v)

        _walk(d)
        assert d["note"] == "calibration, not edge"
        assert d["vs_close"] == "UNPROVEN"


# --------------------------------------------------------------------------- (+) dedup
def test_tried_ids_are_not_re_rolled():
    full = CE.enumerate_specs("nba", tried_ids=set())
    assert len(full) >= 2
    tried = {full[0].candidate_id}
    rest = CE.enumerate_specs("nba", tried_ids=tried)
    rest_ids = {s.candidate_id for s in rest}
    assert full[0].candidate_id not in rest_ids  # tried family never re-rolled
    assert len(rest) == len(full) - 1


def test_tried_memory_roundtrip(tmp_path):
    p = tmp_path / "tried.jsonl"
    assert CE.load_tried_ids(p) == set()
    spec = CF.all_specs("nba")[0]
    CE.append_tried(spec, path=p)
    assert spec.candidate_id in CE.load_tried_ids(p)
    # a corrupt line is skipped, not fatal
    with p.open("a", encoding="ascii") as fh:
        fh.write("not json\n")
    assert spec.candidate_id in CE.load_tried_ids(p)


# --------------------------------------------------------------------------- (3) MF4
def test_build_candidates_routes_every_spec_through_choke(monkeypatch, tmp_path):
    # The enumerator must NEVER construct a candidate itself: it must call the choke.
    # Replace build_candidate with a spy that records each spec id it was asked to build.
    seen = []

    def _spy(name, settled, priority=None, **kw):
        seen.append(kw.get("candidate_id"))
        return None  # the choke decides NO_CANDIDATE here

    out = CE.build_candidates("nba", [{"x": 1}], build_fn=_spy)
    assert out == []  # nothing built (choke returned None) -> NO_CANDIDATE
    enumerated = {s.candidate_id for s in CE.enumerate_specs("nba", tried_ids=set())}
    # every enumerated spec was routed through the choke (no bypass path)
    assert set(seen) == enumerated
    assert len(seen) == len(enumerated)


def test_build_candidates_inert_when_sentinel_absent(monkeypatch, tmp_path):
    # MF4 + MF1: with the sentinel ABSENT and the REAL choke wired, nothing builds.
    monkeypatch.setattr(PF, "SENTINEL_PATH", tmp_path / "ABSENT")
    assert PF.pipeline_enabled() is False
    settled = [{"sport": "nba", "game_id": "G%d" % i, "outcome": 1.0,
                "states": [{"p0": 0.4, "outcome": 1.0}, {"p0": 0.6, "outcome": 0.0}]}
               for i in range(8)]
    out = CE.build_candidates("nba", settled)  # uses the real recalibrator.build_candidate
    assert out == []  # byte-identical to NO_CANDIDATE: the choke's kill-switch dominates


def test_build_candidates_only_collects_choke_output(monkeypatch):
    # If the choke builds one candidate, the enumerator returns exactly that dict --
    # it never fabricates base_preds/cand_preds/y itself.
    sentinel = {"base_preds": [0.4], "cand_preds": [0.5], "y": [1.0],
                "note": "calibration, not edge", "vs_close": "UNPROVEN"}
    calls = {"n": 0}

    def _one(name, settled, priority=None, **kw):
        calls["n"] += 1
        return dict(sentinel) if calls["n"] == 1 else None

    out = CE.build_candidates("nba", [{"x": 1}], build_fn=_one)
    assert len(out) == 1
    assert out[0]["base_preds"] == [0.4]
    assert out[0]["note"] == "calibration, not edge"
