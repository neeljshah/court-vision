"""domains.basketball_nba.prereg.third_season_2023_24 -- the THIRD independent-
corpus run of the 4 fresh preregistered NBA in-game hypotheses named in this
lane's brief, all on the 2023-24 regular season alone:

  a. stint continuity x defensive rebound rate (nba_hypotheses.h7) -- already
     SURVIVED on 2025-26 and REPLICATED on 2024-25; a third same-sign
     significant hit makes it the strongest finding in the ledger.
  b. endQ1 x floor_quality_now  -- conditional_gate_v2's live-state ladder,
     rung1. Record so far: 1 hit (2025-26 MATTERS_PROVISIONAL) vs 1 fail
     (2024-25 NULL). This run is the tiebreaker.
  c. endQ1 x star_minutes_load  -- same ladder, rung2. Same 1-hit/1-fail record.
  d. lineup spacing x transition frequency (derived_label_hypotheses) --
     SURVIVED on 2025-26 (effect=-0.00988, p=8.7e-10); first independent-
     corpus check.

PREREGISTERED BAR (declared before running, per the brief): K=4, plain
Bonferroni alpha=0.05/4=0.0125 -- NOT the eps_eff FWER-tightening curve
stats_common.alpha_fwer uses elsewhere (that curve is for a same-run multi-
hypothesis census; this is 4 independent CONFIRMATORY replications of
already-tested hypotheses, so a flat Bonferroni is the honest bar named here
and used for all 4, unchanged after seeing results).

VERDICT per hypothesis: REPLICATED requires BOTH same effect sign as the
prior hit AND p < 0.0125. Anything else is FAILED_REPLICATION -- an honest
miss, not a failure of this script.

METHOD: zero reimplementation --
  a: nba_hypotheses.build_continuity_dreb + stats_common.fit_single (same
     functions replicate_h7_2024_25.py used, pointed at the 2023-24 dirs).
  b/c: conditional_gate_v2.run_all_rungs("2023-24") (that module's
     _SEASON_DIRS map was extended with a "2023-24" entry this wave); pulls
     the endQ1 rung results for floor_quality_now / star_minutes_load.
  d: composition.shot_clock_proxy.build_shot_clock_frame +
     composition.transition_flag.build_transition_frame + the same sc/tf
     inner-join derived_label_hypotheses.build_frame does, then
     composition.shot_features.add_spacing pointed at the 2023-24
     stints/spacing artifacts (build_frame's internal add_spacing defaults
     to the 2025-26 paths, so the join is inlined here season-correct).

Prerequisite artifacts (built via existing CLIs, not new code) before (d) can
run: stints_2023_24.parquet -> on_off_2023_24.parquet -> lineup_spacing_2023_24
.parquet, the same pbp_lineups.py -> on_off.py -> gravity_spacing.py chain
already used for 2024-25/2025-26.

Descriptive/measurement only. edge_claimed hard-wired False on every row.
NETWORK: zero. CLI: python -m domains.basketball_nba.prereg.third_season_2023_24
Per-file test: python -m pytest domains/basketball_nba/prereg/test_third_season_2023_24.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from domains.basketball_nba.composition.shot_clock_proxy import build_shot_clock_frame
from domains.basketball_nba.composition.shot_features import add_spacing
from domains.basketball_nba.composition.transition_flag import (
    build_transition_frame, validate_vs_fastbreak_qualifier,
)
from domains.basketball_nba.prereg.nba_hypotheses import build_continuity_dreb
from domains.basketball_nba.prereg.stats_common import LEDGER_PATH, append_ledger, fit_interaction, fit_single
from scripts.platformkit.ingame_compose.cli import _row_v2
from scripts.platformkit.ingame_compose.conditional_gate_v2 import run_all_rungs
from scripts.platformkit.intel_weighting.weight_ledger import LEDGER as CLAIM_WEIGHTS_LEDGER

REPO_ROOT = Path(__file__).resolve().parents[3]
_BASE = REPO_ROOT / "data" / "cache" / "team_system"
_PBP_2324 = _BASE / "pbp_2023_24"
_STINTS_2324 = _BASE / "lineups" / "stints_2023_24.parquet"
_SPACING_2324 = _BASE / "lineups" / "lineup_spacing_2023_24.parquet"

ALPHA = 0.05 / 4  # K=4, plain Bonferroni -- declared in the brief, not stats_common's eps curve
METHOD = "third_season_2023_24"
METHOD_V2 = "ingame_livestate_v2_replication_2023_24"  # distinct from live METHOD_V2 -- never clobbers 2025-26 rows

_ORIGINAL_SIGN = {
    "stint continuity x defensive rebound rate (single-factor: no second named "
    "mechanism in the doc)": 1,       # 2025-26 census effect=+0.00065, replicated 2024-25 +0.00057
    "endQ1 x floor_quality_now": 1,   # 2025-26 delta=+0.000824
    "endQ1 x star_minutes_load": 1,   # 2025-26 delta=+0.001017
    "lineup spacing x transition frequency": -1,  # 2025-26 census effect=-0.00988
}


def _verdict_row(name: str, sport: str, atomic_unit: str, fit: Dict[str, Any],
                  note: str = "") -> Dict[str, Any]:
    """PURE: fit dict -> ledger row. same_sign(vs the prior hit) AND p<ALPHA
    both required for REPLICATED -- mirrors replicate_h7_2024_25.verdict_row."""
    if fit["n"] == 0:
        # the gate never scored a single game (UNTESTABLE upstream) -- an
        # un-run test is NOT a failed replication, it is not a test at all
        verdict = "NOT_TESTABLE"
        note = note or "n=0: gate produced no scoreable games on this corpus"
    else:
        same_sign = (fit["effect"] > 0) == (_ORIGINAL_SIGN[name] > 0)
        replicated = same_sign and fit["p"] < ALPHA
        verdict = "REPLICATED" if replicated else "FAILED_REPLICATION"
        note = note or ("" if replicated else "same-sign-and-p<alpha required for REPLICATED")
    return {
        "hypothesis": name, "sport": sport, "atomic_unit": atomic_unit,
        "method": METHOD, "n": fit["n"], "effect": fit["effect"], "p": fit["p"],
        "alpha_fwer": ALPHA, "term": fit["term"],
        "verdict": verdict,
        "note": note,
        "edge_claimed": False,
    }


def run_a_continuity_dreb() -> Dict[str, Any]:
    stints_df = pd.read_parquet(_STINTS_2324)
    cont = build_continuity_dreb(stints_df, pbp_dir=_PBP_2324)
    fit = fit_single(cont, "is_dreb ~ continuity_s", kind="logit")
    return _verdict_row(
        "stint continuity x defensive rebound rate (single-factor: no second "
        "named mechanism in the doc)", "nba", "rebound", fit,
    )


def run_bc_livestate_v2() -> tuple[List[Dict[str, Any]], List[Any]]:
    """Returns (2 ledger rows for b/c, full RungResult list for the claim_weights write)."""
    results, _cp_skips, _glob_skips = run_all_rungs("2023-24")
    by_key = {(r.checkpoint, r.rung): r for r in results}
    rows = []
    caveat = ("2023-24 proxies: top3-FGA derived from pbp shot events "
              "(player_boxscores lacks 2023-24; see conditional_gate_v2._pbp_top3_table); "
              "league shot rates at fallback constants for the same reason.")
    for hyp_name, rung in (("endQ1 x floor_quality_now", "floor_quality_now"),
                           ("endQ1 x star_minutes_load", "star_minutes_load")):
        r = by_key[("endQ1", rung)]
        fit = {"effect": r.delta, "p": r.dm_p, "n": r.n_test, "term": rung}
        row = _verdict_row(hyp_name, "nba", "team_asof_ingame", fit)
        row["note"] = (row["note"] + " " if row["note"] else "") + caveat
        rows.append(row)
    return rows, results


def run_d_spacing_transition() -> Dict[str, Any]:
    sc = build_shot_clock_frame(pbp_dir=_PBP_2324)
    tf = build_transition_frame(pbp_dir=_PBP_2324)
    # NOT derived_label_hypotheses.build_frame -- its internal add_spacing is
    # hardwired to the 2025-26 stints/spacing paths (every 2023-24 row would
    # silently get the median-fallback spacing). Same merge, season-correct paths.
    df = sc.merge(
        tf[["game_id", "team_id", "period", "elapsed_s", "is_transition"]],
        on=["game_id", "team_id", "period", "elapsed_s"], how="inner",
    )
    df = add_spacing(df, stints_src=_STINTS_2324, spacing_src=_SPACING_2324)
    fit = fit_interaction(df, "made ~ spacing_mean_dist * is_transition", kind="logit")
    tf_pr = validate_vs_fastbreak_qualifier(tf)
    if tf_pr["precision"] is None:
        # 2023-24 corpus is ESPN-derived: zero CDN 'fastbreak' qualifier rows to
        # validate against -- label quality rests on the 2025-26 validation.
        note = (f"is_transition derived label (2023-24): NO CDN fastbreak-qualifier rows "
                f"in this corpus (n={tf_pr['n']}); proxy quality not re-measurable here, "
                f"rests on the 2025-26 validation (precision=.172 recall=.905)")
    else:
        note = (f"is_transition derived label (2023-24): precision={tf_pr['precision']:.3f} "
                f"recall={tf_pr['recall']:.3f} vs the real 'fastbreak' qualifier (CDN-only n={tf_pr['n']})")
    return _verdict_row("lineup spacing x transition frequency", "nba", "possession", fit, note=note)


def _append_v2_claim_weights(results: List[Any], ledger: Path = CLAIM_WEIGHTS_LEDGER) -> Path:
    """Same upsert-by-(family, metric, method) discipline as cli.append_results_v2,
    with method overridden to METHOD_V2 (2023-24) so this NEVER upserts over the
    live 2025-26 rows (same precedent as the 2024-25 replication write)."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[tuple, dict] = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="ascii", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[(r.get("family"), r.get("metric"), r.get("method"))] = r
    for res in results:
        row = _row_v2(res)
        row["method"] = METHOD_V2
        existing[(row["family"], row["metric"], row["method"])] = row
    tmp = ledger.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="ascii", errors="strict") as f:
        for row in existing.values():
            f.write(json.dumps(row) + "\n")
    tmp.replace(ledger)
    return ledger


def run() -> List[Dict[str, Any]]:
    row_a = run_a_continuity_dreb()
    rows_bc, v2_results = run_bc_livestate_v2()
    row_d = run_d_spacing_transition()
    rows = [row_a, *rows_bc, row_d]
    append_ledger(rows)
    _append_v2_claim_weights(v2_results)
    return rows


def main() -> int:
    rows = run()
    print(f"K=4 alpha_bonferroni={ALPHA:.6f} (third-season 2023-24 confirmations)")
    for r in rows:
        print(f"  [{r['verdict']:>18}] {r['hypothesis']}: n={r['n']} effect={r['effect']} p={r['p']}")
    print(f"appended {len(rows)} rows -> {LEDGER_PATH}")
    print(f"appended full v2 board -> {CLAIM_WEIGHTS_LEDGER} (method={METHOD_V2})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
