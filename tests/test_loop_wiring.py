"""Tests for src.loop.wiring -- ship_signal / wire_variance_signal / helpers.

All model training is mocked via the ``train_fn`` injectable; no actual XGBoost
or LightGBM training is performed. The store is backed by a tmp directory so
the real data/models/ tree is never touched.
"""
from __future__ import annotations

import datetime as _dt
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.loop.signal import AsOfContext, GateResult, Hypothesis, Signal, SignalValue, Verdict
from src.loop.store import PointInTimeStore, entity_key


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

class _DemoSignal(Signal):
    """Minimal concrete Signal for wiring tests."""

    name = "demo_signal"
    target = "pts"
    scope = "pregame"
    reads_atlas: List[str] = []
    emits: List[str] = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        return 0.5

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(
            name=self.name, target=self.target, scope=self.scope,
            statement="demo statement",
        )


class _DemoSignalWithLearned(_DemoSignal):
    """Signal that exposes ._learned_values (per-entity write-back protocol)."""

    name = "demo_learned"

    def __init__(self, store=None):
        super().__init__(store)
        self._learned_values = {
            "player:1628983": 0.12,
            "player:203954": -0.05,
        }


class _VarianceSignal(_DemoSignal):
    """Signal declared as a variance/sigma signal."""

    name = "demo_variance"
    target = "sigma"
    scope = "pregame"


_DEFAULT_BUCKETS = [{"stat": "pts", "bucket": "high_usage", "n": 120}]


def _make_ship_result(signal_name: str = "demo_signal",
                      buckets: Optional[List[dict]] = None,
                      use_default_buckets: bool = True) -> GateResult:
    # Explicit None -> use default; explicit [] -> empty (don't use `or`)
    regime_buckets = (_DEFAULT_BUCKETS if use_default_buckets else []) if buckets is None else buckets
    return GateResult(
        signal_name=signal_name,
        verdict=Verdict.SHIP,
        reason="all criteria passed",
        wf_folds=[-0.010, -0.008, -0.012, -0.006],
        wf_all_improve=True,
        null_delta=0.009,
        null_pass=True,
        ablation_delta=-0.008,
        ablation_pass=True,
        calibration_ok=True,
        clv=0.55,
        clv_pass=True,
        p_value=0.003,
        fdr_pass=True,
        metrics={"regime_buckets": regime_buckets},
    )


def _make_variance_result(signal_name: str = "demo_variance") -> GateResult:
    return GateResult(
        signal_name=signal_name,
        verdict=Verdict.VARIANCE_ONLY,
        reason="improves interval, not point",
        wf_folds=[0.001, 0.002, -0.001, 0.003],
        wf_all_improve=False,
        calibration_ok=True,
        metrics={},
    )


def _mock_train_fn(target: str, device: str = "cpu",
                   version_tag: str = "v_test") -> Dict[str, Any]:
    return {"status": "ok", "holdout_mae": 4.2, "version_tag": version_tag}


@pytest.fixture
def tmp_store(tmp_path: Path) -> PointInTimeStore:
    return PointInTimeStore(store_dir=tmp_path / "store", autoload=False)


