"""scripts.platformkit.eval_gate.s80_player_grain_screen -- S80 in-game PLAYER-GRAIN screen.

The only in-game tick corpus in this repo that carries player identity at the tick is
MLB: data/cache/ingame_grade/mlb/*.jsonl exposes mlb_pitcher_id / mlb_batter_id on
8,384 ticks, of which 8,309 also carry a settled outcome + in-play market line in the
canonical scored store data/cache/ingame_grade_joined/mlb.  This module adds ONE
player-grain term to the incumbent e4 blend (scripts.platformkit.ingame.gap_blend_arm)
and screens it leak-free on the SCREEN side of a game-level partition.

Candidate = gap_blend_arm._guarded_prob(model, market, w*score_diff + beta*z, 1.0, dev)
so beta = 0 reproduces the incumbent EXACTLY (asserted); the two arms differ only by z.
z = the current pitcher's as-of run-prevention residual through his previous appearance,
signed by which side is pitching (half=top -> home pitching).

A SCREEN is a NON-FINDING: no prereg seal, no ledger charge, no K read.
Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/ingame/test_s80_player_grain_screen.py -q
"""
from __future__ import annotations

import glob
import json
from datetime import date as _date
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.catalog_rescreen import verdict_of
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.foundry.tiers import partition_corpus
from scripts.platformkit.ingame import gap_blend_arm as B

REPO = Path(__file__).resolve().parents[3]
GRADE = REPO / "data" / "cache" / "ingame_grade" / "mlb"
JOINED = REPO / "data" / "cache" / "ingame_grade_joined" / "mlb"
GAMELOGS = REPO / "data" / "domains" / "mlb" / "player_gamelogs.parquet"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s80_player_grain_2026-09-03"
MAX_DEV, W_MAX = B._DEFAULT_MAX_DEVIATION, B._DEFAULT_W_MAX
SHRINK_IP = 30.0          # innings of prior work at which the residual is half-weighted
BETA_GRID = np.linspace(-1.0, 1.0, 201)
PARTITION_SEED = 0
MIN_TRAIN_TICKS = 200


class AsOfLeak(ValueError):
    """A source row at or after the tick's own game date reached an as-of aggregate."""


def assert_asof(source_dates: Sequence[Any], as_of: Any, label: str) -> None:
    """THE tick-time leak guard: every source row must predate the tick's game date."""
    cut = pd.Timestamp(as_of)
    stamps = pd.to_datetime(pd.Series(list(source_dates), dtype="object"))
    bad = [str(d) for d in stamps if d >= cut]
    if bad:
        raise AsOfLeak("%s: %d source row(s) at or after the as-of date %s (first %s)"
                       % (label, len(bad), cut.date(), bad[0]))


