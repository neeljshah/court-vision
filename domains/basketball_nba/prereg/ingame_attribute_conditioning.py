"""domains.basketball_nba.prereg.ingame_attribute_conditioning -- the PREREG
driver for "do PROFILE ATTRIBUTES add in-game conditioning value beyond the one
surviving live-state rung (endQ1 star_minutes_load)?"

PREREGISTERED BAR (declared BEFORE running -- fixed after seeing results):
  K = 3 coach-proposed ATTRIBUTE x LIVE interactions, one preregistered
  checkpoint each. Plain Bonferroni alpha = 0.05 / 3 = 0.016667 (these are 3
  independent DISCOVERY tests, not a same-run census -- a flat Bonferroni is the
  honest bar, same choice third_season_2023_24 made for its confirmations).
    H1  rim_pressure_def x realized rim pressure         @ half
    H2  shot_diet_three_share x realized Q1 3PT luck      @ endQ1  (base carries
                                                            the survivor
                                                            star_minutes_load)
    H3  lineup_continuity x realized starter disruption   @ half

VERDICT per (hypothesis, season): SURVIVES_PREREG iff delta>0 AND dm_p<ALPHA AND
delta_trunc80>0; else NULL; n=0 -> NOT_TESTABLE (an un-run test, never FAILED).
BELIEF requires the same-sign SURVIVES on >=2 seasons -- a single-season lift is
an artifact (no-edge-claims discipline). Run on 2025-26, 2024-25, 2023-24 (pbp +
stints cover all three; priors are recomputed strictly-as-of so all are
leak-legal -- see attribute_conditioning's leak-legality note).

LEAK-LEGALITY DECISION: nba_player_profiles.parquet is whole-season-only
(season_2025_26 / last20_2025_26) -> using it to condition 2025-26 is a leak and
it lacks the older seasons; DISCARDED. Priors are recomputed as-of from raw
pbp/stints instead. This module runs NOT on the profile parquet.

Descriptive/measurement only. edge_claimed hard-wired False on every row.
CLI: python -m domains.basketball_nba.prereg.ingame_attribute_conditioning
Per-file test: python -m pytest domains/basketball_nba/prereg/test_ingame_attribute_conditioning.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.platformkit.ingame_compose.attribute_conditioning import (
    METHOD, HypResult, run_hypotheses,
)
from scripts.platformkit.intel_weighting.weight_ledger import LEDGER as CLAIM_WEIGHTS_LEDGER
from domains.basketball_nba.prereg.stats_common import LEDGER_PATH, append_ledger

ALPHA = 0.05 / 3  # K=3, plain Bonferroni -- declared in the brief, fixed
SEASONS = ["2025-26", "2024-25", "2023-24"]
_FAMILY = "ingame_attribute_cond"
_ATOMIC = "team_asof_ingame"


def _verdict(r: HypResult) -> str:
    if r.n_test == 0 or r.verdict == "NOT_TESTABLE":
        return "NOT_TESTABLE"
    if r.delta > 0 and r.dm_p < ALPHA and r.delta_trunc80 > 0:
        return "SURVIVES_PREREG"
    return "NULL"


def _ledger_row(r: HypResult, season: str) -> Dict[str, Any]:
    v = _verdict(r)
    note = ("PROVISIONAL -- needs same-sign SURVIVES on a 2nd season before belief"
            if v == "SURVIVES_PREREG" else
            ("n=0: no game had this prior+realized defined on this corpus"
             if v == "NOT_TESTABLE" else ""))
    if season == "2023-24":
        note = (note + " " if note else "") + (
            "2023-24: box absent -> league 3PT rate at fallback constant (p3=0.35) "
            "for the H2 realized-luck term.")
    return {
        "hypothesis": r.hypothesis, "sport": "nba", "atomic_unit": _ATOMIC,
        "method": METHOD, "season": season, "checkpoint": r.checkpoint,
        "n": r.n_test, "effect": r.delta, "delta_trunc80": r.delta_trunc80,
        "p": r.dm_p, "alpha_fwer": ALPHA, "term": r.beta, "verdict": v,
        "note": note, "edge_claimed": False,
    }


def _claim_row(r: HypResult, season: str) -> Dict[str, Any]:
    return {
        "family": _FAMILY, "metric": f"{season}:{r.checkpoint}:{r.hypothesis}",
        "sport": "nba", "entity_mapping": _ATOMIC, "n_games": r.n_test,
        "n_test": r.n_test, "brier_base": None, "brier_cond": None,
        "delta": r.delta, "delta_trunc80": r.delta_trunc80, "dm_p": r.dm_p,
        "verdict": _verdict(r), "beta": r.beta,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "method": METHOD, "edge_claimed": False, "caveats": r.caveats,
    }


def _append_claim_weights(rows: List[Dict[str, Any]], ledger: Path = CLAIM_WEIGHTS_LEDGER) -> Path:
    """Upsert by (family, metric, method) -- METHOD is distinct from every
    existing board method, so this NEVER clobbers the v2/relevance rows (same
    precedent as third_season_2023_24._append_v2_claim_weights)."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[tuple, dict] = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[(row.get("family"), row.get("metric"), row.get("method"))] = row
    for row in rows:
        existing[(row["family"], row["metric"], row["method"])] = row
    tmp = ledger.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="ascii", errors="strict") as f:
        for row in existing.values():
            f.write(json.dumps(row) + "\n")
    tmp.replace(ledger)
    return ledger


def run() -> List[Dict[str, Any]]:
    ledger_rows: List[Dict[str, Any]] = []
    claim_rows: List[Dict[str, Any]] = []
    for season in SEASONS:
        for r in run_hypotheses(season):
            ledger_rows.append(_ledger_row(r, season))
            claim_rows.append(_claim_row(r, season))
    append_ledger(ledger_rows)
    _append_claim_weights(claim_rows)
    return ledger_rows


def _replication(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """hypothesis -> count of seasons that SURVIVES_PREREG with a positive
    delta (same-sign = both improve Brier); >=2 is the belief bar."""
    tally: Dict[str, int] = {}
    for r in rows:
        if r["verdict"] == "SURVIVES_PREREG":
            tally[r["hypothesis"]] = tally.get(r["hypothesis"], 0) + 1
    return tally


def main() -> int:
    rows = run()
    print(f"K=3 alpha_bonferroni={ALPHA:.6f}  (attribute -> in-game conditioning, 3 seasons)")
    for r in rows:
        print(f"  [{r['verdict']:>15}] {r['season']} {r['checkpoint']:6s} "
              f"{r['hypothesis'][:46]:46s} n={r['n']:4d} d={r['effect']:+.6f} dm={r['p']:.4f}")
    rep = _replication(rows)
    print("replication (>=2 seasons SURVIVES = belief):",
          {k: v for k, v in rep.items()} or "none survived twice (honest NULL loop complete)")
    print(f"appended {len(rows)} rows -> {LEDGER_PATH} (method={METHOD})")
    print(f"appended {len(rows)} rows -> {CLAIM_WEIGHTS_LEDGER} (method={METHOD})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
