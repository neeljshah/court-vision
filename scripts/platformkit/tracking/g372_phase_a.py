"""G372 phase-A: sealed-window collection, loss attribution, scratch sidecar exercise.

Read-only on /workspace/data. The collection window, the attempt set, the even
sample and the failure-retaining denominators are sealed in
`g372_prereg_amendment_A2_2026-09-10.md`; this module implements them and never
derives its inputs from a directory listing.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import json
import shutil
from collections import Counter
from pathlib import Path

from scripts.platformkit.tracking import g369_prospective_identity as g369
from scripts.platformkit.tracking import g372_source_sidecar as g372
from scripts.platformkit.tracking import g372_window as w

DATA = w.DATA
GATE_UTC = "2026-09-10T17:49:00Z"
CROP_RULE = "TOPCUT = 60"
CENSUS_FIELDS = ("game_id", "sport", "ledger_rows", "first_claim_utc", "last_finished_utc",
                 "gate_side", "location", "located_path", "dir_mtime_utc", "retracked",
                 "retrack_reason")
SIDECAR_FIELDS = ("game_id", "source_identity_path", "state", "source_path", "source_sha256",
                  "source_bytes", "ffprobe", "crop_rule", "route_digest", "weight_digest",
                  "deploy_manifest_sha256", "claim_utc", "daemon_pid", "terminal_diagnostic")
PIN_FIELDS = ("game_id", "claim_utc", "pin_utc", "independent_sha256", "status", "diagnostic")
JOIN_FIELDS = ("game_id", "claim_utc", "sidecar_sha256", "independent_sha256", "agreement",
               "status", "diagnostic")
CONTROL_FIELDS = ("control", "input_kind", "input_bytes", "resolution", "result", "classification")
DELETER_FIELDS = ("game_id", "sport", "gate_side", "location", "deleted_utc", "deleted_bytes",
                  "deleted_path", "deleter", "reason")
VOL_GUARD_LOG = Path("/workspace/vol_guard.log")
even_sample = w.even_sample


def _deletions() -> dict:
    """Index the pod volume guard DEL events by source basename."""
    events = {}
    if not VOL_GUARD_LOG.is_file():
        return events
    for line in VOL_GUARD_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1] == "DEL":
            events[Path(parts[3]).name] = {"deleted_utc": parts[0], "deleted_bytes": parts[2],
                                           "deleted_path": parts[3], "deleter": "vol_guard.py",
                                           "reason": parts[4]}
    return events


def _write(path: Path, fields: tuple, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _merge_summary(out: Path, block: dict) -> None:
    """Update only the keys this run owns; the composed summary is never rebuilt."""
    target = out / "summary.json"
    current = json.loads(target.read_text(encoding="ascii")) if target.is_file() else {}
    current.update(block)
    target.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="ascii")


def cmd_collect(args) -> None:
    """Sample the sealed window evenly and write one manifest row per attempt."""
    snapshot, out = Path(args.snapshot), Path(args.out)
    items = w.attempts(snapshot)
    seed = w.snapshot_sha256(snapshot)
    k, start, indices = w.even_sample(len(items), seed)
    sampled = [items[i] for i in indices]
    _write(out / "sampled_indices.csv", w.SAMPLE_FIELDS, sampled)
    rows = w.collect(sampled, Path(args.scratch), args.cap_bytes)
    _write(out / "collect_manifest.csv", w.MANIFEST_FIELDS, rows)
    print(json.dumps({"snapshot_sha256": seed, "window_n": len(items), "k": k, "start": start,
                      "sampled_n": len(rows),
                      "status": dict(Counter(r["copy_status"] for r in rows))}, sort_keys=True),
          flush=True)


def cmd_census(args) -> None:
    """Attribute every fresh section to a byte location and a re-track state."""
    grouped = w.grouped_window(Path(args.snapshot))
    lines = [s for s in Path(args.snapshot).read_text(encoding="utf-8").splitlines() if s.strip()]
    gate = calendar.timegm((2026, 9, 10, 17, 49, 0, 0, 0, 0))
    rows = []
    for game_id, entries in grouped.items():
        first, last = entries[0], entries[-1]
        claim = float(first.get("finished_at") or 0) - float(first.get("seconds") or 0)
        folder = DATA / "tracking" / game_id
        mtime = folder.stat().st_mtime if folder.exists() else 0.0
        reasons = []
        if len(entries) > 1:
            reasons.append("duplicate_ledger_rows")
        if mtime and mtime > float(first.get("finished_at") or 0) + 1:
            reasons.append("dir_mtime_after_first_row")
        location, path = w.locate(first.get("sport", ""), game_id, first.get("source_variants"))
        rows.append({"game_id": game_id, "sport": first.get("sport", ""),
                     "ledger_rows": len(entries), "first_claim_utc": w.utc(claim),
                     "last_finished_utc": w.utc(last.get("finished_at") or 0),
                     "gate_side": "BEFORE" if claim < gate else "AFTER",
                     "location": location, "located_path": path,
                     "dir_mtime_utc": w.utc(mtime) if mtime else "ABSENT",
                     "retracked": bool(reasons), "retrack_reason": "|".join(reasons) or "none"})
    rows.sort(key=lambda item: item["first_claim_utc"])
    _write(Path(args.out) / "attribution.csv", CENSUS_FIELDS, rows)
    events, deleted = _deletions(), []
    for row in rows:
        hit = events.get("%s__%s.mp4" % (row["sport"], row["game_id"]))
        if hit:
            deleted.append({**{key: row[key] for key in
                               ("game_id", "sport", "gate_side", "location")}, **hit})
    _write(Path(args.out) / "deleters.csv", DELETER_FIELDS, deleted)
    summary = {"total_ledger_rows": len(lines),
               "fresh_ledger_rows": len(lines) - w.FRESH_FROM_ROW + 1, "fresh_sections": len(rows)}
    for side in ("BEFORE", "AFTER"):
        subset = [r for r in rows if r["gate_side"] == side]
        retained = [r for r in subset if r["location"] != "GONE"]
        summary[side.lower()] = {
            "sections": len(subset), "retained": len(retained), "gone": len(subset) - len(retained),
            "retained_share": round(len(retained) / len(subset), 6) if subset else "UNKNOWN",
            "retracked": sum(1 for r in subset if r["retracked"]),
            "gone_and_retracked": sum(1 for r in subset
                                      if r["location"] == "GONE" and r["retracked"])}
    for name in ("BRIDGE", "CORPUS", "QUARANTINE", "GONE"):
        summary["location_" + name] = sum(1 for r in rows if r["location"] == name)
    gone = [r for r in rows if r["location"] == "GONE"]
    names = {r["game_id"] for r in deleted}
    summary["gone_attributed_to_vol_guard"] = sum(1 for r in gone if r["game_id"] in names)
    summary["gone_unattributed"] = len(gone) - summary["gone_attributed_to_vol_guard"]
    summary["vol_guard_del_events_total"] = len(events)
    Path(args.out, "attribution_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(summary, sort_keys=True), flush=True)


def _sidecar_payload(path: Path, manifest: dict, deploy_sha: str) -> dict:
    return {"source_path": str(path), "source_sha256": g372.sha256_file(path),
            "source_bytes": path.stat().st_size, "ffprobe": g372.bounded_ffprobe(path),
            "crop_rule": CROP_RULE,
            "route_digest": {key: item["sha256"] for key, item in manifest["routes"].items()},
            "weight_digest": {}, "deploy_manifest_sha256": deploy_sha,
            "claim_utc": g372.utc_now(), "daemon_pid": 0, "terminal_diagnostic": ""}


def _bind(row: dict, manifest: dict, holder: Path, args) -> tuple:
    """Write one sidecar, take the independent G369 read, and join the two."""
    game_id, source = row["game_id"], Path(row["scratch_path"])
    target, state, diagnostic = holder / (game_id + ".source_identity.json"), "COMMITTED", ""
    payload = _sidecar_payload(source, manifest, args.deploy_manifest)
    try:
        g372.write_sidecar(target, payload)
    except (OSError, ValueError) as exc:
        state, diagnostic = "TERMINAL_ERROR", type(exc).__name__
    record, probe = g369._file_record(source), g369._probe(source)
    agree = state == "COMMITTED" and record["sha256"] == payload["source_sha256"] \
        and record["bytes"] == payload["source_bytes"]
    pin = {"game_id": game_id, "claim_utc": payload["claim_utc"], "pin_utc": g372.utc_now(),
           "independent_sha256": record["sha256"],
           "status": "PINNED" if record["sha256"] != g369.UNKNOWN else "ABSENT",
           "diagnostic": "first_pts=%s" % probe.get("first_pts", g369.UNKNOWN)}
    join = {"game_id": game_id, "claim_utc": payload["claim_utc"],
            "sidecar_sha256": payload["source_sha256"],
            "independent_sha256": record["sha256"], "agreement": agree,
            "status": "AGREE" if agree else ("DISAGREE" if state == "COMMITTED" else state),
            "diagnostic": diagnostic or ("" if agree else "sha256_or_bytes_differ")}
    side = {"game_id": game_id, "source_identity_path": str(target), "state": state,
            "terminal_diagnostic": diagnostic,
            **{key: (json.dumps(value, sort_keys=True) if isinstance(value, dict) else value)
               for key, value in payload.items() if key != "terminal_diagnostic"}}
    return side, pin, join


def cmd_exercise(args) -> None:
    """Bind every collected attempt and LEFT-JOIN every failed attempt by status."""
    out, holder = Path(args.out), Path(args.out) / "sidecars"
    with Path(args.manifest).open(encoding="ascii", newline="") as handle:
        manifest_rows = list(csv.DictReader(handle))
    g369man = g369._manifest(Path.cwd(), [])
    sidecars, pins, joins, bound = [], [], [], []
    for row in manifest_rows:
        game_id, status = row["game_id"], row["copy_status"]
        if status != "OK":
            sidecars.append({"game_id": game_id, "source_identity_path": "", "state": status,
                             "terminal_diagnostic": row["reason"], "source_path": row["src_path"]})
            pins.append({"game_id": game_id, "claim_utc": "", "pin_utc": "",
                         "independent_sha256": "", "status": status, "diagnostic": row["reason"]})
            joins.append({"game_id": game_id, "claim_utc": "", "sidecar_sha256": "",
                          "independent_sha256": "", "agreement": False, "status": status,
                          "diagnostic": row["reason"]})
            continue
        side, pin, join = _bind(row, g369man, holder, args)
        sidecars.append(side)
        pins.append(pin)
        joins.append(join)
        bound.append(Path(row["scratch_path"]))
    _write(out / "sidecars.csv", SIDECAR_FIELDS, sidecars)
    _write(out / "pins.csv", PIN_FIELDS, pins)
    _write(out / "join.csv", JOIN_FIELDS, joins)
    _write(out / "controls.csv", CONTROL_FIELDS, _controls(bound, g369man, args))
    sampled = len(manifest_rows)
    committed = sum(1 for r in sidecars if r["state"] == "COMMITTED")
    agreed = sum(1 for r in joins if r["agreement"])
    block = {"coverage": {"sampled_attempts": sampled, "sidecars_committed": committed,
                          "value": round(committed / sampled, 6) if sampled else "UNKNOWN",
                          "distinct_videos_sampled": len({r["game_id"].split("_s")[0]
                                                          for r in joins}),
                          "distinct_videos_committed":
                              len({r["game_id"].split("_s")[0] for r in sidecars
                                   if r["state"] == "COMMITTED"})},
             "independent_agreement": {"n": sampled, "agree": agreed, "omitted": 0,
                                       "value": round(agreed / sampled, 6) if sampled else "UNKNOWN",
                                       "joined_rows": len(bound),
                                       "value_over_joined_rows": round(agreed / len(bound), 6)
                                       if bound else "UNKNOWN"},
             "failure_classes": dict(Counter(r["status"] for r in joins if not r["agreement"]))}
    _merge_summary(out, block)
    print(json.dumps(block, sort_keys=True), flush=True)


def _controls(sources: list, manifest: dict, args) -> list:
    """Byte-flip, identical-read and deterministic-write controls, all CONSTRUCT."""
    if not sources:
        return [{"control": "all", "input_kind": "CONSTRUCT", "input_bytes": 0, "resolution": "N/A",
                 "result": "NOT VALIDATED", "classification": "CONSTRUCT"}]
    probe, rows = sources[0], []
    scratch = Path(args.scratch) / "control"
    scratch.mkdir(parents=True, exist_ok=True)
    copy = scratch / "flip.mp4"
    shutil.copyfile(probe, copy)
    before_side, before_pin = g372.sha256_file(copy), g369._file_record(copy)["sha256"]
    rows.append({"control": "identical_read", "input_kind": "CONSTRUCT",
                 "input_bytes": copy.stat().st_size, "resolution": "N/A",
                 "result": "PASS" if (g372.sha256_file(copy) == before_side
                                      and g369._file_record(copy)["sha256"] == before_pin
                                      and before_side == before_pin) else "FAIL",
                 "classification": "CONSTRUCT"})
    with copy.open("r+b") as handle:
        first = handle.read(1)
        handle.seek(0)
        handle.write(bytes([first[0] ^ 0x01]))
    rows.append({"control": "byte_flip", "input_kind": "CONSTRUCT",
                 "input_bytes": copy.stat().st_size, "resolution": "N/A",
                 "result": "PASS" if (g372.sha256_file(copy) != before_side
                                      and g369._file_record(copy)["sha256"] != before_pin)
                 else "FAIL", "classification": "CONSTRUCT"})
    payload = _sidecar_payload(copy, manifest, args.deploy_manifest)
    payload["claim_utc"] = "2026-09-10T00:00:00Z"
    one, two = scratch / "one.json", scratch / "two.json"
    one.unlink(missing_ok=True)
    two.unlink(missing_ok=True)
    g372.write_sidecar(one, payload)
    g372.write_sidecar(two, payload)
    rows.append({"control": "deterministic_write", "input_kind": "CONSTRUCT",
                 "input_bytes": one.stat().st_size, "resolution": "N/A",
                 "result": "PASS" if one.read_bytes() == two.read_bytes() else "FAIL",
                 "classification": "CONSTRUCT"})
    copy.unlink(missing_ok=True)
    return rows


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="G372 phase-A measurement")
    subs = parser.add_subparsers(dest="command", required=True)
    collect = subs.add_parser("collect")
    collect.add_argument("--snapshot", required=True)
    collect.add_argument("--scratch", required=True)
    collect.add_argument("--out", required=True)
    collect.add_argument("--cap-bytes", type=int, default=4 * 1024 ** 3, dest="cap_bytes")
    collect.set_defaults(func=cmd_collect)
    census = subs.add_parser("census")
    census.add_argument("--snapshot", required=True)
    census.add_argument("--out", required=True)
    census.set_defaults(func=cmd_census)
    exercise = subs.add_parser("exercise")
    exercise.add_argument("--manifest", required=True)
    exercise.add_argument("--scratch", required=True)
    exercise.add_argument("--out", required=True)
    exercise.add_argument("--deploy-manifest", required=True, dest="deploy_manifest")
    exercise.set_defaults(func=cmd_exercise)
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
