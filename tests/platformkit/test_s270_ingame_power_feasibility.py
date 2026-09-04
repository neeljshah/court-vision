"""Focused S270 feasibility formula, census, exhaustive-row, and seal checks."""
import hashlib
import csv
import json
from pathlib import Path

from scripts.platformkit.s270_ingame_power_feasibility import (
    SCREENS, build_table, census_identity, required_n_eff,
)


def test_s270_required_n_eff_and_eight_rows():
    s06 = next(screen for screen in SCREENS if screen.name == "S06")
    assert round(required_n_eff(s06), 6) == 66914.393835
    counts = {screen.name: [{"name": "only", "clusters": 1, "eligible": True}] for screen in SCREENS}
    assert len(build_table(counts)) == 8


def test_s270_v2_prereg_seal_is_lf_normalized_file_hash():
    path = Path("docs/evidence/harness/S270_attempt_1c_S82_prereg_2026-09-04_v2.md")
    body = path.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = body.split(b"SHA256_SEAL:", 1)
    assert hashlib.sha256(prefix).hexdigest() == seal.strip().decode("ascii")


def test_s270_census_identity_fixture_and_real_attempt2_corpus():
    fixture = [
        {"game_id": "a", "stage": "before_eligibility", "reason": "NO_FINITE_E4"},
        {"game_id": "b", "stage": "without_finite_oof", "reason": "NO_FINITE_OOF"},
    ]
    assert census_identity(4, fixture, {"c", "d"})["eligible_games"] == 3
    root = Path("docs/evidence/harness")
    report = json.loads((root / "S270_attempt_1c_S82_rescreen_2026-09-04_attempt2.json").read_text())
    with (root / "S270_attempt_1c_S82_excluded_games_by_reason_2026-09-04_attempt2.csv").open(newline="") as handle:
        exclusions = list(csv.DictReader(handle))
    with (root / "S270_attempt_1c_S82_rescreen_2026-09-04_attempt2.csv").open(newline="") as handle:
        scored_ids = {row["game_id"] for row in csv.DictReader(handle)}
    assert census_identity(178, exclusions, scored_ids) == report["census"]
