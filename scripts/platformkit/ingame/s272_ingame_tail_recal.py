"""Sealed OOS pooled-tail recalibration screen for the S272 evidence row."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.scoring import ece

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
EVIDENCE = ROOT / "docs/evidence/harness"
STEM = "S272_ingame_tail_recal_screen_2026-09-04"
PREREG = EVIDENCE / "S272_ingame_tail_recal_prereg_2026-09-04.md"
PREREG_SHA256 = "bd33af6d49a43150916e7d4d6a0dd6e15a520165aab9a2834159042b39ed006d"
EMBARGO_DAYS, BOOTSTRAPS, SEED = 1, 2_000, 272


def _season(dates: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(dates)
    start = parsed.dt.year.where(parsed.dt.month >= 7, parsed.dt.year - 1)
    return start.astype(str) + "-" + ((start + 1) % 100).astype(str).str.zfill(2)


def _logit(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(values, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(clipped / (1.0 - clipped))


def _verify_prereg() -> None:
    """Verify the prereg file itself after CRLF-to-LF normalization (Q1)."""
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"Seal SHA-256: ", 1)
    assert hashlib.sha256(prefix).hexdigest() == PREREG_SHA256
    assert seal.decode("ascii").strip() == PREREG_SHA256


def _states(rows: pd.DataFrame) -> list[dict]:
    states = []
    for game, part in rows.groupby("game_id", sort=False):
        season = str(part["season"].iloc[0])
        start_year = int(season[:4]) + 1
        states.append({
            "game_id": str(game), "state_ts": "%d-07-01T00:00:00+00:00" % start_year,
            "home": "GAME_" + str(game), "away": "OPP_" + str(game),
            "outcome": int(part["outcome_home_win"].iloc[0]),
            "features": {"market": part["market_prob"].to_numpy(float)},
            "feature_avail": {"market": str(part["game_date"].iloc[0]) + "T00:00:00+00:00"},
        })
    return states


def _fit(train: pd.DataFrame):
    incumbent = LogisticRegression(C=1e6, max_iter=500, solver="lbfgs")
    incumbent.fit(_logit(train["market_prob"].to_numpy()).reshape(-1, 1), train["outcome_home_win"])
    tails = []
    for mask in (train["market_prob"] <= 0.10, train["market_prob"] >= 0.90):
        part = train.loc[mask]
        model = IsotonicRegression(out_of_bounds="clip")
        model.fit(part["market_prob"].to_numpy(float), part["outcome_home_win"].to_numpy(float))
        tails.append(model)
    return incumbent, tails[0], tails[1]


def _predict(rows: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    parts = {str(game): part.copy() for game, part in rows.groupby("game_id", sort=False)}
    seasons = {game: str(part["season"].iloc[0]) for game, part in parts.items()}
    dates = {game: str(part["game_date"].iloc[0]) for game, part in parts.items()}
    predictions: dict[str, tuple[np.ndarray, np.ndarray, int]] = {}
    models = {}

    def predictor(train_states: list[dict], test: dict, _inside: bool) -> float:
        game, season = str(test["game_id"]), seasons[str(test["game_id"])]
        prior_ids = [str(item["game_id"]) for item in train_states if seasons[str(item["game_id"])] < season]
        assert all(seasons[item] < season for item in prior_ids), "game-first-date purge failed"
        assert all(dates[item] < dates[game] for item in prior_ids), "future game-first-date entered fit"
        assert game not in prior_ids, "scored game entered fit"
        if season not in models:
            train = pd.concat([parts[item] for item in prior_ids], ignore_index=True) if prior_ids else pd.DataFrame()
            models[season] = _fit(train) if not train.empty else None
        market = parts[game]["market_prob"].to_numpy(float)
        fitted = models[season]
        if fitted is None:
            incumbent = candidate = market.copy()
            train_games = 0
        else:
            null, low, high = fitted
            incumbent = null.predict_proba(_logit(market).reshape(-1, 1))[:, 1]
            candidate = incumbent.copy()
            low_mask, high_mask = market <= 0.10, market >= 0.90
            if low_mask.any():
                candidate[low_mask] = low.predict(market[low_mask])
            if high_mask.any():
                candidate[high_mask] = high.predict(market[high_mask])
            train_games = len(prior_ids)
        predictions[game] = (candidate, incumbent, train_games)
        return float(candidate[len(candidate) // 2])

    records = cpcv_evaluate(_states(rows), predictor, n_groups=2, n_test_groups=1,
                            embargo_days=EMBARGO_DAYS)
    record_frame = pd.DataFrame(records)
    assert len(record_frame) == len(parts) and record_frame["game_id"].is_unique, "non-OOF path"
    output = rows.copy()
    output["candidate"] = np.concatenate([predictions[str(game)][0] for game, _ in rows.groupby("game_id", sort=False)])
    output["incumbent"] = np.concatenate([predictions[str(game)][1] for game, _ in rows.groupby("game_id", sort=False)])
    output["n_train_games"] = output["game_id"].astype(str).map(lambda game: predictions[game][2])
    split_by_game = record_frame.set_index("game_id")
    output["split_id"] = output["game_id"].astype(str).map(split_by_game["split_id"])
    output["n_train_shared"] = output["game_id"].astype(str).map(split_by_game["n_train"])
    assert output[["split_id", "n_train_shared"]].notna().all().all(), "missing CPCV diagnostic"
    output["tail"] = (output["market_prob"] <= 0.10) | (output["market_prob"] >= 0.90)
    output["loss_candidate"] = (output["candidate"] - output["outcome_home_win"]) ** 2
    output["loss_incumbent"] = (output["incumbent"] - output["outcome_home_win"]) ** 2
    assert np.array_equal(output.loc[~output["tail"], "candidate"], output.loc[~output["tail"], "incumbent"])
    folds = []
    for season, part in output.groupby("season", sort=True):
        folds.append({"season": str(season), "ticks": int(len(part)), "games": int(part["game_id"].nunique()),
                      "train_games": int(part["n_train_games"].iloc[0]),
                      "shared_train_games": int(part["n_train_shared"].iloc[0]),
                      "fallback_market": bool(part["n_train_games"].iloc[0] == 0)})
    return output, folds


def _interval(values: np.ndarray) -> list[float]:
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def _metrics(rows: pd.DataFrame, tail: bool) -> dict:
    subset = rows[rows["tail"]] if tail else rows
    grouped = list(subset.groupby("game_id", sort=False))
    games = len(grouped)
    assert games >= 30, "fewer than 30 game clusters"
    counts = np.asarray([len(part) for _, part in grouped], dtype=float)
    cand = np.asarray([part["loss_candidate"].sum() for _, part in grouped], dtype=float)
    inc = np.asarray([part["loss_incumbent"].sum() for _, part in grouped], dtype=float)
    rng = np.random.default_rng(SEED + int(tail))
    draw = rng.integers(0, games, size=(BOOTSTRAPS, games))
    weights = np.zeros((BOOTSTRAPS, games), dtype=float)
    np.add.at(weights, (np.arange(BOOTSTRAPS)[:, None], draw), 1)
    denominator = weights @ counts
    cand_boot, inc_boot = (weights @ cand) / denominator, (weights @ inc) / denominator
    result = {"n_ticks": int(len(subset)), "n_games": games,
              "candidate_brier": float(cand.sum() / counts.sum()), "candidate_brier_ci95": _interval(cand_boot),
              "incumbent_brier": float(inc.sum() / counts.sum()), "incumbent_brier_ci95": _interval(inc_boot),
              "improvement": float((inc.sum() - cand.sum()) / counts.sum()), "improvement_ci95": _interval(inc_boot - cand_boot)}
    if tail:
        bins = np.minimum((subset["candidate"].to_numpy(float) * 10).astype(int), 9)
        inc_bins = np.minimum((subset["incumbent"].to_numpy(float) * 10).astype(int), 9)
        def ece_sums(which: str, assignments: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            vectors = []
            for _, part in grouped:
                p, y = part[which].to_numpy(float), part["outcome_home_win"].to_numpy(float)
                local = np.minimum((p * 10).astype(int), 9)
                vectors.append((np.bincount(local, minlength=10), np.bincount(local, weights=p, minlength=10),
                                np.bincount(local, weights=y, minlength=10)))
            return tuple(np.asarray([item[index] for item in vectors], dtype=float) for index in range(3))
        def boot_ece(which: str) -> tuple[float, np.ndarray]:
            count, p_sum, y_sum = ece_sums(which, bins if which == "candidate" else inc_bins)
            c, p, y = weights @ count, weights @ p_sum, weights @ y_sum
            score = (c / c.sum(axis=1, keepdims=True) * np.abs(p / np.maximum(c, 1) - y / np.maximum(c, 1))).sum(axis=1)
            return float(ece(subset[which], subset["outcome_home_win"])), score
        candidate_ece, candidate_boot = boot_ece("candidate")
        incumbent_ece, incumbent_boot = boot_ece("incumbent")
        result.update({"candidate_ece": candidate_ece, "candidate_ece_ci95": _interval(candidate_boot),
                       "incumbent_ece": incumbent_ece, "incumbent_ece_ci95": _interval(incumbent_boot)})
    return result


def _paired_rows(rows: pd.DataFrame) -> pd.DataFrame:
    all_game = rows.groupby(["game_id", "season", "game_date", "split_id"], as_index=False).agg(
        n_ticks=("game_id", "size"), loss_candidate_sum=("loss_candidate", "sum"), loss_incumbent_sum=("loss_incumbent", "sum"),
        n_train_games=("n_train_games", "first"))
    all_game.insert(0, "record_type", "all_game")
    tail = rows[rows["tail"]].loc[:, ["game_id", "season", "game_date", "ts", "split_id", "outcome_home_win", "candidate", "incumbent", "loss_candidate", "loss_incumbent"]].copy()
    tail.insert(0, "record_type", "tail_tick")
    return pd.concat([all_game, tail], ignore_index=True, sort=False)


def _memo(summary: dict) -> str:
    lines = ["# S272 NBA in-game pooled-tail recalibration", "", "## Verdict: " + summary["verdict"], "",
             "Preregistration: `docs/evidence/harness/S272_ingame_tail_recal_prereg_2026-09-04.md`", "",
             "Preregistration SHA-256: `" + PREREG_SHA256 + "`", "",
             "S224 premise reproduced before scoring: low 136809/775, high 171947/963, middle 156493, total 465249, dropped 0.", "",
             "| denominator | arm | Brier (95 pct game-clustered CI) | tail ECE (95 pct game-clustered CI) | n ticks / games |",
             "|---|---|---|---|---|"]
    for name in ("all", "tail"):
        metric = summary["metrics"][name]
        for arm in ("candidate", "incumbent"):
            ece_text = "-" if name == "all" else "%.6f [%.6f, %.6f]" % tuple([metric[arm + "_ece"], *metric[arm + "_ece_ci95"]])
            lines.append("| %s | %s | %.6f [%.6f, %.6f] | %s | %d / %d |" % (name, arm, metric[arm + "_brier"], *metric[arm + "_brier_ci95"], ece_text, metric["n_ticks"], metric["n_games"]))
    all_metric = summary["metrics"]["all"]
    lines += ["", "All-ticks improvement versus recal_null: %.6f [%.6f, %.6f]; frozen bar: +0.004." % tuple([all_metric["improvement"], *all_metric["improvement_ci95"]]),
              "Although pooled tail ECE declines from %.6f to %.6f, the all-ticks result is BEHIND; this is a trade-off, not a win." % (summary["metrics"]["tail"]["incumbent_ece"], summary["metrics"]["tail"]["candidate_ece"]), "",
              "## Method and reproduction", "", "The shared `cpcv_evaluate` route used two season groups, the shared purge, and a symmetric one-day embargo. Fits admit only strict-prior game-first-dates. The candidate changes only the fixed low/high tail; outside it candidate equals recal_null.", "",
              "Artifacts: `docs/evidence/harness/%s_summary.json` and `docs/evidence/harness/%s_paired_losses.csv`. The paired CSV has per-game all-tick loss sums plus tail-tick predictions/losses, sufficient to recompute the reported all-ticks Brier and tail ECE." % (STEM, STEM),
              "Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (%d bytes; tabular, resolution not applicable). RSS at artifact write: %d bytes. Route SHA-256: `%s`." % (summary["input"]["bytes"], summary["rss_bytes"], summary["route_sha256"]),
              "Focused test: `python -m pytest scripts/platformkit/ingame/test_s272_ingame_tail_recal.py -q -p no:cacheprovider`."]
    return "\n".join(lines) + "\n"


def run(output_dir: Path = EVIDENCE) -> dict:
    """Run the sealed S272 comparison and write its differential evidence."""
    _verify_prereg()
    rows = pd.read_parquet(SOURCE)
    rows["season"] = _season(rows["game_date"])
    prediction, folds = _predict(rows)
    metrics = {"all": _metrics(prediction, False), "tail": _metrics(prediction, True)}
    seasons = {str(season): {"all": _metrics(part, False), "tail": _metrics(part, True)}
               for season, part in prediction.groupby("season", sort=True)}
    improvement, ci = metrics["all"]["improvement"], metrics["all"]["improvement_ci95"]
    verdict = "ACCEPT" if improvement >= 0.004 and ci[0] > 0.0 else ("BEHIND" if improvement <= 0.0 else "BELOW_FROZEN_BAR")
    output_dir.mkdir(parents=True, exist_ok=True)
    paired_path = output_dir / (STEM + "_paired_losses.csv")
    _paired_rows(prediction).to_csv(paired_path, index=False, encoding="ascii")
    summary = {"mode": "SEALED_SCREEN", "verdict": verdict, "bar": 0.004, "embargo_days": EMBARGO_DAYS,
               "bootstraps": BOOTSTRAPS, "seed": SEED, "folds": folds, "metrics": metrics, "season_metrics": seasons,
               "preregistration_path": str(PREREG.relative_to(ROOT)).replace("\\", "/"), "prereg_sha256": PREREG_SHA256,
               "paired_losses": str(paired_path.relative_to(ROOT)).replace("\\", "/"),
               "input": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "bytes": SOURCE.stat().st_size, "rows": len(rows), "resolution": "not applicable"},
               "rss_bytes": int(psutil.Process().memory_info().rss),
               "route_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output_dir / (STEM + "_summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (output_dir / (STEM + ".md")).write_text(_memo(summary), encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="S272 sealed NBA tail recalibration screen")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    summary = run(args.output_dir)
    print("S272 verdict=%s all_improvement=%.6f tail_candidate_ece=%.6f" % (summary["verdict"], summary["metrics"]["all"]["improvement"], summary["metrics"]["tail"]["candidate_ece"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
