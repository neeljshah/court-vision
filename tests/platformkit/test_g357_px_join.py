"""Focused construct tests for the additive G357 pixel-space join."""
import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g357_px_join import coordinate_ratios, px_analysis, px_rows


def test_px_join_uses_pixel_fields_and_counts_exclusions() -> None:
    players = [{"frame": str(frame), "track_id": "7", "x": str(frame * 2), "y": "10"}
               for frame in range(4)]
    balls = [{"frame": str(frame), "detected": "1", "ball_x2d": "9999", "ball_y2d": "9999",
              "ball_x2d_px": str(frame * 2), "ball_y2d_px": "10"} for frame in range(4)]
    rows, reasons = px_rows(balls + [{"frame": "4", "ball_x2d_px": "", "ball_y2d_px": "10"}], True)
    assert len(rows) == 4 and reasons == {"missing_px_header": 0, "missing_px_coordinate": 1}
    states, survival = px_analysis("construct", players, balls, 0, 3, 720, True)
    stages = {row["stage"]: row["n"] for row in survival if row["record_type"] == "stage"}
    assert stages["player_within_radius"] == 4 and states[-1]["owner_id"] == "7"
    assert {row["join_source"] for row in states} == {"px"}


def test_missing_header_and_g351_axis_ratios_are_explicit() -> None:
    _, reasons = px_rows([{"frame": "1", "ball_x2d": "1"}], False)
    assert reasons == {"missing_px_header": 1, "missing_px_coordinate": 0}
    players = [{"frame": "1", "x": "0", "y": "0"}, {"frame": "2", "x": "10", "y": "20"}]
    balls = [{"frame": "1", "ball_x2d_px": "0", "ball_y2d_px": "0"},
             {"frame": "2", "ball_x2d_px": "15", "ball_y2d_px": "20"}]
    assert coordinate_ratios(players, balls) == (1.5, 1.0)


def test_prereg_seal_normalizes_crlf_without_git_history() -> None:
    path = Path("docs/evidence/tracking/g357_prereg_2026-09-08.md")
    normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    body, seal = normalized.rsplit(b"SEAL sha256 ", 1)
    assert b"\n" not in seal.strip()
    assert hashlib.sha256(body).hexdigest() == seal.strip().decode("ascii")
