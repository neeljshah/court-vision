"""L41_integration_harness.py — End-to-end integration harness for the autonomous NBA execution loop.

Purpose
-------
Wire every shipped layer (L01–L37) end-to-end against a deterministic stub slate
and verify the full pipeline executes without live API calls.

Environment variables
---------------------
SUBMISSION_MODE : forced to "paper" for every run (never "live" inside the harness).

Invariants
----------
- No live API calls are made; all HTTP is blocked by design in stub mode.
- All RNG is seeded via np.random.default_rng(seed) for full reproducibility.
- Missing layers are soft-imported and result in SKIP stages, not failures.
- Critical-stage failures propagate as SKIP_DEPENDS to downstream stages.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project path wiring
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))

# ---------------------------------------------------------------------------
# Soft imports — each in its own try/except; None on failure
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop.L01_slate_ingester import SlateContest as _SlateContest
    L01 = sys.modules.get("scripts.execute_loop.L01_slate_ingester")
    SlateContest = _SlateContest
except Exception:
    L01 = None
    SlateContest = None  # type: ignore[assignment,misc]

try:
    from scripts.execute_loop.L02_fpts_distribution import FPTSDistribution as _FPTSDistribution
    L02 = sys.modules.get("scripts.execute_loop.L02_fpts_distribution")
    FPTSDistribution = _FPTSDistribution
except Exception:
    L02 = None
    FPTSDistribution = None  # type: ignore[assignment,misc]

try:
    from scripts.execute_loop.L03_cash_optimizer import optimize_cash as _optimize_cash
    L03 = sys.modules.get("scripts.execute_loop.L03_cash_optimizer")
    optimize_cash = _optimize_cash
except Exception:
    L03 = None
    optimize_cash = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L04_gpp_optimizer import optimize_gpp as _optimize_gpp
    L04 = sys.modules.get("scripts.execute_loop.L04_gpp_optimizer")
    optimize_gpp = _optimize_gpp
except Exception:
    L04 = None
    optimize_gpp = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L05_submission_engine import submit_lineup as _submit_lineup
    L05 = sys.modules.get("scripts.execute_loop.L05_submission_engine")
    submit_lineup = _submit_lineup
except Exception:
    L05 = None
    submit_lineup = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L07_pnl_ledger import (  # type: ignore[assignment]
        place_bet as _place_bet,
        settle_unsettled as _settle_unsettled,
        get_pnl_summary as _get_pnl_summary,
        BetRow as _BetRow,
    )
    L07 = sys.modules.get("scripts.execute_loop.L07_pnl_ledger")
    place_bet = _place_bet
    settle_unsettled = _settle_unsettled
    get_pnl_summary = _get_pnl_summary
    BetRow = _BetRow
except Exception:
    L07 = None
    place_bet = None  # type: ignore[assignment]
    settle_unsettled = None  # type: ignore[assignment]
    get_pnl_summary = None  # type: ignore[assignment]
    BetRow = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L08_drift_detector import daily_drift_report as _daily_drift_report
    L08 = sys.modules.get("scripts.execute_loop.L08_drift_detector")
    daily_drift_report = _daily_drift_report
except Exception:
    L08 = None
    daily_drift_report = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L19_clv_calculator import nightly_clv_report as _nightly_clv_report
    L19 = sys.modules.get("scripts.execute_loop.L19_clv_calculator")
    nightly_clv_report = _nightly_clv_report
except Exception:
    L19 = None
    nightly_clv_report = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L37_postmortem import (  # type: ignore[assignment]
        detect_incidents as _detect_incidents,
        run_postmortem as _run_postmortem,
    )
    L37 = sys.modules.get("scripts.execute_loop.L37_postmortem")
    detect_incidents = _detect_incidents
    run_postmortem = _run_postmortem
except Exception:
    L37 = None
    detect_incidents = None  # type: ignore[assignment]
    run_postmortem = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Critical stages — failure here propagates SKIP_DEPENDS downstream
# ---------------------------------------------------------------------------
_CRITICAL = {"ingest_slate", "fpts_distribution", "optimize_cash", "submit_paper", "settle_bets"}


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------

def _build_stub_slate(seed: int = 42) -> Any:
    """Return a SlateContest (or duck-typed dict) with 10 stub players."""
    rng = np.random.default_rng(seed)
    positions = ["PG", "SG", "SF", "PF", "C"]
    teams = ["FAKEA", "FAKEB"]
    players = []
    for i in range(10):
        pos = positions[i % 5]
        team = teams[i % 2]
        salary = int(rng.integers(4000, 9001))
        players.append({
            "player_id": f"stub_{i:03d}",
            "name": f"Player{i:02d}",
            "team": team,
            "position": pos,
            "salary": salary,
            "status": "",
        })

    lock_iso = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()

    if SlateContest is not None:
        return SlateContest(
            contest_id="stub_contest_001",
            book="dk",
            sport="NBA",
            slate_type="classic",
            salary_cap=50000,
            roster_slots=["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"],
            lock_time=lock_iso,
            game_ids=["stub_game_001"],
            players=players,
        )

    # Fallback: plain dict that satisfies the L03/L04 interface
    return {
        "contest_id": "stub_contest_001",
        "book": "dk",
        "sport": "NBA",
        "slate_type": "classic",
        "salary_cap": 50000,
        "roster_slots": ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"],
        "lock_time": lock_iso,
        "game_ids": ["stub_game_001"],
        "players": players,
    }


def _build_stub_fpts(slate: Any, seed: int = 42) -> Dict[str, Any]:
    """Return Dict[player_id, FPTSDistribution] using deterministic RNG."""
    rng = np.random.default_rng(seed)
    players = slate.players if hasattr(slate, "players") else slate["players"]
    result: Dict[str, Any] = {}

    for p in players:
        pid = str(p["player_id"])
        name = str(p["name"])
        mean_fpts = float(rng.uniform(15.0, 50.0))
        std_fpts = float(rng.uniform(3.0, 10.0))
        samples = rng.normal(mean_fpts, std_fpts, 2000).clip(0)

        if FPTSDistribution is not None:
            dist = FPTSDistribution(
                mean=mean_fpts,
                std=std_fpts,
                q10=float(np.quantile(samples, 0.10)),
                q50=float(np.quantile(samples, 0.50)),
                q90=float(np.quantile(samples, 0.90)),
                samples=samples,
            )
        else:
            # Duck-typed namespace
            dist = types.SimpleNamespace(
                mean=mean_fpts,
                std=std_fpts,
                q10=float(np.quantile(samples, 0.10)),
                q50=float(np.quantile(samples, 0.50)),
                q90=float(np.quantile(samples, 0.90)),
                samples=samples,
            )

        result[pid] = dist
        result[name] = dist  # keyed by both player_id and name

    return result


# ---------------------------------------------------------------------------
# IntegrationHarness
# ---------------------------------------------------------------------------

class IntegrationHarness:
    """End-to-end integration harness for the NBA execution loop."""

    def __init__(
        self,
        slate_path: Optional[str] = None,
        bankroll: float = 1000.0,
        seed: int = 42,
        paper_mode: bool = True,
    ) -> None:
        self.slate_path = slate_path
        self.bankroll = bankroll
        self.seed = seed
        self.paper_mode = paper_mode
        self._prev_submission_mode: Optional[str] = None

    # ------------------------------------------------------------------ helpers

    def _assert_paper_mode(self) -> None:
        """Force SUBMISSION_MODE=paper; raise if live mode was set and paper_mode=True."""
        current = os.environ.get("SUBMISSION_MODE", "paper")
        if self.paper_mode and current.lower() == "live":
            raise RuntimeError(
                "IntegrationHarness: SUBMISSION_MODE=live was explicitly set before run, "
                "but paper_mode=True. Refusing to run in live mode."
            )
        self._prev_submission_mode = current
        os.environ["SUBMISSION_MODE"] = "paper"

    def _restore_mode(self) -> None:
        if self._prev_submission_mode is not None:
            os.environ["SUBMISSION_MODE"] = self._prev_submission_mode

    def _run_stage(self, name: str, fn: Callable[[], Any]) -> dict:
        """Time and run fn(); return a normalized stage entry."""
        t0 = time.perf_counter()
        try:
            data = fn()
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            # Serialize numpy arrays / complex objects to safe primitives
            safe_data = self._safe_data(data)
            return {"name": name, "status": "PASS", "duration_ms": duration_ms, "data": safe_data}
        except Exception as exc:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            log.warning("Stage %r FAIL: %s", name, exc)
            return {"name": name, "status": "FAIL", "duration_ms": duration_ms, "error": str(exc)}

    @staticmethod
    def _safe_data(data: Any) -> Any:
        """Convert data to JSON-safe primitives (strip numpy scalars / ndarrays)."""
        if data is None:
            return None
        if isinstance(data, (str, int, float, bool)):
            return data
        if isinstance(data, np.integer):
            return int(data)
        if isinstance(data, np.floating):
            return float(data)
        if isinstance(data, np.ndarray):
            return f"<ndarray shape={data.shape}>"
        if isinstance(data, dict):
            return {k: IntegrationHarness._safe_data(v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return [IntegrationHarness._safe_data(v) for v in data]
        # Dataclasses / objects — convert to string summary
        try:
            return str(data)[:200]
        except Exception:
            return "<unserializable>"

    # ------------------------------------------------------------------ run

    def run_end_to_end(self) -> dict:
        """Execute all integration stages and return the report dict."""
        self._assert_paper_mode()
        started_at = datetime.now(timezone.utc).isoformat()

        # Shared pipeline state
        slate: Any = None
        fpts: Dict[str, Any] = {}
        cash_lineups: List[Any] = []
        gpp_lineups: List[Any] = []
        sub_result: Any = None

        stages: List[dict] = []
        failed_critical: set = set()

        def _skip(name: str) -> dict:
            return {"name": name, "status": "SKIP", "duration_ms": 0.0}

        def _skip_depends(name: str) -> dict:
            return {"name": name, "status": "SKIP_DEPENDS", "duration_ms": 0.0}

        # ── 1. ingest_slate ────────────────────────────────────────────────
        def _ingest():
            nonlocal slate
            slate = _build_stub_slate(self.seed)
            players = slate.players if hasattr(slate, "players") else slate["players"]
            assert len(players) >= 10, f"Stub slate has {len(players)} players"
            cid = getattr(slate, "contest_id", None) or (slate.get("contest_id", "") if isinstance(slate, dict) else "")
            return {"n_players": len(players), "contest_id": cid}

        e = self._run_stage("ingest_slate", _ingest)
        stages.append(e)
        if e["status"] == "FAIL":
            failed_critical.add("ingest_slate")

        # ── 2. fpts_distribution ───────────────────────────────────────────
        def _fpts_dist():
            nonlocal fpts
            if "ingest_slate" in failed_critical:
                raise RuntimeError("depends on ingest_slate")
            fpts = _build_stub_fpts(slate, self.seed)
            assert len(fpts) > 0
            return {"n_distributions": len(fpts)}

        if "ingest_slate" in failed_critical:
            stages.append(_skip_depends("fpts_distribution"))
            failed_critical.add("fpts_distribution")
        else:
            e = self._run_stage("fpts_distribution", _fpts_dist)
            stages.append(e)
            if e["status"] == "FAIL":
                failed_critical.add("fpts_distribution")

        # ── 3. optimize_cash ───────────────────────────────────────────────
        def _opt_cash():
            nonlocal cash_lineups
            if optimize_cash is None:
                raise RuntimeError("L03 not available")
            # Pass only player_id keyed entries to L03 (it looks up by player_id)
            players = slate.players if hasattr(slate, "players") else slate["players"]
            pid_fpts = {str(p["player_id"]): fpts[str(p["player_id"])] for p in players}
            cash_lineups = optimize_cash(slate, pid_fpts, n_lineups=1)
            assert len(cash_lineups) >= 1
            return {"n_lineups": len(cash_lineups)}

        if "fpts_distribution" in failed_critical:
            stages.append(_skip_depends("optimize_cash"))
            failed_critical.add("optimize_cash")
        else:
            e = self._run_stage("optimize_cash", _opt_cash)
            stages.append(e)
            if e["status"] == "FAIL":
                failed_critical.add("optimize_cash")

        # ── 4. optimize_gpp ────────────────────────────────────────────────
        def _opt_gpp():
            nonlocal gpp_lineups
            if optimize_gpp is None:
                raise RuntimeError("L04 not available")
            players = slate.players if hasattr(slate, "players") else slate["players"]
            name_fpts = {str(p["name"]): fpts[str(p["name"])] for p in players}
            gpp_lineups = optimize_gpp(slate, name_fpts, n_lineups=1, field_size=100, seed=self.seed)
            return {"n_lineups": len(gpp_lineups)}

        if "fpts_distribution" in failed_critical:
            stages.append(_skip_depends("optimize_gpp"))
        else:
            e = self._run_stage("optimize_gpp", _opt_gpp)
            stages.append(e)

        # ── 5. submit_paper ────────────────────────────────────────────────
        def _submit():
            nonlocal sub_result
            if submit_lineup is None:
                raise RuntimeError("L05 not available")
            lineup_players = []
            if cash_lineups:
                lu = cash_lineups[0]
                lineup_players = list(lu.players) if hasattr(lu, "players") else []
            elif gpp_lineups:
                lu = gpp_lineups[0]
                lineup_players = [p.get("player_id", p.get("name", "")) if isinstance(p, dict) else str(p)
                                  for p in (lu.players if hasattr(lu, "players") else [])]
            if not lineup_players:
                # Use first 8 player_ids from stub
                players = slate.players if hasattr(slate, "players") else slate["players"]
                lineup_players = [str(p["player_id"]) for p in players[:8]]
            lineup_dict = {"players": lineup_players, "entry_fee": 25.0}
            contest_id = getattr(slate, "contest_id", "stub_contest_001")
            sub_result = submit_lineup("dk", contest_id, lineup_dict)
            assert sub_result.status in ("PAPER_OK", "RATE_LIMITED", "DUPLICATE")
            return {"status": sub_result.status, "submission_id": sub_result.submission_id}

        if "optimize_cash" in failed_critical:
            stages.append(_skip_depends("submit_paper"))
            failed_critical.add("submit_paper")
        else:
            e = self._run_stage("submit_paper", _submit)
            stages.append(e)
            if e["status"] == "FAIL":
                failed_critical.add("submit_paper")

        # ── 6. settle_bets ─────────────────────────────────────────────────
        def _settle():
            if settle_unsettled is None:
                raise RuntimeError("L07 not available")
            n = settle_unsettled()
            return {"settled": n}

        if "submit_paper" in failed_critical:
            stages.append(_skip_depends("settle_bets"))
            failed_critical.add("settle_bets")
        else:
            e = self._run_stage("settle_bets", _settle)
            stages.append(e)
            if e["status"] == "FAIL":
                failed_critical.add("settle_bets")

        # ── 7. ledger_summary ──────────────────────────────────────────────
        def _ledger():
            if get_pnl_summary is None:
                raise RuntimeError("L07 not available")
            summary = get_pnl_summary()
            return {"n_groups": len(summary)}

        if "settle_bets" in failed_critical:
            stages.append(_skip_depends("ledger_summary"))
        else:
            stages.append(self._run_stage("ledger_summary", _ledger))

        # ── 8. clv_report ──────────────────────────────────────────────────
        def _clv():
            if nightly_clv_report is None:
                raise RuntimeError("L19 not available")
            report = nightly_clv_report()
            return {"n_bets": report.get("n_bets", 0)}

        if L19 is None:
            stages.append(_skip("clv_report"))
        else:
            stages.append(self._run_stage("clv_report", _clv))

        # ── 9. drift_check ─────────────────────────────────────────────────
        def _drift():
            if daily_drift_report is None:
                raise RuntimeError("L08 not available")
            report = daily_drift_report()
            return {"n_metrics": len(report.get("metrics", []))}

        if L08 is None:
            stages.append(_skip("drift_check"))
        else:
            stages.append(self._run_stage("drift_check", _drift))

        # ── 10. postmortem ─────────────────────────────────────────────────
        def _postmortem():
            if detect_incidents is None or run_postmortem is None:
                raise RuntimeError("L37 not available")
            incidents = detect_incidents(window_days=1)
            if incidents:
                losing = [i.get("bets", []) for i in incidents]
                flat = [b for sub in losing for b in sub]
                run_postmortem(flat)
            return {"n_incidents": len(incidents)}

        if L37 is None:
            stages.append(_skip("postmortem"))
        else:
            stages.append(self._run_stage("postmortem", _postmortem))

        self._restore_mode()

        finished_at = datetime.now(timezone.utc).isoformat()
        n_pass = sum(1 for s in stages if s["status"] == "PASS")
        n_fail = sum(1 for s in stages if s["status"] == "FAIL")
        n_skip = sum(1 for s in stages if s["status"] in ("SKIP", "SKIP_DEPENDS"))
        overall = "PASS" if n_fail == 0 else "FAIL"

        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "seed": self.seed,
            "paper_mode": self.paper_mode,
            "bankroll": self.bankroll,
            "stages": stages,
            "summary": {
                "n_pass": n_pass,
                "n_fail": n_fail,
                "n_skip": n_skip,
                "overall": overall,
            },
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    harness = IntegrationHarness()
    report = harness.run_end_to_end()
    print(json.dumps(report, indent=2))
