"""S219 NBA tail-guard screen: an uncharged calibration measurement.

The frozen family clamps the S123 ladder-base incumbent toward 0.5.  It scores
every out-of-fold tick, not just the confident ticks the clamp changes.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.cpcv_engine import _blocked_indices
from scripts.platformkit.eval_gate.dm_test import (_student_t_two_tailed_quantile,
                                                   diebold_mariano)
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.foundry.ingame_incumbent_nba import apply_incumbent
from scripts.platformkit.foundry.ingame_screen import BAR
from scripts.platformkit.foundry.ingame_screen_nba import fold_blocks
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

ROOT = Path(__file__).resolve().parents[3]
CHECKPOINTS = ROOT / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
EVIDENCE = ROOT / "docs" / "evidence" / "harness"
STEM = "S219_nba_tail_guard_screen_2026-09-04"
CONFIDENT_CUT = 0.3
EMBARGO_DAYS = 1
S58_ARCHIVE = (EVIDENCE / "neff_requote_2026-09-04" / "restored_sources" /
               "s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv")
GRID = ((0.05, 0.15), (0.05, 0.25), (0.05, 0.35),
        (0.10, 0.15), (0.10, 0.25), (0.10, 0.35))


def member_name(d_hi: float, d_lo: float) -> str:
    return "hi_%.2f_lo_%.2f" % (d_hi, d_lo)


def confident_side(probability: pd.Series) -> pd.Series:
    """Strict 0.3 midpoint cut, expressed as its exact two probability boundaries."""
    p = probability.astype(float)
    return (p > 0.5 + CONFIDENT_CUT) | (p < 0.5 - CONFIDENT_CUT)


def clamp_probability(probability: pd.Series, d_hi: float, d_lo: float) -> pd.Series:
    """Clamp from the midpoint, with the frozen cut deciding which radius applies."""
    p = probability.astype(float)
    radius = np.where(confident_side(p).to_numpy(), d_hi, d_lo)
    return pd.Series(0.5 + np.clip(p.to_numpy() - 0.5, -radius, radius), index=p.index)


def load_rows(path: Path = CHECKPOINTS) -> pd.DataFrame:
    """Read the one checkpoint store and form the S123 input schema."""
    source = pd.read_parquet(path)
    source = source[source["traded"] == True].copy()  # noqa: E712
    source = source.sort_values(["ts", "game_id"], kind="stable").reset_index(drop=True)
    rows = pd.DataFrame({
        "game": source["game_id"].astype(str),
        "game_date": source["game_date"].astype(str),
        "ts": pd.to_datetime(source["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market": source["market_prob"].astype(float),
        "y": source["outcome_home_win"].astype(float),
        "margin": source["margin"].astype(float),
        "rem": ((4 - source["period"].clip(upper=4)) * 12.0 + source["game_clock_s"] / 60.0).clip(lower=0.0),
    })
    rows["date"] = rows["game_date"]
    rows["game_date"] = fold_blocks(rows, n_folds=5)
    return rows


def _loss_summary(rows: pd.DataFrame, probability: pd.Series) -> Dict[str, object]:
    y = rows["y"].to_numpy(dtype=float)
    guard_loss = (probability.to_numpy(dtype=float) - y) ** 2
    incumbent_loss = (rows["incumbent"].to_numpy(dtype=float) - y) ** 2
    market_loss = (rows["market"].to_numpy(dtype=float) - y) ** 2
    differential = incumbent_loss - guard_loss
    dm = diebold_mariano(differential.tolist(), rows["game"].tolist())
    ess = effective_sample_size(pd.DataFrame({"game": rows["game"], "loss_differential": differential}))
    return {
        "n_ticks": int(len(rows)), "n_games": int(rows["game"].nunique()), "n_eff": float(ess["n_eff"]),
        "brier_guard": float(guard_loss.mean()), "brier_incumbent": float(incumbent_loss.mean()),
        "brier_market": float(market_loss.mean()), "improvement_vs_incumbent": float(differential.mean()),
        "dm_ci95": [float(dm.ci95[0]), float(dm.ci95[1])], "dm_p_raw": float(dm.p_value),
        "ece_guard": float(ece(probability.to_numpy(), y)),
        "ece_incumbent": float(ece(rows["incumbent"].to_numpy(), y)),
        "ece_market": float(ece(rows["market"].to_numpy(), y)),
    }


def loser_tail_share(rows: pd.DataFrame, probability: pd.Series) -> float:
    """Game share with any tick above 0.8 on its eventual losing side."""
    p, y = probability.to_numpy(dtype=float), rows["y"].to_numpy(dtype=float)
    losing_side = ((y == 0.0) & (p > 0.8)) | ((y == 1.0) & (p < 0.2))
    return float(pd.Series(losing_side, index=rows["game"]).groupby(level=0).any().mean())


def remeasure_s58_tail(path: Path = S58_ARCHIVE) -> Dict[str, object]:
    """Recompute the Trial B eventual-loser tail premise from its restored archive."""
    frame = pd.read_csv(path, comment="#")
    assert len(frame) == frame["game_id"].nunique() == 1593, "S58 denominator drift"
    losers = frame[frame["y"] == 0.0]

    def tail_count(column: str) -> int:
        return int((losers[column] > 0.8).sum())

    model, market, denominator = tail_count("model"), tail_count("market"), int(len(losers))
    return {"path": str(path), "bytes": int(path.stat().st_size), "denominator": denominator,
            "model_tail_count": model, "market_tail_count": market,
            "model_tail_share": float(model / denominator), "market_tail_share": float(market / denominator)}


def _select(train: pd.DataFrame) -> Tuple[float, float]:
    scored = []
    for d_hi, d_lo in GRID:
        guarded = clamp_probability(train["incumbent"], d_hi, d_lo)
        loss = ((guarded - train["y"]) ** 2).mean()
        scored.append((float(loss), d_hi, d_lo))
    _, d_hi, d_lo = min(scored)
    return d_hi, d_lo


def _purged_selection(rows: pd.DataFrame, fold: str) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Return earlier OOF rows outside S233's symmetric one-day embargo."""
    dates = pd.to_datetime(rows["ts"], utc=True).dt.date
    unique_dates = sorted(set(dates)); date_index = {date: index for index, date in enumerate(unique_dates)}
    states = [{"state_ts": "%sT00:00:00+00:00" % date, "home": "h%s" % index,
               "away": "a%s" % index} for index, date in enumerate(unique_dates)]
    stamps = [pd.Timestamp(str(date), tz="UTC").to_pydatetime() for date in unique_dates]
    test_dates = set(dates[rows["game_date"] == fold])
    blocked = _blocked_indices(states, stamps, [date_index[date] for date in test_dates], EMBARGO_DAYS)
    blocked_dates = {unique_dates[index] for index in blocked}
    earlier = rows[rows["game_date"] < fold]
    selected = earlier.loc[~dates.loc[earlier.index].isin(blocked_dates)].copy()
    selected_dates = set(pd.to_datetime(selected["ts"], utc=True).dt.date)
    assert all(abs((train_day - test_day).days) > EMBARGO_DAYS
               for train_day in selected_dates for test_day in test_dates), "selection embargo violation"
    return selected, {"available_ticks": int(len(earlier)), "selected_ticks": int(len(selected)),
                      "embargoed_ticks": int(len(earlier) - len(selected)),
                      "scored_ticks": int((rows["game_date"] == fold).sum())}


