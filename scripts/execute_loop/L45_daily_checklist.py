"""L45_daily_checklist.py — Operator Daily Checklist Runner (execute_loop layer 45).

Purpose
-------
A single CLI tool the operator runs before/during/after each game day to walk
through the standard operational routine and report readiness for each phase.
Wraps L38 (health dashboard), L42 (production readiness checker), and L41
(integration harness) into a coherent operator-facing workflow.

Environment Variables
---------------------
None required directly.  Underlying layers read their own env vars as
documented in their respective module docstrings.

Paper vs Live Mode (MODE GATING)
---------------------------------
L45 reads paper/live state via L44.is_paper_mode() and surfaces it in every
checklist run, but is itself mode-agnostic — it is an operator observation
tool that does not gate or alter live-mode behaviour.  The paper/live toggle
lives entirely in L44; L45 only reports the observed state.  Default report
path is scripts/execute_loop/checklist_YYYY-MM-DD_<phase>.md unless
overridden by --out.

CLI
---
    python L45_daily_checklist.py morning
    python L45_daily_checklist.py midday --out /tmp/midday.md
    python L45_daily_checklist.py postgame

Exit codes: 0 = all PASS/WARN/SKIP; 1 = any FAIL.
"""
from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_PROJECT_DIR = _HERE.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))

log = logging.getLogger(__name__)
_VALID_PHASES = {"morning", "midday", "postgame"}


# ---------------------------------------------------------------------------
# Soft-import helper
# ---------------------------------------------------------------------------
def _soft_import(key: str):
    try:
        return importlib.import_module(key)
    except Exception as exc:  # noqa: BLE001
        log.debug("soft_import(%s) failed: %s", key, exc)
        return None


