"""S85 -- the declared as-of bridge and the opt-in diversify-by-source-column pick rule.

The load-bearing test is `test_prior_rule_is_strictly_before`: the `prior` rule is the only
reason a same-game total (a referee's cards, a reliever's batters faced) may be served at all,
and it is honest ONLY if the event's own row is unreachable. Everything else here is a construct
check on the registry and on the two rules that do not aggregate over time.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from scripts.platformkit.eval_gate.family_bars import load_families
from scripts.platformkit.foundry import asof_supply, promotion
from scripts.platformkit.foundry.grammar import Hypothesis

SCREENED = frozenset(("nba_boxdetail", "tennis_setdetail", "tennis_hold", "nba_team_adv",
                      "nba_gate", "soccer_gate", "soccer_xg_proxy", "nba_defender_rollup",
                      "nba_carryover", "tennis_gate", "mlb_gate", "mlb_inning"))


def _context(rows: list) -> pd.DataFrame:
    frame = pd.DataFrame(rows).set_index("event_id")
    frame.attrs["sport"] = "nba"
    return frame


def _register(monkeypatch, tmp_path: Path, frame: pd.DataFrame, spec: asof_supply.Supply):
    """Put ONE synthetic family in the registry, backed by a parquet under tmp_path."""
    path = tmp_path / "src.parquet"
    frame.to_parquet(path)
    spec = replace(spec, source=path.as_posix())
    monkeypatch.setitem(asof_supply.REGISTRY, "unit_family", spec)
    monkeypatch.setattr(asof_supply, "ROOT", Path("/"))
    asof_supply._read.cache_clear()
    asof_supply._frame.cache_clear()
    return spec


def test_prior_rule_is_strictly_before(monkeypatch, tmp_path):
    """The served value is the entity's expanding mean over rows STRICTLY BEFORE the event date.

    HOME has 10 on Jan 1 and 100 on Jan 5; AWAY has 1 on Jan 1. An event on Jan 5 must see
    HOME = 10 (its own Jan 5 row unreachable) and on Jan 10 must see HOME = mean(10, 100) = 55.
    An event on Jan 1 has no prior row at all and must be NaN, never the same-day value.
    """
    src = pd.DataFrame({"team": ["HOME", "HOME", "AWAY", "AWAY"],
                        "date": pd.to_datetime(["2024-01-01", "2024-01-05",
                                                "2024-01-01", "2024-01-05"]),
                        "v": [10.0, 100.0, 1.0, 1.0]})
    _register(monkeypatch, tmp_path, src,
              asof_supply.Supply("", "prior", ("v",), entity="team", date="date"))
    context = _context([{"event_id": "e1", "date": "2024-01-01", "home": "HOME", "away": "AWAY"},
                        {"event_id": "e2", "date": "2024-01-05", "home": "HOME", "away": "AWAY"},
                        {"event_id": "e3", "date": "2024-01-10", "home": "HOME", "away": "AWAY"}])
    got = asof_supply.supply("unit_family", "v", context.index, context)
    assert pd.isna(got["e1"])                       # no strictly-prior row: missing, not same-day
    assert got["e2"] == pytest.approx(10.0 - 1.0)   # Jan 5's own 100 / 1 are unreachable
    assert got["e3"] == pytest.approx(55.0 - 1.0)   # mean(10, 100) - mean(1, 1)


def test_side_rule_is_home_minus_away_and_event_rule_uses_the_declared_key(monkeypatch, tmp_path):
    src = pd.DataFrame({"gid": ["e1", "e1", "e2", "e2"], "team_abbr": ["HOME", "AWAY"] * 2,
                        "v": [7.0, 2.0, 1.0, 4.0], "w": [9.0, 0.0, 3.0, 0.0]})
    _register(monkeypatch, tmp_path, src,
              asof_supply.Supply("", "side", ("v", "w"), key="gid", side="team_abbr",
                                 overrides=(("w", "a"),)))
    context = _context([{"event_id": "e1", "date": "2024-01-01", "home": "HOME", "away": "AWAY"},
                        {"event_id": "e2", "date": "2024-01-02", "home": "HOME", "away": "AWAY"}])
    diff = asof_supply.supply("unit_family", "v", context.index, context)
    assert list(diff) == [5.0, -3.0]
    only_home = asof_supply.supply("unit_family", "w", context.index, context)
    assert list(only_home) == [9.0, 3.0]            # the per-column combine override wins

    _register(monkeypatch, tmp_path, src.drop_duplicates("gid"),
              asof_supply.Supply("", "event", ("v",), key="gid"))
    got = asof_supply.supply("unit_family", "v", context.index, None)
    assert list(got) == [7.0, 1.0]                  # keyed on `gid`, not on the index name


def test_all_nan_on_the_served_window_is_refused_as_unavailable(monkeypatch, tmp_path):
    """S111 (c). `nba_quarter_shape` served 0 non-null of 1,814 (an ESPN event_id read against
    the corpus's NBA game_id) and still passed the name guard AND the grain guard, landing as a
    silent UNCOVERED. A pair that supplies nothing on the window it will be SCORED on is
    unavailable. `served_rows` is that window: the last two rows here carry no value, so the
    supply is refused even though the first row does.
    """
    src = pd.DataFrame({"gid": ["e1", "e2", "e3"], "v": [7.0, None, None]})
    _register(monkeypatch, tmp_path, src, asof_supply.Supply("", "event", ("v",), key="gid"))
    context = _context([{"event_id": "e%d" % i, "date": "2024-01-0%d" % i, "home": "H", "away": "A"}
                        for i in (1, 2, 3)])
    assert list(asof_supply.supply("unit_family", "v", context.index, None))[0] == 7.0
    context.attrs["served_rows"] = 2
    with pytest.raises(asof_supply.SupplyUnavailable, match="all-NaN on the served window"):
        asof_supply.supply("unit_family", "v", context.index, context)


def test_registry_is_additive_and_well_formed():
    """No declared pair may touch an already-screened family, and every pair must be a frozen
    family member of a table that is on disk -- otherwise the bridge is fiction."""
    families = {f.name: f for f in load_families().families}
    assert not (set(asof_supply.REGISTRY) & SCREENED), "a screened family's values would move"
    for name, spec in asof_supply.REGISTRY.items():
        family = families[name]
        assert spec.rule in ("event", "side", "prior")
        assert set(spec.columns) <= set(family.members), name
        assert not (set(spec.columns) & asof_supply.IDENTIFIERS), name
        for part in spec.source.split(","):     # S111: a comma lists several patterns
            assert list(asof_supply.ROOT.glob(part.strip())), part
        assert not asof_supply.declared(name, "y")
    assert not asof_supply.declared(None, "total_cards")
    assert not asof_supply.declared("nba_gate", "p_base")


def test_promote_diversifies_by_source_column_only_when_asked():
    """Default OFF reproduces the frozen ranking; ON takes one hypothesis per source column."""
    rule = promotion.PromotionRule.from_spec()

    def result(feature, transform, improvement, index):
        hypothesis = Hypothesis(sport="nba", feature=feature, transform=transform,
                                params=(), conditioning=frozenset(), horizon="pregame",
                                market="ml", family="f")
        return type("R", (), {"tier": "T1", "brier_model": 0.2 - improvement, "brier_close": 0.2,
                              "family": "f", "hash": "h%02d" % index,
                              "hypothesis": hypothesis})()

    rows = [result("a_asof", "raw", 0.005, 0), result("a_asof", "ew", 0.004, 1),
            result("a_asof", "z_vs_league", 0.003, 2), result("b_asof", "raw", 0.002, 3),
            result("c_asof", "raw", 0.001, 4)]
    default = promote_features(promotion.promote(rows, rule))
    assert default[:3] == ["a_asof", "a_asof", "a_asof"], "the frozen default must not move"
    diverse = promote_features(promotion.promote(rows, rule, distinct_source_columns=True))
    assert len(diverse) == len(set(diverse)), diverse
    assert diverse[:3] == ["a_asof", "b_asof", "c_asof"]
    assert len(diverse) <= rule.top_n


def promote_features(hypotheses) -> list:
    return [h.feature for h in hypotheses]
