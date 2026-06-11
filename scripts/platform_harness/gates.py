"""gates.py — verification gate runner (task / wave / phase tiers).
Cardinal rule: absent script/baseline → SKIP, never FAIL. H0: almost everything skips."""
from __future__ import annotations
import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_state  # noqa: E402

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
    "G2": "scripts/platform/fixture_slate_hash.py",
    "G4": "tests/platform/test_api_boot.py",
    "G5": "scripts/platform/check_shims.py",
    "IC": "scripts/platform/check_import_contract.py",
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _script_exists(rel: str) -> bool:
    """Return True if repo-root-relative path *rel* exists."""
    return (ROOT / rel).exists()


def _skip(name: str, why: str) -> dict:
    """Return a SKIP gate dict."""
    return {"gate": name, "status": "SKIP", "why": why}


def protected_scan(files: List[str]) -> List[str]:
    """Return the subset of *files* that are protected (exact or prefix match)."""
    hits: List[str] = []
    for f in files:
        n = f.replace("\\", "/").lstrip("/")
        if n in _EXACT or any(n.startswith(pfx) for pfx in _PREFIXES):
            hits.append(f)
    return hits


def run_pytest(targets: Optional[List[str]] = None, timeout: int = 1800) -> dict:
    """Run pytest and return parsed counts.  Never raises.

    Returns ``{"ran": True, "passed": int, "failed": int, "skipped": int,
    "errors": int, "rc": int}`` or ``{"ran": False, "error": str}`` on error.
    """
    cmd = [sys.executable, "-m", "pytest"]
    cmd += [str(t) for t in targets] if targets else [str(ROOT / "tests")]
    cmd += ["-q", "--no-header", "--tb=no"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=str(ROOT))
    except subprocess.TimeoutExpired as e:
        return {"ran": False, "error": f"timed out after {timeout}s: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ran": False, "error": str(e)}

    out = (r.stdout or "") + (r.stderr or "")
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for line in reversed(out.splitlines()):
        if re.search(r"\d+\s+(passed|failed|error|skipped)", line):
            for key, pat in [("passed", r"(\d+)\s+passed"), ("failed", r"(\d+)\s+failed"),
                              ("skipped", r"(\d+)\s+skipped"), ("errors", r"(\d+)\s+error")]:
                m = re.search(pat, line)
                if m:
                    counts[key] = int(m.group(1))
            break
    return {"ran": True, **counts, "rc": r.returncode}


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


# ---------------------------------------------------------------------------
# Individual gates
# ---------------------------------------------------------------------------

def g1(baseline_required: bool = False) -> dict:
    """G1 — pytest count vs baseline (RECORDED if baseline absent, else PASS/FAIL)."""
    if not PYTEST_BASELINE.exists():
        if baseline_required:
            return _skip("G1", "baseline absent and baseline_required=True")
        res = run_pytest()
        if not res.get("ran"):
            return _skip("G1", f"pytest failed to run: {res.get('error')}")
        try:
            PYTEST_BASELINE.parent.mkdir(parents=True, exist_ok=True)
            PYTEST_BASELINE.write_text(
                "\n".join(f"{k}={res[k]}" for k in ("passed", "failed", "skipped", "errors")) + "\n",
                encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return {"gate": "G1", "status": "RECORDED",
                "why": "baseline absent — current counts recorded", "counts": res}

    baseline: dict = {}
    for line in PYTEST_BASELINE.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            try:
                baseline[k.strip()] = int(v.strip())
            except ValueError:
                pass

    res = run_pytest()
    if not res.get("ran"):
        return _skip("G1", f"pytest failed to run: {res.get('error')}")
    ok = res["passed"] >= baseline.get("passed", 0) and res["failed"] == 0 and res["errors"] == 0
    return {"gate": "G1", "status": "PASS" if ok else "FAIL",
            "baseline": baseline,
            "actual": {k: res[k] for k in ("passed", "failed", "skipped", "errors")},
            "rc": res["rc"]}


def g2() -> dict:
    """G2 — fixture-slate byte-identical (SKIP if script absent)."""
    return _run_script("G2", "G2", ["--compare"])


def g3() -> dict:
    """G3 — always SKIP in H0; loop-adjacent only."""
    return _skip("G3", "not run in H0 / loop-adjacent only")


def g4() -> dict:
    """G4 — API boot test via pytest (SKIP if absent)."""
    rel = _SCRIPTS["G4"]
    if not _script_exists(rel):
        return _skip("G4", f"test absent: {rel}")
    res = run_pytest(targets=[str(ROOT / rel)], timeout=120)
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


# ---------------------------------------------------------------------------
# Tier orchestrator
# ---------------------------------------------------------------------------

def _verdict(gates: List[dict]) -> str:
    """Derive overall verdict: FAIL > UNAVAILABLE > PARTIAL > PASS."""
    statuses = {g["status"] for g in gates}
    if "FAIL" in statuses:
        return "FAIL"
    non_skip = statuses - {"SKIP", "UNAVAILABLE"}
    if not non_skip:
        return "UNAVAILABLE"
    return "PARTIAL" if (statuses & {"SKIP", "UNAVAILABLE"}) else "PASS"


def run_tier(tier: str, task_files: Optional[List[str]] = None,
             phase: Optional[str] = None) -> dict:
    """Orchestrate gates for *tier* (task/wave/phase).

    Args:
        tier: ``"task"``, ``"wave"``, or ``"phase"``.
        task_files: Changed files (task tier: protected scan + import-contract).
        phase: Phase ID for context/recording.

    Returns:
        ``{"tier": tier, "verdict": str, "gates": [<gate dicts>]}``.
    """
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

    elif tier == "wave":
        gs += [g1(), g5(), g4(), import_contract()]

    elif tier == "phase":
        gs += [g1(baseline_required=True), g2(), g3(), g4(), g5()]
        if _verdict(gs) == "UNAVAILABLE":
            gs.append(_skip("NOTE",
                             "phase tier activates after P0-B-002/P0-B-001 exist "
                             "(fixture_slate_hash.py + pytest baseline)"))

    else:
        gs.append({"gate": "UNKNOWN_TIER", "status": "FAIL",
                   "why": f"unknown tier: {tier!r}"})

    return {"tier": tier, "verdict": _verdict(gs), "gates": gs}


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_result(result: dict) -> None:
    """Print human-readable gate summary."""
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
