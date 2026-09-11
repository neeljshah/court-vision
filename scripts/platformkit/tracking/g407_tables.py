"""Pure G407 classification and table rows; every store read happens in the caller.

Two independent stratum systems are reported side by side and never merged: the sealed
receipt-bound format stratum from `g407_population.actual_rendition`, and the measured class
built only from the independently decoded height and native frame rate. A requested itag on its
own never produces either one.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from scripts.platformkit.tracking.g407_population import KNOWN_RENDITIONS, actual_rendition

FPS_BINS = ((24.5, 25.5, "25"), (29.0, 31.0, "30"), (49.0, 51.0, "50"), (59.0, 61.0, "60"))
ITAG_EXPECT = {"270": (1920, 1080, 0.0), "232": (1280, 720, 0.0), "312": (1920, 1080, 50.0),
               "311": (1280, 720, 50.0), "301": (1280, 720, 50.0), "300": (1280, 720, 50.0)}
QUOTA = 30


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def fps_bin(value: Any) -> str:
    """Return the reported native-rate band, never a rounded number posing as exact."""
    fps = _float(value)
    if fps is None:
        return "UNKNOWN"
    for low, high, name in FPS_BINS:
        if low <= fps < high:
            return name
    return "OTHER"


def measured_class(height: Any, fps: Any) -> str:
    """Class the independently decoded bytes only; labels and itags are never consulted."""
    tall, band = _float(height), fps_bin(fps)
    if tall is None or band in ("UNKNOWN",):
        return "UNKNOWN"
    return "%dp%s" % (int(tall), band)


def itag_consistency(requested: Any, width: Any, height: Any, fps: Any) -> str:
    """Compare a fetched-format receipt with the measured native stream."""
    expect = ITAG_EXPECT.get(str(requested).strip())
    wide, tall, rate = _float(width), _float(height), _float(fps)
    if expect is None:
        return "UNKNOWN_ITAG"
    if wide is None or tall is None or rate is None:
        return "UNKNOWN_MEASUREMENT"
    if (int(wide), int(tall)) != expect[:2]:
        return "MISMATCH_RESOLUTION"
    if expect[2] and rate < expect[2]:
        return "MISMATCH_RATE"
    return "CONSISTENT"


def bind_rendition(row: dict[str, Any]) -> dict[str, Any]:
    """Bind an actual rendition only to a delivered-format receipt and its source digest."""
    consistency = itag_consistency(row.get("requested_format_id"), row.get("measured_width"),
                                   row.get("measured_height"), row.get("measured_fps"))
    row["itag_consistency"] = consistency
    row["source_sha256"] = row.get("pc_sha256", "") if row.get("digest_match") == 1 else ""
    receipt_source = str(row.get("delivered_format_source_sha256", "")).strip()
    receipt_digest = str(row.get("delivered_format_receipt_sha256", "")).strip()
    delivered = str(row.get("delivered_format_id", "")).strip()
    row["actual_format_id"] = (delivered if receipt_digest and row["source_sha256"] and
                                receipt_source == row["source_sha256"] else "")
    row["actual_rendition"] = actual_rendition(row)
    row["format_join_status"] = "BOUND" if row["actual_rendition"] != "UNRESOLVED" else "UNRESOLVED"
    row["measured_class"] = measured_class(row.get("measured_height"), row.get("measured_fps"))
    row["measured_fps_bin"] = fps_bin(row.get("measured_fps"))
    return row


def held_share(held: Any, shared: Any) -> str:
    """Held share on shared consecutive evaluated ticks; an empty denominator stays UNKNOWN."""
    total = _float(shared)
    if not total:
        return "UNKNOWN"
    return "%.6f" % (float(held) / total)


def stratum_counts(rows: Iterable[Mapping[str, Any]], key: str,
                   quota: int = QUOTA) -> list[dict[str, Any]]:
    """Per-stratum supply against the sealed quota, with both denominators kept apart."""
    rows = [dict(row) for row in rows]
    in_window: Counter[str] = Counter(str(row.get(key, "UNKNOWN")) for row in rows)
    retained: Counter[str] = Counter(str(row.get(key, "UNKNOWN")) for row in rows
                                     if row.get("retained") == 1)
    bound: Counter[str] = Counter(str(row.get(key, "UNKNOWN")) for row in rows
                                  if row.get("format_join_status") == "BOUND")
    names = sorted(set(in_window) | set(retained) |
                   (set(KNOWN_RENDITIONS) if key == "actual_rendition" else set()))
    out = []
    for name in names:
        unique = len({row.get("section_identity") for row in rows
                      if str(row.get(key, "UNKNOWN")) == name and row.get("retained") == 1})
        quota_met = int(unique >= quota and name not in ("UNRESOLVED", "UNKNOWN"))
        out.append({"stratum_system": key, "stratum": name,
                    "sections_in_window": in_window.get(name, 0),
                    "sections_retained": retained.get(name, 0),
                    "unique_retained_sections": unique,
                    "sections_receipt_bound": bound.get(name, 0), "quota": quota,
                    "quota_met": quota_met,
                    "status": "COMPLETE" if quota_met else "PARTIAL"})
    return out


def boundary_split(rows: Iterable[Mapping[str, Any]], selector_utc: str,
                   probe_utc: str) -> dict[str, int]:
    """Count sections by the activation boundary their own fetch receipt falls after."""
    counts = Counter()
    for row in rows:
        fetched = str(row.get("fetch_utc", ""))
        if not fetched:
            counts["fetch_utc_UNKNOWN"] += 1
        elif fetched >= probe_utc:
            counts["fetched_after_probe_aware_discovery"] += 1
        elif fetched >= selector_utc:
            counts["fetched_after_232_first_selector"] += 1
        else:
            counts["fetched_before_both_boundaries"] += 1
    return dict(counts)


def class_summaries(rows: list[dict[str, Any]], held_rows: list[dict],
                    coverage: list[dict], counts_rows: list[dict]) -> list[dict[str, Any]]:
    """Per-class distributions, keeping the sealed and admitted denominators apart."""
    by_section = {row["section_identity"]: row for row in rows}
    out = []
    for system in ("measured_class", "actual_rendition"):
        for name in sorted({str(row[system]) for row in rows}):
            members = {row["section_identity"] for row in rows if str(row[system]) == name}
            held = [row for row in held_rows if row["section_identity"] in members and
                    row["schedule_status"] == "KNOWN"]
            cover = [row for row in coverage if row["section_identity"] in members and
                     row["schedule_status"] == "KNOWN"]
            losses = [float(row["cap_loss_s"]) for row in cover
                      if row["cap_loss_s"] not in ("UNKNOWN", "")]
            quota_met = int(name not in ("UNRESOLVED", "UNKNOWN") and
                            len(members & {row["section_identity"] for row in rows
                                           if row["retained"] == 1}) >= QUOTA)
            entry = {"stratum_system": system, "stratum": name, "sections": len(members),
                      "sections_retained": sum(by_section[item]["retained"] for item in members),
                      "quota": QUOTA, "quota_met": quota_met,
                      "status": "COMPLETE" if quota_met else "PARTIAL",
                     "ledger_decoded_frames": sum(int(row["ledger_decoded_frames"] or 0)
                                                  for row in cover),
                     "producer_read_frames": sum(int(row["producer_read_frames"] or 0)
                                                 for row in cover),
                     "evaluated_ticks": sum(int(row["evaluated_ticks"] or 0) for row in cover),
                     "suspended_ticks": sum(int(row["suspended_ticks"] or 0) for row in cover),
                     "schedule_known_sections": sum(row["schedule_status"] == "KNOWN"
                                                    for row in cover),
                     "cap_sections_measured": len(losses),
                     "cap_sections_loss_over_5s": sum(int(value > 5.0) for value in losses),
                     "cap_loss_s_min": "%.3f" % min(losses) if losses else "UNKNOWN",
                     "cap_loss_s_max": "%.3f" % max(losses) if losses else "UNKNOWN"}
            for scope in ("FULL_ADMITTED", "SEALED_2S"):
                pairs = [row for row in held if row["scope"] == scope
                         and row["shared_pairs"] != "UNKNOWN"]
                total = sum(int(row["shared_pairs"]) for row in pairs)
                entry["held_pairs_" + scope] = sum(int(row["held_pairs"]) for row in pairs)
                entry["shared_pairs_" + scope] = total
                entry["held_share_" + scope] = held_share(entry["held_pairs_" + scope], total)
                entry["zero_output_ticks_" + scope] = sum(
                    int(row["zero_output_evaluated_ticks"]) for row in pairs)
            out.append(entry)
    return out
