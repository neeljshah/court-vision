"""Run G336's binding premise and, only when it holds, its sealed comparison."""
from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from scripts.platformkit.tracking.g310_instance_key import _milli, _pad, instance_proxies
from scripts.platformkit.tracking.g336_capture import (
    RouteRefused, baseline_from_raw, capture_section, read_raw,
)
from scripts.platformkit.tracking.g336_track_id_continuity import (
    associate, evaluator_records, evaluate_ticks, metrics, write_csv,
)

SECTIONS = (
    ("nba_0081", "data/footage_corpus/nba__0022500081_s2436.mp4", 720),
    ("nba_0575", "data/footage_corpus/nba__0022500575_s4500.mp4", 360),
    ("nba_0592", "data/footage_corpus/nba__0022500592_s2700.mp4", 360),
    ("wnba_5l4", "data/footage_corpus/wnba__-5l407QKuVk_s90.mp4", 1080),
)


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _starts(rows: list[dict]) -> dict[int, int]:
    out: dict[int, int] = defaultdict(int)
    for row in rows:
        out[int(row["frame"])] += int(row["new_instance"])
    return out


def _instance_rows(arm: str, rows: list[dict]) -> list[dict]:
    return [{"arm": arm, "section": r["section"], "frame": str(int(r["frame"])).zfill(6),
             "team": r["team"], "instance_id": str(int(r["instance_id"])).zfill(6)} for r in rows]


def _premise_rows(section: str, rows: list[dict]) -> list[dict]:
    """The exact route rows the premise reads, archived so it is recomputable.

    `instance_proxies` keys on `player_id` and `frame` and measures the bbox
    bottom-centre, so these cells reproduce it exactly; divide a milli cell by
    1000 to recover pixels.
    """
    return [{"section": section, "frame": _pad(float(r["frame"])), "player_id": _pad(r["player_id"]),
             "bbox_x1_milli_px": _milli(r["bbox_x1"]), "bbox_y1_milli_px": _milli(r["bbox_y1"]),
             "bbox_x2_milli_px": _milli(r["bbox_x2"]), "bbox_y2_milli_px": _milli(r["bbox_y2"])}
            for r in rows]


def _signature_choice(raw: list[dict]) -> tuple[str, float]:
    """Amendment prereg rule: OSNet only when EVERY observation in the section has one.

    A mixed 512-dim / 3-dim signature set is not comparable, so the choice is per
    section and all-or-nothing; the measured coverage share is reported either way.
    """
    covered = sum(1 for row in raw if row.get("deep"))
    share = covered / len(raw) if raw else 0.0
    if raw and covered == len(raw):
        for row in raw:
            row["sig"] = row["deep"]
        return "osnet", share
    return "hsv", share


