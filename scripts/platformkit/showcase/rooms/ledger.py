"""ledger.json room: paper-position ledger aggregates (units/status counts
only -- never bet_id, never currency sums, never roi/pnl/bankroll/profit).
Stdlib only.
"""
from __future__ import annotations

import glob
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from scripts.platformkit.showcase.common import FRONTEND, read_json, read_jsonl, receipt, unavailable

CLV_LEDGER = FRONTEND / "clv_ledger.jsonl"
CLV_SCOREBOARD = FRONTEND / "ops" / "clv_scoreboard.json"
FRAMING = "CLV is the yardstick; measurement infrastructure, not an edge claim."

_BANNED = ("roi", "bankroll", "pnl", "profit")


def _has_banned(text: str) -> bool:
    low = text.lower()
    return any(tok in low for tok in _BANNED)


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "bet_id":
                continue
            if isinstance(k, str) and _has_banned(k):
                continue
            if isinstance(v, str) and _has_banned(v):
                continue
            out[k] = _scrub(v)
        return out
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def _scoreboard_summary() -> dict | None:
    data = read_json(CLV_SCOREBOARD)
    if not data:
        return None
    out = {"coverage_pct": data.get("coverage_pct"),
           "total_settled": data.get("total_settled"),
           "total_measurable": data.get("total_measurable")}
    channels = []
    for name, ch in (data.get("channels") or {}).items():
        channels.append(_scrub({
            "channel": name, "label": ch.get("label"),
            "n_settled": ch.get("n_settled"), "n_measurable": ch.get("n_measurable"),
            "coverage_pct": ch.get("coverage_pct")}))
    out["channels"] = channels
    return out


def _reconcile_summaries() -> list[dict]:
    summaries = []
    for path in sorted(Path(p) for p in glob.glob(str(FRONTEND / "ops" / "clv_reconcile_*.json"))):
        data = read_json(path)
        if not data:
            continue
        summaries.append(_scrub({
            "channel": data.get("channel"), "label": data.get("label"),
            "n_measurable": data.get("n_measurable"), "verdict": data.get("verdict")}))
    return summaries


def build() -> dict:
    if not CLV_LEDGER.exists():
        return unavailable(f"missing {CLV_LEDGER}")
    rows = read_jsonl(CLV_LEDGER)
    if not rows:
        return unavailable(f"empty/unreadable {CLV_LEDGER}")

    status_counts = Counter(r.get("status", "unknown") for r in rows)
    venues = sorted({r.get("taken_book") for r in rows if r.get("taken_book")})

    per_sport_rows: dict[str, list[dict]] = {}
    for r in rows:
        per_sport_rows.setdefault(r.get("sport", "unknown"), []).append(r)
    per_sport = []
    for sport, sport_rows in sorted(per_sport_rows.items()):
        per_sport.append({
            "sport": sport, "n": len(sport_rows),
            "settled": dict(Counter(r.get("status", "unknown") for r in sport_rows)),
        })

    paper = {
        "n_positions": len(rows),
        "settled": dict(status_counts),
        "per_sport": per_sport,
        "venues": venues,
        "framing": FRAMING,
    }
    scoreboard = _scoreboard_summary()
    if scoreboard:
        paper["scoreboard"] = scoreboard
    reconcile = _reconcile_summaries()
    if reconcile:
        paper["reconcile"] = reconcile

    return {
        "paper": paper,
        "receipt": receipt(
            claim=f"Paper CLV ledger: {len(rows)} logged positions across "
                  f"{len(per_sport)} sports, {len(venues)} venues",
            value=len(rows), label="MEASURED", artifact=CLV_LEDGER,
            asof=date.today().isoformat()),
    }
