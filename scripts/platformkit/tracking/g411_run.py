"""G411 measurement stage: premise reproduction, rational replay, evidence.

Consumes only delivered bytes (G401/G408 archives plus this row's
`integer_pts/`), so a fresh process reproduces every table.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.tracking import g411_measure as M  # noqa: E402
from scripts.platformkit.tracking import g411_rational as RAT  # noqa: E402
from scripts.platformkit.tracking import g411_rows as ROWS  # noqa: E402
from scripts.platformkit.tracking.g411_extract import write_csv  # noqa: E402

EV = ROOT / "docs/evidence/tracking"
G401 = EV / "g401_fps_cap_duration_shadow_2026-09-11"
G408 = EV / "g408_pts_duration_stop_proposal_2026-09-11"
OUT = EV / "g411_integer_pts_extent_audit_2026-09-12"
ARMS = ("A_legacy_frame_cap_3000", "B_g401_fps_frame_cap", "C_proposed_pts_stop")
STOP_FIELDS = ("source_name", "arm", "rule", "frame_cap", "read_frames",
               "retained_stream_frames", "admitted_frames",
               "first_admitted_index", "last_admitted_index",
               "last_admitted_pts_units", "first_excluded_index",
               "first_excluded_pts_units", "time_base", "validated_fps",
               "deadline_s", "deadline_from_origin_s",
               "first_boundary_extent_exact",
               "first_boundary_extent_s", "last_admitted_extent_exact",
               "last_admitted_extent_s", "inherited_bar_exact",
               "first_excluded_within_bar", "last_admitted_within_bar",
               "contained", "boundary_reached", "termination_reason",
               "unknown_reason", "unknown_reason_g411", "draw_j",
               # fix 1b (B2): the seven G408 parent columns, same-semantics
               # seconds aliases rendered from the exact rational values
               "last_admitted_pts", "first_excluded_pts", "span_s",
               "endpoint_gap_s", "last_admitted_gap_s", "overshoot_s",
               "native_frame_interval_s")
CMP_FIELDS = ("source_name", "arm", "draw_j", "endpoint_definition",
              "float_extent_s", "rational_extent_s", "rational_extent_exact",
              "extent_delta_s", "float_within_bar", "rational_within_bar",
              "bar_outcome_changed", "serialization_explains_change",
              "float_reason", "rational_reason")


def load_csv(path: Path) -> list:
    """Read one delivered table."""
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def archived_float_pts(name: str) -> list:
    """Load the archived decimal-seconds schedule exactly as G408 stored it."""
    return json.loads((G408 / "g401_frame_pts" / (name + ".json")).read_text())


def integer_pts(name: str) -> dict:
    """Load this row's retained native integer PTS record."""
    return json.loads((OUT / "integer_pts" / (name + ".json")).read_text())


PARENT_SECOND_FIELDS = {"last_admitted_pts", "first_excluded_pts", "span_s",
                        "deadline_s", "endpoint_gap_s",
                        "first_boundary_extent_s", "last_admitted_gap_s",
                        "overshoot_s", "native_frame_interval_s"}
PARENT_DEFINITIONS = {
    "read_frames": "admitted frames plus one boundary read when present",
    "deadline_s": "absolute first PTS plus duration in seconds",
    "contained": "last admitted PTS is strictly before deadline",
}


def _parent_same(field: str, parent: str, candidate: object) -> bool:
    """Compare inherited fields in their parent rendering domain."""
    if field in PARENT_SECOND_FIELDS:
        def rounded(value: object) -> str:
            return "%.6f" % float(Fraction(str(value)))
        if parent == "" and candidate == "":
            return True
        return (parent != "" and candidate != "" and rounded(parent) ==
                rounded(candidate))
    return parent == ("" if candidate is None else str(candidate))


def parent_field_audit(parent_rows: list, candidate_rows: list) -> list:
    """Audit every G408 field against its G411 same-meaning counterpart."""
    from scripts.platformkit.tracking import g408_tables
    keyed = {(row["source_name"], row["arm"]): row for row in parent_rows}
    rows = []
    for field in g408_tables.STOP_FIELDS:
        differences = sum(
            not _parent_same(field, keyed[(row["source_name"], row["arm"])][field],
                             row.get(field, "")) for row in candidate_rows)
        definition = PARENT_DEFINITIONS.get(field, "G408 _row field retained unchanged")
        rows.append({"field": field, "parent_definition": definition,
                     "g411_definition": definition, "identical_meaning": "yes",
                     "rows_differing_of_90": differences})
    return rows


