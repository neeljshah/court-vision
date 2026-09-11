"""G405 PC-side census, sealed draw, listing/metadata parsing and exports."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

from scripts.platformkit.tracking.g405_formats import (DRAW_SIZE, UNKNOWN, YES, availability,
                                                       even_draw, raw_inventory_digest, sidecar_row)

POP_FIELDS = ("order", "competition", "tag", "query", "source_id", "ytid", "duration_s",
              "dur", "title", "discovered_at")
DRAW_FIELDS = ("draw_j", "source_id", "ytid", "competition", "tag", "query", "duration_s",
               "dur", "title", "discovered_at", "membership_count", "query_memberships", "fmt")
RECEIPT_FIELDS = ("stage", "source_id", "draw_j", "start_utc", "end_utc", "elapsed_s",
                  "returncode", "timed_out", "stdout_bytes", "stdout_sha256",
                  "pre_redaction_sha256", "post_redaction_sha256", "format_count", "argv_sha256")
BUCKETS = ("720p30", "1080p30", "720p60", "1080p60")


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def unique_population(rows: list[dict]) -> list[dict]:
    """Deduplicate by source id, retaining every query membership."""
    seen: dict[str, dict] = {}
    for row in rows:
        sid = row["source_id"]
        if sid not in seen:
            seen[sid] = dict(row, query_memberships=[], membership_count=0)
        seen[sid]["query_memberships"].append("%s/%s" % (row["competition"], row["query"]))
        seen[sid]["membership_count"] += 1
    for row in seen.values():
        row["query_memberships"] = "|".join(row["query_memberships"])
    return list(seen.values())


def parse_listing(text: str) -> tuple[list[dict], bool]:
    """Parse a yt-dlp -F table into format records; no id-based inference."""
    out: list[dict] = []
    for line in text.splitlines():
        if line.count("|") != 2 or line.startswith("[") or line.strip().startswith("ID "):
            continue
        left, middle, right = (part.split() for part in line.split("|"))
        if len(left) < 3 or not middle or not right:
            continue
        fmt_id, ext, resolution = left[0], left[1], left[2]
        if "x" not in resolution:
            continue
        fps = None
        for token in left[3:]:
            try:
                fps = float(token)
                break
            except ValueError:
                continue
        out.append({"format_id": fmt_id, "ext": ext, "resolution": resolution,
                    "height": resolution.split("x")[-1], "fps": fps,
                    "protocol": middle[-1], "vcodec": right[0], "source": "listing"})
    return out, bool(out)


def parse_metadata(payload: dict) -> tuple[list[dict], bool]:
    """Project the machine-readable inventory onto the shared format schema."""
    out = [{"format_id": str(f.get("format_id", "")), "ext": f.get("ext", ""),
            "resolution": f.get("resolution", ""), "height": f.get("height"),
            "fps": f.get("fps"), "protocol": f.get("protocol", ""),
            "vcodec": f.get("vcodec", ""), "source": "metadata"}
           for f in payload.get("formats") or []]
    return out, bool(out) and not payload.get("error")


def build(evidence: Path) -> int:
    """Classify every drawn source from saved bytes and write every export."""
    with open(evidence / "draw.csv", encoding="utf-8") as handle:
        drawn = list(csv.DictReader(handle))
    receipts = {(r["stage"], r["source_id"]): r for r in
                json.loads((evidence / "runtime_receipts" / "probe_receipts.json").read_text(encoding="utf-8"))}
    fmt_rows, avail_rows, queue_rows, eye_rows = [], [], [], []
    cards = evidence / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    for row in drawn:
        sid = row["source_id"]
        raw_path, meta_path = evidence / "raw_formats" / ("%s.txt" % sid), evidence / "metadata" / ("%s.json" % sid)
        raw_bytes = raw_path.read_bytes() if raw_path.exists() else b""
        meta_bytes = meta_path.read_bytes() if meta_path.exists() else b""
        listing_rc = int(receipts.get(("listing", sid), {}).get("returncode", -1))
        meta_rc = int(receipts.get(("metadata", sid), {}).get("returncode", -1))
        listing, listing_ok = parse_listing(raw_bytes.decode("utf-8", "replace"))
        payload = json.loads(meta_bytes.decode("utf-8", "replace")) if meta_bytes else {"formats": [], "error": "absent"}
        metadata, meta_ok = parse_metadata(payload)
        listing_complete, metadata_complete = listing_ok and listing_rc == 0, meta_ok and meta_rc == 0
        result = availability(listing, metadata, listing_complete, metadata_complete)
        for item in listing + metadata:
            fmt_rows.append(dict(item, source_id=sid, draw_j=row["draw_j"]))
        fps_set = sorted({float(f["fps"]) for f in listing + metadata
                          if _eligible_shape(f) and f.get("fps") is not None})
        error = ""
        if not listing_complete:
            error = "listing_rc=%s formats=%d" % (listing_rc, len(listing))
        if not metadata_complete:
            error = (error + " metadata_rc=%s formats=%d %s" % (meta_rc, len(metadata), payload.get("error", ""))).strip()
        digest = raw_inventory_digest(raw_bytes, meta_bytes)
        status = "OK" if listing_complete and metadata_complete else "INCOMPLETE"
        avail = {"draw_j": row["draw_j"], "source_id": sid, "competition": row["competition"],
                 "tag": row["tag"], "query": row["query"], "discovered_at": row["discovered_at"],
                 "format_probe_at": receipts.get(("listing", sid), {}).get("start_utc", ""),
                 "compatible_30fps": result["compatible_30fps"],
                 "qualifying_format_ids": "|".join(result["qualifying_format_ids"]),
                 "listing_qualifying_ids": "|".join(result["listing_qualifying_ids"]),
                 "metadata_qualifying_ids": "|".join(result["metadata_qualifying_ids"]),
                 "listing_complete": listing_complete, "metadata_complete": metadata_complete,
                 "listing_formats": len(listing), "metadata_formats": len(metadata),
                 "probe_status": status, "raw_inventory_digest": digest, "error": error,
                 "hls_h264_720_1080_fps_set": "|".join("%g" % f for f in fps_set) or "none",
                 **{b: result[b] for b in BUCKETS}}
        avail_rows.append(avail)
        queue_rows.append(sidecar_row(
            {"source_id": sid, "ytid": sid, "sport": row["competition"], "tag": row["tag"],
             "fmt": row["fmt"], "duration_s": row["duration_s"], "dur": row["duration_s"],
             "title": row["title"]},
            result, discovered_at=row["discovered_at"], format_probe_at=avail["format_probe_at"],
            query=row["query"], digest=digest, probe_status=status))
        card = cards / ("card_%02d_%s.txt" % (int(row["draw_j"]), sid))
        card.write_text(_card_text(row, avail, listing, metadata), encoding="utf-8")
        eye_rows.append({"draw_j": row["draw_j"], "source_id": sid, "card": card.name,
                         "raw_listing": "raw_formats/%s.txt" % sid, "metadata": "metadata/%s.json" % sid,
                         "compatible_30fps": avail["compatible_30fps"], "probe_status": status})
    _write_csv(evidence / "probe_receipts.csv", RECEIPT_FIELDS,
               [dict(r, argv_sha256=hashlib.sha256(
                   ("\x00".join(r.get("argv") or [])).encode("utf-8")).hexdigest())
                for r in sorted(receipts.values(), key=lambda r: (int(r["draw_j"]), r["stage"]))])
    _write_csv(evidence / "format_rows.csv",
               ("source_id", "draw_j", "source", "format_id", "ext", "resolution", "height",
                "fps", "protocol", "vcodec"), fmt_rows)
    _write_csv(evidence / "availability.csv", tuple(avail_rows[0].keys()), avail_rows)
    _write_csv(evidence / "eye_index.csv", tuple(eye_rows[0].keys()), eye_rows)
    (evidence / "discovery_queue.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in queue_rows), encoding="utf-8")
    (evidence / "summary.json").write_text(json.dumps(summarize(avail_rows), indent=1, sort_keys=True),
                                           encoding="utf-8")
    print("build sources=%d format_rows=%d" % (len(avail_rows), len(fmt_rows)))
    return 0


def _eligible_shape(item: dict) -> bool:
    """True for an HLS h264 rendition inside the admission height window."""
    from scripts.platformkit.tracking.g405_formats import is_h264
    try:
        height = int(item.get("height") or 0)
    except (TypeError, ValueError):
        return False
    return ("m3u8" in str(item.get("protocol", "")).lower() and is_h264(item.get("vcodec"))
            and 720 <= height <= 1080)


def _card_text(drawn: dict, avail: dict, listing: list[dict], metadata: list[dict]) -> str:
    lines = ["G405 card j=%s source_id=%s competition=%s tag=%s" % (
        drawn["draw_j"], drawn["source_id"], drawn["competition"], drawn["tag"]),
        "query=%s discovered_at=%s probe_at=%s" % (drawn["query"], drawn["discovered_at"],
                                                   avail["format_probe_at"]),
        "compatible_30fps=%s probe_status=%s error=%s" % (avail["compatible_30fps"],
                                                          avail["probe_status"], avail["error"] or "none"),
        "buckets " + " ".join("%s=%s" % (b, avail[b]) for b in BUCKETS),
        "qualifying_format_ids=%s" % (avail["qualifying_format_ids"] or "none"),
        "raw_inventory_digest=%s" % avail["raw_inventory_digest"],
        "-- listing inventory (%d video rows) --" % len(listing)]
    for item in listing + [{"format_id": "--", "resolution": "-- metadata inventory (%d video rows) --" % len(metadata),
                            "fps": None, "protocol": "", "vcodec": "", "source": ""}] + metadata:
        lines.append("  %-8s %-12s fps=%-6s proto=%-12s vcodec=%s" % (
            item.get("format_id", ""), item.get("resolution", ""), item.get("fps"),
            item.get("protocol", ""), item.get("vcodec", "")))
    return "\n".join(lines) + "\n"


def summarize(avail_rows: list[dict]) -> dict:
    """Report over the full planned denominator; UNKNOWN never becomes NO."""
    states = [r["compatible_30fps"] for r in avail_rows]
    per_query: dict[str, dict] = {}
    for row in avail_rows:
        key = "%s/%s" % (row["competition"], row["query"])
        bucket = per_query.setdefault(key, {"n": 0, "YES": 0, "NO": 0, UNKNOWN: 0})
        bucket["n"] += 1
        bucket[row["compatible_30fps"]] += 1
    yes = states.count(YES)
    return {"planned_denominator": DRAW_SIZE, "probed_denominator": len(states),
            "known_denominator": len([s for s in states if s != UNKNOWN]),
            "YES": yes, "NO": states.count("NO"), UNKNOWN: states.count(UNKNOWN),
            "coverage_yes_over_planned": round(yes / DRAW_SIZE, 4),
            "supports_30_only_admission": yes == DRAW_SIZE,
            "projected_loss_under_30_only_max": states.count("NO") + states.count(UNKNOWN),
            "projected_loss_proven": states.count("NO"),
            "bucket_counts": {b: sum(1 for r in avail_rows if r[b]) for b in BUCKETS},
            "hls_h264_720_1080_fps_set_counts": _tally(
                [r["hls_h264_720_1080_fps_set"] for r in avail_rows]),
            "per_query": per_query}


def _tally(values: list[str]) -> dict[str, int]:
    return {key: values.count(key) for key in sorted(set(values))}


def main(argv: list[str]) -> int:
    evidence = Path(argv[2]) if len(argv) > 2 else Path(".")
    if len(argv) > 1 and argv[1] == "census":
        rows = _rows(evidence / "discovery_population.jsonl")
        _write_csv(evidence / "discovery_population.csv", POP_FIELDS, rows)
        uniq = unique_population(rows)
        drawn = even_draw(uniq)
        _write_csv(evidence / "draw.csv", DRAW_FIELDS,
                   [dict(r, fmt="270", ytid=r["source_id"], dur=r["duration_s"]) for r in drawn])
        print("census rows=%d unique=%d drawn=%d sha_draw=%s" % (
            len(rows), len(uniq), len(drawn),
            hashlib.sha256((evidence / "draw.csv").read_bytes()).hexdigest()))
        return 0
    if len(argv) > 1 and argv[1] == "build":
        return build(evidence)
    print("usage: g405_build.py census|build <evidence_dir>")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
