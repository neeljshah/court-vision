"""nightly_report.py — Markdown summary of one day's predictions / bets / settlement.

Reads every per-date artifact the cycles 47-71 ops scripts produce and
emits a single Markdown report:

  data/predictions/<date>.csv  (cycle 47 + 49 - every prediction)
  data/bets/<date>.csv          (cycle 68 - recommended positive-EV bets)
  data/bets/<date>_settled.csv  (cycle 69 - bets with actual W/L + P&L)
  data/injuries_<date>.json     (cycle 43/60 - injury report)
  data/lineups_<date>.json      (cycle 61 - rotowire projected lineups)
  data/actuals/<date>.csv       (cycle 70 - post-game box scores)

Output:
  data/reports/<date>.md        (Markdown sections + summary tables)
  Console prints the same content.

Run:
    python scripts/nightly_report.py                  # today
    python scripts/nightly_report.py --date 2026-05-24
    python scripts/nightly_report.py --print          # stdout only, no file
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date as _date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = os.path.join(PROJECT_DIR, "data")


def _path(*parts: str) -> str:
    return os.path.join(_DATA, *parts)


def _read_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def section_predictions(rows: List[dict]) -> str:
    if not rows:
        return "## Predictions\n_no predictions saved for this date_\n"
    n_players = len({r["player_id"] for r in rows if r.get("player_id")})
    n_games = len({r["game_id"] for r in rows if r.get("game_id")})
    by_stat = defaultdict(list)
    for r in rows:
        try:
            by_stat[r["stat"]].append(float(r["pred"]))
        except (KeyError, ValueError):
            continue
    lines = [
        "## Predictions",
        f"- Total rows: **{len(rows)}**",
        f"- Unique players: **{n_players}**",
        f"- Games: **{n_games}**",
        "",
        "| stat | n | mean pred |",
        "|---|---|---|",
    ]
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        v = by_stat.get(stat)
        if v:
            lines.append(f"| {stat.upper()} | {len(v)} | {sum(v)/len(v):.2f} |")
    return "\n".join(lines) + "\n"


def section_injuries(payload: dict) -> str:
    players = payload.get("players", []) or []
    if not players:
        return "## Injuries\n_no injury report for this date_\n"
    by_status = defaultdict(int)
    for p in players:
        by_status[(p.get("status") or "").upper()] += 1
    by_team = defaultdict(int)
    for p in players:
        by_team[p.get("team", "?")] += 1
    src = payload.get("source_pdf", "?")
    fetched = payload.get("fetched_at", "?")
    lines = [
        "## Injuries",
        f"- Source: `{src}`",
        f"- Fetched: `{fetched}`",
        f"- Players listed: **{len(players)}**",
        "",
        "| status | count |",
        "|---|---|",
    ]
    for s in ("OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "AVAILABLE",
              "NOT WITH TEAM"):
        if by_status.get(s):
            lines.append(f"| {s} | {by_status[s]} |")
    return "\n".join(lines) + "\n"


def section_lineups(payload: dict) -> str:
    games = payload.get("games", []) or []
    if not games:
        return "## Lineups\n_no lineup data for this date_\n"
    n_starters = sum(len(g["home_lineup"]["starters"]) + len(g["away_lineup"]["starters"])
                       for g in games)
    by_status = defaultdict(int)
    for g in games:
        for side in ("home", "away"):
            by_status[g[f"{side}_lineup"]["status"]] += 1
    lines = [
        "## Lineups",
        f"- Games covered: **{len(games)}**",
        f"- Total projected starters: **{n_starters}**",
        "",
        "| lineup_status | count |",
        "|---|---|",
    ]
    for s in ("Confirmed", "Expected", "Projected", "Unknown"):
        if by_status.get(s):
            lines.append(f"| {s} | {by_status[s]} |")
    return "\n".join(lines) + "\n"


def section_bets(rows: List[dict]) -> str:
    if not rows:
        return "## Bets recommended\n_no bets logged for this date_\n"
    by_stat = defaultdict(int)
    total_kelly = 0.0
    for r in rows:
        by_stat[r.get("stat", "?")] += 1
        try:
            total_kelly += float(r.get("kelly_stake") or 0)
        except ValueError:
            pass
    # Top 5 by EV/$
    try:
        top = sorted(rows, key=lambda r: -float(r.get("ev_per_dollar") or 0))[:5]
    except Exception:
        top = rows[:5]
    lines = [
        "## Bets recommended",
        f"- Total bets logged: **{len(rows)}**",
        f"- Total Kelly stake: **${total_kelly:.2f}**",
        "",
        "Top 5 by EV per dollar:",
        "",
        "| player | stat | line | side | edge | EV/$ | Kelly% |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in top:
        lines.append(
            f"| {r.get('player', '?')} | {r.get('stat', '?')} | "
            f"{r.get('line', '?')} | {r.get('side', '?')} | "
            f"{r.get('edge', '?')} | {r.get('ev_per_dollar', '?')} | "
            f"{r.get('kelly_pct', '?')} |"
        )
    return "\n".join(lines) + "\n"


def section_settled(rows: List[dict]) -> str:
    if not rows:
        return "## Settlement\n_no settled file for this date — run `python scripts/daily_run.py --settle`_\n"
    matched = [r for r in rows if r.get("result") in ("W", "L", "P")]
    if not matched:
        return "## Settlement\n_settled file exists but no bets had actuals_\n"
    wins = sum(1 for r in matched if r["result"] == "W")
    losses = sum(1 for r in matched if r["result"] == "L")
    pushes = sum(1 for r in matched if r["result"] == "P")
    pnl = sum(float(r.get("pnl") or 0) for r in matched)
    # Top winners + losers
    try:
        top_wins = sorted(matched, key=lambda r: -float(r.get("pnl") or 0))[:3]
        top_losses = sorted(matched, key=lambda r: float(r.get("pnl") or 0))[:3]
    except Exception:
        top_wins = []; top_losses = []
    lines = [
        "## Settlement",
        f"- Bets matched: **{len(matched)}** / {len(rows)} logged",
        f"- Record: **{wins}-{losses}-{pushes}** (W-L-P)",
        f"- Win rate: **{100*wins/max(1, wins+losses):.1f}%** "
        f"(ignoring pushes)",
        f"- Total P&L: **${pnl:+.2f}**",
    ]
    if top_wins:
        lines += ["", "Top wins:"]
        for r in top_wins:
            if float(r.get("pnl") or 0) <= 0:
                continue
            lines.append(f"- {r.get('player', '?')} {r.get('stat', '?')} "
                          f"{r.get('side', '?')} {r.get('line', '?')}: "
                          f"+${float(r['pnl']):.2f}")
    if top_losses:
        lines += ["", "Top losses:"]
        for r in top_losses:
            if float(r.get("pnl") or 0) >= 0:
                continue
            lines.append(f"- {r.get('player', '?')} {r.get('stat', '?')} "
                          f"{r.get('side', '?')} {r.get('line', '?')}: "
                          f"${float(r['pnl']):.2f}")
    return "\n".join(lines) + "\n"


def build_report(date_str: str) -> str:
    pred_rows = _read_csv(_path("predictions", f"{date_str}.csv"))
    bet_rows = _read_csv(_path("bets", f"{date_str}.csv"))
    settled_rows = _read_csv(_path("bets", f"{date_str}_settled.csv"))
    injuries = _read_json(_path(f"injuries_{date_str}.json"))
    lineups = _read_json(_path(f"lineups_{date_str}.json"))
    header = f"# NBA prediction report — {date_str}\n"
    return "\n".join([
        header,
        section_predictions(pred_rows),
        section_injuries(injuries),
        section_lineups(lineups),
        section_bets(bet_rows),
        section_settled(settled_rows),
    ])


def write_report(md: str, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default=None,
                    help="Output path (default: data/reports/<date>.md)")
    ap.add_argument("--print", action="store_true",
                    help="Print to stdout only; don't write a file.")
    args = ap.parse_args()

    date_str = args.date or _date.today().isoformat()
    md = build_report(date_str)
    print(md)
    if args.print:
        return 0
    out = args.out or _path("reports", f"{date_str}.md")
    write_report(md, out)
    print(f"\n[nightly_report] wrote -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
