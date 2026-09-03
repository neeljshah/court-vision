"""S14 -- both bars, or it is not AHEAD.

Planted-null design follows eval_gate/null_ship_calibration.py: N independent,
outcome-blind candidates, seeded, none dropped or re-labelled afterwards. The
p-value of a null hypothesis is uniform on [0,1], and `family_bars` consumes
p-values rather than data, so the plant happens at the p-value layer.

Run ONLY this file: python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.platformkit.eval_gate import family_bars

from scripts.platformkit.eval_gate import worktree_marker
from scripts.platformkit.eval_gate.family_bars import (
    FAMILY_ALIASES, SPEC_PATH, dual_bar_verdict, git_blob_id, k_family, load_families,
    render_bars, resolve_family)

FWER_LEDGER = Path("data/cache/eval_gate/backtest_fwer.jsonl")
PLANTED_NULLS = 200
SEED = 20260903
MAX_DISCOVERIES = 10


def require_ledger(path: Path = FWER_LEDGER) -> Path:
    """S153: an absent charge ledger is a FAILURE here, a skip only in a worktree.

    data/cache/eval_gate/ is never junctioned into a codex worktree, so the skip is
    correct there; in the main repo the same absence is missing evidence, and a
    bare `if not exists: skip` let it read as a pass.
    """
    if worktree_marker.is_worktree_checkout():
        pytest.skip(f"worktree checkout: {path} is never junctioned into a worktree")
    if not path.exists():
        raise AssertionError(
            f"main-repo checkout: the FWER charge ledger is absent: {path.resolve()}")
    return path


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
TICK_GRID_FAMILIES = ("ingame_nba_tickgrid", "ingame_nba_pairs")


def test_frozen_spec_loads_and_pins_itself_into_every_verdict():
    """S144 amended the partition: 37 grids + 2 ARM + 2 NBA TICK GRIDS = 41.

    The counts moved DELIBERATELY and once per amendment. S14 pin (37 / 396 / 3564,
    s14-families-v1) 62702554f6e57ec9f3182e8edc1e4d6a109a3b41; S89 pin (39 / 407 / 3575,
    s89-families-v2) 9d6cb98c43c74d04b7f995fe380e33705ffb7c0b; the current pin is whatever
    `git hash-object` says now and is asserted against the spec's own stamp, so an
    UNDECLARED edit still fails here. An arm is a whole scored predictor, not a column, and
    a tick grid's members are BASE columns of a derived in-game grammar whose construction
    rule is in its own block, so the 9-transform grid applies to the 37 grids only.
    """
    spec = load_families()
    assert spec.spec_version == "s144-families-v4"
    assert spec.q_within_family == 0.05
    assert len(spec.families) == 41
    special = set(ARM_FAMILIES) | set(TICK_GRID_FAMILIES)
    grids = [f for f in spec.families if f.name not in special]
    arms = [f for f in spec.families if f.name in ARM_FAMILIES]
    ticks = [f for f in spec.families if f.name in TICK_GRID_FAMILIES]
    assert len(grids) == 37 and len(arms) == 2 and len(ticks) == 2
    assert sum(f.features for f in grids) == 396
    assert sum(f.hypotheses for f in grids) == 3564
    assert all(f.hypotheses == f.features * 9 for f in grids)
    assert sum(f.features for f in arms) == 11
    assert all(f.hypotheses == f.features for f in arms)
    assert all(f.horizon == "live_tick" and f.market == "inplay" for f in arms + ticks)
    assert all(f.kind == "arm" for f in arms) and all(f.kind == "grid" for f in grids)
    assert all(f.kind == "tickgrid" for f in ticks)
    # 16 base columns x 6 transforms x 6 conditionings, and the enumerator agrees.
    assert {(f.features, f.hypotheses) for f in ticks} == {(16, 576), (182, 1092)}
    assert sum(f.features for f in spec.families) == 605
    assert sum(f.hypotheses for f in spec.families) == 5243
    assert len({f.name for f in spec.families}) == len(spec.families)
    assert spec.prereg_sha256 == git_blob_id(SPEC_PATH)
    result = dual_bar_verdict(0.001, 1, [0.001, 0.9], family="nba_gate")
    assert result["families_spec_sha"] == spec.prereg_sha256
    assert result["n_families"] == 41
    assert "GLOBAL" in render_bars(result) and "FAMILY" in render_bars(result)
def test_the_tick_grid_family_matches_its_frozen_enumerator():
    """S102: the spec block and `ingame_grammar_nba` must not be able to drift apart."""
    from scripts.platformkit.foundry.ingame_grammar_nba import (BASE, FAMILY,
                                                                enumerate_hypotheses)

    family = load_families().get(FAMILY)
    assert family.kind == "tickgrid" and family.sport == "nba"
    assert tuple(family.members) == BASE
    assert family.features == len(BASE)
    assert family.hypotheses == len(enumerate_hypotheses()) == 576


def test_the_pair_tick_grid_family_matches_its_frozen_enumerator():
    """S144: the pair block stays closed and separate from S102's 576 forms."""
    from scripts.platformkit.foundry.ingame_grammar_nba_pairs import (FAMILY, enumerate_hypotheses,
                                                                       pair_members)

    family = load_families().get(FAMILY)
    assert family.kind == "tickgrid" and family.sport == "nba"
    assert tuple(family.members) == pair_members()
    assert family.features == len(pair_members()) == 182
    assert family.hypotheses == len(enumerate_hypotheses()) == 1092


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
    real = require_ledger()
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


