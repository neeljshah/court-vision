"""G331 -- the harness frame-denominator sidecar and the two reader fixes, hand-pinned.

n = 1 CONSTRUCT (Q7): every value below is enumerated by hand, not sampled. No route is run,
no video is opened, no archive is read and no pod is touched.
"""
import json

from scripts.platformkit.tracking.g310_instance_key import rows_per_frame
from scripts.platformkit.tracking.g310_native_input_arm import p95, proxies
from scripts.platformkit.tracking.g331_evaluated_frames_sidecar import (
    ROUTE_SIDECAR, SIDECAR_NAME, frame_denominators, game_id, modal_gap, p95_nearest_rank,
    span_positions, write_sidecar,
)

ROUTE_REASON = "max_frames_is_detector_dependent_in_this_route"
# Frames 90, 93, 96 emit person rows; 99 is processed but emits none. Stride 3 throughout.
TRACKING_CSV = "frame,player_id\n90,1\n90,2\n93,1\n96,1\n"
BALL_CSV = "frame,detected\n90,1\n93,1\n96,0\n99,0\n"


def _route_dir(tmp_path, **sidecar):
    payload = {"schema_version": "g206-v1", "decoded_frames": None, "stride": None,
               "max_frames": 1500, "start_frame": 0, "evaluated_frames": None,
               "reason": ROUTE_REASON, "source_path": str(tmp_path / "absent.mp4")}
    payload.update(sidecar)
    (tmp_path / ROUTE_SIDECAR).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (tmp_path / "tracking_data.csv").write_text(TRACKING_CSV, encoding="utf-8")
    (tmp_path / "ball_tracking.csv").write_text(BALL_CSV, encoding="utf-8")
    return tmp_path


def test_sidecar_round_trip_carries_the_route_null_verbatim(tmp_path):
    route = _route_dir(tmp_path)
    before = (route / ROUTE_SIDECAR).read_bytes()
    path = write_sidecar(route)
    assert path.name == SIDECAR_NAME
    out = json.loads(path.read_text(encoding="utf-8"))
    # The route's own count is carried, never guessed, and its reason comes through verbatim.
    assert out["evaluated_frames"] is None
    assert out["evaluated_frames_reason"] == ROUTE_REASON
    assert out["decoded_frames"] is None
    assert out["frame_cap"] == 1500
    # Three EMITTED frames, four PROCESSED, four strided positions across 90..99.
    assert out["emitted_frames"] == 3
    assert out["processed_frames_reconstructed"] == 4
    assert out["delivered_frames_in_span_reconstructed"] == 4
    assert out["stride"] == 3
    assert out["field_sources"]["stride"] == "reconstructed_from_ball_table"
    assert out["source_frames"] is None and out["source_frames_method"] == "source_absent"
    # B2: the route's own sidecar is read-only.
    assert (route / ROUTE_SIDECAR).read_bytes() == before


def test_sidecar_prefers_the_route_stride_when_the_route_records_one(tmp_path):
    out = frame_denominators(_route_dir(tmp_path, stride=5))
    assert out["stride"] == 5
    assert out["field_sources"]["stride"] == "route_sidecar.stride"
    # 90..99 is not a whole number of 5-frame steps, so the span is NOT KNOWABLE.
    assert out["delivered_frames_in_span_reconstructed"] is None


def test_an_explicit_zero_is_read_as_present_by_both_readers():
    base = {"person_rows": 10, "denominator_evaluated_frames": 0, "frames_with_rows": 5,
            "denominator_reason": ROUTE_REASON}
    out = rows_per_frame(base)
    # Before the fix a truthiness test sent this to frames_with_rows and printed 2.0.
    assert out["person_rows_per_frame_denominator_source"] == "evaluated_frames"
    assert out["person_rows_per_frame_denominator"] == 0
    assert out["person_rows_per_frame"] is None
    base["denominator_evaluated_frames"] = None
    assert rows_per_frame(base)["person_rows_per_frame_denominator_source"] == "frames_with_rows"
    assert rows_per_frame(base)["person_rows_per_frame"] == 2.0
    rows = [{"frame": "90", "player_id": "1", "bbox_x1": "0", "bbox_y1": "0",
             "bbox_x2": "2", "bbox_y2": "4"}]
    arm = proxies(rows, [], evaluated_frames=0, source_height=1080)
    assert arm["denominator_evaluated_frames"] == 0
    assert arm["person_rows_per_evaluated_frame"] is None


def test_the_two_percentile_estimators_are_pinned_and_can_disagree():
    sample = [float(v) for v in range(1, 13)]  # n = 12
    # Kept estimator: sorted[round(0.95 * 11)] = sorted[10] = 11.0.
    assert p95(sample) == 11.0
    # True nearest-rank: the ceil(0.95 * 12) = 12th smallest = 12.0.
    assert p95_nearest_rank(sample) == 12.0
    assert p95([]) is None and p95_nearest_rank([]) is None
    assert p95([0.05, 0.1, 0.2]) == p95_nearest_rank([0.05, 0.1, 0.2]) == 0.2


def test_stride_and_span_helpers_refuse_what_they_cannot_know():
    assert modal_gap([90, 93, 96, 99, 105]) == 3
    assert modal_gap([]) is None and modal_gap([7]) is None
    assert span_positions([90, 99], 3) == 4
    assert span_positions([90, 95, 96], 3) is None   # 5 is not a multiple of the stride
    assert span_positions([90], 3) is None
    assert span_positions([90, 93], None) is None


def test_game_id_strips_the_pass_prefix_and_the_arm_suffix():
    assert game_id("pilot__wnba_01_1080p_armP_repeat") == "wnba_01_1080p"
    assert game_id("postprereg__wnba_01_1080p_armN") == "wnba_01_1080p"
    assert game_id("pilot__ncaa_basketball_mRkuGgeECak_armP") == "ncaa_basketball_mRkuGgeECak"
