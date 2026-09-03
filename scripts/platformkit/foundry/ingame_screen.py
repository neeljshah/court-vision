"""S82: the signal factory's IN-GAME screen tier -- the one the pregame leak contract refuses.

`screen_predictor.check_feature_name` refuses every member of all 11 `live_tick` families
("leaky: <col> is a same-game column"), because the PREGAME contract's as-of unit is the GAME.
This module screens the same state columns under the tier's own contract instead.

TICK-TIME AS-OF CONTRACT (this tier's leak rule; NOT the pregame game-as-of rule)
-------------------------------------------------------------------------------
A hypothesis is ONE state feature x(g, t) whose value at tick time t of game g is a function
of events of g with timestamp <= t ONLY, plus pregame as-of tables. Reading any event later
than the tick's own is a leak, and so is reading the tick's OWN label. Both are ENFORCED in
`ingame_guards`: `assert_tick_asof` rebuilds from the causal prefix src[:k+1] and requires row
k to equal row k of the full build (truncation invariance), and then `assert_label_blind`
(S124) rebuilds with the label permuted and requires every feature column to be unchanged --
truncation invariance alone cannot see a SAME-TICK label reader. Either raises TickTimeLeak.
A THIRD gate stands in `run` itself (S124's other half): a served `features=` mapping must be
a SUBSET of the frozen grammar `FEATURES` unless `allow_adhoc=True`, and each ad-hoc column is
then put through `assert_column_blind` (a builder cannot be permuted once its column is
materialised). All are re-exported here, so every existing import site is unchanged (A5/B6).

The hypothesis is ONE extra logistic term on the incumbent e4 blend,
p = sigmoid(a + b*logit(p_e4_gd) + c*z(x)), fitted walk-forward over GAME-FIRST-DATE folds
(S36), purged by game settlement with a 1-day embargo, and scored tick-weighted against the
in-play market line at tick time with a game-clustered DM interval. The bar is applied to the
gain over the SAME fit without the c*z(x) term, so the arms differ only by the feature.

A SCREEN IS A NON-FINDING. No ledger row, no prereg seal, no charge: this module imports
nothing from backtest_runner and consumes no K. Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/foundry/test_ingame_screen.py -q
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.foundry.ingame_guards import (  # re-exported (A5/B6)
    AdHocFeature, TickTimeLeak, assert_column_blind, assert_label_blind, assert_tick_asof,
    gate_features, utc_stamps)
from scripts.platformkit.foundry.screen_predictor import RIDGE, _logistic, _logit
from scripts.platformkit.foundry.tick_partition import screen_side
from scripts.platformkit.foundry.tiers import partition_corpus
from scripts.platformkit.mlb_state_features import game_state_features

ROOT = Path(__file__).resolve().parents[3]
BAR = 0.004                      # the S58 in-game bar; never moved (Q3)
EMBARGO_DAYS, MIN_TRAIN, MIN_UNIQUE = 1, 1000, 3
SEED = 0                         # partition seed, frozen here
_BASE_OUT = ["base_out_%d" % i for i in range(24)]

# grammar member (frozen FWER families) -> the tick-corpus column that supplies it.
# A member with no entry is NOT SUPPLIED by this corpus and is reported, never silently dropped.
FEATURES: Dict[str, str] = {
    "state_diff": "score_diff", "frac_elapsed": "inning_progress",
    "leverage_state": "leverage_proxy", "base_run_value": "run_expectancy",
    "count_balls": "balls", "count_strikes": "strikes", "outs": "outs",
    "runners": "base_state", "base_out_known": "base_out_state",
    "sp_pitch_count_prior": "pitch_count", "times_through_order": "times_through_order",
    "pitch_tempo": "pitch_tempo_seconds", "score_change_recency": "score_change_recency",
    "asof_idx": "tick_index_in_game",
}
NOT_SUPPLIED = ("pitch_velocity", "pitch_loc_x", "pitch_loc_y", "velo_decline_vs_early",
                "atbat_pitch_number", "bullpen_usage_asof", "p0", "outcome")


def causal_source(ticks: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """The loader's own causal ordering: ticks sorted by (timestamp, game), stable."""
    frame = pd.DataFrame([{"game": t["game"], "timestamp": t["timestamp"],
                           "state_summary": (t.get("state_summary")
                                             or (t.get("raw") or {}).get("state_summary")),
                           "_row_id": int(t["_row_id"])} for t in ticks])
    return frame.sort_values(["timestamp", "game"], kind="stable").reset_index(drop=True)


