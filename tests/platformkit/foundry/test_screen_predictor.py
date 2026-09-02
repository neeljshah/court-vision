"""S58c: the real T1 screen predictor -- planted as-of signal shows, a same-game column is refused,
and the per-unit differential is archived with cluster ids (Q9). Construct corpus; no real data,
no ledger, no production DB is opened here."""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from scripts.platformkit.foundry import screen_predictor as sp
from scripts.platformkit.foundry import tiers
from scripts.platformkit.foundry.grammar import Hypothesis

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md"
TEAMS = tuple("T%02d" % i for i in range(12))


def _corpus(rows: int = 360, seed: int = 7) -> tuple:
    """States whose outcome depends on the close AND a planted as-of feature `x_asof`."""
    rng, base, states, feats = random.Random(seed), date(2025, 1, 6), [], {}
    for index in range(rows):
        day = base + timedelta(days=(index // 6) * 7 + (index % 6))
        close = 0.35 + 0.3 * rng.random()
        x = rng.gauss(0.0, 1.0)
        eta = math.log(close / (1 - close)) + 1.5 * x
        y = int(rng.random() < 1.0 / (1.0 + math.exp(-eta)))
        event = "g%04d" % index
        states.append({"game_id": event, "state_ts": "%sT12:00:00" % day.isoformat(),
                       "game_date": day.isoformat(), "sport": "nba",
                       "home": TEAMS[index % 12], "away": TEAMS[(index + 5) % 12],
                       "features": {"p_base": close}, "feature_avail": {"p_base": "%sT00:00:00" % day},
                       "devig_close_prob": close, "outcome": y})
        feats[event] = {"x_asof": x, "home_final": float(y), "noise_asof": rng.gauss(0.0, 1.0)}
    return states, pd.DataFrame.from_dict(feats, orient="index")


def _hyp(feature: str, transform: str = "raw", params: tuple = ()) -> Hypothesis:
    return Hypothesis("nba", feature, transform, params, frozenset(), "pregame", "ml", "s58_construct")


def _screen(binder: sp.ScreenBinder, hypothesis: Hypothesis, tmp_path: Path) -> tiers.TierResult:
    states, predict_fn = binder(hypothesis)
    rule = tiers.PromotionRule.from_spec(SPEC)
    part = tiers.partition_corpus(states, seed=rule.partition_seed)
    screen = [s for s in states if s["game_id"] in part.screen_ids]
    return tiers.run_tier(hypothesis, "T1", states=screen, predict_fn=predict_fn,
                          ledger_path=tmp_path / "fwer.jsonl", partition=part, rule=rule,
                          family=hypothesis.family)


def test_planted_asof_feature_beats_the_incumbent_and_is_archived(tmp_path):
    states, table = _corpus()
    binder = sp.ScreenBinder("nba", states, table, rows=len(states), incumbent="devig_close")
    result = _screen(binder, _hyp("x_asof"), tmp_path)
    assert result.verdict == "SCREEN" and result.brier_model < result.brier_close
    assert result.archive["screen_p"] < 0.05 and result.archive["cluster_key"] == "team"
    # Q9: one differential row per scored state, carrying the cluster id and both losses.
    rows = result.archive["differential"]
    assert len(rows) == result.n and len({r[0] for r in rows}) == result.n
    assert all(r[2] in TEAMS and r[3] >= 0.0 and r[4] >= 0.0 for r in rows)
    assert result.archive["fits"] and result.archive["fits"][-1]["coef"] is not None
    # the null twin: a noise feature does not beat the incumbent by the planted margin
    null = _screen(binder, _hyp("noise_asof"), tmp_path)
    assert (result.brier_close - result.brier_model) > (null.brier_close - null.brier_model)
    assert not (tmp_path / "fwer.jsonl").exists()          # a screen never charges


def test_a_same_game_column_is_refused_by_name_before_any_value_is_read():
    states, table = _corpus(rows=60)
    binder = sp.ScreenBinder("nba", states, table, rows=60, incumbent="devig_close")
    with pytest.raises(sp.ScreenRefused, match="leaky"):
        binder(_hyp("home_final"))
    for name in ("fthg", "home_win", "outcome", "asof_idx", "final_margin"):
        with pytest.raises(sp.ScreenRefused):
            sp.check_feature_name(name, table.columns)
    with pytest.raises(sp.ScreenRefused, match="unavailable"):
        sp.check_feature_name("something_unknown", table.columns)


def test_transforms_use_prior_rows_only_and_ratio_needs_a_twin():
    states, table = _corpus(rows=60)
    binder = sp.ScreenBinder("nba", states, table, rows=60, incumbent="devig_close")
    delta = binder.feature_values(_hyp("x_asof", "delta_vs_prior"))
    first_per_team = delta.groupby(binder.frame["cluster"].values).head(1)
    assert first_per_team.isna().all()                       # no prior row -> no value, never a leak
    ew = binder.feature_values(_hyp("x_asof", "ew", (("halflife", 3),)))
    assert ew.groupby(binder.frame["cluster"].values).head(1).isna().all()
    with pytest.raises(sp.ScreenRefused, match="twin"):
        binder(_hyp("x_asof", "ratio_to_opponent"))
