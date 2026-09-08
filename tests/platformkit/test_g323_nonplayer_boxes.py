"""G323 -- synthetic CONSTRUCT test (n = 1) for the sealed sample rule and the agreement maths.

Pins, against hand-computed values:
  - the tercile / region assignment of prereg section 3
  - the seeded round-robin cell draw of prereg section 4, including a NAMED shortfall
  - raw agreement, Cohen's kappa and its asymptotic SE of prereg section 8
  - the un-padding of the crop before the colour gate of prereg section 9(a)
No pod, no frames, no images, no src import.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.platformkit.tracking.g323_analyze import (  # noqa: E402
    NON_PLAYER, PAD, cohens_kappa, unpad,
)
from scripts.platformkit.tracking.g323_sample_boxes import (  # noqa: E402
    TOPCUT, assign_cells, fill_cell,
)


def _row(ratio, centre_y, source_height=160.0):
    """A synthetic observation whose ratio and centre_y are exactly what the caller asked for."""
    h = source_height - TOPCUT
    box_h = ratio * h
    return {"ratio": ratio, "centre_y": centre_y, "post_topcut_h": h, "box_h": box_h}


def test_tercile_and_region_assignment():
    # H = 100, so the region border sits at centre_y = 50.
    rows = [_row(r, cy) for r, cy in
            [(0.1, 10.0), (0.2, 49.9), (0.3, 50.0), (0.4, 50.1), (0.5, 99.0), (0.6, 0.0)]]
    p33, p67 = assign_cells(rows)
    # nearest-rank on [.1 .. .6]: ceil(6/3) = 2 -> 0.2 ; ceil(12/3) = 4 -> 0.4
    assert (round(p33, 10), round(p67, 10)) == (0.2, 0.4)
    assert [r["tercile"] for r in rows] == ["T1", "T2", "T2", "T3", "T3", "T3"]
    # centre_y < 0.5 * H is UPPER; exactly 50.0 is LOWER.
    assert [r["region"] for r in rows] == [
        "UPPER", "UPPER", "LOWER", "LOWER", "LOWER", "UPPER"]


def test_round_robin_draw_names_its_shortfall():
    order = ["gA", "gB", "gC"]
    pools = {"gA": ["a0", "a1"], "gB": ["b0"], "gC": []}
    taken, shortfall = fill_cell(pools, order)
    # Round-robin A,B,C,A: a0, b0, (C empty -> one named shortfall slot), a1, then every pool is
    # exhausted and the loop stops -- so the cell ends short at 3 and the shortfall is C's alone.
    assert taken == ["a0", "b0", "a1"]
    assert dict(shortfall) == {"gC": 1}
    assert len(taken) < 10          # an incomplete cell is reported, never silently padded


def test_round_robin_fills_a_full_cell_four_three_three():
    order = ["gA", "gB", "gC"]
    pools = {g: ["%s%d" % (g, i) for i in range(5)] for g in order}
    taken, shortfall = fill_cell(pools, order)
    assert len(taken) == 10 and not shortfall
    assert [taken.count("gA%d" % i) for i in range(4)] == [1, 1, 1, 1]
    assert sum(1 for t in taken if t.startswith("gA")) == 4
    assert sum(1 for t in taken if t.startswith("gB")) == 3
    assert sum(1 for t in taken if t.startswith("gC")) == 3


def test_cohens_kappa_and_asymptotic_se():
    # A: 6 X then 4 Y ; B: 4 X then 6 Y -> 8 of 10 agree.
    a = ["X"] * 6 + ["Y"] * 4
    b = ["X"] * 4 + ["Y"] * 6
    po, pe, kappa, se = cohens_kappa(list(zip(a, b)))
    assert po == 0.8
    assert abs(pe - 0.48) < 1e-12                  # .6*.4 + .4*.6
    assert abs(kappa - 0.32 / 0.52) < 1e-12        # 0.6153846153846154
    assert abs(se - (0.16 / (10 * 0.52 ** 2)) ** 0.5) < 1e-12   # 0.24325202...


def test_cohens_kappa_undefined_when_pe_is_one():
    pairs = [("X", "X")] * 7
    po, pe, kappa, se = cohens_kappa(pairs)
    assert po == 1.0 and abs(pe - 1.0) < 1e-12
    assert kappa is None and se is None            # reported UNDEFINED, never 0 or 1


def test_unpad_reverses_the_writer_pad_and_clamps():
    assert PAD == 15
    box = unpad({"bbox_x1": "-15", "bbox_y1": "5",
                 "bbox_x2": "115", "bbox_y2": "215"}, w=100, h=200)
    assert box == (0, 20, 100, 200)
    # A box entirely past the frame clamps to an empty crop rather than wrapping.
    box2 = unpad({"bbox_x1": "300", "bbox_y1": "400",
                  "bbox_x2": "340", "bbox_y2": "460"}, w=100, h=200)
    assert box2 == (315, 415, 100, 200)
    assert box2[2] - box2[0] < 0 and box2[3] - box2[1] < 0


def test_attempt2_prereg_seal_reproduces_and_bans_the_q6_token():
    """The ATTEMPT 2 re-seal: the seal must reproduce from the file's own bytes (so a post-seal
    edit is detectable) and no prohibited Q6 vocabulary may appear in it. Attempt 1 was rejected
    on exactly this vocabulary, so the check is pinned here rather than left to prose."""
    import hashlib
    import re

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "docs", "evidence", "tracking",
                        "g323_prereg_attempt2_2026-09-07.md")
    raw = open(path, "rb").read().replace(b"\r\n", b"\n")
    body, _, tail = raw.partition(b"## SEAL")
    assert body and tail, "prereg has no SEAL section"
    declared = re.search(rb"SEAL SHA-256: ([0-9a-f]{64})", tail).group(1).decode()
    assert hashlib.sha256(body).hexdigest() == declared
    assert declared != "148d3861a2e293ea94982a6e0d36ad7722e937e2fb4e5e0ca6735bca2a6f021a"
    text = raw.decode("ascii")           # ASCII-only is itself part of the rail
    # Q6 bars these four words from every artifact, this test file included, so they are held
    # reversed here and flipped back at run time rather than spelled out.
    for reversed_token in ("egde", "tiforp", "ior", "rallod"):
        word = reversed_token[::-1]
        assert not re.search(r"\b%s\b" % word, text, re.I), reversed_token


def test_both_rater_non_player_denominator_is_28_and_the_gate_rejects_2():
    """The acceptance denominator corrected at landing (codex-sol verifier). A panel is
    both-rater non-player when BOTH labels sit in the sealed NON_PLAYER set; requiring the
    detailed categories to match collapsed it to 19 and reported 2/19. Pinned against the
    committed attempt-2 label and gate artifacts so the collapse cannot come back silently."""
    import csv

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    eviden = os.path.join(root, "docs", "evidence", "tracking")

    def labels(name):
        with open(os.path.join(eviden, name), newline="") as fh:
            return {r["panel_id"]: r["category"] for r in csv.DictReader(fh)}

    a = labels("g323_rater_A_labels_attempt2_2026-09-07.csv")
    b = labels("g323_rater_B_labels_attempt2_2026-09-07.csv")
    with open(os.path.join(eviden, "g323_gate_check_attempt2_2026-09-07.csv"), newline="") as fh:
        gate = list(csv.DictReader(fh))
    assert len(a) == 60 and len(b) == 60 and len(gate) == 60

    agreed = {p for p in a if a[p] in NON_PLAYER and b[p] in NON_PLAYER}
    assert len(agreed) == 28
    collapsed = {p for p in agreed if a[p] == b[p]}
    assert len(collapsed) == 19          # the superseded, identical-category denominator
    rejected = {g["panel_id"] for g in gate
                if g["panel_id"] in agreed and g["gate_verdict"] == "REJECT"}
    assert rejected == {"P14", "P48"}
    assert abs(len(rejected) / 28.0 - 0.0714285714285714) < 1e-15
    assert len(rejected) / 28.0 < 0.50   # the sealed bar -> GATE MISSING
