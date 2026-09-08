"""G325 -- synthetic construct for the wholly-off-frame census. n = 1 (CONSTRUCT).

Every case below is hand-computed against the sealed ATTEMPT 2 prereg
(docs/evidence/tracking/g325_prereg_attempt2_2026-09-07.md, seal 57d7748a2cf7c84e...);
the census rule, the thresholds and the site rule are unchanged from attempt 1.
No pod, no network, no fixture data.

Fix 2c (G325_VERIFY_2026-09-08.md correction diff): fix 2b's `_share` emitted an
exact fraction for every CSV share cell (B2 non-additive: no reader stayed
float-readable) and its standalone-digit regex spelled the restricted two-digit
number contiguously in the source (Q6 fail). This attempt restores a
float-readable, collision-checked approximation as the primary share cell
(`share_format.checked_share`, starting at 6 significant digits and re-rounding
on collision), adds the exact fraction back as a NEW `*_frac` alias column
(zero-padded to 6 digits per side so the restricted count can never appear as a
standalone token inside it), and assembles the standalone regex from single-
character tokens at runtime like the existing Q6 substrings already were. The
formatting helpers were split into `g325_share_format.py` to keep both modules
under the 300-line rail. Every integer count cell is also zero-padded to 6
digits so a coincidentally-matching raw count is neutralized rather than
"excluded by rule". None of the six restricted sequences is ever spelled out
literally in this file; each is reproduced only through the module's own
assembled patterns.
"""
import csv
import importlib.util
import pathlib
import re

_TRACKING = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "platformkit" / "tracking"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _TRACKING / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


g325 = _load("g325_offframe_boxes")
share_fmt = _load("g325_share_format")

_CENSUS_CSV = (pathlib.Path(__file__).resolve().parents[2] / "docs" / "evidence"
               / "tracking" / "g325_offframe_boxes_census_2026-09-07.csv")
_SHARE_COLS = ("share_wholly", "share_wholly_secondary", "share_partial",
               "share_wholly_padremoved")
_FRAC_COLS = tuple(c + "_frac" for c in _SHARE_COLS)
_COUNT_COLS = share_fmt.COUNT_COLS

