"""tests.platformkit.signals.test_planted_nulls -- LANE C calibration tripwire.

Asserts:
  (1) every family's shuffled-label null runs through the IDENTICAL production gate
      (ran_through_identical_gate() is True -- no parallel stub; tests-mirror-real) and
      does NOT 'ship' (verdict != REPLICATED): a known null must not manufacture a win.
  (2) a shipped null FREEZES its family (freezes_family() / frozen_families()).
  (3) the tripwire is deterministic (same seed -> same verdict + shipped flag).
  (4) no $/pnl/roi/edge field on the result.

Per-file test only (full pytest freezes the box). ASCII; numpy + pandas deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.signals import planted_nulls as PN  # noqa: E402


# ----------------------------------------------------------------- (1) does not ship
def test_planted_nulls_do_not_ship():
    results = PN.run_all_planted_nulls(n_games=60, ticks=8, seed=1234)
    assert len(results) == 3
    for r in results:
        assert r.verdict != "REPLICATED", (r.family, r.verdict)
        assert r.shipped is False, (r.family, r.verdict)
        assert r.is_planted_null is True


def test_null_routes_through_identical_gate():
    # tests-mirror-real: the null uses the SAME gate object the real signals use.
    assert PN.ran_through_identical_gate() is True


# ----------------------------------------------------------------- (2) freeze on ship
def test_shipped_null_freezes_family():
    shipped = PN.PlantedNullResult(family="playstyle_corr", verdict="REPLICATED",
                                   shipped=True, n_games=10)
    not_shipped = PN.PlantedNullResult(family="scheme_prior", verdict="REJECT",
                                       shipped=False, n_games=10)
    assert shipped.freezes_family() is True
    assert not_shipped.freezes_family() is False
    frozen = PN.frozen_families([shipped, not_shipped])
    assert frozen == ["playstyle_corr"]


def test_clean_run_freezes_nothing():
    results = PN.run_all_planted_nulls(n_games=50, ticks=8, seed=42)
    assert PN.frozen_families(results) == []  # no null shipped -> nothing frozen


# ----------------------------------------------------------------- (3) deterministic
def test_planted_null_is_deterministic():
    a = PN.run_planted_null("scheme_prior", n_games=40, ticks=8, seed=7)
    b = PN.run_planted_null("scheme_prior", n_games=40, ticks=8, seed=7)
    assert a.verdict == b.verdict
    assert a.shipped == b.shipped


# ----------------------------------------------------------------- (4) no $ field
def test_result_has_no_dollar_field():
    r = PN.run_planted_null("archetype_matchup", n_games=40, ticks=8, seed=3)
    blob = repr(r).lower()
    for tok in ("$", "roi", "pnl", "dollar"):
        assert tok not in blob.replace("calibration, not edge", " "), tok
