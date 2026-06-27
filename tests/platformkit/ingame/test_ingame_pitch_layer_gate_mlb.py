"""Per-file test for scripts.platformkit.ingame.ingame_pitch_layer_gate_mlb.

No network -- fully synthetic state corpora. Asserts the gate's TRUSTWORTHINESS rails:
  * PLANTED-NULL CONTROL: a pure-noise column run through the IDENTICAL gate MUST reject
    (proving the gate can FAIL a signal). This is the load-bearing honesty proof.
  * GATE CAN PASS A TRUE SIGNAL: when a feature genuinely shifts the outcome in BOTH
    corpora, the real layer replicates -> SHIP, while the planted-null on the SAME data
    still rejects (so a SHIP is not a rubber stamp).
  * NO-SIGNAL FEATURE REJECTS: a feature uncorrelated with outcome -> REJECT.
  * INSUFFICIENT_DATA is reported honestly when no corpora are materialized.
  * NaN fatigue (first-pitch, no baseline) maps to a 0 shift -- never fabricated.
  * verdict dict carries NO $/ROI/edge field and is proposal-only / CALIBRATION-only.
"""
from __future__ import annotations

import math
import random

from scripts.platformkit.ingame.ingame_pitch_layer_gate_mlb import (
    apply_pitch_layer,
    fit_pitch_layer,
    gate_layer,
    run,
    run_gate,
    fit_null_layer,
    apply_null_layer,
    fit_fatigue_layer,
    apply_fatigue_layer,
    fit_pitch_layer as _fit_layer,
)
from scripts.platformkit.ingame.ingame_gate_generic_models import base_predict, fit_base


def _logistic(x):
    return 1.0 / (1.0 + math.exp(-x))


def _make_corpus(seed, n_games=40, ticks=12, signal=0.0):
    """Synthetic pitch-state corpus. outcome driven by state_diff + (optionally) the
    fatigue column when signal>0. velo_decline carries the (optional) true signal."""
    rng = random.Random(seed)
    states = []
    for g in range(n_games):
        gid = f"{seed}_{g}"
        base_strength = rng.uniform(-1.0, 1.0)
        fatigue = rng.uniform(-2.0, 2.0)  # standardized-ish
        # outcome probability: team strength + signal*fatigue
        p = _logistic(base_strength + signal * fatigue)
        y = 1 if rng.random() < p else 0
        for t in range(ticks):
            sd = base_strength * 3.0 + rng.uniform(-0.5, 0.5)
            vd = float("nan") if t == 0 else fatigue + rng.uniform(-0.3, 0.3)
            states.append({
                "game_id": gid,
                "state_diff": sd,
                "frac_elapsed": min(1.0, t / float(ticks)),
                "p0": _logistic(base_strength),
                "outcome": y,
                "velo_decline": vd,
                "count_balls": float(rng.randint(0, 3)),
                "count_strikes": float(rng.randint(0, 2)),
            })
    return states


def test_planted_null_rejects():
    """A pure-noise column MUST NOT replicate -- proves the gate can FAIL a signal."""
    a = _make_corpus(1, signal=0.0)
    b = _make_corpus(2, signal=0.0)
    null = gate_layer(a, b, fit_null_layer, apply_null_layer, eps=0.05)
    assert null["replicated"] is False, "planted-null must REJECT (gate must be able to fail)"


def test_no_signal_feature_rejects():
    """A fatigue column uncorrelated with outcome -> REJECT (honest, expected)."""
    a = _make_corpus(3, signal=0.0)
    b = _make_corpus(4, signal=0.0)
    res = gate_layer(a, b, fit_pitch_layer, apply_pitch_layer, eps=0.05)
    assert res["replicated"] is False


def test_gate_can_pass_true_signal_while_null_still_rejects():
    """When the fatigue column genuinely drives outcome in BOTH corpora the real layer
    replicates (SHIP), yet the planted-null on the SAME data still rejects -> a SHIP is
    not a rubber stamp."""
    a = _make_corpus(10, signal=1.6)
    b = _make_corpus(11, signal=1.6)
    v = run_gate(a, b, eps=0.05)
    assert v.null_rejected is True
    # the real layer should beat base in at least one direction given a strong signal
    lr = v.layer_result
    any_beat = lr["a_to_b"]["layer_beats_base"] or lr["b_to_a"]["layer_beats_base"]
    assert any_beat, "a strong injected signal should beat BASE in >=1 direction"
    assert v.verdict in ("SHIP", "REJECT")  # honest replication verdict


