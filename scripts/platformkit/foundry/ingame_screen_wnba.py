"""S206 WNBA first in-game calibration screen, using the unchanged S82 machinery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.foundry.ingame_guards import assert_tick_asof
from scripts.platformkit.foundry.ingame_screen import BAR, ROOT, walk_forward_feature
from scripts.platformkit.foundry.ingame_screen_nba import _icc
from scripts.platformkit.ingame.wnba_outcome_resolver import parse_wnba_ticker

STORE = ROOT / "data" / "cache" / "inplay_odds" / "wnba_checkpoints_full.parquet"
PRICE_STORE = ROOT / "data" / "cache" / "inplay_odds" / "wnba_price_series.parquet"
PER_GAME = ROOT / "docs" / "evidence" / "harness" / "wnba_ingame_census_2026-09-04_per_game.csv"
OUT = ROOT / "docs" / "evidence" / "harness"
STEM = "S206_wnba_ingame_first_score_2026-09-04"
FEATURE = "stern_margin_over_sqrt_remaining"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _home_probability_map(path: Path = PRICE_STORE) -> Tuple[pd.DataFrame, dict]:
    """Read price rows first and retain only the derived home-oriented probability map.

    The checkpoint store intentionally retained `prob` but not contract `side`; a raw side
    probability is not comparable with the home-win label.  This reconstructs orientation
    from the original local price rows, then releases that store before checkpoints load.
    """
    prices = pd.read_parquet(path, columns=["event_key", "ts", "prob", "traded", "side",
                                            "market_type", "close_time", "result_where_known"])
    prices = prices[prices["market_type"].eq("moneyline")].copy()
    close = pd.to_datetime(prices["close_time"], utc=True).astype("int64") // 10**9
    prices = prices[prices["ts"] < close].copy()
    prices["_occ"] = prices.groupby(["event_key", "ts", "prob", "traded"], sort=False,
                                     dropna=False).cumcount()
    tails = prices["event_key"].map(lambda key: parse_wnba_ticker(str(key))[1]).to_numpy()
    sides = prices["side"].astype(str).str.upper().to_numpy()
    starts = np.fromiter((tail.startswith(side) for tail, side in zip(tails, sides)), bool)
    ends = np.fromiter((tail.endswith(side) for tail, side in zip(tails, sides)), bool)
    assert (starts | ends).all(), "unknown WNBA side"
    prices["home_market_prob"] = np.where(ends, prices["prob"], 1.0 - prices["prob"])
    facts = {"inplay_priced_events": int(prices["event_key"].nunique()),
             "settled_priced_events": int(prices.groupby("event_key")["result_where_known"].
                                           agg(lambda values: values.notna().any()).sum())}
    return prices[["event_key", "ts", "prob", "traded", "_occ", "home_market_prob"]], facts


def load_rows(path: Path = STORE) -> pd.DataFrame:
    """Read the joined WNBA checkpoint store after deriving its home-probability map."""
    orientation, price_facts = _home_probability_map()
    frame = pd.read_parquet(path)
    required = {"game_id", "game_date", "ts", "period", "game_clock_s", "margin",
                "market_prob", "outcome_home_win", "state_age_s"}
    assert required <= set(frame.columns), "checkpoint store schema changed"
    frame["_occ"] = frame.groupby(["event_key", "ts", "market_prob", "traded"], sort=False,
                                   dropna=False).cumcount()
    frame = frame.merge(orientation, left_on=["event_key", "ts", "market_prob", "traded", "_occ"],
                        right_on=["event_key", "ts", "prob", "traded", "_occ"], how="left",
                        validate="one_to_one")
    assert frame["home_market_prob"].notna().all() and frame["outcome_home_win"].notna().all()
    rows = pd.DataFrame({
        "row_id": np.arange(len(frame)), "game": frame["game_id"].astype(str),
        "ts": pd.to_datetime(frame["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "game_date": frame["game_date"].astype(str), "y": frame["outcome_home_win"].astype(float),
        "p_e4": frame["home_market_prob"].astype(float),
        "market": frame["home_market_prob"].astype(float),
        "period": frame["period"].astype(float), "game_clock_s": frame["game_clock_s"].astype(float),
        "margin": frame["margin"].astype(float), "state_age_s": frame["state_age_s"].astype(float),
    })
    rows = rows.sort_values(["ts", "game", "row_id"], kind="stable").reset_index(drop=True)
    rows.attrs.update(price_facts)
    return rows


def causal_source(rows: pd.DataFrame) -> pd.DataFrame:
    """Only state observed at this tick; labels and market values are deliberately absent."""
    return rows[["game", "ts", "row_id", "period", "game_clock_s", "margin"]].rename(
        columns={"row_id": "_row_id", "ts": "timestamp"})


def build_features(src: pd.DataFrame) -> pd.DataFrame:
    """Stern (1994) state signal: score margin scaled by square-root game time remaining.

    The one fitted coefficient on this term is the free sigma.  It is a function only of
    the current action-derived state, so the S82 prefix guard can enforce tick-time as-of.
    """
    remaining = src["game_clock_s"] + (4.0 - src["period"]).clip(lower=0.0) * 600.0
    # Overtime has its own clock; the floor prevents a terminal divide-by-zero only.
    remaining = remaining.where(src["period"] <= 4.0, src["game_clock_s"]).clip(lower=1.0)
    out = src[["game", "timestamp", "_row_id"]].copy()
    out[FEATURE] = src["margin"].astype(float) / np.sqrt(remaining.astype(float))
    return out


def _reliability(y: np.ndarray, p: np.ndarray) -> Tuple[float, List[dict]]:
    bins = np.linspace(0.0, 1.0, 11)
    rows: List[dict] = []
    ece = 0.0
    for index in range(10):
        lo, hi = bins[index], bins[index + 1]
        keep = (p >= lo) & ((p < hi) if index < 9 else (p <= hi))
        n = int(keep.sum())
        mean_p = float(p[keep].mean()) if n else None
        mean_y = float(y[keep].mean()) if n else None
        if n:
            ece += n / len(y) * abs(mean_p - mean_y)
        rows.append({"bin": "%0.1f-%0.1f" % (lo, hi), "n": n,
                     "mean_probability": mean_p, "observed_rate": mean_y})
    return float(ece), rows


def premise(rows: pd.DataFrame, per_game: Path = PER_GAME) -> dict:
    """Re-measure S206's stated denominator from the joined store plus committed game census."""
    games = pd.read_csv(per_game)
    return {
        "joined_ticks": int(len(rows)), "joined_games": int(rows["game"].nunique()),
        "inplay_denominator": int(games["inplay_ticks"].sum()),
        "in_span_ticks": int(games["inside_pbp_span_ticks"].sum()),
        "in_span_share": float(games["inside_pbp_span_ticks"].sum() / games["inplay_ticks"].sum()),
        "age_median_s": float(rows["state_age_s"].median()),
        "age_p90_s": float(rows["state_age_s"].quantile(0.9)),
        "age_above_300": int((rows["state_age_s"] > 300.0).sum()),
        "games_in_span_at_least_100": int((games["inside_pbp_span_ticks"] >= 100).sum()),
        "settled_labeled_ticks": int(rows["y"].notna().sum()),
        "inplay_priced_events": int(rows.attrs["inplay_priced_events"]),
        "settled_priced_events": int(rows.attrs["settled_priced_events"]),
    }


