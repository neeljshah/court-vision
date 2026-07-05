"""domains.soccer.interaction_gate -- A1-S soccer interaction candidates
(S1 soccer_xg_pace_sot_regime, S2 soccer_xg_supremacy_sot_confirm).

PREREG_AMENDMENT_A1_2026-07-05.md "Family continuation A1-S -- soccer family
(extends V1 Family 3 budget)". K_prior=13 (carried from home_sot_replication_
v1), K_new=2, K_cum=15 -> eps_eff=0.05/15=0.003333 (TIGHTER than V1 Family 3's
0.003846 -- the budget continues, never resets); min_corpora_eff=min(2+floor(
log2 15), 4, 6)=4. BASE identical to the solo reclaim gate: logistic
[1, p_over25_logit] from domains.soccer.ratings.walk_forward_goals, same
6-league div split (E1/E0/SP1/I1/F1/D1), expanding-window WF within league.

L1 sealed-holdout SELECTS between S1 and S2 (one frozen spec, never both);
L3 >=5 bootstrap refits p10 on the selected spec. Judged via
stack_gate_pregame.judge_stack_family PLUS the literal A1 floor enforced in
code: >=4-of-6 leagues pass BOTH directions at per-pair DM p<eps_eff AND
Brier+logloss unanimity vs the fitted base; final verdict = STRICTER of the
harness verdict and the literal floor (home_sot_replication_gate precedent).

PLANTED-NULL per A1: >=20 draws/league, permute the SOT columns WITHIN-league
(regime/agree indicator + product terms RECOMPUTED FROM THE PERMUTED columns,
so the interaction term is destroyed while xG + base columns stay intact);
fdr_hat<=eps_eff; any null ship => FROZEN. L1/L3/planted-null MECHANICS live
in interaction_gate_select.py (LOC-cap split); candidate feature math lives
in interaction_gate_math.py; this module is orchestration + the CLI only.

vs-CLOSE: ou_close_over/ou_close_under devigged via domains.soccer.adapter.
_devig_over (LANDMINE: p_over/p_under columns on odds.parquet are RAW DECIMAL
ODDS, never a devigged prob directly).

Mirrors home_sot_replication_gate.py's run() shape (does NOT import it --
that module is at its LOC cap, owned by wave-1). Does NOT modify
home_sot_replication_gate.py, asof_reclaim_gate_run.py, or any file outside
domains/soccer/interaction_gate*.py + this family's test file.

NO $/edge anywhere; a REJECT here is the expected, successful outcome (A1
"Expected outcome": most or all 4 candidates -- 2 tennis + these 2 soccer --
REJECTing). NO src.*/kernel.* imports. ASCII; <=300 LOC.
CLI: python -m domains.soccer.interaction_gate
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.soccer import interaction_gate_math as gm  # noqa: E402
from domains.soccer import interaction_gate_select as gs  # noqa: E402
from domains.soccer.adapter import _devig_over  # noqa: E402
from scripts.platformkit.combo import stack_fit as sf  # noqa: E402
from scripts.platformkit.combo.nested_cv import select_then_score  # noqa: E402
from scripts.platformkit.combo.stack_gate_pregame import (  # noqa: E402
    StackRow, judge_stack_family, one_direction_dm,
)
from scripts.platformkit.combo.fwer_budget import eps_eff, min_corpora_eff  # noqa: E402
from scripts.platformkit.reject_ledger import record  # noqa: E402

_VERDICT_OUT = _REPO / "data" / "domains" / "soccer" / "soccer_interactions_v1_verdict.json"

K_CUM = 15  # K_prior=13 (home_sot_replication_v1 carried) + K_new=2 (S1, S2)
EPS_BASE = 0.05
LEAGUES = gm.LEAGUES
CANDIDATES = gs.CANDIDATES
fit_and_score_league = gs.fit_and_score_league  # re-exported for test-import convenience


def per_league_replication(league_rows: Dict[str, List[StackRow]], eps: float
                           ) -> Dict[str, object]:
    """A1 literal floor: >=4-of-6 leagues pass, DM p<eps on the WF held-out
    half (mirrors home_sot_replication_gate.per_league_replication)."""
    per_league: Dict[str, object] = {}
    n_pass = 0
    for lg, rows in league_rows.items():
        y = np.array([r.y for r in rows])
        p_base = np.array([r.p_base for r in rows])
        p_cand = np.array([r.p_candidate for r in rows])
        gids = np.array([r.event_id for r in rows])
        d = one_direction_dm(y, p_base, p_cand, gids, eps, lg)
        n_pass += int(d.stack_beats_base)
        per_league[lg] = {"n": d.n, "brier_base": d.brier_base, "brier_stack": d.brier_stack,
                          "dm_p": d.dm_p, "passes": bool(d.stack_beats_base)}
    return {"per_league": per_league, "n_pass": n_pass, "n_leagues": len(league_rows),
            "floor_met": n_pass >= 4}


def close_brier_for_leagues(rows_by_league: Dict[str, List[StackRow]]) -> Tuple[float, float]:
    """In-corpus close judge: odds.parquet's O/U 2.5 close, DEVIGGED via
    adapter._devig_over on ou_close_over/ou_close_under (decimal odds --
    NEVER a raw p_over/p_under column). Same pattern as home_sot_replication
    _gate.close_brier_for_leagues."""
    odds = pd.read_parquet(gm._ODDS)[["event_id", "ou_close_over", "ou_close_under"]].copy()
    odds["event_id"] = odds["event_id"].astype(str)
    odds["p_close"] = odds.apply(
        lambda r: _devig_over(r["ou_close_over"], r["ou_close_under"]), axis=1)
    idx = dict(zip(odds["event_id"], odds["p_close"]))
    p_stack, p_close, y = [], [], []
    for rows in rows_by_league.values():
        for r in rows:
            if r.event_id in idx and np.isfinite(idx[r.event_id]):
                p_stack.append(r.p_candidate)
                p_close.append(float(idx[r.event_id]))
                y.append(r.y)
    if not y:
        return float("nan"), float("nan")
    return sf.brier(np.array(p_stack), np.array(y)), sf.brier(np.array(p_close), np.array(y))


def run() -> Dict[str, object]:
    """Full A1-S gate: L1-select between S1/S2, judge the winner on 6 leagues
    via the harness + literal per-league floor, planted-null, in-corpus close."""
    full = gm.build_corpus()
    league_frames: Dict[str, Dict[str, pd.DataFrame]] = {
        cand: {lg: gm.build_league_frame(lg, full, gm.CANDIDATE_RAW[cand]) for lg in LEAGUES}
        for cand in CANDIDATES
    }
    league_rows: Dict[str, Dict[str, List[StackRow]]] = {
        cand: {lg: gs.fit_and_score_league(league_frames[cand][lg], cand) for lg in LEAGUES}
        for cand in CANDIDATES
    }

    nested_select_fn = gs.select_fn_between_s1_s2(league_frames)
    rows_by_cand_first_league = {cand: league_rows[cand][LEAGUES[0]] for cand in CANDIDATES}
    nested_score_fn = gs.score_fn_for_selected(rows_by_cand_first_league)
    game_ids = [r.event_id for r in league_rows[CANDIDATES[0]][LEAGUES[0]]]

    eps = eps_eff(EPS_BASE, K_CUM)
    min_corp = min_corpora_eff(len(LEAGUES), K_CUM)

    # Probe selection ONCE (sealed-holdout, identical call judge_stack_family
    # repeats internally) purely to learn WHICH candidate name to attach to
    # per-league-floor / planted-null / seed-stability -- never re-selecting
    # after this; the SAME nested_select_fn/nested_score_fn are handed to
    # judge_stack_family below so its own L1 gate is the one that binds.
    nested_probe = select_then_score(nested_select_fn, nested_score_fn, game_ids)
    selected = str(nested_probe.selected_spec)

    corpora = [league_rows[selected][lg] for lg in LEAGUES]
    base_col = {"p_over25_logit": sf.logit(np.array([r.p_base for r in corpora[0]]))}
    repl = per_league_replication(league_rows[selected], eps)
    plant_fn = gs.plant_null_fn(league_frames[selected], selected)
    seed_p10 = gs.seed_stability_p10(league_frames[selected][LEAGUES[0]], selected)

    verdict = judge_stack_family(
        name=f"soccer_interaction_{selected.lower()}", corpora=corpora,
        corpus_labels=list(LEAGUES), base_feature_cols=base_col, k_cum=K_CUM,
        n_corpora_available=len(LEAGUES), nested_cv_select_fn=nested_select_fn,
        nested_cv_score_fn=nested_score_fn, nested_cv_game_ids=game_ids,
        planted_null_fn=plant_fn, seed_stability_p10=seed_p10,
    )

    stack_close_brier, close_brier = close_brier_for_leagues(league_rows[selected])
    vs_close = "not_evaluated"
    if np.isfinite(stack_close_brier) and np.isfinite(close_brier):
        vs_close = ("MATCH" if abs(stack_close_brier - close_brier) < 1e-3
                    else ("BEAT" if stack_close_brier < close_brier else "BEHIND"))

    # SHIP requires BOTH the harness verdict AND the literal A1 floor
    # (home_sot_replication_gate precedent: stricter of the two, never loosened).
    final_verdict = verdict.verdict
    final_reason = verdict.reason
    if verdict.verdict == "SHIP" and not repl["floor_met"]:
        final_verdict = "PARTIAL"
        final_reason = (f"harness judge said SHIP but the A1 literal per-league floor "
                        f"was NOT met ({repl['n_pass']}/6 leagues passed, need >=4)")

    out = {
        "verdict": final_verdict, "harness_layer_verdict": verdict.verdict,
        "layer": verdict.layer, "reason": final_reason, "vs_close": vs_close,
        "selected_candidate": selected, "l1_outer_score": nested_probe.outer_score,
        "eps_eff": eps, "min_corpora_eff": min_corp, "k_cum": K_CUM,
        "n_leagues": len(LEAGUES),
        "league_n": {cand: {lg: len(league_frames[cand][lg]) for lg in LEAGUES}
                    for cand in CANDIDATES},
        "per_league_replication": repl, "seed_stability_p10": seed_p10,
        "stack_close_brier": stack_close_brier, "close_brier": close_brier,
        "detail": verdict.detail, "caveats": verdict.caveats + [
            "L1 sealed-holdout SELECTED between S1 (soccer_xg_pace_sot_regime) and "
            f"S2 (soccer_xg_supremacy_sot_confirm) -> {selected}; the other candidate "
            "is NOT separately judged (one frozen spec per prereg L1/L3).",
            "sot columns enter ONLY inside interaction/isolation terms (S1's z(tot_sot_l10) "
            "main effect exists solely to isolate the regime product per interaction "
            "hygiene); the CLOSED home_sot solo family is not re-gated.",
            "final verdict = harness judge AND the A1 literal per-league floor (>=4/6 "
            "leagues), whichever is STRICTER (never loosened toward SHIP).",
        ],
    }
    record("soccer", f"interaction_{selected.lower()}_v1", final_verdict, final_reason,
          corpus="6_league_split", source="funnel_gate",
          metrics={"layer": verdict.layer, "vs_close": vs_close, "eps_eff": eps,
                   "n_pass_leagues": repl["n_pass"], "n_leagues": repl["n_leagues"],
                   "selected_candidate": selected})
    return out


def main() -> int:
    import json
    res = run()
    _VERDICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _VERDICT_OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("=" * 76)
    print("SOCCER A1-S INTERACTIONS -- xg_pace_sot_regime / xg_supremacy_sot_confirm")
    print("=" * 76)
    print(f"selected_candidate={res['selected_candidate']}  "
         f"verdict={res['verdict']} (harness_layer={res['harness_layer_verdict']} "
         f"layer={res['layer']})  reason: {res['reason']}")
    r = res["per_league_replication"]
    print(f"per-league: {r['n_pass']}/6 pass (floor_met={r['floor_met']})")
    print(f"vs_close={res['vs_close']}  stack_brier={res['stack_close_brier']}  "
         f"close_brier={res['close_brier']}")
    print("\n(REJECT = honest success; calibration only; no edge ever claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run", "main", "fit_and_score_league", "per_league_replication",
           "close_brier_for_leagues", "K_CUM", "LEAGUES", "CANDIDATES"]