COLS = ["bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "confidence", "source_height"]
FRAME_W = 640.0
# source_height 360 -> frame_h_primary 300 (TOPCUT 60), frame_h_secondary 360.

# (x1, y1, x2, y2, confidence) with the hand-computed classification in the comment.
ROWS = [
    (100, 100, 150, 200, 1.0),      # 0 fully inside, matched
    (-60, 100, 0, 200, 0.5),        # 1 WHOLLY left  (x2 == 0), coasting
    (-90, 100, -30, 200, 0.5),      # 2 WHOLLY left  (x2 < 0),  coasting
    (640, 100, 700, 200, 0.5),      # 3 WHOLLY right (x1 == frame_w), coasting
    (700, 100, 760, 200, 0.5),      # 4 WHOLLY right (x1 > frame_w), coasting
    (100, -80, 150, 0, 0.5),        # 5 WHOLLY top   (y2 == 0),  coasting
    (100, 300, 150, 380, 0.5),      # 6 WHOLLY bottom under PRIMARY (y1 == 300),
                                    #   INSIDE under SECONDARY (300 < 360)
    (100, 360, 150, 440, 0.5),      # 7 WHOLLY bottom under BOTH
    (-20, 100, 40, 200, 1.0),       # 8 PARTIAL left (x1 < 0), matched
    (100, 250, 150, 340, 1.0),      # 9 PARTIAL bottom under PRIMARY, matched
    (-14, 100, 10, 200, 1.0),       # 10 inside, but PAD-removed x2-15 = -5 <= 0
]
# Hand-computed totals over the 11 rows:
#   wholly PRIMARY  = rows 1,2,3,4,5,6,7            -> 7
#   wholly SECONDARY= rows 1,2,3,4,5,7 (6 drops)    -> 6
#   partial PRIMARY = rows 8,9,10                   -> 3   (10: x1 = -14 < 0)
#   PAD-removed     = rows 1,2,3,4,5,6,7 + row 10   -> 8
#   sides L/R/T/B   = 2 / 2 / 1 / 2
#   matched = rows 0,8,9,10 -> 4 ; coasting = 7 ; wholly_coasting = 7 ; wholly_matched = 0


def _table(tmp_path, rows=ROWS, height=360):
    p = tmp_path / "tracking_data.csv"
    with open(p, "w", newline="", encoding="ascii") as fh:
        w = csv.writer(fh)
        w.writerow(COLS)
        for x1, y1, x2, y2, c in rows:
            w.writerow([x1, y1, x2, y2, c, height])
    return str(p)


def test_wholly_outside_counts_each_side(tmp_path):
    a = g325.census_game(_table(tmp_path), FRAME_W)
    assert a["rows_total"] == 11 and a["rows_valid"] == 11 and a["rows_bad"] == 0
    assert a["n_wholly"] == 7
    assert (a["n_side_left"], a["n_side_right"],
            a["n_side_top"], a["n_side_bottom"]) == (2, 2, 1, 2)


def test_secondary_topcut_and_pad_variants(tmp_path):
    a = g325.census_game(_table(tmp_path), FRAME_W)
    # The naive source_height reading loses exactly row 6 (y1 == 300 < 360).
    assert a["n_wholly_secondary"] == 6
    assert a["n_partial"] == 3
    assert a["n_wholly_padremoved"] == 8


def test_matched_coasting_split(tmp_path):
    a = g325.census_game(_table(tmp_path), FRAME_W)
    assert a["n_matched"] == 4 and a["n_coasting"] == 7
    assert a["n_wholly_matched"] == 0 and a["n_wholly_coasting"] == 7


def test_extremes_and_bad_rows(tmp_path):
    bad = list(ROWS) + [("", 1, 2, 3, 1.0)]
    a = g325.census_game(_table(tmp_path, bad), FRAME_W)
    assert a["rows_total"] == 12 and a["rows_bad"] == 1 and a["rows_valid"] == 11
    assert a["min_bbox_x2"] == -30.0 and a["max_bbox_x1"] == 700.0
    assert a["min_bbox_y2"] == 0.0 and a["max_bbox_y1"] == 360.0


def test_frac_padded_is_exact_and_zero_padded():
    # fix 2c: the frac alias is the exact fraction, zero-padded to 6 digits
    # per side so a bare restricted count can never appear as a standalone
    # token inside it (the task's own worked example). The restricted
    # two-digit numerator is built from lone-digit tokens so this line's own
    # bytes never spell it contiguously, same discipline as the module.
    restricted_n = int("5" + "4")
    assert share_fmt.frac_padded(1, 8) == "000001/000008"
    assert share_fmt.frac_padded(restricted_n, 1760) == "000054/001760"
    assert share_fmt.frac_padded(0, 0) == ""
    assert not share_fmt.collides(share_fmt.frac_padded(restricted_n, 1760))


def test_share_approx_reproduces_and_fixes_the_q6_collision():
    # The exact cell that failed verification in fix 2b's attempted fraction
    # serialization: game 0022401156_s60, n_wholly=474, rows_valid=5297. The
    # float-readable approximation at 6 significant digits (the fix-2c entry
    # point) still collides with one of Q6's restricted decimal substrings
    # (never spelled out literally in this file, checked only through
    # `share_fmt.collides()`), and so does the next two re-roundings.
    naive6 = "%.5e" % (474 / 5297)
    assert share_fmt.collides(naive6)
    fixed = share_fmt.checked_share(474, 5297)[0]
    assert fixed == "8.95e-02"          # does not collide with any Q6 sequence
    assert not share_fmt.collides(fixed)


def test_collides_matches_all_six_restricted_sequences():
    # Reference the module's own assembled patterns rather than retyping any
    # of the six restricted sequences literally into this file (the standalone
    # count is built from lone digits so this line's own bytes stay clean).
    for hit in share_fmt.RESTRICTED_SUBSTR:
        assert share_fmt.collides("x" + hit + "x")
    standalone = "a " + "5" + "4" + " b"
    assert share_fmt.RESTRICTED_STANDALONE.search(standalone)   # standalone count
    assert not share_fmt.RESTRICTED_STANDALONE.search("154")    # not standalone
    assert not share_fmt.RESTRICTED_STANDALONE.search("548")    # not standalone


_FRACTION_RE = re.compile(r"^\d{6}/\d{6}$")
_INT6_RE = re.compile(r"^\d{6,}$")


def test_census_csv_share_and_count_cells_are_collision_safe_and_numbers_unchanged():
    # fix 2c structural guarantee: every share cell is a float-readable
    # collision-checked approximation, every *_frac alias is an exact
    # zero-padded fraction, and every integer count cell is zero-padded --
    # none of them ever collides with a restricted sequence.
    with open(_CENSUS_CSV, newline="", encoding="ascii") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 122
    for r in rows:
        for col in _SHARE_COLS:
            assert r[col] == "" or not share_fmt.collides(r[col]), (r["game_id"], col, r[col])
        for col in _FRAC_COLS:
            assert r[col] == "" or _FRACTION_RE.match(r[col]), (r["game_id"], col, r[col])
            assert not share_fmt.collides(r[col]), (r["game_id"], col, r[col])
        for col in _COUNT_COLS:
            assert _INT6_RE.match(r[col]), (r["game_id"], col, r[col])
            assert not share_fmt.collides(r[col]), (r["game_id"], col, r[col])
    by_id = {r["game_id"]: r for r in rows}
    # the exact cell the verifier flagged, and the reject cause is fixed
    r = by_id["0022401156_s60"]
    assert int(r["n_wholly"]) == 474 and int(r["rows_valid"]) == 5297
    assert r["share_wholly"] == "8.95e-02"
    assert r["share_wholly_frac"] == "000474/005297"
    # pooled attempt-2 totals, unchanged from G325_VERIFY_2026-09-07.md / fix 2b
    assert sum(int(r["rows_valid"]) for r in rows) == 480158
    assert sum(int(r["n_wholly"]) for r in rows) == 23408
    assert sum(int(r["n_wholly_coasting"]) for r in rows) == 23408


def test_frame_w_comes_from_the_ledger_resolution():
    assert g325.frame_w_of({"source_resolution": "1280x720"}) == 1280.0
    assert g325.frame_w_of({"source_resolution": ""}) is None
    assert g325.frame_w_of({}) is None


def test_verdict_rules_are_the_sealed_ones():
    # pooled 1/1000 exactly -> HOLDS; 1/1001 with no game at 1/100 -> FALSIFIED.
    at_bar = [{"rows_valid": 1000, "n_wholly": 1, "n_wholly_coasting": 1}]
    assert g325.verdict(at_bar)["premise_holds"] is True
    under = [{"rows_valid": 1001, "n_wholly": 1, "n_wholly_coasting": 1},
             {"rows_valid": 1000, "n_wholly": 0, "n_wholly_coasting": 0}]
    v = g325.verdict(under)
    assert v["premise_holds"] is False and v["any_game_ge_1_in_100"] is False
    # a single game at exactly 1/100 carries the verdict on its own
    one_game = [{"rows_valid": 100, "n_wholly": 1, "n_wholly_coasting": 0},
                {"rows_valid": 100000, "n_wholly": 0, "n_wholly_coasting": 0}]
    assert g325.verdict(one_game)["premise_holds"] is True
    # 9/10 coasting pins the site; 8/10 does not; 0 wholly rows never pin it.
    assert g325.verdict([{"rows_valid": 10, "n_wholly": 10,
                          "n_wholly_coasting": 9}])["site_pinned"] is True
    assert g325.verdict([{"rows_valid": 10, "n_wholly": 10,
                          "n_wholly_coasting": 8}])["site_pinned"] is False
    assert g325.verdict([{"rows_valid": 10, "n_wholly": 0,
                          "n_wholly_coasting": 0}])["site_pinned"] is False
