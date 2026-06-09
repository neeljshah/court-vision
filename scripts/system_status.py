"""Single-page system state CLI for the live NBA betting infrastructure.

Prints one ASCII dashboard summarizing daemons, tonight's game, bankroll,
registered bets, recent alerts, last scrape times, slate freshness, and
health-check rollup. Designed for a pre-tipoff "is everything alive" glance.

Usage:
    python scripts/system_status.py
    python scripts/system_status.py --date 2026-05-26 --game-id 0042500315
    python scripts/system_status.py --watch          # re-print every 30s
    python scripts/system_status.py --watch --interval-sec 10

The script is read-only. It never spawns daemons, never writes files.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"
LINES = DATA / "lines"
HEARTBEATS = CACHE / "daemon_heartbeats"
VAULT_IMPR = ROOT / "vault" / "Improvements"

DEAD_MULTIPLIER = 3  # heartbeat older than expected_interval * 3 -> DEAD


# ---------------------------------------------------------------------------
# ASCII table helpers
# ---------------------------------------------------------------------------
def _box(title: str, rows: list[list[str]], headers: list[str] | None = None,
         width: int = 100) -> str:
    """Render a single-section ASCII box. Rows are list-of-list-of-strings."""
    out: list[str] = []
    bar = "+" + "-" * (width - 2) + "+"
    out.append(bar)
    out.append("| " + title.ljust(width - 4) + " |")
    out.append(bar)
    if headers:
        cols = _fit_columns([headers] + rows, width - 4)
        out.append("| " + _fmt_row(headers, cols) + " |")
        out.append("|" + "-" * (width - 2) + "|")
        for r in rows:
            out.append("| " + _fmt_row(r, cols) + " |")
    else:
        for r in rows:
            text = "  ".join(str(c) for c in r)
            out.extend(_wrap_line(text, width - 4))
    out.append(bar)
    return "\n".join(out)


def _fit_columns(rows: list[list[str]], total: int) -> list[int]:
    """Per-column width sized to longest value but capped to fit total width."""
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    widths = [0] * ncols
    for r in rows:
        for i, v in enumerate(r):
            widths[i] = max(widths[i], len(str(v)))
    # 2-space gutter between columns
    overhead = 2 * (ncols - 1)
    avail = total - overhead
    s = sum(widths)
    if s <= avail:
        return widths
    # Scale down proportionally, with a 6-char floor.
    scaled = [max(6, int(w * avail / s)) for w in widths]
    return scaled


def _fmt_row(row: list[str], cols: list[int]) -> str:
    parts: list[str] = []
    for i, w in enumerate(cols):
        v = str(row[i]) if i < len(row) else ""
        if len(v) > w:
            v = v[: max(1, w - 1)] + "…"
        parts.append(v.ljust(w))
    return "  ".join(parts)


def _wrap_line(text: str, width: int) -> list[str]:
    if not text:
        return ["| " + " " * width + " |"]
    out: list[str] = []
    while text:
        chunk = text[:width]
        text = text[width:]
        out.append("| " + chunk.ljust(width) + " |")
    return out


def _age_str(secs: float) -> str:
    if secs < 0:
        return "?"
    if secs < 60:
        return f"{secs:.0f}s"
    if secs < 3600:
        return f"{secs / 60:.1f}m"
    if secs < 86400:
        return f"{secs / 3600:.1f}h"
    return f"{secs / 86400:.1f}d"


def _mtime_age(path: Path, now: float) -> float | None:
    try:
        return now - path.stat().st_mtime
    except OSError:
        return None


# ---------------------------------------------------------------------------
# 1. Daemons
# ---------------------------------------------------------------------------
def _find_pid(process_match: str) -> str:
    """Best-effort local PID lookup. Windows uses wmic; POSIX uses pgrep."""
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["wmic", "process", "where",
                 f"CommandLine like '%{process_match}%' and not Name='wmic.exe'",
                 "get", "ProcessId", "/format:value"],
                stderr=subprocess.DEVNULL, timeout=5,
            ).decode(errors="ignore")
            for ln in out.splitlines():
                ln = ln.strip()
                if ln.startswith("ProcessId="):
                    pid = ln.split("=", 1)[1].strip()
                    if pid and pid != "0":
                        return pid
            return "-"
        out = subprocess.check_output(
            ["pgrep", "-f", process_match], stderr=subprocess.DEVNULL, timeout=5,
        ).decode(errors="ignore").strip()
        return out.splitlines()[0] if out else "-"
    except Exception:
        return "-"


def section_daemons(now: float) -> str:
    reg_path = ROOT / "scripts" / "daemon_registry.json"
    if not reg_path.exists():
        return _box("DAEMONS", [["daemon_registry.json missing"]])
    try:
        reg = json.loads(reg_path.read_text())
    except Exception as e:
        return _box("DAEMONS", [[f"failed to parse registry: {e}"]])
    rows: list[list[str]] = []
    for d in reg.get("daemons", []):
        name = d["name"]
        exp = d.get("expected_interval_sec", 0)
        hb = ROOT / d.get("heartbeat_file", "")
        if hb.exists():
            age = now - hb.stat().st_mtime
            if age > exp * DEAD_MULTIPLIER and exp > 0:
                status = f"DEAD ({_age_str(age)})"
            else:
                status = f"alive ({_age_str(age)})"
        else:
            opt = d.get("heartbeat_optional") or d.get("harmless_for_probe")
            status = "no-heartbeat (optional)" if opt else "MISSING"
        pid = _find_pid(d.get("process_match", name))
        rows.append([name, f"{exp}s", status, pid])
    headers = ["daemon", "interval", "status", "pid"]
    return _box(f"DAEMONS ({len(rows)} registered)", rows, headers)


# ---------------------------------------------------------------------------
# 2. Tonight's game
# ---------------------------------------------------------------------------
def _latest_pin_mainline(date_str: str, game_id: str | None) -> dict[str, Any]:
    path = LINES / f"{date_str}_pin_mainline.csv"
    if not path.exists():
        return {}
    latest: dict[str, dict] = {}
    try:
        with path.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get("market_type", ""), row.get("side", ""),
                       row.get("line", ""))
                latest[key] = row  # last-wins (file already chronological)
    except Exception:
        return {}
    ml_home = next((v for k, v in latest.items()
                    if k[0] == "moneyline" and k[1] == "home"), None)
    ml_away = next((v for k, v in latest.items()
                    if k[0] == "moneyline" and k[1] == "away"), None)
    spreads = [v for k, v in latest.items() if k[0] == "spread"]
    totals = [v for k, v in latest.items() if k[0] == "total"]
    # Pick a representative "current" total (closest to -110 over price).
    rep_total = None
    if totals:
        overs = [v for v in totals if v.get("side") == "over"]
        if overs:
            try:
                rep_total = min(overs, key=lambda v: abs(int(v["price"]) + 110))
            except Exception:
                rep_total = overs[0]
    rep_spread = None
    if spreads:
        homes = [v for v in spreads if v.get("side") == "home"]
        if homes:
            try:
                rep_spread = min(homes, key=lambda v: abs(int(v["price"]) + 110))
            except Exception:
                rep_spread = homes[0]
    return {
        "ml_home": ml_home, "ml_away": ml_away,
        "spread": rep_spread, "total": rep_total,
    }


def section_game(now: float, date_str: str, game_id: str | None) -> str:
    intel = CACHE / f"intel_{date_str}"
    m2 = intel / "m2_game.json"
    info: dict[str, Any] = {}
    if m2.exists():
        try:
            info = json.loads(m2.read_text())
        except Exception:
            info = {}
    if game_id and info.get("game_id") and info["game_id"] != game_id:
        info = {"game_id": game_id, "note": "no m2_game.json for this game_id"}
    mainline = _latest_pin_mainline(date_str, game_id)
    rows: list[list[str]] = []
    gid = info.get("game_id", game_id or "-")
    away, home = info.get("away_team", "?"), info.get("home_team", "?")
    label = info.get("game_label", f"{away} @ {home}")
    tip = info.get("tip_off_utc") or info.get("game_date") or "-"
    # tip_off_utc not always in m2; pull from registered bets if absent.
    if tip == info.get("game_date") or tip == "-":
        reg = intel / "tonight_bets_registered.json"
        if reg.exists():
            try:
                rj = json.loads(reg.read_text())
                tip = rj.get("tip_off_utc", tip)
            except Exception:
                pass
    rows.append(["game_id", gid])
    rows.append(["matchup", label])
    rows.append(["tip_off", tip])
    if mainline.get("ml_home") and mainline.get("ml_away"):
        rows.append([
            "Pin ML",
            f"{mainline['ml_home'].get('home_team', '?')} {mainline['ml_home'].get('price', '?')} / "
            f"{mainline['ml_away'].get('away_team', '?')} {mainline['ml_away'].get('price', '?')}",
        ])
    if mainline.get("spread"):
        s = mainline["spread"]
        rows.append(["Pin spread (home)", f"{s.get('line', '?')} @ {s.get('price', '?')}"])
    if mainline.get("total"):
        t = mainline["total"]
        rows.append(["Pin total (over)", f"{t.get('line', '?')} @ {t.get('price', '?')}"])
    if info.get("predictions"):
        p = info["predictions"]
        rows.append([
            "M2 model",
            f"p_home_win={p.get('p_home_win', '?')}  total={p.get('total_pts', '?')}  "
            f"diff={p.get('score_diff', '?')}",
        ])
    return _box(f"TONIGHT'S GAME ({date_str})", rows,
                headers=["field", "value"])


# ---------------------------------------------------------------------------
# 3. Bankroll
# ---------------------------------------------------------------------------
def section_bankroll(now: float) -> str:
    bj = DATA / "bankroll.json"
    rows: list[list[str]] = []
    if bj.exists():
        try:
            j = json.loads(bj.read_text())
            rows.append(["bankroll", f"${j.get('bankroll', '?'):.2f}"])
            rows.append(["start_bankroll", f"${j.get('start_bankroll', '?'):.2f}"])
            rows.append(["last_deposit", f"${j.get('last_deposit_amount', '?'):.2f} "
                                          f"({j.get('last_deposit_note', '-')})"])
            rows.append(["as_of", j.get("as_of", "?")])
        except Exception as e:
            rows.append(["bankroll.json", f"parse error: {e}"])
    else:
        rows.append(["bankroll.json", "missing"])
    pnl = DATA / "pnl_bankroll.csv"
    if pnl.exists():
        try:
            tail: list[str] = []
            with pnl.open() as f:
                for line in f:
                    tail.append(line.rstrip())
                    if len(tail) > 3:
                        tail = tail[-3:]
            rows.append(["pnl_bankroll.csv (tail)",
                         f"last 3 rows: {len(tail)}"])
            for ln in tail:
                rows.append(["  ", ln])
        except Exception as e:
            rows.append(["pnl_bankroll.csv", f"read error: {e}"])
    return _box("BANKROLL", rows, headers=["field", "value"])


# ---------------------------------------------------------------------------
# 4. Registered bets
# ---------------------------------------------------------------------------
def section_bets(now: float, date_str: str, game_id: str | None) -> str:
    f = CACHE / f"intel_{date_str}" / "tonight_bets_registered.json"
    if not f.exists():
        return _box("REGISTERED BETS", [["no tonight_bets_registered.json"]])
    try:
        j = json.loads(f.read_text())
    except Exception as e:
        return _box("REGISTERED BETS", [[f"parse error: {e}"]])
    bets = j.get("bets", [])
    if game_id:
        bets = [b for b in bets if str(b.get("game_id", "")) == game_id]
    total_stake = sum(float(b.get("stake", 0) or 0) for b in bets)
    rows: list[list[str]] = []
    rows.append(["registered_at", j.get("registered_at", "?")])
    rows.append(["mode", j.get("mode", "?")])
    rows.append(["game_label", j.get("game_label", "?")])
    rows.append(["n_bets", str(len(bets))])
    rows.append(["total_stake", f"${total_stake:,.2f}"])
    section_a = _box(f"REGISTERED BETS ({date_str})", rows,
                     headers=["field", "value"])
    if not bets:
        return section_a
    rows2: list[list[str]] = []
    for b in bets:
        rows2.append([
            f"{b.get('player', '?')}",
            f"{b.get('stat', '?').upper()} {b.get('side', '?')} {b.get('line', '?')}",
            f"{b.get('book', '?')} {b.get('odds', '?')}",
            f"${float(b.get('stake', 0) or 0):.0f}",
            f"EV {b.get('ev_pct', '?')}%",
        ])
    section_b = _box("BET DETAIL", rows2,
                     headers=["player", "market", "book/odds", "stake", "edge"])
    return section_a + "\n" + section_b


# ---------------------------------------------------------------------------
# 5. Recent alerts
# ---------------------------------------------------------------------------
def section_alerts(now: float, date_str: str) -> str:
    log = VAULT_IMPR / f"alerts_{date_str}.log"
    if not log.exists():
        return _box(f"RECENT ALERTS ({date_str})",
                    [[f"alerts_{date_str}.log not found"]])
    try:
        with log.open(encoding="utf-8", errors="ignore") as f:
            tail = [ln.rstrip() for ln in f.readlines() if ln.strip()]
        tail = tail[-5:] if len(tail) > 5 else tail
    except Exception as e:
        return _box(f"RECENT ALERTS ({date_str})", [[f"read error: {e}"]])
    rows = [[ln] for ln in tail] or [["(empty)"]]
    age = _mtime_age(log, now)
    title = f"RECENT ALERTS ({date_str}) — file age {_age_str(age) if age is not None else '?'}"
    return _box(title, rows)


# ---------------------------------------------------------------------------
# 6. Last scrape times
# ---------------------------------------------------------------------------
def section_scrapes(now: float, date_str: str) -> str:
    rows: list[list[str]] = []
    for tag in ("pin", "bov", "fd"):
        for suffix in ("", "_mainline"):
            f = LINES / f"{date_str}_{tag}{suffix}.csv"
            if not f.exists():
                continue
            age = _mtime_age(f, now)
            size_kb = f.stat().st_size / 1024
            rows.append([
                f"{tag}{suffix}.csv", _age_str(age) if age is not None else "?",
                f"{size_kb:.1f} KB",
                datetime.fromtimestamp(f.stat().st_mtime).strftime("%H:%M:%S"),
            ])
    if not rows:
        rows.append(["no scrape files for date", "-", "-", "-"])
    return _box(f"LAST SCRAPE TIMES ({date_str})", rows,
                headers=["file", "age", "size", "mtime"])


# ---------------------------------------------------------------------------
# 7. Slate freshness
# ---------------------------------------------------------------------------
def section_slate(now: float, date_str: str) -> str:
    intel = CACHE / f"intel_{date_str}"
    targets = [
        intel / f"slate_fresh_{date_str}.parquet",
        intel / f"slate_with_teammate_out_{date_str}.parquet",
        intel / "ev_final_top25.csv",
        intel / "mc_tonight.json",
    ]
    rows: list[list[str]] = []
    for f in targets:
        if f.exists():
            age = _mtime_age(f, now)
            rows.append([f.name, _age_str(age) if age is not None else "?",
                         f"{f.stat().st_size / 1024:.1f} KB"])
        else:
            rows.append([f.name, "MISSING", "-"])
    return _box(f"SLATE FRESHNESS ({date_str})", rows,
                headers=["file", "age", "size"])


# ---------------------------------------------------------------------------
# 8. Health summary
# ---------------------------------------------------------------------------
def section_health(now: float) -> str:
    hc = ROOT / "scripts" / "health_check.py"
    if not hc.exists():
        return _box("HEALTH SUMMARY", [["health_check.py missing"]])
    try:
        # health_check exits non-zero when any ERROR found, but stdout is still
        # valid JSON. Use Popen so we can grab stdout regardless of exit code.
        proc = subprocess.Popen(
            [sys.executable, str(hc), "--json", "--skip-network"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=str(ROOT),
        )
        try:
            out, _ = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            return _box("HEALTH SUMMARY", [["health_check timed out (>60s)"]])
        text = out.decode(errors="ignore").strip()
        if not text:
            return _box("HEALTH SUMMARY",
                        [[f"health_check produced no output (exit={proc.returncode})"]])
        j = json.loads(text)
    except Exception as e:
        return _box("HEALTH SUMMARY", [[f"health_check failed: {e}"]])
    summ = j.get("summary", {})
    checks = j.get("checks", [])
    rows = [
        ["OK", str(summ.get("ok", "?"))],
        ["WARN", str(summ.get("warn", "?"))],
        ["ERROR", str(summ.get("error", "?"))],
        ["total checks", str(len(checks))],
        ["timestamp", j.get("timestamp", "?")],
    ]
    bad = [c for c in checks if c.get("status") in ("WARN", "ERROR")]
    section_a = _box("HEALTH SUMMARY", rows, headers=["status", "count"])
    if not bad:
        return section_a
    rows2 = [[c["status"], c["name"], c["detail"][:60]] for c in bad[:10]]
    section_b = _box(f"HEALTH ISSUES (first {len(rows2)} of {len(bad)})",
                     rows2, headers=["sev", "check", "detail"])
    return section_a + "\n" + section_b


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def render(date_str: str, game_id: str | None,
           skip_health: bool = False) -> str:
    now = time.time()
    parts: list[str] = []
    width = 100
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    banner = "+" + "=" * (width - 2) + "+"
    parts.append(banner)
    parts.append("| " + f"NBA SYSTEM STATUS  |  {ts}  |  date={date_str}"
                 f"  game={game_id or 'ALL'}".ljust(width - 4) + " |")
    parts.append(banner)
    parts.append(section_daemons(now))
    parts.append(section_game(now, date_str, game_id))
    parts.append(section_bankroll(now))
    parts.append(section_bets(now, date_str, game_id))
    parts.append(section_alerts(now, date_str))
    parts.append(section_scrapes(now, date_str))
    parts.append(section_slate(now, date_str))
    if not skip_health:
        parts.append(section_health(now))
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                    help="date in YYYY-MM-DD (default: today)")
    ap.add_argument("--game-id", default=None,
                    help="focus on a single NBA game_id (e.g. 0042500315)")
    ap.add_argument("--watch", action="store_true",
                    help="re-print every --interval-sec until Ctrl+C")
    ap.add_argument("--interval-sec", type=int, default=30,
                    help="watch interval (default 30s)")
    ap.add_argument("--skip-health", action="store_true",
                    help="skip the health_check subprocess (faster)")
    args = ap.parse_args(argv)

    if not args.watch:
        print(render(args.date, args.game_id, skip_health=args.skip_health))
        return 0
    try:
        while True:
            # clear screen between renders
            if os.name == "nt":
                os.system("cls")
            else:
                sys.stdout.write("\x1b[2J\x1b[H")
                sys.stdout.flush()
            print(render(args.date, args.game_id, skip_health=args.skip_health))
            print(f"\n[watch] sleeping {args.interval_sec}s — Ctrl+C to exit")
            time.sleep(args.interval_sec)
    except KeyboardInterrupt:
        print("\n[watch] stopped by user")
        return 0


if __name__ == "__main__":
    sys.exit(main())
