"""domains.basketball_nba.prereg.replicate_h7_2024_25 -- independent-corpus
replication of hypothesis #7 (stint continuity x defensive rebound rate) on
the 2024-25 regular season.

WHY: nba_hypotheses.py's h7 SURVIVED at p=1.1e-16 on the 2025-26 corpus alone
(effect=+0.0006493820, term=continuity_s, n=94766) -- per project rule a
single-fold p<alpha result stays PROVISIONAL until replicated on an
INDEPENDENT corpus. This is that K=1 confirmatory replication run.

METHOD: reuse -- zero reimplementation. build_continuity_dreb / fit_single /
append_ledger are the SAME functions nba_hypotheses.py used for the original
run (build_continuity_dreb was parameterized this wave to take a pbp_dir so
it can point at the separate 2024-25 cache instead of reimplementing the
rebound-matching logic). Same formula, same floors (MIN_LINEUP_ELAPSED_S via
_lineup_net_ratings is NOT used by h7 -- h7 only depends on stints_df's
n_on_court==5 filter, identical both corpora).

PREREGISTERED BAR: alpha=0.05, single confirmatory test, K=1 -- no
multiplicity correction (this is a replication of one already-tested
hypothesis, not a new multi-hypothesis census).

VERDICT: REPLICATED requires BOTH same effect sign as the original AND
p < alpha. Anything else is FAILED_REPLICATION -- an honest kill of the
hypothesis, not a failure of this script.

Descriptive/measurement only. edge_claimed hard-wired False.
NETWORK: zero. CLI: python -m domains.basketball_nba.prereg.replicate_h7_2024_25
Per-file test: python -m pytest domains/basketball_nba/prereg/test_replicate_h7_2024_25.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from domains.basketball_nba.prereg.nba_hypotheses import build_continuity_dreb
from domains.basketball_nba.prereg.stats_common import append_ledger, fit_single

REPO_ROOT = Path(__file__).resolve().parents[3]
_PBP_DIR_2425 = REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2024_25"
_STINTS_2425 = REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / "stints_2024_25.parquet"

ALPHA = 0.05
_HYPOTHESIS = ("stint continuity x defensive rebound rate (single-factor: no "
               "second named mechanism in the doc)")
_ORIGINAL_EFFECT_SIGN = 1  # 2025-26 census: effect=+0.0006493820316055143 (p=1.1e-16)


def verdict_row(fit: Dict[str, Any], alpha: float = ALPHA) -> Dict[str, Any]:
    """PURE: fit dict -> ledger row. Split out from run() so the REPLICATED/
    FAILED_REPLICATION branch is testable without touching disk."""
    same_sign = (fit["effect"] > 0) == (_ORIGINAL_EFFECT_SIGN > 0)
    replicated = same_sign and fit["p"] < alpha
    return {
        "hypothesis": _HYPOTHESIS, "sport": "nba", "atomic_unit": "rebound",
        "method": "replication_2024_25",
        "n": fit["n"], "effect": fit["effect"], "p": fit["p"], "alpha_fwer": alpha,
        "term": fit["term"],
        "verdict": "REPLICATED" if replicated else "FAILED_REPLICATION",
        "note": "" if replicated else "same-sign-and-p<alpha required for REPLICATED",
        "edge_claimed": False,
    }


def run(pbp_dir: Path = _PBP_DIR_2425, stints_path: Path = _STINTS_2425) -> Dict[str, Any]:
    stints_df = pd.read_parquet(stints_path)
    cont = build_continuity_dreb(stints_df, pbp_dir=pbp_dir)
    fit = fit_single(cont, "is_dreb ~ continuity_s", kind="logit")
    return verdict_row(fit)


def main() -> int:
    row = run()
    print(f"REPLICATION h7 (2024-25 independent corpus): n={row['n']} "
          f"effect={row['effect']} p={row['p']} verdict={row['verdict']}")
    append_ledger([row])
    print("appended 1 row -> data/cache/intel_claims/prereg_hypothesis_ledger.jsonl")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
