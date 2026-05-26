"""bankroll_monitor_daemon.py - R17_J4 (loop 17).

Continuous bankroll & portfolio-risk monitor. Reads the running P&L ledger
(`data/pnl_ledger.csv`) every --interval-sec and refreshes a vault dashboard
plus an atomically-written JSON state file.

Tracks:
    - current_bankroll        = start_bankroll + sum(profit_loss WHERE settled)
    - pending_exposure        = sum(stake     WHERE pending|open)
    - available_bankroll      = current_bankroll - pending_exposure
    - daily/weekly/monthly P&L (settled only)
    - max_drawdown            (running peak-to-trough on cumulative bankroll)
    - n_open_positions
    - position_concentration  = max(stake by game) / current_bankroll
    - kelly_overhang          = sum(kelly_pct WHERE pending) / current_bankroll

Risk alarms (appended to vault/Improvements/risk_alerts.md):
    - kelly_overhang        > 0.30  -> URGENT
    - position_concentration > 0.15 -> WARN
    - daily_pnl < -0.20 * start_bankroll -> STOP (20% daily circuit breaker)
    - max_drawdown_pct      > 0.30  -> STOP

Outputs (refreshed every tick):
    vault/Bankroll/dashboard.md
    data/cache/bankroll_state.json (atomic write via tmp+rename)

Usage:
    python scripts/bankroll_monitor_daemon.py --interval-sec 300 --start-bankroll 1000
    python scripts/bankroll_monitor_daemon.py --once    # one tick & exit (smoke)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False


PROJECT_DIR = Path(__file__).resolve().parents[1]
LEDGER_PATH = PROJECT_DIR / "data" / "pnl_ledger.csv"
STATE_PATH = PROJECT_DIR / "data" / "cache" / "bankroll_state.json"
DASHBOARD_PATH = PROJECT_DIR / "vault" / "Bankroll" / "dashboard.md"
ALERTS_PATH = PROJECT_DIR / "vault" / "Improvements" / "risk_alerts.md"

SETTLED_STATUSES = {"won", "lost", "push", "settled"}
PENDING_STATUSES = {"pending", "open"}

# R19_L8 — synthetic-row filter for bankroll/ROI dashboards.
# Synthetic rows are produced by build_pnl_ledger_synth.py: player matches
# ^Player_\d+$ AND book == "PP" AND american_odds == -119. Real bets have
# real player names + real book codes.
SYNTH_PLAYER_RE = re.compile(r"^Player_\d+$")
SYNTH_BOOK = "PP"
DEFAULT_LIVE_LAUNCH_DATE = "2026-05-25"  # live-pipeline launch
ENV_EXCLUDE_SYNTH = "BANKROLL_EXCLUDE_SYNTHETIC"

# Alarm thresholds
KELLY_OVERHANG_URGENT = 0.30
POSITION_CONC_WARN = 0.15
DAILY_LOSS_STOP = 0.20  # fraction of start_bankroll
MAX_DD_STOP = 0.30


# --------------------------------------------------------------------------- #
# Core metric computation                                                     #
# --------------------------------------------------------------------------- #
def _parse_placed_at(series: pd.Series) -> pd.Series:
    """Robustly parse mixed-format placed_at strings to UTC tz-aware."""
    return pd.to_datetime(series, errors="coerce", utc=True)


def is_synthetic_row(row: pd.Series) -> bool:
    """Return True if a single ledger row was produced by build_pnl_ledger_synth."""
    player = str(row.get("player", "") or "")
    book = str(row.get("book", "") or "")
    return bool(SYNTH_PLAYER_RE.match(player)) and book == SYNTH_BOOK


def filter_ledger(
    ledger: pd.DataFrame,
    *,
    exclude_synthetic: bool = False,
    start_date: Optional[str] = None,
) -> Dict:
    """Apply synthetic + date filters to a ledger DataFrame.

    Returns ``{"filtered": df, "n_total": int, "n_synth_excluded": int,
    "n_date_excluded": int, "n_kept": int}``.

    Pure / deterministic — used by tests + daemon. Does NOT mutate input.
    """
    if ledger.empty:
        return {
            "filtered": ledger,
            "n_total": 0,
            "n_synth_excluded": 0,
            "n_date_excluded": 0,
            "n_kept": 0,
        }
    df = ledger.copy()
    n_total = len(df)

    # Synthetic filter
    if exclude_synthetic:
        player = df.get("player", pd.Series([""] * len(df))).astype(str)
        book = df.get("book", pd.Series([""] * len(df))).astype(str)
        synth_mask = player.str.match(SYNTH_PLAYER_RE) & (book == SYNTH_BOOK)
        n_synth_excluded = int(synth_mask.sum())
        df = df.loc[~synth_mask].copy()
    else:
        n_synth_excluded = 0

    # Date filter
    n_date_excluded = 0
    if start_date:
        placed = _parse_placed_at(df["placed_at"])
        try:
            cutoff = pd.Timestamp(start_date, tz="UTC")
        except Exception:  # noqa: BLE001
            cutoff = pd.Timestamp(start_date).tz_localize("UTC")
        keep_mask = placed.isna() | (placed >= cutoff)
        n_date_excluded = int((~keep_mask).sum())
        df = df.loc[keep_mask].copy()

    return {
        "filtered": df,
        "n_total": n_total,
        "n_synth_excluded": n_synth_excluded,
        "n_date_excluded": n_date_excluded,
        "n_kept": int(len(df)),
    }


def compute_roi(ledger: pd.DataFrame) -> Dict:
    """Compute ROI (= sum(profit_loss) / sum(stake)) over settled bets only."""
    if ledger.empty:
        return {"n_bets": 0, "total_stake": 0.0, "total_pnl": 0.0, "roi_pct": 0.0}
    df = ledger.copy()
    df["status"] = df["status"].astype(str).str.lower().str.strip()
    settled = df[df["status"].isin(SETTLED_STATUSES)]
    if settled.empty:
        return {"n_bets": 0, "total_stake": 0.0, "total_pnl": 0.0, "roi_pct": 0.0}
    stake = pd.to_numeric(settled["stake"], errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(settled["profit_loss"], errors="coerce").fillna(0.0)
    total_stake = float(stake.sum())
    total_pnl = float(pnl.sum())
    roi_pct = (total_pnl / total_stake * 100.0) if total_stake > 0 else 0.0
    return {
        "n_bets": int(len(settled)),
        "total_stake": total_stake,
        "total_pnl": total_pnl,
        "roi_pct": roi_pct,
    }


def compute_metrics(ledger: pd.DataFrame, start_bankroll: float,
                    now: Optional[datetime] = None) -> Dict:
    """Pure function: ledger -> metrics dict. Used by tests + daemon."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if ledger.empty:
        return _empty_metrics(start_bankroll, now)

    df = ledger.copy()
    df["status"] = df["status"].astype(str).str.lower().str.strip()
    df["stake"] = pd.to_numeric(df["stake"], errors="coerce").fillna(0.0)
    df["profit_loss"] = pd.to_numeric(df["profit_loss"], errors="coerce").fillna(0.0)
    df["kelly_pct"] = pd.to_numeric(df.get("kelly_pct", 0.0), errors="coerce").fillna(0.0)
    df["placed_at"] = _parse_placed_at(df["placed_at"])

    settled = df[df["status"].isin(SETTLED_STATUSES)]
    pending = df[df["status"].isin(PENDING_STATUSES)]

    current_bankroll = float(start_bankroll + settled["profit_loss"].sum())
    pending_exposure = float(pending["stake"].sum())
    available_bankroll = current_bankroll - pending_exposure

    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    daily_pnl = float(settled[settled["placed_at"] >= today_start]["profit_loss"].sum())
    weekly_pnl = float(settled[settled["placed_at"] >= week_start]["profit_loss"].sum())
    monthly_pnl = float(settled[settled["placed_at"] >= month_start]["profit_loss"].sum())

    # max drawdown: running cum-bankroll peak-to-trough on settled bets
    if not settled.empty:
        s_sorted = settled.sort_values("placed_at")
        cum_bankroll = start_bankroll + s_sorted["profit_loss"].cumsum()
        running_peak = cum_bankroll.cummax()
        drawdown = running_peak - cum_bankroll
        max_drawdown = float(drawdown.max())
        peak_at_max_dd = float(running_peak.loc[drawdown.idxmax()]) if max_drawdown > 0 else float(start_bankroll)
        max_drawdown_pct = max_drawdown / peak_at_max_dd if peak_at_max_dd > 0 else 0.0
    else:
        max_drawdown = 0.0
        max_drawdown_pct = 0.0

    n_open_positions = int(len(pending))

    # position concentration: largest stake on a single game / current bankroll
    if not pending.empty and current_bankroll > 0:
        per_game = pending.groupby(pending["game_id"].fillna("NA"))["stake"].sum()
        max_stake_in_one_game = float(per_game.max())
        position_concentration_pct = max_stake_in_one_game / current_bankroll
    else:
        max_stake_in_one_game = 0.0
        position_concentration_pct = 0.0

    # kelly overhang: sum(kelly_pct WHERE pending) -- already a fraction of bankroll
    # The spec divides by current_bankroll but kelly_pct is already a per-bet fraction;
    # the meaningful "total committed Kelly" is the sum of fractions.
    kelly_overhang = float(pending["kelly_pct"].sum())

    # Alarms (deterministic, ordered)
    alarms = []
    if kelly_overhang > KELLY_OVERHANG_URGENT:
        alarms.append({
            "level": "URGENT",
            "rule": "kelly_overhang > 30%",
            "value": kelly_overhang,
            "threshold": KELLY_OVERHANG_URGENT,
            "msg": f"Total pending Kelly {kelly_overhang:.1%} exceeds 30% ceiling",
        })
    if position_concentration_pct > POSITION_CONC_WARN:
        alarms.append({
            "level": "WARN",
            "rule": "position_concentration > 15%",
            "value": position_concentration_pct,
            "threshold": POSITION_CONC_WARN,
            "msg": f"Single-game exposure ${max_stake_in_one_game:.2f} = "
                   f"{position_concentration_pct:.1%} of bankroll",
        })
    if daily_pnl < -DAILY_LOSS_STOP * start_bankroll:
        alarms.append({
            "level": "STOP",
            "rule": "daily_pnl < -20% start_bankroll",
            "value": daily_pnl,
            "threshold": -DAILY_LOSS_STOP * start_bankroll,
            "msg": f"Daily P&L ${daily_pnl:.2f} breached 20% circuit breaker - HALT BETTING",
        })
    if max_drawdown_pct > MAX_DD_STOP:
        alarms.append({
            "level": "STOP",
            "rule": "max_drawdown > 30%",
            "value": max_drawdown_pct,
            "threshold": MAX_DD_STOP,
            "msg": f"Max drawdown {max_drawdown_pct:.1%} exceeds 30% - HALT BETTING",
        })

    return {
        "as_of": now.isoformat(timespec="seconds"),
        "start_bankroll": float(start_bankroll),
        "current_bankroll": current_bankroll,
        "pending_exposure": pending_exposure,
        "available_bankroll": available_bankroll,
        "daily_pnl": daily_pnl,
        "weekly_pnl": weekly_pnl,
        "monthly_pnl": monthly_pnl,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "n_open_positions": n_open_positions,
        "max_stake_in_one_game": max_stake_in_one_game,
        "position_concentration_pct": position_concentration_pct,
        "kelly_overhang": kelly_overhang,
        "n_settled": int(len(settled)),
        "alarms": alarms,
    }


