"""domains.basketball_nba.prereg.derived_label_hypotheses -- runs the 2 of the
10 coach-mechanism hypotheses (docs/research/coach_composition_architecture_
2026_07_08.md section (d)) that nba_hypotheses.py's BLOCKED_REASONS lists as
blocked ONLY for lack of a shot-clock / transition label:

  #2 lineup spacing x transition frequency ("spaced lineups convert
     transition possessions at a higher clip", atomic=possession)
  #6 spacing x late-clock (<=7s) efficiency ("does spacing matter MORE when
     the shot clock is short", atomic=shot)

Unblocked by domains.basketball_nba.composition.shot_clock_proxy and
.transition_flag -- see those modules for the derivation + validation
(96.8% CDN semantic-vs-real-field agreement, 5.67% negative/clipped; 90.5%
recall / 17.2% precision of is_transition vs the real 'fastbreak' qualifier).
Both proxies cleared their validation bar, so K=2 (not fewer).

method='derived_label_v1' on every ledger row, with a caveat naming the
measured proxy-quality numbers from THIS run (not hardcoded) -- an honest
reader can see exactly how much to trust the label before trusting the p.

Same fit machinery as nba_hypotheses.py (fit_interaction, alpha_fwer) --
NOT reimplemented, imported from stats_common. Descriptive/measurement only;
edge_claimed hard-wired False in every row (stats_common).
NETWORK: zero. CLI: python -m domains.basketball_nba.prereg.derived_label_hypotheses
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from domains.basketball_nba.composition.shot_clock_proxy import (
    build_shot_clock_frame, cdn_semantic_agreement, validate_distribution,
)
from domains.basketball_nba.composition.shot_features import add_spacing
from domains.basketball_nba.composition.transition_flag import build_transition_frame, validate_vs_fastbreak_qualifier
from domains.basketball_nba.prereg.stats_common import LEDGER_PATH, alpha_fwer, append_ledger, fit_interaction, tested_row

SPORT = "nba"
LATE_CLOCK_S = 7.0
METHOD = "derived_label_v1"


def build_frame(sc: pd.DataFrame, tf: pd.DataFrame, **spacing_kwargs) -> pd.DataFrame:
    """Shot-level frame: made, shot_clock_proxy, is_transition, spacing_mean_dist.
    spacing_kwargs (stints_src/spacing_src) MUST be passed for non-2025-26
    seasons -- add_spacing's defaults are the 2025-26 artifacts."""
    merged = sc.merge(
        tf[["game_id", "team_id", "period", "elapsed_s", "is_transition"]],
        on=["game_id", "team_id", "period", "elapsed_s"], how="inner",
    )
    merged = add_spacing(merged, **spacing_kwargs)
    merged["is_late_clock"] = (merged["shot_clock_proxy"] <= LATE_CLOCK_S).astype(int)
    return merged


def _proxy_quality_caveats(sc: pd.DataFrame, tf: pd.DataFrame) -> Dict[str, str]:
    """Measures THIS run's proxy quality (not hardcoded) for the ledger caveat."""
    sc_dist = validate_distribution(sc)
    sc_agree = cdn_semantic_agreement()
    tf_pr = validate_vs_fastbreak_qualifier(tf)
    shot_clock_caveat = (
        f"shot_clock_proxy derived label: CDN-vs-semantic agreement={sc_agree['agreement_pct']:.3f} "
        f"(n={sc_agree['n_compared']}), pct_negative/clipped={sc_dist['pct_negative']:.3f} -- "
        f"see composition/shot_clock_proxy.py."
    )
    transition_caveat = (
        f"is_transition derived label: precision={tf_pr['precision']:.3f} recall={tf_pr['recall']:.3f} "
        f"vs the real 'fastbreak' qualifier (CDN-only n={tf_pr['n']}) -- a broad 'early-clock shot' "
        f"proxy, not a 1:1 fastbreak match; see composition/transition_flag.py."
    )
    return {"late_clock": shot_clock_caveat, "transition": transition_caveat}


def run() -> tuple[List[Dict[str, Any]], int]:
    sc = build_shot_clock_frame()
    tf = build_transition_frame()
    df = build_frame(sc, tf)
    caveats = _proxy_quality_caveats(sc, tf)
    k = 2
    alpha = alpha_fwer(k)
    rows: List[Dict[str, Any]] = []

    fit_late = fit_interaction(df, "made ~ spacing_mean_dist * is_late_clock", kind="logit")
    row_late = tested_row("spacing x late-clock (<=7s) efficiency", SPORT, "shot", fit_late, alpha)
    row_late["method"] = METHOD
    row_late["note"] = (row_late["note"] + " " if row_late["note"] else "") + caveats["late_clock"]
    rows.append(row_late)

    fit_trans = fit_interaction(df, "made ~ spacing_mean_dist * is_transition", kind="logit")
    row_trans = tested_row("lineup spacing x transition frequency", SPORT, "possession", fit_trans, alpha)
    row_trans["method"] = METHOD
    row_trans["note"] = (row_trans["note"] + " " if row_trans["note"] else "") + caveats["transition"]
    rows.append(row_trans)

    return rows, k


def main() -> int:
    rows, k = run()
    print(f"K tested (NBA derived-label)={k} alpha_fwer={alpha_fwer(k):.6f}")
    for r in rows:
        print(f"  [{r['verdict']:>16}] {r['hypothesis']}: n={r['n']} effect={r['effect']} p={r['p']}")
        print(f"    note: {r['note']}")
    append_ledger(rows)
    print(f"appended {len(rows)} rows -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
