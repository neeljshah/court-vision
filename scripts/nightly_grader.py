"""nightly_grader.py — Nightly CLV grading pipeline (06:00 UTC daily).

Stages: fetch actuals → auto-settle → gate-1 CLV vs Pinnacle →
        roll data/clv/daily_clv.csv → vault append → Slack notify.

Manual:
    python scripts/nightly_grader.py --date 2026-05-26 --dry-run
    python scripts/nightly_grader.py --date 2026-05-26

Async (live_v2_app integration):
    create_supervised_task("nightly_grader", nightly_grader.schedule_nightly)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from math import sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

log = logging.getLogger("nightly_grader")
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[nightly_grader] %(asctime)s %(message)s",
                                      "%Y-%m-%dT%H:%M:%S"))
    log.addHandler(_h)
log.setLevel(logging.INFO)

_CLV_DIR       = PROJECT_DIR / "data" / "clv"
_DAILY_CLV_CSV = _CLV_DIR / "daily_clv.csv"
_VAULT_MD      = PROJECT_DIR / "vault" / "Improvements" / "CLV Tracker.md"
_DAILY_COLS    = [
    "date", "n_bets", "avg_clv_bps", "win_pct", "roi_pct",
    "total_stake", "total_pnl", "sharpe_30d", "kelly_eff", "model_correct_pct",
]


def _yesterday_utc() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


# ── Stage 1: fetch actuals ────────────────────────────────────────────────────

def _stage_fetch_actuals(date_str: str, dry_run: bool) -> Dict[str, Any]:
    out_path = PROJECT_DIR / "data" / "actuals" / f"{date_str}.csv"
    s: Dict[str, Any] = {"out_path": str(out_path), "n_rows": 0, "n_players": 0, "skipped": False}
    if dry_run:
        s.update(skipped=True, note="dry_run"); return s
    if out_path.exists():
        try:
            rows = list(csv.DictReader(open(out_path, encoding="utf-8")))
            s.update(n_rows=len(rows), n_players=len({r["player"] for r in rows}), note="cached")
        except Exception as exc:
            s["note"] = f"read error: {exc}"
        return s
    try:
        from scripts.fetch_actuals import fetch_actuals_for_date, write_csv  # noqa: PLC0415
        rows = fetch_actuals_for_date(date_str)
        if rows:
            write_csv(rows, str(out_path))
            s.update(n_rows=len(rows), n_players=len({r["player"] for r in rows}))
        else:
            s.update(skipped=True, note="no games / nba_api blocked")
    except Exception as exc:
        log.warning("fetch_actuals failed: %s", exc)
        s.update(skipped=True, note=str(exc))
    return s


# ── Stage 2: settle bets ──────────────────────────────────────────────────────

def _stage_settle(date_str: str, dry_run: bool) -> Dict[str, Any]:
    s: Dict[str, Any] = {"settled": 0, "voided": 0, "skipped": 0, "errored": 0}
    try:
        from scripts.auto_settle_daemon import tick  # noqa: PLC0415
        t = tick(dry_run=dry_run).get("totals", {})
        s.update(settled=t.get("settled", 0), voided=t.get("voided", 0),
                 skipped=t.get("skipped", 0), errored=t.get("errored", 0),
                 games=t.get("games", 0))
    except Exception as exc:
        log.warning("auto_settle tick failed: %s", exc)
        s["note"] = str(exc)
    return s


# ── Stage 3: Gate-1 CLV vs Pinnacle ──────────────────────────────────────────

def _stage_gate1_clv(dry_run: bool) -> Dict[str, Any]:
    s: Dict[str, Any] = {"n_bets": 0, "mean_clv_pct": 0.0, "positive_clv_rate": 0.0,
                          "per_stat": {}, "available": False}
    try:
        from scripts.gate1_clv_pinnacle import run as _run  # noqa: PLC0415
        r = _run(days=7, write_results=not dry_run)
        ov = r.get("overall", {})
        s.update(n_bets=ov.get("n_bets", 0), mean_clv_pct=ov.get("mean_clv_pct", 0.0),
                 positive_clv_rate=ov.get("positive_clv_rate", 0.0),
                 per_stat=r.get("per_stat", {}), available=bool(ov.get("n_bets")))
    except Exception as exc:
        log.warning("gate1_clv_pinnacle failed: %s", exc)
        s["note"] = str(exc)
    return s


# ── Stage 4a: day metrics from pnl_ledger ────────────────────────────────────

def _day_metrics(date_str: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"n_bets": 0, "win_pct": 0.0, "roi_pct": 0.0,
                            "total_stake": 0.0, "total_pnl": 0.0,
                            "kelly_eff": 0.0, "model_correct_pct": 0.0}
    try:
        from src.betting.pnl_ledger import all_bets  # noqa: PLC0415
    except Exception as exc:
        log.warning("pnl_ledger import failed: %s", exc); return out

    day = [b for b in all_bets()
           if (b.get("settled_at") or "").startswith(date_str)
           and b.get("status") in ("won", "lost", "push")]
    if not day:
        return out

    def _f(b: dict, k: str) -> float:
        try: return float(b.get(k) or 0)
        except (TypeError, ValueError): return 0.0

    profits = [_f(b, "profit_loss") for b in day]
    stakes  = [_f(b, "stake")       for b in day]
    n_won   = sum(1 for b in day if b.get("status") == "won")
    n       = len(day)
    ts      = sum(stakes); tp = sum(profits)

    kelly_vals = [_f(b, "kelly_pct") for b in day]
    avg_kelly  = sum(kelly_vals) / len(kelly_vals) if kelly_vals else 0.0
    avg_actual = (ts / n / max(ts, 1e-3)) if n else 0.0
    kelly_eff  = round(avg_actual / avg_kelly, 4) if avg_kelly > 0 else 0.0

    model_correct = sum(
        1 for b in day
        if b.get("status") == "won"
        and str(b.get("side", "")).upper() in ("OVER", "UNDER")
    )
    out.update(n_bets=n, win_pct=round(100.0 * n_won / n, 2),
               roi_pct=round(100.0 * tp / ts, 2) if ts else 0.0,
               total_stake=round(ts, 2), total_pnl=round(tp, 2),
               kelly_eff=kelly_eff,
               model_correct_pct=round(100.0 * model_correct / n, 2))
    return out


def _rolling_sharpe(window_days: int = 30) -> float:
    if not _DAILY_CLV_CSV.exists():
        return 0.0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    try:
        with open(_DAILY_CLV_CSV, encoding="utf-8") as f:
            roi_vals = [float(r["roi_pct"]) for r in csv.DictReader(f)
                        if r.get("date", "") >= cutoff and r.get("roi_pct")]
    except Exception:
        return 0.0
    if len(roi_vals) < 2:
        return 0.0
    mean_r = sum(roi_vals) / len(roi_vals)
    var_r  = sum((v - mean_r) ** 2 for v in roi_vals) / (len(roi_vals) - 1)
    sigma  = sqrt(var_r)
    return round(mean_r / sigma, 4) if sigma > 0 else 0.0


def _rolling_window(window_days: int = 30) -> Dict[str, Any]:
    if not _DAILY_CLV_CSV.exists():
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    try:
        with open(_DAILY_CLV_CSV, encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("date", "") >= cutoff]
    except Exception:
        return {}
    if not rows:
        return {}
    ts = sum(float(r.get("total_stake") or 0) for r in rows)
    tp = sum(float(r.get("total_pnl")   or 0) for r in rows)
    clv_vals = [float(r.get("avg_clv_bps") or 0) for r in rows]
    return {
        "n_days":      len(rows),
        "total_bets":  sum(int(r.get("n_bets") or 0) for r in rows),
        "roi_pct":     round(100.0 * tp / ts, 2) if ts else 0.0,
        "avg_clv_bps": round(sum(clv_vals) / len(clv_vals), 1) if clv_vals else 0.0,
        "sharpe":      _rolling_sharpe(window_days),
    }


# ── Stage 4b: write daily_clv.csv row ────────────────────────────────────────

def _append_daily_row(date_str: str, row: Dict[str, Any], dry_run: bool) -> None:
    _CLV_DIR.mkdir(parents=True, exist_ok=True)
    existing: List[Dict] = []
    if _DAILY_CLV_CSV.exists():
        try:
            with open(_DAILY_CLV_CSV, encoding="utf-8") as f:
                existing = list(csv.DictReader(f))
        except Exception:
            pass
    existing = [r for r in existing if r.get("date") != date_str]
    existing.append({c: row.get(c, "") for c in _DAILY_COLS})
    if dry_run:
        log.info("[dry-run] would write daily_clv row: %s", row)
        _upsert_clv_db(date_str, row, dry_run=True)
        return
    tmp = _DAILY_CLV_CSV.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_DAILY_COLS)
        w.writeheader(); w.writerows(existing)
    os.replace(tmp, _DAILY_CLV_CSV)
    log.info("daily_clv.csv updated (%d rows)", len(existing))
    _upsert_clv_db(date_str, row, dry_run=False)


def _upsert_clv_db(date_str: str, row: Dict[str, Any], *, dry_run: bool) -> None:
    """Mirror the CLV daily row into clv_summary_daily table."""
    if dry_run:
        log.info("[dry-run] would upsert clv_summary_daily for %s", date_str)
        return
    try:
        from database.bet_db import BetDB  # noqa: PLC0415
        BetDB().upsert_clv_daily(date_str, row)
        log.info("clv_summary_daily upserted for %s", date_str)
    except Exception as exc:
        log.warning("clv_summary_daily upsert failed: %s", exc)


# ── Stage 5: vault append ─────────────────────────────────────────────────────

def _append_vault(date_str: str, n_bets: int, roi_pct: float,
                   clv_bps: float, dry_run: bool) -> None:
    _VAULT_MD.parent.mkdir(parents=True, exist_ok=True)
    line = f"\n- **{date_str}** | n={n_bets} | ROI {roi_pct:+.1f}% | CLV {clv_bps:+.0f}bps"
    if dry_run:
        log.info("[dry-run] vault append: %s", line.strip()); return
    with open(_VAULT_MD, "a", encoding="utf-8") as f:
        f.write(line)


# ── Stage 6: Slack notification ───────────────────────────────────────────────

def _slack_notify(date_str: str, day: Dict[str, Any],
                   rolling: Dict[str, Any], dry_run: bool) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return False
    n, roi, clv = day.get("n_bets", 0), day.get("roi_pct", 0.0), day.get("avg_clv_bps", 0.0)
    win = f"{day.get('win_pct', 0.0):.1f}%" if n else "n/a"
    text = (
        f"Nightly CLV — {date_str}\n"
        f"Yesterday: {n} bets | ROI {roi:+.1f}% | CLV {clv:+.0f}bps | win {win}\n"
        f"30-day rolling: ROI {rolling.get('roi_pct', 0.0):+.1f}% | "
        f"CLV {rolling.get('avg_clv_bps', 0.0):+.0f}bps | "
        f"Sharpe {rolling.get('sharpe', 0.0):.2f}"
    )
    if dry_run:
        log.info("[dry-run] Slack notify: %s", text); return True
    try:
        import urllib.request  # noqa: PLC0415
        req = urllib.request.Request(
            url, data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        log.warning("Slack notify failed: %s", exc); return False


# ── Public entry point ────────────────────────────────────────────────────────

def run_once(date_str: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Run the full nightly grading pipeline for one date (default: yesterday UTC)."""
    if date_str is None:
        date_str = _yesterday_utc()
    log.info("starting  date=%s  dry_run=%s", date_str, dry_run)
    t0 = time.monotonic()

    s1 = _stage_fetch_actuals(date_str, dry_run)
    log.info("S1 actuals: rows=%d players=%d skipped=%s", s1["n_rows"], s1["n_players"], s1["skipped"])

    s2 = _stage_settle(date_str, dry_run)
    log.info("S2 settle: settled=%d voided=%d errored=%d", s2["settled"], s2["voided"], s2["errored"])

    s3 = _stage_gate1_clv(dry_run)
    log.info("S3 gate1_clv: n_bets=%d mean_clv=%.4f%% pos_rate=%.2f",
             s3["n_bets"], s3["mean_clv_pct"], s3["positive_clv_rate"])

    dm         = _day_metrics(date_str)
    clv_bps    = round(s3["mean_clv_pct"] * 100.0, 1)
    sharpe_30d = _rolling_sharpe(30)

    daily_row: Dict[str, Any] = {
        "date": date_str, "n_bets": dm["n_bets"] or s3["n_bets"],
        "avg_clv_bps": clv_bps, "win_pct": dm["win_pct"],
        "roi_pct": dm["roi_pct"], "total_stake": dm["total_stake"],
        "total_pnl": dm["total_pnl"], "sharpe_30d": sharpe_30d,
        "kelly_eff": dm["kelly_eff"], "model_correct_pct": dm["model_correct_pct"],
    }

    _append_daily_row(date_str, daily_row, dry_run)
    _append_vault(date_str, daily_row["n_bets"], daily_row["roi_pct"], clv_bps, dry_run)

    rolling    = _rolling_window(30)
    slack_sent = _slack_notify(date_str, {**daily_row, "avg_clv_bps": clv_bps}, rolling, dry_run)

    elapsed = round(time.monotonic() - t0, 2)
    log.info("done  elapsed=%.2fs  roi=%.2f%%  clv_bps=%.1f  slack=%s",
             elapsed, daily_row["roi_pct"], clv_bps, slack_sent)
    return {
        "date": date_str, "dry_run": dry_run, "elapsed_sec": elapsed,
        "stages": {"fetch_actuals": s1, "settle": s2, "gate1_clv": s3},
        "daily_row": daily_row, "rolling_30d": rolling, "slack_sent": slack_sent,
    }


