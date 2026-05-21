"""
tests/test_pod_manager.py - Unit tests for scripts/pod_manager.py.

All external network calls (RunPod API, SSH, rsync) are mocked/stubbed.
No real cloud instances are launched.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict
from unittest import mock

import pytest

# Make sure the scripts directory is importable
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR.parent))

import importlib
import types

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

pod_manager = pytest.importorskip(
    "scripts.pod_manager",
    reason="scripts/pod_manager.py not present",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_cfg() -> Dict[str, str]:
    """Minimal config dict with placeholder credentials."""
    return {
        "RUNPOD_API_KEY": "test-api-key-123",
        "RUNPOD_IP": "1.2.3.4",
        "RUNPOD_PORT": "22222",
        "RUNPOD_POD_ID": "pod-abc123",
    }


@pytest.fixture()
def fake_pod_response() -> Dict[str, Any]:
    """Simulated RunPod podFindAndDeployOnDemand response."""
    return {
        "id": "pod-fake-001",
        "imageName": "runpod/pytorch:latest",
        "desiredStatus": "RUNNING",
        "runtime": {
            "ports": [
                {"ip": "5.6.7.8", "privatePort": 22, "publicPort": 10022, "type": "tcp"}
            ]
        },
    }


@pytest.fixture()
def fake_status_response() -> Dict[str, Any]:
    """Simulated RunPod pod status query response."""
    return {
        "id": "pod-fake-001",
        "desiredStatus": "RUNNING",
        "lastStatusChange": "2026-05-21T00:00:00Z",
        "runtime": {
            "ports": [
                {"ip": "5.6.7.8", "privatePort": 22, "publicPort": 10022, "type": "tcp"}
            ]
        },
    }


# ---------------------------------------------------------------------------
# _load_dotrunpod
# ---------------------------------------------------------------------------


def test_load_dotrunpod_missing(tmp_path: Path) -> None:
    """Returns empty dict when .runpod does not exist."""
    result = pod_manager._load_dotrunpod(root=tmp_path)
    assert result == {}


def test_load_dotrunpod_parses_kv(tmp_path: Path) -> None:
    """Parses KEY=VALUE pairs, ignores comments and blank lines."""
    (tmp_path / ".runpod").write_text(
        "# comment\n\nRUNPOD_IP=1.2.3.4\nRUNPOD_PORT=22222\n",
        encoding="utf-8",
    )
    result = pod_manager._load_dotrunpod(root=tmp_path)
    assert result["RUNPOD_IP"] == "1.2.3.4"
    assert result["RUNPOD_PORT"] == "22222"
    assert "# comment" not in result


def test_load_dotrunpod_strips_quotes(tmp_path: Path) -> None:
    """Strips surrounding quotes from values."""
    (tmp_path / ".runpod").write_text(
        'RUNPOD_API_KEY="my-secret"\nRUNPOD_IP=\'10.0.0.1\'\n',
        encoding="utf-8",
    )
    result = pod_manager._load_dotrunpod(root=tmp_path)
    assert result["RUNPOD_API_KEY"] == "my-secret"
    assert result["RUNPOD_IP"] == "10.0.0.1"


# ---------------------------------------------------------------------------
# _get_config
# ---------------------------------------------------------------------------


def test_get_config_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables take precedence over .runpod file values."""
    (tmp_path / ".runpod").write_text("RUNPOD_IP=9.9.9.9\n", encoding="utf-8")
    monkeypatch.setenv("RUNPOD_IP", "1.1.1.1")

    # Monkeypatch _load_dotrunpod to use our tmp_path
    with mock.patch.object(pod_manager, "_load_dotrunpod", return_value={"RUNPOD_IP": "9.9.9.9"}):
        monkeypatch.setenv("RUNPOD_IP", "1.1.1.1")
        cfg = pod_manager._get_config()
    assert cfg["RUNPOD_IP"] == "1.1.1.1"


# ---------------------------------------------------------------------------
# _require_credentials
# ---------------------------------------------------------------------------


def test_require_credentials_passes(minimal_cfg: Dict[str, str]) -> None:
    """No exit when all required keys are present."""
    pod_manager._require_credentials(minimal_cfg, "RUNPOD_API_KEY", "RUNPOD_IP")


