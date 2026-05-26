"""L41_integration_harness.py — End-to-end integration harness for the NBA execution loop.

Wires L01–L41 layers against a deterministic stub slate; no live API calls.
SUBMISSION_MODE forced to "paper". Missing layers → SKIP. Critical failures → SKIP_DEPENDS.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)

# Project path wiring
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))

# Soft-imports (L01–L41): missing layers → None; no live imports, no HTTP
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

try:
    from scripts.execute_loop.L09_kalshi_client import get_orderbook as kalshi_get_orderbook
    L09 = sys.modules.get("scripts.execute_loop.L09_kalshi_client")
except Exception:
    L09 = None; kalshi_get_orderbook = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L10_polymarket_client import get_orderbook as poly_get_orderbook
    L10 = sys.modules.get("scripts.execute_loop.L10_polymarket_client")
except Exception:
    L10 = None; poly_get_orderbook = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L13_cross_exchange_ev import find_ev_opportunities
    L13 = sys.modules.get("scripts.execute_loop.L13_cross_exchange_ev")
except Exception:
    L13 = None; find_ev_opportunities = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L14_order_manager import sync_all_exchanges
    L14 = sys.modules.get("scripts.execute_loop.L14_order_manager")
except Exception:
    L14 = None; sync_all_exchanges = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L18_bankroll_manager import kelly_fraction
    L18 = sys.modules.get("scripts.execute_loop.L18_bankroll_manager")
except Exception:
    L18 = None; kelly_fraction = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L33_sell_to_close import evaluate_close_decision
    L33 = sys.modules.get("scripts.execute_loop.L33_sell_to_close")
except Exception:
    L33 = None; evaluate_close_decision = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L36_edge_erosion import daily_edge_report
    L36 = sys.modules.get("scripts.execute_loop.L36_edge_erosion")
except Exception:
    L36 = None; daily_edge_report = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L15_market_making import compute_mm_quote as _compute_mm_quote
    L15 = sys.modules.get("scripts.execute_loop.L15_market_making")
    compute_mm_quote = _compute_mm_quote
except Exception:
    L15 = None; compute_mm_quote = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L17_hedge_calculator import recommend_hedge as _recommend_hedge
    L17 = sys.modules.get("scripts.execute_loop.L17_hedge_calculator")
    recommend_hedge = _recommend_hedge
except Exception:
    L17 = None; recommend_hedge = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L20_injury_feed import fetch_nba_official_injuries as _fetch_nba_official_injuries
    L20 = sys.modules.get("scripts.execute_loop.L20_injury_feed")
    fetch_nba_official_injuries = _fetch_nba_official_injuries
except Exception:
    L20 = None; fetch_nba_official_injuries = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L21_lineup_watcher import fetch_confirmed_lineups as _fetch_confirmed_lineups
    L21 = sys.modules.get("scripts.execute_loop.L21_lineup_watcher")
    fetch_confirmed_lineups = _fetch_confirmed_lineups
except Exception:
    L21 = None; fetch_confirmed_lineups = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L25_ab_shadow import list_active_shadows as _list_active_shadows
    L25 = sys.modules.get("scripts.execute_loop.L25_ab_shadow")
    list_active_shadows = _list_active_shadows
except Exception:
    L25 = None; list_active_shadows = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L26_account_hygiene import daily_hygiene_report as _daily_hygiene_report
    L26 = sys.modules.get("scripts.execute_loop.L26_account_hygiene")
    daily_hygiene_report = _daily_hygiene_report
except Exception:
    L26 = None; daily_hygiene_report = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L34_variance_budgeter import compute_daily_allocation as _compute_daily_allocation
    L34 = sys.modules.get("scripts.execute_loop.L34_variance_budgeter")
    compute_daily_allocation = _compute_daily_allocation
except Exception:
    L34 = None; compute_daily_allocation = None  # type: ignore[assignment]

try:
    from scripts.execute_loop.L40_multi_model_dispatcher import get_routing as _get_routing
    L40 = sys.modules.get("scripts.execute_loop.L40_multi_model_dispatcher")
    get_routing = _get_routing
except Exception:
    L40 = None; get_routing = None  # type: ignore[assignment]

try:
    from scripts.execute_loop import L46_event_bus as _L46_MOD
except Exception:
    _L46_MOD = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
_CRITICAL = {"ingest_slate", "fpts_distribution", "optimize_cash", "submit_paper", "settle_bets"}

# Events that MUST be captured during a full run for verify_event_publication to PASS.
# "fill.received" or "order.filled" counts as one required slot.
_REQUIRED_EVENTS = frozenset({"bet.settled", "kelly.sized"})
_FILL_EVENTS = frozenset({"fill.received", "order.filled"})   # at least one required
_OPTIONAL_EVENTS = frozenset({"drift.detected", "incident.opened", "incident.classified"})


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------

def _build_stub_slate(seed: int = 42) -> Any:
    """Return a SlateContest (or duck-typed dict) with 10 stub players."""
    rng = np.random.default_rng(seed)
    pos_cycle = ["PG", "SG", "SF", "PF", "C"]
    players = [
        {"player_id": f"stub_{i:03d}", "name": f"Player{i:02d}",
         "team": ["FAKEA", "FAKEB"][i % 2], "position": pos_cycle[i % 5],
         "salary": int(rng.integers(4000, 9001)), "status": ""}
        for i in range(10)
    ]
    kw = dict(
        contest_id="stub_contest_001", book="dk", sport="NBA", slate_type="classic",
        salary_cap=50000, roster_slots=["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"],
        lock_time=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        game_ids=["stub_game_001"], players=players,
    )
    return SlateContest(**kw) if SlateContest is not None else kw


def _build_stub_fpts(slate: Any, seed: int = 42) -> Dict[str, Any]:
    """Return Dict[player_id, FPTSDistribution] (also keyed by name) via deterministic RNG."""
    rng = np.random.default_rng(seed)
    players = slate.players if hasattr(slate, "players") else slate["players"]
    result: Dict[str, Any] = {}
    _cls = FPTSDistribution if FPTSDistribution is not None else types.SimpleNamespace
    for p in players:
        mu = float(rng.uniform(15.0, 50.0))
        sigma = float(rng.uniform(3.0, 10.0))
        samp = rng.normal(mu, sigma, 2000).clip(0)
        dist = _cls(mean=mu, std=sigma,
                    q10=float(np.quantile(samp, 0.10)),
                    q50=float(np.quantile(samp, 0.50)),
                    q90=float(np.quantile(samp, 0.90)),
                    samples=samp)
        result[str(p["player_id"])] = dist
        result[str(p["name"])] = dist
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
        isolated_dir: Optional[Path] = None,
    ) -> None:
        self.slate_path = slate_path
        self.bankroll = bankroll
        self.seed = seed
        self.paper_mode = paper_mode
        self.isolated_dir = isolated_dir
        self._prev_submission_mode: Optional[str] = None
        self._saved_attrs: List[tuple] = []
        self._tmp_dir: Optional[str] = None
        self._modules_before: Optional[set] = None
        # L46 event capture
        self._captured_events: List[Any] = []
        self._capture_bus: Optional[Any] = None   # fresh EventBus for this run
        self._orig_get_default_bus: Optional[Any] = None

    def _assert_paper_mode(self) -> None:
        """Force SUBMISSION_MODE=paper; raise RuntimeError if live mode set with paper_mode=True."""
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

    # ------------------------------------------------------------------ isolation

    def _patch_attr(self, module: Any, attr: str, value: Any) -> None:
        if module is None:
            return
        original = getattr(module, attr, None)
        if original is None:
            return
        self._saved_attrs.append((module, attr, original))
        setattr(module, attr, value)

    def _redirect_paths_to_tmp(self, tmp: Path) -> None:
        """Redirect all module-level path constants to isolated tmp dir."""
        tmp.mkdir(parents=True, exist_ok=True)
        self._modules_before = set(sys.modules.keys())
        _p = tmp  # alias for brevity

        if L05 is not None:
            self._patch_attr(L05, "_LEDGER_DIR", _p)
            self._patch_attr(L05, "_CACHE_FILE", _p / "submission_cache.json")
            self._patch_attr(L05, "_PAPER_FILE", _p / "paper_submissions.json")
            buckets = getattr(L05, "_buckets", None)
            if isinstance(buckets, dict):
                buckets.clear()

        if L07 is not None:
            for _a, _v in [("_LEDGER_DIR", _p), ("_BETS_FILE", _p / "bets.parquet"),
                           ("_BETS_CSV", _p / "bets.csv"), ("_CONTESTS_FILE", _p / "contests.parquet"),
                           ("_CONTESTS_CSV", _p / "contests.csv")]:
                self._patch_attr(L07, _a, _v)

        for _m in (L08, L19):
            if _m is not None:
                self._patch_attr(_m, "_LEDGER_DIR", _p)
                self._patch_attr(_m, "_BETS_PARQUET", _p / "bets.parquet")
                self._patch_attr(_m, "_BETS_CSV", _p / "bets.csv")

        if L19 is not None:
            self._patch_attr(L19, "_SNAPSHOT_DIR", _p / "snapshots")

        if L37 is not None:
            for _a, _v in [("_LEDGER_DIR", _p), ("_BETS_PARQUET", _p / "bets.parquet"),
                           ("_BETS_CSV", _p / "bets.csv"), ("_POSTMORTEM_DIR", _p / "postmortems"),
                           ("_BANKROLL_STATE", _p / "bankroll_state.json")]:
                self._patch_attr(L37, _a, _v)

        if L09 is not None:
            self._patch_attr(L09, "_SEED_DIR", _p / "exchange_seed" / "kalshi")
            self._patch_attr(L09, "_LEDGER_DIR", _p)
            self._patch_attr(L09, "_PAPER_ORDERS_FILE", _p / "paper_kalshi_orders.json")

        if L10 is not None:
            self._patch_attr(L10, "_SEED_DIR", _p / "exchange_seed" / "polymarket")
            self._patch_attr(L10, "_OB_DIR", _p / "exchange_seed" / "polymarket" / "orderbooks")
            self._patch_attr(L10, "_LEDGER_DIR", _p)
            self._patch_attr(L10, "_LEDGER_FILE", _p / "paper_polymarket_orders.json")

        if L14 is not None:
            self._patch_attr(L14, "_LEDGER_DIR", _p)
            self._patch_attr(L14, "_ORDERS_FILE", _p / "open_orders.json")
            try:
                sys.modules.get("scripts.execute_loop.L14_order_manager")._reset_state()  # type: ignore[union-attr]
            except Exception:
                pass

        if L18 is not None:
            import scripts.execute_loop.L18_bankroll_manager as _l18m
            _orig = _l18m.CONFIG.get("ledger_path", "data/ledger/bankroll_state.json")
            self._saved_attrs.append((_l18m.CONFIG, "ledger_path", _orig))
            _l18m.CONFIG["ledger_path"] = str(_p / "bankroll_state.json")

        if L36 is not None:
            for _a, _v in [("_LEDGER_DIR", _p), ("_BETS_PARQUET", _p / "bets.parquet"),
                           ("_BETS_CSV", _p / "bets.csv"),
                           ("_QUARANTINE_FILE", _p / "quarantined_angles.json")]:
                self._patch_attr(L36, _a, _v)

        if L20 is not None:
            # Redirect seen-hashes and external injury file to tmp; no HTTP in harness mode
            self._patch_attr(L20, "_SEEN_PATH", _p / "injury_seen.json")
            self._patch_attr(L20, "_EXTERNAL", _p / "nba_official_injury.json")

        if L21 is not None:
            # Redirect lineup dir and suppress HTTP by patching _http_get to return ""
            self._patch_attr(L21, "_LINEUP_DIR", _p / "lineup_announcements")
            self._patch_attr(L21, "_http_get", lambda url: "")  # type: ignore[arg-type]

        if L26 is not None:
            self._patch_attr(L26, "_LEDGER_DIR", _p)
            self._patch_attr(L26, "_BETS_FILE", _p / "bets.parquet")
            self._patch_attr(L26, "_BETS_CSV", _p / "bets.csv")

    def _setup_event_capture(self) -> None:
        """Install a fresh EventBus and monkey-patch L46's get_default_bus to return it.

        All producer layers call _L46.publish(...) which internally delegates to
        get_default_bus().publish(...).  By replacing get_default_bus on the
        already-imported module object we redirect every publish call to our
        capture bus without touching any producer module.  The original function
        is restored in _teardown_event_capture via try/finally.
        """
        if _L46_MOD is None:
            return
        from scripts.execute_loop.L46_event_bus import EventBus
        self._capture_bus = EventBus()
        self._captured_events = []

        def _capture_handler(event: Any) -> None:
            self._captured_events.append(event)

        self._capture_bus.subscribe("*", _capture_handler, layer="L41_harness")

        # Save original and patch module-level get_default_bus
        self._orig_get_default_bus = _L46_MOD.get_default_bus
        _capture_bus_ref = self._capture_bus

        def _patched_get_default_bus() -> Any:
            return _capture_bus_ref

        _L46_MOD.get_default_bus = _patched_get_default_bus  # type: ignore[method-assign]

    def _teardown_event_capture(self) -> None:
        """Restore original get_default_bus; clear capture state."""
        if _L46_MOD is None:
            return
        if self._orig_get_default_bus is not None:
            _L46_MOD.get_default_bus = self._orig_get_default_bus  # type: ignore[method-assign]
            self._orig_get_default_bus = None
        self._capture_bus = None

    def _restore_paths(self) -> None:
        """Restore saved module-level constants; clean up newly-imported submodules."""
        for obj, attr, original in self._saved_attrs:
            try:
                (obj.__setitem__(attr, original) if isinstance(obj, dict)
                 else setattr(obj, attr, original))
            except Exception as exc:
                log.debug("_restore_paths: could not restore %r.%r: %s", obj, attr, exc)
        self._saved_attrs.clear()

        if self._modules_before is not None:
            _PFX = "scripts.execute_loop."
            parent = sys.modules.get("scripts.execute_loop")
            for key in [k for k in list(sys.modules) if k not in self._modules_before and k.startswith(_PFX)]:
                sys.modules.pop(key, None)
                if parent is not None:
                    try:
                        delattr(parent, key[len(_PFX):])
                    except AttributeError:
                        pass
            self._modules_before = None

    def _snapshot_real_ledger_mtimes(self) -> Dict[str, float]:
        rl = _PROJECT_DIR / "data" / "ledger"
        out: Dict[str, float] = {}
        for p in (rl.iterdir() if rl.is_dir() else []):
            if p.is_file():
                try:
                    out[str(p)] = p.stat().st_mtime
                except OSError:
                    pass
        return out

    def _check_ledger_pollution(self, before: Dict[str, float], report: dict) -> None:
        rl = _PROJECT_DIR / "data" / "ledger"
        changed: List[str] = []
        for p in (rl.iterdir() if rl.is_dir() else []):
            if not p.is_file():
                continue
            try:
                if str(p) in before and p.stat().st_mtime != before[str(p)]:
                    changed.append(str(p))
            except OSError:
                pass
        if changed:
            log.warning("IntegrationHarness: real data/ledger mutated: %s", changed)
            report.setdefault("warnings", []).append({"type": "real_ledger_pollution", "files": changed})

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
        try:
            return str(data)[:200]
        except Exception:
            return "<unserializable>"

    def run_end_to_end(self) -> dict:
        """Execute all stages in an isolated tmp dir; restore originals in finally."""
        self._assert_paper_mode()
        if self.isolated_dir is not None:
            self.isolated_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = Path(tempfile.mkdtemp(prefix="L41_run_", dir=str(self.isolated_dir)))
        else:
            tmp_path = Path(tempfile.mkdtemp(prefix="L41_run_"))
        self._tmp_dir = str(tmp_path)
        before_mtimes = self._snapshot_real_ledger_mtimes()
        self._redirect_paths_to_tmp(tmp_path)
        self._setup_event_capture()
        started_at = datetime.now(timezone.utc).isoformat()
        report: dict = {}
        try:
            report = self._run_stages(started_at)
        finally:
            self._teardown_event_capture()
            self._restore_paths()
            self._restore_mode()
        self._check_ledger_pollution(before_mtimes, report)
        return report

    def _run_stages(self, started_at: str) -> dict:
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

        def _injury_feed():
            if fetch_nba_official_injuries is None:
                raise RuntimeError("L20 not available")
            updates = fetch_nba_official_injuries()
            assert isinstance(updates, list)
            return {"n_updates": len(updates)}

        stages.append(self._run_stage("injury_feed_check", _injury_feed) if L20 else _skip("injury_feed_check"))

        def _lineup_watcher():
            if fetch_confirmed_lineups is None:
                raise RuntimeError("L21 not available")
            confs = fetch_confirmed_lineups()
            assert isinstance(confs, list)
            return {"n_teams_confirmed": len(confs)}

        stages.append(self._run_stage("lineup_watcher", _lineup_watcher) if L21 else _skip("lineup_watcher"))

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

        def _dispatcher_route():
            if get_routing is None:
                raise RuntimeError("L40 not available")
            routes = get_routing()
            assert isinstance(routes, dict) and len(routes) > 0
            return {"n_routes": len(routes), "stats": list(routes.keys())}

        stages.append(self._run_stage("dispatcher_route", _dispatcher_route) if L40 else _skip("dispatcher_route"))

        def _shadow_compare():
            if list_active_shadows is None:
                raise RuntimeError("L25 not available")
            shadows = list_active_shadows()
            assert isinstance(shadows, list)
            return {"n_active_shadows": len(shadows)}

        stages.append(self._run_stage("shadow_compare", _shadow_compare) if L25 else _skip("shadow_compare"))

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

        def _fetch_orderbooks():
            out: dict = {}
            if kalshi_get_orderbook is not None:
                try:
                    ob = kalshi_get_orderbook("STUB-NBA-001")
                    out["kalshi"] = {"keys": list(ob.keys()) if isinstance(ob, dict) else str(ob)}
                except KeyError:
                    out["kalshi"] = None   # no seed file — paper-mode allowed-empty
            if poly_get_orderbook is not None:
                ob = poly_get_orderbook("stub_condition_001")
                out["polymarket"] = str(ob) if ob is not None else None
            return out

        stages.append(self._run_stage("fetch_exchange_orderbooks", _fetch_orderbooks))

        def _cross_ev():
            if find_ev_opportunities is None:
                raise RuntimeError("L13 not available")
            opps = find_ev_opportunities(
                {("StubPlayer", "PTS"): {"p_over": 0.60, "p_under": 0.40}},
                quotes=[], min_ev_pct=2.0,
                source="paper_clients", market_id="STUB-NBA-001",
            )
            assert isinstance(opps, list)
            return {"n_opportunities": len(opps)}

        stages.append(self._run_stage("cross_exchange_ev", _cross_ev) if L13 else _skip("cross_exchange_ev"))

        def _market_making_quote():
            if compute_mm_quote is None:
                raise RuntimeError("L15 not available")
            quote = compute_mm_quote(model_p=0.55, model_p_std=0.02, target_spread_pp=3, market_id="STUB-NBA-001")
            # may return None if guard rails reject — that's still a valid result
            if quote is not None:
                assert hasattr(quote, "bid_price") and hasattr(quote, "ask_price")
            return {"quote_generated": quote is not None}

        stages.append(self._run_stage("market_making_quote", _market_making_quote) if L15 else _skip("market_making_quote"))

        def _sync_positions():
            if sync_all_exchanges is None:
                raise RuntimeError("L14 not available")
            changed = sync_all_exchanges()   # no open orders in stub → []
            assert isinstance(changed, list)
            return {"n_changed": len(changed)}

        stages.append(self._run_stage("sync_exchange_positions", _sync_positions) if L14 else _skip("sync_exchange_positions"))

        def _hedge_calculate():
            if recommend_hedge is None:
                raise RuntimeError("L17 not available")
            open_bet = {
                "bet_id": "stub_bet_001",
                "side": "OVER",
                "stake": 50.0,
                "odds_american": -110,
                "status": "OPEN",
            }
            live_market = {
                "opposite_side": "UNDER",
                "odds_american_opposite": 120,
                "book": "stub_book",
            }
            rec = recommend_hedge(open_bet, live_market)
            assert rec is not None and rec.decision in ("hedge_full", "hedge_partial", "no_hedge")
            return {"decision": rec.decision, "hedge_stake": rec.hedge_stake}

        stages.append(self._run_stage("hedge_calculate", _hedge_calculate) if L17 else _skip("hedge_calculate"))

        def _kelly():
            if kelly_fraction is None:
                raise RuntimeError("L18 not available")
            frac = float(kelly_fraction(model_p=0.55, american_odds=+100))
            assert 0.0 <= frac <= 1.0, f"Kelly fraction {frac!r} out of [0,1]"
            return {"kelly_fraction": frac}

        stages.append(self._run_stage("kelly_sizing", _kelly) if L18 else _skip("kelly_sizing"))

        def _variance_budget():
            if compute_daily_allocation is None:
                raise RuntimeError("L34 not available")
            allocs = compute_daily_allocation(total_bankroll=self.bankroll)
            assert isinstance(allocs, list)
            return {"n_buckets": len(allocs), "total_dollars": sum(a.target_dollars for a in allocs)}

        stages.append(self._run_stage("variance_budget", _variance_budget) if L34 else _skip("variance_budget"))

        def _sell_to_close():
            if evaluate_close_decision is None:
                raise RuntimeError("L33 not available")
            dec = evaluate_close_decision(
                position={"position_id": "stub_pos_001", "qty": 100.0, "entry_price": 0.50, "side": "YES"},
                current_quote={"bid_price": 0.65, "ask_price": 0.67, "bid_size": 50.0},
                model_p=0.60, time_to_settle_min=30,
            )
            assert dec.action in ("HOLD", "SELL", "SELL_PARTIAL")
            return {"action": dec.action, "reason": dec.decision_reason}

        stages.append(self._run_stage("sell_to_close", _sell_to_close) if L33 else _skip("sell_to_close"))

        def _edge_erosion():
            if daily_edge_report is None:
                raise RuntimeError("L36 not available")
            rpt = daily_edge_report()
            assert isinstance(rpt, dict) and "n_angles" in rpt
            return {"n_angles": rpt.get("n_angles", 0)}

        stages.append(self._run_stage("edge_erosion", _edge_erosion) if L36 else _skip("edge_erosion"))

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

        def _ledger():
            if get_pnl_summary is None:
                raise RuntimeError("L07 not available")
            summary = get_pnl_summary()
            return {"n_groups": len(summary)}

        if "settle_bets" in failed_critical:
            stages.append(_skip_depends("ledger_summary"))
        else:
            stages.append(self._run_stage("ledger_summary", _ledger))

        def _clv():
            if nightly_clv_report is None:
                raise RuntimeError("L19 not available")
            report = nightly_clv_report()
            return {"n_bets": report.get("n_bets", 0)}

        if L19 is None:
            stages.append(_skip("clv_report"))
        else:
            stages.append(self._run_stage("clv_report", _clv))

        def _drift():
            if daily_drift_report is None:
                raise RuntimeError("L08 not available")
            report = daily_drift_report()
            return {"n_metrics": len(report.get("metrics", []))}

        if L08 is None:
            stages.append(_skip("drift_check"))
        else:
            stages.append(self._run_stage("drift_check", _drift))

        def _hygiene_check():
            if daily_hygiene_report is None:
                raise RuntimeError("L26 not available")
            # Pass empty recent_bets to avoid reading real ledger
            report = daily_hygiene_report(recent_bets=[])
            assert isinstance(report, dict) and "status" in report
            return {"status": report.get("status", "unknown"), "n_checks": len(report.get("checks", []))}

        stages.append(self._run_stage("hygiene_check", _hygiene_check) if L26 else _skip("hygiene_check"))

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

        # ---------------------------------------------------------------- L46
        def _verify_event_publication() -> dict:
            """Assert required L46 events were published during this run.

            Required events are gated on whether their source stage PASS'd with
            meaningful output — e.g. kelly.sized is only required if kelly_sizing
            PASS'd with a positive fraction, bet.settled only if settle_bets PASS'd
            with settled > 0, fill.received|order.filled only if sync_exchange_positions
            PASS'd with n_changed > 0.
            """
            captured_names = {getattr(e, "name", None) for e in self._captured_events}
            breakdown: Dict[str, int] = {}
            for e in self._captured_events:
                n = getattr(e, "name", "<unknown>")
                breakdown[n] = breakdown.get(n, 0) + 1

            # Build stage-status and data lookups from already-run stages
            _stage_status = {s["name"]: s.get("status") for s in stages}
            _stage_data = {s["name"]: s.get("data") for s in stages}

            # kelly.sized: required only if kelly_sizing PASS'd with fraction > 0
            _kelly_data = _stage_data.get("kelly_sizing") or {}
            _kelly_frac = (_kelly_data.get("kelly_fraction", 0.0)
                           if isinstance(_kelly_data, dict) else 0.0)
            _need_kelly = (
                _stage_status.get("kelly_sizing") == "PASS" and float(_kelly_frac) > 0.0
            )

            # bet.settled: required only if settle_bets PASS'd with settled > 0
            _settle_data = _stage_data.get("settle_bets") or {}
            _settle_n = (_settle_data.get("settled", 0)
                         if isinstance(_settle_data, dict) else 0)
            _need_bet_settled = (
                _stage_status.get("settle_bets") == "PASS" and int(_settle_n) > 0
            )

            # fill: required only if sync_exchange_positions PASS'd with n_changed > 0
            _sync_data = _stage_data.get("sync_exchange_positions") or {}
            _sync_n = (_sync_data.get("n_changed", 0)
                       if isinstance(_sync_data, dict) else 0)
            _need_fill = (
                _stage_status.get("sync_exchange_positions") == "PASS"
                and int(_sync_n) > 0
            )

            missing_required: List[str] = []
            if _need_kelly and "kelly.sized" not in captured_names:
                missing_required.append("kelly.sized")
            if _need_bet_settled and "bet.settled" not in captured_names:
                missing_required.append("bet.settled")
            if _need_fill and not (_FILL_EVENTS & captured_names):
                missing_required.append("fill.received|order.filled")

            missing_optional: List[str] = [
                ev for ev in sorted(_OPTIONAL_EVENTS) if ev not in captured_names
            ]

            data: Dict[str, Any] = {
                "event_count": len(self._captured_events),
                "breakdown": breakdown,
                "missing_required": missing_required,
                "missing_optional": missing_optional,
                "l46_available": _L46_MOD is not None,
                "gates": {
                    "need_kelly_sized": _need_kelly,
                    "need_bet_settled": _need_bet_settled,
                    "need_fill": _need_fill,
                },
            }

            if _L46_MOD is None:
                data["warn"] = "L46 not available; event capture skipped"
                return data

            if missing_required:
                raise AssertionError(
                    f"Required L46 events not captured: {missing_required}. "
                    f"Captured: {sorted(captured_names)}"
                )
            return data

        stages.append(self._run_stage("verify_event_publication", _verify_event_publication))

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