def screen(rows: pd.DataFrame) -> Tuple[dict, pd.DataFrame]:
    """Fit null and Stern arms on the same purged game-first-date walk-forward folds."""
    table = build_features(causal_source(rows))
    frame = rows.merge(table.drop(columns=["game", "timestamp"]), left_on="row_id",
                       right_on="_row_id", how="left", validate="one_to_one")
    candidate, null, folds = walk_forward_feature(frame, FEATURE)
    keep = candidate.notna()
    scored = frame.loc[keep].copy()
    assert int(keep.sum()) and (null[keep].notna()).all(), "no scored S206 folds"
    scored["p_null"] = null[keep].to_numpy()
    scored["p_candidate"] = candidate[keep].to_numpy()
    scored["loss_market"] = (scored["market"] - scored["y"]) ** 2
    scored["loss_null"] = (scored["p_null"] - scored["y"]) ** 2
    scored["loss_candidate"] = (scored["p_candidate"] - scored["y"]) ** 2
    scored["delta_null_minus_candidate"] = scored["loss_null"] - scored["loss_candidate"]
    delta = scored["delta_null_minus_candidate"].to_numpy()
    dm = diebold_mariano(delta.tolist(), scored["game"].tolist())
    codes, unique = pd.factorize(scored["game"], sort=False)
    icc = _icc(delta, codes, len(unique))
    n_eff = len(scored) / max(1.0, 1.0 + (len(scored) / len(unique) - 1.0) * icc)
    y = scored["y"].to_numpy()
    series = {"market": scored["market"].to_numpy(), "null": scored["p_null"].to_numpy(),
              "candidate": scored["p_candidate"].to_numpy()}
    reliability = {name: _reliability(y, values) for name, values in series.items()}
    result = {
        "n_scored_ticks": int(len(scored)), "n_scored_games": int(len(unique)),
        "n_eff": float(n_eff), "icc_game": float(icc), "bar": BAR,
        "brier_market": float(scored["loss_market"].mean()),
        "brier_null": float(scored["loss_null"].mean()),
        "brier_candidate": float(scored["loss_candidate"].mean()),
        "improvement_vs_null": float(delta.mean()), "dm_stat": float(dm.dm_stat),
        "dm_p_raw": float(dm.p_value), "dm_ci95": [float(dm.ci95[0]), float(dm.ci95[1])],
        "clears_bar": bool(delta.mean() >= BAR and dm.ci95[0] > 0.0), "folds": folds,
        "ece_market": reliability["market"][0], "ece_null": reliability["null"][0],
        "ece_candidate": reliability["candidate"][0],
        "reliability": {name: table for name, (_, table) in reliability.items()},
        "unscored_joined_ticks": int((~keep).sum()),
        "unscored_joined_games": int(frame.loc[~keep, "game"].nunique()),
        "unscored_by_game_date": {str(date): int(count) for date, count in
                                   frame.loc[~keep].groupby("game_date").size().items()},
    }
    return result, scored


