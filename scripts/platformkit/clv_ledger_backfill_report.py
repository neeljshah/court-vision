"""scripts.platformkit.clv_ledger_backfill_report -- honest CLV backfill sidecar.

LANE-4 LEDGER HYGIENE (queue item 4): for every settled row with clv_pct=None
("settled_without_clv" in clv_ledger_sanity.scan_ledger), attempt close
resolution via the EXISTING paths (clv_ledger_enrich.enrich_row, which calls
clv_close_lookup.lookup_close_legs -> odds_provider.line_store.get_close). NO
new close-resolution logic is invented here -- this module is a REPORTING +
SIDECAR-WRITE layer over the vetted enrich path.

CONTRACT (binding):
  * READ-ONLY over the ledger -- never rewrites data/frontend/clv_ledger.jsonl.
  * Backfilled rows are appended to a SIDECAR jsonl (clv_backfill.jsonl), never
    merged back into the canonical ledger (append-only invariant preserved by
    keeping the sidecar entirely separate; a consumer joins by bet_id/edge_key
    when it wants the enriched value).
  * Every unresolvable row is labelled with an honest CAUSE (never silently
    dropped): "off_id_space" (game_id is a venue contract ticker, e.g. Kalshi's
    KX* ids, that cannot join the ESPN-game_id-keyed line_history corpus),
    "prop_market_out_of_scope" (a player-prop market has no two-way moneyline
    legs to devig), or "no_close_captured" (in the right id-space but the
    close-lookup still returned nothing).
  * No $ / pnl / profit / bankroll / roi field anywhere in the output.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_ledger_backfill_report.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.clv_ledger_sanity import _raw_load
from scripts.platformkit.clv_ledger_enrich import enrich_row

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LEDGER = _REPO_ROOT / "data" / "frontend" / "clv_ledger.jsonl"
_DEFAULT_SIDECAR = _REPO_ROOT / "data" / "frontend" / "clv_backfill.jsonl"
_DEFAULT_REPORT = _REPO_ROOT / "data" / "frontend" / "ops" / "clv_backfill_report.json"

BACKFILL_VERSION = "clv_ledger_backfill_report.v1"

# Venue contract-ticker id spaces (Kalshi "KX...", generically any non-numeric
# venue ticker) that cannot join the ESPN-numeric-game_id-keyed line_history
# corpus. Matched against the row's game_id (preferred) or event_id.
_ESPN_NUMERIC_RE = re.compile(r"^\d+$")
_PROP_MARKET_RE = re.compile(r"^prop\|")


def _join_id(row: Dict[str, Any]) -> Optional[str]:
    for k in ("game_id", "event_id"):
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def _is_settled_without_clv(row: Dict[str, Any]) -> bool:
    return (str(row.get("status") or "").lower() == "settled"
            and row.get("clv_pct") is None)


def _classify_unresolvable(row: Dict[str, Any]) -> str:
    """Honest cause label for a row enrich_row could not recover CLV for."""
    market = str(row.get("market") or row.get("market_type") or "")
    if _PROP_MARKET_RE.match(market):
        return "prop_market_out_of_scope"
    jid = _join_id(row)
    if jid is None:
        return "no_join_id"
    if not _ESPN_NUMERIC_RE.match(jid):
        return "off_id_space"
    return "no_close_captured"


def build_report(path: Optional[Path] = None) -> Dict[str, Any]:
    """Run the vetted enrich path over every settled_without_clv row. READ-ONLY.

    Returns {version, total_settled_without_clv, backfilled, unresolvable,
    unresolvable_by_cause, backfilled_rows, honest_note}. backfilled_rows are
    the enriched copies (clv_pct/clv_status/clv_note filled) ready to hand to
    write_sidecar(); they are NOT written to the canonical ledger.
    """
    p = Path(path) if path is not None else _DEFAULT_LEDGER
    if not p.exists() or p.stat().st_size == 0:
        return {
            "version": BACKFILL_VERSION,
            "status": "INSUFFICIENT_DATA",
            "total_settled_without_clv": 0,
            "backfilled": 0,
            "unresolvable": 0,
            "unresolvable_by_cause": {},
            "backfilled_rows": [],
        }
    rows = _raw_load(p)
    targets = [(i, r) for i, r in enumerate(rows) if _is_settled_without_clv(r)]

    backfilled_rows: List[Dict[str, Any]] = []
    unresolvable_by_cause: Dict[str, int] = {}
    n_backfilled = 0
    for idx, row in targets:
        enriched = enrich_row(row)
        if enriched.get("clv_pct") is not None:
            n_backfilled += 1
            stamped = dict(enriched)
            stamped["_source_line_idx"] = idx
            stamped["_backfill_note"] = (
                "derived via clv_ledger_enrich.enrich_row (line_store bridge); "
                "sidecar only -- canonical ledger row untouched"
            )
            backfilled_rows.append(stamped)
        else:
            cause = _classify_unresolvable(row)
            unresolvable_by_cause[cause] = unresolvable_by_cause.get(cause, 0) + 1

    return {
        "version": BACKFILL_VERSION,
        "status": "ok",
        "ledger_path": str(p),
        "total_settled_without_clv": len(targets),
        "backfilled": n_backfilled,
        "unresolvable": len(targets) - n_backfilled,
        "unresolvable_by_cause": unresolvable_by_cause,
        "backfilled_rows": backfilled_rows,
        "honest_note": (
            "calibration not edge; read-only over canonical ledger; backfilled "
            "rows are sidecar-only (clv_backfill.jsonl), never merged back into "
            "the append-only ledger; off_id_space = venue contract ticker "
            "(e.g. Kalshi KX*) cannot join the ESPN-game_id-keyed line_history "
            "corpus; prop_market_out_of_scope = player-prop has no two-way "
            "moneyline legs to devig; no_close_captured = right id-space but "
            "no quote was ever captured for that game"
        ),
    }


def write_sidecar(report: Dict[str, Any], out: Optional[Path] = None) -> Dict[str, Any]:
    """Append backfilled_rows to the sidecar jsonl. Idempotent by source line idx.

    Skips rows whose _source_line_idx already appears in the sidecar (safe to
    re-run). Never touches the canonical ledger. Returns {written, skipped, path}.
    """
    target = Path(out) if out is not None else _DEFAULT_SIDECAR
    target.parent.mkdir(parents=True, exist_ok=True)
    seen_idxs = set()
    if target.exists():
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "_source_line_idx" in existing:
                    seen_idxs.add(existing["_source_line_idx"])

    written = 0
    skipped = 0
    with target.open("a", encoding="utf-8") as fh:
        for row in report.get("backfilled_rows", []):
            if row.get("_source_line_idx") in seen_idxs:
                skipped += 1
                continue
            fh.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
            written += 1
    return {"written": written, "skipped": skipped, "path": str(target)}


def write_report(path: Optional[Path] = None, out: Optional[Path] = None,
                  sidecar: Optional[Path] = None) -> Dict[str, Any]:
    """Build the report, persist the sidecar rows, and write the summary JSON.

    The summary JSON (out) omits backfilled_rows (they live in the sidecar) to
    stay small; it keeps the counts + causes.
    """
    report = build_report(path)
    sidecar_result = {"written": 0, "skipped": 0, "path": str(
        Path(sidecar) if sidecar is not None else _DEFAULT_SIDECAR)}
    if report.get("backfilled_rows"):
        sidecar_result = write_sidecar(report, sidecar)

    summary = {k: v for k, v in report.items() if k != "backfilled_rows"}
    summary["sidecar"] = sidecar_result

    target = Path(out) if out is not None else _DEFAULT_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=True, default=str)
    return summary


def _main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Backfill CLV for settled_without_clv rows via the vetted "
                    "enrich path; writes a sidecar jsonl + summary report. "
                    "Never mutates the canonical ledger."
    )
    ap.add_argument("--ledger", default=None, help="override ledger path")
    ap.add_argument("--out", default=None, help="override summary report path")
    ap.add_argument("--sidecar", default=None, help="override sidecar jsonl path")
    a = ap.parse_args(list(argv) if argv is not None else None)
    res = write_report(
        Path(a.ledger) if a.ledger else None,
        Path(a.out) if a.out else None,
        Path(a.sidecar) if a.sidecar else None,
    )
    print(json.dumps(res, indent=2, ensure_ascii=True, default=str))
    return 0


__all__ = ["build_report", "write_sidecar", "write_report", "BACKFILL_VERSION"]

if __name__ == "__main__":
    raise SystemExit(_main())
