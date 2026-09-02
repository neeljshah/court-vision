"""Construct checks for the foundry cost tiers: a screen may never consume K, a verdict must,
and since S59 a charged verdict decides on BOTH bars (global deflated p AND the frozen family).

The corpus is 60 synthetic rows; the ledger is always a TMP path -- the real
data/cache/eval_gate/backtest_fwer.jsonl is never opened by this file. Likewise the S59
results DB is always tmp_path; the pod's hypotheses.sqlite is never opened here.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import pytest

from scripts.platformkit.eval_gate.family_bars import families_spec_sha
from scripts.platformkit.foundry import tiers
from scripts.platformkit.foundry.grammar import Hypothesis
from scripts.platformkit.foundry.results_db import ResultsDB
from scripts.platformkit.foundry.tiers import (PromotionRule, ScreenPartitionLeak, TierNotChargeable,
                                               charge_tier, partition_corpus, promote, run_tier)

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md"
TEAMS = ("ATL", "BOS", "CHI", "DAL", "DEN", "GSW")
FAMILY = "s12_construct"          # NOT in the frozen FWER partition -- screens only
FROZEN_FAMILY = "nba_gate"        # IS in docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md
SCREENED_N = 40


def _corpus(prefix: str, rows: int = 60) -> list:
    base, states = date(2026, 1, 5), []
    for index in range(rows):
        day = base + timedelta(days=(index // 5) * 7 + (index % 5))
        states.append({
            "game_id": "%s%03d" % (prefix, index),
            "state_ts": "%sT12:00:00" % day.isoformat(),
            "features": {"x": (index % 7) / 7.0},
            "feature_avail": {"x": "%sT00:00:00" % (day - timedelta(days=1)).isoformat()},
            "home": TEAMS[index % 6], "away": TEAMS[(index + 3) % 6],
            "outcome": int(index % 3 != 0),
            "devig_close_prob": 0.5 + 0.01 * ((index % 5) - 2)})
    return states


def _predict(train, test, select_inside):  # noqa: ANN001 - walk_forward's predict_fn shape
    return min(max(0.45 + 0.2 * test["features"]["x"], 0.01), 0.99)


def _rule(tmp_path: Path, top_n: int = 2) -> PromotionRule:
    """Frozen rule with a narrowed top_n: the width comes off the FILE, never an argument."""
    path = tmp_path / "tiers_spec.md"
    path.write_text(SPEC.read_text(encoding="ascii").replace("top_n: 20", "top_n: %d" % top_n),
                    encoding="ascii")
    return PromotionRule.from_spec(path)


def _sides(states: list, rule: PromotionRule) -> tuple:
    part = partition_corpus(states, seed=rule.partition_seed)
    screen = [s for s in states if s["game_id"] in part.screen_ids]
    verdict = [s for s in states if s["game_id"] in part.verdict_ids]
    return part, screen, verdict


def _rows(ledger: Path) -> int:
    return len(ledger.read_text(encoding="ascii").splitlines()) if ledger.exists() else 0


def _hypothesis(feature: str = "pace_diff_asof") -> Hypothesis:
    return Hypothesis("nba", feature, "raw", (), frozenset(), "pregame", "ml")


class _DM(NamedTuple):
    """diebold_mariano's shape, pinned so the BAR logic is what is under test."""

    dm_stat: float
    p_value: float


def _fixed_p(monkeypatch, p: float) -> None:
    monkeypatch.setattr(tiers, "diebold_mariano", lambda losses, ids: _DM(-1.0, p))


def _seed_k(ledger: Path, k: int) -> None:
    """Pre-charge the TMP ledger so the trial under test reads k_cumulative = k + 1."""
    ledger.write_text(json.dumps(
        {"at": "2026-09-03T00:00:00+00:00", "predictor": "seed", "sport": "nba",
         "start": "2026-01-05", "end": "2026-03-30", "k_cumulative": int(k)}) + "\n",
        encoding="ascii")


