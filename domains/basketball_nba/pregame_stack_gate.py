"""domains.basketball_nba.pregame_stack_gate -- Family 2 (nba_pregame_stack_v1) runner.

PREREG_STACK_FAMILIES_2026-07-05.md Family 2: does stacking solo-REJECTed box
dims (dreb/fg3m/stl/blk, pace/oreb/tov) onto walk-forward Elo improve calibration
when STACKED? Pre-registered STRUCTURAL BLOCKER: the only NBA base corpus is the
single 1299-row box-era asof_features.parquet -- no season-disjoint 2nd box
corpus exists. min_corpora_eff=2 is UNREACHABLE for the base-replication arm.
This family is therefore HARD-CODED to never return SHIP; the honest ceiling is
NOT_TESTABLE (fires structurally inside judge_stack_family's `len(corpora) < 2`
branch, since n_corpora_available=1 here) or REJECT.

BASE SPEC: 1-feature logistic [1, logit(p_elo)] -- p_elo is the SAME leak-free
walk-forward Elo the reclaim gates used (domains.basketball_nba.ratings.
walk_forward_elo via asof_ast_rate_eval.build_candidate_frame, reused verbatim
so start-state comparability with the 7 solo reclaim REJECTs holds).
CANDIDATES: nba_stack_box4 (base + z(dreb,fg3m,stl,blk)); nba_stack_top3 (base +
z(top-3 dims by |solo Brier delta| read from the 7 per-dim
reclaim_gate_<dim>.json files -- reclaim_gate_summary.json itself carries no
numeric deltas, only verdicts; ties -> alphabetical)).
CORPUS: the single 1299-row box-era asof_features.parquet joined to
asof_box_extra.parquet on game_id (asof_reclaim_dims.load_reclaim_frame),
restricted to Elo-coverage rows.
vs-CLOSE: data/cache/venue_history/nba_close_corpus.parquet, join key game_id;
n_overlap with the base rows is VERIFIED + LABELED (never blocks -- FABLE
ADJUDICATION Q3), reported as MATCH/BEHIND, never claimed as beating the close.

Judged through stack_gate_pregame.judge_stack_family. NO $ / edge anywhere; a
REJECT or NOT_TESTABLE is an honest success. NO src.*/kernel.* imports.

CLI: python -m domains.basketball_nba.pregame_stack_gate
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.basketball_nba import asof_ast_rate_eval as _elo_eval  # noqa: E402
from domains.basketball_nba.asof_reclaim_dims import load_reclaim_frame  # noqa: E402
from scripts.platformkit.combo import stack_fit as sf  # noqa: E402
from scripts.platformkit.combo.stack_gate_pregame import (  # noqa: E402
    StackRow, judge_stack_family,
)
from scripts.platformkit.reject_ledger import record  # noqa: E402

_DATA = _REPO / "data" / "domains" / "basketball_nba"
_CLOSE_CORPUS = _REPO / "data" / "cache" / "venue_history" / "nba_close_corpus.parquet"
_VERDICT_OUT = _DATA / "nba_pregame_stack_v1_verdict.json"

K_CUM = 2  # nba_stack_box4 + nba_stack_top3 (both new this cycle; K_prior=0)
BOX4_COLS = ("dreb_diff_asof", "fg3m_diff_asof", "stl_diff_asof", "blk_diff_asof")
ALL_DIM_COLS = ("pace_diff_asof", "oreb_pg_diff_asof", "tov_pg_diff_asof") + BOX4_COLS
CANDIDATES = ("nba_stack_box4", "nba_stack_top3")


def top3_dims_by_solo_delta(dims_dir: Path = _DATA) -> List[str]:
    """Read the 7 per-dim reclaim_gate_<dim>.json files; rank by |real.brier_delta|.

    reclaim_gate_summary.json carries verdicts only, no numeric deltas -- the
    deltas live in the individual per-dim files this reads. Ties -> alphabetical.
    """
    deltas: List[Tuple[float, str]] = []
    for dim in ALL_DIM_COLS:
        path = dims_dir / f"reclaim_gate_{dim}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        deltas.append((abs(float(payload["real"]["brier_delta"])), dim))
    deltas.sort(key=lambda t: (-t[0], t[1]))  # descending |delta|, alphabetical tiebreak
    return [d for _, d in deltas[:3]]


def build_base_corpus_frame() -> pd.DataFrame:
    """Elo (via the reclaim gates' own build_candidate_frame) + all 7 box dims.

    Reuses asof_ast_rate_eval.build_candidate_frame verbatim for the Elo replay
    (SAME walk_forward_elo call, SAME games.parquet, SAME warm/cold start state
    the 7 solo reclaim gates used) then left-merges the 7 dim columns from
    asof_reclaim_dims.load_reclaim_frame on game_id. Restricted to rows with
    Elo-side coverage (_cov, mirrors the solo reclaim gate's own coverage rule).
    """
    elo_frame = _elo_eval.build_candidate_frame(feat_col="ast_rate_diff_asof")
    elo_frame = elo_frame[elo_frame["_cov"]].reset_index(drop=True)
    dims = load_reclaim_frame()
    dims = dims[["game_id"] + list(ALL_DIM_COLS)].copy()
    dims["game_id"] = dims["game_id"].astype(str)
    out = elo_frame[["game_id", "date", "home_win", "p_base"]].merge(
        dims, on="game_id", how="left")
    return out.sort_values("date").reset_index(drop=True)


def _fit_base(train: pd.DataFrame) -> sf.LogisticFit:
    """1-feature BASE logistic [1, logit(p_elo)] -- prereg Family 2 base spec."""
    elo_logit = sf.logit(train["p_base"].to_numpy(float))
    X = sf.build_design([elo_logit])
    y = train["home_win"].to_numpy(float)
    return sf.fit_logistic(X, y)


def _fit_candidate(train: pd.DataFrame, added_cols: Sequence[str]
                   ) -> Tuple[sf.LogisticFit, sf.StandardizerParams]:
    """BASE feature + z(added_cols); NaN added rows contribute 0 post-standardize."""
    elo_logit = sf.logit(train["p_base"].to_numpy(float))
    added_raw = train[list(added_cols)].to_numpy(float)
    added_std = sf.fit_standardizer(added_raw)
    added_z = sf.standardize(added_raw, added_std)
    X = sf.build_design([elo_logit] + [added_z[:, i] for i in range(added_z.shape[1])])
    y = train["home_win"].to_numpy(float)
    return sf.fit_logistic(X, y), added_std


def _score_base(df: pd.DataFrame, fit: sf.LogisticFit) -> np.ndarray:
    elo_logit = sf.logit(df["p_base"].to_numpy(float))
    X = sf.build_design([elo_logit])
    return sf.predict_proba(X, fit.weights)


def _score_candidate(df: pd.DataFrame, fit: sf.LogisticFit,
                     added_std: sf.StandardizerParams, added_cols: Sequence[str],
                     p_base: np.ndarray) -> np.ndarray:
    elo_logit = sf.logit(df["p_base"].to_numpy(float))
    added_raw = df[list(added_cols)].to_numpy(float)
    added_z = sf.standardize(added_raw, added_std)
    X = sf.build_design([elo_logit] + [added_z[:, i] for i in range(added_z.shape[1])])
    p_cand = sf.predict_proba(X, fit.weights)
    raw_cols = [df[c].to_numpy(float) for c in added_cols]
    return sf.score_with_fallback(raw_cols, p_base, p_cand)


def fit_and_score_corpus(df: pd.DataFrame, added_cols: Sequence[str]) -> List[StackRow]:
    """Expanding-window mid-split fit (TRAIN=first half); score held-out 2nd half."""
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train, test = df.iloc[tr_idx], df.iloc[te_idx]

    base_fit = _fit_base(train)
    cand_fit, added_std = _fit_candidate(train, added_cols)

    p_base = _score_base(test, base_fit)
    p_cand = _score_candidate(test, cand_fit, added_std, added_cols, p_base)

    rows: List[StackRow] = []
    for i in range(len(test)):
        raw_vals = tuple(float(test.iloc[i][c]) for c in added_cols)
        rows.append(StackRow(event_id=str(test.iloc[i]["game_id"]),
                             y=float(test.iloc[i]["home_win"]),
                             p_base=float(p_base[i]), p_candidate=float(p_cand[i]),
                             added_raw=raw_vals))
    return rows


def close_overlap_and_brier(base_frame: pd.DataFrame, p_candidate_by_game: Dict[str, float]
                            ) -> Tuple[int, Optional[float]]:
    """vs-CLOSE judge (Q3: verify+LABEL overlap with base rows, never block on it)."""
    if not _CLOSE_CORPUS.exists():
        return 0, None
    close = pd.read_parquet(_CLOSE_CORPUS)
    close["game_id"] = close["game_id"].astype(str)
    base_ids = set(base_frame["game_id"].astype(str))
    overlap_ids = base_ids & set(close["game_id"])
    n_overlap = len(overlap_ids)
    if n_overlap == 0:
        return 0, None
    matched = close[close["game_id"].isin(overlap_ids)]
    p = np.array([p_candidate_by_game[g] for g in matched["game_id"] if g in p_candidate_by_game])
    y = matched.loc[matched["game_id"].isin(p_candidate_by_game.keys()), "home_win"].to_numpy(float)
    if len(p) == 0:
        return n_overlap, None
    return n_overlap, sf.brier(p, y)


def _seed_stability_p10(frame: pd.DataFrame, added_cols: Sequence[str]) -> float:
    """L3: >=5 bootstrap-refits of TRAIN rows; p10 of stack-vs-base held-out delta."""
    splits = sf.expanding_window_splits(len(frame), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train_full, test = frame.iloc[tr_idx].reset_index(drop=True), frame.iloc[te_idx]

    def _one(rng: np.random.Generator) -> float:
        resampled = train_full.iloc[sf.bootstrap_resample_rows(len(train_full), rng)]
        base_fit = _fit_base(resampled)
        cand_fit, added_std = _fit_candidate(resampled, added_cols)
        p_base = _score_base(test, base_fit)
        p_cand = _score_candidate(test, cand_fit, added_std, added_cols, p_base)
        y = test["home_win"].to_numpy(float)
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    deltas = sf.bootstrap_refit_deltas(_one, n_refits=5, base_seed=99)
    return float(np.percentile(deltas, 10))


def _make_nested_cv_fns(rows: Sequence[StackRow], cand_name: str) -> Tuple[object, object]:
    """L1 select+score fns (mirrors domains.mlb.pregame_stack_gate exactly)."""
    by_id = {r.event_id: r for r in rows}

    def _select(inner_game_ids: Sequence[str]):
        return cand_name

    def _score(spec, holdout_game_ids: Sequence[str]) -> float:
        held = [by_id[g] for g in holdout_game_ids if g in by_id]
        if not held:
            return float("nan")
        p_base = np.array([r.p_base for r in held])
        p_cand = np.array([r.p_candidate for r in held])
        y = np.array([r.y for r in held])
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    return _select, _score


def run() -> Dict[str, object]:
    """Full Family 2 gate: both candidates, ONE corpus (structurally NOT_TESTABLE
    at replication), vs-close overlap-labeled readout, planted-null, seed p10."""
    frame = build_base_corpus_frame()
    top3 = top3_dims_by_solo_delta()

    results: Dict[str, object] = {
        "corpus_n": len(frame), "top3_dims_selected": top3,
        "min_corpora_eff_guard": "hard-coded NOT_TESTABLE/REJECT only, never SHIP "
                                  "(single base corpus, no 2nd season-disjoint box parquet)",
    }
    for cand_name, added_cols in ((CANDIDATES[0], list(BOX4_COLS)), (CANDIDATES[1], top3)):
        rows = fit_and_score_corpus(frame, added_cols)
        game_ids = [r.event_id for r in rows]
        nested_select_fn, nested_score_fn = _make_nested_cv_fns(rows, cand_name)

        def _plant(rng: np.random.Generator, cols=added_cols) -> bool:
            shuffled = frame.copy()
            for c in cols:
                shuffled[c] = rng.permutation(shuffled[c].to_numpy())
            null_rows = fit_and_score_corpus(shuffled, cols)
            br_b = sf.brier(np.array([r.p_base for r in null_rows]),
                            np.array([r.y for r in null_rows]))
            br_c = sf.brier(np.array([r.p_candidate for r in null_rows]),
                            np.array([r.y for r in null_rows]))
            return bool(br_c < br_b)

        p_candidate_by_game = {r.event_id: r.p_candidate for r in rows}
        n_overlap, stack_brier_close = close_overlap_and_brier(frame, p_candidate_by_game)

        # SHARED HARNESS: n_corpora_available=1, corpora=[rows] -> len(corpora)<2 fires
        # NOT_TESTABLE at L4 structurally (prereg's expected honest ceiling); L1/L3/
        # planted-null are still RUN below (per prereg "run within-corpus WF + planted-
        # null + L1 selection") and recorded in detail even though the harness's own
        # gate short-circuits before consuming them -- reported honestly, not hidden.
        verdict = judge_stack_family(
            name=cand_name, corpora=[rows], corpus_labels=["2024-25_box_era"],
            base_feature_cols={"elo_logit": sf.logit(frame["p_base"].to_numpy(float))
                               [sf.expanding_window_splits(len(frame), 0.5, 1)[0].test_idx]},
            k_cum=K_CUM, n_corpora_available=1,
            nested_cv_select_fn=nested_select_fn, nested_cv_score_fn=nested_score_fn,
            nested_cv_game_ids=game_ids, planted_null_fn=_plant,
            close_brier=stack_brier_close, stack_brier_vs_close=stack_brier_close,
            seed_stability_p10=_seed_stability_p10(frame, added_cols),
        )
        detail = verdict.to_dict()
        detail["n_overlap_with_base_corpus"] = n_overlap
        detail["close_brier_on_overlap"] = stack_brier_close
        detail["added_cols"] = list(added_cols)
        detail["min_corpora_eff_unreachable"] = True
        # Hard guard (prereg-mandated): this family MUST NOT SHIP on this corpus.
        if detail["verdict"] == "SHIP":
            detail["verdict"] = "NOT_TESTABLE"
            detail["reason"] = ("prereg guard: min_corpora_eff=2 unreachable with 1 "
                                "available corpus -- SHIP is disallowed on this corpus "
                                "regardless of layer outcome")
        results[cand_name] = detail
        record("nba", "nba_pregame_stack_v1__" + cand_name, detail["verdict"], detail["reason"],
              source="funnel_gate",
              metrics={"layer": detail["layer"], "vs_close": detail["vs_close"],
                       "n_overlap_with_base_corpus": n_overlap})
    return results


def main() -> int:
    res = run()
    _VERDICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _VERDICT_OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("=" * 72)
    print("NBA PREGAME STACK v1 -- Family 2 (nba_pregame_stack_v1)")
    print("=" * 72)
    print(f"corpus_n={res['corpus_n']} top3_dims_selected={res['top3_dims_selected']}")
    for name in CANDIDATES:
        v = res[name]
        print(f"\n{name}: verdict={v['verdict']} layer={v['layer']} "
             f"vs_close={v['vs_close']} n_overlap={v['n_overlap_with_base_corpus']}\n"
             f"  reason={v['reason']}")
    print("\n(NOT_TESTABLE/REJECT = honest success; calibration only; no edge claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
