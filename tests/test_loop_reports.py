"""Tests for src/loop/report_generator.py.

Runs completely offline (NBA_OFFLINE=1) with an in-memory PointInTimeStore and
synthetic data so they never touch the live server or data/live/.
"""
from __future__ import annotations

import datetime
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# Ensure repo root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("NBA_OFFLINE", "1")

import pytest

from src.loop.store import PointInTimeStore, entity_key
from src.loop.signal import AsOfContext
from src.loop.error_miner import ResidualBucket
from src.loop.signal import Hypothesis
from src.loop import report_generator as rg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_store(tmp_path: Path) -> PointInTimeStore:
    """An isolated in-memory+disk store written to a temp dir."""
    store = PointInTimeStore(store_dir=tmp_path / "loop_store", autoload=False)
    return store


@pytest.fixture()
def tmp_reports_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect REPORTS_DIR to a temp path so tests do not pollute the repo."""
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(rg, "REPORTS_DIR", reports)
    return reports


@pytest.fixture()
def populated_store(tmp_store: PointInTimeStore) -> PointInTimeStore:
    """Store pre-populated with team + player atlas sections."""
    as_of = "2026-05-29"

    # Team atlases
    for tri in ["BOS", "DAL"]:
        tmp_store.write_atlas("team", tri, "ratings", as_of, {
            "off_rtg": 115.0 + (2 if tri == "BOS" else 0),
            "def_rtg": 108.0,
            "net_rtg": 7.0,
            "pace": 98.5,
        }, {"source": "team_advanced_stats.parquet", "n": 82, "confidence": "high"})
        tmp_store.write_atlas("team", tri, "defense_scheme", as_of, {
            "primary_scheme": "drop" if tri == "BOS" else "switch",
            "drop_rate": 0.55 if tri == "BOS" else 0.20,
            "switch_rate": 0.25 if tri == "BOS" else 0.60,
            "blitz_rate": 0.10,
        }, {"source": "defensive_schemes.parquet", "n": 82, "confidence": "high"})
        tmp_store.write_atlas("team", tri, "rebounding", as_of, {
            "off_reb_pct": 0.28,
            "def_reb_pct": 0.72,
            "total_reb_pg": 45.0,
        }, {"source": "team_reb_context.parquet", "n": 82, "confidence": "high"})

    # Player atlas
    for pid in [1628983, 1629029]:
        tmp_store.write_atlas("player", pid, "scoring_usage", as_of, {
            "pts_pg": 28.5,
            "min_per_game": 34.0,
            "usage_rate": 0.31,
        }, {"source": "player_profile_features.parquet", "n": 60, "confidence": "high"})
        tmp_store.write_atlas("player", pid, "shot_profile", as_of, {
            "rim_freq": 0.35,
            "mid_freq": 0.15,
            "three_freq": 0.40,
        }, {"source": "shot_diet.parquet", "n": 60, "confidence": "high"})

    return tmp_store


def _make_ctx(*, team: str = "BOS", opp: str = "DAL",
              game_id: str = "0042500407", game_date: str = "2026-05-29",
              roster: List[int] | None = None,
              simulation: Dict[str, Any] | None = None) -> AsOfContext:
    return AsOfContext(
        decision_time=datetime.datetime(2026, 5, 29, 10, 0, 0),
        team=team,
        opp=opp,
        game_id=game_id,
        game_date=game_date,
        season="2025-26",
        is_home=True,
        scope="pregame",
        extra={
            "roster": roster or [1628983, 1629029],
            **({"simulation": simulation} if simulation is not None else {}),
        },
    )


# ---------------------------------------------------------------------------
# 1. pregame_report
# ---------------------------------------------------------------------------

class TestPregameReport:
    def test_returns_path(self, populated_store, tmp_reports_dir):
        ctx = _make_ctx()
        path = rg.pregame_report(ctx, store=populated_store, dry_run=False)
        assert isinstance(path, Path)

    def test_file_written(self, populated_store, tmp_reports_dir):
        ctx = _make_ctx()
        path = rg.pregame_report(ctx, store=populated_store, dry_run=False)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_header_content(self, populated_store, tmp_reports_dir):
        ctx = _make_ctx()
        path = rg.pregame_report(ctx, store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "BOS" in text
        assert "DAL" in text
        assert "Pregame Intelligence Report" in text

    def test_dry_run_no_file(self, populated_store, tmp_reports_dir):
        ctx = _make_ctx()
        path = rg.pregame_report(ctx, store=populated_store, dry_run=True)
        assert isinstance(path, Path)
        assert not path.exists()

    def test_team_atlas_sections_rendered(self, populated_store, tmp_reports_dir):
        ctx = _make_ctx()
        path = rg.pregame_report(ctx, store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "defense_scheme" in text or "ratings" in text

    def test_player_atlas_rendered(self, populated_store, tmp_reports_dir):
        ctx = _make_ctx(roster=[1628983])
        path = rg.pregame_report(ctx, store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "1628983" in text

    def test_lines_table_rendered(self, populated_store, tmp_reports_dir):
        ctx = _make_ctx()
        lines = [{"stat": "pts", "line": 28.5, "projection": 30.1,
                  "ev": 0.07, "kelly": 0.04}]
        path = rg.pregame_report(ctx, store=populated_store, lines=lines)
        text = path.read_text(encoding="utf-8")
        assert "pts" in text
        assert "28.5" in text

    def test_simulation_rendered(self, populated_store, tmp_reports_dir):
        sim = {
            "player_marginals": {
                "1628983": {"pts": {"p25": 22.0, "p50": 28.5, "p75": 35.0}},
            },
            "team_totals": {"BOS": 112.0},
            "final_score": {"home": 112, "away": 106},
        }
        ctx = _make_ctx(simulation=sim)
        path = rg.pregame_report(ctx, store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "28.5" in text  # p50
        assert "Joint-Sim" in text

    def test_no_roster_graceful(self, populated_store, tmp_reports_dir):
        ctx = _make_ctx(roster=[])
        path = rg.pregame_report(ctx, store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "Pregame" in text  # still renders


# ---------------------------------------------------------------------------
# 2. postgame_report
# ---------------------------------------------------------------------------

class TestPostgameReport:
    def test_returns_path(self, tmp_store, tmp_reports_dir):
        path = rg.postgame_report("0042500407", "2026-05-29", store=tmp_store)
        assert isinstance(path, Path)

    def test_file_written(self, tmp_store, tmp_reports_dir):
        path = rg.postgame_report("0042500407", "2026-05-29", store=tmp_store)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_header_content(self, tmp_store, tmp_reports_dir):
        path = rg.postgame_report("0042500407", "2026-05-29", store=tmp_store)
        text = path.read_text(encoding="utf-8")
        assert "Postgame" in text
        assert "0042500407" in text

    def test_dry_run_no_file(self, tmp_store, tmp_reports_dir):
        path = rg.postgame_report("0042500407", "2026-05-29", store=tmp_store,
                                  dry_run=True)
        assert not path.exists()

    def test_with_store_data(self, tmp_store, tmp_reports_dir):
        # Write synthetic pred/actual into the store
        tmp_store.write("game:0042500407", "prediction_summary", "2026-05-29",
                        {"player:1628983": {"pts": 28.5}})
        tmp_store.write("game:0042500407", "actual_summary", "2026-05-29",
                        {"player:1628983": {"pts": 31.0}})
        path = rg.postgame_report("0042500407", "2026-05-29", store=tmp_store)
        text = path.read_text(encoding="utf-8")
        assert "28.5" in text or "31" in text

    def test_clv_section_present(self, tmp_store, tmp_reports_dir):
        tmp_store.write("game:0042500407", "clv_summary", "2026-05-29", {
            "pts": {"direction": "over", "clv_pp": 3.5, "result": "win"},
        })
        path = rg.postgame_report("0042500407", "2026-05-29", store=tmp_store)
        text = path.read_text(encoding="utf-8")
        assert "CLV" in text or "clv" in text.lower()

    def test_residuals_section_present(self, tmp_store, tmp_reports_dir):
        tmp_store.write("game:0042500407", "residuals", "2026-05-29", {
            "player:1628983": {
                "pts": {"pred": 28.5, "actual": 31.0, "resid": -2.5},
            },
        })
        path = rg.postgame_report("0042500407", "2026-05-29", store=tmp_store)
        text = path.read_text(encoding="utf-8")
        assert "Residuals" in text

    def test_missing_data_graceful(self, tmp_store, tmp_reports_dir):
        # Store empty — should render placeholder text rather than crash
        path = rg.postgame_report("XXXX", "2026-01-01", store=tmp_store)
        text = path.read_text(encoding="utf-8")
        assert "Postgame" in text


# ---------------------------------------------------------------------------
# 3. league_trend_report
# ---------------------------------------------------------------------------

class TestLeagueTrendReport:
    def test_returns_path(self, tmp_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=tmp_store)
        assert isinstance(path, Path)

    def test_file_written(self, tmp_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=tmp_store)
        assert path.exists()

    def test_header_content(self, tmp_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=tmp_store)
        text = path.read_text(encoding="utf-8")
        assert "League-Trend" in text

    def test_dry_run_no_file(self, tmp_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=tmp_store, dry_run=True)
        assert not path.exists()

    def test_teams_rendered(self, populated_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "BOS" in text
        assert "DAL" in text

    def test_scheme_section(self, populated_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "Defensive-Scheme" in text

    def test_rebounding_section(self, populated_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "Rebounding" in text

    def test_coverage_gap_section(self, populated_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=populated_store)
        text = path.read_text(encoding="utf-8")
        assert "Coverage" in text  # Coverage Gaps section

    def test_empty_store_graceful(self, tmp_store, tmp_reports_dir):
        path = rg.league_trend_report("2026-05-29", store=tmp_store)
        text = path.read_text(encoding="utf-8")
        # Should note missing data without crashing
        assert "League-Trend" in text


# ---------------------------------------------------------------------------
# 4. model_error_report
# ---------------------------------------------------------------------------

class TestModelErrorReport:
    def _make_buckets(self) -> List[ResidualBucket]:
        return [
            ResidualBucket(stat="pts",
                           dims={"game_state": "blowout", "quarter": 4},
                           n=120, mean_resid=2.3, std_resid=4.1, p_value=0.003),
            ResidualBucket(stat="pts",
                           dims={"game_state": "clutch"},
                           n=80, mean_resid=-0.5, std_resid=3.8, p_value=0.42),
            ResidualBucket(stat="reb",
                           dims={"is_home": False},
                           n=200, mean_resid=-1.1, std_resid=2.9, p_value=0.01),
            ResidualBucket(stat="ast",
                           dims={"rest": "b2b"},
                           n=55, mean_resid=0.8, std_resid=1.5, p_value=0.09),
        ]

    def test_returns_path(self, tmp_reports_dir):
        path = rg.model_error_report([])
        assert isinstance(path, Path)

    def test_file_written(self, tmp_reports_dir):
        buckets = self._make_buckets()
        path = rg.model_error_report(buckets)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_header_content(self, tmp_reports_dir):
        buckets = self._make_buckets()
        path = rg.model_error_report(buckets)
        text = path.read_text(encoding="utf-8")
        assert "Model-Error" in text

    def test_dry_run_no_file(self, tmp_reports_dir):
        buckets = self._make_buckets()
        path = rg.model_error_report(buckets, dry_run=True)
        assert not path.exists()

    def test_bias_table_rendered(self, tmp_reports_dir):
        buckets = self._make_buckets()
        path = rg.model_error_report(buckets)
        text = path.read_text(encoding="utf-8")
        assert "OVER" in text or "UNDER" in text

    def test_sorted_by_abs_mean_resid(self, tmp_reports_dir):
        buckets = self._make_buckets()
        path = rg.model_error_report(buckets)
        text = path.read_text(encoding="utf-8")
        # blowout bucket (mean=2.3) should appear before b2b bucket (mean=0.8)
        idx_blowout = text.find("blowout")
        idx_b2b = text.find("b2b")
        assert idx_blowout < idx_b2b

    def test_per_stat_section(self, tmp_reports_dir):
        buckets = self._make_buckets()
        path = rg.model_error_report(buckets)
        text = path.read_text(encoding="utf-8")
        assert "Per-Stat Analysis" in text
        assert "Points" in text  # label for pts
        assert "Rebounds" in text

    def test_empty_buckets_graceful(self, tmp_reports_dir):
        path = rg.model_error_report([])
        text = path.read_text(encoding="utf-8")
        assert "Model-Error" in text

    def test_hypotheses_rendered(self, tmp_reports_dir):
        buckets = self._make_buckets()
        hyps = [
            Hypothesis(
                name="blowout_pts_correction",
                target="pts",
                scope="pregame",
                statement="Model over-predicts pts in blowouts",
                rationale="blowout bucket mean_resid=+2.3, n=120, p=0.003",
                source="error_miner",
                atlas_fields=["scoring_usage"],
                priority="P1",
            ),
        ]
        path = rg.model_error_report(buckets, hypotheses=hyps)
        text = path.read_text(encoding="utf-8")
        assert "blowout_pts_correction" in text
        assert "Hypotheses" in text

    def test_hypothesis_rationale_rendered(self, tmp_reports_dir):
        buckets = self._make_buckets()
        hyps = [
            Hypothesis(
                name="rest_ast_correction",
                target="ast",
                scope="pregame",
                statement="Under-predicts ast on b2b",
                rationale="b2b rest bucket residual +0.8",
                source="error_miner",
                atlas_fields=["scoring_usage", "playtypes"],
                priority="P2",
            ),
        ]
        path = rg.model_error_report(buckets, hypotheses=hyps)
        text = path.read_text(encoding="utf-8")
        assert "b2b rest bucket" in text


# ---------------------------------------------------------------------------
# 5. Integration: all four reports can co-exist in one reports dir
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_all_four_report_types(self, populated_store, tmp_reports_dir):
        buckets = [
            ResidualBucket(stat="pts", dims={"game_state": "normal"},
                           n=500, mean_resid=0.1, std_resid=4.0, p_value=0.8),
        ]
        ctx = _make_ctx()

        p1 = rg.pregame_report(ctx, store=populated_store)
        p2 = rg.postgame_report("0042500407", "2026-05-29", store=populated_store)
        p3 = rg.league_trend_report("2026-05-29", store=populated_store)
        p4 = rg.model_error_report(buckets)

        for p in [p1, p2, p3, p4]:
            assert p.exists(), f"Report not found: {p}"
            assert p.stat().st_size > 100, f"Report too small: {p}"

    def test_reports_dir_created_automatically(self, tmp_store, monkeypatch,
                                               tmp_path):
        # Point at a non-existing subdir and verify it gets created
        new_dir = tmp_path / "deep" / "reports"
        monkeypatch.setattr(rg, "REPORTS_DIR", new_dir)
        path = rg.league_trend_report("2026-05-29", store=tmp_store)
        assert new_dir.exists()
        assert path.exists()
