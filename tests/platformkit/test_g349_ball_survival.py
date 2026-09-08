"""Focused tests for G349's additive survival diagnostics and prereg seal."""
from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.platformkit.tracking.g349_ball_survival import analyze_window, artifact_rows, pooled_stage_rows
from scripts.platformkit.tracking.g344_synthetic import case


def test_survival_stages_are_cumulative_and_full_frame() -> None:
    _, players, balls, _, _, _ = case(0)
    states, rows = analyze_window("construct", players, balls, 0, 3, 720)
    stages = {row["stage"]: row["n"] for row in rows if row["record_type"] == "stage"}
    assert stages == {"frames": 4, "any_ball_row": 4, "detected_ball": 4, "player_rows": 4,
                      "player_within_radius": 4, "prerequisite_available": 1,
                      "motion_agreement": 1, "accepted_ownership": 1}
    assert states[-1]["prerequisite_available"] == 1
    rendered = artifact_rows(rows)
    assert rendered[0]["n"] == "000004" and rendered[0]["share_per_mille"] == "1000"
    assert any(row["record_type"] == "coordinate" and row["source_height"] == "720" for row in rendered)
    pooled = {row["stage"]: row["n"] for row in pooled_stage_rows(rows + rows)}
    assert pooled["frames"] == 8 and pooled["accepted_ownership"] == 2


def test_prereg_seal_normalizes_crlf_without_git_history() -> None:
    path = Path("docs/evidence/tracking/g349_prereg_2026-09-08.md")
    normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    body, seal = normalized.rsplit(b"SEAL sha256 ", 1)
    assert b"\n" not in seal.strip()
    assert hashlib.sha256(body).hexdigest() == seal.strip().decode("ascii")