def write_artifacts(report: dict, scored: pd.DataFrame, *, out: Path = OUT) -> Tuple[Path, Path]:
    """Archive the paired differential in CSV and a machine-readable summary outside data/."""
    out.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = out / (STEM + "_paired_loss.csv"), out / (STEM + "_summary.json")
    columns = ["row_id", "game", "timestamp", "game_date", "y", "market", "p_null",
               "p_candidate", "margin", "period", "game_clock_s", "state_age_s", FEATURE,
               "loss_market", "loss_null", "loss_candidate", "delta_null_minus_candidate"]
    scored.rename(columns={"ts": "timestamp"})[columns].to_csv(csv_path, index=False)
    payload = dict(report)
    try:
        rendered_csv = str(csv_path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        rendered_csv = str(csv_path)
    payload["paired_loss_csv"] = rendered_csv
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return csv_path, json_path


def run() -> Tuple[dict, Path, Path]:
    """Run S206 locally; it writes evidence only and never touches data, ledger, or register."""
    rows = load_rows()
    facts = premise(rows)
    expected = (18650, 85, 186736, 19456, 15.0, 132.0, 0, 84)
    measured = (facts["joined_ticks"], facts["joined_games"], facts["inplay_denominator"],
                facts["in_span_ticks"], facts["age_median_s"], facts["age_p90_s"],
                facts["age_above_300"], facts["games_in_span_at_least_100"])
    assert measured == expected, "S206 premise falsified"
    probes = assert_tick_asof(causal_source(rows), build_features, probes=8)
    report, scored = screen(rows)
    report.update({"verdict": "SCREEN (a non-finding)", "sport": "wnba", "feature": FEATURE,
                   "premise": facts, "asof_probes": probes, "sources": [
                       {"path": str(STORE.relative_to(ROOT)).replace("\\", "/"),
                        "bytes": STORE.stat().st_size, "sha256": _sha256(STORE)},
                       {"path": str(PRICE_STORE.relative_to(ROOT)).replace("\\", "/"),
                        "bytes": PRICE_STORE.stat().st_size, "sha256": _sha256(PRICE_STORE)},
                       {"path": str(PER_GAME.relative_to(ROOT)).replace("\\", "/"),
                        "bytes": PER_GAME.stat().st_size, "sha256": _sha256(PER_GAME)}]})
    csv_path, json_path = write_artifacts(report, scored)
    return report, csv_path, json_path


if __name__ == "__main__":
    result, csv_file, json_file = run()
    print("premise joined %d/%d inplay; in-span %d; ages median %.0f p90 %.0f above300 %d; >=100 %d"
          % (result["premise"]["joined_ticks"], result["premise"]["inplay_denominator"],
             result["premise"]["in_span_ticks"], result["premise"]["age_median_s"],
             result["premise"]["age_p90_s"], result["premise"]["age_above_300"],
             result["premise"]["games_in_span_at_least_100"]))
    print("as-of probes %s" % result["asof_probes"])
    print("scored %d ticks / %d games; market %.6f null %.6f candidate %.6f; improvement %+.6f CI [%+.6f %+.6f]; n_eff %.2f"
          % (result["n_scored_ticks"], result["n_scored_games"], result["brier_market"],
             result["brier_null"], result["brier_candidate"], result["improvement_vs_null"],
             result["dm_ci95"][0], result["dm_ci95"][1], result["n_eff"]))
    print("paired loss %s; summary %s" % (csv_file, json_file))