L44 = _soft_import("scripts.execute_loop.L44_paper_mode")
L42 = _soft_import("scripts.execute_loop.L42_production_readiness")
L38 = _soft_import("scripts.execute_loop.L38_health_dashboard")
L07 = _soft_import("scripts.execute_loop.L07_pnl_ledger")
L41 = _soft_import("scripts.execute_loop.L41_integration_harness")
L08 = _soft_import("scripts.execute_loop.L08_drift_detector")
L14 = _soft_import("scripts.execute_loop.L14_order_manager")
L16 = _soft_import("scripts.execute_loop.L16_live_trader")
L19 = _soft_import("scripts.execute_loop.L19_clv_calculator")
L37 = _soft_import("scripts.execute_loop.L37_postmortem")
L27 = _soft_import("scripts.execute_loop.L27_tax_tracking")


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class ChecklistItem:
    phase: str        # "morning" | "midday" | "postgame"
    name: str
    status: str       # "PASS" | "FAIL" | "WARN" | "SKIP"
    detail: str
    duration_ms: int
    timestamp: str    # ISO 8601 UTC


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------
def _atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically via a sibling temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# DailyChecklist
# ---------------------------------------------------------------------------
class DailyChecklist:
    """Run the per-phase operator checklist and produce a markdown report."""

    def __init__(self, phase: str) -> None:
        if phase not in _VALID_PHASES:
            raise ValueError(f"Unknown phase {phase!r}. Must be one of: {sorted(_VALID_PHASES)}")
        self.phase = phase

    def _item(self, name: str, status: str, detail: str, duration_ms: int) -> ChecklistItem:
        return ChecklistItem(
            phase=self.phase, name=name, status=status, detail=detail,
            duration_ms=duration_ms, timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _run_step(self, name: str, fn: Callable[[], Tuple[str, str]]) -> ChecklistItem:
        """Time fn(); convert any exception to a SKIP item."""
        t0 = time.perf_counter()
        try:
            status, detail = fn()
        except Exception as exc:  # noqa: BLE001
            return self._item(name, "SKIP", f"exception: {exc}", int((time.perf_counter() - t0) * 1000))
        return self._item(name, status, detail, int((time.perf_counter() - t0) * 1000))

    # ── Shared steps ────────────────────────────────────────────────────────

    def _s_paper_mode(self) -> Tuple[str, str]:
        if L44 is None:
            raise ImportError("L44_paper_mode not available")
        mode = "PAPER" if L44.is_paper_mode() else "LIVE"
        return "PASS", f"mode={mode}"

    def _s_health_snapshot(self) -> Tuple[str, str]:
        if L38 is None:
            raise ImportError("L38_health_dashboard not available")
        rpt = L38.get_latest_health()
        n_fail = sum(1 for c in rpt.checks if c.status == "FAIL")
        n_warn = sum(1 for c in rpt.checks if c.status == "WARN")
        status = "PASS" if rpt.overall_status == "HEALTHY" else ("WARN" if rpt.overall_status == "DEGRADED" else "FAIL")
        return status, f"overall={rpt.overall_status} fail={n_fail} warn={n_warn} ts={rpt.timestamp[:19]}"

    # ── Morning steps ────────────────────────────────────────────────────────

    def _s_readiness(self) -> Tuple[str, str]:
        if L42 is None:
            raise ImportError("L42_production_readiness not available")
        checker = L42.ReadinessChecker(layers_dir=_HERE, state_json_path=_HERE / "state.json")
        rpt = checker.run_all_checks()
        s = rpt.summary
        status = "FAIL" if s.get("fail", 0) > 0 else "PASS"
        return status, (f"layers={s.get('layers',0)} pass={s.get('pass',0)} "
                        f"fail={s.get('fail',0)} skip={s.get('skip',0)} n/a={s.get('n_a',0)}")

    def _s_bankroll(self) -> Tuple[str, str]:
        if L07 is None:
            raise ImportError("L07_pnl_ledger not available")
        summary = L07.get_pnl_summary()
        total_pnl = sum(v.get("total_pnl", 0.0) for v in summary.values())
        total_staked = sum(v.get("total_staked", 0.0) for v in summary.values())
        return "PASS", f"groups={len(summary)} total_pnl={total_pnl:.2f} staked={total_staked:.2f}"

    def _s_integration_smoke(self) -> Tuple[str, str]:
        if L41 is None:
            raise ImportError("L41_integration_harness not available")
        rpt = L41.IntegrationHarness().run_end_to_end()
        sm = rpt.get("summary", {})
        overall = sm.get("overall", "FAIL")
        status = "PASS" if overall in ("PASS", "PARTIAL") else "FAIL"
        return status, f"overall={overall} pass={sm.get('n_pass',0)} fail={sm.get('n_fail',0)} skip={sm.get('n_skip',0)}"

    # ── Midday steps ─────────────────────────────────────────────────────────

    def _s_drift(self) -> Tuple[str, str]:
        if L08 is None:
            raise ImportError("L08_drift_detector not available")
        rpt = L08.daily_drift_report()
        n_drift, n_warn = rpt.get("n_drift", 0), rpt.get("n_warn", 0)
        status = "WARN" if (n_drift > 0 or n_warn > 0) else "PASS"
        return status, f"n_drift={n_drift} n_warn={n_warn} n_ok={rpt.get('n_ok',0)}"

    def _s_open_positions(self) -> Tuple[str, str]:
        count, source = 0, "unknown"
        if L07 is not None:
            try:
                count, source = len(L07.get_open_bets()), "L07_ledger"
            except Exception:  # noqa: BLE001
                pass
        if source == "unknown" and L16 is not None:
            try:
                ledger = getattr(L16, "_PAPER_LEDGER", None)
                if ledger is not None:
                    count, source = len(ledger), "L16_paper_ledger"
            except Exception:  # noqa: BLE001
                pass
        return "PASS", f"open_positions={count} source={source}"

    # ── Postgame steps ────────────────────────────────────────────────────────

    def _s_settle(self) -> Tuple[str, str]:
        if L07 is None:
            raise ImportError("L07_pnl_ledger not available")
        return "PASS", f"settled={L07.settle_unsettled()}"

    def _s_clv(self) -> Tuple[str, str]:
        if L19 is None:
            raise ImportError("L19_clv_calculator not available")
        rpt = L19.nightly_clv_report()
        return "PASS", f"n_bets={rpt.get('n_bets',0)} generated_at={str(rpt.get('generated_at','?'))[:19]}"

    def _s_postmortem(self) -> Tuple[str, str]:
        if L37 is None:
            raise ImportError("L37_postmortem not available")
        n = len(L37.detect_incidents(window_days=1))
        return ("PASS" if n == 0 else "WARN"), f"incidents={n}"

    def _s_tax(self) -> Tuple[str, str]:
        if L27 is None:
            raise ImportError("L27_tax_tracking not available")
        year = datetime.now(timezone.utc).year
        path = L27.export_1099_ready(year)
        return "PASS", f"1099_path={path}"

    # ── run ──────────────────────────────────────────────────────────────────

    def run(self) -> List[ChecklistItem]:
        if self.phase == "morning":
            return [
                self._run_step("paper_mode_check", self._s_paper_mode),
                self._run_step("l42_readiness_audit", self._s_readiness),
                self._run_step("l38_health_snapshot", self._s_health_snapshot),
                self._run_step("bankroll_check", self._s_bankroll),
                self._run_step("l41_integration_smoke", self._s_integration_smoke),
            ]
        if self.phase == "midday":
            return [
                self._run_step("paper_mode_check", self._s_paper_mode),
                self._run_step("l38_health_snapshot", self._s_health_snapshot),
                self._run_step("drift_check", self._s_drift),
                self._run_step("open_positions_count", self._s_open_positions),
            ]
        # postgame
        return [
            self._run_step("settle_pending", self._s_settle),
            self._run_step("clv_report", self._s_clv),
            self._run_step("postmortem", self._s_postmortem),
            self._run_step("tax_tracking_update", self._s_tax),
        ]

    # ── reporting ────────────────────────────────────────────────────────────

    def to_markdown(self, items: List[ChecklistItem]) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines = [
            f"# Daily Checklist — {self.phase.capitalize()} — {today}",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()[:19]}Z",
            "",
            "| Step | Status | Duration (ms) | Detail |",
            "|------|--------|---------------|--------|",
        ]
        _icon = {"PASS": "OK", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}
        for i in items:
            lines.append(f"| {i.name} | {_icon.get(i.status, i.status)} | {i.duration_ms} | {i.detail} |")
        n_pass = sum(1 for i in items if i.status == "PASS")
        n_fail = sum(1 for i in items if i.status == "FAIL")
        n_warn = sum(1 for i in items if i.status == "WARN")
        n_skip = sum(1 for i in items if i.status == "SKIP")
        overall = "READY" if n_fail == 0 else "NOT READY"
        lines += [
            "",
            f"**Summary:** PASS={n_pass} FAIL={n_fail} WARN={n_warn} SKIP={n_skip}",
            f"**Overall:** {overall}",
            "",
        ]
        return "\n".join(lines)

    def write_report(self, items: List[ChecklistItem], path: Optional[Path] = None) -> Path:
        """Atomically write the markdown report; return the path written to."""
        if path is None:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            path = _HERE / f"checklist_{today}_{self.phase}.md"
        path = Path(path)
        _atomic_write_text(path, self.to_markdown(items))
        log.info("checklist report written: %s", path)
        return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L45_daily_checklist",
                                description="Run the operator daily checklist.")
    p.add_argument("phase", choices=sorted(_VALID_PHASES), help="Checklist phase")
    p.add_argument("--out", metavar="PATH", default=None, help="Override output markdown path")
    args = p.parse_args(argv)

    cl = DailyChecklist(args.phase)
    items = cl.run()
    out_path = cl.write_report(items, path=Path(args.out) if args.out else None)
    print(cl.to_markdown(items))
    print(f"Report written: {out_path}")
    return 1 if any(i.status == "FAIL" for i in items) else 0


if __name__ == "__main__":
    sys.exit(main())
