"""S14 -- both bars, or it is not AHEAD.

Planted-null design follows eval_gate/null_ship_calibration.py: N independent,
outcome-blind candidates, seeded, none dropped or re-labelled afterwards. The
p-value of a null hypothesis is uniform on [0,1], and `family_bars` consumes
p-values rather than data, so the plant happens at the p-value layer.

Run ONLY this file: python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.eval_gate.family_bars import (
    FAMILY_ALIASES, SPEC_PATH, dual_bar_verdict, git_blob_id, k_family, load_families,
    render_bars, resolve_family)

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


ARM_FAMILIES = ("ingame_arms_mlb", "ingame_arms_nba")


def test_frozen_spec_loads_and_pins_itself_into_every_verdict():
    """S89 amended the frozen partition: 37 feature grids + 2 in-game ARM families = 39.

    The counts below moved DELIBERATELY and once. Old pin (37 / 396 / 3564,
    s14-families-v1) 62702554f6e57ec9f3182e8edc1e4d6a109a3b41; the new pin is whatever
    `git hash-object` says now and is asserted against the spec's own stamp, so an
    UNDECLARED edit still fails here. An arm is a whole scored predictor, not a column,
    so the 9-transform grid applies to the 37 grids only and an arm family carries
    hypotheses == features.
    """
    spec = load_families()
    assert spec.spec_version == "s89-families-v2"
    assert spec.q_within_family == 0.05
    assert len(spec.families) == 39
    grids = [f for f in spec.families if f.name not in ARM_FAMILIES]
    arms = [f for f in spec.families if f.name in ARM_FAMILIES]
    assert len(grids) == 37 and len(arms) == 2
    assert sum(f.features for f in grids) == 396
    assert sum(f.hypotheses for f in grids) == 3564
    assert all(f.hypotheses == f.features * 9 for f in grids)
    assert sum(f.features for f in arms) == 11
    assert all(f.hypotheses == f.features for f in arms)
    assert all(f.horizon == "live_tick" and f.market == "inplay" for f in arms)
    assert all(f.kind == "arm" for f in arms) and all(f.kind == "grid" for f in grids)
    assert len({f.name for f in spec.families}) == len(spec.families)
    assert spec.prereg_sha256 == git_blob_id(SPEC_PATH)
    result = dual_bar_verdict(0.001, 1, [0.001, 0.9], family="nba_gate")
    assert result["families_spec_sha"] == spec.prereg_sha256
    assert result["n_families"] == 39
    assert "GLOBAL" in render_bars(result) and "FAMILY" in render_bars(result)


def test_historical_ingame_family_strings_resolve_into_the_frozen_arm_families():
    """S89: the three strings already on the ledger price inside a real frozen family."""
    spec = load_families()
    assert set(FAMILY_ALIASES) == {"ingame_mlb_arms", "ingame_mlb_clamp",
                                   "ingame_nba_halftime_asof"}
    assert resolve_family("ingame_mlb_arms") == "ingame_arms_mlb"
    assert resolve_family("ingame_mlb_clamp") == "ingame_arms_mlb"
    assert resolve_family("ingame_nba_halftime_asof") == "ingame_arms_nba"
    assert resolve_family(None) is None and resolve_family("nba_gate") == "nba_gate"
    for old_name in FAMILY_ALIASES:
        assert spec.get(old_name).name == FAMILY_ALIASES[old_name]
    result = dual_bar_verdict(0.001, 1, [0.001, 0.9], family="ingame_mlb_clamp")
    assert result["families_spec_sha"] == spec.prereg_sha256


def test_frozen_grammar_still_enumerates_only_the_37_grids():
    """S89 must not leak 11 arms x 9 transforms into the feature seed queue."""
    from scripts.platformkit.foundry.seed_queue import frozen_hypotheses

    features = {h.feature for h in frozen_hypotheses()}
    assert not features & set(load_families().get("ingame_arms_mlb").members)
    assert "nba_halftime_asof" not in features


def test_k_family_counts_the_two_historical_mlb_arm_charges(tmp_path):
    """k_family is READ-ONLY over the real ledger: rows 15 and 16 -> ingame_arms_mlb = 2."""
    real = Path("data/cache/eval_gate/backtest_fwer.jsonl")
    before = real.read_bytes()
    assert k_family("ingame_arms_mlb") == 2
    assert k_family("ingame_mlb_arms") == 2      # the alias counts the same two rows
    assert k_family("ingame_arms_nba") == 1
    assert k_family("nba_gate") == 0
    assert real.read_bytes() == before, "k_family must never write the charge ledger"
    assert k_family("ingame_arms_mlb", tmp_path / "absent.jsonl") == 0


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