# --- S134: alias chains resolve transitively and the two K counters agree -------

def test_alias_chains_resolve_to_a_fixed_point(monkeypatch):
    """A rename ON TOP of an existing alias (a -> b -> c) must still reach `c`.

    Reproduced before the fix: resolve_family("a") stopped at "b", so no ledger row
    matched "c" and next_k_family returned 1 instead of 3 -- the family's K re-zeroed.
    """
    from scripts.platformkit.eval_gate.ledger import next_k_family

    monkeypatch.setitem(family_bars.FAMILY_ALIASES, "a", "b")
    monkeypatch.setitem(family_bars.FAMILY_ALIASES, "b", "c")
    assert resolve_family("a") == "c"
    assert resolve_family("b") == "c"
    assert resolve_family("c") == "c"
    rows = [{"family": "a", "k_family": 1}, {"family": "a", "k_family": 2}]
    assert next_k_family(rows, "c") == 3


def test_a_rename_preserves_k_once_its_alias_is_added(monkeypatch, tmp_path):
    """The rename test: K survives a rename iff the alias is added with it."""
    from scripts.platformkit.eval_gate.ledger import next_k_family

    ledger = tmp_path / "renamed.jsonl"
    rows = [{"family": "old_fam", "k_family": 1}, {"family": "old_fam", "k_family": 2}]
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="ascii")
    assert next_k_family(rows, "new_fam") == 1 and k_family("new_fam", ledger) == 0
    monkeypatch.setitem(family_bars.FAMILY_ALIASES, "old_fam", "new_fam")
    assert next_k_family(rows, "new_fam") == 3      # K preserved across the rename
    assert k_family("new_fam", ledger) == 2


def test_an_alias_cycle_raises_instead_of_looping(monkeypatch):
    monkeypatch.setitem(family_bars.FAMILY_ALIASES, "p", "q")
    monkeypatch.setitem(family_bars.FAMILY_ALIASES, "q", "p")
    with pytest.raises(ValueError, match="cycle"):
        resolve_family("p")


def test_the_two_k_counters_agree_on_every_family_of_the_real_ledger():
    """S134: the read path (k_family) and the write path (next_k_family) count the
    SAME rule -- family, aliases resolved -- over the real 18-row charge ledger.

    READ-ONLY: the ledger's bytes are asserted unchanged either side of the count.
    """
    from scripts.platformkit.eval_gate.ledger import load_fwer, next_k_family

    real = require_ledger()
    before = real.read_bytes()
    rows = load_fwer(real)
    assert len(rows) == 18
    families = sorted({resolve_family(r["family"]) for r in rows if r.get("family")})
    assert families, "the ledger carries at least one family"
    for name in families:
        assert k_family(name, real) == next_k_family(rows, name) - 1, name
    assert real.read_bytes() == before, "counting must never write the charge ledger"


def test_the_frozen_39_family_counts_are_unchanged_by_s134():
    """The bar: k_family over the unmodified ledger is what it was for every family.

    The S134 register row says 39 frozen families; the frozen spec now carries 40
    (S102 added a tickgrid family after the row was filed), so the count is asserted
    from the spec rather than restated.
    """
    real = require_ledger()
    counts = {f.name: k_family(f.name, real) for f in load_families().families}
    assert len(counts) == 41
    assert {n: v for n, v in counts.items() if v} == {
        "ingame_arms_mlb": 2, "ingame_arms_nba": 1, "soccer_gate": 1}


def test_the_two_counters_also_agree_on_a_pre_s13_row():
    """The remaining half of S134: a row carrying `family` with `k_family` None.

    It IS a charge against that family, but the write path filters it out
    (ledger.py:155 `r.get("k_family") is not None`) while the read path counts it --
    measured 1 vs 2 on this pair. XPASS here means the proposed one-line patch landed
    and this marker should be removed.
    """
    from scripts.platformkit.eval_gate.ledger import next_k_family

    rows = [{"family": "X", "k_family": 1}, {"family": "X", "k_family": None}]
    assert next_k_family(rows, "X") == 3


# --- S153: absent evidence must not read as a pass -----------------------------

def test_a_worktree_checkout_skips_the_ledger_tests(monkeypatch):
    """Worktree mode -> Skipped, because data/cache/eval_gate is never junctioned."""
    monkeypatch.setenv("FOUNDRY_WORKTREE", "1")
    assert worktree_marker.is_worktree_checkout() is True
    with pytest.raises(pytest.skip.Exception):
        require_ledger(FWER_LEDGER)


def test_a_missing_ledger_in_the_main_repo_fails_instead_of_skipping(monkeypatch, tmp_path):
    """Main-repo mode -> AssertionError naming the path. This is the S153 bar."""
    monkeypatch.setattr(worktree_marker, "is_worktree_checkout", lambda *a, **k: False)
    absent = tmp_path / "backtest_fwer.jsonl"
    with pytest.raises(AssertionError, match="charge ledger is absent"):
        require_ledger(absent)