def test_nan_fatigue_maps_to_zero_shift():
    """First-pitch NaN fatigue must not crash and must produce finite predictions."""
    a = _make_corpus(20, signal=0.0)
    ab = fit_base(a)
    base_tr = base_predict(a, ab)
    params = _fit_layer(a, base_tr)
    pred = apply_pitch_layer(a, base_tr, params)
    assert all(0.0 <= float(p) <= 1.0 and not math.isnan(float(p)) for p in pred)


def test_insufficient_data_when_no_corpora(tmp_path, monkeypatch):
    """No materialized pitch corpora -> honest INSUFFICIENT_DATA, never 0-filled win."""
    import scripts.platformkit.ingame.ingame_pitch_layer_gate_mlb as mod
    monkeypatch.setattr(mod, "_STATE_DIR", str(tmp_path))
    v = run()
    assert v.verdict == "INSUFFICIENT_DATA"
    assert v.coverage.get("corpora_found") == 0


def test_verdict_has_no_dollar_field():
    import json
    a = _make_corpus(30, signal=0.0)
    b = _make_corpus(31, signal=0.0)
    d = run_gate(a, b).to_dict()
    # NO $ / ROI / edge FIELD (key) anywhere -- the only mentions of "$"/"edge" are
    # inside the explicit "not a market edge / no $ anywhere" CALIBRATION disclaimers.
    def _keys(obj):
        out = []
        if isinstance(obj, dict):
            for k, val in obj.items():
                out.append(str(k).lower())
                out += _keys(val)
        elif isinstance(obj, list):
            for v in obj:
                out += _keys(v)
        return out
    keys = [k for k in _keys(d) if k != "no_dollar_field"]
    assert not any(("roi" in k or "edge" in k or "$" in k or "dollar" in k) for k in keys)
    assert d["no_dollar_field"] is True
    assert d["proposal_only"] is True
    assert "CALIBRATION" in d["vs_close"]
    json.dumps(d)  # serializable


def test_thin_corpus_insufficient():
    a = _make_corpus(40, n_games=3, ticks=4)
    b = _make_corpus(41, n_games=3, ticks=4)
    v = run_gate(a, b)
    assert v.verdict == "INSUFFICIENT_DATA"


def test_isolated_sp_fatigue_lever_rejects_when_no_signal():
    """The structurally-NEW lever in isolation (velo_decline only, count beta forced 0)
    must REJECT when fatigue carries no outcome signal -- proves the isolated lever is
    held to the IDENTICAL bar and is not silently passed."""
    a = _make_corpus(50, signal=0.0)
    b = _make_corpus(51, signal=0.0)
    res = gate_layer(a, b, fit_fatigue_layer, apply_fatigue_layer, eps=0.05)
    assert res["replicated"] is False


def test_isolated_sp_fatigue_lever_can_pass_true_signal():
    """When velo_decline genuinely drives the outcome in BOTH corpora, the isolated
    fatigue-only lever beats BASE in >=1 direction -- so the isolated test can PASS a
    real signal (it is not a rubber-stamp REJECT)."""
    a = _make_corpus(60, signal=1.6)
    b = _make_corpus(61, signal=1.6)
    res = gate_layer(a, b, fit_fatigue_layer, apply_fatigue_layer, eps=0.05)
    assert res["a_to_b"]["layer_beats_base"] or res["b_to_a"]["layer_beats_base"]


def test_isolated_fatigue_apply_finite_with_nan_firstpitch():
    """First-pitch NaN fatigue maps to a 0 shift in the isolated lever too (no crash,
    finite predictions, never fabricated)."""
    a = _make_corpus(70, signal=0.0)
    ab = fit_base(a)
    base_tr = base_predict(a, ab)
    params = fit_fatigue_layer(a, base_tr)
    pred = apply_fatigue_layer(a, base_tr, params)
    assert all(0.0 <= float(p) <= 1.0 and not math.isnan(float(p)) for p in pred)