def test_require_credentials_exits_on_missing() -> None:
    """sys.exit(1) when a required credential is missing."""
    cfg: Dict[str, str] = {}
    with pytest.raises(SystemExit) as exc_info:
        pod_manager._require_credentials(cfg, "RUNPOD_API_KEY")
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# launch_pod (mocked API)
# ---------------------------------------------------------------------------


def test_launch_pod_calls_gql(fake_pod_response: Dict[str, Any]) -> None:
    """launch_pod sends a GraphQL mutation and returns pod info."""
    api_response = {"data": {"podFindAndDeployOnDemand": fake_pod_response}}

    with mock.patch.object(pod_manager, "_gql_request", return_value=api_response) as mock_gql:
        result = pod_manager.launch_pod(api_key="fake-key", gpu_type="RTX 3090", workers=6)

    mock_gql.assert_called_once()
    assert result["id"] == "pod-fake-001"
    assert result["desiredStatus"] == "RUNNING"


def test_launch_pod_sets_worker_env(fake_pod_response: Dict[str, Any]) -> None:
    """launch_pod includes PARALLEL_WORKERS env var in the API payload."""
    api_response = {"data": {"podFindAndDeployOnDemand": fake_pod_response}}
    captured: list = []

    def capture_gql(api_key: str, query: str, variables: Any = None) -> Dict[str, Any]:
        captured.append(variables)
        return api_response

    with mock.patch.object(pod_manager, "_gql_request", side_effect=capture_gql):
        pod_manager.launch_pod(api_key="fake-key", workers=4)

    env_vars = captured[0]["input"]["env"]
    worker_entry = next((e for e in env_vars if e["key"] == "PARALLEL_WORKERS"), None)
    assert worker_entry is not None
    assert worker_entry["value"] == "4"


# ---------------------------------------------------------------------------
# get_pod_status (mocked API)
# ---------------------------------------------------------------------------


def test_get_pod_status_returns_info(fake_status_response: Dict[str, Any]) -> None:
    """get_pod_status returns desiredStatus from API response."""
    api_response = {"data": {"pod": fake_status_response}}

    with mock.patch.object(pod_manager, "_gql_request", return_value=api_response):
        result = pod_manager.get_pod_status("fake-key", "pod-fake-001")

    assert result["desiredStatus"] == "RUNNING"


# ---------------------------------------------------------------------------
# terminate_pod (mocked API)
# ---------------------------------------------------------------------------


def test_terminate_pod_returns_true() -> None:
    """terminate_pod returns True on success."""
    api_response = {"data": {"podTerminate": None}}

    with mock.patch.object(pod_manager, "_gql_request", return_value=api_response):
        result = pod_manager.terminate_pod("fake-key", "pod-fake-001")

    assert result is True


# ---------------------------------------------------------------------------
# cmd_sync
# ---------------------------------------------------------------------------


def test_cmd_sync_dry_run_exits_zero(minimal_cfg: Dict[str, str]) -> None:
    """cmd_sync --dry-run returns 0 without calling rsync."""
    args = argparse.Namespace(dry_run=True)
    with mock.patch.object(pod_manager, "_rsync_pull") as mock_rsync:
        rc = pod_manager.cmd_sync(args, minimal_cfg)
    assert rc == 0
    mock_rsync.assert_not_called()


def test_cmd_sync_no_ip_exits_nonzero() -> None:
    """cmd_sync exits non-zero when RUNPOD_IP is absent (and not dry-run)."""
    args = argparse.Namespace(dry_run=False)
    cfg: Dict[str, str] = {}
    rc = pod_manager.cmd_sync(args, cfg)
    assert rc != 0


def test_cmd_sync_calls_rsync(minimal_cfg: Dict[str, str]) -> None:
    """cmd_sync calls _rsync_pull with correct IP/port when RUNPOD_IP is set."""
    args = argparse.Namespace(dry_run=False)
    with mock.patch.object(pod_manager, "_rsync_pull", return_value=0) as mock_rsync:
        rc = pod_manager.cmd_sync(args, minimal_cfg)
    assert rc == 0
    mock_rsync.assert_called_once_with("1.2.3.4", "22222", dry_run=False)


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------


