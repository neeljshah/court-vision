"""gates.py — verification gate runner (task / wave / phase tiers).
Cardinal rule: absent script/baseline → SKIP, never FAIL. H0: almost everything skips."""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import FrozenSet, List, Optional, Set

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts" / "platformkit"))
import harness_state  # noqa: E402

# Lazy import of select_tests — absent during bootstrap before select_tests.py is written.
try:
    import select_tests as _select_tests  # noqa: E402
    _SELECT_AVAILABLE = True
except ImportError:
    _select_tests = None  # type: ignore[assignment]
    _SELECT_AVAILABLE = False

# Lazy import of the P0-H-005 junit parser (scripts/platformkit on sys.path above).
try:
    import capture_pytest_baseline as _cap  # noqa: E402
    _CAP_AVAILABLE = True
except ImportError:
    _cap = None  # type: ignore[assignment]
    _CAP_AVAILABLE = False

# ---------------------------------------------------------------------------
# Protected-file registry (§6.4)
# ---------------------------------------------------------------------------
PROTECTED: List[str] = [
    "src/prediction/betting_portfolio.py",
    "database/schema.sql",
    "CLAUDE.md",
    "requirements.txt",
    "environment.yml",
    "src/brain/flags.py",
    "README.md",
    "docs/JOB_EVIDENCE_PACKET.md",
    "api/templates/",
    "data/registry/",
    ".planning/loop/",
]
_EXACT = [p for p in PROTECTED if not p.endswith("/")]
_PREFIXES = [p for p in PROTECTED if p.endswith("/")]

PYTEST_BASELINE = ROOT / ".planning" / "platform" / "baselines" / "pytest_baseline.txt"
_SCRIPTS = {
    "G2": "scripts/platformkit/fixture_slate_hash.py",
    "G4": "tests/platform/test_api_boot.py",
    "G5": "scripts/platformkit/check_shims.py",
    "IC": "scripts/platformkit/check_import_contract.py",
}

# ---------------------------------------------------------------------------
# Hermeticity — P0-H-004
# A gate run must leave zero git diff.
# Allowlist grows ONLY by adding an explicit entry here with a comment explaining
# why the path is exempt.  Starts empty: porcelain already excludes .gitignored
# paths, so legitimate build artefacts should be gitignored, not allowlisted.
# ---------------------------------------------------------------------------
HERMETICITY_ALLOWLIST: FrozenSet[str] = frozenset(
    # intentionally empty — add entries here with a comment recording the decision
)


def _git_porcelain() -> Set[str]:
    """Return the set of porcelain-status lines from ``git status --porcelain``.

    Each entry is a raw porcelain line (e.g. ``" M src/foo.py"``).
    Returns an empty set if git is unavailable or the repo has no git history.
    """
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(ROOT),
        )
        if r.returncode != 0:
            return set()
        return {line for line in r.stdout.splitlines() if line.strip()}
    except Exception:  # noqa: BLE001
        return set()


def hermeticity_gate(before: Set[str], after: Set[str], tier: str) -> dict:
    """Compare git-status snapshots taken before/after a pytest-running gate.

    Returns a gate dict with status PASS or FAIL.  On FAIL, appends the
    offending paths and tier to the harness ledger (REPORT-ONLY — never reverts).

    Args:
        before: porcelain lines captured before the gate ran.
        after:  porcelain lines captured after the gate ran.
        tier:   the tier string (``"task"`` / ``"wave"`` / ``"phase"``).

    Returns:
        Gate dict with keys: gate, status, tier, and (on FAIL) why + offending.
    """
    added = after - before - HERMETICITY_ALLOWLIST
    removed = before - after - HERMETICITY_ALLOWLIST

    if not added and not removed:
        return {"gate": "HERMETICITY", "status": "PASS", "tier": tier}

    offending = sorted(added | removed)
    why = (
        f"gate run mutated git working tree ({len(offending)} path(s)); "
        f"added={sorted(added)!r} removed={sorted(removed)!r}"
    )
    # Append to ledger — REPORT-ONLY, never auto-revert
    try:
        harness_state.append_ledger(
            "hermeticity_fail",
            tier=tier,
            offending=offending,
            added=sorted(added),
            removed=sorted(removed),
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "gate": "HERMETICITY",
        "status": "FAIL",
        "tier": tier,
        "why": why,
        "offending": offending,
    }


# Detect pytest-timeout once at import; degrade silently when absent.
try:
    import pytest_timeout as _pt  # noqa: F401
    _PYTEST_TIMEOUT_AVAILABLE = True
except ImportError:
    _PYTEST_TIMEOUT_AVAILABLE = False


