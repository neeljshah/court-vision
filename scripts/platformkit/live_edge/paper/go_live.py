"""scripts.platformkit.live_edge.paper.go_live -- promotes ELIGIBLE dry-run
sports from slate_trader into REAL live-ledger paper recording, without
double-counting scripts.platformkit.pm_trading (which already mints
mlb/soccer_intl/wnba/npb/kbo into data/frontend/clv_ledger.jsonl).

STEP 0 FINDING (verified live 2026-07-14): pm_trading.run_paper_today's own
DEFAULT_SPORTS lists tennis, but data/frontend/clv_ledger.jsonl has ZERO
tennis rows all-time -- the D1-SHADOW feed pm_trading reads carries a
market-echo placeholder for tennis (no real model), so pm_trading can never
select a tennis bet (see slate_trader.py's own docstring, same root cause).
wnba (n=83) and soccer_intl (n=414) DO have rows minted by pm_trading TODAY
(checked dynamically below, not hardcoded) -- recording them again here would
double-count the same matches into the same ledger. Eligibility is therefore
computed per run, not assumed: a sport is ELIGIBLE only when pm_trading has
placed NOTHING for it today (game_date == run date, channel != ours).

Dedup (idempotent re-run): before writing, this module computes each
candidate bet's clv_ledger.bet_id() (sport|event_id|market|side|book|
game_date -- the same durable key clv_ledger itself uses to collapse
open/settled twins) and skips any candidate whose id is already present with
status=open in the target ledger. Re-running the same day is therefore a
safe no-op on top of a prior run.

Own-row tracking: bridge.shadow_row_to_bet stamps channel=paper_live_edge
only on the in-memory returned dict, never onto the on-disk ledger row (by
design -- see bridge.py's own docstring), so the persisted ledger alone
cannot distinguish "we minted this" from "pm_trading minted this". This
module therefore keeps its own append-only manifest of bet_ids it has minted
(data/omni/live_edge/paper/go_live_minted.jsonl, under this lane's OWNS) and
uses that -- not a channel field -- to decide whether a given day's ledger
rows for a sport came from pm_trading (not in the manifest -> treat sport as
covered, skip) or from a prior run of this module (in the manifest -> not a
double-count signal).

Guard: a sport with an empty shadow-row slate (no live/upcoming match found
in today's line_history capture) is an honest no-op, never a fabricated row.

Writes to clv_ledger.DEFAULT_LEDGER (data/frontend/clv_ledger.jsonl) by
default; a path= override exists for tests only. executed=False and
edge_claimed=False throughout (clv_ledger.record_bet's own invariants,
reused verbatim via bridge.run_bridge_row -- never reimplemented).

INVARIANTS: import bridge/slate_trader/clv_ledger only, never reimplement
identity/selection/record math; ASCII; <=300 LOC; paper-only.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, List, Optional

from scripts.platformkit import clv_ledger
from scripts.platformkit.live_edge.paper import bridge, slate_trader

# Candidates this lane can build a real shadow-row producer for (slate_trader
# has a build_*_shadow_rows for each). Actual eligibility is decided per run
# by _sport_covered_by_pm_trading below, never assumed from this list alone.
CANDIDATE_SPORTS = ("tennis", "wnba", "soccer", "soccer_intl")

_DEFAULT_MANIFEST = slate_trader._PAPER_DIR / "go_live_minted.jsonl"

_BUILDERS = {
    "tennis": lambda date, lh: slate_trader.build_tennis_shadow_rows(date, line_history_dir=lh),
    "wnba": lambda date, lh: slate_trader.build_wnba_shadow_rows(date, line_history_dir=lh),
    "soccer": lambda date, lh: slate_trader.build_soccer_shadow_rows("soccer", date, line_history_dir=lh),
    "soccer_intl": lambda date, lh: slate_trader.build_soccer_shadow_rows("soccer_intl", date, line_history_dir=lh),
}


def _load_minted_ids(manifest_path) -> set:
    """bet_ids this module has minted in any prior run. Missing file -> empty
    set (honest: nothing minted yet)."""
    if not manifest_path.is_file():
        return set()
    out = set()
    for ln in manifest_path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.add(json.loads(ln)["bet_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def _append_minted(bet_id_val: str, sport: str, date: str, manifest_path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"bet_id": bet_id_val, "sport": sport, "date": date}) + "\n")


def _sport_covered_by_pm_trading(sport: str, date: str, ledger_rows: List[Dict[str, Any]],
                                  minted_ids: set) -> bool:
    """True iff *ledger_rows* already has >=1 row for *sport* dated *date*
    whose bet_id is NOT in *minted_ids* (this module's own manifest) -- i.e.
    pm_trading (or any other minter) is actively covering this sport today,
    so this lane must not also record it (would double-count). The on-disk
    ledger row never carries a channel field (bridge.py stamps that on the
    in-memory copy only), so the manifest -- not the row -- is the source of
    truth for "did WE mint this"."""
    for r in ledger_rows:
        if str(r.get("sport") or "").lower() != sport:
            continue
        gd = str(r.get("game_date") or str(r.get("ts") or "")[:10])[:10]
        if gd != date:
            continue
        if r.get("bet_id") not in minted_ids:
            return True
    return False


def _existing_open_bet_ids(ledger_rows: List[Dict[str, Any]]) -> set:
    return {r.get("bet_id") for r in ledger_rows if r.get("status", "open") == "open"}


def _prospective_bet_id(shadow_row: Dict[str, Any], identity: Dict[str, Any]) -> Optional[str]:
    """Same key clv_ledger.record_bet will itself compute -- built here,
    read-only, purely to check membership before writing."""
    side = identity.get("side")
    if side not in ("home", "away"):
        return None
    ek = identity["event_key"]
    return clv_ledger.bet_id({
        "sport": ek.sport, "event_id": str(shadow_row.get("game")),
        "market": ek.market_family, "side": side,
        "taken_book": str(identity.get("book") or "unknown"),
        "game_date": ek.date,
    })


def run_go_live(date: Optional[str] = None, *, threshold: float = bridge.DEFAULT_THRESHOLD,
                 stake_units: float = slate_trader.STAKE_UNITS_DEFAULT,
                 path=None, line_history_dir=slate_trader._LINE_HISTORY_DIR,
                 manifest_path=_DEFAULT_MANIFEST) -> Dict[str, Any]:
    """One day, every CANDIDATE sport: skip sports pm_trading already covers
    today, dedupe against the live ledger's existing open bet_ids (+ this
    module's own mint manifest), record the rest. Returns a per-sport
    accounted summary (never raises). path/line_history_dir/manifest_path
    overrides exist for tests only -- production callers omit all three
    (real live ledger, real odds capture dir, real manifest)."""
    if date is None:
        date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    target = clv_ledger.DEFAULT_LEDGER if path is None else path
    ledger_rows = clv_ledger.load_ledger(path=target)
    seen_ids = _existing_open_bet_ids(ledger_rows)
    minted_ids = _load_minted_ids(manifest_path)

    results: Dict[str, Any] = {}
    for sport in CANDIDATE_SPORTS:
        if _sport_covered_by_pm_trading(sport, date, ledger_rows, minted_ids):
            results[sport] = {"eligible": False, "reason": "covered_by_pm_trading_today",
                               "n_recorded": 0, "n_skipped_dup": 0, "n_total": 0}
            continue
        rows = _BUILDERS[sport](date, line_history_dir)
        n_recorded = 0
        n_skipped_dup = 0
        n_ungradeable = 0
        for r in rows:
            identity = bridge.resolve_identity(r, line_history_dir=line_history_dir)
            if identity is None:
                n_ungradeable += 1
                continue
            if not bridge.select(r, threshold=threshold):
                continue
            prospective_id = _prospective_bet_id(r, identity)
            if prospective_id is not None and (prospective_id in seen_ids
                                                or prospective_id in minted_ids):
                n_skipped_dup += 1
                continue
            out = bridge.run_bridge_row(r, threshold=threshold, stake_units=stake_units,
                                         path=target, line_history_dir=line_history_dir)
            if out["status"] == "recorded":
                n_recorded += 1
                bid = out["bet"]["bet_id"]
                seen_ids.add(bid)
                minted_ids.add(bid)
                _append_minted(bid, sport, date, manifest_path)
        results[sport] = {"eligible": True, "reason": "no_pm_trading_coverage_today",
                           "n_total": len(rows), "n_recorded": n_recorded,
                           "n_skipped_dup": n_skipped_dup, "n_ungradeable": n_ungradeable}
    return {"date": date, "path": str(target), "results": results}


def render_report(summary: Dict[str, Any]) -> str:
    lines = [f"# GO-LIVE report {summary['date']} -> {summary['path']}", ""]
    for sport, r in summary["results"].items():
        lines.append(f"## {sport}: eligible={r['eligible']} ({r['reason']})")
        if r["eligible"]:
            lines.append(f"n_total={r['n_total']} n_recorded={r['n_recorded']} "
                         f"n_skipped_dup={r['n_skipped_dup']} n_ungradeable={r['n_ungradeable']}")
        lines.append("")
    lines.append("Paper-only. executed=False, edge_claimed=False throughout. "
                 "channel=paper_live_edge on every row this module writes.")
    return "\n".join(lines)


def main() -> int:
    summary = run_go_live()
    print(render_report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_go_live", "render_report", "CANDIDATE_SPORTS"]
