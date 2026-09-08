"""G62 -- the run-environment sidecar: every schema key, every null path, the stampless read.

n = 6 CONSTRUCT (Q7): each case below is enumerated by hand, not sampled, and matches section 4 of
docs/evidence/tracking/g62_prereg_2026-09-08.md. No route runs, no video is opened, no pod is
touched and nothing outside tmp_path is written.
"""
import builtins
import json

from scripts.platformkit import env_sidecar
from scripts.platformkit.env_sidecar import SCHEMA, SIDECAR_NAME, capture, read, write
from scripts.platformkit.tracking import census_recomputable

TOP_KEYS = {"captured_utc", "cgroup_cpu_quota", "cpu_count", "git", "host", "import_shim", "libraries",
            "modules", "platform", "python_version", "schema", "seed", "seed_reason", "threads",
            "torch_build"}
SELF = "scripts/platformkit/env_sidecar.py"


class _Result:
    """Stand-in for a completed subprocess, so the git probe is exercised without a repository."""

    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


# CASE 1 -- with torch: every key present with the declared type.
def test_capture_carries_every_key_with_the_right_type():
    stamp = capture(modules=[SELF])
    assert set(stamp) == TOP_KEYS
    assert stamp["schema"] == SCHEMA
    assert isinstance(stamp["python_version"], str) and stamp["python_version"][0].isdigit()
    assert isinstance(stamp["platform"], str) and stamp["platform"]
    assert stamp["captured_utc"].endswith("Z") and len(stamp["captured_utc"]) == 20
    assert stamp["cpu_count"] is None or isinstance(stamp["cpu_count"], int)
    assert stamp["cgroup_cpu_quota"] is None or isinstance(stamp["cgroup_cpu_quota"], str)
    assert set(stamp["host"]) == {"hostname", "role", "role_rule"}
    assert stamp["host"]["role"] in ("pod", "local") and stamp["host"]["role_rule"]
    assert isinstance(stamp["import_shim"], str)
    assert set(stamp["libraries"]) == set(env_sidecar.LIBRARIES)
    assert all(v is None or isinstance(v, str) for v in stamp["libraries"].values())
    assert set(stamp["threads"]) == {"MKL_NUM_THREADS", "OMP_NUM_THREADS", "torch_num_threads"}
    assert set(stamp["torch_build"]) == {"cuda_available", "cuda_version", "cudnn_version",
                                         "unavailable_reason"}
    assert set(stamp["git"]) == {"head_sha", "dirty", "unavailable_reason"}
    assert stamp["seed"] is None and stamp["seed_reason"] == env_sidecar.NO_SEED
    assert [item["path"] for item in stamp["modules"]] == [SELF]
    assert len(stamp["modules"][0]["sha256"]) == 64
    assert stamp["modules"][0]["unavailable_reason"] is None


# CASES 2 and 6 -- write() round-trips as ASCII with sorted keys; a stampless artifact reads None.
def test_write_round_trips_and_a_stampless_artifact_still_parses(tmp_path):
    stamped, bare = tmp_path / "stamped", tmp_path / "bare"
    bare.mkdir()
    target = write(stamped, modules=[SELF], seed=7, seed_reason="pinned by the construct")
    assert target == stamped / SIDECAR_NAME
    body = target.read_bytes()
    body.decode("ascii")
    document = json.loads(body)
    assert list(document) == sorted(document)
    assert document == read(stamped) and document["seed"] == 7
    assert document["seed_reason"] == "pinned by the construct"
    assert read(bare) is None
    assert read(tmp_path / "never_written") is None


# CASE "WITHOUT TORCH" -- an unimportable library is a null, never an import error.
def test_an_unimportable_library_is_a_null_not_an_exception(monkeypatch):
    real = builtins.__import__

    def fake(name, *args, **kwargs):
        if name in env_sidecar.LIBRARIES:
            raise ImportError("monkeypatched away: " + name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake)
    stamp = capture()
    assert stamp["libraries"] == {name: None for name in env_sidecar.LIBRARIES}
    assert stamp["torch_build"] == {"cuda_available": None, "cuda_version": None,
                                    "cudnn_version": None,
                                    "unavailable_reason": "torch not importable"}
    assert stamp["threads"]["torch_num_threads"] is None
    assert set(stamp) == TOP_KEYS


# CASE 3 -- a dirty tree is recorded as dirty.
def test_a_dirty_tree_is_recorded(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _Result(0, "abc1234\n") if "rev-parse" in cmd else _Result(0, " M one.py\n")

    monkeypatch.setattr(env_sidecar.subprocess, "run", fake_run)
    assert env_sidecar._git("/nowhere") == {"head_sha": "abc1234", "dirty": True,
                                            "unavailable_reason": None}


# CASE 4 -- an unreadable revision is an explicit null with a reason, never a silent empty sha.
def test_an_unreadable_revision_is_an_explicit_null_with_a_reason(monkeypatch):
    monkeypatch.setattr(env_sidecar.subprocess, "run",
                        lambda cmd, **kwargs: _Result(129, "", "not a git repository"))
    absent = env_sidecar._git("/nowhere")
    assert absent["head_sha"] is None and absent["dirty"] is None
    assert "not a git repository" in absent["unavailable_reason"]

    def boom(cmd, **kwargs):
        raise OSError("no git on this box")

    monkeypatch.setattr(env_sidecar.subprocess, "run", boom)
    assert env_sidecar._git(".")["unavailable_reason"] == "git not runnable: OSError"


# CASE 5 -- a named module that does not exist is a null with a reason, not a crash.
def test_a_missing_named_module_is_a_null_with_a_reason(tmp_path):
    stamp = capture(modules=[SELF, "scripts/platformkit/no_such_module.py"])
    missing = [item for item in stamp["modules"] if item["path"].endswith("no_such_module.py")][0]
    assert missing["sha256"] is None
    assert missing["unavailable_reason"] == "unreadable: FileNotFoundError"
    assert len(stamp["modules"]) == 2


# The hook is additive: identical bytes with the opt-out, one extra new file without it.
def test_the_hooked_runner_is_additive_and_the_opt_out_restores_master(tmp_path):
    on, off = tmp_path / "on" / "census.csv", tmp_path / "off" / "census.csv"
    common = ["absent_memo.md", "--root", str(tmp_path), "--csv"]
    assert census_recomputable.main(common + [str(on)]) == 0
    assert census_recomputable.main(common + [str(off), "--no-env-sidecar"]) == 0
    assert on.read_bytes() == off.read_bytes()
    assert (on.parent / SIDECAR_NAME).exists()
    assert not (off.parent / SIDECAR_NAME).exists()
    stamp = read(on.parent)
    assert [item["path"] for item in stamp["modules"]] == list(census_recomputable.ENV_MODULES)
