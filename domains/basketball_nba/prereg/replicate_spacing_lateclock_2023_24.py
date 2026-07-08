"""domains.basketball_nba.prereg.replicate_spacing_lateclock_2023_24 -- the
FIRST independent-corpus replication of hypothesis #6 (spacing x late-clock
(<=7s) efficiency), which SURVIVED on 2025-26 (derived_label_hypotheses.py:
effect=+0.00567, p=1.3e-4, term=spacing_mean_dist:is_late_clock) but was
never checked on another season.

PREREGISTERED (declared before running): K=1 confirmatory replication,
alpha=0.05. REPLICATED requires BOTH same effect sign as the 2025-26 hit AND
p < 0.05. If the gate cannot score a single shot (n=0) the verdict is
NOT_TESTABLE -- an un-run test is not a failed one.

METHOD: zero reimplementation -- same sc/tf build + inline season-correct
merge run_d_spacing_transition() in third_season_2023_24.py uses (NOT
derived_label_hypotheses.build_frame, whose internal add_spacing defaults to
the 2025-26 stints/spacing paths), LATE_CLOCK_S imported from
derived_label_hypotheses (not re-hardcoded), stats_common.fit_interaction for
the interaction-term Wald test, stats_common.append_ledger for the write.

Descriptive/measurement only. edge_claimed hard-wired False.
NETWORK: zero. CLI: python -m domains.basketball_nba.prereg.replicate_spacing_lateclock_2023_24
Per-file test: python -m pytest domains/basketball_nba/prereg/test_replicate_spacing_lateclock_2023_24.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from domains.basketball_nba.composition.shot_clock_proxy import build_shot_clock_frame
from domains.basketball_nba.composition.shot_features import add_spacing
from domains.basketball_nba.composition.transition_flag import build_transition_frame
from domains.basketball_nba.prereg.derived_label_hypotheses import LATE_CLOCK_S
from domains.basketball_nba.prereg.stats_common import LEDGER_PATH, append_ledger, fit_interaction

REPO_ROOT = Path(__file__).resolve().parents[3]
_BASE = REPO_ROOT / "data" / "cache" / "team_system"
_PBP_2324 = _BASE / "pbp_2023_24"
_STINTS_2324 = _BASE / "lineups" / "stints_2023_24.parquet"
_SPACING_2324 = _BASE / "lineups" / "lineup_spacing_2023_24.parquet"

ALPHA = 0.05  # K=1 confirmatory replication, declared before running
METHOD = "replication_spacing_lateclock_2023_24"
HYPOTHESIS = "spacing x late-clock (<=7s) efficiency"
_ORIGINAL_SIGN = 1  # 2025-26 census effect=+0.00567472699482241, p=1.3e-4


def _verdict_row(fit: Dict[str, Any]) -> Dict[str, Any]:
    """PURE: fit dict -> ledger row. same_sign(vs the 2025-26 hit) AND
    p<ALPHA both required for REPLICATED -- same shape as third_season_2023_24
    ._verdict_row, K=1 instead of K=4."""
    if fit["n"] == 0:
        verdict = "NOT_TESTABLE"
        note = "n=0: gate produced no scoreable shots on this corpus"
    else:
        same_sign = (fit["effect"] > 0) == (_ORIGINAL_SIGN > 0)
        replicated = same_sign and fit["p"] < ALPHA
        verdict = "REPLICATED" if replicated else "FAILED_REPLICATION"
        note = "" if replicated else "same-sign-and-p<alpha required for REPLICATED"
    return {
        "hypothesis": HYPOTHESIS, "sport": "nba", "atomic_unit": "shot",
        "method": METHOD, "n": fit["n"], "effect": fit["effect"], "p": fit["p"],
        "alpha_fwer": ALPHA, "term": fit["term"],
        "verdict": verdict,
        "note": note,
        "edge_claimed": False,
    }


def run() -> Dict[str, Any]:
    sc = build_shot_clock_frame(pbp_dir=_PBP_2324)
    tf = build_transition_frame(pbp_dir=_PBP_2324)
    # NOT derived_label_hypotheses.build_frame -- its internal add_spacing is
    # hardwired to the 2025-26 stints/spacing paths. Same merge, season-correct paths.
    df = sc.merge(
        tf[["game_id", "team_id", "period", "elapsed_s", "is_transition"]],
        on=["game_id", "team_id", "period", "elapsed_s"], how="inner",
    )
    df = add_spacing(df, stints_src=_STINTS_2324, spacing_src=_SPACING_2324)
    df["is_late_clock"] = (df["shot_clock_proxy"] <= LATE_CLOCK_S).astype(int)
    fit = fit_interaction(df, "made ~ spacing_mean_dist * is_late_clock", kind="logit")
    row = _verdict_row(fit)
    append_ledger([row])
    return row


def main() -> int:
    row = run()
    print(f"K=1 alpha={ALPHA} (spacing x late-clock replication, 2023-24)")
    print(f"  [{row['verdict']:>18}] {row['hypothesis']}: n={row['n']} effect={row['effect']} p={row['p']}")
    print(f"appended 1 row -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
