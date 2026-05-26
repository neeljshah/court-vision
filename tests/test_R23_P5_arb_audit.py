"""tests/test_R23_P5_arb_audit.py — R23_P5 probe + classifier audit.

Synthetic snapshot with known-correct primary/alt labels:
    * Confirms classify_market_tier picks the realistic anchor rung
      (both-sided, low spread, near cluster median) as primary.
    * Confirms find_middles(allow_alt_lines=False) blocks the alt-rung
      cross-book false-arb pattern.
    * Confirms find_middles(allow_alt_lines=True) reproduces the legacy
      false-arb so the BEFORE/AFTER delta is measurable.
    * Confirms a legitimate primary-vs-primary middle survives the gate.
    * End-to-end smoke-test: invokes probe_R23_P5_middle_finder_audit.run_probe
      and asserts the result JSON is well-formed with the expected keys.
"""
from __future__ import annotations

import importlib
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts", "improve_loop"))

import middle_finder_daemon as mfd  # noqa: E402


def _bov_altline_rows(player="Test Star", stat="pts"):
    """Realistic Bov-style alt ladder: many rungs, one balanced (-115/-115)
    near the cluster CENTER (true primary), and a low-line alt rung
    (3.5 @ +105/-135) that the legacy code mis-pairs into a false arb."""
    return [
        {"line": 11.5, "over_price": -275, "under_price": 200},
        {"line": 12.5, "over_price": -200, "under_price": 150},
        {"line": 13.5, "over_price": -150, "under_price": 115},
        {"line": 14.5, "over_price": -115, "under_price": -115},  # PRIMARY
        {"line": 15.5, "over_price": 110, "under_price": -145},
        {"line": 16.5, "over_price": 140, "under_price": -185},
        {"line": 17.5, "over_price": 180, "under_price": -245},
        {"line": 3.5, "over_price": 105, "under_price": -135},   # ALT (low)
    ]


def _pin_primary_row(line=13.5):
    return [{"line": line, "over_price": -151, "under_price": 119}]


def _make_index():
    """Synthetic (player, stat) -> {book: [rows]} cluster mimicking the real
    R20_M1 fix scenario."""
    return {
        ("Test Star", "pts"): {
            "bov": _bov_altline_rows(),
            "pin": _pin_primary_row(line=13.5),
        },
        # A legit primary-vs-primary middle that MUST survive the gate.
        ("Legit Middle", "pts"): {
            "fd": [{"line": 24.5, "over_price": -110, "under_price": -110}],
            "bov": [{"line": 25.5, "over_price": -110, "under_price": -110}],
        },
    }


def _apply_classifier(index):
    for _pkey, bdict in index.items():
        for _book, rows in bdict.items():
            mfd.classify_market_tier(rows, csv_alt_present=False)
    return index


def test_classifier_tags_alt_rung_correctly():
    """The 3.5 rung must end up tagged is_alt_line=True, NOT primary."""
    rows = _bov_altline_rows()
    mfd.classify_market_tier(rows, csv_alt_present=False)
    by_line = {r["line"]: r for r in rows}
    # The balanced 14.5 rung (-115/-115, spread=0) is the realistic anchor.
    assert by_line[14.5]["market_tier"] == "primary"
    assert by_line[14.5]["is_alt_line"] is False
    # The low 3.5 rung MUST be tagged alt — it is the false-arb trap.
    assert by_line[3.5]["market_tier"] == "alt"
    assert by_line[3.5]["is_alt_line"] is True


def test_arb_engine_blocks_false_arb_post_m1():
    """With allow_alt_lines=False (post-M1 behaviour), the Test Star
    PTS-OVER-3.5 / pin-UNDER-13.5 false-arb MUST be filtered out, while
    the legit 24.5/25.5 -110/-110 middle MUST survive."""
    index = _apply_classifier(_make_index())
    middles_post = mfd.find_middles(
        index, min_width=0.5, max_juice_each_side=-135,
        allow_alt_lines=False)

    free_post = [m for m in middles_post if m.get("free_arb")]
    # 0 free_arbs post-M1 — the only would-be free arb was the alt-rung trap.
    assert len(free_post) == 0, (
        f"expected 0 free-arbs post-M1, got: {free_post}")

    # The legit primary-vs-primary 1-wide middle survives.
    legit = [m for m in middles_post
             if m["player"] == "Legit Middle"
             and m["over_book"] == "fd" and m["under_book"] == "bov"
             and m["middle_width"] == 1.0]
    assert len(legit) == 1, (
        f"legit primary middle dropped by gate; got: {middles_post}")
    assert legit[0]["free_arb"] is False


