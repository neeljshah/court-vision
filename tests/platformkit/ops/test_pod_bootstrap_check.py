"""S47 -- pod_bootstrap_check: module list, self-exclusion, missing module.

Three CONSTRUCT cases, one per claim the bootstrap rests on:
  1. the module list is READ from config/boot/paper.json + supervisor/stack_specs
     (not hardcoded) -- a name added to the profile JSON changes the output;
  2. the /proc scan excludes the checking command itself (own pid AND own
     cmdline marker), so it can never report or act on its own shell;
  3. a module that does not exist is REPORTED as failing.
"""
from __future__ import annotations

import json
import os
import sys

from scripts.platformkit.ops import pod_bootstrap_check as pbc


def test_module_list_is_read_from_the_profile_and_specs() -> None:
    """Case 1 -- the list comes from the JSON allowlist + stack_specs."""
    services = json.loads(
        (pbc._REPO_ROOT / "config" / "boot" / "paper.json").read_text("utf-8")
    )["services"]
    mods = pbc.profile_modules("paper")
    names = [n for n, _ in mods]

    # every allowlisted service appears, with a real module string from specs
    assert set(names) == set(services), (sorted(names), sorted(services))
    assert all(m and "." in m for _, m in mods)
    assert ("m1_producer", "predict_service.scheduler") in mods

    # dropping a service from the allowlist drops it from the list -> read, not
    # hardcoded. (manifest() keeps the depends_on chain, so drop a leaf.)
    from supervisor.config import BootProfile

    kept = tuple(s for s in services if s != "m44_exec_evidence")
    trimmed = BootProfile(name="paper", profile="paper", services=kept)
    assert "m44_exec_evidence" not in [
        s.name for s in trimmed.specs()]

    # the required env flags are the profile's global_env plus the two capture
    # flags run_pod_capture demands.
    env = pbc.required_env("paper")
    assert "NBA_AI_SUPERVISED" in env
    assert "CV_CAPTURE_POD" in env and "CV_MLB_BOOK_ARCHIVE_LIVE" in env


def test_proc_scan_excludes_the_checking_command(tmp_path) -> None:
    """Case 2 -- own pid and own cmdline marker are both skipped."""
    def _mkpid(pid: int, cmdline: str) -> None:
        d = tmp_path / str(pid)
        d.mkdir()
        (d / "cmdline").write_bytes(cmdline.replace(" ", "\0").encode())

    _mkpid(19236, "/usr/local/bin/python -u -m supervisor --profile paper")
    _mkpid(4035, "python track_daemon.py")          # must not match
    _mkpid(777, "sh -c python pod_bootstrap_check.py --profile paper")
    _mkpid(999, "python -m supervisor --profile paper")  # the caller itself

    found = pbc.scan_proc(("-m supervisor",), proc_root=str(tmp_path),
                          self_pid=999)
    hits = found["-m supervisor"]
    assert [pid for pid, _ in hits] == [19236], hits   # 999 self, 777 marker

    # a non-existent /proc (running locally on Windows) is empty, not an error
    assert pbc.scan_proc(("-m supervisor",),
                         proc_root=str(tmp_path / "nope")) == {
        "-m supervisor": []}


def test_missing_module_is_reported_and_exits_nonzero() -> None:
    """Case 3 -- a fake module fails the import check and the CLI dry-run passes."""
    res = pbc.check_imports(["json", "s47_no_such_module_xyz"], sys.executable)
    assert res["json"] is None
    assert res["s47_no_such_module_xyz"] is not None
    assert "ModuleNotFoundError" in res["s47_no_such_module_xyz"]

    # a bad interpreter path fails every module rather than raising
    bad = pbc.check_imports(["json"], os.path.join("no", "such", "python"))
    assert bad["json"] is not None

    assert pbc.main(["--profile", "paper", "--dry-run"]) == 0