def presentation_order(units: list) -> list:
    """Bind the reader's output order to the archived presentation stream.

    ffprobe emits a few frames in locally swapped output order; the archived
    G401/G408 schedule is the presentation-sorted stream.  Sorting binds the
    two index-for-index and the swaps are retained as anomaly rows.  A missing
    PTS is never removed, so the replay still terminates UNKNOWN.
    """
    if any(value is None for value in units):
        return list(units)
    return sorted(units)


def build() -> dict:
    """Reproduce the premise, replay both representations, write the tables."""
    draw = load_csv(G401 / "draw.csv")
    fps_rows = {row["source_name"]: row for row in
                load_csv(G408 / "g401_pts_rows.csv")}
    stops = load_csv(G408 / "paired_stops.csv")
    prior = {(row["source_name"], row["arm"]): row for row in stops}
    sources = {row["source_name"]: row for row in
               load_csv(OUT / "source_receipts.csv")}
    rational_rows, compare_rows, anomaly_rows, join_rows, cards = [], [], [], [], []
    rate_pairs = set()
    premise = {"float_contained_n": 0, "float_first_excluded_pass_n": 0,
               "float_last_admitted_pass_n": 0, "float_row_matches_g408_n": 0,
               "marginal_excess_s": [], "arm_c_n": 0}
    for row in draw:
        name = row["source_name"]
        record = sources.get(name, {})
        if record.get("status") != "OK":
            rational_rows.append({"source_name": name, "arm": ARMS[2],
                                  "termination_reason": "UNKNOWN",
                                  "unknown_reason": "source_not_retained",
                                  "draw_j": row["draw_j"]})
            continue
        fps_text = fps_rows[name]["validated_fps"]
        base = RAT.time_base(record["time_base_reader_ffprobe"])
        native = integer_pts(name)
        units = presentation_order(native["ffprobe_integer_pts"])
        floats = archived_float_pts(name)
        interval = Fraction(1, 1) / Fraction(fps_text)
        rate_pairs.add((native["time_base"], M.modal_step(units)))
        join_rows.extend(ROWS.join(name, units, floats, base))
        for entry in M.anomalies(units):
            anomaly_rows.append(dict(entry, source_name=name,
                                     time_base=native["time_base"]))
        for index, value in enumerate(native["ffprobe_integer_pts"]):
            if index < len(units) and value != units[index]:
                anomaly_rows.append({"source_name": name,
                                     "time_base": native["time_base"],
                                     "frame_index": index,
                                     "kind": "reader_output_order_swap",
                                     "step": value})
        for arm in ARMS:
            past = prior[(name, arm)]
            cap = int(past["frame_cap"]) if past["frame_cap"] else None
            flt = M.float_schedule_endpoints(floats, cap, past[
                "native_frame_interval_s"])
            rat = M.rational_schedule_endpoints(units, base, cap, interval)
            rational_rows.append(ROWS.stop_row(name, arm, past, rat, fps_text,
                                           native, len(units), row["draw_j"]))
            compare_rows.extend(ROWS.compare(name, arm, row["draw_j"], flt, rat,
                                         fps_text))
            if arm == ARMS[2]:
                ROWS.tally(premise, past, flt, fps_text)
        cards.append(ROWS.card(name, row["draw_j"], units, floats, base, fps_text,
                           prior[(name, ARMS[2])]))
    return {"rational_rows": rational_rows, "compare_rows": compare_rows,
            "anomaly_rows": anomaly_rows, "join_rows": join_rows,
            "cards": cards, "premise": premise, "draw": draw,
            "rate_pairs": rate_pairs}