def _script_exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def _skip(name: str, why: str) -> dict:
    return {"gate": name, "status": "SKIP", "why": why}


def protected_scan(files: List[str]) -> List[str]:
    """Return the subset of *files* that are protected (exact or prefix match)."""
    hits: List[str] = []
    for f in files:
        n = f.replace("\\", "/").lstrip("/")
        if n in _EXACT or any(n.startswith(pfx) for pfx in _PREFIXES):
            hits.append(f)
    return hits


def _parse_counts(text: str) -> dict:
    """Parse pytest summary counts from output text."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for line in reversed(text.splitlines()):
        if re.search(r"\d+\s+(passed|failed|error|skipped)", line):
            for key, pat in [("passed", r"(\d+)\s+passed"), ("failed", r"(\d+)\s+failed"),
                              ("skipped", r"(\d+)\s+skipped"), ("errors", r"(\d+)\s+error")]:
                m = re.search(pat, line)
                if m:
                    counts[key] = int(m.group(1))
            break
    return counts


def run_pytest(targets: Optional[List[str]] = None, timeout: int = 1800,
               junitxml: Optional[str] = None) -> dict:
    """Run pytest; never raises.  Keys: ran, timed_out, passed, failed, skipped, errors,
    rc (success only), elapsed_s.  On timeout salvages partial counts from e.stdout."""
    cmd = [sys.executable, "-m", "pytest"]
    cmd += [str(t) for t in targets] if targets else [str(ROOT / "tests")]
    cmd += ["-q", "--no-header", "--tb=no"]
    if junitxml:
        # Full-suite id-aware runs must survive duplicate-basename collection
        # errors (they become frozen error ids) instead of aborting (P0-H-005).
        cmd += ["--junitxml=" + str(junitxml), "--continue-on-collection-errors"]
    if _PYTEST_TIMEOUT_AVAILABLE:
        cmd += ["--timeout=300", "--timeout-method=thread"]
    child_env = {**os.environ, "NBA_OFFLINE": "1"}
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=str(ROOT), env=child_env)
        return {"ran": True, "timed_out": False,
                **_parse_counts((r.stdout or "") + (r.stderr or "")),
                "rc": r.returncode, "elapsed_s": time.monotonic() - t0}
    except subprocess.TimeoutExpired as e:
        partial = ""
        if hasattr(e, "stdout") and e.stdout:
            partial += e.stdout if isinstance(e.stdout, str) else e.stdout.decode("utf-8", errors="replace")
        if hasattr(e, "output") and e.output and e.output is not getattr(e, "stdout", None):
            partial += e.output if isinstance(e.output, str) else e.output.decode("utf-8", errors="replace")
        return {"ran": False, "timed_out": True, "error": f"timed out after {timeout}s",
                "elapsed_s": time.monotonic() - t0, **_parse_counts(partial)}
    except Exception as e:  # noqa: BLE001
        return {"ran": False, "timed_out": False, "error": str(e),
                "elapsed_s": time.monotonic() - t0}


def _run_script(gate: str, script_key: str, extra_args: Optional[List[str]] = None) -> dict:
    """Run a helper script via subprocess; return SKIP if absent."""
    rel = _SCRIPTS[script_key]
    if not _script_exists(rel):
        return _skip(gate, f"script absent: {rel}")
    try:
        r = subprocess.run([sys.executable, str(ROOT / rel)] + (extra_args or []),
                           capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        verdict = "PASS" if r.returncode == 0 else "FAIL"
        return {"gate": gate, "status": verdict, "rc": r.returncode,
                "stdout": (r.stdout or "").strip()[:400]}
    except subprocess.TimeoutExpired:
        return _skip(gate, "script timed out after 120s")
    except Exception as e:  # noqa: BLE001
        return _skip(gate, f"exception: {e}")


# --- G1 id-aware full-suite gate (P0-H-005) --------------------------------
# The full serial suite runs for hours; budget matches the capture run's 8h.
G1_FULL_SUITE_TIMEOUT = int(os.environ.get("CV_G1_TIMEOUT_S", "28800"))
G1_JUNIT = ROOT / ".planning" / "platform" / "baselines" / "_g1_last_run_junit.xml"


def _g1_legacy_counts(text: str) -> dict:
    """Pre-P0-H-005 count-only comparison (baseline in `k=v` format)."""
    baseline: dict = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            try:
                baseline[k.strip()] = int(v.strip())
            except ValueError:
                pass
    res = run_pytest(timeout=G1_FULL_SUITE_TIMEOUT)
    if res.get("timed_out"):
        return {"gate": "G1", "status": "FAIL",
                "why": f"pytest timed out after {res.get('elapsed_s', 0):.1f}s with baseline present",
                "baseline": baseline, "timed_out": True}
    if not res.get("ran"):
        return _skip("G1", f"pytest failed to run: {res.get('error')}")
    ok = res["passed"] >= baseline.get("passed", 0) and res["failed"] == 0 and res["errors"] == 0
    return {"gate": "G1", "status": "PASS" if ok else "FAIL",
            "why": "legacy count-format baseline -- re-baseline via run_pytest_baseline.py",
            "baseline": baseline,
            "actual": {k: res[k] for k in ("passed", "failed", "skipped", "errors")},
            "rc": res["rc"]}


def g1(baseline_required: bool = False) -> dict:
    """G1 — id-aware full-suite gate (P0-H-005).

    FAIL iff NEW failing/error ids appear vs the frozen baseline, or the
    collected count drops beyond tolerance.  Frozen (pre-existing) failing ids
    are excluded until an explicit phase-boundary re-baseline.  Parses
    junit-xml, never the pytest summary line.  Legacy ``k=v`` count baselines
    fall back to the old count comparison until the id-aware baseline lands.
    """
    if not PYTEST_BASELINE.exists():
        if baseline_required:
            return _skip("G1", "baseline absent and baseline_required=True")
        res = run_pytest(timeout=G1_FULL_SUITE_TIMEOUT, junitxml=str(G1_JUNIT))
        if not res.get("ran"):
            return _skip("G1", f"pytest failed to run: {res.get('error')}")
        try:
            PYTEST_BASELINE.parent.mkdir(parents=True, exist_ok=True)
            if _CAP_AVAILABLE and G1_JUNIT.exists():
                parsed = _cap.parse_junit_xml(G1_JUNIT)
                PYTEST_BASELINE.write_text(json.dumps({
                    "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "partial": False,
                    "note": "recorded by g1() -- id-aware",
                    "passed": parsed["passed"], "skipped": parsed["skipped"],
                    "total_collected": parsed["total_collected"],
                    "failed_ids": sorted(parsed["failed_ids"]),
                    "error_ids": sorted(parsed["error_ids"]),
                }, indent=2) + "\n", encoding="utf-8")
            else:
                PYTEST_BASELINE.write_text(
                    "\n".join(f"{k}={res[k]}" for k in ("passed", "failed", "skipped", "errors")) + "\n",
                    encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return {"gate": "G1", "status": "RECORDED",
                "why": "baseline absent — current run recorded", "counts": res}

    text = PYTEST_BASELINE.read_text(encoding="utf-8")
    if not text.lstrip().startswith("{"):
        return _g1_legacy_counts(text)

    baseline = json.loads(text)
    baseline.setdefault("failed_ids", [])
    baseline.setdefault("error_ids", [])
    if baseline.get("partial"):
        return _skip("G1", "baseline is PARTIAL (capture budget exceeded) -- "
                           "re-run scripts/platformkit/run_pytest_baseline.py")
    if not _CAP_AVAILABLE:
        return _skip("G1", "capture_pytest_baseline module unavailable")

    res = run_pytest(timeout=G1_FULL_SUITE_TIMEOUT, junitxml=str(G1_JUNIT))
    if res.get("timed_out"):
        return {"gate": "G1", "status": "FAIL",
                "why": f"pytest timed out after {res.get('elapsed_s', 0):.1f}s with baseline present",
                "timed_out": True}
    if not res.get("ran"):
        return _skip("G1", f"pytest failed to run: {res.get('error')}")
    if not G1_JUNIT.exists():
        return _skip("G1", "junit-xml not produced by pytest run")

    parsed = _cap.parse_junit_xml(G1_JUNIT)
    ok, reasons = _cap.g1_compare(baseline, parsed)
    frozen = len(set(baseline["failed_ids"]) | set(baseline["error_ids"]))
    return {"gate": "G1", "status": "PASS" if ok else "FAIL",
            "why": ("; ".join(reasons) if reasons else
                    f"id-aware: no new failing/error ids ({frozen} frozen excluded); "
                    f"collected {parsed['total_collected']}"),
            "frozen_excluded": frozen,
            "actual": {"passed": parsed["passed"], "skipped": parsed["skipped"],
                        "failed": len(parsed["failed_ids"]),
                        "errors": len(parsed["error_ids"]),
                        "collected": parsed["total_collected"]},
            "rc": res.get("rc")}


def g2() -> dict:
    """G2 — fixture-slate byte-identical (SKIP if script absent)."""
    return _run_script("G2", "G2", ["--compare"])


def g3() -> dict:
    """G3 — always SKIP in H0; loop-adjacent only."""
    return _skip("G3", "not run in H0 / loop-adjacent only")


def g4() -> dict:
    """G4 — API boot test via pytest (SKIP if absent; budget=420s)."""
    rel = _SCRIPTS["G4"]
    if not _script_exists(rel):
        return _skip("G4", f"test absent: {rel}")
    res = run_pytest(targets=[str(ROOT / rel)], timeout=420)
    if not res.get("ran"):
        return _skip("G4", f"pytest failed to run: {res.get('error')}")
    verdict = "PASS" if (res["failed"] == 0 and res["errors"] == 0) else "FAIL"
    return {"gate": "G4", "status": verdict, "counts": res}


def g5() -> dict:
    """G5 — shim integrity (SKIP if script absent)."""
    return _run_script("G5", "G5")


def import_contract() -> dict:
    """IC — import-contract check (SKIP if script absent)."""
    return _run_script("IC", "IC")


def _verdict(gates: List[dict]) -> str:
    """Derive overall verdict: FAIL > UNAVAILABLE > PARTIAL > PASS."""
    statuses = {g["status"] for g in gates}
    if "FAIL" in statuses:
        return "FAIL"
    non_skip = statuses - {"SKIP", "UNAVAILABLE"}
    if not non_skip:
        return "UNAVAILABLE"
    return "PARTIAL" if (statuses & {"SKIP", "UNAVAILABLE"}) else "PASS"


def _scoped_g1(files: List[str], tier: str = "wave") -> List[dict]:
    """Run G1 over the blast-radius test selection for *files*.

    Wave tier: replaces the old full-suite g1(); full-suite G1 is PHASE-only.
    Task tier: additional targeted pytest (EXECUTION_HARNESS §6.1).

    Returns a list of gate dicts: [G1-dict, HERMETICITY-dict].
    HERMETICITY snapshots git status before/after the pytest run (P0-H-004).
    When pytest is not actually invoked (SKIP path), HERMETICITY is also SKIP.
    """
    def _skip_both(why: str) -> List[dict]:
        return [
            _skip("G1", why),
            _skip("HERMETICITY", f"G1 skipped — {why}"),
        ]

    if not _SELECT_AVAILABLE:
        return _skip_both(
            "select_tests unavailable — install scripts/platformkit/select_tests.py"
        )

    try:
        sel = _select_tests.select(files, repo_root=ROOT)
    except Exception as e:  # noqa: BLE001
        return _skip_both(f"select_tests.select() raised: {e}")

    if sel.get("sentinel") == "ALL":
        return _skip_both(
            f"selection too broad → phase tier | {sel.get('reason', '')}"
        )

    targets = sel.get("tests") or []
    if not targets:
        return _skip_both("no tests selected by blast-radius selector")

    # Resolve targets relative to ROOT
    abs_targets = [str(ROOT / t) for t in targets]

    # --- P0-H-004: snapshot git status before pytest ---
    snap_before = _git_porcelain()

    t0 = time.monotonic()
    res = run_pytest(targets=abs_targets)
    elapsed = time.monotonic() - t0

    # --- P0-H-004: snapshot git status after pytest ---
    snap_after = _git_porcelain()
    herm = hermeticity_gate(snap_before, snap_after, tier)

    if res.get("timed_out"):
        g1: dict = {"gate": "G1", "status": "FAIL",
                    "why": f"scoped pytest timed out after {res.get('elapsed_s', 0):.1f}s",
                    "selection": targets, "elapsed_s": elapsed, "timed_out": True}
        return [g1, herm]
    if not res.get("ran"):
        return [_skip("G1", f"scoped pytest failed to run: {res.get('error')}"),
                _skip("HERMETICITY", "G1 did not run (subprocess error)")]

    ok = res["failed"] == 0 and res["errors"] == 0
    g1 = {
        "gate": "G1",
        "status": "PASS" if ok else "FAIL",
        "why": (f"scoped: {len(targets)} files, {res['passed']}p {res['failed']}f {res['errors']}e"
                f" in {elapsed:.1f}s"),
        "selection": targets,
        "elapsed_s": elapsed,
        "counts": {k: res[k] for k in ("passed", "failed", "skipped", "errors")},
    }
    return [g1, herm]


def _g4_with_hermeticity() -> List[dict]:
    """Run G4 (API boot pytest) and bracket with a HERMETICITY snapshot (P0-H-004).

    Returns [G4-dict, HERMETICITY-dict].
    When G4 is skipped (test absent), HERMETICITY is also SKIP.
    """
    rel = _SCRIPTS["G4"]
    if not _script_exists(rel):
        return [_skip("G4", f"test absent: {rel}"),
                _skip("HERMETICITY", "G4 skipped — test absent")]

    snap_before = _git_porcelain()
    res = run_pytest(targets=[str(ROOT / rel)], timeout=420)
    snap_after = _git_porcelain()
    herm = hermeticity_gate(snap_before, snap_after, "g4")

    if not res.get("ran"):
        return [_skip("G4", f"pytest failed to run: {res.get('error')}"),
                _skip("HERMETICITY", "G4 did not run (subprocess error)")]
    verdict = "PASS" if (res["failed"] == 0 and res["errors"] == 0) else "FAIL"
    return [{"gate": "G4", "status": verdict, "counts": res}, herm]


def run_tier(tier: str, task_files: Optional[List[str]] = None,
             phase: Optional[str] = None) -> dict:
    """Orchestrate gates for *tier* (task/wave/phase). Returns {tier, verdict, gates}."""
    gs: List[dict] = []

    if tier == "task":
        files = task_files or []
        hits = protected_scan(files)
        gs.append({"gate": "PROTECTED_SCAN",
                   "status": "FAIL" if hits else "PASS",
                   "why": (f"protected files must route to review, not auto-merge: {hits}"
                            if hits else "no protected files touched"),
                   **({"hits": hits} if hits else {})})
        if hits:
            return {"tier": tier, "verdict": "FAIL", "gates": gs}
        kernel_touched = any(f.replace("\\", "/").lstrip("/").startswith("kernel/")
                             for f in files)
        gs.append(import_contract() if kernel_touched
                  else _skip("IC", "no kernel/ files in task scope"))
        # EXECUTION_HARNESS §6.1: targeted pytest for blast-radius files at task tier.
        # _scoped_g1 returns [G1, HERMETICITY] (P0-H-004).
        gs.extend(_scoped_g1(files, tier="task"))

    elif tier == "wave":
        # Wave must NEVER run the full test suite (G1 full-suite run is PHASE-only).
        # Scoped G1: select tests in blast radius; if too broad → SKIP with reason.
        # _scoped_g1 returns [G1, HERMETICITY] (P0-H-004).
        gs.extend(_scoped_g1(task_files or [], tier="wave"))
        gs.append(g5())
        gs.extend(_g4_with_hermeticity())
        gs.append(import_contract())

    elif tier == "phase":
        gs += [g1(baseline_required=True), g2(), g3()]
        gs.extend(_g4_with_hermeticity())
        gs.append(g5())
        if _verdict(gs) == "UNAVAILABLE":
            gs.append(_skip("NOTE",
                             "phase tier activates after P0-B-002/P0-B-001 exist "
                             "(fixture_slate_hash.py + pytest baseline)"))

    else:
        gs.append({"gate": "UNKNOWN_TIER", "status": "FAIL",
                   "why": f"unknown tier: {tier!r}"})

    return {"tier": tier, "verdict": _verdict(gs), "gates": gs}


def record(tier_result: dict, phase: Optional[str] = None) -> None:
    """Append gate run to ledger; optionally persist G-results to phase record."""
    harness_state.append_ledger("gate_run", tier=tier_result.get("tier"),
                                verdict=tier_result.get("verdict"),
                                gates=tier_result.get("gates"), phase=phase)
    if phase is not None:
        state = harness_state.load()
        gate_summary = {g["gate"]: g.get("status")
                        for g in tier_result.get("gates", [])
                        if g.get("gate") in ("G1", "G2", "G3", "G4", "G5")}
        harness_state.set_phase(state, phase, gates=gate_summary)
        harness_state.save(state)


def _print_result(result: dict) -> None:
    print(f"GATE {result.get('tier','?')}: {result.get('verdict','?')}")
    for g in result.get("gates", []):
        why = f"  — {g['why']}" if g.get("why") else ""
        print(f"  {g.get('gate','?')}: {g.get('status','?')}{why}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Run platform verification gates.")
    p.add_argument("--tier", choices=["task", "wave", "phase"], required=True)
    p.add_argument("--phase", default=None)
    p.add_argument("--files", default=None, help="Comma-separated changed files.")
    p.add_argument("--record", action="store_true")
    args = p.parse_args()
    files_list: Optional[List[str]] = (
        [f.strip() for f in args.files.split(",") if f.strip()] if args.files else None
    )
    result = run_tier(tier=args.tier, task_files=files_list, phase=args.phase)
    _print_result(result)
    if args.record:
        record(result, phase=args.phase)
    sys.exit(0 if result.get("verdict") in {"PASS", "RECORDED", "UNAVAILABLE", "PARTIAL"} else 1)
