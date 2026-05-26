"""clv_weekly_report.py -- R9 C8 weekly CLV report.

Reads two optional inputs (gracefully handles absence):
- ``data/models/clv_log.json``    : per-bet CLV log from clv_tracker
- ``data/pnl_ledger_clv.csv``     : enriched ledger from src.betting.clv

Emits two outputs:
- ``vault/Models/CLV Weekly.md``  : human-readable markdown table
- ``data/models/clv_weekly_<ISO_year-W##>.json`` : machine-readable

Breakdown axes: per-stat, per-book, per-timing-bucket. Timing buckets:
- ``pre_24h`` : 24h+ before tip
- ``pre_2h``  : 2h-24h before tip
- ``pre_30m`` : <2h before tip (closest to close)
(Timing detection is a PLACEHOLDER until R9 C7 ships explicit ``placed_at``
vs ``tipoff`` annotation; without that, all rows are tagged ``unknown``.)

Idempotent on rerun for the same ISO week.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

_CLV_LOG = PROJECT_DIR / "data" / "models" / "clv_log.json"
_PNL_LEDGER_CLV = PROJECT_DIR / "data" / "pnl_ledger_clv.csv"
_VAULT_OUT = PROJECT_DIR / "vault" / "Models" / "CLV Weekly.md"
_JSON_OUT_DIR = PROJECT_DIR / "data" / "models"


def _iso_week_label(d: Optional[date] = None) -> str:
    d = d or date.today()
    iy, iw, _ = d.isocalendar()
    return f"{iy}-W{iw:02d}"


def _safe_float(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _load_clv_log() -> List[Dict]:
    if not _CLV_LOG.exists():
        return []
    try:
        return json.loads(_CLV_LOG.read_text(encoding="utf-8")) or []
    except Exception:
        return []


def _load_pnl_clv() -> List[Dict]:
    if not _PNL_LEDGER_CLV.exists():
        return []
    try:
        with open(_PNL_LEDGER_CLV, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def _timing_bucket(row: Dict) -> str:
    """Best-effort: classify a row's placement timing relative to tipoff.

    Until C7 wires explicit ``tipoff`` annotation, ledger rows don't carry
    a tip timestamp -- so every row maps to ``unknown`` for now. The bucket
    machinery is in place so C7 can flip on the precise math without touching
    callers.
    """
    placed = row.get("placed_at", "")
    tip = row.get("tipoff_at") or row.get("game_tip_iso") or ""
    if not placed or not tip:
        return "unknown"
    try:
        p = datetime.fromisoformat(str(placed))
        t = datetime.fromisoformat(str(tip))
    except Exception:
        return "unknown"
    delta_h = (t - p).total_seconds() / 3600.0
    if delta_h >= 24:
        return "pre_24h"
    if delta_h >= 2:
        return "pre_2h"
    return "pre_30m"


def _summarise(rows: List[Dict], pct_field: str, beat_field: str) -> Dict:
    """Return beat_rate + mean_clv summary from a list of rows.

    pct_field   : column to read clv_percent (string or float) from
    beat_field  : column to read beat_close bool from
    """
    n = len(rows)
    if n == 0:
        return {"n": 0, "beat_rate": 0.0, "mean_clv_percent": 0.0}
    pcts: List[float] = []
    beats = 0
    n_with_close = 0
    for r in rows:
        p = _safe_float(r.get(pct_field))
        if p is not None:
            pcts.append(p)
            n_with_close += 1
        b = str(r.get(beat_field, "")).lower()
        if b in ("true", "1"):
            beats += 1
    if n_with_close == 0:
        return {"n": n, "beat_rate": 0.0, "mean_clv_percent": 0.0}
    return {
        "n":                n,
        "n_with_close":     n_with_close,
        "beat_rate":        round(beats / n_with_close, 4),
        "mean_clv_percent": round(sum(pcts) / len(pcts), 6) if pcts else 0.0,
    }


def _group_by(rows: List[Dict], key: str, pct_field: str,
              beat_field: str) -> Dict[str, Dict]:
    grp: Dict[str, List[Dict]] = {}
    for r in rows:
        k = (r.get(key) or "unknown")
        k = str(k).lower().strip() or "unknown"
        grp.setdefault(k, []).append(r)
    return {k: _summarise(v, pct_field, beat_field) for k, v in sorted(grp.items())}


def _group_by_timing(rows: List[Dict], pct_field: str,
                     beat_field: str) -> Dict[str, Dict]:
    grp: Dict[str, List[Dict]] = {}
    for r in rows:
        grp.setdefault(_timing_bucket(r), []).append(r)
    return {k: _summarise(v, pct_field, beat_field) for k, v in sorted(grp.items())}


def _build_report(week: str) -> Dict:
    clv_log_rows = _load_clv_log()
    pnl_rows = _load_pnl_clv()

    # clv_log uses "clv" field (signed line move ratio) and "stat".
    # Treat clv>0 as beat_close.
    log_summary = {
        "by_stat":  {},
        "by_book":  {},
        "by_timing": {},
        "overall": {"n": 0, "beat_rate": 0.0, "mean_clv_percent": 0.0},
    }
    if clv_log_rows:
        # Synthesise the fields _summarise expects.
        norm: List[Dict] = []
        for e in clv_log_rows:
            clv = _safe_float(e.get("clv"))
            row = dict(e)
            row["clv_percent_norm"] = clv if clv is not None else None
            row["beat_close_norm"] = "true" if (clv is not None and clv > 0) else "false"
            norm.append(row)
        log_summary["overall"] = _summarise(
            norm, "clv_percent_norm", "beat_close_norm")
        log_summary["by_stat"] = _group_by(
            norm, "stat", "clv_percent_norm", "beat_close_norm")
        log_summary["by_book"] = _group_by(
            norm, "book", "clv_percent_norm", "beat_close_norm")
        log_summary["by_timing"] = _group_by_timing(
            norm, "clv_percent_norm", "beat_close_norm")

    # pnl_ledger_clv has clv_percent (vig-included) and beat_close strings.
    pnl_summary = {
        "by_stat":  {},
        "by_book":  {},
        "by_timing": {},
        "overall": {"n": 0, "beat_rate": 0.0, "mean_clv_percent": 0.0},
    }
    if pnl_rows:
        pnl_summary["overall"]  = _summarise(pnl_rows, "clv_percent", "beat_close")
        pnl_summary["by_stat"]  = _group_by(pnl_rows, "stat", "clv_percent", "beat_close")
        pnl_summary["by_book"]  = _group_by(pnl_rows, "book", "clv_percent", "beat_close")
        pnl_summary["by_timing"] = _group_by_timing(pnl_rows, "clv_percent", "beat_close")

    return {
        "week":           week,
        "generated_at":   datetime.now().isoformat(timespec="seconds"),
        "sources": {
            "clv_log_path":      str(_CLV_LOG),
            "clv_log_exists":    _CLV_LOG.exists(),
            "clv_log_rows":      len(clv_log_rows),
            "pnl_ledger_path":   str(_PNL_LEDGER_CLV),
            "pnl_ledger_exists": _PNL_LEDGER_CLV.exists(),
            "pnl_ledger_rows":   len(pnl_rows),
        },
        "clv_log":  log_summary,
        "pnl_clv":  pnl_summary,
        "notes": (
            "timing buckets are placeholders until R9 C7 wires explicit "
            "tipoff annotation onto ledger rows."
        ),
    }


def _render_md(report: Dict) -> str:
    lines = [f"# CLV Weekly Report -- {report['week']}", "",
             f"_generated {report['generated_at']}_", ""]
    src = report["sources"]
    lines.append("## Sources")
    lines.append("")
    lines.append(f"- `clv_log`: exists={src['clv_log_exists']} rows={src['clv_log_rows']}")
    lines.append(f"- `pnl_ledger_clv`: exists={src['pnl_ledger_exists']} rows={src['pnl_ledger_rows']}")
    lines.append("")

    def _table(title: str, by: Dict[str, Dict]) -> List[str]:
        out = [f"### {title}", "",
               "| key | n | n_with_close | beat_rate | mean_clv_pct |",
               "|-----|---|--------------|-----------|--------------|"]
        if not by:
            out.append("| _(no rows)_ | 0 | 0 | 0 | 0 |")
            return out + [""]
        for k, v in by.items():
            out.append(
                f"| {k} | {v.get('n', 0)} | {v.get('n_with_close', 0)} "
                f"| {v.get('beat_rate', 0):.4f} "
                f"| {v.get('mean_clv_percent', 0):+.4f} |"
            )
        out.append("")
        return out

    # CLV log section
    lines.append("## clv_log.json")
    lines.append("")
    ov = report["clv_log"]["overall"]
    lines.append(f"- overall: n={ov.get('n', 0)} "
                 f"beat_rate={ov.get('beat_rate', 0):.4f} "
                 f"mean_clv_pct={ov.get('mean_clv_percent', 0):+.4f}")
    lines.append("")
    lines += _table("By stat", report["clv_log"]["by_stat"])
    lines += _table("By book", report["clv_log"]["by_book"])
    lines += _table("By timing bucket (placeholder)", report["clv_log"]["by_timing"])

    # PNL ledger section
    lines.append("## pnl_ledger_clv.csv")
    lines.append("")
    ov2 = report["pnl_clv"]["overall"]
    lines.append(f"- overall: n={ov2.get('n', 0)} "
                 f"beat_rate={ov2.get('beat_rate', 0):.4f} "
                 f"mean_clv_pct={ov2.get('mean_clv_percent', 0):+.4f}")
    lines.append("")
    lines += _table("By stat", report["pnl_clv"]["by_stat"])
    lines += _table("By book", report["pnl_clv"]["by_book"])
    lines += _table("By timing bucket (placeholder)", report["pnl_clv"]["by_timing"])

    lines.append(f"> {report['notes']}")
    lines.append("")
    return "\n".join(lines)


def write_report(week: Optional[str] = None) -> Tuple[Path, Path]:
    """Build + write both outputs. Returns (md_path, json_path)."""
    week = week or _iso_week_label()
    report = _build_report(week)

    _VAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _VAULT_OUT.write_text(_render_md(report), encoding="utf-8")

    _JSON_OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = _JSON_OUT_DIR / f"clv_weekly_{week}.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"  [clv_weekly_report] md  -> {_VAULT_OUT}")
    print(f"  [clv_weekly_report] json -> {json_path}")
    return _VAULT_OUT, json_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Weekly CLV report")
    ap.add_argument("--week", default=None,
                    help="ISO week label like 2026-W22 (default: this week)")
    args = ap.parse_args()
    write_report(args.week)
