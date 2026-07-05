"""domains.mlb.pregame_stack_gate -- Family 1 (mlb_pregame_stack_v1) runner.

PREREG_STACK_FAMILIES_2026-07-05.md Family 1: does adding park_factor and/or
sp_ra_diff_asof (both already SOLO-REJECTed) to the 2-signal pregame BASE
[1, elo_logit, z(sp_first6_diff_ew)] improve calibration when STACKED?

BASE SPEC: 2-feature logistic (elo_logit, sp_first6_diff_ew) fit walk-forward
via stack_fit.fit_logistic. SAME Elo start state, SAME eval rows as candidates
(walk_forward_elo is called ONCE per corpus and shared).
CANDIDATES: mlb_stack_park (base + z(park_factor)); mlb_stack_park_ra (base +
z(park_factor) + z(sp_ra_diff_asof)).
CORPORA: games.parquet 2010-2021 (27983 rows, full added-feature coverage) and
games_current.parquet 2022-2026 (10826 rows, ZERO added-feature coverage --
pitchers.parquet/asof_park/asof_features cover corpus A ONLY, verified by the
lane; every corpus-B row therefore falls back to p_base per the prereg's
missing-feature rule, so B->A direction tests transfer while A->B on corpus B
degenerates to base==candidate on every row -- reported honestly, not hidden).
vs-CLOSE: oddsapi_close_corpus.build_states('mlb'), joined via team_resolver.

Judged through stack_gate_pregame.judge_stack_family (L0-L6 + FDR). NO $ / edge
anywhere; a REJECT is an honest success. NO src.*/kernel.* imports.

CLI: python -m domains.mlb.pregame_stack_gate
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.mlb.ratings import walk_forward_elo  # noqa: E402
from domains.mlb.asof_sp_form import build_sp_form_features  # noqa: E402
from scripts.platformkit.combo import stack_fit as sf  # noqa: E402
from scripts.platformkit.combo.stack_gate_pregame import (  # noqa: E402
    StackRow, judge_stack_family,
)
from scripts.platformkit.combo.nested_cv import outer_fold_of  # noqa: E402
from scripts.platformkit.odds_provider.oddsapi_close_corpus import build_states  # noqa: E402
from scripts.platformkit.odds_provider.team_resolver import canonical  # noqa: E402
from scripts.platformkit.reject_ledger import record  # noqa: E402

_GAMES_A = _REPO / "data/domains/mlb/games.parquet"
_GAMES_B = _REPO / "data/domains/mlb/games_current.parquet"
_PARK = _REPO / "data/domains/mlb/asof_park.parquet"
_ASOF = _REPO / "data/domains/mlb/asof_features.parquet"
_VERDICT_OUT = _REPO / "data/domains/mlb/mlb_pregame_stack_v1_verdict.json"

K_CUM = 2  # mlb_stack_park + mlb_stack_park_ra (both new this cycle; K_prior=0)
EPS = 0.05
CANDIDATES = ("mlb_stack_park", "mlb_stack_park_ra")


def _load_games(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    return df[df["target_home_win"].notna()].reset_index(drop=True)


def build_corpus_frame(games_path: Path) -> pd.DataFrame:
    """Elo + SP-form + park + RA merged on event_id, chronologically sorted.

    Shared Elo replay so base and every candidate see the IDENTICAL p_home_elo
    per row (same warm/cold state). Missing added features stay NaN (handled by
    the fallback contract downstream, never dropped).
    """
    games = _load_games(games_path)
    elo = walk_forward_elo(games)[["event_id", "date", "p_home_elo"]]
    sp = build_sp_form_features()[["event_id", "sp_first6_diff_ew"]]
    park = pd.read_parquet(_PARK)[["event_id", "park_factor"]]
    ra = pd.read_parquet(_ASOF)[["event_id", "sp_ra_diff_asof"]]

    out = games[["event_id", "target_home_win"]].merge(elo, on="event_id", how="left")
    out = out.merge(sp, on="event_id", how="left")
    out = out.merge(park, on="event_id", how="left")
    out = out.merge(ra, on="event_id", how="left")
    return out.sort_values("date").reset_index(drop=True)


def _fit_base(train: pd.DataFrame) -> Tuple[sf.LogisticFit, sf.StandardizerParams]:
    """2-feature BASE logistic [1, elo_logit, z(sp_first6_diff_ew)] on TRAIN only."""
    elo_logit = sf.logit(train["p_home_elo"].to_numpy(float))
    sp_std = sf.fit_standardizer(train["sp_first6_diff_ew"].to_numpy(float).reshape(-1, 1))
    sp_z = sf.standardize(train["sp_first6_diff_ew"].to_numpy(float).reshape(-1, 1), sp_std)[:, 0]
    X = sf.build_design([elo_logit, sp_z])
    y = train["target_home_win"].to_numpy(float)
    return sf.fit_logistic(X, y), sp_std


def _fit_candidate(train: pd.DataFrame, added_cols: Sequence[str]
                   ) -> Tuple[sf.LogisticFit, sf.StandardizerParams, sf.StandardizerParams]:
    """BASE features + z(added_cols); NaN added rows contribute 0 post-standardize
    (train fit only, matches the fallback contract used at SCORE time)."""
    elo_logit = sf.logit(train["p_home_elo"].to_numpy(float))
    sp_raw = train["sp_first6_diff_ew"].to_numpy(float)
    sp_std = sf.fit_standardizer(sp_raw.reshape(-1, 1))
    sp_z = sf.standardize(sp_raw.reshape(-1, 1), sp_std)[:, 0]
    added_raw = train[list(added_cols)].to_numpy(float)
    added_std = sf.fit_standardizer(added_raw)
    added_z = sf.standardize(added_raw, added_std)
    X = sf.build_design([elo_logit] + [sp_z] + [added_z[:, i] for i in range(added_z.shape[1])])
    y = train["target_home_win"].to_numpy(float)
    return sf.fit_logistic(X, y), sp_std, added_std


def _score_base(df: pd.DataFrame, fit: sf.LogisticFit, sp_std: sf.StandardizerParams) -> np.ndarray:
    elo_logit = sf.logit(df["p_home_elo"].to_numpy(float))
    sp_z = sf.standardize(df["sp_first6_diff_ew"].to_numpy(float).reshape(-1, 1), sp_std)[:, 0]
    X = sf.build_design([elo_logit, sp_z])
    return sf.predict_proba(X, fit.weights)


def _score_candidate(df: pd.DataFrame, fit: sf.LogisticFit, sp_std: sf.StandardizerParams,
                     added_std: sf.StandardizerParams, added_cols: Sequence[str],
                     p_base: np.ndarray) -> np.ndarray:
    elo_logit = sf.logit(df["p_home_elo"].to_numpy(float))
    sp_z = sf.standardize(df["sp_first6_diff_ew"].to_numpy(float).reshape(-1, 1), sp_std)[:, 0]
    added_raw = df[list(added_cols)].to_numpy(float)
    added_z = sf.standardize(added_raw, added_std)
    X = sf.build_design([elo_logit] + [sp_z] + [added_z[:, i] for i in range(added_z.shape[1])])
    p_cand = sf.predict_proba(X, fit.weights)
    raw_cols = [df[c].to_numpy(float) for c in added_cols]
    return sf.score_with_fallback(raw_cols, p_base, p_cand)


def fit_and_score_corpus(df: pd.DataFrame, added_cols: Sequence[str]
                         ) -> List[StackRow]:
    """Expanding-window mid-split fit (TRAIN=first half); score p_base/p_candidate
    on the held-out second half. NO reselect at the seam."""
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train, test = df.iloc[tr_idx], df.iloc[te_idx]

    base_fit, base_sp_std = _fit_base(train)
    cand_fit, cand_sp_std, added_std = _fit_candidate(train, added_cols)

    p_base = _score_base(test, base_fit, base_sp_std)
    p_cand = _score_candidate(test, cand_fit, cand_sp_std, added_std, added_cols, p_base)

    rows: List[StackRow] = []
    for i in range(len(test)):
        raw_vals = tuple(float(test.iloc[i][c]) for c in added_cols)
        rows.append(StackRow(event_id=str(test.iloc[i]["event_id"]),
                             y=float(test.iloc[i]["target_home_win"]),
                             p_base=float(p_base[i]), p_candidate=float(p_cand[i]),
                             added_raw=raw_vals))
    return rows


def _close_join_key(row: pd.Series) -> str:
    d = str(row["date"])[:10].replace("-", "")
    h, a = canonical("mlb", str(row["home_team"])), canonical("mlb", str(row["away_team"]))
    return f"{d}|{h}|{a}"


def close_brier_for_frame(games_df: pd.DataFrame) -> Optional[float]:
    """vs-CLOSE judge: build_states('mlb') joined via team_resolver + date."""
    states = build_states("mlb")
    if not states:
        return None
    close_idx: Dict[str, float] = {}
    for s in states:
        d = str(s["state_ts"])[:10].replace("-", "")
        h, a = canonical("mlb", str(s["home"])), canonical("mlb", str(s["away"]))
        close_idx[f"{d}|{h}|{a}"] = float(s["devig_close_prob"])
    keys = games_df.apply(_close_join_key, axis=1)
    matched = [(close_idx[k], float(y)) for k, y in
              zip(keys, games_df["target_home_win"]) if k in close_idx]
    if not matched:
        return None
    p = np.array([m[0] for m in matched])
    y = np.array([m[1] for m in matched])
    return sf.brier(p, y)


def _make_nested_cv_fns(rows: Sequence[StackRow], cand_name: str
                        ) -> Tuple[object, object]:
    """L1 select+score fns bound to ONE candidate's already-frozen (p_base, p_candidate).

    Only one spec is enumerated per call (the candidate name is fixed by the
    caller), so select_fn is deterministic; score_fn is the REAL sealed-holdout
    stack-vs-base Brier delta (positive = stack better), computed on the subset
    of `rows` whose event_id falls in the frozen outer holdout. This is what
    `nested.outer_score` in judge_stack_family actually gates on (mirrors
    combo_gate.py's score_fn: score a fixed spec on holdout ids, no re-fit).
    """
    by_id = {r.event_id: r for r in rows}

    def _select(inner_game_ids: Sequence[str]):
        return cand_name  # deterministic: one spec per candidate, no sub-variant search

    def _score(spec, holdout_game_ids: Sequence[str]) -> float:
        held = [by_id[g] for g in holdout_game_ids if g in by_id]
        if not held:
            return float("nan")
        p_base = np.array([r.p_base for r in held])
        p_cand = np.array([r.p_candidate for r in held])
        y = np.array([r.y for r in held])
        return sf.brier(p_base, y) - sf.brier(p_cand, y)  # >0 == stack beats base

    return _select, _score


def run() -> Dict[str, object]:
    """Full Family 1 gate: both candidates, both corpora, vs-close, planted-null."""
    frame_a = build_corpus_frame(_GAMES_A)
    frame_b = build_corpus_frame(_GAMES_B)
    close_brier = close_brier_for_frame(pd.concat([
        frame_a.merge(pd.read_parquet(_GAMES_A)[["event_id", "home_team", "away_team"]],
                      on="event_id"),
        frame_b.merge(pd.read_parquet(_GAMES_B)[["event_id", "home_team", "away_team"]],
                      on="event_id"),
    ], ignore_index=True))

    results: Dict[str, object] = {"corpus_a_n": len(frame_a), "corpus_b_n": len(frame_b),
                                  "close_brier": close_brier}
    for cand_name, added_cols in ((CANDIDATES[0], ["park_factor"]),
                                  (CANDIDATES[1], ["park_factor", "sp_ra_diff_asof"])):
        rows_a = fit_and_score_corpus(frame_a, added_cols)
        rows_b = fit_and_score_corpus(frame_b, added_cols)
        game_ids = [r.event_id for r in rows_a]
        te_idx_a = sf.expanding_window_splits(len(frame_a), 0.5, 1)[0].test_idx
        base_elo_logit_a = sf.logit(frame_a["p_home_elo"].to_numpy(float))[te_idx_a]
        nested_select_fn, nested_score_fn = _make_nested_cv_fns(rows_a, cand_name)

        def _plant(rng: np.random.Generator, cols=added_cols) -> bool:
            shuffled = frame_a.copy()
            for c in cols:
                shuffled[c] = rng.permutation(shuffled[c].to_numpy())
            null_rows = fit_and_score_corpus(shuffled, cols)
            br_b = sf.brier(np.array([r.p_base for r in null_rows]),
                            np.array([r.y for r in null_rows]))
            br_c = sf.brier(np.array([r.p_candidate for r in null_rows]),
                            np.array([r.y for r in null_rows]))
            return bool(br_c < br_b)  # a shuffled column "shipping" -> beats base at all

        stack_brier_vs_close = sf.brier(
            np.array([r.p_candidate for r in rows_a] + [r.p_candidate for r in rows_b]),
            np.array([r.y for r in rows_a] + [r.y for r in rows_b]))

        verdict = judge_stack_family(
            name=cand_name, corpora=[rows_a, rows_b], corpus_labels=["2010-2021", "2022-2026"],
            base_feature_cols={"elo_logit": base_elo_logit_a},
            k_cum=K_CUM, n_corpora_available=2,
            nested_cv_select_fn=nested_select_fn, nested_cv_score_fn=nested_score_fn,
            nested_cv_game_ids=game_ids, planted_null_fn=_plant,
            close_brier=close_brier, stack_brier_vs_close=stack_brier_vs_close,
            seed_stability_p10=_seed_stability_p10(frame_a, added_cols),
        )
        results[cand_name] = verdict.to_dict()
        record("mlb", "mlb_pregame_stack_v1__" + cand_name, verdict.verdict, verdict.reason,
              source="funnel_gate", metrics={"layer": verdict.layer, "vs_close": verdict.vs_close})
    return results


def _seed_stability_p10(frame: pd.DataFrame, added_cols: Sequence[str]) -> float:
    """L3: >=5 bootstrap-refits of TRAIN rows; p10 of stack-vs-base held-out delta."""
    splits = sf.expanding_window_splits(len(frame), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train_full, test = frame.iloc[tr_idx].reset_index(drop=True), frame.iloc[te_idx]

    def _one(rng: np.random.Generator) -> float:
        resampled = train_full.iloc[sf.bootstrap_resample_rows(len(train_full), rng)]
        base_fit, base_sp = _fit_base(resampled)
        cand_fit, cand_sp, added_std = _fit_candidate(resampled, added_cols)
        p_base = _score_base(test, base_fit, base_sp)
        p_cand = _score_candidate(test, cand_fit, cand_sp, added_std, added_cols, p_base)
        y = test["target_home_win"].to_numpy(float)
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    deltas = sf.bootstrap_refit_deltas(_one, n_refits=5, base_seed=99)
    return float(np.percentile(deltas, 10))


def main() -> int:
    import json
    res = run()
    _VERDICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _VERDICT_OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("=" * 72)
    print("MLB PREGAME STACK v1 -- Family 1 (mlb_pregame_stack_v1)")
    print("=" * 72)
    print(f"corpus_a_n={res['corpus_a_n']} corpus_b_n={res['corpus_b_n']} "
         f"close_brier={res['close_brier']}")
    for name in CANDIDATES:
        v = res[name]
        print(f"\n{name}: verdict={v['verdict']} layer={v['layer']} "
             f"vs_close={v['vs_close']}\n  reason={v['reason']}")
    print("\n(REJECT = honest success; calibration only; no edge ever claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
