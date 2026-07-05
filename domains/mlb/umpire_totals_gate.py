"""domains.mlb.umpire_totals_gate -- leak-free umpire-tendency-vs-totals PRE-REGISTERED gate.

HYPOTHESIS (pre-registered, binding): home-plate umpire zone tendency (per-
umpire out-of-zone STRIKE rate, called-or-swung -- see catcher_framing_index.py
CORRECTNESS FIX for why this is not an isolated called-strike rate) carries
predictive signal for a game's TOTAL RUNS beyond an internal season/park-
adjusted baseline. EXPECTATION = REJECT (MLB pregame is proven efficient;
umpire effects are plausibly priced or small). A clean REJECT is a full
SUCCESS here, not a failure -- see .claude/rules/no-edge-claims.md.

SCOPE: internal-baseline MATCH-not-beat framing only. NO market totals close
is used anywhere (no features, no comparison) -- vs-close is OUT OF SCOPE.

CORPUS: statcast_fuller 2022+2023 pitch-level parquets, joined DIRECTLY on
game_pk to data/domains/mlb/probables.parquet (hp_umpire_id, game_date,
home_team). Verified live this session: 4861 distinct games with a resolved
hp_umpire_id (103 distinct umpires), 100%% game_date agreement between the
statcast-derived date and probables.parquet's game_date on the joined set.
total_runs is derived directly from statcast's own post_home_score/
post_away_score (max per game_pk = final score; monotonic across a game) --
NOT from games_current.parquet/games.parquet (disjoint season range / team
codes).

BASELINE (simplest internal baseline, per LANE spec): expanding chronological
league-mean total runs (games strictly before game i), mirroring
weather_totals_gate.py's baseline, PLUS an expanding per-home-team park
adjustment (home_team as it appears natively in probables.parquet -- no
cross-corpus team-code mapping needed). No market totals used anywhere.

CANDIDATE = baseline + umpire tendency term, recomputed EXPANDING/AS-OF
WITHIN THIS GATE (per LANE spec: never use the pooled umpire_zone_index.
parquet as a feature for in-corpus games -- it would leak future games).
For game i: that umpire's expanding-prior (games strictly before i, same
hp_umpire_id) out-of-zone-strike-rate MINUS the same-window league-expanding
rate (demeaned, centered at 0 = neutral). Fewer than MIN_UMPIRE_PRIOR prior
games for that umpire -> falls back to 0.0 (no signal, no guess) -- same
fallback discipline as weather_totals_gate.py's missing-weather case.

REUSE: derive_out_of_zone() imported from domains.mlb.catcher_framing_index
(identical zone-based out-of-zone predicate as umpire_zone_index.py -- never
re-derived).

GATE-COMPARABILITY: baseline and candidate scored on IDENTICAL walk-forward
folds; candidate differs from baseline ONLY by the additive umpire term.

PLANTED NULL (mandatory): shuffle_umpire_assignment shuffles hp_umpire_id
ACROSS games (breaking the true umpire<->game link, preserving each game's
real total_runs/date). run_gate emits both real_result and null_result so a
real "beat" matched by the null is exposed as an added-flexibility artifact,
not umpire signal (mirrors the MLB SP fatigue in-game gate precedent).

METHOD: walk-forward, >=3 folds (equal-size chronological slices after a
burn-in), min 200 games/fold. Metric = RMSE (+MAE reported). Verdict =
SHIP_REVIEW only if candidate beats baseline RMSE in ALL folds AND the real
candidate's improvement exceeds the planted-null candidate's improvement;
otherwise REJECT. EXPECTED VERDICT (pre-registered) = REJECT.

NETWORK: zero. Pure pandas/numpy over already-materialized parquets.
NO src/kernel/api imports. ASCII only. <=300 LOC.

CLI:
    python -m domains.mlb.umpire_totals_gate
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from domains.mlb.catcher_framing_index import derive_out_of_zone

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROBABLES = _REPO_ROOT / "data" / "domains" / "mlb" / "probables.parquet"
_OUT_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "umpire_totals_gate_verdict.json"
_ROWS_OUT_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "umpire_totals_gate_rows.parquet"

SEASONS = (2022, 2023)
BURN_IN: int = 300          # games before any candidate/baseline is scored (league + park warmup)
N_FOLDS: int = 3
MIN_PER_FOLD: int = 200
MIN_UMPIRE_PRIOR: int = 15  # min prior games for THIS umpire before its term is non-zero
PARK_MIN_GAMES: int = 10    # min prior home games before a park adjustment applies


_STATCAST_PATHS = {
    2022: _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet",
    2023: _REPO_ROOT / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet",
}


def _load_raw_statcast(seasons: tuple = SEASONS) -> pd.DataFrame:
    """Full pitch-level rows (incl. type=='X', balls in play) for both the
    final-score derivation and the ooz (type in {S,B}) subset."""
    frames = [pd.read_parquet(_STATCAST_PATHS[s]) for s in seasons]
    return pd.concat(frames, ignore_index=True)


def build_umpire_totals_corpus(
    raw: Optional[pd.DataFrame] = None,
    probables: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """statcast (2022+2023) -> per-game total_runs + per-game ooz strike counts,
    joined on game_pk to probables.parquet's hp_umpire_id/game_date/home_team.

    Columns: game_pk, date, home_team, hp_umpire_id, total_runs, n_ooz,
    ooz_strikes. Sorted chronologically (date, game_pk) mergesort-stable.
    Rows without a resolved hp_umpire_id are dropped (never guessed).
    """
    if raw is None:
        raw = _load_raw_statcast()

    totals = raw.groupby("game_pk").agg(
        final_home=("post_home_score", "max"),
        final_away=("post_away_score", "max"),
    ).reset_index()
    totals["total_runs"] = totals["final_home"].astype(float) + totals["final_away"].astype(float)

    called = raw[raw["type"].isin(["S", "B"])].copy()
    derived = derive_out_of_zone(called)
    ooz = derived[derived["out_of_zone"]].copy()
    ooz["is_strike"] = (ooz["type"] == "S").astype(int)
    per_game_ooz = ooz.groupby("game_pk").agg(
        n_ooz=("is_strike", "size"), ooz_strikes=("is_strike", "sum"),
    ).reset_index()

    prob = (probables.copy() if isinstance(probables, pd.DataFrame)
            else pd.read_parquet(str(_PROBABLES)))
    prob2 = prob[["game_pk", "game_date", "home_team", "hp_umpire_id"]].drop_duplicates(
        subset=["game_pk"]
    )

    merged = (totals.merge(per_game_ooz, on="game_pk", how="inner")
                     .merge(prob2, on="game_pk", how="inner"))
    merged = merged[merged["hp_umpire_id"].notna()].copy()
    merged["hp_umpire_id"] = merged["hp_umpire_id"].astype(int)
    merged["date"] = pd.to_datetime(merged["game_date"])
    merged = merged.sort_values(["date", "game_pk"], kind="mergesort").reset_index(drop=True)
    return merged[["game_pk", "date", "home_team", "hp_umpire_id",
                   "total_runs", "n_ooz", "ooz_strikes"]]


def shuffle_umpire_assignment(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """PLANTED-NULL harness: shuffle hp_umpire_id ACROSS games (breaking the
    true umpire<->game link) while preserving each game's real total_runs,
    date, home_team, and the umpire's own n_ooz/ooz_strikes pairing is
    reassigned together with the id so a shuffled umpire's tendency stream
    stays internally consistent -- only the umpire<->OUTCOME link is severed.
    """
    rng = np.random.default_rng(seed)
    out = df.copy()
    perm = rng.permutation(len(out))
    out["hp_umpire_id"] = out["hp_umpire_id"].values[perm]
    out["n_ooz"] = out["n_ooz"].values[perm]
    out["ooz_strikes"] = out["ooz_strikes"].values[perm]
    return out


def _walk_forward_scores(df: pd.DataFrame) -> Dict[str, np.ndarray]:
    """Compute baseline_pred and candidate_pred arrays, strictly expanding /
    snapshot-before-update, for every row (NaN before BURN_IN)."""
    n = len(df)
    total_runs = df["total_runs"].values.astype(float)
    home_team = df["home_team"].astype(str).values
    ump_id = df["hp_umpire_id"].values
    n_ooz = df["n_ooz"].values.astype(float)
    ooz_strikes = df["ooz_strikes"].values.astype(float)

    baseline_pred = np.full(n, np.nan)
    candidate_pred = np.full(n, np.nan)

    league_sum, league_n = 0.0, 0
    park_hist: Dict[str, List[float]] = {}
    ump_hist: Dict[int, List[float]] = {}  # umpire_id -> [n_ooz_sum, strikes_sum, n_games]
    league_ooz_sum, league_ooz_strikes, league_ooz_games = 0.0, 0.0, 0

    for i in range(n):
        # --- league expanding mean total runs (snapshot before update) ---
        league_mean = league_sum / league_n if league_n > 0 else np.nan

        # --- park adjustment: home_team's prior mean total minus league prior mean ---
        rec = park_hist.get(home_team[i], [0.0, 0])
        park_n = rec[1]
        park_adj = 0.0
        if park_n >= PARK_MIN_GAMES and league_n >= PARK_MIN_GAMES:
            park_mean = rec[0] / park_n
            park_adj = park_mean - league_mean

        base_i = league_mean + park_adj if league_n > 0 else np.nan
        baseline_pred[i] = base_i

        # --- umpire tendency term (expanding, as-of, demeaned vs league) ---
        u_rec = ump_hist.get(int(ump_id[i]), [0.0, 0.0, 0])
        u_games = u_rec[2]
        ump_term = 0.0
        if u_games >= MIN_UMPIRE_PRIOR and league_ooz_games >= MIN_UMPIRE_PRIOR and u_rec[0] > 0:
            u_rate = u_rec[1] / u_rec[0]
            league_rate = (league_ooz_strikes / league_ooz_sum) if league_ooz_sum > 0 else np.nan
            if not np.isnan(league_rate):
                ump_term = u_rate - league_rate

        # Higher out-of-zone strike rate -> more called/swung strikes -> weakly
        # fewer runs. UMPIRE_TERM_SCALE is a fixed, un-fitted literal constant
        # (see definition below), never tuned to an observed effect size.
        candidate_pred[i] = base_i - ump_term * UMPIRE_TERM_SCALE if not np.isnan(base_i) else np.nan

        # --- update AFTER snapshot ---
        league_sum += total_runs[i]
        league_n += 1
        if home_team[i] not in park_hist:
            park_hist[home_team[i]] = [0.0, 0]
        park_hist[home_team[i]][0] += total_runs[i]
        park_hist[home_team[i]][1] += 1
        uid = int(ump_id[i])
        if uid not in ump_hist:
            ump_hist[uid] = [0.0, 0.0, 0]
        ump_hist[uid][0] += n_ooz[i]
        ump_hist[uid][1] += ooz_strikes[i]
        ump_hist[uid][2] += 1
        league_ooz_sum += n_ooz[i]
        league_ooz_strikes += ooz_strikes[i]
        league_ooz_games += 1

    return {"baseline_pred": baseline_pred, "candidate_pred": candidate_pred, "total_runs": total_runs}


# Run-equivalent scale for a +-1 rate gap (never actually observed -- real
# per-umpire demeaned gaps are ~+-0.05). Set to this corpus's total-runs/game
# std (~4.5); fixed and un-fitted, not tuned to any observed effect size.
UMPIRE_TERM_SCALE: float = 4.5


def _fold_scores(y_true: np.ndarray, base_pred: np.ndarray, cand_pred: np.ndarray) -> Dict[str, float]:
    base_rmse = float(np.sqrt(np.mean((y_true - base_pred) ** 2)))
    cand_rmse = float(np.sqrt(np.mean((y_true - cand_pred) ** 2)))
    return {
        "n": int(len(y_true)),
        "baseline_rmse": base_rmse,
        "baseline_mae": float(np.mean(np.abs(y_true - base_pred))),
        "candidate_rmse": cand_rmse,
        "candidate_mae": float(np.mean(np.abs(y_true - cand_pred))),
        "rmse_delta": cand_rmse - base_rmse,  # negative = candidate better
    }


def _score_corpus(df: pd.DataFrame) -> Dict[str, object]:
    n_total = len(df)
    if n_total <= BURN_IN:
        return {"n": n_total, "n_scorable": 0, "folds": [], "beats_all_folds": False,
                "overall_rmse_delta": None}

    arrs = _walk_forward_scores(df)
    scorable_idx = np.arange(BURN_IN, n_total)
    n_scorable = int(len(scorable_idx))
    if n_scorable < MIN_PER_FOLD * N_FOLDS:
        return {"n": n_total, "n_scorable": n_scorable, "folds": [], "beats_all_folds": False,
                "overall_rmse_delta": None,
                "honest_note": "fewer than %d scorable rows -- cannot form %d folds of %d"
                                % (MIN_PER_FOLD * N_FOLDS, N_FOLDS, MIN_PER_FOLD)}

    y_true = arrs["total_runs"][scorable_idx]
    base_pred = arrs["baseline_pred"][scorable_idx]
    cand_pred = arrs["candidate_pred"][scorable_idx]

    fold_bounds = np.array_split(np.arange(n_scorable), N_FOLDS)
    folds = [_fold_scores(y_true[b], base_pred[b], cand_pred[b]) for b in fold_bounds]
    overall = _fold_scores(y_true, base_pred, cand_pred)
    beats_all_folds = all(f["rmse_delta"] < 0 for f in folds)

    return {
        "n": int(n_total), "n_scorable": n_scorable,
        "folds": folds, "overall": overall,
        "beats_all_folds": beats_all_folds,
        "overall_rmse_delta": overall["rmse_delta"],
    }


def run_gate(corpus: Optional[pd.DataFrame] = None) -> Dict[str, object]:
    """Pre-registered gate: real-assignment candidate vs baseline, gated
    against a mandatory shuffled-umpire planted null. See module docstring.
    """
    df = corpus if corpus is not None else build_umpire_totals_corpus()
    real_result = _score_corpus(df)

    null_df = shuffle_umpire_assignment(df, seed=0)
    null_result = _score_corpus(null_df)

    real_delta = real_result.get("overall_rmse_delta")
    null_delta = null_result.get("overall_rmse_delta")

    if real_delta is None or null_delta is None:
        verdict = "INCONCLUSIVE"
        reason = "insufficient scorable rows for real or null corpus"
    elif not real_result["beats_all_folds"]:
        verdict = "REJECT"
        reason = "real-assignment candidate does not beat baseline RMSE in all %d folds" % N_FOLDS
    elif null_result["beats_all_folds"] and null_delta <= real_delta:
        verdict = "REJECT"
        reason = ("planted null (shuffled umpire assignment) shows an equal-or-larger "
                   "RMSE improvement than the real assignment -- added-flexibility artifact, "
                   "not umpire signal")
    elif real_delta >= 0:
        verdict = "REJECT"
        reason = "real-assignment candidate does not beat baseline RMSE overall"
    else:
        verdict = "SHIP_REVIEW"
        reason = ("real-assignment candidate beats baseline RMSE in all %d folds and beats "
                   "the planted-null candidate's improvement" % N_FOLDS)

    return {
        "hypothesis": ("home-plate umpire out-of-zone strike-rate tendency (expanding, "
                       "as-of within this gate) predicts game total runs beyond an internal "
                       "league+park baseline"),
        "pre_registered_expectation": "REJECT",
        "n_umpires": int(df["hp_umpire_id"].nunique()),
        "real_result": real_result,
        "null_result": null_result,
        "verdict": verdict,
        "verdict_reason": reason,
        "scope_note": ("internal-baseline MATCH-not-beat only; NO market totals close used "
                        "anywhere in this module; vs-close comparison is OUT OF SCOPE "
                        "(no close corpus wired here); no $ edge claimed"),
    }


def _write_rows_export(df: pd.DataFrame, arrs: Dict[str, np.ndarray]) -> None:
    """Per-row reprocess-schema export: game_pk, date, hp_umpire_id, total_runs,
    baseline_pred, candidate_pred (real assignment only)."""
    out = df[["game_pk", "date", "hp_umpire_id", "total_runs"]].copy()
    out["baseline_pred"] = arrs["baseline_pred"]
    out["candidate_pred"] = arrs["candidate_pred"]
    _ROWS_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _ROWS_OUT_PATH.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False)
    os.replace(str(tmp), str(_ROWS_OUT_PATH))


def main() -> None:
    df = build_umpire_totals_corpus()
    result = run_gate(df)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _OUT_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(result, f, indent=2, default=str)
    os.replace(str(tmp), str(_OUT_PATH))
    _write_rows_export(df, _walk_forward_scores(df))
    print(json.dumps(result, indent=2, default=str))
    print("\nWrote verdict to %s" % _OUT_PATH)
    print("Wrote per-row export to %s" % _ROWS_OUT_PATH)


if __name__ == "__main__":
    main()
