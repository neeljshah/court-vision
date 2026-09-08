"""G304 attempt 2 -- recompute the preregistered agreement statistics from the committed CSVs.

Pins the rating schema, the 756 x 2 row count, both ACCEPT counts, the both-ACCEPT count that
decides the packet, Cohen's kappa, the adjudicated disagreement set and the E1-ready frame count.
Reads committed evidence only; imports nothing from `src/`, `domains/` or `kernel/`.
"""
from __future__ import annotations

import csv
import pathlib

EVID = pathlib.Path(__file__).resolve().parents[3] / "docs" / "evidence" / "tracking"
MANIFEST = EVID / "g304_crop_manifest_2026-09-07.csv"
PROPOSALS = EVID / "g304_proposals_2026-09-07.csv"
RATER_A = EVID / "g304_ratings_codex_2026-09-07.csv"
RATER_B = EVID / "g304_ratings_codex_gpt5_2026-09-07.csv"
ADJUDICATION = EVID / "g304_adjudication2_2026-09-07.csv"

RATING_COLUMNS = ["row_id", "proposal_id", "decision", "nudge_dx", "nudge_dy", "reason_code"]
REASON_CODES = {"ON_LANDMARK", "NUDGED", "WRONG_FEATURE", "NOT_VISIBLE", "OCCLUDED",
                "NOT_A_LINE", "OFF_BY_TOO_MUCH"}
FRAME_RULE_LANDMARKS = 6
FRAME_RULE_STRUCTURES = 3


def _read(path: pathlib.Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_both_rating_sheets_match_the_manifest_schema_and_row_count() -> None:
    manifest = _read(MANIFEST)
    assert len(manifest) == 756
    for path in (RATER_A, RATER_B):
        rows = _read(path)
        assert len(rows) == 756, path.name
        assert list(rows[0].keys()) == RATING_COLUMNS, path.name
        assert [r["proposal_id"] for r in rows] == [m["proposal_id"] for m in manifest]
        assert [r["row_id"] for r in rows] == [m["row_id"] for m in manifest]
        assert all(r["decision"] in ("ACCEPT", "REJECT") for r in rows)
        assert all(r["reason_code"] in REASON_CODES for r in rows)
        for r in rows:
            assert abs(int(r["nudge_dx"])) <= 8 and abs(int(r["nudge_dy"])) <= 8
            if int(r["nudge_dx"]) or int(r["nudge_dy"]):
                assert r["reason_code"] == "NUDGED"


def test_accept_counts_and_the_both_accept_count_that_decides_the_packet() -> None:
    a = {r["proposal_id"]: r["decision"] for r in _read(RATER_A)}
    b = {r["proposal_id"]: r["decision"] for r in _read(RATER_B)}
    assert sum(1 for v in a.values() if v == "ACCEPT") == 4
    assert sum(1 for v in b.values() if v == "ACCEPT") == 9
    both = [k for k in a if a[k] == "ACCEPT" and b[k] == "ACCEPT"]
    assert both == []


def test_cohens_kappa_recomputed_from_the_committed_sheets() -> None:
    a = {r["proposal_id"]: r["decision"] for r in _read(RATER_A)}
    b = {r["proposal_id"]: r["decision"] for r in _read(RATER_B)}
    ids = sorted(a)
    n = len(ids)
    assert n == 756
    agree = sum(1 for k in ids if a[k] == b[k])
    assert agree == 743
    p_o = agree / n
    pa = sum(1 for k in ids if a[k] == "ACCEPT") / n
    pb = sum(1 for k in ids if b[k] == "ACCEPT") / n
    p_e = pa * pb + (1 - pa) * (1 - pb)
    kappa = (p_o - p_e) / (1 - p_e)
    assert abs(p_o - 0.9828042328) < 1e-9
    assert abs(kappa - (-0.0073796)) < 1e-6
    # Climate Pledge Arena is a degenerate cell: both raters REJECT all 408, so kappa is undefined.
    climate = [k for k in ids if k.startswith("wnba_04")]
    assert len(climate) == 408
    assert all(a[k] == "REJECT" and b[k] == "REJECT" for k in climate)


def test_adjudication_covers_exactly_the_disagreement_set() -> None:
    a = {r["proposal_id"]: r["decision"] for r in _read(RATER_A)}
    b = {r["proposal_id"]: r["decision"] for r in _read(RATER_B)}
    disagreements = sorted(k for k in a if a[k] != b[k])
    adj = _read(ADJUDICATION)
    assert len(adj) == 13
    assert sorted(r["proposal_id"] for r in adj) == disagreements
    assert all(r["adjudicator"] == "Claude Opus 5 (MODEL)" for r in adj)
    verdicts = [r["adjudication"] for r in adj]
    assert verdicts.count("ACCEPT") == 0
    assert verdicts.count("REJECT") == 10
    assert verdicts.count("UNRESOLVED") == 3
    assert all(r["rater_A"] == a[r["proposal_id"]] for r in adj)
    assert all(r["rater_B"] == b[r["proposal_id"]] for r in adj)


def test_no_frame_reaches_the_e1_ready_rule_even_counting_every_split_accept() -> None:
    """A landmark needs both raters; the generous counterfactual still cannot fill a frame."""
    proposals = {r["proposal_id"]: r for r in _read(PROPOSALS)}
    a = {r["proposal_id"]: r["decision"] for r in _read(RATER_A)}
    b = {r["proposal_id"]: r["decision"] for r in _read(RATER_B)}
    structures = {
        "CORNER_NEAR_L": "court_corner", "CORNER_NEAR_R": "court_corner",
        "CORNER_FAR_L": "court_corner", "CORNER_FAR_R": "court_corner",
        "LANE_BASE_L": "lane_boundary", "LANE_BASE_R": "lane_boundary",
        "FT_LINE_L": "lane_boundary", "FT_LINE_R": "lane_boundary",
        "KEY_TOP": "free_throw_line",
        "THREE_PT_BASE_L": "three_point_arc", "THREE_PT_BASE_R": "three_point_arc",
        "CENTER_SIDELINE_NEAR": "midcourt_line", "CENTER_SIDELINE_FAR": "midcourt_line",
        "CENTER_CIRCLE_TOP": "center_circle", "CENTER_CIRCLE_BOTTOM": "center_circle",
    }

    def ready(keep) -> int:
        per_frame: dict[str, list[str]] = {}
        for pid in keep:
            row = proposals[pid]
            per_frame.setdefault(row["row_id"], []).append(row["landmark_name"])
        good = 0
        for names in per_frame.values():
            if len(names) >= FRAME_RULE_LANDMARKS and \
                    len({structures[n] for n in names}) >= FRAME_RULE_STRUCTURES:
                good += 1
        return good

    strict = [k for k in a if a[k] == "ACCEPT" and b[k] == "ACCEPT"]
    generous = [k for k in a if a[k] == "ACCEPT" or b[k] == "ACCEPT"]
    assert strict == []
    assert ready(strict) == 0
    assert len(generous) == 13
    assert ready(generous) == 0
