"""tests.platformkit.combo.test_combo_bandit -- persistence + freeze + UH3 no-favorite.

Per-file test only (full pytest freezes the box). ASCII; stdlib deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.combo import combo_bandit as B  # noqa: E402


def test_fresh_state_is_skeptical_and_no_favorite():
    """An empty state gives EVERY family the identical Beta(1,4) prior mean -- no favorite."""
    st = B.BanditState()
    fams = ["COMB_INTERACTION", "COMB_REGIME", "COMB_WEAK_ON_PROVEN"]
    means = {f: B.post_mean(st, f) for f in fams}
    assert len(set(round(m, 12) for m in means.values())) == 1  # all equal (UH3 no-favorite)
    assert abs(means[fams[0]] - 1.0 / 5.0) < 1e-12  # Beta(1,4) mean = 1/(1+4)


def test_ship_and_reject_move_posterior():
    st = B.BanditState()
    B.update(st, "COMB_INTERACTION", B.SHIP)
    B.update(st, "COMB_REGIME", B.REJECT)
    assert B.post_mean(st, "COMB_INTERACTION") > B.post_mean(st, "COMB_REGIME")
    # A partial moves NEITHER posterior (REPLICATION_PENDING is not evidence).
    before = B.post_mean(st, "COMB_REGIME")
    B.update(st, "COMB_REGIME", B.PARTIAL)
    assert abs(B.post_mean(st, "COMB_REGIME") - before) < 1e-12
    assert st.arm("COMB_REGIME")["partials"] == 1


def test_null_ship_freezes_family_in_prioritizer_shape():
    """A planted-null SHIP freezes the family, and the emitted ledger is read by the REAL
    prioritizer.frozen_families (tests-mirror-real: no parallel freeze rule)."""
    from scripts.platformkit.improve.prioritizer import frozen_families as real_frozen
    st = B.BanditState()
    B.update(st, "COMB_INTERACTION", B.SHIP, is_null=True)
    assert B.is_frozen(st, "COMB_INTERACTION") is True
    led = B.frozen_ledger(st)
    assert "COMB_INTERACTION" in real_frozen(led)
    # A frozen family sinks LAST in the deterministic draw order.
    order = B.family_order(st, ["COMB_INTERACTION", "COMB_REGIME"])
    assert order[-1] == "COMB_INTERACTION"


def test_persistence_roundtrip_and_resume_lossless(tmp_path):
    p = str(tmp_path / "combo" / "state.json")
    st = B.BanditState()
    B.update(st, "COMB_REGIME", B.SHIP)
    B.update(st, "COMB_REGIME", B.REJECT)
    B.update(st, "COMB_INTERACTION", B.SHIP, is_null=True)
    B.save_state(st, p)
    st2 = B.load_state(p)
    assert st2.arm("COMB_REGIME")["ships"] == 1
    assert st2.arm("COMB_REGIME")["rejects"] == 1
    assert B.is_frozen(st2, "COMB_INTERACTION") is True
    # enum_ledger zeroes a frozen family's passes so it sinks in the enum ranking too.
    led = B.enum_ledger(st2)
    assert led["COMB_INTERACTION"][0] == 0


def test_family_order_deterministic_on_restart(tmp_path):
    p = str(tmp_path / "s.json")
    st = B.BanditState()
    B.update(st, "COMB_REGIME", B.SHIP)
    B.save_state(st, p)
    o1 = B.family_order(B.load_state(p), ["COMB_INTERACTION", "COMB_REGIME", "COMB_DETAIL_x_DETAIL"])
    o2 = B.family_order(B.load_state(p), ["COMB_INTERACTION", "COMB_REGIME", "COMB_DETAIL_x_DETAIL"])
    assert o1 == o2  # pure function of persisted ledger -- restart re-derives identical order
    assert o1[0] == "COMB_REGIME"  # the one ship floats to the top
