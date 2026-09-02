"""Per-file test for the soccer/tennis mechanism close-effect wiring (S22).

Fixture-only: a planted effect must land CONFIRMED_LOCAL, a null must land
NULL_LOCAL, and a mechanism whose declared column is absent must land
NOT_TESTABLE with that column named. No corpus, no ledger, no network.
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.analytics_showcase import (
    mechanism_close_effect as effect, mechanism_wiring as wiring,
    mechanism_wiring_soccer, mechanism_wiring_tennis)
from scripts.platformkit.analytics_showcase.mechanism_exposure import parse_mechanisms

KNOWLEDGE = Path(__file__).resolve().parents[3] / "domains"


def _frame(n: int = 400, planted: float = 0.0, units: tuple[str, ...] = ("ATP", "WTA")) -> pd.DataFrame:
    """Synthetic states: residual = planted * sign(trigger) + tiny fixed noise."""
    rng = np.random.default_rng(7)
    rows = []
    for unit in units:
        for i in range(n):
            trigger = -1.0 + 2.0 * (i % 2)
            residual = planted * trigger + rng.normal(0, 0.01)
            rows.append({"event_id": "%s-%d" % (unit, i), "corpus_unit": unit,
                         "game_date": "2020-01-%02d" % (1 + i % 28),
                         "devig_close_prob": 0.5, "outcome": 0.5 + residual,
                         "vintage": "SYNTHETIC", "trig": trigger, "surface": "Clay"})
    frame = pd.DataFrame(rows)
    frame["residual"] = frame["outcome"] - frame["devig_close_prob"]
    return frame


def _spec(expr: str = "trig", columns: tuple[str, ...] = ("trig",), mask: str | None = None) -> dict:
    return {"source": "data/cache/combo/gate_corpus_tennis.parquet", "expr": expr,
            "columns": columns, "mask": mask, "note": "fixture"}


def test_a_planted_effect_is_confirmed_local_in_every_corpus_unit() -> None:
    row = effect.measure("planted", _spec(), _frame(planted=0.05))
    assert row["verdict"] == "CONFIRMED_LOCAL"
    assert set(row["corpus_units"]) == {"ATP", "WTA"}
    for unit in row["corpus_units"].values():
        assert unit["verdict"] == "CONFIRMED_LOCAL" and abs(unit["effect"]) >= effect.MIN_EFFECT
        assert unit["p_value"] < effect.ALPHA and unit["n"] >= 2 * effect.MIN_UNIT_ROWS


def test_a_null_trigger_is_null_local_not_confirmed() -> None:
    row = effect.measure("null", _spec(), _frame(planted=0.0))
    assert row["verdict"] == "NULL_LOCAL"
    assert all(unit["verdict"] == "NULL_LOCAL" for unit in row["corpus_units"].values())


def test_an_effect_below_the_declared_bar_is_null_local_despite_a_tiny_p() -> None:
    # Bars are never lowered: 0.005 clears p<0.01 by a mile but misses |eff|>=0.02.
    row = effect.measure("small", _spec(), _frame(planted=0.005))
    assert row["verdict"] == "NULL_LOCAL"
    for unit in row["corpus_units"].values():
        assert unit["p_value"] < effect.ALPHA and abs(unit["effect"]) < effect.MIN_EFFECT


def test_an_absent_column_is_not_testable_and_names_the_column() -> None:
    row = effect.measure("absent", _spec(expr="ghost_col", columns=("ghost_col",)), _frame())
    assert row["verdict"] == "NOT_TESTABLE" and "ghost_col" in row["reason"]


def test_a_unit_whose_column_is_entirely_null_is_not_testable_not_thin() -> None:
    frame = _frame(planted=0.05)
    frame.loc[frame.corpus_unit.eq("WTA"), "trig"] = np.nan
    row = effect.measure("atp_only", _spec(), frame)
    assert row["corpus_units"]["WTA"]["verdict"] == "NOT_TESTABLE"
    assert "entirely null" in row["corpus_units"]["WTA"]["reason"]
    assert row["single_corpus_unit"] is True and row["corpus_units_scored"] == 1


def test_atp_and_wta_are_measured_separately_and_never_pooled() -> None:
    frame = _frame(planted=0.05)
    frame.loc[frame.corpus_unit.eq("WTA"), "trig"] *= -1.0  # opposite sign per unit
    row = effect.measure("opposed", _spec(), frame)
    assert row["verdict"] == "NULL_LOCAL", "opposite-sign units must not confirm"
    signs = {unit["effect"] > 0 for unit in row["corpus_units"].values()}
    assert signs == {True, False}
    for unit in row["corpus_units"].values():
        assert unit["date_range"] == ["2020-01-01", "2020-01-28"]


def test_a_thin_coverage_trigger_stays_not_testable() -> None:
    frame = _frame(planted=0.05)
    frame.loc[frame.index[100:], "trig"] = np.nan
    row = effect.measure("thin", _spec(), frame)
    assert row["verdict"] == "NOT_TESTABLE" and row["coverage_share"] < effect.MIN_COVERAGE


def test_a_mask_restricts_the_trigger_to_the_declared_subset() -> None:
    frame = _frame(planted=0.05)
    frame.loc[frame.index[:200], "surface"] = "Hard"
    row = effect.measure("masked", _spec(mask="surface == 'Clay'"), frame)
    assert row["n"] < len(frame) and row["mask"] == "surface == 'Clay'"


def test_a_trigger_expression_may_never_read_the_outcome() -> None:
    with pytest.raises(AssertionError):
        effect.trigger_values(_frame(), _spec(expr="trig + outcome", columns=("trig", "outcome")))


@pytest.mark.parametrize("sport,module,expected", [
    ("soccer", mechanism_wiring_soccer, 15), ("tennis", mechanism_wiring_tennis, 23)])
def test_every_confirmed_mechanism_has_a_declared_row_and_no_row_is_orphaned(
        sport: str, module, expected: int) -> None:
    slugs = [row["slug"] for row in parse_mechanisms(KNOWLEDGE / sport / "knowledge" / "mechanisms.md")]
    assert len(slugs) == expected, "%s ledger parsed %d confirmed sections" % (sport, len(slugs))
    assert wiring.rollup(slugs, sport)["not_wired"] == []
    assert set(module.WIRING) == set(slugs), "a declared row matches no confirmed section"


@pytest.mark.parametrize("module", [mechanism_wiring_soccer, mechanism_wiring_tennis])
def test_no_dollar_or_roi_language_in_any_declared_row(module) -> None:
    # Word-boundary matching on purpose: "ledger" contains the letters of "edge".
    banned = re.compile(r"\b(roi|profit|edge|bankroll|ev\+|\+ev)\b|\$")
    text = " ".join(str(row.get("reason", "")) + str(row.get("note", ""))
                    for row in module.WIRING.values()).lower()
    assert banned.search(text) is None, banned.search(text)


def test_every_declared_trigger_column_is_listed_in_its_columns_tuple() -> None:
    for slug, spec in mechanism_wiring_tennis.WIRING.items():
        if not spec["expr"]:
            continue
        text = spec["expr"] + " " + (spec.get("mask") or "")
        for column in spec["columns"]:
            assert column in text, "%s declares %s but never uses it" % (slug, column)


def test_build_charges_nothing_and_seals_its_prereg_before_the_rows() -> None:
    frame = _frame(planted=0.05)
    result = effect.build("tennis", frame)
    assert result["label"] == "DESCRIPTIVE_ONLY" and result["edge_claimed"] is False
    assert len(result["prereg_sha256"]) == 64
    assert result["counts"]["mechanisms"] == len(mechanism_wiring_tennis.WIRING)
    assert set(result["counts"]["by_verdict"]) <= {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
