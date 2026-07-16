"""Test scripts.platformkit.ops.quiet_subprocess -- CREATE_NO_WINDOW is applied on win32."""
from unittest import mock

from scripts.platformkit.ops import quiet_subprocess as qs


def test_run_sets_create_no_window_on_win32(monkeypatch):
    monkeypatch.setattr(qs.sys, "platform", "win32")
    monkeypatch.setattr(qs, "CREATE_NO_WINDOW", 0x08000000)
    with mock.patch.object(qs.subprocess, "run") as mock_run:
        qs.run(["echo", "hi"])
    _, kwargs = mock_run.call_args
    assert kwargs["creationflags"] == 0x08000000


def test_run_leaves_creationflags_untouched_off_windows(monkeypatch):
    monkeypatch.setattr(qs.sys, "platform", "linux")
    with mock.patch.object(qs.subprocess, "run") as mock_run:
        qs.run(["echo", "hi"])
    _, kwargs = mock_run.call_args
    assert "creationflags" not in kwargs


def test_popen_sets_create_no_window_on_win32(monkeypatch):
    monkeypatch.setattr(qs.sys, "platform", "win32")
    monkeypatch.setattr(qs, "CREATE_NO_WINDOW", 0x08000000)
    with mock.patch.object(qs.subprocess, "Popen") as mock_popen:
        qs.popen(["echo", "hi"])
    _, kwargs = mock_popen.call_args
    assert kwargs["creationflags"] == 0x08000000


def test_existing_creationflags_are_ored_in(monkeypatch):
    monkeypatch.setattr(qs.sys, "platform", "win32")
    monkeypatch.setattr(qs, "CREATE_NO_WINDOW", 0x08000000)
    with mock.patch.object(qs.subprocess, "run") as mock_run:
        qs.run(["echo", "hi"], creationflags=0x00000200)  # CREATE_NEW_PROCESS_GROUP
    _, kwargs = mock_run.call_args
    assert kwargs["creationflags"] == (0x08000000 | 0x00000200)
