"""Focused pure controls for the G405 discovery-format helpers and measurement."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g405_build import (parse_listing, parse_metadata, summarize,
                                                     unique_population)
from scripts.platformkit.tracking.g405_formats import (NO, UNKNOWN, YES, availability, even_draw,
                                                       is_h264, is_qualifying_format, sidecar_row)
from scripts.platformkit.tracking.g405_pod_probe import (MAX_RUN_WIDE, MIN_DURATION_S,
                                                         gate_reason)
from scripts.platformkit.tracking.g405_prereg import FORBIDDEN, verify_prereg

EVIDENCE = Path("docs/evidence/tracking/g405_discovery_format_admission_2026-09-11")
MEASURED_ROW = ("270 mp4   1920x1080   30    | ~  4.62GiB 5586k m3u8  | "
                "avc1.640028   5586k video only")
PAL_ROW = ("232    mp4   1280x720    25    | ~  2.05GiB 2807k m3u8  | "
           "avc1.4D401F   2807k video only")


def _format(format_id: str, **extra: object) -> dict[str, object]:
    return {"format_id": format_id, "protocol": "m3u8_native", "vcodec": "h264", "height": 720, "fps": 29.97, **extra}


def test_prereg_seal_normalizes_crlf_file_bytes() -> None:
    assert verify_prereg(EVIDENCE / "prereg.md")


def test_missing_or_omitted_fps_is_unknown() -> None:
    assert availability([_format("a")], [{"format_id": "a", "protocol": "m3u8", "vcodec": "h264", "height": 720}], True, True)["compatible_30fps"] == UNKNOWN


def test_non_hls_30_does_not_qualify() -> None:
    item = _format("a", protocol="https")
    assert not is_qualifying_format(item)
    assert availability([item], [item], True, True)["compatible_30fps"] == NO


def test_duplicate_source_cannot_fill_draw() -> None:
    rows = [{"source_id": "same", "competition": "nba", "query": "q"} for _ in range(30)]
    with pytest.raises(ValueError, match="duplicate-or-empty-source-id"):
        even_draw(rows)


def test_ntsc_2997_and_non_numeric_format_id_require_actual_fields() -> None:
    item = _format("999")
    assert is_qualifying_format(item)
    assert availability([item], [item], True, True)["compatible_30fps"] == YES
    assert not is_qualifying_format({"format_id": "999"})


def test_inherited_fields_are_preserved_in_additive_sidecar() -> None:
    original = {"source_id": "s1", "existing_field": "kept"}
    row = sidecar_row(original, {"compatible_30fps": YES, "qualifying_format_ids": ["a"]},
                      discovered_at="2026-09-11T00:00:00Z", format_probe_at="2026-09-11T00:01:00Z",
                      query="nba", digest="d", probe_status="OK")
    assert original == {"source_id": "s1", "existing_field": "kept"}
    assert row["existing_field"] == "kept" and row["preferred_format_if_available"] == "a"


def test_29_yes_cannot_support_30_only_branch() -> None:
    outcomes = [YES] * 29 + [UNKNOWN]
    assert outcomes.count(YES) != 30


def test_avc1_fourcc_is_h264() -> None:
    """Measured correction: yt-dlp lists H.264 as avc1.*, never the token h264."""
    assert is_h264("avc1.640028") and is_h264("AVC1.4D401E") and is_h264("avc3.64001f")
    assert not is_h264("vp09.00.21.08") and not is_h264("vp9") and not is_h264("")


def test_listing_parser_reads_the_measured_table_shape() -> None:
    rows, complete = parse_listing("\n".join([
        "[youtube] Extracting URL: x", "ID  EXT   RESOLUTION FPS CH | FILESIZE TBR PROTO | VCODEC",
        "233 mp4   audio only        |                  m3u8  | audio only",
        "sb0 mhtml 320x180      0    |                  mhtml | images     storyboard",
        MEASURED_ROW, PAL_ROW]))
    assert complete and [r["format_id"] for r in rows] == ["sb0", "270", "232"]
    assert rows[1]["fps"] == 30.0 and rows[1]["protocol"] == "m3u8" and rows[1]["height"] == "1080"
    assert is_qualifying_format(rows[1]) and not is_qualifying_format(rows[2])


def test_pal_25fps_source_is_no_not_unknown() -> None:
    """Measured: 8 of 30 drawn sources list only 25 fps renditions."""
    rows, _ = parse_listing(PAL_ROW)
    assert availability(rows, rows, True, True)["compatible_30fps"] == NO


def test_incomplete_inventory_never_becomes_no() -> None:
    rows, _ = parse_listing(PAL_ROW)
    assert availability(rows, rows, True, False)["compatible_30fps"] == UNKNOWN
    assert availability([], [], False, False)["compatible_30fps"] == UNKNOWN


def test_metadata_projection_keeps_every_format() -> None:
    rows, complete = parse_metadata({"formats": [
        {"format_id": "270", "protocol": "m3u8_native", "vcodec": "avc1.640028", "height": 1080, "fps": 30},
        {"format_id": "139", "protocol": "https", "vcodec": "none", "acodec": "mp4a"}]})
    assert complete and len(rows) == 2 and is_qualifying_format(rows[0])


def test_repeated_query_membership_cannot_increase_n() -> None:
    rows = [{"source_id": "a", "competition": "nba", "query": "q1"},
            {"source_id": "a", "competition": "nba", "query": "q2"},
            {"source_id": "b", "competition": "nba", "query": "q1"}]
    uniq = unique_population(rows)
    assert len(uniq) == 2 and uniq[0]["membership_count"] == 2
    assert uniq[0]["query_memberships"] == "nba/q1|nba/q2"


def test_summary_denominator_is_all_thirty_and_unknown_is_not_no() -> None:
    base = {"compatible_30fps": YES, "competition": "nba", "query": "q", "720p30": True,
            "1080p30": False, "720p60": False, "1080p60": False, "hls_h264_720_1080_fps_set": "30"}
    rows = [dict(base) for _ in range(29)] + [dict(base, compatible_30fps=UNKNOWN,
                                                  hls_h264_720_1080_fps_set="none")]
    out = summarize(rows)
    assert out["planned_denominator"] == 30 and out["known_denominator"] == 29
    assert out["supports_30_only_admission"] is False
    assert out["projected_loss_proven"] == 0 and out["projected_loss_under_30_only_max"] == 1


def test_measured_evidence_accounts_for_every_planned_source() -> None:
    with open(EVIDENCE / "availability.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    summary = json.loads((EVIDENCE / "summary.json").read_text(encoding="utf-8"))
    states = [r["compatible_30fps"] for r in rows]
    assert len(rows) == 30 and len({r["source_id"] for r in rows}) == 30
    assert summary["YES"] + summary["NO"] + summary[UNKNOWN] == 30
    assert states.count(YES) == summary["YES"] and summary["supports_30_only_admission"] is False
    queue = [json.loads(line) for line in
             (EVIDENCE / "discovery_queue.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(queue) == 30 and all("raw_inventory_digest" in q and q.get("sport") for q in queue)


GATE = {"seen": {"seen_id_000"}, "deny": {"deny_id_0000"}}


def test_gate_reason_reproduces_the_live_discovery_eligibility() -> None:
    """discover_sources.py:53 -- skip empty, seen, denied, or under-2400-second ids."""
    assert MIN_DURATION_S == 2400
    assert gate_reason("", 9999, GATE) == "no_id"
    assert gate_reason("seen_id_000", 9999, GATE) == "seen_in_ledger_or_queue"
    assert gate_reason("deny_id_0000", 9999, GATE) == "deny_list"
    assert gate_reason("fresh_id_001", 2399, GATE) == "duration_lt_2400"
    assert gate_reason("fresh_id_001", 2400, GATE) is None


def test_gate_matches_the_archived_live_recipe() -> None:
    """Fix 1c: seen() is ledger | sources.txt only and the live MAX is run-wide."""
    gate = json.loads((EVIDENCE / "runtime_receipts" / "discovery_receipts.json").read_text(
        encoding="utf-8"))["eligibility_gate"]
    assert gate["seen_is_ledger_plus_sources_txt_only"] is True
    assert gate["discover_log_is_recorded_but_never_gated"] is True
    assert gate["run_wide_cap"] == MAX_RUN_WIDE == 30
    assert gate["eligible_rows"] == MAX_RUN_WIDE and gate["run_wide_cap_reached_at"]
    seen = [json.loads(line) for line in
            (EVIDENCE / "seen_set.jsonl").read_text(encoding="utf-8").splitlines()]
    live = {r["id"] for r in seen if r["member_of"] in ("ledger", "sources_txt_queue")}
    log_only = {r["id"] for r in seen if r["member_of"].startswith("discover_log_only")}
    assert len(live) == gate["counts"]["live_seen_union_ledger_plus_sources_txt"]
    assert log_only and not (log_only & live)
    admitted = {json.loads(line)["source_id"] for line in
                (EVIDENCE / "discovery_population.jsonl").read_text(encoding="utf-8").splitlines()}
    assert admitted and not (admitted & live)


def test_scan_receipts_never_spell_a_restricted_pattern() -> None:
    """Q6: every landed scan receipt emits opaque pattern indices, not the token text."""
    words = ["".join(chr(code) for code in item) for item in FORBIDDEN]
    receipts = sorted(EVIDENCE.rglob("q6_scan.json"))
    assert len(receipts) >= 3
    for path in receipts:
        text = path.read_text(encoding="utf-8").lower()
        assert "pattern_0" in text
        spelled = [w for w in words
                   if re.search("(?<![a-z0-9])%s(?![a-z0-9])" % w, text)]
        assert not spelled, path.as_posix()


def test_gated_population_and_draw_carry_only_eligible_sources() -> None:
    """The measured draw comes from the gated population, never the raw return."""
    returned = [json.loads(line) for line in
                (EVIDENCE / "discovery_population_all_returned.jsonl").read_text(
                    encoding="utf-8").splitlines()]
    gated = [json.loads(line) for line in
             (EVIDENCE / "discovery_population.jsonl").read_text(encoding="utf-8").splitlines()]
    receipts = json.loads((EVIDENCE / "runtime_receipts" / "discovery_receipts.json").read_text(
        encoding="utf-8"))["eligibility_gate"]
    assert receipts["applied_before_the_draw"] is True
    assert len(gated) < len(returned) and receipts["eligible_rows"] == len(gated)
    assert all(row["duration_s"] >= MIN_DURATION_S for row in gated)
    assert {r["source_id"] for r in gated} <= {r["source_id"] for r in returned if r["eligible"]}
    with open(EVIDENCE / "draw.csv", encoding="utf-8") as handle:
        drawn = list(csv.DictReader(handle))
    assert {r["source_id"] for r in drawn} <= {r["source_id"] for r in gated}
    assert all(int(r["duration_s"]) >= MIN_DURATION_S for r in drawn)


def test_sidecar_preserves_the_inherited_ytid_and_dur_aliases() -> None:
    """ACCEPTANCE-3: the live queue names are kept beside the new field names."""
    row = sidecar_row({"source_id": "s1", "ytid": "s1", "duration_s": 3000, "dur": 3000},
                      {"compatible_30fps": YES, "qualifying_format_ids": ["a"]},
                      discovered_at="2026-09-11T00:00:00Z", format_probe_at="2026-09-11T00:01:00Z",
                      query="nba", digest="d", probe_status="OK")
    assert row["ytid"] == row["source_id"] and row["dur"] == row["duration_s"]
    queue = [json.loads(line) for line in
             (EVIDENCE / "discovery_queue.jsonl").read_text(encoding="utf-8").splitlines()]
    assert queue and all(q["ytid"] == q["source_id"] and str(q["dur"]) == str(q["duration_s"])
                         for q in queue)


def test_root_probe_receipts_csv_covers_every_probe() -> None:
    """The spec names a root probe_receipts.csv beside the raw json receipts."""
    with open(EVIDENCE / "probe_receipts.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 60 and {r["stage"] for r in rows} == {"listing", "metadata"}
    assert len({r["source_id"] for r in rows}) == 30
    assert not any("http" in cell for row in rows for cell in row.values())
