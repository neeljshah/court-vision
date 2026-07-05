"""domains.soccer.home_sot_replication_gate -- Family 3 (soccer_home_sot_replication_v1):
genuine independent replication of the home_sot_for_l10 SHIP-at-gate.

PREREG_STACK_FAMILIES_2026-07-05.md Family 3: the original asof_reclaim_gate.json
SHIP replicated on exactly 1 of 11 YEAR-BUCKET pairs of ONE football-data.co.uk
source -- an unreplicated, flexibility-shaped prior; zero partial credit carries
in. This module runs the genuine independent test: 6 disjoint LEAGUES (not year
buckets of the same rows), tightened bar eps_eff=0.003846 (K_cum=13, floor=4).

BASE = domains.soccer.ratings.walk_forward_goals Poisson p_over25 (leak-free,
snapshot-before-update) -- the SAME base asof_features_gate/asof_reclaim_gate use.
CANDIDATE = base + z(home_sot_for_l10). Reuses asof_reclaim_gate_math.build_corpus
for the identical matches+asof_features merge (same base + state handling). Judged
through BOTH: (a) stack_gate_pregame.judge_stack_family (L0/L1/L2/L3/L6/FDR,
imported not reimplemented) on its adjacent-pair L4/L5 loop, AND (b) the prereg's
own STRICTER per-league floor (>=4-of-6 leagues pass, DM p<eps_eff, each league its
own cross-corpus unit) -- final verdict takes whichever is stricter.

vs-CLOSE: Q2-verified DROP of candidate 2 -- build_states('soccer_intl') never
carries any asof_features column (a 2-way home-win close corpus, not this
family's O/U 2.5; see wc_corpus_check). Bars STAY PINNED at K_cum=13/eps_eff=
0.003846 per the prereg's Q2 instruction. vs-close uses odds.parquet's own
O/U 2.5 devigged close (same source) as the in-corpus judge.

NO $/edge anywhere; a REJECT here CLOSES the candidate. NO src.*/kernel.*
imports. ASCII; <=300 LOC. CLI: python -m domains.soccer.home_sot_replication_gate
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.soccer.adapter import _devig_over  # noqa: E402
from domains.soccer.asof_reclaim_gate_math import build_corpus  # noqa: E402
from scripts.platformkit.combo import stack_fit as sf  # noqa: E402
from scripts.platformkit.combo.stack_gate_pregame import (  # noqa: E402
    StackRow, judge_stack_family, one_direction_dm,
)
from scripts.platformkit.combo.fwer_budget import eps_eff, min_corpora_eff  # noqa: E402
from scripts.platformkit.odds_provider.oddsapi_close_corpus import build_states  # noqa: E402
from scripts.platformkit.reject_ledger import record  # noqa: E402

_VERDICT_OUT = _REPO / "data" / "domains" / "soccer" / "soccer_home_sot_replication_v1_verdict.json"
_ODDS = _REPO / "data" / "domains" / "soccer" / "odds.parquet"

K_CUM = 13  # K_prior=11 (asof_reclaim_gate enumeration) + K_new=1 (WC dropped, Q2)
EPS_BASE = 0.05
LEAGUES: Tuple[str, ...] = ("E1", "E0", "SP1", "I1", "F1", "D1")
FEAT_COL = "home_sot_for_l10"
MIN_PRIOR = 5

def _fit_base(train: pd.DataFrame) -> Tuple[sf.LogisticFit, None]:
    """1-feature BASE logistic [1, p_over25_logit] -- the SAME base the original
    reclaim gate used (no standardizer needed; logit is already a natural scale)."""
    X = sf.build_design([sf.logit(train["p_over25"].to_numpy(float))])
    return sf.fit_logistic(X, train["target_over25"].to_numpy(float)), None

def _fit_candidate(train: pd.DataFrame) -> Tuple[sf.LogisticFit, sf.StandardizerParams]:
    base_logit = sf.logit(train["p_over25"].to_numpy(float))
    raw = train[[FEAT_COL]].to_numpy(float)
    std = sf.fit_standardizer(raw)
    z = sf.standardize(raw, std)[:, 0]
    X = sf.build_design([base_logit, z])
    return sf.fit_logistic(X, train["target_over25"].to_numpy(float)), std

def _score_base(df: pd.DataFrame, fit: sf.LogisticFit) -> np.ndarray:
    X = sf.build_design([sf.logit(df["p_over25"].to_numpy(float))])
    return sf.predict_proba(X, fit.weights)

def _score_candidate(df: pd.DataFrame, fit: sf.LogisticFit, std: sf.StandardizerParams,
                     p_base: np.ndarray) -> np.ndarray:
    base_logit = sf.logit(df["p_over25"].to_numpy(float))
    z = sf.standardize(df[[FEAT_COL]].to_numpy(float), std)[:, 0]
    p_cand = sf.predict_proba(sf.build_design([base_logit, z]), fit.weights)
    return sf.score_with_fallback([df[FEAT_COL].to_numpy(float)], p_base, p_cand)

def _covered(df: pd.DataFrame) -> pd.DataFrame:
    home_n = df.get("home_n_prior", pd.Series(0, index=df.index)).fillna(0)
    away_n = df.get("away_n_prior", pd.Series(0, index=df.index)).fillna(0)
    ok = (home_n >= MIN_PRIOR) & (away_n >= MIN_PRIOR) & df[FEAT_COL].notna()
    return df[ok].reset_index(drop=True)

def build_league_frame(league: str, full_corpus: pd.DataFrame) -> pd.DataFrame:
    """One league's covered, chronologically-sorted, target-labeled frame."""
    lf = full_corpus[full_corpus["div"] == league].sort_values("date").reset_index(drop=True)
    return _covered(lf)

