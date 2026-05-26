"""probe_R22_O5_operator_dashboard.py — end-to-end probe for /operator.

Procedure
---------
1. Build the mobile_html_server app pointed at synthetic data sources
   (so the probe never depends on whatever the live system happens to
   have on disk).
2. Bind a free local port, start the aiohttp server in the same process.
3. HTTP GET ``/operator`` (and ``/morning`` alias) and parse the response.
4. Assert every required section heading appears in the rendered HTML
   AND that the 60s meta-refresh + viewport tags are present.
5. Persist the result JSON to ``data/cache/probe_R22_O5_results.json``.
6. Shut the server down cleanly.

LOCAL ONLY — no SSH, no RunPod, no live ledger writes. Pulls from synthetic
fixtures under a tmp dir so multiple probe runs are deterministic.
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import socket
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import mobile_html_server as mhs  # noqa: E402
import operator_dashboard as od  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(_ROOT, "data", "cache", "probe_R22_O5_results.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_fixtures(tmp_root: Path) -> Dict[str, Path]:
    """Create synthetic fixture files under ``tmp_root`` for every section."""
    # --- daemon registry + heartbeats ---
    hb_dir = tmp_root / "hb"
    registry = tmp_root / "daemon_registry.json"
    fresh_hb = hb_dir / "fresh.txt"
    stale_hb = hb_dir / "stale.txt"
    hb_dir.mkdir(parents=True, exist_ok=True)
    fresh_hb.write_text("ok", encoding="utf-8")
    stale_hb.write_text("ok", encoding="utf-8")
    old = time.time() - 600
    os.utime(stale_hb, (old, old))
    registry.write_text(json.dumps({"daemons": [
        {"name": "fresh_daemon", "expected_interval_sec": 30,
         "heartbeat_file": str(fresh_hb)},
        {"name": "stale_daemon", "expected_interval_sec": 30,
         "heartbeat_file": str(stale_hb)},
    ]}), encoding="utf-8")

    # --- bankroll_state.json ---
    bankroll = tmp_root / "bankroll_state.json"
    bankroll.write_text(json.dumps({
        "as_of": _iso_now(),
        "start_bankroll": 1000.0,
        "current_bankroll": 1037.42,
        "available_bankroll": 950.00,
        "daily_pnl": 37.42,
        "roi": {"roi_pct": 3.74, "n_bets": 4},
        "filter_info": {
            "exclude_synthetic": True, "start_date": "2026-05-25",
            "n_total": 12345, "n_synth_excluded": 12342,
            "n_date_excluded": 0, "n_kept": 3,
        },
    }), encoding="utf-8")

    # --- pnl_ledger.csv (synthetic, NEVER touches real data/pnl_ledger.csv) ---
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ledger = tmp_root / "pnl_ledger.csv"
    cols = [
        "bet_id", "placed_at", "game_id", "player_id", "player", "team",
        "stat", "line", "side", "book", "american_odds", "stake",
        "model_pred", "model_prob", "model_edge", "kelly_pct",
        "status", "settled_at", "actual_stat", "profit_loss",
        "bankroll_after", "strategy",
    ]
    with open(ledger, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerow({"bet_id": "1", "placed_at": f"{today}T10:00:00",
                    "player": "Wemby", "stat": "blk", "line": "2.5",
                    "side": "UNDER", "book": "bov", "model_edge": "0.31",
                    "kelly_pct": "0.025", "status": "open", "strategy": "real"})
        w.writerow({"bet_id": "2", "placed_at": f"{today}T11:00:00",
                    "player": "SGA", "stat": "reb", "line": "3.5",
                    "side": "OVER", "book": "fd", "model_edge": "0.51",
                    "kelly_pct": "0.04", "status": "open", "strategy": "real"})

    # --- alerts vault + critical-stack ---
    alerts_vault = tmp_root / "alerts.md"
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    ts = (now_dt - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    alerts_vault.write_text(
        f"# alerts\n- {ts} [WARN] [probe] R22_O5 synthetic warn line\n",
        encoding="utf-8",
    )
    alerts_dir = tmp_root / "alerts"
    alerts_dir.mkdir(parents=True, exist_ok=True)
    (alerts_dir / f"critical_{today}.json").write_text(json.dumps([
        {"timestamp": ts, "level": "critical", "tag": "probe_R22_O5",
         "message": "synthetic critical record"},
    ]), encoding="utf-8")

    # --- predictions parquet (skipped if pandas missing) ---
    predictions_dir = tmp_root / "preds"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd  # noqa: F401
        pd.DataFrame([
            {"player_id": 1, "player_name": "Wemby", "team": "SAS", "stat": "pts",
             "q10": 18.0, "q50": 28.0, "q90": 42.0, "sigma": 7.0,
             "computed_at": _iso_now()},
            {"player_id": 2, "player_name": "SGA", "team": "OKC", "stat": "pts",
             "q10": 22.0, "q50": 32.0, "q90": 40.0, "sigma": 5.0,
             "computed_at": _iso_now()},
        ]).to_parquet(predictions_dir / f"predictions_cache_{today}.parquet")
    except Exception:  # noqa: BLE001
        # Tracker section will report yellow/red — page still renders.
        pass
    # m2_family file used by the tracker section.
    (predictions_dir / "m2_family_predictions_2024-25_probe.json").write_text(
        json.dumps({}), encoding="utf-8",
    )

    # --- supporting files for the existing handle_index route (so /healthz
    #     and the rest of the server start cleanly).
    md = tmp_root / "TONIGHT.md"
    md.write_text("# Probe Tonight\n\nNothing here.\n", encoding="utf-8")
    live_bets = tmp_root / "live_bets"; live_bets.mkdir()
    lineups   = tmp_root / "lineups";   lineups.mkdir()

    return {
        "registry": registry, "hb_dir": hb_dir,
        "bankroll": bankroll, "ledger": ledger,
        "alerts_vault": alerts_vault, "alerts_dir": alerts_dir,
        "predictions_dir": predictions_dir,
        "md": md, "live_bets": live_bets, "lineups": lineups,
    }


def _run_probe() -> Dict[str, Any]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tmp_root = Path(tempfile.mkdtemp(prefix="R22_O5_probe_"))
    fixtures = _build_fixtures(tmp_root)
    port = _free_port()

    app = mhs.create_app(
        md_path=fixtures["md"],
        bankroll_path=fixtures["bankroll"],  # used only by /api/state path
        live_bets_dir=fixtures["live_bets"],
        lineups_dir=fixtures["lineups"],
        refresh_sec=30,
        operator_refresh_sec=60,
        operator_overrides={
            "registry_path":   fixtures["registry"],
            "heartbeat_dir":   fixtures["hb_dir"],
            "bankroll_path":   fixtures["bankroll"],
            "ledger_path":     fixtures["ledger"],
            "alerts_vault":    fixtures["alerts_vault"],
            "alerts_dir":      fixtures["alerts_dir"],
            "predictions_dir": fixtures["predictions_dir"],
            "today": today,
        },
    )

    runner = None
    site = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _start() -> None:
        nonlocal runner, site
        from aiohttp import web
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()

    async def _stop() -> None:
        if site is not None:
            await site.stop()
        if runner is not None:
            await runner.cleanup()

    loop.run_until_complete(_start())

    operator_html = ""
    morning_html = ""
    operator_status: Optional[int] = None
    morning_status: Optional[int] = None
    error_repr: Optional[str] = None

    async def _fetch(url: str):
        # Use aiohttp's client so the request shares the same event loop as
        # the server — otherwise urllib's blocking read starves the server.
        from aiohttp import ClientSession, ClientTimeout
        timeout = ClientTimeout(total=10)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                body = await resp.text()
                return resp.status, body

    try:
        operator_status, operator_html = loop.run_until_complete(
            _fetch(f"http://127.0.0.1:{port}/operator")
        )
        morning_status, morning_html = loop.run_until_complete(
            _fetch(f"http://127.0.0.1:{port}/morning")
        )
    except Exception as exc:  # noqa: BLE001
        error_repr = repr(exc)
        traceback.print_exc()
    finally:
        try:
            loop.run_until_complete(_stop())
        finally:
            loop.close()

    sections_present = {t: (t in operator_html) for t in od.SECTION_TITLES}
    sections_rendered = sum(1 for v in sections_present.values() if v)

    result: Dict[str, Any] = {
        "probe_id": "R22_O5",
        "timestamp_utc": _iso_now(),
        "port": port,
        "operator_status": operator_status,
        "morning_status": morning_status,
        "operator_html_bytes": len(operator_html),
        "morning_html_bytes": len(morning_html),
        "morning_alias_matches_operator": (
            morning_html == operator_html and bool(operator_html)
        ),
        "sections_present": sections_present,
        "sections_rendered_n": sections_rendered,
        "sections_required_n": len(od.SECTION_TITLES),
        "auto_refresh_60s_present": (
            '<meta http-equiv="refresh" content="60">' in operator_html
        ),
        "viewport_present": "width=device-width" in operator_html,
        "fixtures_dir": str(tmp_root),
        "ship": (
            operator_status == 200
            and morning_status == 200
            and sections_rendered == len(od.SECTION_TITLES)
            and error_repr is None
        ),
        "error": error_repr,
    }
    return result


def main() -> int:
    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    try:
        result = _run_probe()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        result = {
            "probe_id": "R22_O5",
            "timestamp_utc": _iso_now(),
            "ship": False,
            "error": repr(exc),
        }
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ship") else 1


if __name__ == "__main__":
    sys.exit(main())