def test_cmd_status_no_ip_exits_nonzero() -> None:
    """cmd_status exits non-zero when neither RUNPOD_IP nor RUNPOD_POD_ID is set."""
    args = argparse.Namespace()
    cfg: Dict[str, str] = {}
    rc = pod_manager.cmd_status(args, cfg)
    assert rc != 0


def test_cmd_status_with_ip_calls_ssh(minimal_cfg: Dict[str, str]) -> None:
    """cmd_status attempts an SSH connectivity check when RUNPOD_IP is set."""
    args = argparse.Namespace()
    with mock.patch.object(pod_manager, "_ssh_cmd", return_value=0) as mock_ssh:
        rc = pod_manager.cmd_status(args, minimal_cfg)
    assert rc == 0
    mock_ssh.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_teardown
# ---------------------------------------------------------------------------


def test_cmd_teardown_force_terminates(minimal_cfg: Dict[str, str]) -> None:
    """cmd_teardown --force calls terminate_pod without prompting."""
    args = argparse.Namespace(force=True)
    with mock.patch.object(pod_manager, "terminate_pod", return_value=True) as mock_term:
        rc = pod_manager.cmd_teardown(args, minimal_cfg)
    assert rc == 0
    mock_term.assert_called_once_with("test-api-key-123", "pod-abc123")


def test_cmd_teardown_missing_creds_exits() -> None:
    """cmd_teardown exits non-zero when API key is missing."""
    args = argparse.Namespace(force=True)
    cfg: Dict[str, str] = {"RUNPOD_POD_ID": "pod-abc"}
    with pytest.raises(SystemExit) as exc_info:
        pod_manager.cmd_teardown(args, cfg)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# cmd_launch
# ---------------------------------------------------------------------------


def test_cmd_launch_missing_api_key_exits() -> None:
    """cmd_launch exits when RUNPOD_API_KEY is absent."""
    args = argparse.Namespace(gpu=pod_manager.DEFAULT_GPU, workers=6)
    cfg: Dict[str, str] = {}
    with pytest.raises(SystemExit) as exc_info:
        pod_manager.cmd_launch(args, cfg)
    assert exc_info.value.code == 1


def test_cmd_launch_api_error_returns_one(minimal_cfg: Dict[str, str]) -> None:
    """cmd_launch returns 1 when the RunPod API raises RuntimeError."""
    args = argparse.Namespace(gpu=pod_manager.DEFAULT_GPU, workers=6)
    with mock.patch.object(pod_manager, "launch_pod", side_effect=RuntimeError("timeout")):
        rc = pod_manager.cmd_launch(args, minimal_cfg)
    assert rc == 1


def test_cmd_launch_success(
    minimal_cfg: Dict[str, str],
    fake_pod_response: Dict[str, Any],
    fake_status_response: Dict[str, Any],
) -> None:
    """cmd_launch returns 0 when pod reaches RUNNING state."""
    args = argparse.Namespace(gpu=pod_manager.DEFAULT_GPU, workers=6)
    with mock.patch.object(pod_manager, "launch_pod", return_value=fake_pod_response), \
         mock.patch.object(pod_manager, "get_pod_status", return_value=fake_status_response), \
         mock.patch("time.sleep"):
        rc = pod_manager.cmd_launch(args, minimal_cfg)
    assert rc == 0


# ---------------------------------------------------------------------------
# build_parser / --help
# ---------------------------------------------------------------------------


def test_build_parser_has_all_subcommands() -> None:
    """build_parser exposes launch, status, sync, teardown subcommands."""
    parser = pod_manager.build_parser()
    # argparse stores choices in subparsers actions (choices may be None on some actions)
    subparsers_action = next(
        (a for a in parser._actions if hasattr(a, "choices") and isinstance(a.choices, dict)),
        None,
    )
    assert subparsers_action is not None, "No subparsers action found in parser"
    choices = set(subparsers_action.choices.keys())
    for cmd in ("launch", "status", "sync", "teardown"):
        assert cmd in choices, "Missing subcommand: {}".format(cmd)


def test_main_no_subcommand_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() with no subcommand prints help and returns 0."""
    monkeypatch.setattr(sys, "argv", ["pod_manager"])
    rc = pod_manager.main()
    assert rc == 0
