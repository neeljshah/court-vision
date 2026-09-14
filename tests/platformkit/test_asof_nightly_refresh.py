"""Tests for scripts/platformkit/asof_nightly_refresh.py -- all network/subprocess
calls are mocked; nothing here touches the real NBA API or real data/ tables."""
from __future__ import annotations

import subprocess
import sys
import types
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.platformkit import asof_nightly_refresh as m


def _fake_completed(returncode=0, stdout="ok\n", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# --------------------------------------------------------------------------
# season string derivation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("d,expected", [
    (date(2026, 10, 5), "2026-27"),   # Oct -> season starting this Oct
    (date(2027, 3, 1), "2026-27"),    # Mar -> mid in-season, started previous Oct
    (date(2026, 8, 15), "2025-26"),   # Aug (Jul-Sep) -> just-finished season
])
def test_current_season_three_dates(d, expected):
    assert m.current_season(d) == expected


# --------------------------------------------------------------------------
# env injection
# --------------------------------------------------------------------------

def test_env_injects_bundle_when_present(tmp_path, monkeypatch):
    bundle = tmp_path / "winroots.pem"
    bundle.write_text("cert", encoding="utf-8")
    monkeypatch.setattr(m, "WINROOTS", bundle)
    env = m._build_env(needs_bundle=True)
    assert env["REQUESTS_CA_BUNDLE"] == str(bundle)
    assert env["SSL_CERT_FILE"] == str(bundle)


def test_env_skips_bundle_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "WINROOTS", tmp_path / "missing.pem")
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    env = m._build_env(needs_bundle=True)
    assert "REQUESTS_CA_BUNDLE" not in env
    assert "SSL_CERT_FILE" not in env


def test_env_skips_bundle_when_not_needed(tmp_path, monkeypatch):
    bundle = tmp_path / "winroots.pem"
    bundle.write_text("cert", encoding="utf-8")
    monkeypatch.setattr(m, "WINROOTS", bundle)
    env = m._build_env(needs_bundle=False)
    assert "REQUESTS_CA_BUNDLE" not in env


# --------------------------------------------------------------------------
# backup rotation
# --------------------------------------------------------------------------

def test_backup_rotation_keeps_last_three(tmp_path):
    target = tmp_path / "asof_features.parquet"
    target.write_text("v0", encoding="utf-8")
    for day in ("2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13", "2026-09-14"):
        m._rotate_backup(target, day)
    backups = sorted(p.name for p in tmp_path.glob(target.name + ".bak_*"))
    assert backups == [
        "asof_features.parquet.bak_2026-09-12",
        "asof_features.parquet.bak_2026-09-13",
        "asof_features.parquet.bak_2026-09-14",
    ]


def test_backup_rotation_noop_when_missing(tmp_path):
    target = tmp_path / "missing.parquet"
    m._rotate_backup(target, "2026-09-14")
    assert list(tmp_path.glob("*.bak_*")) == []


# --------------------------------------------------------------------------
# quarter-box row-count guard
# --------------------------------------------------------------------------

def test_quarter_box_guard_refuses_regression(tmp_path, monkeypatch):
    real_out = tmp_path / "nba_quarter_points.parquet"
    staging = tmp_path / "nba_quarter_points.staging.parquet"
    real_out.write_text("old", encoding="utf-8")

    def fake_run(argv, **kwargs):
        staging.write_text("new", encoding="utf-8")  # simulate the builder writing staging
        return _fake_completed(returncode=0)

    counts = {str(real_out): 100, str(staging): 40}  # regression: new < old
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(m, "_parquet_game_count", lambda p: counts[str(p)])

    result = m._run_quarter_box_step(real_out=real_out, staging=staging)

    assert result["returncode"] == 0
    assert "guard refused" in result["note"]
    assert real_out.read_text(encoding="utf-8") == "old"  # untouched
    assert not staging.exists()  # rejected staging file removed


def test_quarter_box_guard_promotes_on_growth(tmp_path, monkeypatch):
    real_out = tmp_path / "nba_quarter_points.parquet"
    staging = tmp_path / "nba_quarter_points.staging.parquet"
    real_out.write_text("old", encoding="utf-8")

    def fake_run(argv, **kwargs):
        staging.write_text("new", encoding="utf-8")
        return _fake_completed(returncode=0)

    counts = {str(real_out): 100, str(staging): 150}  # growth: promote
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(m, "_parquet_game_count", lambda p: counts[str(p)])

    result = m._run_quarter_box_step(real_out=real_out, staging=staging)

    assert result["returncode"] == 0
    assert "promoted" in result["note"]
    assert real_out.read_text(encoding="utf-8") == "new"
    assert not staging.exists()
    assert (tmp_path / (real_out.name + f".bak_{m._today_str()}")).exists()


# --------------------------------------------------------------------------
# step ordering / --steps filtering
# --------------------------------------------------------------------------

def test_step_ordering_default():
    plan = m.build_step_list("2025-26", include_quarter_box=False)
    assert plan[0] == "fetch_advanced_boxscores"
    assert "quarter_box" not in plan
    assert plan[-4:] == [f"coverage_check_{t}" for t in m.COVERAGE_TABLES]
    assert plan.index("asof_features") < plan.index("asof_runvar") < plan.index("corpus_b_build")
    assert plan.index("coverage_receipt_build") < plan.index("coverage_check_asof_features")


def test_step_ordering_with_quarter_box():
    plan = m.build_step_list("2025-26", include_quarter_box=True)
    assert plan[0] == "quarter_box"


def test_steps_flag_filters_and_preserves_order():
    plan = m.build_step_list("2025-26", include_quarter_box=False)
    wanted = {"asof_team_adv", "asof_features"}
    filtered = [s for s in plan if s in wanted]
    assert filtered == ["asof_features", "asof_team_adv"]


# --------------------------------------------------------------------------
# full main(): dry-run, exit code on a failed coverage check
# --------------------------------------------------------------------------

def test_dry_run_executes_nothing(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("subprocess.run must not be called in --dry-run")
    monkeypatch.setattr(subprocess, "run", boom)
    rc = m.main(["--dry-run", "--season", "2025-26"])
    assert rc == 0


def test_main_exits_3_when_a_coverage_check_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "_call_asof_runvar", lambda: None)
    monkeypatch.setattr(m, "_rotate_backup", lambda *a, **k: None)  # no real data/ writes

    def fake_run(argv, **kwargs):
        if "--check" in argv and "asof_team_adv" in argv:
            return _fake_completed(returncode=3, stdout="", stderr="coverage below 0.95")
        return _fake_completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    rc = m.main(["--season", "2025-26"])
    assert rc == 3
    assert (tmp_path / f"{m._today_str()}.log").exists()
    assert (tmp_path / f"{m._today_str()}.json").exists()


def test_main_exits_0_when_all_checks_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "_call_asof_runvar", lambda: None)
    monkeypatch.setattr(m, "_rotate_backup", lambda *a, **k: None)
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: _fake_completed(returncode=0))
    rc = m.main(["--season", "2025-26"])
    assert rc == 0


def test_main_uses_python_call_for_asof_runvar(tmp_path, monkeypatch):
    """asof_runvar must be invoked via build_asof_runvar(force=True), never a CLI flag."""
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "_rotate_backup", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(m, "_call_asof_runvar", lambda: calls.append("called"))
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: _fake_completed(returncode=0))
    m.main(["--season", "2025-26", "--steps", "asof_runvar"])
    assert calls == ["called"]