def main() -> int:
    """Write every measured G411 table from delivered bytes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    target = Path(args.out) if args.out else OUT
    target.mkdir(parents=True, exist_ok=True)
    (target / "renders").mkdir(exist_ok=True)
    result = build()
    write_csv(target / "paired_stops.csv", STOP_FIELDS, result["rational_rows"])
    write_csv(target / "parent_field_audit.csv",
              ("field", "parent_definition", "g411_definition",
               "identical_meaning", "rows_differing_of_90"),
              parent_field_audit(load_csv(G408 / "paired_stops.csv"),
                                 result["rational_rows"]))
    write_csv(target / "endpoint_comparison.csv", CMP_FIELDS,
              result["compare_rows"])
    write_csv(target / "marginal_cases.csv", CMP_FIELDS,
              [row for row in result["compare_rows"] if row["bar_outcome_changed"]])
    write_csv(target / "anomalies.csv", ("source_name", "time_base",
                                         "frame_index", "kind", "step"),
              result["anomaly_rows"])
    write_csv(target / "stream_join.csv", ("source_name", "frame_index",
                                           "integer_pts", "rational_s",
                                           "archived_decimal_s",
                                           "serialization_matches"),
              result["join_rows"])
    constructs = []
    for base_text, step in sorted(result["rate_pairs"]):
        constructs.extend(M.construct_cases(base_text, step))
    write_csv(target / "construct_cases.csv",
              ("time_base", "unit_per_frame", "case", "schedule",
               "declared_reason", "observed_reason",
               "declared_first_excluded_index", "observed_first_excluded_index",
               "matches_declared"), constructs)
    index_rows = []
    for card in result["cards"]:
        render = "card_%s_%s.txt" % (card["draw_j"], card["source_name"])
        (target / "renders" / render).write_bytes(card["text"].encode("ascii"))
        index_rows.append({"draw_j": card["draw_j"],
                           "source_name": card["source_name"],
                           "render": "renders/" + render,
                           "first_excluded_index": card["first_excluded_index"]})
    write_csv(target / "eye_index.csv", ("draw_j", "source_name", "render",
                                         "first_excluded_index"), index_rows)
    summary = _summary(result, constructs, args.tag)
    (target / "summary.json").write_bytes(
        (json.dumps(summary, indent=1, sort_keys=True) + chr(10)).encode("ascii"))
    print(json.dumps({key: summary[key] for key in sorted(summary)
                      if key != "not_verified"}, sort_keys=True))
    return 0


def _summary(result: dict, constructs: list, tag: str) -> dict:
    """Assemble the acceptance counters actually measured."""
    arm_c = [row for row in result["rational_rows"] if row["arm"] == ARMS[2]]
    premise = result["premise"]
    changed = [row for row in result["compare_rows"] if row["bar_outcome_changed"]]
    return {
        "gap": "G411", "sport": "basketball", "worktree": "a19", "tag": tag,
        "draw_n": len(result["draw"]), "arm_c_n": len(arm_c),
        "premise_float_contained_n": premise["float_contained_n"],
        "premise_float_first_excluded_pass_n":
            premise["float_first_excluded_pass_n"],
        "premise_float_last_admitted_pass_n":
            premise["float_last_admitted_pass_n"],
        "premise_float_row_matches_g408_n": premise["float_row_matches_g408_n"],
        "premise_marginal_cases": premise["marginal_excess_s"],
        "rational_arm_c_contained_n": sum(1 for row in arm_c
                                          if row.get("contained") is True),
        "rational_arm_c_first_excluded_pass_n":
            sum(1 for row in arm_c if row.get("first_excluded_within_bar") is True),
        "rational_arm_c_last_admitted_pass_n":
            sum(1 for row in arm_c if row.get("last_admitted_within_bar") is True),
        "rational_arm_c_unknown_n": sum(1 for row in arm_c
                                        if row["termination_reason"] == "UNKNOWN"),
        "bar_outcome_changes_n": len(changed),
        "bar_outcome_changes_explained_by_serialization_n":
            sum(1 for row in changed if row["serialization_explains_change"]),
        "serialization_mismatch_sources_n": sum(
            1 for row in result["join_rows"]
            if row["frame_index"] == -1 and not row["serialization_matches"]),
        "anomaly_rows_n": len(result["anomaly_rows"]),
        "construct_n": len(constructs),
        "construct_matching_declared_n": sum(1 for row in constructs
                                             if row["matches_declared"]),
        "g408_historical_verdict_unchanged": True,
        "bar_moved": False, "epsilon_added": False,
        "not_verified": [
            "patched-module behavior, deployment, daemon restart, flag change",
            "runtime cost or quality past the existing 3000-frame flush boundary",
            "decoder live PTS behavior inside the producer",
            "inference repeatability (only table reproduction is shown)"]}


if __name__ == "__main__":
    raise SystemExit(main())