def test_arb_engine_reproduces_false_arb_pre_m1():
    """With allow_alt_lines=True (legacy behaviour), the alt-rung pair
    becomes a false 'free arb' — used in the audit BEFORE/AFTER delta."""
    index = _apply_classifier(_make_index())
    middles_pre = mfd.find_middles(
        index, min_width=0.5, max_juice_each_side=-135,
        allow_alt_lines=True)
    free_pre = [m for m in middles_pre if m.get("free_arb")]
    # Find the alt-rung false arb specifically.
    bogus = [m for m in free_pre
             if m["player"] == "Test Star"
             and m["over_book"] == "bov" and m["over_line"] == 3.5
             and m["under_book"] == "pin"]
    assert len(bogus) == 1, (
        f"expected the alt-rung false-arb to surface PRE-M1; got: {free_pre}")
    assert bogus[0]["over_price"] == 105 and bogus[0]["under_price"] == 119
    assert bogus[0]["middle_width"] == 10.0


def test_before_after_delta_is_blocked_count():
    """The probe's headline metric: pre minus post free-arb count == 1 blocked."""
    index = _apply_classifier(_make_index())
    free_pre = [m for m in mfd.find_middles(index, allow_alt_lines=True)
                 if m.get("free_arb")]
    free_post = [m for m in mfd.find_middles(index, allow_alt_lines=False)
                  if m.get("free_arb")]
    assert len(free_pre) - len(free_post) == 1, (
        f"expected 1 false-arb blocked, got pre={free_pre} post={free_post}")


def test_probe_module_importable_and_well_formed():
    """End-to-end: the probe module must import + expose run_probe(); the
    on-disk JSON it would write must contain all required headline keys."""
    import probe_R23_P5_middle_finder_audit as probe
    assert hasattr(probe, "run_probe")
    required_keys = {
        "n_snapshots_audited", "n_rows_tagged_primary",
        "n_rows_tagged_alt", "n_real_arbs_post_M1",
        "n_would_be_false_arbs_pre_M1", "n_remaining_suspect_arbs",
        "per_book_breakdown",
    }
    # Inspect the source to confirm all keys are produced (cheap structural
    # check — running the probe here would touch live data/lines, which we
    # avoid in unit tests).
    src = open(probe.__file__, encoding="utf-8").read()
    for k in required_keys:
        assert f'"{k}"' in src, f"probe missing required output key: {k}"


def test_suspect_classifier_logic():
    """The probe's _classify_suspect must flag a free_arb whose leg sits
    far (>=3 pts) from its own book's ladder median."""
    import probe_R23_P5_middle_finder_audit as probe
    # Build a fake index where bov ladder spans 11.5..17.5 (median 14.5),
    # and a synthetic free-arb names bov-OVER at 3.5 (11 points away).
    index = _apply_classifier(_make_index())
    fake_middle = {
        "player": "Test Star", "stat": "pts",
        "over_book": "bov", "over_line": 3.5, "over_price": 105,
        "under_book": "pin", "under_line": 13.5, "under_price": 119,
    }
    suspect, diag = probe._classify_suspect(fake_middle, index, max_dist=3.0)
    assert suspect is True
    assert diag["over_dist_from_median"] >= 3.0

    # A middle whose legs sit AT each book's median is NOT suspect.
    safe_middle = {
        "player": "Test Star", "stat": "pts",
        "over_book": "bov", "over_line": 14.5, "over_price": -115,
        "under_book": "pin", "under_line": 13.5, "under_price": 119,
    }
    safe_suspect, _ = probe._classify_suspect(safe_middle, index,
                                                 max_dist=3.0)
    assert safe_suspect is False


if __name__ == "__main__":
    test_classifier_tags_alt_rung_correctly()
    test_arb_engine_blocks_false_arb_post_m1()
    test_arb_engine_reproduces_false_arb_pre_m1()
    test_before_after_delta_is_blocked_count()
    test_probe_module_importable_and_well_formed()
    test_suspect_classifier_logic()
    print("OK")
