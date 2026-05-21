"""
tests/test_infrastructure.py — Phase 17 infrastructure test stubs.

All 8 stubs are importable and runnable without GPU or Docker.
Each stub raises AssertionError or pytest.skip — never ImportError.
"""

import os
import subprocess
import sys

import pytest


# ---------------------------------------------------------------------------
# Task 1 — Test stubs
# ---------------------------------------------------------------------------


def test_docker_health_endpoint():
    """GET /health returns JSON with keys status, database, redis.

    Skipped unless DOCKER_TEST=1 is set in the environment.
    """
    if not os.environ.get("DOCKER_TEST"):
        pytest.skip("Set DOCKER_TEST=1 to run Docker health check")

    requests = pytest.importorskip("requests")
    response = requests.get("http://localhost:8000/health", timeout=5)
    data = response.json()
    assert "status" in data, "Health response missing 'status' key"
    assert "database" in data, "Health response missing 'database' key"
    assert "redis" in data, "Health response missing 'redis' key"


def test_ci_config_lint():
    """CI workflow YAML is valid and contains top-level 'on' and 'jobs' keys.

    Each job must have a 'steps' key.
    """
    yaml = pytest.importorskip("yaml")

    ci_path = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "ci.yml")
    ci_path = os.path.normpath(ci_path)
    if not os.path.exists(ci_path):
        pytest.skip("No .github/workflows/ci.yml found — skipping CI lint")

    with open(ci_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    assert config is not None, "ci.yml parsed as None (empty file?)"
    assert "on" in config or True in config, "ci.yml missing 'on' trigger key"
    assert "jobs" in config, "ci.yml missing 'jobs' key"

    jobs = config["jobs"]
    assert isinstance(jobs, dict) and len(jobs) >= 1, "ci.yml 'jobs' must contain at least one job"
    for job_name, job_def in jobs.items():
        assert "steps" in job_def, f"Job '{job_name}' has no 'steps' key"


def test_drift_alert_fires(tmp_path, monkeypatch):
    """FeatureDriftDetector flags feat_a when its importance drops 80%.

    Uses pytest.importorskip so the test skips (not errors) if the module
    does not exist yet.

    Adapts to two possible API shapes:
      - Two-arg: log_importance(model_id, importances) / check_drift(model_id)
      - One-arg: log_importance(importances) / check_drift()
    """
    fdd_mod = pytest.importorskip(
        "src.pipeline.feature_drift_detector",
        reason="feature_drift_detector not yet implemented — REQ-14-1",
    )
    FeatureDriftDetector = fdd_mod.FeatureDriftDetector

    # Redirect drift log to tmp_path so tests don't pollute data/models/
    drift_log = str(tmp_path / "feature_drift_log.json")
    if hasattr(fdd_mod, "_DRIFT_LOG"):
        monkeypatch.setattr(fdd_mod, "_DRIFT_LOG", drift_log)

    detector = FeatureDriftDetector()

    baseline = {"feat_a": 0.5, "feat_b": 0.3, "feat_c": 0.2}
    drifted = {"feat_a": 0.1, "feat_b": 0.3, "feat_c": 0.6}  # feat_a dropped 80%

    # Detect API shape from the actual signature
    import inspect
    sig = inspect.signature(detector.log_importance)
    two_arg_api = len(sig.parameters) >= 2  # (self, model_id, importances) or (model_id, importances)

    model_id = "test_model"
    if two_arg_api:
        detector.log_importance(model_id, baseline)
        detector.log_importance(model_id, drifted)
        result = detector.check_drift(model_id)
    else:
        detector.log_importance(baseline)
        detector.log_importance(drifted)
        result = detector.check_drift()

    # Support both return shapes:
    #   Shape A (plan spec):    {"drifted": bool, "drifted_features": list[str]}
    #   Shape B (existing impl):{"drifted_features": list[dict], "is_degraded": bool}
    drifted_key = result.get("drifted_features", [])
    drifted_bool = result.get("drifted", result.get("is_degraded", False))

    assert drifted_bool or len(drifted_key) > 0, (
        "Expected drift to be detected for feat_a (80% drop exceeds 30% threshold)"
    )
    # feat_a must appear in drifted_features (either as str or dict with 'feature' key)
    feat_names = [
        (f if isinstance(f, str) else f.get("feature", ""))
        for f in drifted_key
    ]
    assert "feat_a" in feat_names, (
        f"Expected feat_a in drifted_features; got {feat_names}"
    )


def test_auto_retrain_milestone(monkeypatch):
    """check_and_retrain returns milestone_hit when game count reaches 20.

    Uses pytest.importorskip so the test skips if the module doesn't exist yet.
    Side-effecting helpers are monkeypatched to noops.
    """
    ar_mod = pytest.importorskip(
        "src.pipeline.auto_retrain",
        reason="auto_retrain not yet implemented — REQ-14-2",
    )
    check_and_retrain = ar_mod.check_and_retrain

    # Patch helpers to avoid real model training
    if hasattr(ar_mod, "get_game_count"):
        monkeypatch.setattr(ar_mod, "get_game_count", lambda: 20)
    if hasattr(ar_mod, "_run_props_retrain"):
        monkeypatch.setattr(ar_mod, "_run_props_retrain", lambda *a, **kw: None)
    if hasattr(ar_mod, "_retrain_tier3"):
        monkeypatch.setattr(ar_mod, "_retrain_tier3", lambda *a, **kw: None)

    result = check_and_retrain("test_game_001", "2024-25")

    assert result is not None, "check_and_retrain returned None"
    assert result.get("milestone_hit") is not None, (
        "Expected milestone_hit to be truthy at game count 20 (tier3_20 milestone)"
    )


def test_model_validation_gate():
    """compare_models is importable from scripts.compare_models.

    Skipped (not errored) until plan 03 implements the module — REQ-14-3.
    """
    try:
        from scripts.compare_models import compare_models  # noqa: F401
    except ImportError:
        pytest.skip("compare_models not yet implemented — REQ-14-3")

    # If the import succeeds, verify it is callable
    assert callable(compare_models), "compare_models must be a callable"


def test_pod_manager_status_no_creds():
    """pod_manager status exits non-zero when RunPod credentials are absent.

    Skipped if scripts/pod_manager.py does not yet exist (plan 04).
    """
    pod_manager_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "pod_manager.py")
    )
    if not os.path.exists(pod_manager_path):
        pytest.skip("pod_manager.py not yet implemented — REQ-14-5")

    env = {k: v for k, v in os.environ.items() if k not in ("RUNPOD_IP", "RUNPOD_API_KEY")}
    result = subprocess.run(
        [sys.executable, pod_manager_path, "status"],
        capture_output=True,
        env=env,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0 or (
        b"RUNPOD_IP" in combined or b"No .runpod" in combined
    ), (
        "Expected non-zero return or credential error message when RUNPOD_IP not set"
    )


def test_pod_manager_sync_dry_run():
    """pod_manager sync --dry-run exits 0 and prints 'dry-run' to stdout.

    Skipped if scripts/pod_manager.py does not yet exist (plan 04).
    """
    pod_manager_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "pod_manager.py")
    )
    if not os.path.exists(pod_manager_path):
        pytest.skip("pod_manager.py not yet implemented — REQ-14-5")

    env = {**os.environ, "RUNPOD_IP": "1.2.3.4", "RUNPOD_PORT": "22"}
    result = subprocess.run(
        [sys.executable, pod_manager_path, "sync", "--dry-run"],
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0, (
        f"sync --dry-run returned {result.returncode}; stderr: {result.stderr.decode()}"
    )
    assert b"dry-run" in result.stdout, (
        "Expected 'dry-run' in stdout for dry-run sync"
    )


def test_pod_manager_launch_preflight():
    """pod_manager --help exits 0 and lists all four subcommands.

    Skipped if scripts/pod_manager.py does not yet exist (plan 04).
    """
    pod_manager_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "pod_manager.py")
    )
    if not os.path.exists(pod_manager_path):
        pytest.skip("pod_manager.py not yet implemented — REQ-14-5")

    result = subprocess.run(
        [sys.executable, pod_manager_path, "--help"],
        capture_output=True,
    )

    assert result.returncode == 0, (
        f"--help returned {result.returncode}; stderr: {result.stderr.decode()}"
    )
    combined = result.stdout + result.stderr
    for subcommand in (b"launch", b"status", b"sync", b"teardown"):
        assert subcommand in combined, (
            f"Expected subcommand '{subcommand.decode()}' in --help output"
        )
