"""pod_bootstrap_check -- preflight for the pod paper stack after a restart.

Reports, for one boot profile (config/boot/<name>.json + supervisor/stack_specs):

  1. the python MODULE list the profile boots,
  2. an IMPORT check of each module under a given interpreter,
  3. the required ENV flags (profile global_env + the two capture flags),
  4. the matching /proc pids (own shell EXCLUDED) + heartbeat file ages,
  5. with --functional, seven RUNTIME probes (S54 + the S78 factory-source
     probe): an import-only preflight passed 14/14 while every parquet read
     failed (pyarrow wiped), and the tree shipped clean while every gitignored
     data/ source the screen predictor reads was absent.

Exit status is nonzero when any module fails to import (a missing module or a
missing package) or any --functional probe FAILs; ENV / PROC findings are
reported but do not change it, so the bootstrap can use this as an import gate
and still decide about booting itself.

Runs on the pod and locally (`--dry-run` skips the import subprocess and the
/proc scan, so it works on a box with neither the packages nor /proc).

Stdlib-only, ASCII-only. Reads only; never kills, never boots, never writes
data/registry/, never flips a flag on.

    python scripts/platformkit/ops/pod_bootstrap_check.py --profile paper \
        --functional --python /usr/local/bin/python
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:  # run as a file path, not as -m
    sys.path.insert(0, str(_REPO_ROOT))

from supervisor.config import load_profile  # noqa: E402
from scripts.platformkit.ops.preflight_floors import MLB_EXISTENCE_FLOOR_PROBES

# run_pod_capture refuses to start without these (S21 memo section 7); the
# profile's own global_env carries the rest.
_CAPTURE_ENV = ("CV_CAPTURE_POD", "CV_MLB_BOOK_ARCHIVE_LIVE")

# Anything whose /proc cmdline contains this is the checking command itself.
_SELF_MARKER = "pod_bootstrap"

_PROC_PATTERNS = ("-m supervisor", "run_pod_capture")

# One child per module, printed as "OK <module>" / "FAIL <module> <error>".
_IMPORT_PROBE = (
    "import importlib,sys\n"
    "for m in sys.argv[1:]:\n"
    "    try:\n"
    "        importlib.import_module(m)\n"
    "        print('OK %s' % m)\n"
    "    except BaseException as exc:\n"
    "        print('FAIL %s %s: %s' % (m, type(exc).__name__, exc))\n"
)


# --functional: one snippet per probe, run in ONE child of --python with a hard
# 60 s timeout. Prints one line on success; ANY exception -> FAIL + that cause.
_PROBE_TIMEOUT_S = 60.0
_FUNCTIONAL_PROBES: Dict[str, str] = {
    **MLB_EXISTENCE_FLOOR_PROBES,
    # live_states() stays fail-open BY DESIGN ([] on any error): an empty slate is
    # OK; FAIL only when the call itself raises (import / name breakage).
    "espn_live_state_mlb": (
        "from scripts.platformkit.ingame.ingame_live_state import live_states\n"
        "st = live_states('mlb'); assert isinstance(st, list), repr(type(st))\n"
        "print('live_games=%d' % len(st))\n"),
    # S78: the tree ships by `git archive`, but every source the real screen predictor reads
    # lives under gitignored data/ -- an unprovisioned pod boots a runner that crashes at bind
    # and then throws FileNotFound screen_failed per pass. The required set is DERIVED from the
    # sidecars + screen_predictor's own registries, so this probe cannot drift from them.
    "factory_sources": (
        "from scripts.platformkit.ops.factory_source_manifest import missing_local, required\n"
        "need = required(ingame=False); gone = missing_local(need)\n"
        "assert not gone, '%d of %d absent, e.g. %s' % (len(gone), len(need), gone[:3])\n"
        "print('factory sources present: %d/%d' % (len(need), len(need)))\n"),
    "boot_packages": (
        "import fastapi, sklearn, pyarrow, statsmodels, xgboost\n"
        "print('fastapi=%s sklearn=%s pyarrow=%s statsmodels=%s xgboost=%s'"
        " % (fastapi.__version__, sklearn.__version__, pyarrow.__version__,"
        " statsmodels.__version__, xgboost.__version__))\n"),
    # pid from cmdline; scan_proc self-excludes this child (its own cmdline
    # carries the _SELF_MARKER via the import line below).
    "supervisor_lock_env": (
        "import os; from supervisor._singleton import DEFAULT_LOCK_PATH\n"
        "from scripts.platformkit.ops.pod_bootstrap_check import scan_proc, _CAPTURE_ENV\n"
        "hits = scan_proc(('-m supervisor',))['-m supervisor']\n"
        "assert hits, 'no -m supervisor pid in /proc'\n"
        "pid = hits[0][0]\n"
        "kvs = open('/proc/%d/environ' % pid).read().split(chr(0))\n"
        "env = dict(kv.split('=', 1) for kv in kvs if '=' in kv)\n"
        "missing = [n for n in _CAPTURE_ENV if n not in env]\n"
        "assert not missing, 'pid %d missing %s' % (pid, missing)\n"
        "print('pid=%d lock_exists=%s flags=%s'"
        " % (pid, os.path.exists(DEFAULT_LOCK_PATH), ','.join(_CAPTURE_ENV)))\n"),
}


def profile_modules(profile: str) -> List[Tuple[str, str]]:
    """[(service name, python module)] for every kind=="py" spec of *profile*."""
    specs = load_profile(profile).specs()
    return [(s.name, s.module) for s in specs if s.kind == "py" and s.module]


def required_env(profile: str) -> List[str]:
    """Env flag names the booted stack needs: profile global_env + capture."""
    names = list(load_profile(profile).global_env)
    names += [n for n in _CAPTURE_ENV if n not in names]
    return names


def heartbeat_paths(profile: str) -> List[Tuple[str, str]]:
    """[(service name, heartbeat file)] for specs with a heartbeat probe."""
    out: List[Tuple[str, str]] = []
    for spec in load_profile(profile).specs():
        path = getattr(spec.readiness, "heartbeat_path", None)
        if spec.readiness.kind == "heartbeat-file-fresh" and path:
            out.append((spec.name, str(path)))
    return out


def check_imports(modules: Sequence[str], python: str,
                  cwd: Optional[str] = None) -> Dict[str, Optional[str]]:
    """Import each module in ONE child of *python*. Value None == imported."""
    result: Dict[str, Optional[str]] = {m: "not reported" for m in modules}
    if not modules:
        return result
    try:
        proc = subprocess.run(
            [python, "-c", _IMPORT_PROBE, *modules],
            cwd=cwd or str(_REPO_ROOT), capture_output=True, text=True,
            timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return {m: "%s: %s" % (type(exc).__name__, exc) for m in modules}
    for line in proc.stdout.splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 2 or parts[1] not in result:
            continue
        result[parts[1]] = None if parts[0] == "OK" else (
            parts[2] if len(parts) > 2 else "import failed")
    return result


def scan_proc(patterns: Sequence[str] = _PROC_PATTERNS,
              proc_root: str = "/proc",
              self_pid: Optional[int] = None,
              self_marker: str = _SELF_MARKER,
              ) -> Dict[str, List[Tuple[int, str]]]:
    """Live pids whose cmdline contains each pattern.

    SELF-EXCLUSION: this scan's own pid and any cmdline carrying *self_marker*
    are skipped, so the checking command can never match itself (a pattern that
    matches the checker is how a /proc loop kills its own ssh session).
    """
    self_pid = os.getpid() if self_pid is None else self_pid
    found: Dict[str, List[Tuple[int, str]]] = {p: [] for p in patterns}
    root = Path(proc_root)
    if not root.is_dir():
        return found
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == self_pid:
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        cmd = raw.decode("utf-8", "replace").replace("\0", " ").strip()
        if not cmd or self_marker in cmd:
            continue
        for pat in patterns:
            if pat in cmd:
                found[pat].append((pid, cmd))
    return found


def run_probe(code: str, python: str, cwd: Optional[str] = None,
              timeout: float = _PROBE_TIMEOUT_S) -> Tuple[bool, str]:
    """Run ONE probe snippet in a child of *python*. -> (ok, one-line cause)."""
    try:
        proc = subprocess.run([python, "-c", code], cwd=cwd or str(_REPO_ROOT),
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "timeout after %.0fs" % timeout
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)
    last = lambda s: ([ln.strip() for ln in s.splitlines() if ln.strip()] or [""])[-1]
    if proc.returncode == 0:
        return True, last(proc.stdout) or "(no output)"
    return False, last(proc.stderr) or "exit %d" % proc.returncode


def run_functional(python: str, cwd: Optional[str] = None,
                   probes: Optional[Dict[str, str]] = None) -> int:
    """Print OK/FAIL + cause for each named probe. Returns the FAIL count."""
    probes = _FUNCTIONAL_PROBES if probes is None else probes
    print("FUNCTIONAL (%s, %.0fs each):" % (python, _PROBE_TIMEOUT_S))
    failed = 0
    for name, code in probes.items():
        ok, cause = run_probe(code, python, cwd)
        failed += 0 if ok else 1
        print("  %-4s %-20s %s" % ("OK" if ok else "FAIL", name, cause[:140]))
    return failed


def _print_env(profile: str) -> int:
    missing = 0
    print("ENV (required flags):")
    for name in required_env(profile):
        val = os.environ.get(name)
        if val is None:
            missing += 1
            print("  MISSING %s" % name)
        else:
            print("  set     %s=%s" % (name, val))
    return missing


def _print_heartbeats(profile: str, repo: Optional[str] = None) -> None:
    print("HEARTBEATS:")
    now = time.time()
    root = Path(repo) if repo else _REPO_ROOT
    for name, path in heartbeat_paths(profile):
        p = Path(path)
        if not p.is_absolute():
            p = root / p
        try:
            print("  %-24s %8.0fs  %s" % (name, now - p.stat().st_mtime, path))
        except OSError:
            print("  %-24s   ABSENT  %s" % (name, path))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="pod boot-profile preflight")
    ap.add_argument("--profile", default="paper", help="config/boot/<name>.json")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter to import-check under")
    ap.add_argument("--dry-run", action="store_true",
                    help="list only: no import subprocess, no /proc scan")
    ap.add_argument("--functional", action="store_true",
                    help="also run the runtime probes (60s each; not in dry-run)")
    ap.add_argument("--repo", default=None,
                    help="repo root when run from OUTSIDE the tree (import cwd)")
    args = ap.parse_args(argv)

    bp = load_profile(args.profile)
    mods = profile_modules(args.profile)
    print("PROFILE: %s (source=%s, manifest=%s) -- %d python services"
          % (bp.name, bp.source, bp.profile, len(mods)))
    print("MODULES:")
    for name, mod in mods:
        print("  %-24s %s" % (name, mod))

    if args.dry_run:
        print("IMPORTS: skipped (--dry-run)")
        _print_env(args.profile)
        print("PROC: skipped (--dry-run)")
        _print_heartbeats(args.profile, args.repo)
        print("RESULT: dry-run OK")
        return 0

    results = check_imports([m for _, m in mods], args.python, cwd=args.repo)
    bad = [(m, e) for m, e in results.items() if e is not None]
    print("IMPORTS (%s): %d/%d OK"
          % (args.python, len(results) - len(bad), len(results)))
    for mod, err in sorted(bad):
        print("  FAIL %s -- %s" % (mod, err))

    _print_env(args.profile)

    print("PROC (self-excluded):")
    for pat, hits in scan_proc().items():
        if not hits:
            print("  %-16s ABSENT" % pat)
        for pid, cmd in hits:
            print("  %-16s pid %-8d %s" % (pat, pid, cmd[:110]))

    _print_heartbeats(args.profile, args.repo)

    n_fail = run_functional(args.python, args.repo) if args.functional else 0
    problems = (["%d module(s) not importable" % len(bad)] if bad else []) + (
        ["%d functional probe(s) FAILED" % n_fail] if n_fail else [])
    print("RESULT: %s" % ("FAIL -- " + "; ".join(problems) if problems
                          else "OK -- imports clean, no probe failed"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
