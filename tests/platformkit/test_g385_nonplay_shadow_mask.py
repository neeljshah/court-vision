"""Prepare-only rails for G385's unused SHADOW mask."""

import copy
import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g385_mask import KEEP, MASK, UNKNOWN, shadow_decision
from scripts.platformkit.tracking.g385_sample import even_sections, frame_plan, interior_indices
from scripts.platformkit.tracking.g385_score import score


PREREG = (Path(__file__).resolve().parents[2] / "docs" / "evidence" / "tracking" /
          "g385_nonplay_shadow_mask_2026-09-10" / "g385_prereg_2026-09-10.md")


def test_seal_uses_lf_normalized_preregistration_bytes():
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    cut = raw.rfind(b"SEAL sha256")
    assert cut > 0
    assert raw[cut:].split()[2].decode("ascii") == hashlib.sha256(raw[:cut]).hexdigest()


def test_shadow_decision_never_mutates_input_and_absent_passes_through():
    absent = {"tick_key": "a", "p_nonplay": None, "evidence_status": "ABSENT"}
    before = copy.deepcopy(absent)
    result = shadow_decision(absent)
    assert absent == before
    assert result["shadow_decision"] == UNKNOWN
    assert "production_mask" not in result and "flag" not in result
    assert shadow_decision({"p_nonplay": 0.94, "evidence_status": "READABLE"})["shadow_decision"] == KEEP
    assert shadow_decision({"p_nonplay": 0.95, "evidence_status": "READABLE"})["shadow_decision"] == MASK


def test_unknown_is_retained_in_planned_and_mask_precision_denominators():
    rows = []
    for index in range(360):
        label = "PLAY" if index < 100 else ("NONPLAY" if index < 200 else "UNKNOWN")
        decision = "MASK" if index in (0, 100, 200) else "KEEP"
        rows.append({"tick_key": "s:%04d" % index, "reference_label": label,
                     "shadow_decision": decision, "evidence_status": "READABLE"})
    result = score(rows)
    assert result["planned_frames"] == 360 and result["reference_unknown"] == 160
    assert result["masked_frames"] == 3
    assert result["mask_precision_all_masked"][0] == 1 / 3
    assert result["unknown_all_planned"][0] == 160 / 360


def test_even_sampler_is_not_a_head_slice_and_plans_full_denominator():
    assert interior_indices(120)[0] > 0 and interior_indices(120)[-1] < 119
    sections = [{"section_id": "s%02d" % index, "video_id": "v%02d" % (index % 10),
                 "competition": "c", "offset_s": str(index), "frame_count": "120"}
                for index in range(60)]
    picked = even_sections(sections)
    assert picked[0]["section_id"] != "s00" and picked[-1]["section_id"] != "s29"
    planned = frame_plan(picked)
    assert len(planned) == len({row["tick_key"] for row in planned}) == 360
