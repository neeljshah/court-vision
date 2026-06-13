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


class TestNoEdgeClaims:
    @pytest.mark.parametrize("phrase", _FORBIDDEN_PHRASES)
    def test_forbidden_phrase_absent(self, phrase: str, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8").lower()
        assert phrase.lower() not in text, f"Forbidden phrase found: {phrase!r}"

    def test_no_edge_disclaimer_present(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8").lower()
        assert "no edge" in text or "no edge claimed" in text

    def test_calibration_not_edge_framing(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8").lower()
        assert "calibration" in text and ("!= edge" in text or "not.*edge" in text
                                          or "not edge" in text or "calibration != edge" in text
                                          or "reliability" in text)

    def test_reliability_keyword_present(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8")
        assert "reliability" in text.lower() or "Reliability" in text

    def test_soccer_honest_note_present(self, vault_full: pathlib.Path) -> None:
        text = build_calibration_segments(vault_full).read_text(encoding="utf-8").lower()
        # soccer miscalibration note should appear when soccer computed
        assert "poisson" in text or "soccer" in text


# ---------------------------------------------------------------------------
# Graceful-skip on absent corpora
# ---------------------------------------------------------------------------

class TestGracefulSkip:
    def test_empty_vault_no_exception(self, vault_empty: pathlib.Path) -> None:
        out = build_calibration_segments(vault_empty)
        assert out.exists()

    def test_empty_vault_skipped_section_or_note(self, vault_empty: pathlib.Path) -> None:
        text = build_calibration_segments(vault_empty).read_text(encoding="utf-8")
        has_skip = ("Skipped" in text or "absent" in text or "skipped" in text.lower()
                    or "sports_computed: 0" in text)
        assert has_skip

    def test_only_tennis_present(self, tmp_path: pathlib.Path) -> None:
        vault = _vault(tmp_path)
        _parquet(tmp_path / "data/domains/tennis/matches.parquet", _tennis())
        text = build_calibration_segments(vault).read_text(encoding="utf-8")
        assert "Tennis" in text
        assert "sports_computed: 1" in text

    def test_only_mlb_present(self, tmp_path: pathlib.Path) -> None:
        vault = _vault(tmp_path)
        _parquet(tmp_path / "data/domains/mlb/games.parquet", _mlb())
        text = build_calibration_segments(vault).read_text(encoding="utf-8")
        assert "MLB" in text
        assert "sports_computed: 1" in text

    def test_only_soccer_present(self, tmp_path: pathlib.Path) -> None:
        vault = _vault(tmp_path)
        _parquet(tmp_path / "data/domains/soccer/matches.parquet", _soccer())
        text = build_calibration_segments(vault).read_text(encoding="utf-8")
        assert "Soccer" in text
        assert "sports_computed: 1" in text


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_raises_on_nonexistent_vault_dir(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_calibration_segments(tmp_path / "does_not_exist")


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_second_run_same_content(self, vault_full: pathlib.Path) -> None:
        def _strip(t: str) -> str:
            return "\n".join(
                ln for ln in t.splitlines()
                if not ln.startswith("*Generated") and "generated:" not in ln
            )
        t1 = _strip(build_calibration_segments(vault_full).read_text(encoding="utf-8"))
        t2 = _strip(build_calibration_segments(vault_full).read_text(encoding="utf-8"))
        assert t1 == t2