def _bh(records: List[Dict[str, object]]) -> None:
    ordered = sorted(enumerate(records), key=lambda pair: float(pair[1]["dm_p_raw"]))
    count, running = len(records), 1.0
    adjusted = [1.0] * count
    for rank, (index, row) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, float(row["dm_p_raw"]) * count / rank)
        adjusted[index] = running
    for row, value in zip(records, adjusted):
        row["bh_q05"] = bool(value <= 0.05)
        row["bh_adjusted_p"] = float(value)
        row["bar_ci_bh_pass"] = bool(row["improvement_vs_incumbent"] >= BAR and
                                      row["dm_ci95"][0] > 0.0 and value <= 0.05)


def _per_game(rows: pd.DataFrame, probability: pd.Series, member: str,
              selection: str) -> List[Dict[str, object]]:
    frame = pd.DataFrame({"game": rows["game"], "fold": rows["game_date"], "timestamp": rows["ts"],
                          "y": rows["y"], "guard_probability": probability,
                          "incumbent_probability": rows["incumbent"], "market_probability": rows["market"],
                          "guard_loss": (probability - rows["y"]) ** 2,
                          "incumbent_loss": (rows["incumbent"] - rows["y"]) ** 2,
                          "market_loss": (rows["market"] - rows["y"]) ** 2})
    grouped = frame.groupby(["game", "fold"], sort=True)
    archive = []
    for (game, fold), part in grouped:
        values = {key: np.where(part["y"] == 0.0, part[key], 1.0 - part[key])
                  for key in ("guard_probability", "incumbent_probability", "market_probability")}
        tails = {key: bool((((part["y"] == 0.0) & (part[key] > 0.8)) |
                            ((part["y"] == 1.0) & (part[key] < 0.2))).any()) for key in values}
        archive.append({"member": member, "selection": selection, "game": str(game), "fold": str(fold),
                        "timestamp": str(part["timestamp"].min()), "n_ticks": int(len(part)),
                        "loss_guard_sum": float(part["guard_loss"].sum()),
                        "loss_incumbent_sum": float(part["incumbent_loss"].sum()),
                        "loss_market_sum": float(part["market_loss"].sum()),
                        "tail_guard": tails["guard_probability"], "tail_incumbent": tails["incumbent_probability"],
                        "tail_market": tails["market_probability"],
                        "max_loser_probability_guard": float(values["guard_probability"].max()),
                        "max_loser_probability_incumbent": float(values["incumbent_probability"].max()),
                        "max_loser_probability_market": float(values["market_probability"].max())})
    return archive


