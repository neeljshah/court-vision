"""Daily, units-only readout for the append-only paper CLV series."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List

from scripts.platformkit.clv_ledger import DEFAULT_LEDGER, is_clv_suspect, load_ledger
from scripts.platformkit.pm_trading.clv_beatrate_rollup import _row_exec_mode

_I = "INSUFFICIENT"
_MIN_N = 8


def _outcome(row: Dict[str, Any]) -> bool:
    return bool(str(row.get("outcome") or "").strip())


def _finite(row: Dict[str, Any], key: str) -> float | None:
    try:
        value = float(row.get(key))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _gross_legacy(row: Dict[str, Any]) -> bool:
    """Match grade_paper_one's unresolvable-maker-fee branch without mutation."""
    fee = row.get("maker_fee_units")
    gate = row.get("exec_gate")
    if fee is None and isinstance(gate, dict):
        fee = gate.get("maker_fee_units")
    if fee is not None:
        try:
            float(fee)
            return False
        except (TypeError, ValueError):
            pass
    maker = (str(row.get("taken_book") or "").strip().lower() == "paper_ingame_maker"
             or (isinstance(gate, dict)
                 and str(gate.get("execution_mode") or "").strip().lower() == "maker_only"))
    if not maker:
        return False
    venue = str(row.get("venue") or "").strip().lower()
    if venue == "polymarket":
        return False
    if venue == "kalshi":
        try:
            1.0 / float(row["taken_decimal"])
            float(row.get("stake_units", 1.0) or 1.0)
            return False
        except (TypeError, ValueError, ZeroDivisionError, KeyError):
            return True
    return True


def _kind(row: Dict[str, Any]) -> str:
    if _row_exec_mode(row) == "legacy":
        return "legacy"
    if row.get("unit_result") is not None and not _outcome(row):
        return "integrity_flag"
    return "settled" if str(row.get("status") or "").lower() == "settled" and _outcome(row) else "open"


def _wilson(beats: int, n: int) -> List[float]:
    z = 1.959963984540054
    p = beats / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / d
    return [round(100 * (c - h), 4), round(100 * (c + h), 4)]


def _pctl(values: List[float], pct: float) -> float:
    return round(sorted(values)[min(int(pct * len(values)), len(values) - 1)], 2)


def rollup(rows: Iterable[Dict[str, Any]], *, now_iso: str) -> Dict[str, Any]:
    """Return a pure readout; each input row has one explicit classification."""
    rows = [row for row in rows if isinstance(row, dict)]
    settled = [row for row in rows if _kind(row) == "settled"]
    classes = {kind: sum(_kind(row) == kind for row in rows)
               for kind in ("settled", "open", "integrity_flag", "legacy")}
    modes = {mode: sum(_row_exec_mode(row) == mode for row in settled)
             for mode in ("maker", "taker")}
    if not settled:
        empty = not rows
        counts = {key: _I for key in classes} if empty else classes
        return {"n_records": _I if empty else len(rows), "n_settled": _I,
                "n_open": _I if empty else classes["open"],
                "n_integrity_flags": _I if empty else classes["integrity_flag"],
                "n_legacy": _I if empty else classes["legacy"],
                "n_maker": _I if empty else modes["maker"],
                "n_taker": _I if empty else modes["taker"],
                "gross_legacy_count": _I if empty else sum(
                    _gross_legacy(row) for row in rows if _kind(row) == "legacy"),
                "is_clv_suspect_share": _I, "median_clv_units": _I,
                "beat_rate_pct": _I, "beat_rate_ci_95_pct": _I,
                "tick_latency_sec_p50": _I, "tick_latency_sec_p90": _I,
                "settled_by_sport": {}, "settled_by_day": {}, "fee_net_complete": _I,
                "verdict": _I, "row_classes": counts}
    by_sport: Dict[str, int] = {}
    by_day: Dict[str, int] = {}
    for row in settled:
        sport = str(row.get("sport") or "unknown")
        day = str(row.get("settled_at") or row.get("graded_at") or now_iso)[:10]
        by_sport[sport] = by_sport.get(sport, 0) + 1
        by_day[day] = by_day.get(day, 0) + 1
    values = [value for row in settled if (value := _finite(row, "clv_units")) is not None]
    ticks = [value for row in rows if (value := _finite(row, "tick_latency_sec")) is not None]
    suspect = sum(is_clv_suspect(row) for row in settled)
    gross = sum(_gross_legacy(row) for row in rows if _kind(row) == "legacy")
    enough = len(settled) >= _MIN_N and len(values) == len(settled)
    verdict = _I if not enough else ("AHEAD" if median(values) > 0 else "BEHIND" if median(values) < 0 else "PAR")
    beats = sum(value > 0 for value in values)
    return {"n_records": len(rows), "n_settled": len(settled), "n_open": classes["open"],
            "n_integrity_flags": classes["integrity_flag"], "n_legacy": classes["legacy"],
            "n_maker": modes["maker"], "n_taker": modes["taker"], "gross_legacy_count": gross,
            "is_clv_suspect_share": round(suspect / len(settled), 6),
            "median_clv_units": round(median(values), 6) if enough else _I,
            "beat_rate_pct": round(100 * beats / len(values), 4) if enough else _I,
            "beat_rate_ci_95_pct": _wilson(beats, len(values)) if enough else _I,
            "tick_latency_sec_p50": _pctl(ticks, .5) if ticks else _I,
            "tick_latency_sec_p90": _pctl(ticks, .9) if ticks else _I,
            "settled_by_sport": by_sport, "settled_by_day": by_day,
            "fee_net_complete": gross == 0, "verdict": verdict, "row_classes": classes}


def write_readout(ledger_path: Path, out_json: Path, memo_md: Path, *, now_iso: str) -> Dict[str, Any]:
    """Read safely, write the consumer envelope, and append one daily memo row."""
    rows = load_ledger(Path(ledger_path))
    doc = rollup(rows, now_iso=now_iso)
    timestamps = [str(row.get("settled_at") or row.get("graded_at")) for row in rows if _kind(row) == "settled"]
    doc.update({"source_artifact": str(ledger_path).replace("\\", "/"),
                "as_of": max(timestamps) if timestamps else "%s (no rows)" % now_iso,
                "generated_at": now_iso, "staleness_days": 0 if timestamps else _I,
                "status": "ok" if timestamps else "no_data"})
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    memo_md.parent.mkdir(parents=True, exist_ok=True)
    memo_md.open("a", encoding="utf-8").write(
        "| as_of | status | n_settled | maker | taker | legacy | verdict |\n"
        "|---|---|---:|---:|---:|---:|---|\n"
        "| {as_of} | {status} | {n_settled} | {n_maker} | {n_taker} | {n_legacy} | {verdict} |\n".format(**doc))
    return doc


def main() -> None:
    now_iso = "2026-09-03T00:00:00+00:00"
    write_readout(DEFAULT_LEDGER, Path("data/frontend/analytics/execution_status.json"),
                  Path("docs/evidence/execution/PAPER_LIVE_2026-09-03.md"), now_iso=now_iso)


if __name__ == "__main__":
    main()