def _jsonl(directory: Path) -> List[dict]:
    rows: List[dict] = []
    for path in sorted(glob.glob(str(directory / "*.jsonl"))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def load_player_ticks(joined: Path = JOINED, grade: Path = GRADE) -> pd.DataFrame:
    """Scored ticks (outcome + market line) that also carry pitcher identity at the tick."""
    ident = {(r["game_id"], r["ts"]): r for r in _jsonl(grade) if r.get("mlb_pitcher_id") is not None}
    rows = []
    for r in _jsonl(joined):
        key = (r["game_id"], r["ts"])
        if key not in ident or r.get("outcome") is None or r.get("market_prob") is None:
            continue
        summary = str(r.get("state_summary") or "")
        parts = dict(p.split("=", 1) for p in summary.split() if "=" in p)
        try:
            diff = float(parts["home_score"]) - float(parts["away_score"])
        except (KeyError, ValueError):
            continue
        rows.append({"game": str(r["game_id"]), "timestamp": str(r["ts"]),
                     "outcome": float(r["outcome"]), "model_prob": float(r["model_prob"]),
                     "market_prob": float(r["market_prob"]), "signal": diff,
                     "pitcher_id": int(ident[key]["mlb_pitcher_id"]),
                     "batter_id": int(ident[key]["mlb_batter_id"]),
                     "half": parts.get("half", "")})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["tick_date"] = frame["timestamp"].str[:10]
    frame["date"] = frame["game"].map(frame.groupby("game")["tick_date"].min())  # game-first-date (S36)
    return frame.sort_values(["timestamp", "game"], kind="stable").reset_index(drop=True)


def pitcher_residuals(logs: pd.DataFrame, pitcher_ids: Sequence[int], as_of: str) -> Dict[int, float]:
    """As-of run-prevention residual per pitcher, from appearances STRICTLY before `as_of`.

    residual = (league RA9 - pitcher RA9) / 9, shrunk by IP / (IP + SHRINK_IP).
    Positive = prevented more runs per inning than the league to date.  Unknown -> 0.0.
    """
    prior = logs[(logs["is_pitcher"]) & (logs["date"] < pd.Timestamp(as_of))]
    assert_asof(prior["date"].tolist(), as_of, "pitcher_residuals league window")
    league_ip = float(prior["outs"].sum()) / 3.0
    if league_ip <= 0.0:
        return {int(p): 0.0 for p in pitcher_ids}
    league_ra9 = 9.0 * float(prior["earnedRuns"].sum()) / league_ip
    agg = prior.groupby("player_id")[["outs", "earnedRuns"]].sum()
    out: Dict[int, float] = {}
    for pid in {int(p) for p in pitcher_ids}:
        if pid not in agg.index:
            out[pid] = 0.0
            continue
        innings = float(agg.at[pid, "outs"]) / 3.0
        if innings < 1.0:
            out[pid] = 0.0
            continue
        ra9 = 9.0 * float(agg.at[pid, "earnedRuns"]) / innings
        out[pid] = ((league_ra9 - ra9) / 9.0) * (innings / (innings + SHRINK_IP))
    return out


def attach_feature(ticks: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    """Add `z`: the as-of residual of the pitcher on the mound, signed toward the home side."""
    frame = ticks.copy()
    values = np.zeros(len(frame), dtype=float)
    for as_of, block in frame.groupby("date"):
        resid = pitcher_residuals(logs, block["pitcher_id"].tolist(), as_of)
        half = block["half"].to_numpy()
        sign = np.where(half == "top", 1.0, np.where(half == "bottom", -1.0, 0.0))  # top -> home pitching
        values[block.index.to_numpy()] = block["pitcher_id"].map(resid).to_numpy(dtype=float) * sign
    frame["z"] = values
    return frame


def screen_side(frame: pd.DataFrame, seed: int = PARTITION_SEED):
    """foundry partition on game blocks -> the SCREEN-side rows and the partition record."""
    states = [{"game_id": g, "corpus_unit": g, "state_ts": s + "T00:00:00"}
              for g, s in frame.groupby("game")["date"].min().items()]
    part = partition_corpus(states, seed=seed)
    return frame[frame["game"].isin(part.screen_ids)].reset_index(drop=True), part


def _fit_beta(train: pd.DataFrame, weight: float, z: np.ndarray) -> float:
    """One grid-searched logistic term on top of the incumbent's own fitted weight."""
    model, market, sig, y = (train[c].to_numpy(dtype=float) for c in
                             ("model_prob", "market_prob", "signal", "outcome"))
    scores = [(float(np.mean((B._guarded_prob(model, market, weight * sig + b * z, 1.0, MAX_DEV) - y) ** 2)),
               abs(float(b)), float(b)) for b in BETA_GRID]
    return min(scores)[2]                     # ties resolve toward beta = 0 (the incumbent)


def walk_forward(frame: pd.DataFrame, *, embargo_days: int) -> Tuple[pd.DataFrame, List[dict]]:
    """Game-first-date walk-forward; train games are purged (disjoint) and embargoed."""
    dates, scored, folds = sorted(frame["date"].unique()), [], []
    for d in dates:
        cut = str(_date.fromisoformat(d) - timedelta(days=int(embargo_days)))
        train, test = frame[frame["date"] < cut], frame[frame["date"] == d].copy()
        if len(train) < MIN_TRAIN_TICKS or train["outcome"].nunique() < 2:
            folds.append({"test_date": d, "status": "INSUFFICIENT", "n_train_ticks": int(len(train))})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= d, "embargo/ordering violated"
        mu = float(train["z"].mean())
        sd = float(train["z"].std(ddof=0))
        sd = sd if sd > 1e-12 else 1.0
        z_train = (train["z"].to_numpy() - mu) / sd
        z_test = (test["z"].to_numpy() - mu) / sd
        weight = B._fit_weight(train, W_MAX, MAX_DEV)
        beta = _fit_beta(train, weight, z_train)
        model, market, sig = (test[c].to_numpy(dtype=float) for c in ("model_prob", "market_prob", "signal"))
        test["p_incumbent"] = B._guarded_prob(model, market, sig, weight, MAX_DEV)
        test["p_zero_beta"] = B._guarded_prob(model, market, weight * sig + 0.0 * z_test, 1.0, MAX_DEV)
        test["p_candidate"] = B._guarded_prob(model, market, weight * sig + beta * z_test, 1.0, MAX_DEV)
        test["z_std"], test["beta"], test["weight"] = z_test, beta, weight
        assert np.allclose(test["p_incumbent"], test["p_zero_beta"], atol=1e-12), "beta=0 is not the incumbent"
        scored.append(test)
        folds.append({"test_date": d, "status": "OK", "embargo_cut": cut, "weight": weight, "beta": beta,
                      "n_train_ticks": int(len(train)), "n_train_games": int(train["game"].nunique()),
                      "train_date_max": str(train["date"].max()), "n_test_ticks": int(len(test)),
                      "n_test_games": int(test["game"].nunique()), "z_mu": mu, "z_sd": sd})
    return (pd.concat(scored, ignore_index=True) if scored else frame.iloc[0:0].copy()), folds


def score(scored: pd.DataFrame, folds: List[dict], part, *, embargo_days: int) -> Tuple[dict, pd.DataFrame]:
    y = scored["outcome"].to_numpy(dtype=float)
    l_inc = (scored["p_incumbent"].to_numpy() - y) ** 2
    l_cand = (scored["p_candidate"].to_numpy() - y) ** 2
    l_mkt = (scored["market_prob"].to_numpy() - y) ** 2
    diff = l_inc - l_cand                                  # d > 0 -> the candidate lost less
    games = scored["game"].astype(str).tolist()
    dm = diebold_mariano(diff.tolist(), games)
    improvement = float(l_inc.mean() - l_cand.mean())
    summary = {
        "spec_id": "scripts.platformkit.eval_gate.s80_player_grain_screen:mlb_pitcher_asof_ra9_v1",
        "sport": "mlb", "tier": "SCREEN (uncharged, no prereg seal, no K read)",
        "embargo_days": int(embargo_days), "purge": "by game (train games disjoint from test games)",
        "partition": {"basis": part.basis, "seed": part.seed, "screen_sha256": part.screen_sha256,
                      "verdict_sha256": part.verdict_sha256, "n_screen_games": len(part.screen_ids),
                      "n_verdict_games": len(part.verdict_ids)},
        "n_ticks": int(len(scored)), "n_games": int(scored["game"].nunique()),
        "brier": {"incumbent_e4": float(l_inc.mean()), "candidate_e4_plus_player": float(l_cand.mean()),
                  "market": float(l_mkt.mean())},
        "improvement_vs_e4": improvement,
        "dm": {"stat": float(dm.dm_stat), "p_value": float(dm.p_value),
               "ci95": [float(dm.ci95[0]), float(dm.ci95[1])], "n_clusters": int(dm.n_clusters)},
        "verdict": verdict_of(improvement, float(dm.p_value)),
        "beta_by_fold": {f["test_date"]: f.get("beta") for f in folds},
        "folds": folds, "single_window": True,
    }
    series = scored[["game", "timestamp", "date", "outcome", "pitcher_id", "z", "z_std", "beta", "weight",
                     "p_incumbent", "p_candidate", "market_prob"]].copy()
    series["loss_incumbent"] = l_inc
    series["loss_candidate"] = l_cand
    series["loss_differential"] = diff
    series["cluster_id"] = series["game"]
    return summary, series


def run(*, embargo_days: int = 1, out_dir: Path = OUT_DIR, suffix: str = "") -> dict:
    ticks = load_player_ticks()
    logs = pd.read_parquet(GAMELOGS, columns=["player_id", "date", "is_pitcher", "outs", "earnedRuns"])
    frame = attach_feature(ticks, logs)
    screen, part = screen_side(frame)
    scored, folds = walk_forward(screen, embargo_days=embargo_days)
    if scored.empty:
        return {"verdict": "SCREEN_INFEASIBLE", "folds": folds, "embargo_days": embargo_days,
                "n_screen_games": len(part.screen_ids), "n_screen_ticks": int(len(screen))}
    summary, series = score(scored, folds, part, embargo_days=embargo_days)
    summary["n_screen_ticks_available"] = int(len(screen))
    summary["n_player_ticks_total"] = int(len(frame))
    out_dir.mkdir(parents=True, exist_ok=True)
    csv = out_dir / ("%s%s.csv" % (STEM, suffix))
    series.to_csv(csv, index=False)
    summary["per_tick_series"] = str(csv)
    (out_dir / ("%s%s.json" % (STEM, suffix))).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    for embargo, suffix in ((1, ""), (0, "_embargo0")):
        res = run(embargo_days=embargo, suffix=suffix)
        if res["verdict"] == "SCREEN_INFEASIBLE":
            print("embargo=%d SCREEN_INFEASIBLE %s" % (embargo, res["folds"]))
            continue
        b = res["brier"]
        print("embargo=%d %s | n_ticks %d n_games %d | e4 %.6f -> %.6f (impr %+.6f) | market %.6f | "
              "dm p %.4g ci95 [%.6f, %.6f] clusters %d" % (
                  embargo, res["verdict"], res["n_ticks"], res["n_games"], b["incumbent_e4"],
                  b["candidate_e4_plus_player"], res["improvement_vs_e4"], b["market"],
                  res["dm"]["p_value"], res["dm"]["ci95"][0], res["dm"]["ci95"][1], res["dm"]["n_clusters"]))
        print("   betas %s" % res["beta_by_fold"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
