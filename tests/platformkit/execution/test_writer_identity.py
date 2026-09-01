"""Per-file test for scripts.platformkit.execution.writer_identity.

Run: python -m pytest tests/platformkit/execution/test_writer_identity.py -q
"""
from __future__ import annotations

from scripts.platformkit.execution import writer_identity as wi


def test_posix_default_is_the_writer():
    # The pod paper node (Linux) is the one sanctioned writer when unarmed.
    assert wi.default_ledger_write_allowed(environ={}, host_os="posix") is True


def test_windows_default_is_not_the_writer():
    # The local Windows dev box must never append the shared ledger unarmed.
    assert wi.default_ledger_write_allowed(environ={}, host_os="nt") is False


def test_env_arm_overrides_host():
    assert wi.default_ledger_write_allowed(
        environ={wi.ARM_ENV: "1"}, host_os="nt") is True
    assert wi.default_ledger_write_allowed(
        environ={wi.ARM_ENV: "pod"}, host_os="nt") is True


def test_env_disarm_overrides_host():
    assert wi.default_ledger_write_allowed(
        environ={wi.ARM_ENV: "0"}, host_os="posix") is False
    assert wi.default_ledger_write_allowed(
        environ={wi.ARM_ENV: "no"}, host_os="posix") is False


def test_garbage_flag_falls_back_to_host_rule():
    assert wi.default_ledger_write_allowed(
        environ={wi.ARM_ENV: "maybe"}, host_os="nt") is False
    assert wi.default_ledger_write_allowed(
        environ={wi.ARM_ENV: "maybe"}, host_os="posix") is True
