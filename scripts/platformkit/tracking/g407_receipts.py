"""G407 off-pod retention receipts: independent rehash and native decode of every drawn source.

Runs on the receiving machine over the retained copies only. Each retained source is hashed
again and probed again with a local ffprobe, and both results are compared with the pod-side
census values. A source the quota guard pruned before retention stays an explicit UNKNOWN row
and is never scored as a failure of the producer.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g397_census import sha256_file
from scripts.platformkit.tracking.g407_probe import probe_source, seal_window

FIELDS = ("section_identity", "retained", "retention_status", "receiver_path", "pod_source_path",
          "bytes", "pc_sha256", "pod_sha256", "digest_match", "probe_status",
          "measured_width", "measured_height", "codec_name", "avg_frame_rate_rational",
          "r_frame_rate_rational", "measured_fps", "decoded_pts_count", "first_pts", "last_pts",
          "sealed_start_pts", "sealed_stop_pts", "sealed_start_frame", "sealed_stop_frame",
          "sealed_source_frames", "pod_measured_height", "pod_measured_fps", "probe_agreement")


def _pod_probe_index(probes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("section_identity")): row for row in probes}


def receipt(row: dict[str, Any], receiver: Path, pod: dict[str, Any],
            ffprobe: str) -> dict[str, Any]:
    """One retention receipt; every absent measurement is a named UNKNOWN, never a zero."""
    identity = row["section_identity"]
    out: dict[str, Any] = {name: "UNKNOWN" for name in FIELDS}
    out.update({"section_identity": identity, "retained": 0,
                "pod_source_path": row.get("retained_pod_path", ""),
                "pod_sha256": row.get("pod_source_sha256", "PRUNED"),
                "pod_measured_height": pod.get("measured_height", "UNKNOWN"),
                "pod_measured_fps": pod.get("measured_fps", "UNKNOWN")})
    pod_path = str(row.get("retained_pod_path") or "")
    if not pod_path:
        out.update({"retention_status": "PRUNED_BEFORE_CENSUS", "receiver_path": "",
                    "probe_status": "SOURCE_NOT_RETAINED", "probe_agreement": "UNKNOWN"})
        return out
    local = Path(receiver) / Path(pod_path).name
    if not local.exists():
        out.update({"retention_status": "PRUNED_BEFORE_TRANSFER", "receiver_path": str(local),
                    "probe_status": "SOURCE_NOT_RETAINED", "probe_agreement": "UNKNOWN"})
        return out
    probe = probe_source(local, ffprobe)
    digest = sha256_file(local)
    out.update({"retained": 1, "retention_status": "RETAINED_OFF_POD",
                "receiver_path": str(local), "bytes": local.stat().st_size,
                "pc_sha256": digest,
                "digest_match": int(digest == str(row.get("pod_source_sha256", ""))),
                "probe_status": probe.get("probe_status", "UNKNOWN")})
    for name in ("measured_width", "measured_height", "codec_name", "avg_frame_rate_rational",
                 "r_frame_rate_rational", "measured_fps", "decoded_pts_count",
                 "first_pts", "last_pts"):
        out[name] = probe.get(name, "UNKNOWN")
    if probe.get("pts"):
        out.update(seal_window(probe["pts"]))
    agree = (str(probe.get("measured_height")) == str(pod.get("measured_height"))
             and str(probe.get("measured_fps")) == str(pod.get("measured_fps")))
    out["probe_agreement"] = "AGREE" if agree else "DISAGREE"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="G407 off-pod retention receipts")
    parser.add_argument("--population", required=True)
    parser.add_argument("--probes", required=True)
    parser.add_argument("--receiver", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    population = json.loads(Path(args.population).read_text(encoding="utf-8"))["population"]
    pods = _pod_probe_index(json.loads(Path(args.probes).read_text(encoding="utf-8")))
    rows = [receipt(row, Path(args.receiver), pods.get(row["section_identity"], {}),
                    args.ffprobe) for row in population]
    with Path(args.out).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print("RECEIPTS %d RETAINED %d DIGEST_MATCH %d AGREE %d" % (
        len(rows), sum(row["retained"] == 1 for row in rows),
        sum(row["digest_match"] == 1 for row in rows),
        sum(row["probe_agreement"] == "AGREE" for row in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