# ── Async scheduler ───────────────────────────────────────────────────────────

async def schedule_nightly() -> None:
    """Sleep until 06:00 UTC, run once, repeat every 24h.

    Wrapped by create_supervised_task → auto-restarts on crash.
    """
    import asyncio  # noqa: PLC0415
    _TARGET_HOUR_UTC = 6
    while True:
        now_utc = datetime.now(timezone.utc)
        nxt = now_utc.replace(hour=_TARGET_HOUR_UTC, minute=0, second=0, microsecond=0)
        if nxt <= now_utc:
            nxt += timedelta(days=1)
        sleep_sec = (nxt - now_utc).total_seconds()
        log.info("next nightly run at %s UTC (in %.0fs)", nxt.isoformat(), sleep_sec)
        await asyncio.sleep(sleep_sec)
        try:
            await asyncio.to_thread(run_once)
        except Exception as exc:
            log.error("run_once failed: %s", exc)
        await asyncio.sleep(10)  # prevent same-second re-trigger


# ── CLI ───────────────────────────────────────────────────────────────────────

def _print_summary(s: Dict[str, Any]) -> None:
    dr, r = s["daily_row"], s.get("rolling_30d", {})
    print(f"\n=== Nightly CLV Grader — {s['date']} ===")
    if s["dry_run"]:
        print("  ** DRY RUN — no files written **")
    print(f"  S1 actuals : rows={s['stages']['fetch_actuals']['n_rows']}"
          f"  players={s['stages']['fetch_actuals']['n_players']}"
          f"  skipped={s['stages']['fetch_actuals']['skipped']}")
    print(f"  S2 settle  : settled={s['stages']['settle']['settled']}"
          f"  voided={s['stages']['settle']['voided']}"
          f"  errored={s['stages']['settle']['errored']}")
    print(f"  S3 gate1   : n_bets={s['stages']['gate1_clv']['n_bets']}"
          f"  mean_clv={s['stages']['gate1_clv']['mean_clv_pct']:+.4f}%"
          f"  pos_rate={s['stages']['gate1_clv']['positive_clv_rate']:.2%}")
    print(f"\n  Daily row ({s['date']}):")
    for k in _DAILY_COLS[1:]:
        print(f"    {k:<20} = {dr.get(k, '')}")
    if r:
        print(f"\n  Rolling 30d: n_days={r.get('n_days')}  total_bets={r.get('total_bets')}"
              f"  roi={r.get('roi_pct', 0.0):+.2f}%  clv={r.get('avg_clv_bps', 0.0):+.1f}bps"
              f"  sharpe={r.get('sharpe', 0.0):.2f}")
    print(f"\n  elapsed={s['elapsed_sec']:.2f}s  slack={s['slack_sent']}\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Nightly CLV grading pipeline")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday UTC)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute all stages but skip file writes and Slack notify")
    args = ap.parse_args(argv)
    _print_summary(run_once(date_str=args.date, dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