def fit_and_score_league(df: pd.DataFrame) -> List[StackRow]:
    """Expanding-window mid-split (TRAIN=first half); NO reselect at the seam."""
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train, test = df.iloc[tr_idx], df.iloc[te_idx]
    base_fit, _ = _fit_base(train)
    cand_fit, cand_std = _fit_candidate(train)
    p_base = _score_base(test, base_fit)
    p_cand = _score_candidate(test, cand_fit, cand_std, p_base)
    return [StackRow(event_id=str(test.iloc[i]["event_id"]),
                     y=float(test.iloc[i]["target_over25"]),
                     p_base=float(p_base[i]), p_candidate=float(p_cand[i]),
                     added_raw=(float(test.iloc[i][FEAT_COL]),))
            for i in range(len(test))]

def per_league_replication(league_rows: Dict[str, List[StackRow]], eps: float
                           ) -> Dict[str, object]:
    """The prereg's LITERAL floor: >=4-of-6 leagues pass, DM p<eps on the WF
    held-out half (distinct from judge_stack_family's 5-adjacent-pair tally)."""
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
    adapter._devig_over on ou_close_over/ou_close_under (decimal odds -- the
    parquet's p_over/p_under are duplicate decimal-odds copies, NOT devigged
    probs; reading them raw would fabricate a close). NOT the WC corpus (Q2
    drop). Returns (stack_brier, close_brier) on the SAME rows."""
    odds = pd.read_parquet(_ODDS)[["event_id", "ou_close_over", "ou_close_under"]].copy()
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

def _make_nested_cv_fns(rows: Sequence[StackRow]) -> Tuple[object, object]:
    """One spec enumerated (the family has no sub-variant search); deterministic
    select, REAL sealed-holdout stack-vs-base Brier delta score (mirrors mlb Family 1)."""
    by_id = {r.event_id: r for r in rows}

    def _select(inner_game_ids: Sequence[str]):
        return "soccer_repl_home_sot"

    def _score(spec, holdout_game_ids: Sequence[str]) -> float:
        held = [by_id[g] for g in holdout_game_ids if g in by_id]
        if not held:
            return float("nan")
        p_base = np.array([r.p_base for r in held])
        p_cand = np.array([r.p_candidate for r in held])
        y = np.array([r.y for r in held])
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    return _select, _score

def _seed_stability_p10(df: pd.DataFrame) -> float:
    """L3: >=5 bootstrap refits of TRAIN rows; p10 of the held-out stack-vs-base delta."""
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train_full, test = df.iloc[tr_idx].reset_index(drop=True), df.iloc[te_idx]

    def _one(rng: np.random.Generator) -> float:
        resampled = train_full.iloc[sf.bootstrap_resample_rows(len(train_full), rng)]
        base_fit, _ = _fit_base(resampled)
        cand_fit, cand_std = _fit_candidate(resampled)
        p_base = _score_base(test, base_fit)
        p_cand = _score_candidate(test, cand_fit, cand_std, p_base)
        y = test["target_over25"].to_numpy(float)
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    deltas = sf.bootstrap_refit_deltas(_one, n_refits=5, base_seed=71)
    return float(np.percentile(deltas, 10))

def wc_corpus_check() -> Dict[str, object]:
    """Q2: build_states('soccer_intl') never carries home_sot_for_l10 (no asof_
    features parquet under data/domains/soccer_intl/); candidate 2 DROPPED."""
    states = build_states("soccer_intl")
    keys = set(states[0].keys()) if states else set()
    has_feat = FEAT_COL in keys
    reason = ("soccer_intl build_states carries no asof_features column (2-way "
             "home-win close corpus, not O/U 2.5 shot-stats); no shot/SoT sidecar on disk")
    return {"n_states": len(states), "state_keys": sorted(keys),
           "has_home_sot_for_l10": has_feat, "candidate_2_dropped": not has_feat,
           "reason": reason}

def run() -> Dict[str, object]:
    """Full Family 3 gate: 6 leagues, harness judge + literal per-league floor,
    planted-null, in-corpus close, WC-drop record."""
    full = build_corpus()
    league_rows: Dict[str, List[StackRow]] = {}
    league_frames: Dict[str, pd.DataFrame] = {}
    for lg in LEAGUES:
        lf = build_league_frame(lg, full)
        league_frames[lg] = lf
        league_rows[lg] = fit_and_score_league(lf)

    eps = eps_eff(EPS_BASE, K_CUM)
    min_corp = min_corpora_eff(len(LEAGUES), K_CUM)
    repl = per_league_replication(league_rows, eps)

    corpora = [league_rows[lg] for lg in LEAGUES]
    game_ids = [r.event_id for r in corpora[0]]
    base_col = {"p_over25_logit": sf.logit(np.array([r.p_base for r in corpora[0]]))}
    nested_select_fn, nested_score_fn = _make_nested_cv_fns(corpora[0])

    def _plant(rng: np.random.Generator) -> bool:
        """Within-league shuffle of home_sot_for_l10, refit; ships iff ANY league's
        shuffled stack beats base on its own test half."""
        any_ship = False
        for lg in LEAGUES:
            shuf = league_frames[lg].copy()
            shuf[FEAT_COL] = rng.permutation(shuf[FEAT_COL].to_numpy())
            null_rows = fit_and_score_league(shuf)
            if not null_rows:
                continue
            br_b = sf.brier(np.array([r.p_base for r in null_rows]),
                            np.array([r.y for r in null_rows]))
            br_c = sf.brier(np.array([r.p_candidate for r in null_rows]),
                            np.array([r.y for r in null_rows]))
            any_ship = any_ship or bool(br_c < br_b)
        return any_ship

    verdict = judge_stack_family(
        name="soccer_repl_home_sot", corpora=corpora, corpus_labels=list(LEAGUES),
        base_feature_cols=base_col, k_cum=K_CUM, n_corpora_available=len(LEAGUES),
        nested_cv_select_fn=nested_select_fn, nested_cv_score_fn=nested_score_fn,
        nested_cv_game_ids=game_ids, planted_null_fn=_plant,
        seed_stability_p10=_seed_stability_p10(league_frames[LEAGUES[0]]),
    )

    stack_close_brier, close_brier = close_brier_for_leagues(league_rows)
    vs_close = "not_evaluated"
    if np.isfinite(stack_close_brier) and np.isfinite(close_brier):
        vs_close = ("MATCH" if abs(stack_close_brier - close_brier) < 1e-3
                    else ("BEAT" if stack_close_brier < close_brier else "BEHIND"))
    # SHIP requires BOTH the harness verdict AND the literal per-league floor.
    final_verdict = verdict.verdict
    final_reason = verdict.reason
    if verdict.verdict == "SHIP" and not repl["floor_met"]:
        final_verdict = "PARTIAL"
        final_reason = (f"harness judge said SHIP but the prereg's literal per-league "
                        f"floor was NOT met ({repl['n_pass']}/6 leagues passed, need >=4)")

    wc_check = wc_corpus_check()
    out = {
        "verdict": final_verdict, "harness_layer_verdict": verdict.verdict,
        "layer": verdict.layer, "reason": final_reason, "vs_close": vs_close,
        "eps_eff": eps, "min_corpora_eff": min_corp, "k_cum": K_CUM,
        "n_leagues": len(LEAGUES), "league_n": {lg: len(league_frames[lg]) for lg in LEAGUES},
        "per_league_replication": repl, "wc_corpus_check": wc_check,
        "stack_close_brier": stack_close_brier, "close_brier": close_brier,
        "detail": verdict.detail, "caveats": verdict.caveats + [
            "candidate_2 (WC/soccer_intl) DROPPED per prereg Q2 -- verified absent, "
            "bars stay pinned at K_cum=13/eps_eff=0.003846 (never loosened).",
            "final verdict = harness judge AND the prereg's literal per-league floor "
            "(>=4/6 leagues), whichever is STRICTER (never loosened toward SHIP).",
        ],
    }
    record("soccer", "home_sot_for_l10__replication_v1", final_verdict, final_reason,
          corpus="6_league_split", source="funnel_gate",
          metrics={"layer": verdict.layer, "vs_close": vs_close, "eps_eff": eps,
                   "n_pass_leagues": repl["n_pass"], "n_leagues": repl["n_leagues"]})
    return out

def main() -> int:
    import json
    res = run()
    _VERDICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _VERDICT_OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("=" * 76)
    print("SOCCER HOME_SOT_FOR_L10 REPLICATION -- Family 3 (soccer_home_sot_replication_v1)")
    print("=" * 76)
    print(f"verdict={res['verdict']} (harness_layer={res['harness_layer_verdict']} "
         f"layer={res['layer']})  reason: {res['reason']}")
    r = res["per_league_replication"]
    print(f"per-league: {r['n_pass']}/6 pass (floor_met={r['floor_met']})")
    print(f"vs_close={res['vs_close']}  stack_brier={res['stack_close_brier']}  "
         f"close_brier={res['close_brier']}")
    w = res["wc_corpus_check"]
    print(f"wc_corpus_check: candidate_2_dropped={w['candidate_2_dropped']} reason={w['reason']}")
    print("\n(REJECT = honest success; calibration only; no edge ever claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
