"""morning_briefing.py - daily wake-up report for the Strategy D bettor.

Glues iter-12 (strategy_d_daily_runner) + iter-13 (strategy_d_auto_settle)
into a single morning briefing covering:

    Section 1 - Yesterday's settle (auto-grades any dry-run-pending rows).
    Section 2 - Today's slate (auto-runs daily_runner if ledger not yet built).
    Section 3 - Running totals (career + last-7-day rolling).
    Section 4 - Calibration health (iter-8 isotonic Brier).
    Section 5 - Alerts (cold streak / concentration / stale caches).

Output: clean markdown to stdout + saved to vault/Reports/morning_briefing_<date>.md
if the vault path exists.

Usage:
    python scripts/morning_briefing.py
    python scripts/morning_briefing.py --date 2026-05-27

DOES NOT modify production scripts; imports + invokes them. DOES NOT call NBA
API directly (downstream scripts may, but only via their existing cached paths).
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from datetime import date as _date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

BETS_DIR = os.path.join(PROJECT_DIR, "data", "bets")
CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
VAULT_REPORTS = os.path.join(PROJECT_DIR, "vault", "Reports")
ROTOWIRE_HTML = os.path.join(CACHE_DIR, "rotowire_lineups.html")

DEFAULT_BANKROLL = 10000.0
EXPOSURE_PCT_WARN = 10.0
COLD_HIT_RATE_PCT = 30.0
COLD_MIN_BETS = 5
STALE_PRED_HOURS = 12
STALE_LINEUP_HOURS = 4


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _ledger_path(date_str: str) -> str:
    return os.path.join(BETS_DIR, f"strategy_d_{date_str}.csv")


def _load_csv(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _safe_float(s, default: float = 0.0) -> float:
    try:
        return float(s) if s not in (None, "",) else default
    except (TypeError, ValueError):
        return default


def _safe_int(s, default: int = -110) -> int:
    try:
        return int(float(s)) if s not in (None, "",) else default
    except (TypeError, ValueError):
        return default


def _payout(odds: int) -> float:
    return (odds / 100.0) if odds > 0 else (100.0 / -odds)


def _row_profit(r: Dict) -> float:
    """Return the realized profit on this row (negative for losses)."""
    status = (r.get("status") or "").lower()
    stake = _safe_float(r.get("stake"))
    odds = _safe_int(r.get("odds"))
    if status in ("win", "won"):
        # Trust ledger's stored profit if present; else compute.
        stored = _safe_float(r.get("profit"), default=float("nan"))
        if stored == stored:  # not NaN
            return stored
        return stake * _payout(odds)
    if status in ("loss", "lost"):
        return -stake
    return 0.0


def _file_age_hours(path: str) -> Optional[float]:
    if not os.path.exists(path):
        return None
    return (datetime.now().timestamp() - os.path.getmtime(path)) / 3600.0


# --------------------------------------------------------------------------- #
# Section 1 — Yesterday's settle                                              #
# --------------------------------------------------------------------------- #
def section_yesterday(date_str: str) -> str:
    y = (datetime.fromisoformat(date_str).date() - timedelta(days=1)).isoformat()
    path = _ledger_path(y)
    lines = [f"## Section 1 — Yesterday ({y})", ""]
    rows = _load_csv(path)
    if not rows:
        lines += ["_No bets placed yesterday (no ledger at "
                  f"`data/bets/strategy_d_{y}.csv`)._", ""]
        return "\n".join(lines)

    pending = [r for r in rows if (r.get("status") or "").lower()
               == "dry-run-pending"]
    if pending:
        lines.append(f"_{len(pending)} pending row(s) — triggering auto-settle..._")
        try:
            from scripts.strategy_d_auto_settle import settle_ledger
            settle_ledger(path, use_cdn=True)
        except Exception as e:  # pragma: no cover
            lines.append(f"> auto-settle warning: `{type(e).__name__}: {e}`")
        rows = _load_csv(path)
        lines.append("")

    counts = {"WIN": 0, "LOSS": 0, "PUSH": 0, "PENDING": 0}
    pnl = 0.0
    staked = 0.0
    enriched: List[Tuple[float, Dict]] = []
    for r in rows:
        status = (r.get("status") or "").upper()
        if status in ("WIN", "WON"):
            counts["WIN"] += 1
        elif status in ("LOSS", "LOST"):
            counts["LOSS"] += 1
        elif status in ("PUSH", "PUSHED"):
            counts["PUSH"] += 1
        else:
            counts["PENDING"] += 1
        staked += _safe_float(r.get("stake"))
        p = _row_profit(r)
        pnl += p
        enriched.append((p, r))

    roi = (pnl / staked * 100.0) if staked else 0.0
    lines += [
        f"- **Total bets:** {len(rows)} (WIN {counts['WIN']} / "
        f"LOSS {counts['LOSS']} / PUSH {counts['PUSH']} / "
        f"PENDING {counts['PENDING']})",
        f"- **Daily PnL:** ${pnl:+,.2f}  (staked ${staked:,.2f})",
        f"- **Daily ROI:** {roi:+.2f}%",
    ]

    graded = [(p, r) for p, r in enriched
              if (r.get("status") or "").upper() in
              ("WIN", "WON", "LOSS", "LOST")]
    if graded:
        graded.sort(key=lambda x: x[0], reverse=True)
        top_p, top_r = graded[0]
        bot_p, bot_r = graded[-1]
        lines.append(
            f"- **Top winner:** {top_r.get('player','?')} "
            f"{(top_r.get('stat') or '').upper()} "
            f"{(top_r.get('side') or '')[:1]} {top_r.get('line','')} "
            f"-> ${top_p:+,.2f}"
        )
        if bot_r is not top_r:
            lines.append(
                f"- **Biggest loser:** {bot_r.get('player','?')} "
                f"{(bot_r.get('stat') or '').upper()} "
                f"{(bot_r.get('side') or '')[:1]} {bot_r.get('line','')} "
                f"-> ${bot_p:+,.2f}"
            )
    lines.append("")
    return "\n".join(lines), counts, len(rows)  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Section 2 — Today's slate                                                   #
# --------------------------------------------------------------------------- #
def section_today(date_str: str, bankroll: float) -> Tuple[str, float]:
    path = _ledger_path(date_str)
    lines = [f"## Section 2 — Today ({date_str})", ""]

    if not os.path.exists(path):
        lines.append("_Ledger not present — invoking Strategy D daily runner..._")
        try:
            from scripts.strategy_d_daily_runner import main as runner_main
            runner_main(["--date", date_str, "--bankroll", str(bankroll)])
        except SystemExit:
            pass
        except Exception as e:  # pragma: no cover
            lines.append(f"> daily-runner warning: `{type(e).__name__}: {e}`")
        lines.append("")

    rows = _load_csv(path)
    if not rows:
        lines += ["_No Strategy D bets generated for today._", ""]
        return "\n".join(lines), 0.0

    exposure = sum(_safe_float(r.get("stake")) for r in rows)
    by_stat: Dict[str, int] = {"blk": 0, "fg3m": 0, "stl": 0}
    for r in rows:
        s = (r.get("stat") or "").lower()
        if s in by_stat:
            by_stat[s] += 1

    lines += [
        f"- **Total bets recommended:** {len(rows)}",
        f"- **Total exposure:** ${exposure:,.2f} "
        f"({exposure / bankroll * 100:.2f}% of ${bankroll:,.0f} bankroll)",
        "- **Per-stat breakdown:** "
        f"BLK {by_stat['blk']} / FG3M {by_stat['fg3m']} / STL {by_stat['stl']}",
        "",
        "### Top 3 bets (by |edge|)",
        "",
        "| # | Player | Stat | Side | Line | Model | Edge | Odds | Stake |",
        "|---|--------|------|------|------|-------|------|------|-------|",
    ]
    ranked = sorted(
        rows,
        key=lambda r: abs(_safe_float(r.get("edge"))),
        reverse=True,
    )[:3]
    for i, r in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {r.get('player','?')} "
            f"| {(r.get('stat') or '').upper()} "
            f"| {(r.get('side') or '')[:1]} "
            f"| {r.get('line','')} "
            f"| {r.get('model_pred','')} "
            f"| {_safe_float(r.get('edge')):+.2f} "
            f"| {_safe_int(r.get('odds')):+d} "
            f"| ${_safe_float(r.get('stake')):,.0f} |"
        )
    lines.append("")
    return "\n".join(lines), exposure


# --------------------------------------------------------------------------- #
# Section 3 — Running totals                                                  #
# --------------------------------------------------------------------------- #
def section_running(date_str: str) -> str:
    paths = sorted(glob.glob(os.path.join(BETS_DIR, "strategy_d_*.csv")))
    lines = ["## Section 3 — Running totals", ""]
    if not paths:
        lines += ["_No historical ledgers in `data/bets/`._", ""]
        return "\n".join(lines)

    today = datetime.fromisoformat(date_str).date()
    cutoff_7d = today - timedelta(days=7)

    career = {"bets": 0, "wins": 0, "losses": 0, "pushes": 0,
              "pending": 0, "staked": 0.0, "pnl": 0.0}
    rolling7 = {"bets": 0, "wins": 0, "losses": 0,
                "staked": 0.0, "pnl": 0.0}

    for p in paths:
        # Pull the date out of the filename — robust against stale 'date' cells.
        try:
            f_date = _date.fromisoformat(
                os.path.basename(p).replace("strategy_d_", "").replace(".csv", ""))
        except ValueError:
            f_date = None
        rows = _load_csv(p)
        for r in rows:
            status = (r.get("status") or "").upper()
            stake = _safe_float(r.get("stake"))
            profit = _row_profit(r)
            career["bets"] += 1
            career["staked"] += stake
            career["pnl"] += profit
            if status in ("WIN", "WON"):
                career["wins"] += 1
            elif status in ("LOSS", "LOST"):
                career["losses"] += 1
            elif status in ("PUSH", "PUSHED"):
                career["pushes"] += 1
            else:
                career["pending"] += 1

            if f_date is not None and cutoff_7d <= f_date <= today:
                rolling7["bets"] += 1
                rolling7["staked"] += stake
                rolling7["pnl"] += profit
                if status in ("WIN", "WON"):
                    rolling7["wins"] += 1
                elif status in ("LOSS", "LOST"):
                    rolling7["losses"] += 1

    settled = career["wins"] + career["losses"] + career["pushes"]
    career_hit = (career["wins"] / settled * 100.0) if settled else 0.0
    career_roi = (career["pnl"] / career["staked"] * 100.0
                  ) if career["staked"] else 0.0
    r7_settled = rolling7["wins"] + rolling7["losses"]
    r7_hit = (rolling7["wins"] / r7_settled * 100.0) if r7_settled else 0.0
    r7_roi = (rolling7["pnl"] / rolling7["staked"] * 100.0
              ) if rolling7["staked"] else 0.0

    lines += [
        f"### Career ({len(paths)} ledger day(s))",
        "",
        f"- **Bets:** {career['bets']} "
        f"(W {career['wins']} / L {career['losses']} / "
        f"P {career['pushes']} / Pend {career['pending']})",
        f"- **Hit rate:** {career_hit:.1f}%  (settled only)",
        f"- **Staked:** ${career['staked']:,.2f}",
        f"- **PnL:** ${career['pnl']:+,.2f}",
        f"- **ROI:** {career_roi:+.2f}%",
        "",
        "### Last 7 days",
        "",
        f"- **Bets:** {rolling7['bets']} "
        f"(W {rolling7['wins']} / L {rolling7['losses']})",
        f"- **Hit rate:** {r7_hit:.1f}%",
        f"- **ROI:** {r7_roi:+.2f}%  "
        f"(PnL ${rolling7['pnl']:+,.2f})",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Section 4 — Calibration health                                              #
# --------------------------------------------------------------------------- #
def section_calibration() -> str:
    """Report last-known iso calibrator Brier. Falls back to iter-8 audit values."""
    lines = ["## Section 4 — Calibration health", ""]
    metric_paths = [
        os.path.join(CACHE_DIR, "iso_calibrator_metrics.json"),
        os.path.join(PROJECT_DIR, "data", "models", "iso_calibrator_metrics.json"),
    ]
    found = None
    for mp in metric_paths:
        if os.path.exists(mp):
            found = mp
            break
    if found:
        import json
        try:
            d = json.load(open(found, encoding="utf-8"))
            raw = float(d.get("brier_raw", 0.0))
            cal = float(d.get("brier_cal", 0.0))
            improve = (raw - cal) / raw * 100.0 if raw else 0.0
            lines += [
                f"- Iso calibrator (`{os.path.basename(found)}`): "
                f"Brier raw **{raw:.3f}** -> cal **{cal:.3f}** "
                f"(**{improve:+.1f}%**)",
                "",
            ]
            return "\n".join(lines)
        except (OSError, ValueError) as e:
            lines.append(f"> calibration metric file unreadable: {e}")

    # Fallback to iter-8 audit (vault: Open Issues #19)
    lines += [
        "- Iso calibrator (iter-8 audit, vault Open Issues #19): "
        "Brier raw **0.265** -> cal **0.243** (**+8.2%**)",
        "- _No fresh `iso_calibrator_metrics.json` found — value is the "
        "last archived audit number._",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Section 5 — Alerts                                                          #
# --------------------------------------------------------------------------- #
def section_alerts(date_str: str, yesterday_counts: Dict[str, int],
                   yesterday_n: int, today_exposure: float,
                   bankroll: float) -> Tuple[str, List[str]]:
    triggered: List[str] = []

    # 5.1 Cold streak — yesterday hit < 30% over >= 5 bets
    settled_y = (yesterday_counts.get("WIN", 0)
                 + yesterday_counts.get("LOSS", 0))
    if settled_y >= COLD_MIN_BETS:
        hit = yesterday_counts["WIN"] / settled_y * 100.0
        if hit < COLD_HIT_RATE_PCT:
            triggered.append(
                f"COLD STREAK: yesterday hit rate {hit:.1f}% on "
                f"{settled_y} settled bets (< {COLD_HIT_RATE_PCT:.0f}% on "
                f">= {COLD_MIN_BETS} bets)."
            )

    # 5.2 Concentration risk — today exposure > 10% of bankroll
    exp_pct = (today_exposure / bankroll * 100.0) if bankroll else 0.0
    if exp_pct > EXPOSURE_PCT_WARN:
        triggered.append(
            f"CONCENTRATION: today's exposure ${today_exposure:,.2f} = "
            f"{exp_pct:.2f}% of bankroll (> {EXPOSURE_PCT_WARN:.0f}%)."
        )

    # 5.3 Stale predictions cache (>= 12 hours)
    pred_path = os.path.join(CACHE_DIR, f"predictions_cache_{date_str}.parquet")
    pred_age = _file_age_hours(pred_path)
    if pred_age is None:
        triggered.append(
            f"STALE PREDS: `predictions_cache_{date_str}.parquet` is missing."
        )
    elif pred_age >= STALE_PRED_HOURS:
        triggered.append(
            f"STALE PREDS: `predictions_cache_{date_str}.parquet` is "
            f"{pred_age:.1f}h old (>= {STALE_PRED_HOURS}h)."
        )

    # 5.4 Stale rotowire lineups html (>= 4 hours)
    lineup_age = _file_age_hours(ROTOWIRE_HTML)
    if lineup_age is None:
        triggered.append("STALE LINEUPS: `rotowire_lineups.html` is missing.")
    elif lineup_age >= STALE_LINEUP_HOURS:
        triggered.append(
            f"STALE LINEUPS: `rotowire_lineups.html` is "
            f"{lineup_age:.1f}h old (>= {STALE_LINEUP_HOURS}h)."
        )

    # 5.5 IN-PLAY DARK — yesterday had a game but no in-play snapshots landed.
    # (iter-27: this is the alert that would have caught the WCF G7 blackout.)
    try:
        y_dt = datetime.fromisoformat(date_str).date() - timedelta(days=1)
        y_str = y_dt.isoformat()
        # Did we register any bets for yesterday's game?
        intel_path = os.path.join(
            CACHE_DIR, f"intel_{y_str}", "tonight_bets_registered.json")
        inplay_path = os.path.join(
            PROJECT_DIR, "data", "predictions", f"{y_str}_inplay.csv")
        if os.path.exists(intel_path):
            n_inplay = 0
            if os.path.exists(inplay_path):
                with open(inplay_path, encoding="utf-8") as fh:
                    n_inplay = max(sum(1 for _ in fh) - 1, 0)
            if n_inplay == 0:
                triggered.append(
                    f"IN-PLAY DARK: a game was registered yesterday ({y_str}) "
                    f"but no in-play snapshots landed in "
                    f"data/predictions/{y_str}_inplay.csv. "
                    "Likely cause: live daemons silently died — see "
                    "data/cache/daemon_heartbeats/watchdog.log and rerun "
                    "live_orchestrator_watchdog.py for tonight."
                )
    except Exception:  # noqa: BLE001
        pass

    lines = ["## Section 5 — Alerts", ""]
    if not triggered:
        lines += ["_All clear._", ""]
    else:
        for a in triggered:
            lines.append(f"- **ALERT:** {a}")
        lines.append("")
    return "\n".join(lines), triggered


# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #
def build_briefing(date_str: str, bankroll: float) -> str:
    today = datetime.fromisoformat(date_str).date()
    parts: List[str] = []
    parts.append(f"# Morning Briefing — {today.isoformat()}\n")
    parts.append(f"_Generated {datetime.now().isoformat(timespec='seconds')}_\n")

    # Section 1 — returns (text, counts, n)
    y_out = section_yesterday(date_str)
    if isinstance(y_out, tuple):
        y_text, y_counts, y_n = y_out
    else:  # no rows
        y_text, y_counts, y_n = y_out, {"WIN": 0, "LOSS": 0, "PUSH": 0, "PENDING": 0}, 0
    parts.append(y_text)

    # Section 2
    t_text, t_exposure = section_today(date_str, bankroll)
    parts.append(t_text)

    # Section 3
    parts.append(section_running(date_str))

    # Section 4
    parts.append(section_calibration())

    # Section 5
    a_text, _ = section_alerts(date_str, y_counts, y_n, t_exposure, bankroll)
    parts.append(a_text)

    return "\n".join(parts)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Daily morning briefing for Strategy D bettor."
    )
    ap.add_argument("--date", default=None,
                    help="YYYY-MM-DD (default: today)")
    ap.add_argument("--bankroll", type=float, default=DEFAULT_BANKROLL,
                    help=f"Bankroll for % exposure calc (default ${DEFAULT_BANKROLL:,.0f})")
    args = ap.parse_args(argv)
    date_str = args.date or _date.today().isoformat()

    md = build_briefing(date_str, args.bankroll)
    print(md)

    if os.path.isdir(VAULT_REPORTS):
        out = os.path.join(VAULT_REPORTS, f"morning_briefing_{date_str}.md")
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(md)
            print(f"\n_Saved to_ `{out}`")
        except OSError as e:
            print(f"\n_could not save report: {e}_")

    return 0


if __name__ == "__main__":
    sys.exit(main())
