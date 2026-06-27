"""Per-file test for scripts.platformkit.ingame.gate_run_nba_possession (no network).

Synthetic possession-states corpora (frozen base schema + additive detail cols) so the
run is fast + deterministic. Verifies:
  * the PLANTED-NULL pure-noise column does NOT replicate through the IDENTICAL gate
    (proves the gate can FAIL a signal -> null_rejects True);
  * the layer verdict + per-column verdicts have the expected shape, BOTH directions,
    and a clustered-DM p in each non-empty direction;
  * INSUFFICIENT_DATA is reported honestly when a corpus parquet is absent;
  * the serialized verdict JSON carries vs_close=UNPROVEN, no_dollar_field, and
    wired_into_repricer False -- i.e. nothing rejected is force-fed and there is no $.

Calibration only; no $ / edge asserted anywhere. ASCII-only.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit.ingame import gate_run_nba_possession as GR
from scripts.platformkit.ingame import possession_layer_gate_nba as PG


def _corpus(n_games=160, ticks=18, seed=0):
    """Synthetic as-of states: frozen base (state_diff/frac_elapsed/outcome) + the 4
    additive possession detail cols. Detail cols are noisy per-game latents that do NOT
    cleanly determine the outcome -> the honest expectation is REJECT (like real data)."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        true_p = rng.uniform(0.2, 0.8)
        win = None
        for t in range(ticks):
            frac = (t + 0.5) / ticks
            margin = rng.normal((true_p - 0.5) * 20, 6)
            if win is None:
                lin = (true_p - 0.5) * 3
                win = int(rng.uniform() < 1.0 / (1.0 + np.exp(-lin)))
            rows.append({
                "game_id": f"g{g}", "asof_idx": t,
                "state_diff": float(margin), "frac_elapsed": float(frac),
                "outcome": int(win),
                "possessions_elapsed": float(t * 2 + rng.normal(0, 1)),
                "pace_so_far": float(0.4 + rng.normal(0, 0.05)),
                "run_diff": float(rng.normal(0, 2)),
                "poss_since_lead_change": float(abs(rng.normal(0, 3))),
            })
    return pd.DataFrame(rows)


def _patch_corpora(monkeypatch, a, b):
    def _load(season):
        return a if season.endswith("a") or season == "2024_25" else b
    monkeypatch.setattr(PG, "load_corpus", _load)


def test_planted_null_does_not_replicate(monkeypatch, tmp_path):
    a, b = _corpus(seed=1), _corpus(seed=2)
    _patch_corpora(monkeypatch, a, b)
    monkeypatch.setattr(GR, "_OUT", tmp_path / "v.json")
    res = GR.run("2024_25", "2025_26", min_ticks=50)
    # gate CAN fail a noise column: the null must be in a rejecting state.
    assert res["null"]["verdict"] in GR._REJECTING
    assert res["null_rejects"] is True
    # a noise null is never a clean cross-corpus REPLICATED ship.
    assert res["null"]["verdict"] != "REPLICATED"


def test_verdict_shape_both_dirs_and_dm(monkeypatch, tmp_path):
    a, b = _corpus(seed=3), _corpus(seed=4)
    _patch_corpora(monkeypatch, a, b)
    monkeypatch.setattr(GR, "_OUT", tmp_path / "v.json")
    res = GR.run("2024_25", "2025_26", min_ticks=50)
    assert res["verdict"] in ("REPLICATED", "REJECT", "NOT_TESTABLE")
    assert set(PG.DETAIL_COLS).issubset(res["columns"].keys())
    for col, c in res["columns"].items():
        assert c["verdict"] in ("REPLICATED", "PARTIAL", "REJECT",
                                "INVALID_BASE", "INSUFFICIENT_DATA")
        # both cross-corpus directions present; each non-empty dir carries a DM p.
        assert "a_to_b" in c and "b_to_a" in c
        for d in (c["a_to_b"], c["b_to_a"]):
            if d:
                assert "dm_p" in d and "brier_base" in d


def test_insufficient_data_when_corpus_absent(monkeypatch, tmp_path):
    def _load(season):
        raise FileNotFoundError(f"missing {season}")
    monkeypatch.setattr(PG, "load_corpus", _load)
    monkeypatch.setattr(GR, "_OUT", tmp_path / "v.json")
    res = GR.run("2024_25", "2025_26")
    assert res["verdict"] == "INSUFFICIENT_DATA"
    assert res["n_corpora"] == 0


def test_written_json_no_dollar_and_unproven(monkeypatch, tmp_path):
    a, b = _corpus(seed=5), _corpus(seed=6)
    _patch_corpora(monkeypatch, a, b)
    out = tmp_path / "nba_possession_ingame_gate.json"
    monkeypatch.setattr(GR, "_OUT", out)
    GR.run("2024_25", "2025_26", min_ticks=50)
    assert out.exists()
    blob = json.loads(out.read_text(encoding="ascii"))
    assert blob["no_dollar_field"] is True
    assert blob["wired_into_repricer"] is False     # nothing rejected force-fed
    assert "UNPROVEN" in blob["vs_close"]
    raw = out.read_text(encoding="ascii").lower()
    assert "roi" not in raw and "$" not in raw      # NO dollar/edge field anywhere
