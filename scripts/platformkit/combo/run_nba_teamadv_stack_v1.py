"""scripts.platformkit.combo.run_nba_teamadv_stack_v1 -- A3 Family 3 runner.

PREREG_AMENDMENT_A3_2026-07-06.md (binding on V1, which stays FROZEN): does
stacking trailing team-advanced ratings (off/def rtg, four-factors) onto
walk-forward Elo improve calibration when STACKED, on the era-disjoint
2022-24 / 2024-25 pair asof_team_adv.parquet supplies?

BASE: 1-feature logistic [1, logit(p_elo)] -- SAME form as V1/A2 Family 2.
p_elo = domains.basketball_nba.ratings.walk_forward_elo over the FULL
games.parquet (2022-10 warm start). CANDIDATES (A3 clause 2, verbatim):
  TA1 nba_stack_ratings:      [logit(p_elo), z(off_rtg_diff), z(def_rtg_diff)]
  TA2 nba_stack_four_factors: [logit(p_elo), z(efg_pct_diff), z(tov_ratio_diff),
                               z(oreb_pct_diff)]
CORPORA (SAME-SOURCE pipeline; era-disjoint, NOT independent -- A3 clause 3
REPLICATED_WEAK cap applies, verdict can NEVER read SHIP here): CORPUS A =
2022-23+2023-24 (2460 games); CORPUS B = 2024-25 (1225). n_prior=0 rows
(either side) fall back to p_base via score_with_fallback (the asof NaNs on
those exact rows trigger it). vs-CLOSE: nba_close_corpus.parquet, join key
game_id, overlap VERIFIED+LABELED per corpus (never blocks).

Judged through stack_gate_pregame.judge_stack_family (L0-L6+FDR), K_cum=6
(K_prior=4 from V1 Family 2 + A2, NOT re-litigated). NO $ / edge anywhere;
REJECT/REPLICATED_WEAK is the expected, honest outcome. NO src.*/kernel.*.

CLI: python -m scripts.platformkit.combo.run_nba_teamadv_stack_v1
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.basketball_nba.ratings import walk_forward_elo  # noqa: E402
from scripts.platformkit.combo import null_floor as nf, stack_fit as sf  # noqa: E402
from scripts.platformkit.combo.stack_gate_pregame import StackRow, judge_stack_family  # noqa: E402
from scripts.platformkit.reject_ledger import record  # noqa: E402

_GAMES = _REPO / "data/domains/basketball_nba/games.parquet"
_TEAM_ADV = _REPO / "data/domains/basketball_nba/asof_team_adv.parquet"
_CLOSE_CORPUS = _REPO / "data/cache/venue_history/nba_close_corpus.parquet"
_VERDICT_OUT = _REPO / "data/domains/basketball_nba/nba_teamadv_stack_v1_verdict.json"

K_CUM = 6  # A3 clause 2: K_prior=4 (V1 Family2 P1/P2 + A2 N1/N2) + K_new=2 (TA1/TA2)
CORPUS_A_SEASONS = ("2022-23", "2023-24")
CORPUS_B_SEASONS = ("2024-25",)
TA1_COLS = ("off_rtg_diff_asof", "def_rtg_diff_asof")
TA2_COLS = ("efg_pct_diff_asof", "tov_ratio_diff_asof", "oreb_pct_diff_asof")
CANDIDATES = ("nba_stack_ratings", "nba_stack_four_factors")


def _season_to_int(season: object) -> int:
    """'2022-23' -> 2022 (walk_forward_elo consumes int(season); mirrors the
    same one-line convention domains.basketball_nba.adapter uses)."""
    s = str(season)
    return int(s.split("-")[0]) if "-" in s else (int(s) if s.isdigit() else 0)


def build_corpus_frame() -> pd.DataFrame:
    """games.parquet (zero-padded game_id) joined 1:1 to asof_team_adv.parquet,
    with p_elo from a walk-forward Elo replay over the FULL games.parquet (so
    2022-24 Elo warms from real 2022-10 games -- no truncated warm start)."""
    games = pd.read_parquet(_GAMES)
    games["game_id"] = games["game_id"].astype(str).str.zfill(10)
    games["_season_orig"] = games["season"]
    games["season"] = games["season"].apply(_season_to_int)
    elo = walk_forward_elo(games)[["game_id", "date", "_season_orig", "home_win", "p_home_elo"]]
    elo = elo.rename(columns={"_season_orig": "season"})
    adv = pd.read_parquet(_TEAM_ADV)
    adv["game_id"] = adv["game_id"].astype(str).str.zfill(10)
    keep = ["game_id"] + list(TA1_COLS) + list(TA2_COLS)
    out = elo.merge(adv[keep], on="game_id", how="inner")
    return out.sort_values("date").reset_index(drop=True)


def _fit_base(train: pd.DataFrame) -> sf.LogisticFit:
    """1-feature BASE logistic [1, logit(p_elo)] -- IDENTICAL form to V1/A2 Family 2."""
    elo_logit = sf.logit(train["p_home_elo"].to_numpy(float))
    X = sf.build_design([elo_logit])
    y = train["home_win"].to_numpy(float)
    return sf.fit_logistic(X, y)


def _fit_candidate(train: pd.DataFrame, added_cols: Sequence[str]
                   ) -> Tuple[sf.LogisticFit, sf.StandardizerParams]:
    """BASE feature + z(added_cols); z fit on TRAIN only (stack_fit.fit_standardizer)."""
    elo_logit = sf.logit(train["p_home_elo"].to_numpy(float))
    added_raw = train[list(added_cols)].to_numpy(float)
    added_std = sf.fit_standardizer(added_raw)
    added_z = sf.standardize(added_raw, added_std)
    X = sf.build_design([elo_logit] + [added_z[:, i] for i in range(added_z.shape[1])])
    y = train["home_win"].to_numpy(float)
    return sf.fit_logistic(X, y), added_std


def _score_base(df: pd.DataFrame, fit: sf.LogisticFit) -> np.ndarray:
    elo_logit = sf.logit(df["p_home_elo"].to_numpy(float))
    X = sf.build_design([elo_logit])
    return sf.predict_proba(X, fit.weights)


def _score_candidate(df: pd.DataFrame, fit: sf.LogisticFit,
                     added_std: sf.StandardizerParams, added_cols: Sequence[str],
                     p_base: np.ndarray) -> np.ndarray:
    elo_logit = sf.logit(df["p_home_elo"].to_numpy(float))
    added_raw = df[list(added_cols)].to_numpy(float)
    added_z = sf.standardize(added_raw, added_std)
    X = sf.build_design([elo_logit] + [added_z[:, i] for i in range(added_z.shape[1])])
    p_cand = sf.predict_proba(X, fit.weights)
    raw_cols = [df[c].to_numpy(float) for c in added_cols]
    return sf.score_with_fallback(raw_cols, p_base, p_cand)


def _fit_score(train: pd.DataFrame, test: pd.DataFrame,
              added_cols: Sequence[str]) -> Tuple[np.ndarray, np.ndarray]:
    """Fit base+candidate on TRAIN, score both on TEST -- shared by the corpus
    pass and the L3 bootstrap-refit loop (same fit/score path, only TRAIN differs)."""
    base_fit = _fit_base(train)
    cand_fit, added_std = _fit_candidate(train, added_cols)
    p_base = _score_base(test, base_fit)
    p_cand = _score_candidate(test, cand_fit, added_std, added_cols, p_base)
    return p_base, p_cand


def fit_and_score_corpus(df: pd.DataFrame, added_cols: Sequence[str]) -> List[StackRow]:
    """Expanding-window mid-split fit (TRAIN=first half); score held-out 2nd half."""
    splits = sf.expanding_window_splits(len(df), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train, test = df.iloc[tr_idx], df.iloc[te_idx]
    p_base, p_cand = _fit_score(train, test, added_cols)
    rows: List[StackRow] = []
    for i in range(len(test)):
        raw_vals = tuple(float(test.iloc[i][c]) for c in added_cols)
        rows.append(StackRow(event_id=str(test.iloc[i]["game_id"]),
                             y=float(test.iloc[i]["home_win"]),
                             p_base=float(p_base[i]), p_candidate=float(p_cand[i]),
                             added_raw=raw_vals))
    return rows


def fallback_count(df: pd.DataFrame, added_cols: Sequence[str]) -> int:
    """Count of rows where >=1 added col is non-finite (either side n_prior=0)."""
    has_all = np.ones(len(df), dtype=bool)
    for c in added_cols:
        has_all &= np.isfinite(df[c].to_numpy(float))
    return int((~has_all).sum())


def close_overlap_and_brier(base_frame: pd.DataFrame, p_candidate_by_game: Dict[str, float]
                            ) -> Tuple[int, Optional[float]]:
    """vs-CLOSE judge (A3 clause 5): verify+LABEL overlap, never claim beating it."""
    if not _CLOSE_CORPUS.exists():
        return 0, None
    close = pd.read_parquet(_CLOSE_CORPUS)
    close["game_id"] = close["game_id"].astype(str).str.zfill(10)
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
    """L3: >=5 bootstrap-refits; p10 of stack-vs-base held-out delta."""
    splits = sf.expanding_window_splits(len(frame), initial_train_frac=0.5, n_folds=1)
    tr_idx, te_idx = splits[0].train_idx, splits[0].test_idx
    train_full, test = frame.iloc[tr_idx].reset_index(drop=True), frame.iloc[te_idx]
    y = test["home_win"].to_numpy(float)

    def _one(rng: np.random.Generator) -> float:
        resampled = train_full.iloc[sf.bootstrap_resample_rows(len(train_full), rng)]
        p_base, p_cand = _fit_score(resampled, test, added_cols)
        return sf.brier(p_base, y) - sf.brier(p_cand, y)

    deltas = sf.bootstrap_refit_deltas(_one, n_refits=5, base_seed=99)
    return float(np.percentile(deltas, 10))


def _make_nested_cv_fns(rows_holdout_source: Sequence[StackRow], cand_name: str
                        ) -> Tuple[object, object]:
    """L1 select+score fns (mirrors domains.mlb/basketball_nba.pregame_stack_gate)."""
    by_id = {r.event_id: r for r in rows_holdout_source}

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


def _null_floor_prescreen(sport: str, corpus_unit: str, n_extra: int,
                          candidate_delta: float) -> Optional[str]:
    """A3 clause 4: null_floor prescreen MAY auto-REJECT (layer=FDR_PRESCREEN);
    NEVER substitutes for the full ceremony. Returns None (proceed to full
    ceremony) when no floor table is cached for this unit -- the prescreen is
    optional per its own module contract, never a blocker."""
    try:
        return nf.prescreen_verdict(sport, corpus_unit, n_extra, candidate_delta)
    except (FileNotFoundError, KeyError):
        return None


def run() -> Dict[str, object]:
    """Full A3 Family 3 gate: both candidates, 2 era-disjoint corpora (same-source
    pipeline -- REPLICATED_WEAK cap applies), vs-close labeled, planted-null, L1/L3."""
    frame = build_corpus_frame()
    frame_a = frame[frame["season"].isin(CORPUS_A_SEASONS)].reset_index(drop=True)
    frame_b = frame[frame["season"].isin(CORPUS_B_SEASONS)].reset_index(drop=True)
    results: Dict[str, object] = {
        "corpus_a_n": len(frame_a), "corpus_b_n": len(frame_b),
        "corpus_a_expected": 2460, "corpus_b_expected": 1225, "same_source_pipeline": True,
        "replicated_weak_cap": "any SHIP-clearing candidate is capped to REPLICATED_WEAK "
                              "(proposal_only=true) per A3 clause 3 -- never a live SHIP "
                              "on this same-source era-disjoint pair.",
    }
    for cand_name, added_cols in ((CANDIDATES[0], list(TA1_COLS)),
                                  (CANDIDATES[1], list(TA2_COLS))):
        results[f"{cand_name}_fallback_n_corpus_a"] = fallback_count(frame_a, added_cols)
        results[f"{cand_name}_fallback_n_corpus_b"] = fallback_count(frame_b, added_cols)
        # A3 clause 4: null_floor prescreen first (optional cheap early-exit).
        rows_a = fit_and_score_corpus(frame_a, added_cols)
        y_a = np.array([r.y for r in rows_a])
        delta_a = (sf.brier(np.array([r.p_base for r in rows_a]), y_a) -
                  sf.brier(np.array([r.p_candidate for r in rows_a]), y_a))
        prescreen = _null_floor_prescreen("nba", "2022-23_2023-24_teamadv", len(added_cols), delta_a)
        if prescreen == "REJECT":
            reason = f"null_floor prescreen: delta <= p99 of matched noise floor (delta={delta_a:.6f})"
            detail = {"verdict": "REJECT", "reason": reason, "layer": "FDR_PRESCREEN",
                     "vs_close": "not_evaluated", "proposal_only": True,
                     "detail": {}, "coverage": {}, "caveats": []}
            results[cand_name] = detail
            record("nba", "nba_teamadv_stack_v1__" + cand_name, "REJECT", reason,
                  source="funnel_gate", metrics={"layer": "FDR_PRESCREEN"})
            continue
        rows_b = fit_and_score_corpus(frame_b, added_cols)
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
            return bool(br_c < br_b)

        p_candidate_by_game = {r.event_id: r.p_candidate for r in rows_a + rows_b}
        overlap = [close_overlap_and_brier(f, p_candidate_by_game) for f in (frame_a, frame_b)]
        (n_overlap_a, close_brier_a), (n_overlap_b, close_brier_b) = overlap
        stack_brier_vs_close = sf.brier(
            np.array([r.p_candidate for r in rows_a] + [r.p_candidate for r in rows_b]),
            np.array([r.y for r in rows_a] + [r.y for r in rows_b]))
        close_brier = close_brier_a if close_brier_a is not None else close_brier_b
        verdict = judge_stack_family(
            name=cand_name, corpora=[rows_a, rows_b],
            corpus_labels=["2022-23_2023-24", "2024-25"],
            base_feature_cols={"elo_logit": base_elo_logit_a},
            k_cum=K_CUM, n_corpora_available=2,
            nested_cv_select_fn=nested_select_fn, nested_cv_score_fn=nested_score_fn,
            nested_cv_game_ids=[r.event_id for r in rows_a], planted_null_fn=_plant,
            close_brier=close_brier, stack_brier_vs_close=stack_brier_vs_close,
            seed_stability_p10=_seed_stability_p10(frame_a, added_cols),
        )
        detail = verdict.to_dict()
        detail["n_overlap_corpus_a"] = n_overlap_a
        detail["n_overlap_corpus_b"] = n_overlap_b
        detail["close_brier_corpus_a"] = close_brier_a
        detail["close_brier_corpus_b"] = close_brier_b
        detail["added_cols"] = list(added_cols)
        # A3 clause 3: MANDATORY cap -- same-source pipeline, NOT independent-source.
        if detail["verdict"] == "SHIP":
            detail["verdict"] = "REPLICATED_WEAK"
            detail["reason"] = ("A3 clause 3: all V1 JUDGMENT layers passed, but corpus A/B "
                                "share ONE team_advanced_stats pipeline (era-disjoint, not "
                                "independent-source) -- capped, requires independent-source "
                                "confirmation before promotion; NEVER SHIP/wired/flipped.")
        detail["proposal_only"] = True
        results[cand_name] = detail
        record("nba", "nba_teamadv_stack_v1__" + cand_name, detail["verdict"], detail["reason"],
              source="funnel_gate",
              metrics={"layer": detail["layer"], "vs_close": detail["vs_close"],
                       "n_overlap_corpus_a": n_overlap_a, "n_overlap_corpus_b": n_overlap_b})
    return results


def main() -> int:
    res = run()
    _VERDICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    _VERDICT_OUT.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("NBA TEAM-ADV STACK v1 -- A3 Family 3: "
         f"corpus_a_n={res['corpus_a_n']} corpus_b_n={res['corpus_b_n']}")
    for name in CANDIDATES:
        v = res[name]
        print(f"{name}: verdict={v['verdict']} layer={v['layer']} "
             f"vs_close={v.get('vs_close')} reason={v['reason']}")
    print("(REJECT/REPLICATED_WEAK = honest ceiling; calibration only; no edge claimed.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
