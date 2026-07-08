"""cli -- run the composed NBA challenger, print the scoreboard, log the ledger.

    python -m scripts.platformkit.compose.cli

Prints the ASCII ablation scoreboard (Elo base -> +offense -> +concession ->
+synergy/gravity -> +rest) and appends one row per rung to the weight ledger
(data/cache/intel_claims/claim_weights.jsonl) with method
"composed_challenger_v1_walkforward". Calibration record only -- edge_claimed
is hard-wired False. NO dollar/edge language.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from scripts.platformkit.compose.challenger import METHOD, run_challenger
from scripts.platformkit.intel_weighting.relevance_gate import GateResult
from scripts.platformkit.intel_weighting.weight_ledger import LEDGER, _key


def _append_ledger(results: List[GateResult], ledger: Path = LEDGER) -> Path:
    """Upsert one row per rung keyed by (family, metric, method). Mirrors
    weight_ledger.append_results but stamps the composed METHOD (that module
    hard-codes the relevance_gate method string, so it cannot be reused here)."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    existing[_key(r)] = r
                except json.JSONDecodeError:
                    continue
    for g in results:
        r = {
            "family": g.family, "metric": g.metric, "sport": g.sport,
            "entity_mapping": g.entity_mapping, "n_games": g.n_games,
            "brier_base": g.brier_base, "brier_cond": g.brier_cond,
            "delta": g.delta, "delta_trunc80": g.delta_trunc80, "dm_p": g.dm_p,
            "verdict": g.verdict,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "method": METHOD, "edge_claimed": False, "caveats": g.caveats,
        }
        existing[_key(r)] = r
    tmp = ledger.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="ascii", errors="strict") as f:
        for r in existing.values():
            f.write(json.dumps(r) + "\n")
    tmp.replace(ledger)
    return ledger


def _scoreboard(results: List[GateResult]) -> str:
    w = results[0].n_games
    hdr = (f"COMPOSED NBA CHALLENGER vs Elo -- walk-forward within 2025-26 "
           f"(n={w}, method={METHOD})\n"
           "calibration only; NO edge/$ -- an honest NULL is a success\n")
    line = "-" * 78
    cols = (f"{'rung':<18}{'brier':>10}{'delta_vs_elo':>14}"
            f"{'delta_t80':>12}{'dm_p':>8}  verdict")
    body = []
    for r in results:
        body.append(f"{r.metric:<18}{r.brier_cond:>10.5f}{r.delta:>+14.5f}"
                    f"{r.delta_trunc80:>+12.5f}{r.dm_p:>8.4f}  {r.verdict}")
    return "\n".join([hdr, line, cols, line, *body, line])


def main() -> int:
    results = run_challenger()
    print(_scoreboard(results))
    path = _append_ledger(results)
    print(f"\nappended {len(results)} rows -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
