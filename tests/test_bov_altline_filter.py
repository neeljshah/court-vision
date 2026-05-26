"""tests/test_bov_altline_filter.py — R20_M1.

Verifies the Bov/FD/Pin alt-line normalizer + arb-engine guard that fixes
the 'PTS OVER 3.5' false-arb bug.

The bug: cross-book arb engine paired Bov ALT 'PTS over 3.5 @ +105' with
Pin PRIMARY 'PTS under 13.5 @ +119' and reported a 5.88% guaranteed free
arb — because the on-disk Bov CSV (and FD/Pin always) lacked the
`is_alt_line` flag. The fix re-classifies tiers at load time via vig
heuristic and the arb engine refuses to pair alt rungs with anything.

Coverage:
  1. classify_market_tier picks the lowest-vig rung as primary on a real
     SGA-style ladder (sanity: classifier correctness).
  2. classify_market_tier marks single-side rungs (no over OR no under
     priced) as alt (single-book all-alt case for FD).
  3. find_middles pairs cross-book primary↔primary (positive control).
  4. find_middles refuses cross-book primary↔alt — the exact PTS-OVER-3.5
     pattern (regression test for the bug).
  5. find_middles handles 'all alt' cluster (no primary rung) — returns
     no middles (no primary leg => nothing to join).
  6. classify_market_tier trusts the CSV column when present
     (csv_alt_present=True) and does NOT re-classify based on vig.
  7. End-to-end load_latest_snapshots → find_middles on a synthetic
     dataset that reproduces the live De'Aaron Fox PTS bug ⇒ zero free
     arbs (vs the buggy baseline of 1+).
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

import middle_finder_daemon as mfd  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — mirror the live de'Aaron Fox PTS bug from data/cache/middles_live.json
# ---------------------------------------------------------------------------

def _sga_pts_ladder_bov():
    """Real Bov ladder shape lifted from data/lines/2026-05-26_bov.csv."""
    return [
        {"line": 25.5, "over_price": -280, "under_price": 205},
        {"line": 26.5, "over_price": -230, "under_price": 170},
        {"line": 27.5, "over_price": -185, "under_price": 140},
        {"line": 28.5, "over_price": -150, "under_price": 115},
        {"line": 29.5, "over_price": -125, "under_price": -105},  # PRIMARY
        {"line": 30.5, "over_price": -105, "under_price": -125},
        {"line": 31.5, "over_price": 115,  "under_price": -150},
        {"line": 32.5, "over_price": 135,  "under_price": -180},
        {"line": 33.5, "over_price": 160,  "under_price": -215},
        {"line": 34.5, "over_price": 190,  "under_price": -260},
        {"line": 6.5,  "over_price": -125, "under_price": -105},  # bogus tier?
    ]


def _fox_pts_ladder_bov():
    """De'Aaron Fox PTS ladder — produces the live bug. Lower rung 3.5 has
    over=+105/under=-160 in real data; here we mirror that ratio so the
    vig sentinel picks the correct primary, while preserving the bogus-arb
    bait that the live system fell for. The 13.5 rung is the most-balanced
    rung (spread → 0), so the classifier crowns it primary."""
    return [
        {"line": 3.5,  "over_price": 105,  "under_price": -160},  # ALT (heavy under-juice)
        {"line": 11.5, "over_price": -185, "under_price": 140},   # ALT
        {"line": 13.5, "over_price": -110, "under_price": -110},  # PRIMARY (most balanced)
        {"line": 15.5, "over_price": 120,  "under_price": -160},  # ALT
        {"line": 17.5, "over_price": 160,  "under_price": -215},  # ALT
    ]


# ---------------------------------------------------------------------------
# 1) classifier correctness on a real ladder
# ---------------------------------------------------------------------------

class TestClassifyMarketTierBasic(unittest.TestCase):

    def test_sga_ladder_primary_is_balanced_rung(self):
        rows = _sga_pts_ladder_bov()
        mfd.classify_market_tier(rows, csv_alt_present=False)
        primaries = [r for r in rows if r["market_tier"] == "primary"]
        self.assertEqual(len(primaries), 1,
                         f"exactly one primary expected, got {primaries}")
        prim = primaries[0]
        # Real ladder primary should be the balanced -125/-105 rung
        # (lowest absolute vig).
        self.assertEqual(prim["line"], 29.5,
                         f"primary should be 29.5 (balanced rung); got {prim}")
        self.assertTrue(prim["over_price"] is not None
                         and prim["under_price"] is not None,
                         "primary must have both sides priced")
        # All other rungs become alts.
        alts = [r for r in rows if r["market_tier"] == "alt"]
        self.assertEqual(len(alts), len(rows) - 1)
        for r in alts:
            self.assertTrue(r["is_alt_line"])

    def test_single_rung_is_primary_by_default(self):
        rows = [{"line": 25.5, "over_price": -110, "under_price": -110}]
        mfd.classify_market_tier(rows, csv_alt_present=False)
        self.assertEqual(rows[0]["market_tier"], "primary")
        self.assertFalse(rows[0]["is_alt_line"])


# ---------------------------------------------------------------------------
# 2) single-book all-alt: FD often emits OVER-only rows (no under price).
# ---------------------------------------------------------------------------

class TestSingleSideRungsAreAlt(unittest.TestCase):

    def test_fd_over_only_ladder_classified_alt(self):
        # FD writes a typical alt ladder where over_price is set but
        # under_price is missing. None of these can be primary.
        rows = [
            {"line": 19.5, "over_price": -1600, "under_price": None},
            {"line": 24.5, "over_price": -330,  "under_price": None},
            {"line": 29.5, "over_price": -108,  "under_price": None},
            {"line": 34.5, "over_price": 260,   "under_price": None},
        ]
        mfd.classify_market_tier(rows, csv_alt_present=False)
        # With no rung priced on both sides, classifier must mark them ALL
        # as alt (defensive default — no clean primary exists, so the arb
        # engine can't safely cross-book pair them).
        tiers = {r["market_tier"] for r in rows}
        self.assertEqual(tiers, {"alt"},
                         f"all single-side rungs should be alt; got {rows}")

    def test_mixed_ladder_picks_two_sided_primary(self):
        # Two-sided rung exists alongside one-sided rungs => it wins primary.
        rows = [
            {"line": 19.5, "over_price": -1600, "under_price": None},
            {"line": 24.5, "over_price": -330,  "under_price": None},
            {"line": 29.5, "over_price": -110,  "under_price": -110},  # PRIMARY
            {"line": 34.5, "over_price": 260,   "under_price": None},
        ]
        mfd.classify_market_tier(rows, csv_alt_present=False)
        prims = [r for r in rows if r["market_tier"] == "primary"]
        self.assertEqual(len(prims), 1)
        self.assertEqual(prims[0]["line"], 29.5)


# ---------------------------------------------------------------------------
# 3) Positive control: cross-book primary↔primary still produces middles.
# ---------------------------------------------------------------------------

class TestPrimaryPrimaryJoinWorks(unittest.TestCase):

    def test_primary_primary_classic_middle(self):
        # FD OVER 28.5 / Bov UNDER 29.5 — both primary, classic 1-wide
        # middle. This is the BENIGN case that we must NOT break.
        index = {
            ("LeBron James", "pts"): {
                "fd":  [{"line": 28.5, "over_price": -110,
                          "under_price": -110, "market_tier": "primary",
                          "is_alt_line": False}],
                "bov": [{"line": 29.5, "over_price": -110,
                          "under_price": -110, "market_tier": "primary",
                          "is_alt_line": False}],
            }
        }
        middles = mfd.find_middles(index, min_width=0.5,
                                     max_juice_each_side=-135)
        self.assertTrue(any(m["over_book"] == "fd"
                             and m["under_book"] == "bov"
                             and m["middle_width"] == 1.0
                             for m in middles),
                        f"primary↔primary middle missing: {middles}")


# ---------------------------------------------------------------------------
# 4) REGRESSION: cross-book primary↔alt is skipped (the bug fix).
# ---------------------------------------------------------------------------

class TestPrimaryAltJoinIsSkipped(unittest.TestCase):

    def test_pts_over_3_5_false_arb_blocked(self):
        # Reproduce the live bug: Bov ALT 'OVER 3.5 @ +105' paired with
        # Pin PRIMARY 'UNDER 13.5 @ +119' previously fired as a free arb.
        # With the fix, the Bov alt rung is filtered out → 0 middles.
        index = {
            ("De'Aaron Fox", "pts"): {
                "bov": [
                    {"line": 3.5,  "over_price": 105,  "under_price": -160,
                     "market_tier": "alt", "is_alt_line": True},
                    {"line": 13.5, "over_price": -125, "under_price": -105,
                     "market_tier": "primary", "is_alt_line": False},
                ],
                "pin": [
                    {"line": 13.5, "over_price": -113, "under_price": 119,
                     "market_tier": "primary", "is_alt_line": False},
                ],
            }
        }
        middles = mfd.find_middles(index, min_width=0.5,
                                     max_juice_each_side=-135)
        # The ALT OVER 3.5 must never appear in middles.
        bogus = [m for m in middles
                 if m["over_book"] == "bov" and m["over_line"] == 3.5]
        self.assertEqual(bogus, [],
                         f"ALT OVER 3.5 leaked into middles: {bogus}")
        # And specifically: zero free arbs (the original symptom).
        free = [m for m in middles if m.get("free_arb")]
        self.assertEqual(free, [],
                         f"PTS-OVER-3.5 false-arb regression: {free}")

    def test_opt_in_allow_alt_lines_restores_buggy_behavior(self):
        # Sanity: caller can still opt into alt-lines for research, but
        # the default is primary-only (the safe path).
        index = {
            ("De'Aaron Fox", "pts"): {
                "bov": [
                    {"line": 3.5, "over_price": 105, "under_price": -160,
                     "market_tier": "alt", "is_alt_line": True},
                ],
                "pin": [
                    {"line": 13.5, "over_price": -113, "under_price": 119,
                     "market_tier": "primary", "is_alt_line": False},
                ],
            }
        }
        # Default (safe): zero middles.
        safe = mfd.find_middles(index, min_width=0.5,
                                  max_juice_each_side=-135)
        self.assertEqual(safe, [])
        # Opt-in: the alt-rung pair surfaces (legacy buggy behavior).
        unsafe = mfd.find_middles(index, min_width=0.5,
                                    max_juice_each_side=-135,
                                    allow_alt_lines=True)
        self.assertTrue(len(unsafe) >= 1,
                        "opt-in should restore old behavior")


# ---------------------------------------------------------------------------
# 5) Edge case: only alt lines available — no primary anywhere → no middles.
# ---------------------------------------------------------------------------

class TestAllAltCluster(unittest.TestCase):

    def test_only_alt_lines_yields_no_middles(self):
        # Both books only offer the alt rungs (no balanced primary). The
        # safe behavior is to return zero middles rather than guess.
        index = {
            ("Chet Holmgren", "pts"): {
                "bov": [
                    {"line": 3.5, "over_price": 105, "under_price": -160,
                     "market_tier": "alt", "is_alt_line": True},
                    {"line": 4.5, "over_price": 130, "under_price": -180,
                     "market_tier": "alt", "is_alt_line": True},
                ],
                "pin": [
                    {"line": 5.5, "over_price": 110, "under_price": -150,
                     "market_tier": "alt", "is_alt_line": True},
                ],
            }
        }
        middles = mfd.find_middles(index, min_width=0.5,
                                     max_juice_each_side=-135)
        self.assertEqual(middles, [],
                         f"all-alt cluster should produce no middles: {middles}")


# ---------------------------------------------------------------------------
# 6) classify_market_tier honors the CSV column when present.
# ---------------------------------------------------------------------------

class TestCsvAltColumnTrusted(unittest.TestCase):

    def test_csv_present_trusts_writer(self):
        # Writer flagged is_alt_line: classifier must NOT re-derive based
        # on vig — it must accept whatever the writer said.
        rows = [
            {"line": 25.5, "over_price": -110, "under_price": -110,
             "is_alt_line": True},   # writer says ALT (e.g. policy override)
            {"line": 29.5, "over_price": -180, "under_price": 140,
             "is_alt_line": False},  # writer says PRIMARY (heavy vig anyway)
        ]
        mfd.classify_market_tier(rows, csv_alt_present=True)
        # First row stays alt (would have been heuristic-primary).
        self.assertEqual(rows[0]["market_tier"], "alt")
        self.assertTrue(rows[0]["is_alt_line"])
        # Second row stays primary (would have been heuristic-alt).
        self.assertEqual(rows[1]["market_tier"], "primary")
        self.assertFalse(rows[1]["is_alt_line"])


# ---------------------------------------------------------------------------
# 7) End-to-end: synthetic on-disk CSVs (legacy 10-col shape) → load → arb.
# ---------------------------------------------------------------------------

class TestEndToEndCsvLoadArbGuard(unittest.TestCase):

    def _write_csv(self, path, rows_with_header):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerows(rows_with_header)

    def test_legacy_csvs_classified_and_no_false_arb(self):
        # Recreate the live 2026-05-26 bug with synthetic legacy 10-col
        # CSVs (no is_alt_line column) for bov + pin + fd. Expect:
        # find_middles returns zero free_arbs after load-time classifier
        # tags the bov alt rungs.
        date = "2026-05-26"
        with tempfile.TemporaryDirectory() as td:
            hdr = ["captured_at", "book", "game_id", "player_id",
                   "player_name", "stat", "line", "over_price",
                   "under_price", "start_time"]
            ts = "2026-05-26T15:00:00"

            # Bov: full PTS ladder for De'Aaron Fox (alts + one primary)
            bov_rows = [hdr]
            for r in _fox_pts_ladder_bov():
                bov_rows.append([ts, "bov", "g1", "", "De'Aaron Fox", "pts",
                                  r["line"], r["over_price"],
                                  r["under_price"], "2026-05-27T00:00:00"])
            self._write_csv(os.path.join(td, f"{date}_bov.csv"), bov_rows)

            # Pin: single primary line at 13.5 (the leg the bug joined).
            pin_rows = [
                hdr,
                [ts, "pin", "g1", "", "De'Aaron Fox", "pts", 13.5,
                  -113, 119, "2026-05-27T00:00:00"],
            ]
            self._write_csv(os.path.join(td, f"{date}_pin.csv"), pin_rows)

            # FD: empty so we don't muddle the test.
            self._write_csv(os.path.join(td, f"{date}_fd.csv"), [hdr])

            index = mfd.load_latest_snapshots(date, lines_dir=td,
                                                books=("fd", "bov", "pin"))
            # Verify the Bov 3.5 rung was tagged ALT by the classifier.
            bov_rows_idx = index[("De'Aaron Fox", "pts")]["bov"]
            r35 = next(r for r in bov_rows_idx if r["line"] == 3.5)
            self.assertEqual(r35["market_tier"], "alt",
                             f"Bov 3.5 rung must be ALT after classify; got {r35}")
            # And the 13.5 rung is primary.
            r135 = next(r for r in bov_rows_idx if r["line"] == 13.5)
            self.assertEqual(r135["market_tier"], "primary",
                             f"Bov 13.5 rung must be PRIMARY; got {r135}")
            # Now the arb engine: zero false arbs.
            middles = mfd.find_middles(index, min_width=0.5,
                                         max_juice_each_side=-135)
            free = [m for m in middles if m.get("free_arb")]
            # Specifically no PTS-OVER-3.5 leak.
            for m in middles:
                self.assertFalse(
                    m["over_book"] == "bov" and m["over_line"] == 3.5,
                    f"bug regression: alt-rung 3.5 still leaks: {m}")
            self.assertEqual(free, [],
                             f"false-arb regression at e2e level: {free}")


if __name__ == "__main__":
    unittest.main()
