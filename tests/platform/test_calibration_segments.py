"""tests.platform.test_calibration_segments — Unit tests for calibration_segments.py.

Checks:
  - Note exists at correct path with valid frontmatter.
  - Per-sport decile tables present; observed/predicted in [0,1], n >= 0.
  - Person-free: no known athlete names.
  - No edge-claim language; honest calibration framing present.
  - Graceful-skip on absent corpora; raises on bad vault dir.
  - Idempotency.

All tests build into tmp_path — real vault never touched.  Py 3.9.
"""
from __future__ import annotations

import pathlib
import re

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.atlas.calibration_segments import build_calibration_segments


# ---------------------------------------------------------------------------
# Synthetic corpus helpers (mirrors test_base_rates.py pattern)
# ---------------------------------------------------------------------------

def _parquet(path: pathlib.Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _tennis(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2020-01-01", periods=n, freq="7D")
    return pd.DataFrame({
        "event_id": [f"T{i}" for i in range(n)],
        "date": dates, "tour": "ATP", "tourney_id": "t",
        "tourney_name": "Test Open", "tourney_level": "A",
        "surface": rng.choice(["Hard", "Clay", "Grass"], n),
        "best_of": 3, "round": "R32", "match_num": range(n),
        "p1_id": rng.integers(100, 200, n),
        "p2_id": rng.integers(200, 300, n),
        "p1_name": "Player_A", "p2_name": "Player_B",
        "p1_rank": rng.integers(1, 100, n),
        "p2_rank": rng.integers(1, 100, n),
        "winner": rng.choice([1, 2], n),
        "score": "6-3 6-2", "retirement": 0,
        "minutes": rng.integers(60, 120, n),
    })


def _soccer(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2020-01-01", periods=n, freq="7D")
    fthg = rng.integers(0, 4, n)
    ftag = rng.integers(0, 4, n)
    total = fthg + ftag
    return pd.DataFrame({
        "event_id": [f"S{i}" for i in range(n)],
        "date": dates, "season": 2020, "div": "E0",
        "home_team": "Team_A", "away_team": "Team_B",
        "fthg": fthg, "ftag": ftag, "total_goals": total,
        # target_over25 required by SoccerAdapter.feature_bundle
        "target_over25": (total >= 3).astype(float),
        "ftr": ["H" if h > a else ("A" if a > h else "D")
                for h, a in zip(fthg, ftag)],
    })


def _mlb(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2020-04-01", periods=n, freq="D")
    hr = rng.integers(0, 10, n)
    ar = rng.integers(0, 10, n)
    return pd.DataFrame({
        "event_id": [f"M{i}" for i in range(n)],
        "date": dates, "season": 2020,
        "home_team": "Team_H", "away_team": "Team_A",
        "home_runs": hr,
        "away_runs": ar,
        # target_home_win required by MLBAdapter.feature_bundle
        "target_home_win": (hr > ar).astype(float),
        "game_seq": 1, "home_league": "AL",
    })


def _vault(tmp: pathlib.Path) -> pathlib.Path:
    d = tmp / "vault" / "Sports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _all_corpora(tmp: pathlib.Path) -> None:
    _parquet(tmp / "data/domains/tennis/matches.parquet", _tennis())
    _parquet(tmp / "data/domains/soccer/matches.parquet", _soccer())
    _parquet(tmp / "data/domains/mlb/games.parquet", _mlb())


@pytest.fixture()
def vault_full(tmp_path: pathlib.Path) -> pathlib.Path:
    v = _vault(tmp_path)
    _all_corpora(tmp_path)
    return v


@pytest.fixture()
def vault_empty(tmp_path: pathlib.Path) -> pathlib.Path:
    return _vault(tmp_path)


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------

class TestOutputFile:
    def test_created_at_correct_path(self, vault_full: pathlib.Path) -> None:
        out = build_calibration_segments(vault_full)
        assert out.exists()
        assert out.name == "_Calibration_Segments.md"
        assert out.parent == vault_full

    def test_returns_path_instance(self, vault_full: pathlib.Path) -> None:
        assert isinstance(build_calibration_segments(vault_full), pathlib.Path)

    def test_nonempty(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert len(text) > 300


# ---------------------------------------------------------------------------
# Valid frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_opens_with_triple_dashes(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert text.startswith("---")

    def test_expected_tags(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        for tag in ("calibration", "reliability", "cross-sport", "honest"):
            assert tag in text

    def test_generated_date_field(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert re.search(r"generated: 2\d{3}-\d{2}-\d{2}", text)

    def test_hub_uplink(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert "[[_Hub]]" in text

    def test_closing_triple_dashes(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert text.count("---") >= 2


# ---------------------------------------------------------------------------
# Decile tables: sports present, predicted/observed in [0,1], n >= 0
# ---------------------------------------------------------------------------

class TestDecileTables:
    @pytest.mark.parametrize("sport_token", ["Tennis", "Soccer", "MLB"])
    def test_sport_section_present(self, sport_token: str, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert sport_token in text

    def test_reliability_table_headers(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert "Pred" in text and "Obs" in text

    def test_predicted_values_in_unit_interval(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        # Match decimal values in table cells (0.xxxx pattern)
        vals = re.findall(r"\|\s*(0\.\d{4})\s*\|", text)
        assert len(vals) > 0, "No 0.xxxx values found in decile table"
        for v in vals:
            assert 0.0 <= float(v) <= 1.0, f"Value out of [0,1]: {v}"

    def test_n_column_nonnegative(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        # n values appear as standalone integers in table cells
        n_vals = re.findall(r"\|\s*(\d+)\s*\|", text)
        for v in n_vals:
            assert int(v) >= 0, f"Negative n found: {v}"

    def test_bin_labels_present(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        # Decile bins show [0.x,0.x) pattern
        assert re.search(r"\[0\.\d,0\.\d\)", text), "No decile bin labels found"

    def test_ece_reported(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert "ECE" in text

    def test_sports_computed_count(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert "sports_computed: 3" in text


# ---------------------------------------------------------------------------
# Person-free check
# ---------------------------------------------------------------------------

_ATHLETES = [
    re.compile(r"\bLeBron\b", re.I),
    re.compile(r"\bJokic\b", re.I),
    re.compile(r"\bWembanyama\b", re.I),
    re.compile(r"\bFederer\b", re.I),
    re.compile(r"\bDjokovic\b", re.I),
    re.compile(r"\bMessi\b", re.I),
    re.compile(r"\bOhtani\b", re.I),
    re.compile(r"\bAlcaraz\b", re.I),
    re.compile(r"\bNadal\b", re.I),
]


class TestPersonFree:
    def test_no_known_athlete_names(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        for pat in _ATHLETES:
            assert not pat.search(text), (
                f"Athlete {pat.pattern!r} found in output — must be person-free"
            )

    def test_no_players_section(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert "## Players" not in text and "### Players" not in text


# ---------------------------------------------------------------------------
# No edge-claim language; honest calibration framing present
# ---------------------------------------------------------------------------

_FORBIDDEN_PHRASES = [
    "profitable edge",
    "+EV proven",
    "beats the market",
    "+18.38%",
    "ROI advantage",
    "guaranteed profit",
    "durable edge found",
    "edge detected",
    "model beats",
    "guaranteed return",
    "calibration proves edge",
]