def build_features(src: pd.DataFrame) -> pd.DataFrame:
    """State features at each tick from events of that game with timestamp <= the tick's own."""
    out = game_state_features(src)
    ordinal = pd.Series(np.nan, index=out.index)
    for position, column in enumerate(_BASE_OUT):
        ordinal = ordinal.where(out[column] != 1.0, float(position))
    out["base_out_state"] = ordinal
    out["outs"] = ordinal % 3.0
    out["base_state"] = ordinal // 3.0
    out["tick_index_in_game"] = out.groupby("game").cumcount().astype(float)
    return out[["game", "timestamp", "_row_id"] + sorted(set(FEATURES.values()))]


def screen_rows(ticks: Sequence[Mapping[str, Any]], e4: Sequence[Optional[float]],
                table: pd.DataFrame, first_dates: Mapping[str, str]) -> pd.DataFrame:
    """One row per scored tick: incumbent, market, label, game-first date, every feature."""
    finite = [i for i, t in enumerate(ticks)
              if e4[i] is not None and math.isfinite(float(e4[i]))
              and t.get("market_prob") is not None and math.isfinite(float(t["market_prob"]))]
    base = pd.DataFrame({"row_id": finite,
                         "game": [str(ticks[i]["game"]) for i in finite],
                         "ts": [str(ticks[i]["timestamp"]) for i in finite],
                         "y": [float(ticks[i]["outcome"]) for i in finite],
                         "p_e4": [float(e4[i]) for i in finite],
                         "market": [float(ticks[i]["market_prob"]) for i in finite]})
    base["game_date"] = [first_dates[g] for g in base["game"]]
    joined = base.merge(table.drop(columns=["game", "timestamp"]), left_on="row_id",
                        right_on="_row_id", how="left", validate="one_to_one")
    assert len(joined) == len(base), "the feature join changed the tick denominator"
    return joined.sort_values(["ts", "game"], kind="stable").reset_index(drop=True)


def partition(rows: pd.DataFrame, seed: int = SEED):
    """SF-1 sides over the SCORED games. Ticks are not in the foundry hash partition, so this
    is the spec's game-first-date ISO-week rule (tiers.partition_corpus, basis iso_week)."""
    states = [{"game_id": game, "state_ts": "%sT12:00:00" % date}
              for game, date in sorted(rows.groupby("game")["game_date"].min().items())]
    return partition_corpus(states, seed=seed)


def _fit(train: pd.DataFrame, column: str) -> Optional[tuple]:
    """Two fits on the SAME rows: the null [1, logit(p_e4)] and the candidate [null, z(x)].

    The null exists because [1, logit(p_e4)] alone re-calibrates the incumbent, and that gain
    is not the feature's. Base and candidate must differ ONLY by the candidate term, so the
    feature's marginal contribution is scored against the null, never against raw e4."""
    x = train[column].to_numpy(dtype=float)
    keep = np.isfinite(x)
    if int(keep.sum()) < MIN_TRAIN or len(np.unique(x[keep])) < MIN_UNIQUE:
        return None
    sub, x = train[keep], x[keep]
    if sub["y"].nunique() < 2:
        return None
    mu, sd = float(x.mean()), float(x.std()) or 1.0
    anchor = np.column_stack([np.ones(len(sub)), [_logit(p) for p in sub["p_e4"]]])
    y = sub["y"].to_numpy(dtype=float)
    null = _logistic(anchor, y, ridge=RIDGE)
    full = _logistic(np.column_stack([anchor, (x - mu) / sd]), y, ridge=RIDGE)
    return full, null, mu, sd