def _base_rate_predict(train, test, select_inside):  # noqa: ANN001 - predict_fn shape
    """Predict the TRAIN base rate -- no leakage (the test row is redacted anyway), and on a
    2-of-3 corpus it is sharper than the ~0.5 close, which is what makes AHEAD reachable."""
    ys = [int(s["outcome"]) for s in train]
    return min(max(sum(ys) / len(ys), 0.01), 0.99) if ys else 0.5


def _db_with_family_p_values(tmp_path: Path, values: list, family: str) -> ResultsDB:
    """A tmp results DB already carrying `values` as recorded raw p-values for `family`."""
    db = ResultsDB(tmp_path / "hypotheses.sqlite")
    for index, raw_p in enumerate(values):
        digest = db.upsert_hypothesis(_hypothesis("prior_%03d" % index), family=family)
        db.record({"hash": digest, "tier": "T2", "corpus": "nba", "corpus_unit": "u%03d" % index,
                   "corpus_sha": "s%03d" % index, "n": 30, "n_eff": 30.0, "brier_model": 0.25,
                   "brier_close": 0.25, "dm_stat": 0.0, "raw_p": raw_p, "k_family": index + 1,
                   "k_global": index + 1, "deflated_p": 1.0, "pbo": 0.5, "verdict": "MATCH",
                   "artifact_path": "", "prereg_sha256": "", "run_at": None})
    return db


def _charged(tmp_path: Path, monkeypatch, raw_p: float, *, k_seed: int = 0,
             family: str = FROZEN_FAMILY, predict=_base_rate_predict, db=None,
             artifact: str = ""):
    """One T2 on the verdict side with a pinned p-value. Returns the TierResult."""
    rule, ledger = _rule(tmp_path), tmp_path / "fwer.jsonl"
    if k_seed:
        _seed_k(ledger, k_seed)
    part, _, verdict = _sides(_corpus("a"), rule)
    _fixed_p(monkeypatch, raw_p)
    return run_tier(_hypothesis(), "T2", states=verdict, predict_fn=predict, ledger_path=ledger,
                    partition=part, rule=rule, family=family, screened_n=SCREENED_N,
                    results_db=db, artifact_path=artifact), ledger


def test_partition_sides_are_disjoint_and_cover_the_corpus() -> None:
    part, screen, verdict = _sides(_corpus("a"), PromotionRule.from_spec(SPEC))
    assert not part.screen_ids & part.verdict_ids
    assert len(screen) + len(verdict) == 60 and screen and verdict
    assert part.screen_sha256 != part.verdict_sha256


def test_t0_and_t1_refuse_to_charge_and_leave_the_ledger_empty(tmp_path: Path) -> None:
    rule, ledger = _rule(tmp_path), tmp_path / "fwer.jsonl"
    part, screen, _ = _sides(_corpus("a"), rule)
    t0 = run_tier(_hypothesis(), "T0", states=screen, predict_fn=_predict, ledger_path=ledger,
                  partition=part, rule=rule, family=FAMILY)
    t1 = run_tier(_hypothesis(), "T1", states=screen, predict_fn=_predict, ledger_path=ledger,
                  partition=part, rule=rule, family=FAMILY)
    assert t0.verdict == "COVERED" and t0.k_global is None
    assert t1.verdict == "SCREEN" and t1.k_global is None and t1.brier_model is not None
    assert _rows(ledger) == 0
    for tier in ("T0", "T1"):
        with pytest.raises(TierNotChargeable):
            charge_tier(tier, ledger_path=ledger, family=FAMILY, hypothesis_hash="0" * 64,
                        prereg_sha256=rule.prereg_sha256, sport="nba",
                        start="2026-01-05", end="2026-03-30")
    assert _rows(ledger) == 0