@pytest.fixture
def tmp_models_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect all wiring registry JSON writes to a temp directory."""
    import src.loop.wiring as wiring
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setattr(wiring, "_MODELS_DIR", models)
    monkeypatch.setattr(wiring, "_FEATURE_REGISTRY_PATH", models / "loop_feature_registry.json")
    monkeypatch.setattr(wiring, "_REGIME_GATE_PATH", models / "loop_regime_gates.json")
    monkeypatch.setattr(wiring, "_VARIANCE_REGISTRY_PATH", models / "loop_variance_signals.json")
    return models


# ---------------------------------------------------------------------------
# register_feature
# ---------------------------------------------------------------------------

class TestRegisterFeature:
    def test_registers_new_feature(self, tmp_models_dir):
        from src.loop.wiring import register_feature
        signal = _DemoSignal()
        names = register_feature(signal)
        assert names == ["demo_signal"]
        reg_path = tmp_models_dir / "loop_feature_registry.json"
        assert reg_path.exists()
        reg = json.loads(reg_path.read_text())
        assert "demo_signal" in reg["features"]
        assert reg["features"]["demo_signal"]["target"] == "pts"

    def test_idempotent_no_duplicate(self, tmp_models_dir):
        from src.loop.wiring import register_feature
        signal = _DemoSignal()
        register_feature(signal)
        register_feature(signal)  # second call
        reg = json.loads((tmp_models_dir / "loop_feature_registry.json").read_text())
        # Still just one entry
        assert len([k for k in reg["features"] if k == "demo_signal"]) == 1

    def test_dict_signal_registers_sub_features(self, tmp_models_dir):
        from src.loop.wiring import register_feature

        class _DictSig(_DemoSignal):
            name = "dict_sig"
            emits = ["alpha", "beta"]

        s = _DictSig()
        names = register_feature(s)
        assert set(names) == {"dict_sig__alpha", "dict_sig__beta"}
        reg = json.loads((tmp_models_dir / "loop_feature_registry.json").read_text())
        assert "dict_sig__alpha" in reg["features"]
        assert "dict_sig__beta" in reg["features"]


# ---------------------------------------------------------------------------
# register_regime_gate
# ---------------------------------------------------------------------------

class TestRegisterRegimeGate:
    def test_writes_gate_entry(self, tmp_models_dir):
        from src.loop.wiring import register_regime_gate
        signal = _DemoSignal()
        result = _make_ship_result()
        buckets = register_regime_gate(signal, result, "v_test_001")
        assert len(buckets) == 1
        gate_path = tmp_models_dir / "loop_regime_gates.json"
        assert gate_path.exists()
        gates = json.loads(gate_path.read_text())
        assert "demo_signal:v_test_001" in gates["gates"]
        entry = gates["gates"]["demo_signal:v_test_001"]
        assert entry["verdict"] == "SHIP"
        assert entry["signal"] == "demo_signal"

    def test_empty_buckets(self, tmp_models_dir):
        from src.loop.wiring import register_regime_gate
        signal = _DemoSignal()
        result = _make_ship_result(buckets=[], use_default_buckets=False)
        buckets = register_regime_gate(signal, result, "v_no_buckets")
        assert buckets == []


# ---------------------------------------------------------------------------
# write_back_atlas_field
# ---------------------------------------------------------------------------

class TestWriteBackAtlasField:
    def test_sentinel_when_no_learned_values(self, tmp_store):
        from src.loop.wiring import write_back_atlas_field
        signal = _DemoSignal(store=tmp_store)
        result = write_back_atlas_field(signal, tmp_store)
        assert result is True
        # wiring writes with as_of = date.today(); read with same anchor.
        today = _dt.date.today().isoformat()
        val = tmp_store.read_signal_field("signal", "demo_signal", "demo_signal", today)
        assert val is not None
        assert val["signal_name"] == "demo_signal"

    def test_writes_per_entity_learned_values(self, tmp_store):
        from src.loop.wiring import write_back_atlas_field
        signal = _DemoSignalWithLearned(store=tmp_store)
        result = write_back_atlas_field(signal, tmp_store)
        assert result is True
        # as_of matches wiring.write_back_atlas_field (date.today())
        today = _dt.date.today().isoformat()
        v1 = tmp_store.read_signal_field("player", "1628983", "demo_learned", today)
        assert v1 == 0.12
        v2 = tmp_store.read_signal_field("player", "203954", "demo_learned", today)
        assert v2 == -0.05

    def test_dry_run_does_not_write(self, tmp_store):
        from src.loop.wiring import write_back_atlas_field
        signal = _DemoSignalWithLearned(store=tmp_store)
        result = write_back_atlas_field(signal, tmp_store, dry_run=True)
        assert result is True
        # Nothing should be persisted in store
        today = _dt.date.today().isoformat()
        v1 = tmp_store.read_signal_field("player", "1628983", "demo_learned", today)
        assert v1 is None


# ---------------------------------------------------------------------------
# wire_variance_signal
# ---------------------------------------------------------------------------

class TestWireVarianceSignal:
    def test_wires_variance_signal(self, tmp_store, tmp_models_dir):
        from src.loop.wiring import wire_variance_signal
        signal = _VarianceSignal(store=tmp_store)
        result = _make_variance_result()
        wiring_result = wire_variance_signal(signal, result, store=tmp_store)
        assert wiring_result.ok is True
        assert wiring_result.retrained == []
        assert wiring_result.features_added == ["demo_variance"]
        reg = json.loads((tmp_models_dir / "loop_variance_signals.json").read_text())
        assert "demo_variance" in reg["variance_signals"]

    def test_rejects_non_variance_verdict(self, tmp_store, tmp_models_dir):
        from src.loop.wiring import wire_variance_signal
        signal = _VarianceSignal(store=tmp_store)
        result = _make_ship_result()  # SHIP, not VARIANCE_ONLY
        wiring_result = wire_variance_signal(signal, result, store=tmp_store)
        assert wiring_result.ok is False
        assert "VARIANCE_ONLY" in wiring_result.reason

    def test_dry_run_does_not_write_registry(self, tmp_store, tmp_models_dir):
        from src.loop.wiring import wire_variance_signal
        signal = _VarianceSignal(store=tmp_store)
        result = _make_variance_result()
        wiring_result = wire_variance_signal(signal, result, store=tmp_store, dry_run=True)
        assert wiring_result.ok is True
        # Registry should NOT be written in dry_run
        reg_path = tmp_models_dir / "loop_variance_signals.json"
        assert not reg_path.exists()


# ---------------------------------------------------------------------------
# ship_signal (integration / mocked train)
# ---------------------------------------------------------------------------

class TestShipSignal:
    def test_ship_signal_full_flow_mocked(self, tmp_store, tmp_models_dir):
        from src.loop.wiring import ship_signal
        signal = _DemoSignal(store=tmp_store)
        result = _make_ship_result()
        wr = ship_signal(signal, result, store=tmp_store, train_fn=_mock_train_fn)
        assert wr.ok is True
        assert "demo_signal" in wr.features_added
        assert wr.version_tag is not None
        assert wr.wrote_back is True

    def test_ship_signal_dry_run_no_side_effects(self, tmp_store, tmp_models_dir):
        from src.loop.wiring import ship_signal
        signal = _DemoSignal(store=tmp_store)
        result = _make_ship_result()
        wr = ship_signal(signal, result, store=tmp_store,
                         train_fn=_mock_train_fn, dry_run=True)
        assert wr.ok is True
        # Nothing persisted
        assert not (tmp_models_dir / "loop_feature_registry.json").exists()
        assert not (tmp_models_dir / "loop_regime_gates.json").exists()

    def test_ship_signal_rejects_non_ship_verdict(self, tmp_store, tmp_models_dir):
        from src.loop.wiring import ship_signal
        signal = _DemoSignal(store=tmp_store)
        result = GateResult(
            signal_name="demo_signal",
            verdict=Verdict.REJECT,
            reason="failed null control",
        )
        wr = ship_signal(signal, result, store=tmp_store)
        assert wr.ok is False
        assert "REJECT" in wr.reason

    def test_ship_signal_idempotent_second_call(self, tmp_store, tmp_models_dir):
        """Second ship_signal call on the same day returns cached result."""
        from src.loop.wiring import ship_signal, _version_tag
        signal = _DemoSignal(store=tmp_store)
        result = _make_ship_result()
        wr1 = ship_signal(signal, result, store=tmp_store, train_fn=_mock_train_fn)
        assert wr1.ok is True
        vtag1 = wr1.version_tag
        wr2 = ship_signal(signal, result, store=tmp_store, train_fn=_mock_train_fn)
        assert wr2.ok is True
        assert wr2.version_tag == vtag1
        assert "idempotent" in wr2.reason

    def test_ship_signal_variance_only_delegates(self, tmp_store, tmp_models_dir):
        """ship_signal with VARIANCE_ONLY verdict delegates to wire_variance_signal."""
        from src.loop.wiring import ship_signal
        signal = _VarianceSignal(store=tmp_store)
        result = _make_variance_result()
        wr = ship_signal(signal, result, store=tmp_store)
        assert wr.ok is True
        assert wr.retrained == []

    def test_write_back_roundtrip(self, tmp_store, tmp_models_dir):
        """Learned per-entity values written back are readable from the store."""
        from src.loop.wiring import ship_signal
        signal = _DemoSignalWithLearned(store=tmp_store)
        # _DemoSignalWithLearned already sets name="demo_learned"; don't shadow
        result = _make_ship_result(signal_name="demo_learned")
        ship_signal(signal, result, store=tmp_store, train_fn=_mock_train_fn)
        # as_of matches wiring.write_back_atlas_field (date.today())
        today = _dt.date.today().isoformat()
        v = tmp_store.read_signal_field("player", "1628983", "demo_learned", today)
        assert v == 0.12


# ---------------------------------------------------------------------------
# retrain_model (unit -- noop surface path, no actual training)
# ---------------------------------------------------------------------------

class TestRetrainModel:
    def test_injected_train_fn(self, tmp_models_dir):
        from src.loop.wiring import retrain_model
        result = retrain_model("pts", device="cpu", train_fn=_mock_train_fn)
        assert result["version_tag"].startswith("loop_pts_")
        assert "injected:pts" in result["surface"]

    def test_unknown_target_returns_noop(self, tmp_models_dir):
        from src.loop.wiring import retrain_model
        result = retrain_model("sigma", device="cpu", train_fn=None)
        assert "noop" in result["surface"]
        assert result["model_path"] == ""
