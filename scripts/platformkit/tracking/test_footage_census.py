import numpy as np

from scripts.platformkit.tracking.footage_census import (
    sport_of, verdict_of, _edge_density, discover_clips,
)


def test_sport_of_handles_all_naming_conventions():
    from pathlib import Path
    assert sport_of(Path("football__football_x.mp4")) == "football"
    assert sport_of(Path("football_BN5zn5hu1zU.mp4")) == "football"
    assert sport_of(Path("football.mp4")) == "football"


def test_verdict_thresholds():
    assert verdict_of(surface_frac=0.0, graphic_frac=0.0) == "JUNK"
    assert verdict_of(surface_frac=0.2, graphic_frac=0.0) == "SUSPECT"
    assert verdict_of(surface_frac=0.9, graphic_frac=0.9) == "SUSPECT"
    assert verdict_of(surface_frac=0.9, graphic_frac=0.1) == "USABLE"


def test_edge_density_flat_frame_is_near_zero():
    flat = np.full((180, 320, 3), 100, dtype=np.uint8)
    assert _edge_density(flat) < 0.02


def test_discover_clips_skips_fragments_and_quarantined(tmp_path):
    (tmp_path / "football__good.mp4").write_bytes(b"v")
    (tmp_path / "football__partial.f137.mp4").write_bytes(b"v")
    bad = tmp_path / "football__bad.mp4"
    bad.write_bytes(b"v")
    bad.with_suffix(".mp4.json").write_text('{"sport_verified": false}')

    clips = discover_clips([tmp_path])

    assert [c.name for c in clips] == ["football__good.mp4"]