def test_t2_and_t3_each_append_exactly_one_ledger_row(tmp_path: Path) -> None:
    rule, ledger = _rule(tmp_path), tmp_path / "fwer.jsonl"
    part_a, _, verdict_a = _sides(_corpus("a"), rule)
    part_b, _, verdict_b = _sides(_corpus("b"), rule)
    t2 = run_tier(_hypothesis(), "T2", states=verdict_a, predict_fn=_predict, ledger_path=ledger,
                  partition=part_a, rule=rule, family=FROZEN_FAMILY, screened_n=SCREENED_N)
    assert _rows(ledger) == 1
    t3 = run_tier(_hypothesis(), "T3", states=verdict_b, predict_fn=_predict, ledger_path=ledger,
                  partition=part_b, rule=rule, family=FROZEN_FAMILY, screened_n=SCREENED_N,
                  n_corpora=2)
    assert _rows(ledger) == 2
    for result, tier in ((t2, "T2"), (t3, "T3")):
        assert result.tier == tier and result.k_global >= 1 and result.k_family >= 1
        assert result.screened_n == SCREENED_N and result.prereg_sha256 == rule.prereg_sha256
        assert result.cluster_key == "team" and 0.0 <= result.pbo <= 1.0
        assert 0.0 < result.deflated_p <= 1.0 and result.deflated_p >= result.raw_p
        assert result.verdict in ("MATCH", "BEHIND", "AHEAD", "SINGLE-WINDOW")
    assert t3.k_family == t2.k_family + 1
    assert t2.screen_partition_sha256 == part_a.screen_sha256


def test_t2_on_rows_that_intersect_the_screen_partition_self_rejects(tmp_path: Path) -> None:
    rule, ledger = _rule(tmp_path), tmp_path / "fwer.jsonl"
    part, screen, verdict = _sides(_corpus("a"), rule)
    with pytest.raises(ScreenPartitionLeak):
        run_tier(_hypothesis(), "T2", states=verdict + screen[:1], predict_fn=_predict,
                 ledger_path=ledger, partition=part, rule=rule, family=FAMILY,
                 screened_n=SCREENED_N)
    assert _rows(ledger) == 0


def test_charged_tier_refuses_an_unpriced_screen_width(tmp_path: Path) -> None:
    rule, ledger = _rule(tmp_path), tmp_path / "fwer.jsonl"
    part, _, verdict = _sides(_corpus("a"), rule)
    with pytest.raises(ValueError, match="screened_n"):
        run_tier(_hypothesis(), "T2", states=verdict, predict_fn=_predict, ledger_path=ledger,
                 partition=part, rule=rule, family=FAMILY)
    assert _rows(ledger) == 0


def test_top_n_two_promotes_exactly_two(tmp_path: Path) -> None:
    rule, ledger = _rule(tmp_path, top_n=2), tmp_path / "fwer.jsonl"
    part, screen, _ = _sides(_corpus("a"), rule)
    features = ("pace_diff_asof", "rest_diff_asof", "elo_diff_asof", "srs_diff_asof", "pt_diff_asof")
    screens = [run_tier(_hypothesis(name), "T1", states=screen, predict_fn=_predict,
                        ledger_path=ledger, partition=part, rule=rule, family=FAMILY)
               for name in features]
    promoted = promote(screens, rule)
    assert rule.top_n == 2 and len(promoted) == 2
    assert {h.feature for h in promoted}.issubset(set(features))
    assert _rows(ledger) == 0


# -- S59: the charged tiers decide on BOTH bars ------------------------------------------

def test_a_family_outside_the_frozen_partition_is_reported_and_never_charged(tmp_path, monkeypatch):
    """Case 3. No frozen family -> no family bar -> no AHEAD is reachable, and the refusal
    lands BEFORE charge_tier so an unfrozen family cannot consume K silently."""
    result, ledger = _charged(tmp_path, monkeypatch, 1e-9, family="s12_construct")
    assert result.verdict == "NOT_IN_FROZEN_FAMILIES"
    assert result.dual_verdict == "" and result.k_global is None and result.raw_p is None
    assert result.bh_passed is None and result.global_passed is None
    assert result.families_spec_sha256 == families_spec_sha()
    assert _rows(ledger) == 0