def walk_forward_feature(rows: pd.DataFrame, column: str,
                         embargo_days: int = EMBARGO_DAYS) -> tuple:
    """Candidate probability per row: fit on strictly earlier games, predict the fold's ticks.

    Folds are game-first-date (S36) and therefore game-disjoint. The PURGE is on the game's
    SETTLEMENT, not its first date: this store quotes a Kalshi game market up to ~2 days before
    first pitch, so a game whose first date is earlier can still be ticking during the fold. A
    train game must have produced its LAST tick at least `embargo_days` before the fold's first
    tick. That is stricter than the incumbent's own game-first-date fold rule, so the candidate
    always trains on less than the incumbent did -- conservative, never the other way.

    S125: every stamp is parsed to tz-aware UTC before it is compared. The old code compared
    the stamp STRINGS to a strftime'd cut, and ' ' sorts before 'T', so a space-separated
    spelling admitted a game settling 2 h before the fold and both asserts passed with it."""
    out = pd.Series(np.nan, index=rows.index)
    null_out = pd.Series(np.nan, index=rows.index)
    folds: List[dict] = []
    stamps = utc_stamps(rows["ts"])   # S125: parse ONCE; `<` on stamp strings is not a time order
    last_ts = stamps.groupby(rows["game"].to_numpy()).max()
    dates = sorted(rows["game_date"].unique())
    for date in dates[1:]:
        test = rows[rows["game_date"] == date]
        if test.empty:
            continue
        first = stamps[test.index].min()
        edge = first - pd.Timedelta(days=embargo_days)
        cut = edge.strftime("%Y-%m-%dT%H:%M:%SZ")     # the archived spelling, unchanged
        train = rows[rows["game"].isin(last_ts.index[last_ts < edge])]
        if train.empty:
            folds.append({"date": date, "status": "NO_TRAIN", "n_train": 0, "cut": cut})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint"
        assert stamps[train.index].max() < first, "purge violated: train outlives the fold"
        fit = _fit(train, column)
        if fit is None:
            folds.append({"date": date, "status": "UNFITTABLE", "n_train": int(len(train))})
            continue
        coef, null, mu, sd = fit
        x = test[column].to_numpy(dtype=float)
        anchor = np.array([_logit(p) for p in test["p_e4"]])
        p_e4 = test["p_e4"].to_numpy(dtype=float)
        eta = coef[0] + coef[1] * anchor + coef[2] * (x - mu) / sd
        # missing != bad: a tick with no feature value falls back to the null on both arms.
        p_null = np.clip(1.0 / (1.0 + np.exp(-(null[0] + null[1] * anchor))), 0.001, 0.999)
        prob = np.where(np.isfinite(x), np.clip(1.0 / (1.0 + np.exp(-eta)), 0.001, 0.999), p_null)
        out.loc[test.index], null_out.loc[test.index] = prob, p_null
        folds.append({"date": date, "status": "OK", "n_train": int(len(train)),
                      "n_test": int(len(test)), "cut": cut, "n_train_games": int(train["game"].nunique()),
                      "coef": [float(c) for c in coef], "coef_null": [float(c) for c in null],
                      "mu": mu, "sd": sd, "feature_coverage_test": float(np.isfinite(x).mean()),
                      "brier_e4_fold": float(((p_e4 - test["y"]) ** 2).mean())})
    return out, null_out, folds


def _dm(delta: np.ndarray, games: Sequence[str]) -> tuple:
    if not len(delta) or float(np.abs(delta).max()) == 0.0:
        return 0.0, 1.0, [0.0, 0.0]
    res = diebold_mariano(delta.tolist(), games)
    return float(res.dm_stat), float(res.p_value), [float(res.ci95[0]), float(res.ci95[1])]


def score_feature(rows: pd.DataFrame, candidate: pd.Series, null: pd.Series, column: str) -> dict:
    """Tick-weighted paired comparison on the rows the candidate actually scored.

    The BAR is applied to `improvement_vs_null`: the null carries the same walk-forward
    re-calibration of the incumbent, so the two arms differ ONLY by the feature term."""
    keep = candidate.notna()
    sub = rows[keep]
    p_c, p_n = candidate[keep].to_numpy(dtype=float), null[keep].to_numpy(dtype=float)
    y = sub["y"].to_numpy(dtype=float)
    p_i, mkt = sub["p_e4"].to_numpy(dtype=float), sub["market"].to_numpy(dtype=float)
    loss_c, loss_n = (p_c - y) ** 2, (p_n - y) ** 2
    loss_i, loss_m = (p_i - y) ** 2, (mkt - y) ** 2
    games = [str(g) for g in sub["game"]]
    stat, p_raw, ci = _dm(loss_n - loss_c, games)          # > 0 means the feature helped
    stat_e4, p_e4, ci_e4 = _dm(loss_i - loss_c, games)
    phase = sub["inning_progress"] if "inning_progress" in sub else pd.Series(dtype=float)
    coverage = {} if phase.empty else {
        str(int(b)): int(v) for b, v
        in phase.dropna().astype(int).value_counts().sort_index().items()}
    improvement = float(loss_n.mean() - loss_c.mean())
    return {"feature": column, "n_ticks": int(len(sub)), "n_games": len(set(games)),
            "brier_e4": float(loss_i.mean()), "brier_null_recal": float(loss_n.mean()),
            "brier_candidate": float(loss_c.mean()), "brier_market": float(loss_m.mean()),
            "improvement_vs_null": improvement, "bar": BAR, "dm_stat": stat, "dm_p_raw": p_raw,
            "improvement_vs_e4": float(loss_i.mean() - loss_c.mean()), "dm_ci95": ci,
            "improvement_vs_market": float(loss_m.mean() - loss_c.mean()),
            "dm_vs_e4": {"stat": stat_e4, "p_raw": p_e4, "ci95": ci_e4},
            "clears_bar": bool(improvement >= BAR and ci[0] > 0.0), "_index": sub.index,
            "feature_coverage": float(rows[column].notna().mean()), "phase_coverage_inning": coverage}


