"""probe_R9_C4_clv_join_repair.py — R9 C4.

End-to-end probe:
  1. Run scripts/etl_snapshots_to_lines.py (PrizePicks snapshots → data/lines/<date>_pp.csv).
  2. Call src.betting.clv.enrich_pnl_with_clv() on the full ledger, writing
     data/pnl_ledger_clv.csv.
  3. Re-walk the ledger with per-failure-mode counters
     (no_snapshot / book_mismatch / stat_mismatch / window_miss /
      name_unresolved / id_unresolved / match_ok).
  4. Emit data/cache/probe_R9_C4_clv_join_repair_results.json (SHIP gate result)
     and data/cache/clv_join_debug.json (per-bet attribution, capped at 5,000
     example failures).

Also handles the SHIP=impossible case: if the ledger has zero PrizePicks-book
bets, the SHIP gate cannot be satisfied with current data — mark BLOCKED and
verify the wiring against a synthetic PP bet so the artefacts still prove the
pipe is correct.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.betting import clv as clv_mod  # noqa: E402

import importlib  # noqa: E402
etl_mod = importlib.import_module("scripts.etl_snapshots_to_lines")

PNL_PATH        = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")
LINES_DIR       = os.path.join(PROJECT_DIR, "data", "lines")
OUT_LEDGER      = os.path.join(PROJECT_DIR, "data", "pnl_ledger_clv.csv")
RESULT_JSON     = os.path.join(PROJECT_DIR, "data", "cache", "probe_R9_C4_clv_join_repair_results.json")
DEBUG_JSON      = os.path.join(PROJECT_DIR, "data", "cache", "clv_join_debug.json")
DEBUG_MAX_EXAMPLES = 5_000


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# --------------------------------------------------------------------------- #
# Failure-mode attribution (local re-walk; doesn't mutate prod logic).        #
# --------------------------------------------------------------------------- #
def _attribute(
    bet: Dict,
    snapshots: List[Dict],
) -> Tuple[str, Optional[Dict]]:
    """Return (failure_mode, matched_row_or_None).

    failure_mode in:
      match_ok | no_snapshot | book_mismatch | stat_mismatch |
      window_miss | name_unresolved | id_unresolved | bad_placed_at
    """
    if not snapshots:
        return ("no_snapshot", None)

    placed_at = clv_mod._parse_iso(bet.get("placed_at", ""))
    if placed_at is None:
        return ("bad_placed_at", None)
    asof = placed_at + timedelta(minutes=30)

    book_c = clv_mod._book_canon(bet.get("book", ""))
    stat_l = (bet.get("stat", "") or "").lower().strip()
    pid_s  = str(bet.get("player_id", "") or "").strip()
    pname_k = clv_mod._name_key(bet.get("player", ""))

    target = asof - timedelta(minutes=clv_mod.CLOSING_OFFSET_MIN)
    max_age = timedelta(hours=clv_mod.MAX_SNAPSHOT_AGE_HOURS)

    saw_book = False
    saw_stat = False
    saw_name_or_id = False
    in_window = False
    best = None  # (dist, row)
    best_tier = 99

    for r in snapshots:
        if clv_mod._book_canon(r.get("book", "")) != book_c:
            continue
        saw_book = True
        if (r.get("stat", "") or "").lower().strip() != stat_l:
            continue
        saw_stat = True

        tier = 99
        rpid = str(r.get("player_id", "") or "").strip()
        if pid_s and rpid and rpid == pid_s:
            tier = 1
        elif pname_k and clv_mod._name_key(r.get("player_name", "")) == pname_k:
            tier = 2
        else:
            continue
        saw_name_or_id = True

        ts = clv_mod._parse_iso(r.get("captured_at", ""))
        if ts is None or ts >= asof:
            continue
        if (asof - ts) > max_age:
            continue
        in_window = True

        dist = abs((ts - target).total_seconds())
        if tier < best_tier or (tier == best_tier and (best is None or dist < best[0])):
            best = (dist, r)
            best_tier = tier

    if best is not None:
        return ("match_ok", best[1])
    if not saw_book:
        return ("book_mismatch", None)
    if not saw_stat:
        return ("stat_mismatch", None)
    if not saw_name_or_id:
        # Tier 1 is id-based; if we had a pid we never matched it. Otherwise the
        # name fallback failed.
        return ("id_unresolved" if pid_s else "name_unresolved", None)
    if not in_window:
        return ("window_miss", None)
    return ("window_miss", None)


def _last_7d_window(ledger: List[Dict]) -> datetime:
    """Anchor "last 7 days" off the max placed_at in the ledger.

    Using max(placed_at) rather than wall-clock so the gate is reproducible
    against a frozen ledger.
    """
    mx = None
    for b in ledger:
        ts = clv_mod._parse_iso(b.get("placed_at", ""))
        if ts is None:
            continue
        if mx is None or ts > mx:
            mx = ts
    if mx is None:
        mx = datetime.utcnow()
    return mx - timedelta(days=7)


def _synthetic_wiring_check(snapshots: List[Dict]) -> Dict:
    """Confirm enrich_pnl_with_clv plumbing works end-to-end on a synthetic
    PP bet matched to a real snapshot.

    Picks the most recent PP snapshot, fabricates a bet placed 90 min later
    (so the snapshot is the "closing" line by the algorithm), runs the join.
    """
    # Find a recent snapshot.
    pp_snaps = [
        r for r in snapshots
        if clv_mod._book_canon(r.get("book", "")) == "prizepicks"
    ]
    if not pp_snaps:
        return {"ran": False, "reason": "no pp snapshots in data/lines"}

    # Newest captured_at.
    def _ts(r):
        return clv_mod._parse_iso(r.get("captured_at", "")) or datetime.min
    snap = max(pp_snaps, key=_ts)
    snap_ts = _ts(snap)
    placed_at = (snap_ts + timedelta(minutes=20)).isoformat(timespec="seconds")

    synthetic = {
        "bet_id":       "synthetic-pp-wiring-check",
        "placed_at":    placed_at,
        "game_id":      "",
        "player_id":    "",
        "player":       snap.get("player_name", ""),
        "team":         "",
        "stat":         snap.get("stat", ""),
        "line":         snap.get("line", ""),
        "side":         "OVER",
        "book":         "pp",
        "american_odds": "-110",
        "stake":        "10",
    }
    asof = placed_at  # function adds +30 internally
    clos = clv_mod.find_closing_line(
        book=synthetic["book"],
        game_id=synthetic["game_id"],
        player_id=synthetic["player_id"],
        stat=synthetic["stat"],
        side=synthetic["side"],
        asof=clv_mod._parse_iso(placed_at) + timedelta(minutes=30),
        snapshots=snapshots,
        player_name=synthetic["player"],
    )
    return {
        "ran":         True,
        "synthetic_bet": {k: synthetic[k] for k in ("placed_at", "player", "stat", "line", "side", "book")},
        "snapshot_used": {
            "captured_at": snap.get("captured_at"),
            "player_name": snap.get("player_name"),
            "stat":        snap.get("stat"),
            "line":        snap.get("line"),
        },
        "closing_line_returned": None if clos is None else {"line": clos[0], "odds": clos[1]},
        "wiring_ok":   clos is not None,
    }


def main() -> int:
    os.makedirs(os.path.dirname(RESULT_JSON), exist_ok=True)

    # 1) ETL ---------------------------------------------------------------- #
    etl_result = etl_mod.run()
    etl_stats = etl_result["stats"]
    print(f"[probe] ETL stats: {etl_stats}")

    # 2) Run enrichment on the live ledger --------------------------------- #
    enriched = clv_mod.enrich_pnl_with_clv(
        pnl_path=PNL_PATH,
        lines_dir=LINES_DIR,
        out_path=OUT_LEDGER,
    )
    n_bets_total = len(enriched)
    n_with_clv = sum(1 for r in enriched if (r.get("closing_line") or "") != "")
    print(f"[probe] enriched {n_bets_total} bets; {n_with_clv} have closing_line")

    # 3) Re-walk for per-mode attribution ---------------------------------- #
    snapshots = clv_mod._load_snapshots(LINES_DIR)
    book_counter_ledger = Counter()
    book_counter_snaps = Counter(
        clv_mod._book_canon(r.get("book", "")) for r in snapshots
    )

    last_7d_cutoff = _last_7d_window(enriched)
    by_mode = Counter()
    by_mode_last7 = Counter()
    examples_by_mode: Dict[str, List[Dict]] = defaultdict(list)
    n_last7 = 0
    n_last7_with_clv = 0
    debug_examples_emitted = 0

    for b in enriched:
        book_counter_ledger[(b.get("book") or "").strip()] += 1
        mode, _row = _attribute(b, snapshots)
        # Override: trust the actual write — if closing_line was filled, it's match_ok.
        actual_mode = "match_ok" if (b.get("closing_line") or "") != "" else mode
        by_mode[actual_mode] += 1

        placed_at = clv_mod._parse_iso(b.get("placed_at", ""))
        in_last7 = placed_at is not None and placed_at >= last_7d_cutoff
        if in_last7:
            n_last7 += 1
            by_mode_last7[actual_mode] += 1
            if (b.get("closing_line") or "") != "":
                n_last7_with_clv += 1

        if actual_mode != "match_ok" and debug_examples_emitted < DEBUG_MAX_EXAMPLES:
            if len(examples_by_mode[actual_mode]) < 25:
                examples_by_mode[actual_mode].append({
                    "bet_id":     b.get("bet_id", ""),
                    "placed_at":  b.get("placed_at", ""),
                    "book":       b.get("book", ""),
                    "stat":       b.get("stat", ""),
                    "player":     b.get("player", ""),
                    "player_id":  b.get("player_id", ""),
                    "side":       b.get("side", ""),
                    "line":       b.get("line", ""),
                })
                debug_examples_emitted += 1

    # 4) Synthetic wiring check (always runs) ------------------------------ #
    wiring = _synthetic_wiring_check(snapshots)

    # 5) Snapshot stats ---------------------------------------------------- #
    snap_min_ts = None
    snap_max_ts = None
    for r in snapshots:
        ts = clv_mod._parse_iso(r.get("captured_at", ""))
        if ts is None:
            continue
        if snap_min_ts is None or ts < snap_min_ts:
            snap_min_ts = ts
        if snap_max_ts is None or ts > snap_max_ts:
            snap_max_ts = ts

    # 6) Decision: SHIP / REJECT / BLOCKED --------------------------------- #
    pct_last7 = (n_last7_with_clv / n_last7) if n_last7 > 0 else 0.0
    pct_total = (n_with_clv / n_bets_total) if n_bets_total > 0 else 0.0

    has_pp_in_ledger = book_counter_ledger.get("pp", 0) + book_counter_ledger.get("PP", 0) + book_counter_ledger.get("prizepicks", 0) > 0

    if n_last7_with_clv >= 50 and pct_last7 >= 0.01:
        status = "SHIP"
        ship_reason = (
            f"SHIP gate met: {n_last7_with_clv} bets (>=50) with real CLV in last 7d "
            f"and {pct_last7*100:.2f}% coverage (>=1%)."
        )
    elif not has_pp_in_ledger:
        status = "BLOCKED"
        ship_reason = (
            "Ledger has no PrizePicks bets — only PP snapshots exist, so no real-line "
            "join can succeed. Needs C2 (run DK scraper) or C1 (DK historical line backfill) "
            "to populate matching real lines for the ledger's DK-only bets."
        )
    else:
        status = "REJECT"
        ship_reason = (
            f"SHIP gate failed: only {n_last7_with_clv} bets with CLV in last 7d "
            f"(need >=50 AND >=1%); current {pct_last7*100:.2f}%."
        )

    # 7) Write results JSON ------------------------------------------------ #
    result = {
        "probe":         "R9_C4_clv_join_repair",
        "generated_at":  _now_iso(),
        "status":        status,
        "ship_reason":   ship_reason,
        "n_bets_total":  n_bets_total,
        "n_with_clv":    n_with_clv,
        "pct_with_clv":  round(pct_total, 6),
        "last_7_days":   {
            "cutoff":      last_7d_cutoff.isoformat(timespec="seconds"),
            "n":           n_last7,
            "n_with_clv":  n_last7_with_clv,
            "pct":         round(pct_last7, 6),
        },
        "by_failure_mode":          dict(by_mode),
        "by_failure_mode_last7":    dict(by_mode_last7),
        "etl_stats":                etl_stats,
        "ledger_book_counts":       dict(book_counter_ledger),
        "snapshot_book_counts":     dict(book_counter_snaps),
        "snapshot_min_captured_at": snap_min_ts.isoformat(timespec="seconds") if snap_min_ts else None,
        "snapshot_max_captured_at": snap_max_ts.isoformat(timespec="seconds") if snap_max_ts else None,
        "snapshot_row_count":       len(snapshots),
        "wiring_check":             wiring,
        "outputs": {
            "enriched_ledger": OUT_LEDGER,
            "result_json":     RESULT_JSON,
            "debug_json":      DEBUG_JSON,
        },
    }

    with open(RESULT_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(f"[probe] wrote {RESULT_JSON}")

    # 8) Write per-bet failure debug -------------------------------------- #
    debug = {
        "probe":         "R9_C4_clv_join_repair",
        "generated_at":  _now_iso(),
        "totals":        dict(by_mode),
        "totals_last7":  dict(by_mode_last7),
        "examples":      dict(examples_by_mode),
        "diagnosis":     {
            "ledger_books":        dict(book_counter_ledger),
            "snapshot_books":      dict(book_counter_snaps),
            "snapshot_min_captured_at": snap_min_ts.isoformat(timespec="seconds") if snap_min_ts else None,
            "snapshot_max_captured_at": snap_max_ts.isoformat(timespec="seconds") if snap_max_ts else None,
            "dominant_failure":    by_mode.most_common(1)[0][0] if by_mode else None,
        },
        "wiring_check": wiring,
    }
    with open(DEBUG_JSON, "w", encoding="utf-8") as fh:
        json.dump(debug, fh, indent=2)
    print(f"[probe] wrote {DEBUG_JSON}")

    # Summary line for the runner.
    print(json.dumps({
        "status":            status,
        "n_bets_total":      n_bets_total,
        "n_with_clv":        n_with_clv,
        "last_7d_n":         n_last7,
        "last_7d_n_with_clv": n_last7_with_clv,
        "ship_reason":       ship_reason,
        "wiring_ok":         wiring.get("wiring_ok"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
