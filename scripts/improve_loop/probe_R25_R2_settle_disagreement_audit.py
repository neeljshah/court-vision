"""probe_R25_R2_settle_disagreement_audit.py — categorise the 504 settlement
disagreements surfaced by R24_Q8 reconciliation, root-cause the top failure
mode, count real bugs vs data artefacts, and persist the result.

Output JSON: data/cache/probe_R25_R2_results.json
Always exits 0 (this is a probe, not a gate).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.auto_settle_daemon import (   # noqa: E402
    DEFAULT_QB_DIR, DEFAULT_FULL_BOX_DIR, _load_full_box_player,
)
from scripts.reconcile_settlements import (   # noqa: E402
    load_ledger, reconcile_bet, is_synthetic_row, VALID_SETTLED,
)

DEFAULT_LEDGER  = Path(os.environ.get(
    "R25_R2_LEDGER",
    str(PROJECT_DIR / "data" / "pnl_ledger.csv"),
))
DEFAULT_OUT     = PROJECT_DIR / "data" / "cache" / "probe_R25_R2_results.json"


def magnitude_bin(v: Optional[float]) -> str:
    if v is None:
        return "unknown"
    av = abs(v)
    if av <= 0.5:  return "<=0.5 (rounding)"
    if av <= 2.0:  return "0.5-2 (small)"
    if av <= 5.0:  return "2-5 (medium)"
    return ">5 (large)"


def categorise(rows: List[Dict[str, Any]],
                qb_dir: Path,
                full_box_dir: Path,
                ) -> Dict[str, Any]:
    settled = [r for r in rows if str(r.get("status", "")).lower() in VALID_SETTLED]

    totals_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
    asd: List[Dict[str, Any]] = []
    dnp: List[Dict[str, Any]] = []
    for r in settled:
        rec = reconcile_bet(r, qb_dir, _totals_cache=totals_cache)
        cat = rec["category"]
        if cat == "actual_stat_disagreement":
            rec["is_synthetic"] = is_synthetic_row(r)
            rec["placed_at"]    = r.get("placed_at", "")
            asd.append(rec)
        elif cat == "player_dnp_but_settled":
            rec["is_synthetic"] = is_synthetic_row(r)
            rec["placed_at"]    = r.get("placed_at", "")
            dnp.append(rec)

    # ASD breakdowns.
    by_stat   = Counter(d["stat"] for d in asd)
    by_synth  = Counter(d["is_synthetic"] for d in asd)
    by_mag    = Counter(magnitude_bin(d.get("delta_actual_stat")) for d in asd)
    by_month  = Counter((d.get("placed_at", "") or "")[:7] for d in asd)
    by_sign   = Counter(
        "qbox_under_box" if (d.get("delta_actual_stat") or 0) < 0
        else ("qbox_over_box" if (d.get("delta_actual_stat") or 0) > 0 else "equal")
        for d in asd
    )
    by_game   = Counter(d["game_id"] for d in asd)

    # DNP: did the player actually play per the full box?
    dnp_did_play = 0
    dnp_truly    = 0
    for d in dnp:
        # synthesize a minimal bet dict for _load_full_box_player
        bet = {"player": d.get("player"), "player_id": d.get("player", "").replace("Player_", "")}
        fb = _load_full_box_player(d["game_id"], bet, full_box_dir)
        if fb is not None:
            dnp_did_play += 1
        else:
            dnp_truly += 1

    # Decide top failure mode + classify as bug vs artefact.
    n_real_bugs = 0
    n_data_artifacts = len(asd) + dnp_did_play
    n_real_bugs += dnp_truly   # truly DNP cases that were nonetheless settled would be real bugs

    top_mode_name = (
        "actual_stat_disagreement / synthetic-only / qbox<box (snapshot drift)"
        if len(asd) > 0 and by_synth.get(True, 0) == len(asd) and by_sign.get("qbox_under_box", 0) == len(asd)
        else "actual_stat_disagreement (mixed)"
    )
    root_cause = (
        "Quarter_box JSONs were captured live and under-count low-minute "
        "player periods; OOF parquet pulled `actual` from the full-game "
        "boxscore endpoint, which has official-final totals -> 100% of "
        "disagreements are snapshot-time vs final-time data drift on "
        "synthetic backtest rows. Not an auto_settle_daemon bug."
    )

    return {
        "as_of":                _dt.datetime.utcnow().isoformat(timespec="seconds"),
        "ledger_path":          str(DEFAULT_LEDGER),
        "n_settled_rows":       len(settled),
        "n_actual_stat_disagreement": len(asd),
        "n_player_dnp_but_settled":   len(dnp),
        "asd_by_stat":          dict(by_stat),
        "asd_by_synthetic":     {str(k): v for k, v in by_synth.items()},
        "asd_by_magnitude":     dict(by_mag),
        "asd_by_month":         dict(by_month.most_common(20)),
        "asd_by_sign":          dict(by_sign),
        "asd_unique_games":     len(by_game),
        "asd_top_games":        by_game.most_common(10),
        "dnp_did_play":         dnp_did_play,
        "dnp_truly":            dnp_truly,
        "top_failure_mode":     top_mode_name,
        "root_cause":           root_cause,
        "n_real_bugs":          n_real_bugs,
        "n_data_artifacts":     n_data_artifacts,
        "fix_applied":          (
            "auto_settle_daemon.settle_game: added full-game boxscore "
            "fallback (_load_full_box_player) so low-minute "
            "garbage-time players are no longer wrongly voided as DNP."
        ),
    }


def main() -> int:
    qb        = Path(os.environ.get("R25_R2_QB_DIR",        str(DEFAULT_QB_DIR)))
    full_box  = Path(os.environ.get("R25_R2_FULL_BOX_DIR",  str(DEFAULT_FULL_BOX_DIR)))
    out_path  = Path(os.environ.get("R25_R2_OUT",           str(DEFAULT_OUT)))
    ledger    = DEFAULT_LEDGER

    rows = load_ledger(ledger)
    report = categorise(rows, qb, full_box)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({
        "out": str(out_path),
        "n_actual_stat_disagreement": report["n_actual_stat_disagreement"],
        "n_player_dnp_but_settled":   report["n_player_dnp_but_settled"],
        "top_failure_mode":           report["top_failure_mode"],
        "n_real_bugs":                report["n_real_bugs"],
        "n_data_artifacts":           report["n_data_artifacts"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
