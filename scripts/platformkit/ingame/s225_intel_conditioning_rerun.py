"""S225 leak-free NBA conditioning calibration screen."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.foundry.ingame_guards import assert_tick_asof
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size
from scripts.platformkit.ingame.s225_conditioning_prior import (
    alignment_rows, load_raw_game_rows, rebuild_prior_conditions, source_paths,
)

ROOT = Path(__file__).resolve().parents[3]
BRIDGE = ROOT / "data/domains/basketball_nba/espn_nba_game_bridge.parquet"
TICKS = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
ROWS = ROOT / "data/domains/basketball_nba"
EVIDENCE = ROOT / "docs/evidence/harness"
STEM = "S225_ingame_intel_conditioning_rerun_2026-09-04"
PREREG = EVIDENCE / "S225_ATTEMPT2_PREREG_2026-09-04.json"
PREREG_SHA256 = "b457d7ac03bfe8745bd52334166d4d159d029f93fed786a85dc5c1a5dab9bb17"
TOLERANCE_SECONDS, EMBARGO_DAYS, N_GROUPS = 60.0, 1, 6
LAYERS = ("hot_night", "scheme_fit")


def _logit(values) -> np.ndarray:
    p = np.clip(np.asarray(values, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))


def _verify_prereg() -> None:
    payload = json.loads(PREREG.read_text(encoding="ascii"))
    seal = payload.pop("seal_sha256")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    assert seal == PREREG_SHA256 == hashlib.sha256(canonical).hexdigest(), "preregistration seal mismatch"


def _clock_alignment(raw: pd.DataFrame, clocks: dict) -> dict:
    nearest = []
    for item in alignment_rows(raw).itertuples(index=False):
        expected = float(item.seconds_remaining) - (4 - int(item.period)) * 720.0
        available = clocks.get((item.game, int(item.period)), [])
        nearest.append(min((abs(expected - clock) for clock in available), default=np.inf))
    return {"rows": len(nearest), "tolerance_seconds": TOLERANCE_SECONDS,
            "exact_rows": int(sum(value == 0.0 for value in nearest)),
            "within_tolerance_rows": int(sum(value <= TOLERANCE_SECONDS for value in nearest)),
            "max_nearest_seconds": float(max(nearest, default=0.0))}


def load_rows(layer: str) -> tuple[pd.DataFrame, dict]:
    """Load bridge/ticks and rebuild one layer's values from prior games only."""
    bridge = pd.read_parquet(BRIDGE)
    bridge = bridge[bridge["match_confidence"].eq("exact")].copy()
    bridge["game"] = bridge["event_id"].astype(str)
    bridge = bridge.set_index("game")
    ticks = pd.read_parquet(TICKS)
    ticks["game"] = ticks["game_id"].astype(str)
    ticks = ticks[ticks["traded"].eq(True) & ticks["game"].isin(bridge.index)].copy()
    ticks["market"] = ticks["market_prob"].astype(float)
    ticks["y"] = ticks["outcome_home_win"].astype(float)
    ticks["timestamp"] = pd.to_datetime(ticks["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    ticks["game_date"] = ticks["game"].map(bridge["date"]).astype(str)
    clocks = {(str(game), int(period)): sorted(part["game_clock_s"].astype(float))
              for (game, period), part in ticks.groupby(["game", "period"], sort=False)}
    raw = load_raw_game_rows(ROWS, layer, bridge)
    alignments = []
    for season, part in raw.groupby("season", sort=True):
        alignments.append({"season": str(season), **_clock_alignment(part[part["game"].isin(ticks["game"])], clocks)})
    conditions = rebuild_prior_conditions(raw, bridge, layer)
    ticks = ticks.merge(conditions, on=["game", "game_date"], how="left", validate="many_to_one")
    missing_condition = ticks[["condition", "null_condition"]].isna().any(axis=1)
    missing_games = int(ticks.loc[missing_condition, "game"].nunique())
    missing_ticks = int(missing_condition.sum())
    ticks[["condition", "null_condition"]] = ticks[["condition", "null_condition"]].fillna(0.0)
    assert ticks[["condition", "null_condition"]].notna().all().all(), "unnamed conditioning exclusion"
    ticks = ticks.sort_values(["game_date", "timestamp", "game"], kind="stable").reset_index(drop=True)
    hot_meta = None
    if layer == "hot_night":
        team_games = raw[raw["season"].eq("2024-25")].groupby(["game", "team"], sort=False, as_index=False).first()
        home = team_games[team_games["team"].eq(team_games["game"].map(bridge["home_nba"]))]
        matched = home[home["game"].isin(ticks["game"])]
        hot_meta = {"full_games": int(home["game"].nunique()), "checkpoint_matched_games": int(matched["game"].nunique()),
                    "missing_checkpoint_matches": int(home["game"].nunique() - matched["game"].nunique()),
                    "full_home_outcome_base_rate": float(home.groupby("game")["outcome"].first().mean()),
                    "matched_home_outcome_base_rate": float(matched.groupby("game")["outcome"].first().mean())}
    paths = source_paths(ROWS, layer)
    meta = {"bridge_exact_games": int(len(bridge)), "bridged_ticks": int(len(ticks)),
            "bridged_games": int(ticks["game"].nunique()), "alignment": alignments,
            "condition_missing_games": missing_games, "condition_missing_ticks": missing_ticks,
            "neutral_missing_condition_games": missing_games, "neutral_missing_condition_ticks": missing_ticks,
            "hot_non_tautology": hot_meta,
            "inputs": [{"path": str(path.relative_to(ROOT)).replace("\\", "/"), "bytes": path.stat().st_size} for path in paths]}
    return ticks, meta


def _states(rows: pd.DataFrame) -> list[dict]:
    states = []
    for game, part in rows.groupby("game", sort=False):
        part = part.sort_values("timestamp", kind="stable")
        feature_time = str(part["timestamp"].iloc[-1]).replace("Z", "+00:00")
        available = (pd.Timestamp(part["timestamp"].iloc[-1]) + timedelta(seconds=1)).isoformat()
        states.append({"game_id": str(game), "state_ts": available,
                       "home": "H" + str(game), "away": "A" + str(game), "outcome": int(part["y"].iloc[0]),
                       "features": {"market": part["market"].to_numpy(float),
                                    "condition": part["condition"].to_numpy(float),
                                    "null_condition": part["null_condition"].to_numpy(float)},
                       "feature_avail": {"market": feature_time, "condition": feature_time,
                                          "null_condition": feature_time}})
    return states


def _fit_model(train: list[pd.DataFrame], include_condition: bool):
    fitted = pd.concat(train, ignore_index=True) if train else pd.DataFrame()
    if fitted.empty or fitted["y"].nunique() < 2:
        return None
    x_train = [_logit(fitted["market"])]
    if include_condition:
        x_train.append(fitted["selected_condition"].to_numpy(float))
    model = LogisticRegression(C=1e6, max_iter=500, solver="lbfgs")
    model.fit(np.column_stack(x_train), fitted["y"].to_numpy(float))
    return model


def _model_prediction(model, market: np.ndarray, condition: np.ndarray | None = None) -> np.ndarray:
    if model is None:
        return market.copy()
    columns = [_logit(market)]
    if condition is not None:
        columns.append(condition)
    return model.predict_proba(np.column_stack(columns))[:, 1]


def _predict(rows: pd.DataFrame, planted_null: bool) -> tuple[pd.DataFrame, list[dict]]:
    """Score once via shared CPCV while independently enforcing strict-prior fitting."""
    grouped = {str(game): part.copy() for game, part in rows.groupby("game", sort=False)}
    dates = {game: str(part["game_date"].iloc[0]) for game, part in grouped.items()}
    stash: dict[str, pd.DataFrame] = {}
    model_cache = {}

    def predictor(train_states: list[dict], test: dict, _select_inside: bool) -> float:
        game, test_date = str(test["game_id"]), dates[str(test["game_id"])]
        shared_ids = {str(item["game_id"]) for item in train_states}
        cutoff = min(dates[item] for item in grouped if item not in shared_ids)
        prior_ids = [str(item["game_id"]) for item in train_states if dates[str(item["game_id"])] < cutoff]
        assert all(dates[item] < test_date for item in prior_ids), "scored game or later game entered fit"
        assert game not in prior_ids, "scored game entered fit"
        cache_key = tuple(sorted(prior_ids))
        if cache_key not in model_cache:
            train = []
            for item in prior_ids:
                part = grouped[item].copy()
                part["selected_condition"] = part["null_condition"] if planted_null else part["condition"]
                train.append(part)
            model_cache[cache_key] = (_fit_model(train, False), _fit_model(train, True))
        market = np.asarray(test["features"]["market"], dtype=float)
        selected = np.asarray(test["features"]["null_condition" if planted_null else "condition"], dtype=float)
        incumbent_model, arm_model = model_cache[cache_key]
        incumbent, arm = _model_prediction(incumbent_model, market), _model_prediction(arm_model, market, selected)
        test_rows = grouped[game][["game", "game_date", "timestamp", "y", "market"]].copy()
        test_rows["prediction_incumbent"] = incumbent; test_rows["prediction_arm"] = arm
        test_rows["prediction_market"] = market; test_rows["n_train_prior"] = len(prior_ids)
        test_rows["train_last_game_date"] = max((dates[item] for item in prior_ids), default=None)
        assert game not in stash, "shared evaluator scored a game more than once"
        stash[game] = test_rows
        return float(arm[len(arm) // 2])

    records = cpcv_evaluate(_states(rows), predictor, n_groups=N_GROUPS, n_test_groups=1,
                            embargo_days=EMBARGO_DAYS)
    record_frame = pd.DataFrame(records)
    assert len(record_frame) == rows["game"].nunique() and record_frame["game_id"].is_unique, "non-OOF path"
    prediction = pd.concat([stash[game] for game in sorted(stash)], ignore_index=True)
    prediction = prediction.merge(record_frame[["game_id", "split_id", "n_train"]], left_on="game", right_on="game_id",
                                  how="left", validate="many_to_one").drop(columns="game_id")
    prediction = prediction.rename(columns={"n_train": "n_train_shared"})
    assert len(prediction) == len(rows), "tick loss"
    folds = [{"fold": int(split), "split": int(split), "test_games": int(part["game"].nunique()),
              "fallback_market_ticks": int(len(part) if part["n_train_prior"].max() == 0 else 0),
              "train_games": int(part["n_train_prior"].iloc[0]),
              "shared_train_states": int(part["n_train_shared"].iloc[0]),
              "prior_train_games_min": int(part["n_train_prior"].min()),
              "prior_train_games_max": int(part["n_train_prior"].max())}
             for split, part in prediction.groupby("split_id", sort=True)]
    return prediction, folds


def _summary(prediction: pd.DataFrame, arm: str, folds: list[dict]) -> tuple[dict, pd.DataFrame]:
    output = prediction.copy(); y = output["y"].to_numpy(float)
    for name in ("arm", "incumbent", "market"):
        output["loss_" + name] = (output["prediction_" + name].to_numpy(float) - y) ** 2
    result = {"arm": arm, "n_ticks": len(output), "n_games": int(output["game"].nunique()),
              "brier_arm": float(output["loss_arm"].mean()), "brier_incumbent": float(output["loss_incumbent"].mean()),
              "brier_market": float(output["loss_market"].mean()), "ece_arm": float(ece(output["prediction_arm"], y)),
              "ece_incumbent": float(ece(output["prediction_incumbent"], y)), "ece_market": float(ece(output["prediction_market"], y)),
              "folds": folds}
    for reference in ("incumbent", "market"):
        differential = output["loss_" + reference] - output["loss_arm"]
        dm = diebold_mariano(differential.tolist(), output["game"].tolist())
        result["improvement_vs_" + reference] = float(differential.mean())
        result["dm_ci95_vs_" + reference] = [float(dm.ci95[0]), float(dm.ci95[1])]
    result["n_eff"] = float(effective_sample_size(output.assign(loss_differential=output["loss_incumbent"] - output["loss_arm"]))["n_eff"])
    output["arm"] = arm; output["outcome"] = output.pop("y")
    output["loss_differential_incumbent"] = output["loss_incumbent"] - output["loss_arm"]
    output["loss_differential_market"] = output["loss_market"] - output["loss_arm"]
    output["preregistration_path"] = str(PREREG.relative_to(ROOT)).replace("\\", "/"); output["prereg_sha256"] = PREREG_SHA256
    return result, output


def _per_game_rows(output: pd.DataFrame, arm: str) -> list[dict]:
    return [{"arm": arm, "game": str(game), "game_date": str(part["game_date"].iloc[0]),
             "n_ticks": int(len(part)), "loss_arm_sum": float(part["loss_arm"].sum()),
             "loss_incumbent_sum": float(part["loss_incumbent"].sum()),
             "loss_market_sum": float(part["loss_market"].sum())}
            for game, part in output.groupby("game", sort=True)]


def run(output_dir: Path = EVIDENCE) -> dict:
    """Run all sealed S225 arms and stream independently recomputable state rows."""
    _verify_prereg(); output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / (STEM + "_per_game_differentials.csv")
    state_path = output_dir / (STEM + "_state_differentials.csv")
    summaries, per_game, wrote_header = [], [], False
    with state_path.open("w", newline="", encoding="ascii") as handle:
        for layer in LAYERS:
            rows, meta = load_rows(layer)
            probes = assert_tick_asof(rows[["game", "timestamp", "market", "condition", "null_condition"]],
                                      lambda part: part[["market", "condition", "null_condition"]], probes=8)
            layer_result = {"layer": layer, "meta": meta, "tick_asof_probes": probes,
                            "execution_order": [layer + "_planted_null", layer]}
            for name, planted in ((layer + "_planted_null", True), (layer, False)):
                prediction, folds = _predict(rows, planted)
                summary, export = _summary(prediction, name, folds)
                export.to_csv(handle, index=False, header=not wrote_header, quoting=csv.QUOTE_MINIMAL)
                per_game.extend(_per_game_rows(export, name))
                wrote_header = True; layer_result["planted_null" if planted else "real"] = summary
            summaries.append(layer_result)
    with csv_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_game[0]))
        writer.writeheader(); writer.writerows(per_game)
    summary = {"mode": "SCREEN", "bar_unchanged": 0.004, "embargo_days": EMBARGO_DAYS, "n_groups": N_GROUPS,
               "preregistration_path": str(PREREG.relative_to(ROOT)).replace("\\", "/"), "prereg_sha256": PREREG_SHA256,
               "layers": summaries, "per_game_differentials": str(csv_path.relative_to(ROOT)).replace("\\", "/"),
               "state_differentials": str(state_path.relative_to(ROOT)).replace("\\", "/")}
    (output_dir / (STEM + "_summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="S225 NBA conditioning calibration screen")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE); args = parser.parse_args()
    summary = run(args.output_dir)
    for item in summary["layers"]:
        print("S225 %s null_then_real ticks=%d games=%d embargo_days=%d" %
              (item["layer"], item["real"]["n_ticks"], item["real"]["n_games"], EMBARGO_DAYS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