def run(destination: Path, offset: int = 90, cap: int = 540) -> int:
    """Execute the four fixed production-route sections in a single pod job.

    `offset` and `cap` default to the sealed amendment prereg values (90 / 540 source
    frames, fix 1b); any other pair is a declared deviation the caller must label.
    """
    destination.mkdir(parents=True, exist_ok=True)
    raw_by_section, tracking, elapsed, wall, gate = {}, {}, {}, {}, {}
    for section, video, height in SECTIONS:
        output, raw_path = destination / (section + "_route"), destination / (section + "_raw.jsonl")
        meta_path = destination / (section + "_meta.json")
        if meta_path.exists():
            # A completed capture is never re-run: the route is the expensive half and
            # its detector stream is already on disk, so scoring can be redone freely.
            meta = json.loads(meta_path.read_text())
            raw_gate = meta["route_gate"]
            if raw_gate.startswith("bypassed_exit_"):
                # Legacy token from the deleted preflight-bypass path (pre fix-1b). Any
                # cache written under it is void regardless of its stored `scored` flag,
                # so it is mapped to refused and never read as scored data (B4).
                gate[section] = "refused_exit_" + raw_gate[len("bypassed_exit_"):]
                continue
            gate[section] = raw_gate
            if meta["scored"]:
                raw_by_section[section] = read_raw(raw_path)
                tracking[section] = _read_csv(output / "tracking_data.csv")
                elapsed[section], wall[section] = meta["assoc_ms"], meta["route_wall_ms"]
            continue
        try:
            raw, rows, millis, secs = capture_section(section, video, height, offset, cap,
                                                      output, raw_path)
            gate[section] = "pass"
        except RouteRefused as refused:
            # The route's OWN production preflight refused this section. It is recorded
            # REFUSED and never scored: neutralising that gate would score footage the
            # production route does not track.
            gate[section] = "refused_exit_%s" % refused.code
            meta_path.write_text(json.dumps({"route_gate": gate[section], "scored": False}) + "\n")
            continue
        raw_by_section[section], tracking[section] = raw, rows
        elapsed[section], wall[section] = millis, secs
        meta_path.write_text(json.dumps({"route_gate": gate[section], "scored": True,
                                         "assoc_ms": millis, "route_wall_ms": secs}) + "\n")
    # IDENTICAL OBSERVATION SETS (amendment prereg): both arms score exactly the
    # observations the route assigned to a slot, so the detections AND the evaluated
    # frames are one set. Detections the route left unassigned are excluded from BOTH.
    excluded, sig_kind, sig_share = {}, {}, {}
    for section, rows in list(raw_by_section.items()):
        kept = [row for row in rows if row.get("baseline_slot") is not None]
        excluded[section] = len(rows) - len(kept)
        raw_by_section[section] = kept
        sig_kind[section], sig_share[section] = _signature_choice(kept)
    scored = [entry for entry in SECTIONS if raw_by_section.get(entry[0])]
    premise_rows: list[dict] = []
    premise = []
    for section, _, height in SECTIONS:
        if section not in raw_by_section:
            premise.append({"section": section, "route_gate": gate[section], "slot_ids": None,
                            "instances": None, "median_instance_len": None,
                            "frames": None, "n_rows": None})
            continue
        proxy = instance_proxies(tracking[section], height)
        premise_rows.extend(_premise_rows(section, tracking[section]))
        premise.append({"section": section, "route_gate": gate[section],
                        "slot_ids": len({r["player_id"] for r in tracking[section]}),
                        "instances": proxy["distinct_instances"],
                        "median_instance_len": proxy["median_instance_len_rows"],
                        "frames": len({r["frame"] for r in tracking[section]}), "n_rows": len(tracking[section])})
    write_csv(destination / "premise.csv", premise, list(premise[0]))
    if premise_rows:
        write_csv(destination / "premise_rows.csv", premise_rows, list(premise_rows[0]))
    false_count = sum((row["median_instance_len"] or 0) > 40 for row in premise)
    if false_count >= 3:
        (destination / "result.json").write_text(json.dumps({"verdict": "PREMISE FALSE", "premise": premise}) + "\n")
        print("G336_PREMISE_FALSE count=%d" % false_count)
        return 0
    cand_ms = {}
    candidate = []
    for section, _, _ in scored:
        tick = time.perf_counter()
        part = associate(raw_by_section[section])
        cand_ms[section] = (time.perf_counter() - tick) * 1000.0
        candidate.extend(part)
    baseline = []
    for section, _, height in scored:
        baseline.extend(baseline_from_raw(raw_by_section[section], height))
    states = []
    summary = []
    for index, (section, _, _) in enumerate(scored):
        raw = raw_by_section[section]
        base = [row for row in baseline if row["section"] == section]
        cand = [row for row in candidate if row["section"] == section]
        frames = sorted({int(row["frame"]) for row in raw})
        states.extend(evaluate_ticks(section, frames, _starts(base), _starts(cand), index))
        b = metrics(base, len(frames), raw, elapsed[section])
        c = metrics(cand, len(frames), raw, cand_ms[section])
        head = {"section": section, "route_gate": gate[section], "route_wall_ms": wall[section],
                "signature": sig_kind[section], "osnet_coverage_share": sig_share[section],
                "excluded_unassigned_observations": excluded[section]}
        summary.extend([{**head, "arm": "baseline", **b}, {**head, "arm": "candidate", **c}])
    losses = evaluator_records(states)
    by_section = defaultdict(list)
    for row in losses:
        by_section[row["tick_key"].split(":", 1)[0]].append(row)
    for row in summary:
        ticks = by_section[row["section"]]
        field = row["arm"] + "_loss"
        row["fragmentation_ratio"] = sum(t[field] for t in ticks) / len(ticks)
        row["n_ticks"] = len(ticks)
    write_csv(destination / "metrics.csv", summary, list(summary[0]))
    write_csv(destination / "evaluator_records.csv", losses, list(losses[0]))
    instances = _instance_rows("baseline", baseline) + _instance_rows("candidate", candidate)
    write_csv(destination / "instances.csv", instances, ["arm", "section", "frame", "team", "instance_id"])
    (destination / "result.json").write_text(json.dumps(
        {"verdict": "MEASURED", "premise": premise, "route_gate": gate,
         "signature": sig_kind, "osnet_coverage_share": sig_share,
         "excluded_unassigned_observations": excluded}) + "\n")
    print("G336_MEASURED sections=%d ticks=%d" % (len(scored), len(losses)))
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="G336 one-job runner")
    ap.add_argument("--dest", required=True)
    raise SystemExit(run(Path(ap.parse_args().dest)))


if __name__ == "__main__":
    main()
