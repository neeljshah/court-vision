"""scripts.platformkit.execution.smoke_e2e -- one-command end-to-end proof
that the paper execution chain runs on REAL captured data, any day, without
waiting for a live slate or touching the live-statsapi ticker-resolution gate.

It bypasses nothing risky: it seeds intents with the ACTUAL Kalshi leg tickers
found in the freshest captured book_depth snapshot (so parse_intent resolves
them directly -- no matchup-string guessing, no wrong-leg risk), drives them
through the real run_dryrun (fills simulated against that same captured book),
then run_reconcile (scores those fills vs the later captured tape). Prints a
compact scoreboard. Writes ONLY to a caller-supplied temp dir -- never the
production data/frontend/ops files.

This is a PROOF HARNESS, not a data source: it demonstrates the machine is
wired and green on real books. It makes no $/edge claim (units/probability
only); a NOT_TESTABLE reconcile verdict (no later snapshot in window) is
reported honestly, same as the production reconcile.

INVARIANTS: stdlib only; ASCII stdout; <=300 LOC; never writes data/registry/
or the production ops files; never flips a flag.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/test_smoke_e2e.py -q
"""
from __future__ import annotations

import argparse
import glob
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.execution.executor.dryrun import (
    BOOK_DEPTH_DIR, run_dryrun,
)
from scripts.platformkit.execution.executor.reconcile import run_reconcile


def _mid(row: Dict[str, Any]) -> float:
    """Book mid -> a plausible 0-1 model prob for the intent. Falls back to
    0.5 when only one side of the book is quoted."""
    bid, ask = row.get("best_bid"), row.get("best_ask")
    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and ask >= bid:
        return max(0.01, min(0.99, (bid + ask) / 2.0))
    for v in (bid, ask):
        if isinstance(v, (int, float)) and 0.0 < v < 1.0:
            return v
    return 0.5


def build_intents(depth_dir: Path, n: int) -> List[Dict[str, Any]]:
    """Freshest book day -> up to *n* distinct-ticker intent rows carrying the
    REAL captured leg ticker (parse_intent reads row['ticker'] directly)."""
    files = sorted(glob.glob(str(depth_dir / "*.jsonl")))
    if not files:
        return []
    rows = [json.loads(l) for l in Path(files[-1]).read_text().splitlines() if l.strip()]
    seen: set = set()
    intents: List[Dict[str, Any]] = []
    for r in rows:
        tk = r.get("ticker")
        if not tk or tk in seen:
            continue
        seen.add(tk)
        intents.append({
            "ticker": tk, "sport": r.get("sport", "mlb"), "side": "yes",
            "model_prob": _mid(r), "contracts": 10, "market_type": "moneyline",
        })
        if len(intents) >= n:
            break
    return intents


def run_smoke(depth_dir: Path = BOOK_DEPTH_DIR, n_intents: int = 25,
              work_dir: Path | None = None) -> Dict[str, Any]:
    tmp = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="smoke_e2e_"))
    tmp.mkdir(parents=True, exist_ok=True)
    inp, out = tmp / "intents.jsonl", tmp / "orders.jsonl"
    intents = build_intents(depth_dir, n_intents)
    inp.write_text("".join(json.dumps(i) + "\n" for i in intents))

    dry = run_dryrun(input_path=inp, out_path=out, depth_dir=depth_dir,
                     max_rows=n_intents)
    rec = run_reconcile(orders_path=out, depth_dir=depth_dir)
    return {
        "edge_claimed": False,
        "book_days": len(glob.glob(str(depth_dir / "*.jsonl"))),
        "n_intents_seeded": len(intents),
        "dryrun": {k: dry.get(k) for k in
                   ("n_input_rows", "n_intents", "n_written", "states")},
        "reconcile": {k: rec.get(k) for k in
                      ("n_dryrun_rows", "n_fills", "vs_later_tape")},
        "work_dir": str(tmp),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="End-to-end paper-execution smoke on real captured books")
    ap.add_argument("--depth-dir", default=str(BOOK_DEPTH_DIR))
    ap.add_argument("--n", type=int, default=25)
    args = ap.parse_args()
    print(json.dumps(run_smoke(Path(args.depth_dir), args.n), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