def test_clearing_bh_but_failing_the_global_bar_is_not_ahead(tmp_path, monkeypatch):
    """Case 1. The S14 loosening cannot ship anything on its own: bar 1 still blocks."""
    result, ledger = _charged(tmp_path, monkeypatch, 0.004, k_seed=999)
    assert _rows(ledger) == 2 and result.k_global == 1000    # the seed row plus this trial
    assert result.bh_passed is True and result.global_passed is False
    assert result.deflated_p == 1.0 and result.family_q == 0.05
    assert result.dual_verdict == "NOT AHEAD" and result.verdict != "AHEAD"


def test_clearing_both_bars_is_ahead(tmp_path, monkeypatch):
    """Case 2. Both bars cleared and the model is sharper than the close -- the only AHEAD."""
    result, ledger = _charged(tmp_path, monkeypatch, 1e-9)
    assert _rows(ledger) == 1 and result.k_global == 1
    assert result.brier_model < result.brier_close
    assert result.global_passed is True and result.bh_passed is True
    assert result.verdict == "AHEAD" and result.dual_verdict == "AHEAD"
    assert result.families_spec_sha256 == families_spec_sha()


def test_recorded_family_p_values_block_an_otherwise_global_pass(tmp_path, monkeypatch):
    """The family's p-values come off the results DB rows recorded so far, plus this trial:
    40 recorded nulls turn a lone global pass into NOT AHEAD."""
    with _db_with_family_p_values(tmp_path, [0.9] * 40, FROZEN_FAMILY) as db:
        result, ledger = _charged(tmp_path, monkeypatch, 0.03, db=db)
    assert _rows(ledger) == 1
    assert result.global_passed is True and result.bh_passed is False
    assert result.dual_verdict == "NOT AHEAD" and result.verdict != "AHEAD"


def test_the_artifact_json_prints_both_bars_and_both_q_rules(tmp_path, monkeypatch):
    """Both q-rules are printed whichever one the frozen spec chose, so the reader can see
    how much of the verdict rests on BH's PRDS assumption."""
    artifact = tmp_path / "trials" / "t2.json"
    result, _ = _charged(tmp_path, monkeypatch, 1e-9, artifact=artifact.as_posix())
    printed = json.loads(artifact.read_text(encoding="ascii"))
    assert printed["q_rule"] == "fdr_bh" and printed["family"] == FROZEN_FAMILY
    assert printed["fdr_bh_pass"] is True and printed["fdr_by_pass"] is True
    assert printed["fdr_bh_adjusted_p"] <= printed["fdr_by_adjusted_p"]
    assert printed["families_spec_sha"] == result.families_spec_sha256
    assert "GLOBAL" in printed["bars_line"] and "FAMILY" in printed["bars_line"]
    assert "fdr_bh_adj_p" in printed["bars_line"] and "fdr_by_adj_p" in printed["bars_line"]


def test_t0_passes_portable_only_when_the_env_flag_is_set(tmp_path, monkeypatch):
    """S16b: FOUNDRY_PORTABLE_CORPUS=1 is the only way T0 asks for the S68 portable load."""
    seen = []
    monkeypatch.setattr(tiers, "load_gate_corpus", lambda sport, portable=False: seen.append(portable))
    rule, ledger = _rule(tmp_path), tmp_path / "fwer.jsonl"
    part, screen, _ = _sides(_corpus("a"), rule)
    for value, expected in (("1", True), ("0", False), (None, False)):
        monkeypatch.delenv("FOUNDRY_PORTABLE_CORPUS", raising=False)
        if value is not None:
            monkeypatch.setenv("FOUNDRY_PORTABLE_CORPUS", value)
        run_tier(_hypothesis(), "T0", states=screen, predict_fn=_predict, ledger_path=ledger,
                 partition=part, rule=rule, family=FAMILY)
        assert seen[-1] is expected
    assert len(seen) == 3