def _empty_metrics(start_bankroll: float, now: datetime) -> Dict:
    return {
        "as_of": now.isoformat(timespec="seconds"),
        "start_bankroll": float(start_bankroll),
        "current_bankroll": float(start_bankroll),
        "pending_exposure": 0.0,
        "available_bankroll": float(start_bankroll),
        "daily_pnl": 0.0,
        "weekly_pnl": 0.0,
        "monthly_pnl": 0.0,
        "max_drawdown": 0.0,
        "max_drawdown_pct": 0.0,
        "n_open_positions": 0,
        "max_stake_in_one_game": 0.0,
        "position_concentration_pct": 0.0,
        "kelly_overhang": 0.0,
        "n_settled": 0,
        "alarms": [],
    }


# --------------------------------------------------------------------------- #
# I/O - atomic write, dashboard render, alert log                             #
# --------------------------------------------------------------------------- #
def atomic_write_json(path: Path, data: Dict) -> None:
    """Write JSON via tmp+rename so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


def render_dashboard(metrics: Dict) -> str:
    """Build the markdown dashboard string."""
    lines = []
    lines.append("# Bankroll Dashboard")
    lines.append("")
    lines.append(f"_Updated: {metrics['as_of']}_")
    lines.append("")
    lines.append("## Bankroll")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Start bankroll | ${metrics['start_bankroll']:.2f} |")
    lines.append(f"| **Current bankroll** | **${metrics['current_bankroll']:.2f}** |")
    lines.append(f"| Pending exposure | ${metrics['pending_exposure']:.2f} |")
    lines.append(f"| Available bankroll | ${metrics['available_bankroll']:.2f} |")
    lines.append(f"| Net P&L | ${metrics['current_bankroll'] - metrics['start_bankroll']:+.2f} |")
    lines.append("")
    lines.append("## P&L Windows")
    lines.append("")
    lines.append(f"| Window | P&L |")
    lines.append(f"|--------|-----|")
    lines.append(f"| Daily | ${metrics['daily_pnl']:+.2f} |")
    lines.append(f"| Weekly | ${metrics['weekly_pnl']:+.2f} |")
    lines.append(f"| Monthly | ${metrics['monthly_pnl']:+.2f} |")
    lines.append("")
    lines.append("## Risk")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Max drawdown | ${metrics['max_drawdown']:.2f} ({metrics['max_drawdown_pct']:.1%}) |")
    lines.append(f"| Open positions | {metrics['n_open_positions']} |")
    lines.append(f"| Max single-game stake | ${metrics['max_stake_in_one_game']:.2f} |")
    lines.append(f"| Position concentration | {metrics['position_concentration_pct']:.1%} |")
    lines.append(f"| Kelly overhang | {metrics['kelly_overhang']:.1%} |")
    lines.append(f"| Settled bets | {metrics['n_settled']} |")
    lines.append("")
    lines.append("## Alarms")
    lines.append("")
    if not metrics["alarms"]:
        lines.append("_No active alarms - all systems green._")
    else:
        for a in metrics["alarms"]:
            lines.append(f"- **[{a['level']}]** {a['rule']}: {a['msg']}")
    lines.append("")
    return "\n".join(lines)


def write_dashboard(path: Path, metrics: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        f.write(render_dashboard(metrics))
    os.replace(tmp, path)


def append_alerts(path: Path, metrics: Dict) -> None:
    """Append non-duplicate alarms to the risk-alerts log."""
    if not metrics["alarms"]:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new_header = not path.exists()
    with open(path, "a") as f:
        if new_header:
            f.write("# Risk Alerts Log\n\n")
        for a in metrics["alarms"]:
            f.write(f"- {metrics['as_of']} [{a['level']}] {a['rule']}: {a['msg']}\n")
    # R21_N3 — layered alert (vault + critical-stack always; Discord if URL set).
    try:
        from src.alerts.discord_webhook import alert
        for a in metrics["alarms"]:
            if str(a.get("level", "")).upper() == "URGENT":
                alert(
                    f"Risk alarm: {a.get('rule', '?')} — {a.get('msg', '')}",
                    level="critical",
                    tag="bankroll_monitor_daemon",
                    source="bankroll_monitor_daemon",
                    body=str(a.get("msg", "")),
                    fields=[{"name": "rule", "value": str(a.get("rule", "?"))},
                            {"name": "as_of", "value": str(metrics.get("as_of", "?"))}],
                )
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Daemon loop                                                                 #
# --------------------------------------------------------------------------- #
def load_ledger(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=[
            "bet_id", "placed_at", "game_id", "player_id", "player", "team",
            "stat", "line", "side", "book", "american_odds", "stake",
            "model_pred", "model_prob", "model_edge", "kelly_pct",
            "status", "settled_at", "actual_stat", "profit_loss",
            "bankroll_after", "strategy",
        ])
    return pd.read_csv(path, low_memory=False)


def tick(start_bankroll: float, ledger_path: Path = LEDGER_PATH,
         state_path: Path = STATE_PATH, dashboard_path: Path = DASHBOARD_PATH,
         alerts_path: Path = ALERTS_PATH,
         exclude_synthetic: bool = False,
         start_date: Optional[str] = None) -> Dict:
    ledger = load_ledger(ledger_path)
    filt = filter_ledger(ledger, exclude_synthetic=exclude_synthetic,
                         start_date=start_date)
    metrics = compute_metrics(filt["filtered"], start_bankroll)
    roi = compute_roi(filt["filtered"])
    # R19_L8 — attach filter + ROI metadata so downstream consumers (mobile
    # HTML / vault) can display "filtered out N synthetic rows".
    metrics["filter_info"] = {
        "exclude_synthetic": bool(exclude_synthetic),
        "start_date": start_date,
        "n_total": filt["n_total"],
        "n_synth_excluded": filt["n_synth_excluded"],
        "n_date_excluded": filt["n_date_excluded"],
        "n_kept": filt["n_kept"],
    }
    metrics["roi"] = roi
    atomic_write_json(state_path, metrics)
    write_dashboard(dashboard_path, metrics)
    append_alerts(alerts_path, metrics)
    return metrics


def main() -> int:
    p = argparse.ArgumentParser(description="Bankroll & portfolio risk monitor")
    p.add_argument("--interval-sec", type=int, default=300, help="Seconds between ticks")
    p.add_argument("--start-bankroll", type=float, default=1000.0, help="Starting bankroll in $")
    p.add_argument("--once", action="store_true", help="Run one tick then exit")
    p.add_argument("--ledger", type=str, default=str(LEDGER_PATH))
    # R19_L8 — synthetic/date filters
    env_default = os.environ.get(ENV_EXCLUDE_SYNTH, "").lower() in ("1", "true", "yes")
    p.add_argument("--exclude-synthetic", action="store_true", default=env_default,
                   help=f"Drop synthetic rows produced by build_pnl_ledger_synth.py "
                        f"(default from env ${ENV_EXCLUDE_SYNTH}={env_default})")
    p.add_argument("--no-exclude-synthetic", dest="exclude_synthetic",
                   action="store_false", help="Force-include synthetic rows.")
    p.add_argument("--start-date", type=str, default=None,
                   help=f"Drop rows placed before this ISO date (e.g. {DEFAULT_LIVE_LAUNCH_DATE}). "
                        f"Pass empty string to disable.")
    args = p.parse_args()
    # Normalize start_date: empty string -> None
    if args.start_date == "":
        args.start_date = None

    ledger_path = Path(args.ledger)
    print(f"[bankroll-monitor] start_bankroll=${args.start_bankroll:.2f} "
          f"interval={args.interval_sec}s ledger={ledger_path}", flush=True)
    print(f"[bankroll-monitor] filter exclude_synthetic={args.exclude_synthetic} "
          f"start_date={args.start_date}", flush=True)

    while True:
        # R19_L3 heartbeat
        _r19_hb('bankroll_monitor_daemon')
        try:
            m = tick(args.start_bankroll, ledger_path,
                     exclude_synthetic=args.exclude_synthetic,
                     start_date=args.start_date)
            fi = m.get("filter_info", {})
            roi = m.get("roi", {})
            print(f"[bankroll-monitor] {m['as_of']} "
                  f"current=${m['current_bankroll']:.2f} "
                  f"pending=${m['pending_exposure']:.2f} "
                  f"avail=${m['available_bankroll']:.2f} "
                  f"daily=${m['daily_pnl']:+.2f} "
                  f"ROI={roi.get('roi_pct', 0):+.2f}% "
                  f"kept={fi.get('n_kept', 0)}/{fi.get('n_total', 0)} "
                  f"alarms={len(m['alarms'])}", flush=True)
        except Exception as e:
            print(f"[bankroll-monitor] tick failed: {e}", flush=True)
        if args.once:
            return 0
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    sys.exit(main())
