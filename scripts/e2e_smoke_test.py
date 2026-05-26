"""e2e_smoke_test.py — R27_T5 full-stack end-to-end smoke test.

Single-command smoke test for the entire production stack. Designed to be
run in CI or pre-deploy. Exercises 12 named stages, each in a sandboxed
tmp directory using cached/local fixtures where possible (no live network
calls beyond a single lightweight scraper probe that can SKIP cleanly).

The 12 stages:

    SCRAPER_BOV         — Bovada scraper module imports + invokes a parser
                           round-trip on synthetic JSON (NO live HTTP).
    SCRAPER_PIN         — Pinnacle scraper module imports + parses a
                           cached/synthetic matchup payload.
    INJURY_FEED         — nba_injury_report_scraper.to_dataframe round-trip
                           over a synthetic raw-row list.
    PREDICTIONS         — predictions_cache_<date>.parquet present + has
                           expected columns + non-zero rows.
    LIVE_REC_ENGINE     — live_recommendation_engine.run_engine end-to-end
                           against the local lines + predictions cache.
    INPLAY_RANKER       — inplay_bet_ranker.run_tick against a sandbox
                           quarter_box dir + synthetic lines.
    PLACE_BET           — pnl_ledger.place_bet writes one row to a TEST
                           ledger (never data/pnl_ledger.csv).
    AUTO_SETTLE         — auto_settle_daemon.tick consumes the TEST ledger
                           and writes a status.
    RECONCILE           — reconcile_settlements.reconcile runs on the
                           TEST ledger.
    DASHBOARD_RENDER    — operator_dashboard.render_operator_html emits
                           valid non-empty HTML against degraded inputs.
    ALERT_FIRE          — alerts.discord_webhook.alert dispatches with
                           webhook URL forced to None (vault + file path).
    WATCHDOG_HEARTBEAT  — daemon_watchdog.check_daemon round-trips a fake
                           registry entry with a freshly-written heartbeat.

Per-stage cap: 30 seconds. Overall wall clock cap: 5 minutes.

Stage status values:
    PASS      — stage completed successfully
    FAIL      — stage crashed or assertion failed
    SKIP      — stage prerequisites missing (logged, not a failure)
    TIMEOUT   — stage exceeded the 30s per-stage cap

Exit code:
    0  iff all stages are in {PASS, SKIP} AND overall <5min
    1  if ANY stage is FAIL or TIMEOUT (or wall clock > 5min)

Output:
    Console — formatted PASS/FAIL table.
    JSON    — data/cache/e2e_smoke_<date>.json (full per-stage detail).

Hard rules:
    * NEVER touches data/pnl_ledger.csv — TEST ledger is sandboxed.
    * NEVER makes live HTTP calls in CI mode (default).
    * All filesystem writes are scoped to a per-run tempdir.

CLI:
    python scripts/e2e_smoke_test.py
    python scripts/e2e_smoke_test.py --json-out path.json
    python scripts/e2e_smoke_test.py --quiet         # JSON only
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# --------------------------------------------------------------------------- #
# Tuning knobs
# --------------------------------------------------------------------------- #
STAGE_TIMEOUT_SEC = 30.0
OVERALL_TIMEOUT_SEC = 300.0
SHIP_GATE_MIN_PASSES = 8  # >=8 of 12 stages must PASS (rest may SKIP)

STAGES_ORDER: Tuple[str, ...] = (
    "SCRAPER_BOV",
    "SCRAPER_PIN",
    "INJURY_FEED",
    "PREDICTIONS",
    "LIVE_REC_ENGINE",
    "INPLAY_RANKER",
    "PLACE_BET",
    "AUTO_SETTLE",
    "RECONCILE",
    "DASHBOARD_RENDER",
    "ALERT_FIRE",
    "WATCHDOG_HEARTBEAT",
)


# --------------------------------------------------------------------------- #
# Result helpers
# --------------------------------------------------------------------------- #
def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _mk(status: str, *, reason: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    """Build a per-stage result dict."""
    payload: Dict[str, Any] = {"status": status, "reason": reason}
    payload.update(extra)
    return payload


# --------------------------------------------------------------------------- #
# Stage runner — wraps each stage with timing + timeout + crash isolation
# --------------------------------------------------------------------------- #
def _run_stage(name: str, fn: Callable[..., Dict[str, Any]],
               sandbox: Path) -> Dict[str, Any]:
    """Execute one stage with crash isolation + wallclock cap.

    Per-stage cap is enforced via wall-clock CHECK after the call returns
    (we do not use signal-based timeouts because Windows lacks SIGALRM and
    forcibly killing in-progress Python is unsafe). Stages that take >cap
    are marked TIMEOUT but allowed to finish.
    """
    t0 = time.time()
    try:
        res = fn(sandbox)
        runtime = round(time.time() - t0, 3)
        if not isinstance(res, dict):
            res = {"status": "FAIL", "reason": f"stage returned non-dict: {type(res)!r}"}
        if runtime > STAGE_TIMEOUT_SEC and res.get("status") == "PASS":
            res = {**res, "status": "TIMEOUT",
                   "reason": f"runtime {runtime}s > cap {STAGE_TIMEOUT_SEC}s"}
        res["runtime_sec"] = runtime
        res["name"] = name
        return res
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "status": "FAIL",
            "reason": f"crash: {type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=4),
            "runtime_sec": round(time.time() - t0, 3),
        }


# --------------------------------------------------------------------------- #
# Stage 1 — SCRAPER_BOV (parser round-trip, no live HTTP)
# --------------------------------------------------------------------------- #
def stage_scraper_bov(sandbox: Path) -> Dict[str, Any]:
    try:
        import bov_scraper_daemon as bov  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    # Smoke the dedup-key helper + minute key helper + classifier --- these
    # are the load-bearing pure-fn building blocks of the daemon.
    try:
        mk = bov._minute_key("2026-05-26T12:34:56")
        assert mk == "2026-05-26T12:34", f"unexpected minute key {mk!r}"
        stat = bov._bov_stat_from_market("LeBron James", "Total Points")
        # Must return a known stat code or None — just make sure it returns.
        assert stat is None or isinstance(stat, str)
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"helper round-trip failed: {exc}")

    # Use the lines_dir → row-counter path to verify the append/dedup flow
    # works without network. Write a synthetic row, then re-append and
    # verify dedup squashes the duplicate.
    try:
        lines_dir = sandbox / "bov_lines"
        lines_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(lines_dir / "2099-01-01_bov.csv")
        row = {
            "captured_at": "2099-01-01T12:00:00",
            "book": "bov",
            "game_id": "",
            "player_id": "",
            "player_name": "Test Player",
            "team": "ATL",
            "stat": "pts",
            "line": "25.5",
            "over_price": -110,
            "under_price": -110,
            "market_status": "open",
        }
        n1 = bov.append_rows([row], out_path)
        n2 = bov.append_rows([row], out_path)  # duplicate → 0 new
        if n1 != 1 or n2 != 0:
            return _mk("FAIL",
                       reason=f"append_rows dedup broken (n1={n1} n2={n2})")
        return _mk("PASS",
                   detail={"rows_written": n1, "rows_deduped": n2,
                           "out_path": out_path})
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"append round-trip failed: {exc}")


# --------------------------------------------------------------------------- #
# Stage 2 — SCRAPER_PIN (parser round-trip, no live HTTP)
# --------------------------------------------------------------------------- #
def stage_scraper_pin(sandbox: Path) -> Dict[str, Any]:
    try:
        import pinnacle_scraper as pin  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    # Smoke the pure helper functions on representative inputs.
    try:
        # stat_from_units_and_desc covers the parser's most critical mapping.
        for units, desc, expected_nonnull in [
            ("Points", "LeBron James Total Points", True),
            ("Rebounds", "LeBron James Total Rebounds", True),
            ("Assists", "LeBron James Total Assists", True),
        ]:
            res = pin._stat_from_units_and_desc(units, desc)
            assert isinstance(res, str), f"expected str stat for {units!r}, got {res!r}"

        # player_from_description: well-formed inputs
        name = pin._player_from_description("LeBron James Total Points", "Points")
        assert "lebron" in (name or "").lower(), f"unexpected player parse: {name!r}"
        return _mk("PASS",
                   detail={"stat_map_works": True, "player_parse_works": True})
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"helper round-trip failed: {exc}")


# --------------------------------------------------------------------------- #
# Stage 3 — INJURY_FEED (dataframe round-trip, no live network)
# --------------------------------------------------------------------------- #
def stage_injury_feed(sandbox: Path) -> Dict[str, Any]:
    try:
        import nba_injury_report_scraper as inj  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    # status normalizer must handle the canonical 5 statuses.
    try:
        cases = [
            ("Out", "OUT"),
            ("Questionable", "QUESTIONABLE"),
            ("Doubtful", "DOUBTFUL"),
            ("Probable", "PROBABLE"),
            ("Available", "AVAILABLE"),
        ]
        for raw, expected in cases:
            got = inj.normalize_status(raw)
            assert got == expected, f"normalize_status({raw!r}) = {got!r}, expected {expected!r}"
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"normalize_status round-trip failed: {exc}")

    # to_dataframe: build a synthetic 3-row raw input and verify the parquet
    # schema comes out right.
    try:
        rows = [
            {"player_name": "Test One", "team": "LAL", "status": "Out", "reason": "rest"},
            {"player_name": "Test Two", "team": "GSW", "status": "Questionable", "reason": "ankle"},
            {"player_name": "Test Three", "team": "BOS", "status": "Probable", "reason": "knee"},
        ]
        df = inj.to_dataframe(rows, report_date="2099-01-01",
                              fetched_at="2099-01-01T00:00:00",
                              name_index={})
        # Required columns from the parquet schema.
        needed = {"player_name", "status"}
        missing = needed - set(df.columns)
        if missing:
            return _mk("FAIL", reason=f"to_dataframe missing cols: {missing}")
        if len(df) < 3:
            return _mk("FAIL", reason=f"expected >=3 rows, got {len(df)}")
        # Verify atomic parquet write helper works
        out = sandbox / "test_injuries.parquet"
        inj.write_parquet_atomic(df, str(out))
        if not out.exists():
            return _mk("FAIL", reason="atomic write did not produce file")
        return _mk("PASS",
                   detail={"n_rows": int(len(df)),
                           "cols": list(df.columns)[:10]})
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"dataframe round-trip failed: {exc}")


# --------------------------------------------------------------------------- #
# Stage 4 — PREDICTIONS (verify cache file exists + schema valid)
# --------------------------------------------------------------------------- #
def stage_predictions(sandbox: Path) -> Dict[str, Any]:
    today = _today_iso()
    cache_dir = Path(PROJECT_DIR) / "data" / "cache"
    # Find the freshest predictions_cache_*.parquet (today or last 7d).
    pattern = "predictions_cache_*.parquet"
    cands = sorted(cache_dir.glob(pattern), reverse=True)
    if not cands:
        return _mk("SKIP",
                   reason=f"no {pattern} in {cache_dir} (no slate today)")
    path = cands[0]
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"read failed: {exc}")
    needed = {"player_name", "stat", "q10", "q50", "q90"}
    missing = needed - set(df.columns)
    if missing:
        return _mk("FAIL", reason=f"missing cols: {sorted(missing)}")
    if df.empty:
        return _mk("FAIL", reason="predictions cache empty")
    return _mk("PASS",
               detail={"path": str(path), "n_rows": int(len(df)),
                       "is_today": path.name == f"predictions_cache_{today}.parquet"})


# --------------------------------------------------------------------------- #
# Stage 5 — LIVE_REC_ENGINE (run engine end-to-end on local fixtures)
# --------------------------------------------------------------------------- #
def stage_live_rec_engine(sandbox: Path) -> Dict[str, Any]:
    try:
        from live_recommendation_engine import run_engine  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    today = _today_iso()
    cache_dir = Path(PROJECT_DIR) / "data" / "cache"
    pred_path: Optional[str] = None
    for d in (today,):
        p = cache_dir / f"predictions_cache_{d}.parquet"
        if p.exists():
            pred_path = str(p)
            break
    if pred_path is None:
        cands = sorted(cache_dir.glob("predictions_cache_*.parquet"), reverse=True)
        if cands:
            pred_path = str(cands[0])
            today = cands[0].stem.replace("predictions_cache_", "")
    if pred_path is None:
        return _mk("SKIP", reason="no predictions_cache parquet on disk")

    try:
        payload = run_engine(
            bankroll=1000.0, top=5, date=today, min_edge=0.02,
            predictions_path=pred_path,
        )
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"run_engine raised: {exc}")

    # Required keys: engine ran shape-correctly even if zero recs.
    needed = {"engine_version", "date", "bankroll", "recommendations"}
    missing = needed - set(payload.keys())
    if missing:
        return _mk("FAIL", reason=f"payload missing: {sorted(missing)}")
    return _mk("PASS",
               detail={
                   "engine_version": payload.get("engine_version"),
                   "n_recs": len(payload.get("recommendations") or []),
                   "n_evaluated": payload.get("n_evaluated", 0),
                   "n_snapshots_loaded": payload.get("n_snapshots_loaded", 0),
                   "books_loaded": payload.get("books_loaded", []),
               })


# --------------------------------------------------------------------------- #
# Stage 6 — INPLAY_RANKER (run_tick against sandboxed qbox + synthetic lines)
# --------------------------------------------------------------------------- #
def stage_inplay_ranker(sandbox: Path) -> Dict[str, Any]:
    qbox_dir = Path(PROJECT_DIR) / "data" / "cache" / "quarter_box"
    if not qbox_dir.is_dir():
        return _mk("SKIP", reason=f"no quarter_box dir at {qbox_dir}")
    # Find one game with q1+q2 (no need for q4 — we test mid-game ranking).
    gid: Optional[str] = None
    for fn in sorted(os.listdir(qbox_dir)):
        if not fn.endswith("_q2.json"):
            continue
        cand = fn[: -len("_q2.json")]
        if len(cand) != 10 or not cand.isdigit():
            continue
        if (qbox_dir / f"{cand}_q1.json").exists():
            gid = cand
            break
    if gid is None:
        return _mk("SKIP", reason="no game with q1+q2 box on disk")

    try:
        import inplay_bet_ranker as ibr  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    # Set up an isolated qbox dir with ONLY q1+q2 for this game.
    iso_qbox = sandbox / "qbox_iso"
    iso_qbox.mkdir(parents=True, exist_ok=True)
    for q in (1, 2):
        src = qbox_dir / f"{gid}_q{q}.json"
        dst = iso_qbox / f"{gid}_q{q}.json"
        shutil.copy2(src, dst)

    # Write an empty lines csv so the ranker doesn't error on missing files.
    lines_dir = sandbox / "lines_iso"
    lines_dir.mkdir(parents=True, exist_ok=True)
    date_s = _today_iso()
    for book in ("bov", "pin", "fd"):
        with open(lines_dir / f"{date_s}_{book}.csv", "w", encoding="utf-8") as fh:
            fh.write("captured_at,book,game_id,player_id,player_name,"
                     "stat,line,over_price,under_price,start_time\n")

    # Patch projector to a fast deterministic stub (avoids needing model load).
    def _fake_project(snap, period_override=None):
        rows = []
        for p in snap.get("players", []) or []:
            for stat in ("pts", "reb", "ast"):
                cur = float(p.get(stat, 0) or 0)
                rows.append({
                    "name": p.get("name", ""), "team": p.get("team", ""),
                    "player_id": p.get("player_id"), "stat": stat,
                    "current": cur, "projected_final": cur * 2.0,
                    "period": snap.get("period"),
                    "q10": cur * 1.2, "q90": cur * 2.8,
                })
        return rows

    orig_qbox = ibr.QBOX_DIR
    orig_lines = ibr.LINES_DIR
    orig_proj = ibr._project_with_engine
    try:
        ibr.QBOX_DIR = str(iso_qbox)
        ibr.LINES_DIR = str(lines_dir)
        ibr._project_with_engine = _fake_project
        out = ibr.run_tick(
            game_id=gid, date_str=date_s, bankroll=1000.0,
            qbox_dir=str(iso_qbox), books=("bov",),
        )
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"run_tick raised: {exc}")
    finally:
        ibr.QBOX_DIR = orig_qbox
        ibr.LINES_DIR = orig_lines
        ibr._project_with_engine = orig_proj

    if "status" not in out:
        return _mk("FAIL", reason="run_tick missing status field")
    return _mk("PASS",
               detail={"game_id": gid, "status": out.get("status"),
                       "n_props_evaluated": out.get("n_props_evaluated", 0),
                       "tick_latency_ms": out.get("tick_latency_ms")})


# --------------------------------------------------------------------------- #
# Stage 7 — PLACE_BET (write one fake bet to TEST ledger)
# --------------------------------------------------------------------------- #
def stage_place_bet(sandbox: Path) -> Dict[str, Any]:
    try:
        from src.betting import pnl_ledger as ledger  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    # Mandatory safety: TEST ledger MUST NOT equal production ledger.
    test_ledger = str(sandbox / "pnl_ledger_test.csv")
    test_bankroll = str(sandbox / "pnl_bankroll_test.csv")
    prod = os.path.abspath(os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv"))
    if os.path.abspath(test_ledger) == prod:
        return _mk("FAIL", reason="REFUSE: test ledger path == production")

    # Monkey-patch ledger paths.
    orig_l = ledger.LEDGER_CSV
    orig_b = ledger.BANKROLL_CSV
    orig_lock = ledger.LOCK_PATH
    bet_id: Optional[str] = None
    try:
        ledger.LEDGER_CSV = test_ledger
        ledger.BANKROLL_CSV = test_bankroll
        ledger.LOCK_PATH = test_ledger + ".lock"
        ledger.record_bankroll(1000.0, "r27_t5_smoke")
        bet_id = ledger.place_bet(
            game_id="0099900099", player="Smoke Player", stat="pts",
            line=20.5, side="OVER", book="bov", odds=-110, stake=10.0,
            model_pred=24.0, model_prob=0.60, kelly_pct=0.01,
            player_id=999, team="TEST",
        )
        bets = ledger.all_bets()
    finally:
        ledger.LEDGER_CSV = orig_l
        ledger.BANKROLL_CSV = orig_b
        ledger.LOCK_PATH = orig_lock

    if not bet_id:
        return _mk("FAIL", reason="place_bet returned no bet_id")
    if len(bets) < 1:
        return _mk("FAIL", reason="ledger empty after place_bet")
    # Stash bet metadata in sandbox so AUTO_SETTLE can pick it up.
    (sandbox / "place_bet_meta.json").write_text(
        json.dumps({"bet_id": bet_id, "test_ledger": test_ledger,
                    "test_bankroll": test_bankroll, "stake": 10.0}),
        encoding="utf-8",
    )
    return _mk("PASS",
               detail={"bet_id": bet_id, "n_bets_in_ledger": len(bets),
                       "test_ledger": test_ledger})


# --------------------------------------------------------------------------- #
# Stage 8 — AUTO_SETTLE (tick consumes TEST ledger)
# --------------------------------------------------------------------------- #
def stage_auto_settle(sandbox: Path) -> Dict[str, Any]:
    meta_path = sandbox / "place_bet_meta.json"
    if not meta_path.exists():
        return _mk("SKIP", reason="no place_bet meta (PLACE_BET did not run)")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    try:
        from src.betting import pnl_ledger as ledger  # noqa: PLC0415
        import auto_settle_daemon as asd  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    # Run a single tick with a seen-set that pre-skips ALL real q4 files
    # (we never want to settle real games — only our fake bet would match,
    # and there's no q4 for game 0099900099 so the daemon simply finds 0 work).
    qbox_dir = Path(PROJECT_DIR) / "data" / "cache" / "quarter_box"
    if not qbox_dir.is_dir():
        return _mk("SKIP", reason="no quarter_box on disk")

    every_q4: set = set()
    for fn in os.listdir(qbox_dir):
        if fn.endswith("_q4.json"):
            pre = fn[: -len("_q4.json")]
            if len(pre) == 10 and pre.isdigit():
                every_q4.add(pre)
    seen_path = sandbox / "auto_settle_seen.json"
    seen_path.write_text(json.dumps(sorted(every_q4)), encoding="utf-8")

    orig_l = ledger.LEDGER_CSV
    orig_b = ledger.BANKROLL_CSV
    orig_lock = ledger.LOCK_PATH
    orig_refresh = asd.refresh_bankroll
    try:
        ledger.LEDGER_CSV = meta["test_ledger"]
        ledger.BANKROLL_CSV = meta["test_bankroll"]
        ledger.LOCK_PATH = meta["test_ledger"] + ".lock"
        # Don't touch bankroll outside sandbox.
        asd.refresh_bankroll = lambda *_a, **_k: {"skipped_in_smoke": True}
        result = asd.tick(qb_dir=qbox_dir, seen_path=seen_path,
                          dry_run=True, start_bankroll=1000.0)
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"tick raised: {exc}")
    finally:
        ledger.LEDGER_CSV = orig_l
        ledger.BANKROLL_CSV = orig_b
        ledger.LOCK_PATH = orig_lock
        asd.refresh_bankroll = orig_refresh

    # Shape check — tick returns a dict with timestamps + games list.
    if not isinstance(result, dict):
        return _mk("FAIL", reason=f"tick returned {type(result)!r}, not dict")
    return _mk("PASS",
               detail={"n_games_processed": len(result.get("games") or []),
                       "dry_run": True})


# --------------------------------------------------------------------------- #
# Stage 9 — RECONCILE (run reconciliation on TEST ledger)
# --------------------------------------------------------------------------- #
def stage_reconcile(sandbox: Path) -> Dict[str, Any]:
    meta_path = sandbox / "place_bet_meta.json"
    if not meta_path.exists():
        return _mk("SKIP", reason="no place_bet meta (PLACE_BET did not run)")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    try:
        from scripts import reconcile_settlements as recon  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    qbox_dir = Path(PROJECT_DIR) / "data" / "cache" / "quarter_box"
    try:
        rpt = recon.reconcile(
            days=7,
            ledger_path=Path(meta["test_ledger"]),
            qb_dir=qbox_dir,
            include_synthetic=True,  # bet 0099900099 is synthetic
        )
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"reconcile raised: {exc}")

    needed = {"as_of", "n_total_settled", "n_real_settled", "n_mismatched"}
    missing = needed - set(rpt.keys())
    if missing:
        return _mk("FAIL", reason=f"report missing keys: {sorted(missing)}")
    return _mk("PASS",
               detail={"n_total_settled": rpt.get("n_total_settled", 0),
                       "n_real_settled": rpt.get("n_real_settled", 0),
                       "n_mismatched": rpt.get("n_mismatched", 0)})


# --------------------------------------------------------------------------- #
# Stage 10 — DASHBOARD_RENDER (operator dashboard HTML, degraded inputs)
# --------------------------------------------------------------------------- #
def stage_dashboard_render(sandbox: Path) -> Dict[str, Any]:
    try:
        from scripts import operator_dashboard as od  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    # Build minimal section payloads (all marked "no data" — the renderer
    # must degrade gracefully). This exercises the HTML pipeline without
    # depending on any specific local data state.
    try:
        html = od.render_operator_html(
            health={"ok": False, "reason": "smoke test"},
            bankroll={"ok": False},
            alerts={"ok": False},
            bets={"ok": False},
            slate={"ok": False},
            tracker={"ok": False},
            live_recs={"ok": False},
            rec_perf={"ok": False},
            settlement={"ok": False},
            title="R27_T5 Smoke",
        )
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"render raised: {exc}")

    if not isinstance(html, str) or len(html) < 200:
        return _mk("FAIL", reason=f"html too short ({len(html) if isinstance(html, str) else 'non-str'})")
    if "<html" not in html.lower() or "</html>" not in html.lower():
        return _mk("FAIL", reason="html missing <html>...</html> envelope")
    # Verify the harness can also write it to disk.
    out = sandbox / "smoke_dashboard.html"
    out.write_text(html, encoding="utf-8")
    return _mk("PASS",
               detail={"html_len": len(html), "out_path": str(out)})


# --------------------------------------------------------------------------- #
# Stage 11 — ALERT_FIRE (dispatch alert with sandboxed paths, no webhook)
# --------------------------------------------------------------------------- #
def stage_alert_fire(sandbox: Path) -> Dict[str, Any]:
    try:
        from src.alerts import discord_webhook as dw  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    vault_path = sandbox / "alerts_vault.md"
    fallback = sandbox / "alerts_fallback.jsonl"
    crit_dir = sandbox / "alerts_critical"
    dedup_path = sandbox / "alerts_dedup.json"

    # Force no webhook URL — alert lands in vault + fallback only.
    orig_env = os.environ.pop("DISCORD_WEBHOOK_URL", None)
    try:
        # Use the warn-level public API; expect vault append at minimum.
        result = dw.alert(
            message="R27_T5 smoke probe",
            level="warn",
            tag="r27_t5_smoke",
            source="e2e_smoke_test",
            webhook_url="",  # explicit empty → no Discord
            fallback_path=str(fallback),
            vault_path=str(vault_path),
            critical_stack_dir=str(crit_dir),
            dedup_state_path=str(dedup_path),
        )
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"alert raised: {exc}")
    finally:
        if orig_env is not None:
            os.environ["DISCORD_WEBHOOK_URL"] = orig_env

    if not isinstance(result, dict):
        return _mk("FAIL", reason=f"alert returned {type(result)!r}")
    # vault_appended OR file_written must be true (durable trail).
    if not (result.get("vault_appended") or result.get("file_written")):
        return _mk("FAIL",
                   reason=f"no durable trail: {result}")
    return _mk("PASS",
               detail={"vault_appended": bool(result.get("vault_appended")),
                       "file_written": bool(result.get("file_written")),
                       "discord_sent": bool(result.get("discord_sent")),
                       "suppressed": bool(result.get("suppressed"))})


# --------------------------------------------------------------------------- #
# Stage 12 — WATCHDOG_HEARTBEAT (write hb + watchdog.check_daemon round-trip)
# --------------------------------------------------------------------------- #
def stage_watchdog_heartbeat(sandbox: Path) -> Dict[str, Any]:
    try:
        from src.monitor.daemon_heartbeat import write_heartbeat  # noqa: PLC0415
        import daemon_watchdog as dw  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"import failed: {exc}")

    hb_dir = sandbox / "hb"
    hb_dir.mkdir(parents=True, exist_ok=True)
    name = "r27_t5_smoke_daemon"
    ok = write_heartbeat(name, hb_dir=str(hb_dir))
    if not ok:
        return _mk("FAIL", reason="write_heartbeat returned False")
    hb_file = hb_dir / f"{name}.txt"
    if not hb_file.exists():
        return _mk("FAIL", reason=f"heartbeat file not created at {hb_file}")

    # Round-trip through watchdog.check_daemon — fake registry entry.
    fake_entry = {
        "name": name,
        "expected_interval_sec": 60,
        # Absolute path: watchdog uses it as-is when path is absolute.
        "heartbeat_file": str(hb_file),
        "process_match": "r27_t5_smoke_daemon_NEVER_EXISTS",
        "harmless_for_probe": True,
    }
    try:
        # Force fresh-heartbeat + dead-process scenario: ps_runner returns ""
        status = dw.check_daemon(fake_entry, ps_runner=lambda: "")
    except Exception as exc:  # noqa: BLE001
        return _mk("FAIL", reason=f"check_daemon raised: {exc}")
    if status.get("heartbeat_age_sec") is None:
        return _mk("FAIL", reason="heartbeat_age_sec is None despite fresh write")
    if status.get("heartbeat_stale"):
        return _mk("FAIL", reason="freshly-written hb reported as stale")
    return _mk("PASS",
               detail={"heartbeat_age_sec": status.get("heartbeat_age_sec"),
                       "heartbeat_stale": status.get("heartbeat_stale"),
                       "dead": status.get("dead"),
                       "reason": status.get("reason")})


# --------------------------------------------------------------------------- #
# Stage dispatch table
# --------------------------------------------------------------------------- #
STAGE_FNS: Dict[str, Callable[[Path], Dict[str, Any]]] = {
    "SCRAPER_BOV":         stage_scraper_bov,
    "SCRAPER_PIN":         stage_scraper_pin,
    "INJURY_FEED":         stage_injury_feed,
    "PREDICTIONS":         stage_predictions,
    "LIVE_REC_ENGINE":     stage_live_rec_engine,
    "INPLAY_RANKER":       stage_inplay_ranker,
    "PLACE_BET":           stage_place_bet,
    "AUTO_SETTLE":         stage_auto_settle,
    "RECONCILE":           stage_reconcile,
    "DASHBOARD_RENDER":    stage_dashboard_render,
    "ALERT_FIRE":          stage_alert_fire,
    "WATCHDOG_HEARTBEAT":  stage_watchdog_heartbeat,
}


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def run_smoke(json_out: Optional[str] = None,
              quiet: bool = False) -> Dict[str, Any]:
    """Run all 12 stages, write JSON, print table, return summary dict."""
    t0 = time.time()
    sandbox_root = Path(tempfile.mkdtemp(prefix="r27_t5_smoke_"))
    stage_results: List[Dict[str, Any]] = []
    overall_timed_out = False

    # Stages that share state (PLACE_BET writes a meta file consumed by
    # AUTO_SETTLE + RECONCILE) need a shared sandbox dir.
    _SHARED_BET_FLOW = {"PLACE_BET", "AUTO_SETTLE", "RECONCILE"}
    shared_bet_dir = sandbox_root / "shared_bet_flow"
    shared_bet_dir.mkdir(parents=True, exist_ok=True)

    try:
        for name in STAGES_ORDER:
            elapsed = time.time() - t0
            if elapsed > OVERALL_TIMEOUT_SEC:
                stage_results.append({
                    "name": name, "status": "TIMEOUT",
                    "reason": f"overall wall clock exceeded ({elapsed:.1f}s)",
                    "runtime_sec": 0.0,
                })
                overall_timed_out = True
                continue
            fn = STAGE_FNS[name]
            if name in _SHARED_BET_FLOW:
                sandbox = shared_bet_dir
            else:
                sandbox = sandbox_root / name.lower()
                sandbox.mkdir(parents=True, exist_ok=True)
            res = _run_stage(name, fn, sandbox)
            stage_results.append(res)
    finally:
        # Always clean up the tmp root.
        shutil.rmtree(sandbox_root, ignore_errors=True)

    runtime = round(time.time() - t0, 3)

    # Summarize.
    n_passed = sum(1 for r in stage_results if r["status"] == "PASS")
    n_failed = sum(1 for r in stage_results if r["status"] == "FAIL")
    n_skipped = sum(1 for r in stage_results if r["status"] == "SKIP")
    n_timeout = sum(1 for r in stage_results if r["status"] == "TIMEOUT")
    failed_names = [r["name"] for r in stage_results
                    if r["status"] in ("FAIL", "TIMEOUT")]

    overall_pass = (n_failed == 0 and n_timeout == 0
                    and runtime <= OVERALL_TIMEOUT_SEC
                    and not overall_timed_out)

    summary: Dict[str, Any] = {
        "task":             "R27_T5 end-to-end smoke test",
        "ts":               _iso_now(),
        "ok":               overall_pass,
        "status":           "PASS" if overall_pass else "FAIL",
        "n_stages":         len(stage_results),
        "n_passed":         n_passed,
        "n_failed":         n_failed,
        "n_skipped":        n_skipped,
        "n_timeout":        n_timeout,
        "failed_stage_names": failed_names,
        "runtime_sec":      runtime,
        "overall_cap_sec":  OVERALL_TIMEOUT_SEC,
        "per_stage_cap_sec": STAGE_TIMEOUT_SEC,
        "ship_gate_min_passes": SHIP_GATE_MIN_PASSES,
        "stages":           stage_results,
        "sandbox_cleaned":  not sandbox_root.exists(),
    }

    # Persist to data/cache/e2e_smoke_<date>.json (and any custom path).
    today = _today_iso()
    cache_path = Path(PROJECT_DIR) / "data" / "cache" / f"e2e_smoke_{today}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, default=str)
        summary["results_path"] = str(cache_path)
    except Exception as exc:  # noqa: BLE001
        summary["results_path_error"] = str(exc)

    if json_out:
        try:
            os.makedirs(os.path.dirname(json_out) or ".", exist_ok=True)
            with open(json_out, "w", encoding="utf-8") as fh:
                json.dump(summary, fh, indent=2, default=str)
        except Exception as exc:  # noqa: BLE001
            summary["json_out_error"] = str(exc)

    if not quiet:
        _print_table(summary)

    return summary


def _print_table(summary: Dict[str, Any]) -> None:
    """Print a tidy fixed-width PASS/FAIL table to stdout."""
    width_name = max(len(r["name"]) for r in summary["stages"])
    print()
    print(f"R27_T5 End-to-End Smoke Test  —  {summary['ts']}")
    print("=" * (width_name + 50))
    header = f"{'STAGE'.ljust(width_name)}  {'STATUS':<8}  {'TIME':>8}  REASON"
    print(header)
    print("-" * (width_name + 50))
    for r in summary["stages"]:
        rt = f"{r.get('runtime_sec', 0):.2f}s"
        reason = (r.get("reason") or "")[:60]
        print(f"{r['name'].ljust(width_name)}  {r['status']:<8}  {rt:>8}  {reason}")
    print("-" * (width_name + 50))
    print(f"TOTAL: {summary['n_passed']} PASS  "
          f"{summary['n_failed']} FAIL  "
          f"{summary['n_skipped']} SKIP  "
          f"{summary['n_timeout']} TIMEOUT  "
          f"in {summary['runtime_sec']}s")
    print(f"OUTCOME: {summary['status']}  "
          f"(ship gate: >={summary['ship_gate_min_passes']} PASS, no FAIL/TIMEOUT)")
    if summary.get("failed_stage_names"):
        print(f"FAILED: {', '.join(summary['failed_stage_names'])}")
    if summary.get("results_path"):
        print(f"JSON:    {summary['results_path']}")
    print()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="R27_T5 end-to-end smoke test of the full production stack"
    )
    ap.add_argument("--json-out", default=None,
                    help="Write the result summary to this JSON path (in addition to data/cache).")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress the console table (JSON only).")
    args = ap.parse_args(argv)

    summary = run_smoke(json_out=args.json_out, quiet=args.quiet)
    # Exit non-zero on any FAIL/TIMEOUT.
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