def _summaries(ticks, rows: pd.DataFrame) -> List[Any]:
    """The state_summary of each scored row, so the S121 tick partition can purge by real game."""
    return [(ticks[i].get("state_summary") or (ticks[i].get("raw") or {}).get("state_summary"))
            for i in rows["row_id"]]


def run(ticks, e4, table, first_dates, *, out_json: Optional[Path] = None,
        out_csv: Optional[Path] = None, features: Optional[Mapping[str, str]] = None,
        mode: Optional[str] = None, allow_adhoc: bool = False) -> dict:
    """Screen every supplied in-game state feature on the SCREEN side; archive the differential.

    `mode` (or FOUNDRY_INGAME_PARTITION) selects the S121 partition grain; the default stays
    the frozen ticker-week rule so this artifact reproduces S82 byte-identically.

    S124's second gate: a served `features=` mapping must be a SUBSET of the frozen grammar
    `FEATURES`; an ad-hoc member is refused unless `allow_adhoc=True`, and is then put through
    `assert_column_blind`. On the frozen default `gate_features` returns [] -- a pure no-op."""
    features = dict(FEATURES if features is None else features)
    adhoc = gate_features(features, FEATURES, allow_adhoc)              # S124
    rows = screen_rows(ticks, e4, table, first_dates)
    for member in adhoc:
        if features[member] in rows.columns:
            assert_column_blind(rows[features[member]], rows["y"], features[member])
    part = partition(rows)
    side, side_meta = screen_side(rows, part, mode=mode, state_summary=_summaries(ticks, rows))
    results: List[dict] = []
    series: List[pd.DataFrame] = []
    for member, column in sorted(features.items()):
        if column not in side.columns:
            results.append({"feature": column, "grammar_member": member, "status": "NOT_SUPPLIED"})
            continue
        candidate, null, folds = walk_forward_feature(side, column)
        if not candidate.notna().any():
            results.append({"feature": column, "grammar_member": member, "status": "UNSCORED",
                            "folds": folds})
            continue
        record = score_feature(side, candidate, null, column)
        index = record.pop("_index")
        scored = side.loc[index]
        series.append(pd.DataFrame({
            "feature": column, "tick_index": scored["row_id"].to_numpy(),
            "game": scored["game"].to_numpy(), "timestamp": scored["ts"].to_numpy(),
            "y": scored["y"].to_numpy(), "p_e4": scored["p_e4"].to_numpy(),
            "p_null": null[index].to_numpy(), "p_candidate": candidate[index].to_numpy(),
            "market": scored["market"].to_numpy(), "x": scored[column].to_numpy()}))
        record.update({"grammar_member": member, "status": "SCREENED", "folds": folds})
        results.append(record)
    results.sort(key=lambda r: -(r["improvement_vs_null"] if "improvement_vs_null" in r else -9.9))
    report = {"tier": "in-game screen (S82)", "verdict": "SCREEN (a non-finding)", "sport": "mlb",
              "bar": BAR, "seed": SEED, "embargo_days": EMBARGO_DAYS, "min_train": MIN_TRAIN,
              "partition": {"basis": part.basis, "screen_sha256": part.screen_sha256,
                            "verdict_sha256": part.verdict_sha256, "tick_grain": side_meta,
                            "n_screen_games": len(part.screen_ids), "n_verdict_games": len(part.verdict_ids)},
              "corpus": {"n_scored_ticks": int(len(rows)), "n_scored_games": int(rows["game"].nunique()),
                         "n_screen_ticks": int(len(side)), "n_screen_games": int(side["game"].nunique()),
                         "ts_min": str(rows["ts"].min()), "ts_max": str(rows["ts"].max())},
              "not_supplied": list(NOT_SUPPLIED), "results": results,
              "n_clearing_bar": sum(1 for r in results if r.get("clears_bar")),
              "per_tick_series": str(out_csv) if out_csv else None}
    if out_csv and series:
        pd.concat(series, ignore_index=True).to_csv(out_csv, index=False)
    if out_json:
        Path(out_json).write_text(json.dumps(report, indent=1, sort_keys=True, default=str), "ascii")
    return report