def recompute_from_per_game(rows: Iterable[Dict[str, object]]) -> Dict[str, object]:
    """Recompute the tick-weighted differential and clustered CI from Q9 sums."""
    parts = list(rows)
    counts = np.asarray([float(row["n_ticks"]) for row in parts])
    guard = np.asarray([float(row["loss_guard_sum"]) for row in parts])
    incumbent = np.asarray([float(row["loss_incumbent_sum"]) for row in parts])
    n, games = int(counts.sum()), len(parts)
    mean = float((incumbent - guard).sum() / n)
    centered_sums = incumbent - guard - counts * mean
    variance = float((centered_sums @ centered_sums) / (n * n) * games / (games - 1.0))
    half = float(_student_t_two_tailed_quantile(0.05, games - 1) * np.sqrt(variance))
    result = {"n_ticks": n, "n_games": games, "improvement_vs_incumbent": mean,
              "dm_ci95": [mean - half, mean + half]}
    for arm in ("guard", "incumbent", "market"):
        result["tail_" + arm] = float(np.mean([str(row["tail_" + arm]).lower() == "true" for row in parts]))
    return result


def screen(rows: pd.DataFrame) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    """Score every fixed guard plus a train-selected composite on all outer-test ticks."""
    anchored = apply_incumbent(rows, "ladder_base").drop(columns=["incumbent"], errors="ignore")
    anchored = anchored.rename(columns={"p_e4": "incumbent"})
    anchored = anchored.sort_values(["game_date", "ts", "game"], kind="stable").reset_index(drop=True)
    folds = sorted(anchored["game_date"].unique())
    tests = []
    selections: Dict[str, str] = {}
    selection_tick_counts: Dict[str, Dict[str, int]] = {}
    for fold in folds:
        train, selection_tick_counts[str(fold)] = _purged_selection(anchored, str(fold))
        test = anchored[anchored["game_date"] == fold].copy()
        if train.empty or test.empty:
            continue
        d_hi, d_lo = _select(train)
        test["composite"] = clamp_probability(test["incumbent"], d_hi, d_lo)
        selections[str(fold)] = member_name(d_hi, d_lo)
        tests.append(test)
    scored = pd.concat(tests, ignore_index=True)
    qualified = anchored.groupby("game")["incumbent"].apply(
        lambda p: bool(confident_side(p).any()))
    records: List[Dict[str, object]] = []
    archive: List[Dict[str, object]] = []
    for d_hi, d_lo in GRID:
        name = member_name(d_hi, d_lo)
        probability = clamp_probability(scored["incumbent"], d_hi, d_lo)
        row: Dict[str, object] = {"member": name, "d_hi": d_hi, "d_lo": d_lo}
        row.update(_loss_summary(scored, probability))
        row["tail_guard"] = loser_tail_share(scored, probability)
        row["tail_incumbent"] = loser_tail_share(scored, scored["incumbent"])
        row["tail_market"] = loser_tail_share(scored, scored["market"])
        records.append(row)
        archive.extend(_per_game(scored, probability, name, "fixed"))
    _bh(records)
    composite = _loss_summary(scored, scored["composite"])
    composite.update({"member": "composite", "d_hi": None, "d_lo": None,
                      "tail_guard": loser_tail_share(scored, scored["composite"]),
                      "tail_incumbent": loser_tail_share(scored, scored["incumbent"]),
                      "tail_market": loser_tail_share(scored, scored["market"]),
                      "selection_by_outer_fold": selections})
    archive.extend(_per_game(scored, scored["composite"], "composite", "inner_selected"))
    selected_members = {name for name in selections.values()}; selected_bh = [row for row in records if row["member"] in selected_members]
    composite["bh_q05"] = bool(selected_bh) and all(bool(row["bh_q05"]) for row in selected_bh)
    composite["bh_adjusted_p"] = max(float(row["bh_adjusted_p"]) for row in selected_bh)
    composite["bar_ci_bh_pass"] = bool(composite["improvement_vs_incumbent"] >= BAR and
                                        composite["dm_ci95"][0] > 0.0 and composite["bh_q05"])
    for row in records + [composite]:
        reproduced = recompute_from_per_game(item for item in archive if item["member"] == row["member"])
        assert all(reproduced["tail_" + arm] == row["tail_" + arm] for arm in ("guard", "incumbent", "market"))
    summary = {"bar": BAR, "confident_cut": CONFIDENT_CUT, "grid": [list(item) for item in GRID],
               "incumbent": "ladder_base", "n_qualifying_games": int(qualified.sum()),
               "n_scored_games": int(scored["game"].nunique()), "n_scored_ticks": int(len(scored)),
               "selection_tick_counts": selection_tick_counts,
               "members": records, "composite": composite,
               "verdict": "SCREEN_SIGNAL" if composite["bar_ci_bh_pass"] else "SCREEN_NULL"}
    return summary, archive


