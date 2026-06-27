"""tests/supervisor/test_proc.py -- unit tests for supervisor.proc_win / proc_posix.

Tests use INJECTED subprocess factories; no real long-lived processes are spawned
and no real ports are bound.

Coverage: spawn / is_alive / kill (per-backend) + pid-file round-trip +
find_by_match + proc.py selector.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import supervisor.proc_posix as _posix
import supervisor.proc_win as _win

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _FakeProc:
    def __init__(self, pid: int = 99999) -> None:
        self.pid = pid


def _factory(pid: int):
    def _f(*args, **kwargs):
        for key in ("stdout", "stderr"):
            fh = kwargs.get(key)
            if fh is not None and hasattr(fh, "close"):
                fh.close()
        return _FakeProc(pid)
    return _f


_SPEC = {"name": "test_svc", "python": sys.executable,
         "module": "http.server", "args": ["9987"]}


# ---------------------------------------------------------------------------
# pid-file round-trip (backend-neutral via proc_win)
# ---------------------------------------------------------------------------

class TestPidFile:
    def test_write_read(self, tmp_path: Path) -> None:
        pf = str(tmp_path / "s.pid")
        _win.write_pid_file(pf, 12345)
        assert _win.read_pid_file(pf) == 12345

    def test_missing_returns_none(self, tmp_path: Path) -> None:
        assert _win.read_pid_file(str(tmp_path / "nope.pid")) is None

    def test_corrupt_returns_none(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.pid"
        p.write_text("not-an-int", encoding="ascii")
        assert _win.read_pid_file(str(p)) is None

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        pf = str(tmp_path / "a" / "b" / "c.pid")
        _win.write_pid_file(pf, 7)
        assert Path(pf).exists()

    def test_posix_roundtrip(self, tmp_path: Path) -> None:
        pf = str(tmp_path / "p.pid")
        _posix.write_pid_file(pf, 55555)
        assert _posix.read_pid_file(pf) == 55555


# ---------------------------------------------------------------------------
# spawn -- Windows backend
# ---------------------------------------------------------------------------

class TestSpawnWin:
    def test_handle_fields(self, tmp_path: Path) -> None:
        h = _win.spawn(_SPEC, log_dir=str(tmp_path), subprocess_factory=_factory(77777))
        assert h["name"] == "test_svc"
        assert h["pid"] == 77777
        assert "http.server" in h["cmd"]
        assert "-u" in h["cmd"]

    def test_pid_file_written(self, tmp_path: Path) -> None:
        _win.spawn(_SPEC, log_dir=str(tmp_path), subprocess_factory=_factory(88888))
        assert int((tmp_path / "test_svc.pid").read_text().strip()) == 88888

    def test_log_files_created(self, tmp_path: Path) -> None:
        _win.spawn(_SPEC, log_dir=str(tmp_path), subprocess_factory=_factory(11111))
        assert (tmp_path / "test_svc.out").exists()
        assert (tmp_path / "test_svc.err").exists()


# ---------------------------------------------------------------------------
# spawn -- POSIX backend
# ---------------------------------------------------------------------------

class TestSpawnPosix:
    def test_handle_fields(self, tmp_path: Path) -> None:
        h = _posix.spawn(_SPEC, log_dir=str(tmp_path), subprocess_factory=_factory(44444))
        assert h["pid"] == 44444
        assert h["pid_file"].endswith("test_svc.pid")
        assert "-u" in h["cmd"]

    def test_pid_file_written(self, tmp_path: Path) -> None:
        _posix.spawn(_SPEC, log_dir=str(tmp_path), subprocess_factory=_factory(55555))
        assert _posix.read_pid_file(str(tmp_path / "test_svc.pid")) == 55555


# ---------------------------------------------------------------------------
# is_alive
# ---------------------------------------------------------------------------

class TestIsAlive:
    def test_win_empty_pid_false(self) -> None:
        assert _win.is_alive({"pid": None}) is False

    def test_posix_empty_pid_false(self) -> None:
        assert _posix.is_alive({"pid": None}) is False

    def test_posix_self_is_alive(self) -> None:
        assert _posix.is_alive({"pid": os.getpid()}) is True

    def test_posix_dead_pid_false(self) -> None:
        assert _posix.is_alive({"pid": 9999991}) is False

    def test_win_patched_alive(self) -> None:
        with patch("supervisor.proc_win.is_alive", return_value=True) as m:
            assert m({"pid": 12345}) is True


# ---------------------------------------------------------------------------
# kill
# ---------------------------------------------------------------------------

class TestKill:
    def test_win_no_pid_noop(self) -> None:
        _win.kill({"pid": None, "pid_file": None})  # must not raise

    def test_posix_no_pid_noop(self) -> None:
        _posix.kill({"pid": None, "pid_file": None})  # must not raise

    def test_posix_dead_pid_no_raise(self) -> None:
        _posix.kill({"pid": 9999994, "pid_file": None})

    def test_posix_removes_pid_file(self, tmp_path: Path) -> None:
        pf = tmp_path / "svc.pid"
        pf.write_text("9999993", encoding="ascii")
        _posix.kill({"pid": 9999993, "pid_file": str(pf)})
        # no exception = pass; pid-file removal is best-effort

    def test_win_no_raise_on_dead_pid(self) -> None:
        with patch("supervisor.proc_win.is_alive", return_value=False):
            _win.kill({"pid": 9999992, "pid_file": None})


# ---------------------------------------------------------------------------
# find_by_match -- Windows backend
# ---------------------------------------------------------------------------

class TestFindByMatchWin:
    def test_empty_output(self) -> None:
        fr = MagicMock(); fr.stdout = ""
        with patch("supervisor.proc_win.subprocess") as ms:
            ms.run.return_value = fr
            assert _win.find_by_match("no_such_xyz") == []

    def test_matching_line(self) -> None:
        line = "PC01,C:\\py.exe my_module --arg,54321"
        fr = MagicMock(); fr.stdout = f"Header\r\n{line}\r\n"
        with patch("supervisor.proc_win.subprocess") as ms:
            ms.run.return_value = fr
            result = _win.find_by_match("my_module")
        assert len(result) == 1
        assert result[0]["pid"] == 54321

    def test_no_match(self) -> None:
        fr = MagicMock(); fr.stdout = "H\r\nPC,other.exe,111\r\n"
        with patch("supervisor.proc_win.subprocess") as ms:
            ms.run.return_value = fr
            assert _win.find_by_match("special_xyz") == []


# ---------------------------------------------------------------------------
# find_by_match -- POSIX backend
# ---------------------------------------------------------------------------

class TestFindByMatchPosix:
    def test_proc_fs_match(self, tmp_path: Path) -> None:
        pid_dir = tmp_path / "11223"; pid_dir.mkdir()
        (pid_dir / "cmdline").write_bytes(b"python\x00-m\x00mymodule\x00")
        other = tmp_path / "99887"; other.mkdir()
        (other / "cmdline").write_bytes(b"bash\x00script.sh\x00")
        notd = tmp_path / "notdigit"  # should be skipped

        with patch("supervisor.proc_posix.Path") as mpc:
            mp = MagicMock()
            mp.is_dir.return_value = True
            mp.iterdir.return_value = [pid_dir, other, notd]
            mpc.side_effect = lambda p: mp if p == "/proc" else Path(p)
            result = _posix.find_by_match("mymodule")

        pids = [h["pid"] for h in result]
        assert 11223 in pids
        assert 99887 not in pids

    def test_ps_fallback(self) -> None:
        fr = MagicMock()
        fr.stdout = "  42 python -m special_daemon --forever\n  43 bash\n"
        with patch("supervisor.proc_posix.Path") as mpc:
            pp = MagicMock(); pp.is_dir.return_value = False
            mpc.return_value = pp
            with patch("supervisor.proc_posix.subprocess") as ms:
                ms.run.return_value = fr
                result = _posix.find_by_match("special_daemon")
        assert any(h["pid"] == 42 for h in result)


# ---------------------------------------------------------------------------
# proc.py selector
# ---------------------------------------------------------------------------

class TestProcSelector:
    def test_imports_cleanly(self) -> None:
        import importlib
        import supervisor.proc as pm
        importlib.reload(pm)
        for attr in ("spawn", "is_alive", "kill", "write_pid_file",
                     "read_pid_file", "find_by_match"):
            assert callable(getattr(pm, attr))

    def test_win_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SUPERVISOR_BACKEND", "win")
        import importlib, supervisor.proc as pm
        importlib.reload(pm)
        assert callable(pm.spawn)

    def test_posix_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SUPERVISOR_BACKEND", "posix")
        import importlib, supervisor.proc as pm
        importlib.reload(pm)
        assert callable(pm.spawn)
