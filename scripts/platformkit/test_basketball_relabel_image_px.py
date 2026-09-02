"""Focused tests for the basketball image-pixel relabel migration."""
import pandas as pd
from types import SimpleNamespace

from scripts.platformkit.basketball_relabel_image_px import reemit_game, relabel_all
from scripts.platformkit.tracking_schema import write_ball_telemetry_declaration


def _source_rows() -> pd.DataFrame:
    return pd.DataFrame({
        "frame": [0, 0, 1, 1], "timestamp": [0.0, 0.0, 0.1, 0.1],
        "player_id": [1, 2, 1, 2], "team": ["a", "b", "a", "b"],
        "x_position": [100, 200, 110, 210], "y_position": [300, 400, 310, 410],
        "ft_x": [1.0, 2.0, 1.1, 2.1], "ft_y": [3.0, 4.0, 3.1, 4.1],
        # Source-plane bbox, stored by the pipeline as x1,y1,x2,y2.
        "bbox_x1": [10.0, 20.0, 12.0, 22.0], "bbox_y1": [5.0, 6.0, 7.0, 8.0],
        "bbox_x2": [30.0, 40.0, 32.0, 42.0], "bbox_y2": [50.0, 60.0, 52.0, 62.0],
    })


def test_relabel_all_preserves_pixels_and_fails_harness(tmp_path):
    tracking = tmp_path / "tracking"
    for index in range(5):
        game = tracking / "wnba_{:02d}".format(index + 1)
        game.mkdir(parents=True)
        _source_rows().to_csv(game / "tracking_data.csv", index=False)
    for index in range(6):
        game = tracking / "ncaa_{}".format(index + 1)
        game.mkdir(parents=True)
        _source_rows().to_csv(game / "tracking_data.csv", index=False)

    results = relabel_all(tracking)

    assert len(results) == 11
    assert all(result.verdict_before == "FAIL" for result in results)
    assert all(result.verdict_after == "FAIL" for result in results)
    result_path = tracking / "wnba_01" / "tracking_data.csv"
    relabeled = pd.read_csv(result_path)
    assert relabeled.columns.tolist() == [
        "frame", "track_id", "cls", "x", "y", "coordinate_calibration_reason",
        "map2d_x", "map2d_y", "coordinate_space", "observation", "calibration",
    ]
    # x/y are the SOURCE-PLANE bbox foot point; the minimap canvas that used to
    # masquerade as x/y now rides under its own name.
    assert relabeled[["x", "y"]].values.tolist() == [
        [20.0, 50.0], [30.0, 60.0], [22.0, 52.0], [32.0, 62.0]]
    assert relabeled[["map2d_x", "map2d_y"]].values.tolist() == [
        [100, 300], [200, 400], [110, 310], [210, 410]]
    assert set(relabeled["coordinate_space"]) == {"image_px"}
    assert set(relabeled["coordinate_calibration_reason"]) == {"no_court_calibration_sidecar"}
    assert (tracking / "wnba_01" / "tracking_data.csv.pre_relabel").exists()


def test_reemit_game_copies_source_ball_telemetry_sidecar(monkeypatch, tmp_path):
    from scripts.platformkit.tracking import image_px_containment

    source = tmp_path / "source" / "tracking_data.csv"
    source.parent.mkdir(parents=True)
    _source_rows().to_csv(source, index=False)
    write_ball_telemetry_declaration(source, "basketball", False)
    output = tmp_path / "re_emitted" / "tracking_data.csv"
    output.parent.mkdir(parents=True)
    monkeypatch.setattr(image_px_containment, "source_resolution", lambda video: (1280, 720))
    monkeypatch.setattr(
        image_px_containment,
        "containment",
        lambda rows, width, height: SimpleNamespace(n_rows=len(rows), inside_share=1.0,
                                                     verdict="PASS"),
    )

    reemit_game(source, source, tmp_path / "clip.mp4", output)

    assert (output.parent / "tracking_capability.json").read_text(encoding="utf-8") == (
        source.parent / "tracking_capability.json").read_text(encoding="utf-8")
