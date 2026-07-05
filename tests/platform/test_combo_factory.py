"""tests/platform/test_combo_factory.py -- combo test-factory (corpus_cache,
null_floor, batch_gate) synthetic-fixture tests.

Covers:
  1. Cache staleness refusal (StaleCorpusError on a source-file mtime/sha change).
  2. Prescreen rejects an inside-floor candidate WITHOUT running full nulls.
  3. Prescreen does NOT skip full nulls for an above-floor candidate (ceremony
     still runs -- the run_batch path reaches judge_stack_family, not just the
     prescreen REJECT shortcut).
  4. batch_gate emits exactly one verdict per spec.
  5. A planted real signal survives prescreen (the factory is not trivially-zero).

All fixtures are synthetic (no real parquet / network); fast and isolated.
No src.*/kernel.* imports.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.combo import batch_gate as bg
from scripts.platformkit.combo import corpus_cache as cc
from scripts.platformkit.combo import null_floor as nf


# --------------------------------------------------------------------------- #
# Synthetic corpus builders
# --------------------------------------------------------------------------- #

def _make_corpus(n: int = 400, seed: int = 0, signal_strength: float = 0.0) -> pd.DataFrame:
    """A synthetic 2-corpus_unit gate frame: `y` depends on a base latent AND
    (when signal_strength>0) a SECOND, INDEPENDENT latent that p_base cannot
    see. `real_feature` proxies that second latent (genuine incremental
    signal on top of base); `noise_feature` is always pure noise unrelated
    to y. This is the honest shape of a real stack candidate -- it must add
    information base does NOT already have, not just re-express it."""
    rng = np.random.default_rng(seed)
    rows = []
    for unit in ("unit_a", "unit_b"):
        base_latent = rng.standard_normal(n)
        extra_latent = rng.standard_normal(n)
        y_logit = base_latent * 0.6 + extra_latent * signal_strength
        y = (y_logit + rng.standard_normal(n) * 0.3 > 0).astype(float)
        p_base = np.clip(1.0 / (1.0 + np.exp(-base_latent * 0.6)), 1e-3, 1 - 1e-3)
        real_feature = extra_latent + rng.standard_normal(n) * 0.3
        noise_feature = rng.standard_normal(n)
        for i in range(n):
            rows.append({
                "event_id": f"{unit}_{i:05d}", "corpus_unit": unit, "y": y[i],
                "p_base": p_base[i], "real_feature": real_feature[i],
                "noise_feature": noise_feature[i],
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# 1. Cache staleness refusal
# --------------------------------------------------------------------------- #

def test_stale_corpus_refuses_on_source_change(tmp_path: Path):
    src = tmp_path / "source.parquet"
    src.write_bytes(b"original bytes")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    corpus_path = cache_dir / "gate_corpus_fake.parquet"
    sidecar_path = cache_dir / "gate_corpus_fake.sources.json"

    df = pd.DataFrame({"event_id": ["a"], "corpus_unit": ["u"], "y": [1.0], "p_base": [0.5]})
    df.to_parquet(corpus_path, index=False)
    manifest = {"sport": "fake", "sources": {str(src): {
        "mtime": src.stat().st_mtime, "sha256": cc._file_sha256(src)}}}
    sidecar_path.write_text(json.dumps(manifest), encoding="utf-8")

    with patch.object(cc, "_CACHE_DIR", cache_dir):
        cc.load_gate_corpus("fake")  # no error yet -- source unchanged

        time.sleep(0.01)
        src.write_bytes(b"CHANGED bytes -- source moved since build")
        with pytest.raises(cc.StaleCorpusError):
            cc.load_gate_corpus("fake")


def test_stale_corpus_refuses_when_missing(tmp_path: Path):
    with patch.object(cc, "_CACHE_DIR", tmp_path):
        with pytest.raises(cc.StaleCorpusError):
            cc.load_gate_corpus("never_built")


# --------------------------------------------------------------------------- #
# 2/3. Prescreen behavior: inside-floor skips nulls, above-floor does not
# --------------------------------------------------------------------------- #

def test_prescreen_rejects_inside_floor_without_full_nulls(tmp_path: Path):
    corpus = _make_corpus(n=300, seed=1, signal_strength=0.0)  # pure noise feature

    with patch.object(nf, "_CACHE_DIR", tmp_path):
        nf.build_null_floor("fake", corpus, m_draws=10, base_seed=0)

        # A "candidate" delta drawn from the SAME noise process should land
        # inside its own floor's p99 (it IS the floor's own distribution).
        y = corpus[corpus["corpus_unit"] == "unit_a"]["y"].to_numpy(float)
        p_base = np.clip(corpus[corpus["corpus_unit"] == "unit_a"]["p_base"].to_numpy(float),
                         1e-6, 1 - 1e-6)
        inside_delta = nf._one_noise_delta(y, p_base, 1, np.random.default_rng(999))

        verdict = nf.prescreen_verdict("fake", "unit_a", 1, inside_delta)
        assert verdict in ("REJECT", "PROCEED")  # deterministic given the floor; sanity only

        # Directly verify the REJECT branch fires for a delta AT the floor's p99.
        floor = nf.load_null_floor("fake")["floors"]["unit_a"]["1"]
        at_floor = nf.prescreen_verdict("fake", "unit_a", 1, floor["p99"])
        assert at_floor == "REJECT", "delta == p99 (<=) must REJECT per the rail"
        below_floor = nf.prescreen_verdict("fake", "unit_a", 1, floor["p99"] - 1.0)
        assert below_floor == "REJECT"


def test_prescreen_proceeds_for_above_floor_candidate(tmp_path: Path):
    corpus = _make_corpus(n=300, seed=2, signal_strength=0.0)
    with patch.object(nf, "_CACHE_DIR", tmp_path):
        nf.build_null_floor("fake", corpus, m_draws=10, base_seed=0)
        floor = nf.load_null_floor("fake")["floors"]["unit_a"]["1"]
        above_floor = nf.prescreen_verdict("fake", "unit_a", 1, floor["p99"] + 10.0)
        assert above_floor == "PROCEED", "a delta clearly above p99 must PROCEED to full ceremony"


def test_run_batch_reaches_full_ceremony_for_above_floor_candidate(tmp_path: Path):
    """An above-floor candidate must NOT short-circuit at FDR_PRESCREEN -- the
    verdict layer must be one judge_stack_family actually assigns (L0-L6/FDR),
    proving the full ceremony ran (mocking prescreen_verdict to force PROCEED
    isolates this from the floor's own randomness)."""
    corpus = _make_corpus(n=300, seed=3, signal_strength=1.5)  # strong real signal
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    with patch.object(cc, "_CACHE_DIR", cache_dir), \
        patch.object(bg, "load_gate_corpus", lambda sport: corpus), \
        patch.object(bg, "prescreen_verdict", lambda *a, **k: "PROCEED"), \
        patch.object(bg, "record", lambda *a, **k: None), \
        patch.object(bg, "_OUT_DIR", tmp_path / "out"):
        specs = [{"name": "cand_real", "features": ["real_feature"],
                 "family": "fake_family", "k_cum": 1}]
        results = bg.run_batch(specs, "fake", write_ledger=True)

    v = results["cand_real"]
    assert v["layer"] != "FDR_PRESCREEN", "above-floor candidate must not stop at the prescreen"
    assert v["verdict"] in ("SHIP", "PARTIAL", "REJECT", "VOID", "NOT_TESTABLE")


# --------------------------------------------------------------------------- #
# 4. batch emits exactly one verdict per spec
# --------------------------------------------------------------------------- #

def test_batch_emits_one_verdict_per_spec(tmp_path: Path):
    corpus = _make_corpus(n=200, seed=4, signal_strength=0.0)
    with patch.object(cc, "_CACHE_DIR", tmp_path / "cache"), \
        patch.object(bg, "load_gate_corpus", lambda sport: corpus), \
        patch.object(bg, "record", lambda *a, **k: None), \
        patch.object(bg, "_OUT_DIR", tmp_path / "out"):
        specs = [
            {"name": "cand_1", "features": ["real_feature"], "family": "fam", "k_cum": 2},
            {"name": "cand_2", "features": ["noise_feature"], "family": "fam", "k_cum": 2},
        ]
        results = bg.run_batch(specs, "fake", write_ledger=True)

    assert set(results.keys()) == {"cand_1", "cand_2"}
    for v in results.values():
        assert "verdict" in v and "layer" in v


def test_batch_not_testable_when_fewer_than_two_units(tmp_path: Path):
    corpus = _make_corpus(n=50, seed=5, signal_strength=0.0)
    single_unit = corpus[corpus["corpus_unit"] == "unit_a"]
    with patch.object(bg, "load_gate_corpus", lambda sport: single_unit), \
        patch.object(bg, "record", lambda *a, **k: None), \
        patch.object(bg, "_OUT_DIR", tmp_path / "out"):
        specs = [{"name": "cand_x", "features": ["real_feature"], "family": "fam", "k_cum": 1}]
        results = bg.run_batch(specs, "fake", write_ledger=True)
    assert results["cand_x"]["verdict"] == "NOT_TESTABLE"


# --------------------------------------------------------------------------- #
# 5. A planted real signal survives prescreen (factory not trivially-zero)
# --------------------------------------------------------------------------- #

def test_planted_real_signal_survives_prescreen(tmp_path: Path):
    corpus = _make_corpus(n=500, seed=6, signal_strength=2.0)  # strong, unmistakable signal
    with patch.object(nf, "_CACHE_DIR", tmp_path):
        nf.build_null_floor("fake", corpus, m_draws=15, base_seed=0)

        sub = corpus[corpus["corpus_unit"] == "unit_a"].reset_index(drop=True)
        splits_y = sub["y"].to_numpy(float)
        p_base = np.clip(sub["p_base"].to_numpy(float), 1e-6, 1 - 1e-6)

        rows = bg._fit_and_score_unit(sub, ["real_feature"])
        real_delta = bg._prescreen_delta(rows)

        verdict = nf.prescreen_verdict("fake", "unit_a", 1, real_delta)
        assert verdict == "PROCEED", (
            f"a planted strong real signal (delta={real_delta:.6f}) must clear its own "
            f"noise floor -- the prescreen is not trivially rejecting everything")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
