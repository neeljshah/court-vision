"""Unit tests for src.loop.intel_validator (ARM-B atlas validation gate).

Self-contained: uses a fake AtlasSection so no real profile parquets are touched.
Run: python -m pytest tests/test_loop_intel_validator.py -q
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot  # noqa: E402
from src.loop import intel_validator as iv  # noqa: E402

_AS_OF = "2026-05-27"
_AS_OF_DT = _dt.datetime(2026, 5, 27)


def _cv_slots():
    return {"contest_level": CVSlot(name="contest_level", dtype="float",
                                    description="avg defender contest", unit=None)}


class _FakeSection(AtlasSection):
    """A minimal leak-safe section returning a fixed payload regardless of as_of."""

    name = "shot_profile"
    entity = "player"
    source_name = "test.parquet"

    def __init__(self, payload=None, prov=None, conf="high", earlier=None):
        self._payload = payload or {"rim_freq": 0.42, "pts_pg": 24.3, "ts_pct": 0.61}
        self._prov = prov or {"source": "test.parquet", "n": 40, "as_of": _AS_OF}
        self._conf = conf
        self._earlier = earlier  # artifact returned for an earlier build (or None)

    def build(self, entity_id, as_of):
        if as_of.date() < _AS_OF_DT.date() and self._earlier is not None:
            return self._earlier
        return AtlasArtifact(
            section=self.name, entity=self.entity, entity_id=entity_id,
            sub_fields=dict(self._payload), provenance=dict(self._prov),
            confidence=self._conf, as_of=_AS_OF, cv_fields=self.cv_fields(),
        )

    def validate(self, artifact):
        return isinstance(artifact.sub_fields, dict) and bool(artifact.sub_fields)

    def cv_fields(self):
        return _cv_slots()


def _artifact(sub=None, prov=None, conf="high", cv=None, as_of=_AS_OF):
    return AtlasArtifact(
        section="shot_profile", entity="player", entity_id=999999,
        sub_fields=sub if sub is not None else {"rim_freq": 0.42, "pts_pg": 24.3, "ts_pct": 0.61},
        provenance=prov if prov is not None else {"source": "t", "n": 40, "as_of": as_of},
        confidence=conf, as_of=as_of,
        cv_fields=cv if cv is not None else _cv_slots(),
    )


def test_all_pass_clean_artifact():
    sec = _FakeSection()
    res = iv.validate(sec, _artifact(), min_n=5)
    assert res.ok is True
    assert res.leak_free and res.face_valid and res.coverage_ok
    assert res.not_duplicate and res.cv_schema_ok
    assert res.reasons == []


def test_face_validity_flags_out_of_range_pct():
    bad = iv.check_face_validity(_artifact(sub={"ts_pct": 1.9, "pts_pg": 20.0}))
    assert any("ts_pct" in r for r in bad)
    good = iv.check_face_validity(_artifact(sub={"ts_pct": 0.6}))
    assert good == []


def test_face_validity_flags_negative_per_game_and_dispersion():
    reasons = iv.check_face_validity(_artifact(sub={"pts_pg": -3.0, "blk_dispersion": -1.0}))
    assert any("per-game" in r for r in reasons)
    assert any("dispersion" in r for r in reasons)


def test_coverage_hard_floor_and_downgrade():
    # below min_n -> fails coverage
    low = _artifact(prov={"source": "t", "n": 2, "as_of": _AS_OF}, conf="low")
    assert iv.check_coverage(low, min_n=5) is False
    # n=10 supports only "med" but stamped "high" -> downgrade, still coverage_ok
    marg = _artifact(prov={"source": "t", "n": 10, "as_of": _AS_OF}, conf="high")
    res = iv.validate(_FakeSection(), marg, min_n=5)
    assert res.coverage_ok is True
    assert res.downgraded_confidence == "med"


def test_leak_detected_when_provenance_after_as_of():
    art = _artifact(prov={"source": "t", "n": 40, "as_of": "2026-06-10"}, as_of=_AS_OF)
    assert iv.check_leak_free(_FakeSection(), art) is False


def test_leak_detected_when_earlier_build_used_future_data():
    # earlier build claims a value but its provenance as_of is AFTER the earlier date
    earlier = AtlasArtifact(
        section="shot_profile", entity="player", entity_id=999999,
        sub_fields={"rim_freq": 0.99}, provenance={"source": "t", "n": 40, "as_of": _AS_OF},
        confidence="high", as_of="2026-05-26",
    )
    sec = _FakeSection(earlier=earlier)
    art = _artifact(sub={"rim_freq": 0.42})  # differs from earlier's 0.99
    assert iv.check_leak_free(sec, art) is False


def test_cv_schema_rejects_filled_or_mistyped_slot():
    sec = _FakeSection()
    filled = _artifact(cv={"contest_level": CVSlot(name="contest_level", dtype="float", value=1.2)})
    assert iv.check_cv_schema(sec, filled) is False
    mistyped = _artifact(cv={"contest_level": CVSlot(name="contest_level", dtype="bogus")})
    assert iv.check_cv_schema(sec, mistyped) is False
    assert iv.check_cv_schema(sec, _artifact()) is True


def test_cv_schema_rejects_missing_declared_slot():
    sec = _FakeSection()
    missing = _artifact(cv={})  # section declares contest_level but artifact omits it
    assert iv.check_cv_schema(sec, missing) is False


def test_dedup_no_existing_profile_is_not_duplicate():
    # entity_id 999999 has no profile file -> not a duplicate
    assert iv.check_dedup(_artifact(), dedup_threshold=0.97) is True


def test_benjamini_independence_validate_returns_result_type():
    res = iv.validate(_FakeSection(), _artifact(), min_n=5)
    assert isinstance(res, iv.ValidationResult)
