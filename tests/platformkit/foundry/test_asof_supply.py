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


def test_prior_rule_uses_the_source_season_not_the_calendar_year(monkeypatch, tmp_path):
    """S128. A season that spans two calendar years put 51.78 pct of soccer matches in the year
    AFTER their own season label, so keying `allow_exact_matches=False` on `dt.year` served the
    match its OWN season's aggregate. Synthetic first, then the reproduced real case.

    HOME's season-1 value is 10 and its season-2 value is 100; the event is played in calendar
    year 3 but belongs to season 2, so it must see 10, never mean(10, 100).
    """
    src = pd.DataFrame({"team": ["HOME", "HOME", "AWAY", "AWAY"], "season": [1, 2, 1, 2],
                        "v": [10.0, 100.0, 1.0, 1.0]})
    seasons = pd.DataFrame({"event_id": ["e1"], "season": [2]})
    table = tmp_path / "seasons.parquet"
    seasons.to_parquet(table)
    _register(monkeypatch, tmp_path, src,
              asof_supply.Supply("", "prior", ("v",), entity="team", date="season",
                                 grain="season", season_table=table.as_posix()))
    context = _context([{"event_id": "e1", "date": "0003-01-01", "home": "HOME", "away": "AWAY"}])
    assert asof_supply.supply("unit_family", "v", context.index, context)["e1"] == 10.0 - 1.0

    monkeypatch.setitem(asof_supply.REGISTRY, "unit_family",
                        replace(asof_supply.REGISTRY["unit_family"], season_table="",
                                season_start_month=0))
    with pytest.raises(asof_supply.SupplyUnavailable, match="declares no season_table"):
        asof_supply.supply("unit_family", "v", context.index, context)


def test_soccer_prior_serves_the_honest_pre_season_value_on_the_real_corpus():
    """S128 end to end: the 2026-01-01 Brentford-Tottenham match belongs to season 2025 and must
    be served the <= 2024 prior -0.275744, not the own-season-inclusive -0.221968."""
    matches = pd.read_parquet(asof_supply.ROOT / "data/domains/soccer/matches.parquet")
    row = matches[matches["event_id"] == "20260101-E0-brentford-tottenham"].iloc[0]
    assert int(row["season"]) == 2025 and str(row["date"])[:4] == "2026"
    context = pd.DataFrame([{"date": "2026-01-01", "home": "Brentford", "away": "Tottenham"}],
                           index=pd.Index([row["event_id"]], name="event_id"))
    context.attrs["sport"] = "soccer"
    got = asof_supply.supply("soccer_style_fingerprints", "ppg", context.index, context)
    assert float(got.iloc[0]) == pytest.approx(-0.275744, abs=5e-7)


def test_side_rule_refuses_a_column_with_no_declared_pregame_basis(monkeypatch, tmp_path):
    """S129. The side rule serves the event's OWN row, so it fails closed: a planted column equal
    to the event outcome is refused by NAME unless the entry declares a pregame as-of basis."""
    src = pd.DataFrame({"gid": ["e1", "e1", "e2", "e2"], "team_abbr": ["HOME", "AWAY"] * 2,
                        "leak_outcome": [9.0, 0.0, -9.0, 0.0]})
    _register(monkeypatch, tmp_path, src,
              asof_supply.Supply("", "side", ("leak_outcome",), key="gid", side="team_abbr"))
    context = _context([{"event_id": "e1", "date": "2024-01-01", "home": "HOME", "away": "AWAY"},
                        {"event_id": "e2", "date": "2024-01-02", "home": "HOME", "away": "AWAY"}])
    with pytest.raises(asof_supply.SupplyUnavailable, match="no declared pregame as-of basis"):
        asof_supply.supply("unit_family", "leak_outcome", context.index, context)


def test_side_rule_is_home_minus_away_and_event_rule_uses_the_declared_key(monkeypatch, tmp_path):
    src = pd.DataFrame({"gid": ["e1", "e1", "e2", "e2"], "team_abbr": ["HOME", "AWAY"] * 2,
                        "v": [7.0, 2.0, 1.0, 4.0], "w": [9.0, 0.0, 3.0, 0.0]})
    _register(monkeypatch, tmp_path, src,
              asof_supply.Supply("", "side", ("v", "w"), key="gid", side="team_abbr",
                                 pregame="unit source, state BEFORE gid", overrides=(("w", "a"),)))
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
        if spec.rule == "side":                 # S129: an undeclared side entry serves own rows
            assert spec.pregame, name
        if spec.grain == "season":              # S128: never dt.year
            assert bool(spec.season_table) != bool(spec.season_start_month), name
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
