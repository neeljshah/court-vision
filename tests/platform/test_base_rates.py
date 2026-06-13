"""tests.platform.test_base_rates — Unit tests for scripts.platformkit.atlas.base_rates.

Checks: note exists with valid frontmatter; all available sports + base rates in [0,1] + n;
person-free; no edge-claim language; graceful-skip on absent corpora; raises on bad dir;
idempotency.  All tests build into tmp_path — real vault is never touched.  Py 3.9.
"""
from __future__ import annotations

import pathlib
import re

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.atlas.base_rates import build_base_rates


# ---------------------------------------------------------------------------
# Synthetic corpus helpers
# ---------------------------------------------------------------------------

def _parquet(path: pathlib.Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _tennis(n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="7D")
    return pd.DataFrame({
        "event_id": [f"T{i}" for i in range(n)],
        "date": dates, "tour": "ATP", "tourney_id": "t", "tourney_name": "Test Open",
        "tourney_level": "A", "surface": "Hard", "best_of": 3, "round": "R32",
        "match_num": range(n),
        "p1_id": rng.integers(100, 200, n), "p2_id": rng.integers(200, 300, n),
        "p1_name": "Player_A", "p2_name": "Player_B",
        "p1_rank": rng.integers(1, 100, n), "p2_rank": rng.integers(1, 100, n),
        "winner": rng.choice([1, 2], n), "score": "6-3 6-2",
        "retirement": 0, "minutes": rng.integers(60, 120, n),
    })


def _soccer(n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="7D")
    fthg = rng.integers(0, 4, n)
    ftag = rng.integers(0, 4, n)
    total = fthg + ftag
    return pd.DataFrame({
        "event_id": [f"S{i}" for i in range(n)], "date": dates, "season": 2020,
        "div": "E0", "home_team": "Team_A", "away_team": "Team_B",
        "fthg": fthg, "ftag": ftag, "total_goals": total,
        "ftr": ["H" if h > a else ("A" if a > h else "D") for h, a in zip(fthg, ftag)],
    })


def _mlb(n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-04-01", periods=n, freq="D")
    return pd.DataFrame({
        "event_id": [f"M{i}" for i in range(n)], "date": dates, "season": 2020,
        "home_team": "Team_H", "away_team": "Team_A",
        "home_runs": rng.integers(0, 10, n), "away_runs": rng.integers(0, 10, n),
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
        out = build_base_rates(vault_full)
        assert out.exists() and out.name == "_Base_Rates.md" and out.parent == vault_full

    def test_returns_path_instance(self, vault_full: pathlib.Path) -> None:
        assert isinstance(build_base_rates(vault_full), pathlib.Path)

    def test_nonempty(self, vault_full: pathlib.Path) -> None:
        assert len(build_base_rates(vault_full).read_text(encoding="utf-8")) > 300


# ---------------------------------------------------------------------------
# Valid frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_opens_with_triple_dashes(self, vault_full: pathlib.Path) -> None:
        assert build_base_rates(vault_full).read_text(encoding="utf-8").startswith("---")

    def test_expected_tags(self, vault_full: pathlib.Path) -> None:
        text = build_base_rates(vault_full).read_text(encoding="utf-8")
        for tag in ("base-rates", "meta", "cross-sport", "honest"):
            assert tag in text

    def test_generated_date_field(self, vault_full: pathlib.Path) -> None:
        assert re.search(r"generated: 2\d{3}-\d{2}-\d{2}",
                         build_base_rates(vault_full).read_text(encoding="utf-8"))

    def test_hub_uplink(self, vault_full: pathlib.Path) -> None:
        assert "[[_Hub]]" in build_base_rates(vault_full).read_text(encoding="utf-8")

    def test_closing_triple_dashes(self, vault_full: pathlib.Path) -> None:
        assert build_base_rates(vault_full).read_text(encoding="utf-8").count("---") >= 2


# ---------------------------------------------------------------------------
# Sports coverage, base rates in [0, 1], n > 0
# ---------------------------------------------------------------------------

class TestSportCoverage:
    @pytest.mark.parametrize("sport_token", ["Tennis", "Soccer", "MLB"])
    def test_sport_mentioned(self, sport_token: str, vault_full: pathlib.Path) -> None:
        assert sport_token in build_base_rates(vault_full).read_text(encoding="utf-8")

    def test_base_rates_in_unit_interval(self, vault_full: pathlib.Path) -> None:
        text = build_base_rates(vault_full).read_text(encoding="utf-8")
        vals = re.findall(r"\|\s*(0\.\d{4})\s*\|", text)
        assert len(vals) > 0, "No base-rate values found in output"
        for v in vals:
            assert 0.0 <= float(v) <= 1.0, f"Base rate out of [0,1]: {v}"

    def test_n_values_positive(self, vault_full: pathlib.Path) -> None:
        text = build_base_rates(vault_full).read_text(encoding="utf-8")
        vals = re.findall(r"\|\s*([\d,]+)\s*\|\s*0\.\d{4}", text)
        assert len(vals) > 0, "No n-value rows found in table"
        for v in vals:
            assert int(v.replace(",", "")) > 0

    def test_summary_table_header(self, vault_full: pathlib.Path) -> None:
        text = build_base_rates(vault_full).read_text(encoding="utf-8")
        assert "Base Rate" in text and ("Market Shape" in text or "Market" in text)


# ---------------------------------------------------------------------------
# Person-free check
# ---------------------------------------------------------------------------

_ATHLETES = [
    re.compile(r"\bLeBron\b", re.I), re.compile(r"\bJokic\b", re.I),
    re.compile(r"\bWembanyama\b", re.I), re.compile(r"\bFederer\b", re.I),
    re.compile(r"\bDjokovic\b", re.I), re.compile(r"\bMessi\b", re.I),
    re.compile(r"\bOhtani\b", re.I), re.compile(r"\bAlcaraz\b", re.I),
]


class TestPersonFree:
    def test_no_known_athlete_names(self, vault_full: pathlib.Path) -> None:
        text = build_base_rates(vault_full).read_text(encoding="utf-8")
        for pat in _ATHLETES:
            assert not pat.search(text), f"Athlete {pat.pattern!r} found — must be person-free"

    def test_no_players_section(self, vault_full: pathlib.Path) -> None:
        text = build_base_rates(vault_full).read_text(encoding="utf-8")
        assert "## Players" not in text and "### Players" not in text


# ---------------------------------------------------------------------------
# No edge-claim language
# ---------------------------------------------------------------------------

_FORBIDDEN = [
    "profitable edge", "+EV proven", "beats the market", "+18.38%",
    "ROI advantage", "guaranteed profit", "durable edge found", "edge detected",
    "model beats", "guaranteed return",
]


class TestNoEdgeClaims:
    @pytest.mark.parametrize("phrase", _FORBIDDEN)
    def test_forbidden_phrase_absent(self, phrase: str, vault_full: pathlib.Path) -> None:
        assert phrase.lower() not in build_base_rates(vault_full).read_text(encoding="utf-8").lower()

    def test_honest_disclaimer_present(self, vault_full: pathlib.Path) -> None:
        text = build_base_rates(vault_full).read_text(encoding="utf-8").lower()
        assert "no edge" in text or "no edge claimed" in text

    def test_descriptive_framing_present(self, vault_full: pathlib.Path) -> None:
        assert "descriptive" in build_base_rates(vault_full).read_text(encoding="utf-8").lower()


# ---------------------------------------------------------------------------
# Graceful-skip on absent corpora
# ---------------------------------------------------------------------------

class TestGracefulSkip:
    def test_empty_vault_no_exception(self, vault_empty: pathlib.Path) -> None:
        assert build_base_rates(vault_empty).exists()

    def test_empty_vault_skipped_section(self, vault_empty: pathlib.Path) -> None:
        text = build_base_rates(vault_empty).read_text(encoding="utf-8")
        assert "Skipped" in text or "absent" in text or "skipped" in text.lower()

    def test_only_tennis_present(self, tmp_path: pathlib.Path) -> None:
        vault = _vault(tmp_path)
        _parquet(tmp_path / "data/domains/tennis/matches.parquet", _tennis())
        text = build_base_rates(vault).read_text(encoding="utf-8")
        assert "Tennis" in text and "sports_computed: 1" in text

    def test_only_mlb_present(self, tmp_path: pathlib.Path) -> None:
        vault = _vault(tmp_path)
        _parquet(tmp_path / "data/domains/mlb/games.parquet", _mlb())
        text = build_base_rates(vault).read_text(encoding="utf-8")
        assert "MLB" in text and "sports_computed: 1" in text

    def test_no_exception_missing_all_corpora(self, tmp_path: pathlib.Path) -> None:
        assert build_base_rates(_vault(tmp_path)).exists()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_raises_on_nonexistent_vault_dir(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            build_base_rates(tmp_path / "does_not_exist")


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
        t1 = _strip(build_base_rates(vault_full).read_text(encoding="utf-8"))
        t2 = _strip(build_base_rates(vault_full).read_text(encoding="utf-8"))
        assert t1 == t2
