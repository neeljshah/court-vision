"""Construct checks for the foundry cost tiers: a screen may never consume K, a verdict must.

The corpus is 60 synthetic rows; the ledger is always a TMP path -- the real
data/cache/eval_gate/backtest_fwer.jsonl is never opened by this file.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.platformkit.foundry.grammar import Hypothesis
from scripts.platformkit.foundry.tiers import (PromotionRule, ScreenPartitionLeak, TierNotChargeable,
                                               charge_tier, partition_corpus, promote, run_tier)

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md"
TEAMS = ("ATL", "BOS", "CHI", "DAL", "DEN", "GSW")
FAMILY = "s12_construct"
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
                  partition=part_a, rule=rule, family=FAMILY, screened_n=SCREENED_N)
    assert _rows(ledger) == 1
    t3 = run_tier(_hypothesis(), "T3", states=verdict_b, predict_fn=_predict, ledger_path=ledger,
                  partition=part_b, rule=rule, family=FAMILY, screened_n=SCREENED_N, n_corpora=2)
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