def run(output_dir: Path = EVIDENCE, source: Path = CHECKPOINTS) -> Dict[str, object]:
    """Run the uncharged screen and write its recomputable summary and paired series."""
    premise_s58 = remeasure_s58_tail()
    rows = load_rows(source)
    summary, archive = screen(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    series_path = output_dir / (STEM + "_per_game_paired_losses.csv")
    with series_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(archive[0]))
        writer.writeheader()
        writer.writerows(archive)
    summary["input"] = {"path": str(source), "bytes": source.stat().st_size,
                        "source_rows": int(len(rows)), "source_games": int(rows["game"].nunique())}
    summary["paired_loss_series"] = str(series_path)
    summary["premise_s58"] = premise_s58
    (output_dir / (STEM + "_summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="ascii")
    return summary


def main() -> int:
    summary = run()
    composite = summary["composite"]
    premise = summary["premise_s58"]
    print("S219 S58 premise model=%d/%d (%.6f) market=%d/%d (%.6f)" %
          (premise["model_tail_count"], premise["denominator"], premise["model_tail_share"],
           premise["market_tail_count"], premise["denominator"], premise["market_tail_share"]))
    print("S219 qualifying_games=%d scored_games=%d scored_ticks=%d" %
          (summary["n_qualifying_games"], summary["n_scored_games"], summary["n_scored_ticks"]))
    print("S219 composite improvement=%+.6f ci=%s" %
          (composite["improvement_vs_incumbent"], composite["dm_ci95"]))
    print("S219 composite verdict=%s" % summary["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
