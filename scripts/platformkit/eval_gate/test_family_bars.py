"""S14 -- both bars, or it is not AHEAD.

Planted-null design follows eval_gate/null_ship_calibration.py: N independent,
outcome-blind candidates, seeded, none dropped or re-labelled afterwards. The
p-value of a null hypothesis is uniform on [0,1], and `family_bars` consumes
p-values rather than data, so the plant happens at the p-value layer.

Run ONLY this file: python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.eval_gate.family_bars import (
    SPEC_PATH, dual_bar_verdict, git_blob_id, load_families, render_bars)

PLANTED_NULLS = 200
SEED = 20260903
MAX_DISCOVERIES = 10


def planted_nulls(n: int = PLANTED_NULLS, seed: int = SEED) -> list:
    """n independent null p-values -- uniform by construction, nothing conditioned on."""
    return [float(p) for p in np.random.default_rng(seed).uniform(0.0, 1.0, size=n)]


def test_two_hundred_planted_nulls_stay_under_the_bar():
    """The whole denominator is scored: all 200 are in, none is re-seeded or dropped."""
    nulls = planted_nulls()
    assert len(nulls) == PLANTED_NULLS
    verdicts = [dual_bar_verdict(p, k_global=1, family_p_values=nulls) for p in nulls]
    ahead = sum(v["verdict"] == "AHEAD" for v in verdicts)
    family_hits = verdicts[0]["family_discoveries"]
    assert family_hits <= MAX_DISCOVERIES, "BH discoveries on an all-null family: %d" % family_hits
    assert ahead <= MAX_DISCOVERIES
    assert len(verdicts) == PLANTED_NULLS


def test_planted_nulls_split_across_families_stay_under_the_bar():
    """Same 200 nulls, partitioned into 20 families of 10; discoveries are summed."""
    nulls = planted_nulls()
    families = [nulls[i:i + 10] for i in range(0, PLANTED_NULLS, 10)]
    assert sum(len(f) for f in families) == PLANTED_NULLS
    hits = sum(dual_bar_verdict(f[0], 1, f)["family_discoveries"] for f in families)
    assert hits <= MAX_DISCOVERIES


def test_planted_true_effect_passes_both_bars():
    effect = 1e-9
    family = [effect] + planted_nulls(19)
    result = dual_bar_verdict(effect, k_global=100, family_p_values=family)
    assert result["global_pass"] and result["family_pass"]
    assert result["verdict"] == "AHEAD" and result["blocked_by"] == ()


def test_bh_pass_but_global_fail_is_not_ahead():
    """The loosening cannot ship a hypothesis on its own: bar 1 still blocks."""
    candidate = 0.004
    family = [candidate] + [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.91, 0.92, 0.93]
    result = dual_bar_verdict(candidate, k_global=1000, family_p_values=family)
    assert result["family_pass"] is True
    assert result["global_pass"] is False and result["deflated_p"] == 1.0
    assert result["verdict"] == "NOT AHEAD" and result["blocked_by"] == ("global",)


def test_global_pass_but_bh_fail_is_not_ahead():
    candidate = 0.03
    family = [candidate] + [0.9] * 40
    result = dual_bar_verdict(candidate, k_global=1, family_p_values=family)
    assert result["global_pass"] is True and result["family_pass"] is False
    assert result["blocked_by"] == ("family",)


def test_hypothesis_must_be_priced_inside_its_own_family():
    with pytest.raises(ValueError, match="OWN frozen family"):
        dual_bar_verdict(0.01, 1, [0.2, 0.3, 0.4])


def test_unknown_family_name_is_refused():
    with pytest.raises(KeyError, match="invented after the fact"):
        dual_bar_verdict(0.01, 1, [0.01, 0.9], family="nba_wishful_thinking")


def test_frozen_spec_loads_and_pins_itself_into_every_verdict():
    spec = load_families()
    assert spec.spec_version == "s14-families-v1"
    assert spec.q_within_family == 0.05
    assert len(spec.families) == 37
    assert sum(f.features for f in spec.families) == 396
    assert sum(f.hypotheses for f in spec.families) == 3564
    assert all(f.hypotheses == f.features * 9 for f in spec.families)
    assert len({f.name for f in spec.families}) == len(spec.families)
    assert spec.prereg_sha256 == git_blob_id(SPEC_PATH)
    result = dual_bar_verdict(0.001, 1, [0.001, 0.9], family="nba_gate")
    assert result["families_spec_sha"] == spec.prereg_sha256
    assert result["n_families"] == 37
    assert "GLOBAL" in render_bars(result) and "FAMILY" in render_bars(result)


def test_verdict_reads_no_ledger_and_no_stored_result(monkeypatch):
    """Condition (iii): a past verdict cannot be re-scored because nothing is read."""
    import builtins

    real_open = builtins.open
    opened = []

    def watched(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watched)
    load_families.cache_clear()
    dual_bar_verdict(0.001, 5, [0.001, 0.5, 0.9], family="nba_gate")
    assert not [p for p in opened if "backtest_fwer" in p or "hypotheses.sqlite" in p], opened
