"""scripts.platformkit.eval_gate.s94_nba_early_shrinkage -- S94: phase-conditioned shrinkage
of the NBA in-play line toward the as-of state price.

S86 measured the market's OWN reliability on the screen side and found it worst early in
close games: P1|close ECE 0.0556, P2|close ECE 0.0642, one-directional (the 0.4-0.5 bin
realises about 0.55, the 0.8-0.9 bin about 0.73). The candidate arm asks whether shrinking
the line back toward the pregame-prior state price repairs that:

    p = sigmoid((1 - w_c) * logit(market) + w_c * logit(prior_state))

with prior_state = the S86 `model` column (price_checkpoint over ratings.replay(until=
game_date)) and w_c fit per phase cell (period x |margin| x time-remaining -- the S86 cells)
by minimising Brier on TRAIN folds only. Two NULL arms on identical rows: a global logistic
recalibration [1, logit(market)] and a per-cell logistic recalibration. If the candidate does
not beat the per-cell recalibration, the effect is recalibration, not shrinkage.

Input is the S86 archived per-tick CSV (SCREEN side, 232,951 ticks / 797 games); the verdict
side is never read. A SCREEN is a NON-FINDING: no prereg seal, no ledger charge, no K read,
no ledger write. SINGLE-WINDOW. Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/ingame/test_s94_nba_early_shrinkage.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

REPO = Path(__file__).resolve().parents[3]
S86_CSV = REPO / "data" / "cache" / "eval_gate" / "s86_nba_every_tick_2026-09-03.csv"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s94_nba_early_shrinkage_2026-09-03"

TARGET_PERIODS = ("P1", "P2")
TARGET_MARGIN = "close_le5"
TARGET_REM = "rem_gt12"
IMPROVEMENT_BAR = 0.004          # the row's bar; NEVER lowered (Q3)
N_FOLDS = 5
EMBARGO_DAYS = 1
MIN_CELL_TRAIN = 200             # below this a cell keeps w=0 (raw market) / the global recal
W_GRID = np.round(np.arange(0.0, 1.0 + 1e-9, 0.005), 4)
EPS = 1e-6
COLS = ["game_id", "game_date", "ts", "period_bucket", "margin_bucket", "rem_bucket",
        "model", "market", "y"]
ARMS = ("market", "recal", "cellrecal", "candidate")


def logit(p) -> np.ndarray:
    q = np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)
    return np.log(q / (1.0 - q))


def sigmoid(z) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def load_screen(path: Path = S86_CSV) -> pd.DataFrame:
    """The S86 SCREEN-side per-tick archive, plus the phase cell and the game-first date.

    NOTE (measured 2026-09-03): the S86 CSV rounds market prices that sit exactly on a bin
    edge -- the parquet holds 0.30000000000000004 and the CSV holds 0.3 -- which moves 34
    (P1) / 44 (P2) close-game ticks across the 0.3 reliability edge. Brier and the DM CI are
    unaffected at 1e-16; only bin-counted diagnostics shift (market ECE by about 0.0006).
    """
    return prepare(pd.read_csv(path, usecols=COLS))


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["game"] = out["game_id"].astype(str)
    out["date"] = out["game"].map(out.groupby("game")["game_date"].min())
    out["cell"] = out["period_bucket"] + "|" + out["margin_bucket"] + "|" + out["rem_bucket"]
    out["logit_market"] = logit(out["market"])
    out["logit_model"] = logit(out["model"])
    return out.sort_values(["date", "game", "ts"], kind="stable").reset_index(drop=True)


def target_mask(frame: pd.DataFrame) -> pd.Series:
    return (frame["period_bucket"].isin(TARGET_PERIODS)
            & (frame["margin_bucket"] == TARGET_MARGIN)
            & (frame["rem_bucket"] == TARGET_REM))


def fold_dates(frame: pd.DataFrame, n_folds: int = N_FOLDS) -> List[Sequence[str]]:
    """Ordered game dates split into n_folds+1 contiguous blocks of roughly equal tick count.

    Block 0 is the train-only seed; blocks 1..n_folds are the held-out test blocks.
    """
    per_day = frame.groupby("date").size().sort_index()
    days = list(per_day.index)
    edges = np.linspace(0, len(frame), n_folds + 2)[1:-1]
    cuts = np.searchsorted(per_day.to_numpy().cumsum(), edges)
    bounds = [0] + sorted({min(int(c) + 1, len(days)) for c in cuts}) + [len(days)]
    return [days[a:b] for a, b in zip(bounds[:-1], bounds[1:]) if b > a]


def fit_w(train: pd.DataFrame) -> Dict[str, float]:
    """w_c per cell on TRAIN only: the grid point minimising that cell's tick-weighted Brier."""
    out: Dict[str, float] = {}
    for cell, sub in train.groupby("cell", sort=True):
        if len(sub) < MIN_CELL_TRAIN or sub["y"].nunique() < 2:
            out[cell] = 0.0
            continue
        lm = sub["logit_market"].to_numpy()
        gap = sub["logit_model"].to_numpy() - lm
        y = sub["y"].to_numpy(dtype=float)
        losses = [float(np.mean((sigmoid(lm + w * gap) - y) ** 2)) for w in W_GRID]
        out[cell] = float(W_GRID[int(np.argmin(losses))])
    return out


def _recal(train: pd.DataFrame) -> LogisticRegression:
    """Unregularised logistic recalibration on [1, logit(market)] (C large == no penalty)."""
    return LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000).fit(
        train[["logit_market"]].to_numpy(), train["y"].to_numpy(dtype=int))


def apply_fold(train: pd.DataFrame, test: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Fit w_c and both recalibration nulls on TRAIN, then apply all three to TEST."""
    w_by_cell = fit_w(train)
    out = test.copy()
    w = out["cell"].map(w_by_cell).fillna(0.0).to_numpy(dtype=float)
    lm = out["logit_market"].to_numpy()
    out["w_c"] = w
    out["p_candidate"] = sigmoid(lm + w * (out["logit_model"].to_numpy() - lm))
    glob = _recal(train)
    out["p_recal"] = glob.predict_proba(out[["logit_market"]].to_numpy())[:, 1]
    cell_p = np.array(out["p_recal"], dtype=float)
    for cell, sub in train.groupby("cell", sort=True):
        rows = (out["cell"] == cell).to_numpy()
        if not rows.any():
            continue
        model = _recal(sub) if len(sub) >= MIN_CELL_TRAIN and sub["y"].nunique() >= 2 else glob
        cell_p[rows] = model.predict_proba(out.loc[rows, ["logit_market"]].to_numpy())[:, 1]
    out["p_cellrecal"] = cell_p
    return out, w_by_cell


def walk_forward(frame: pd.DataFrame, *, embargo_days: int = EMBARGO_DAYS,
                 n_folds: int = N_FOLDS) -> Tuple[pd.DataFrame, List[dict]]:
    """Expanding walk-forward by game-first date; train purged by game and embargoed."""
    blocks = fold_dates(frame, n_folds)
    scored: List[pd.DataFrame] = []
    folds: List[dict] = []
    for k, block in enumerate(blocks[1:], start=1):
        day0 = min(block)
        cut = str(dt.date.fromisoformat(str(day0)) - dt.timedelta(days=int(embargo_days)))
        train = frame[frame["date"] < cut]
        test = frame[frame["date"].isin(set(block))]
        if train.empty or train["y"].nunique() < 2 or test.empty:
            folds.append({"fold": k, "status": "INSUFFICIENT", "n_train": int(len(train))})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= day0, "embargo/ordering violated"
        block_out, w_by_cell = apply_fold(train, test)
        block_out["fold"] = k
        scored.append(block_out)
        folds.append({"fold": k, "status": "OK", "test_start": str(day0), "test_end": str(max(block)),
                      "embargo_cut": cut, "train_date_max": str(train["date"].max()),
                      "n_train_ticks": int(len(train)), "n_train_games": int(train["game"].nunique()),
                      "n_test_ticks": int(len(test)), "n_test_games": int(test["game"].nunique()),
                      "w_by_cell": w_by_cell})
    return (pd.concat(scored, ignore_index=True) if scored else frame.iloc[0:0].copy()), folds


def _dm(diff: np.ndarray, games: pd.Series) -> Dict[str, Any]:
    if games.nunique() < 2:
        return {"stat": None, "p_value": None, "ci95": None, "n_clusters": int(games.nunique())}
    r = diebold_mariano([float(v) for v in diff], games.astype(str).tolist())
    return {"stat": float(r.dm_stat), "p_value": float(r.p_value),
            "ci95": [float(r.ci95[0]), float(r.ci95[1])], "n_clusters": int(r.n_clusters)}


def _p(sub: pd.DataFrame, arm: str) -> np.ndarray:
    return sub["market"].to_numpy(dtype=float) if arm == "market" else sub["p_" + arm].to_numpy(dtype=float)


def score_cell(sub: pd.DataFrame) -> Dict[str, Any]:
    """Tick-weighted Brier / ECE of every arm on one slice, with game-clustered DM CIs."""
    if sub.empty:
        return {"n": 0}
    y = sub["y"].to_numpy(dtype=float)
    loss = {a: (_p(sub, a) - y) ** 2 for a in ARMS}
    row: Dict[str, Any] = {
        "n": int(len(sub)), "n_games": int(sub["game"].nunique()),
        "brier": {a: float(v.mean()) for a, v in loss.items()},
        "ece": {a: float(ece(_p(sub, a), y)) for a in ARMS},
        "improvement": {}, "dm": {},
    }
    for a in ("market", "recal", "cellrecal"):
        d = loss[a] - loss["candidate"]          # d > 0 -> the candidate lost less
        row["improvement"]["candidate_vs_" + a] = float(d.mean())
        row["dm"]["candidate_vs_" + a] = _dm(d, sub["game"])
    ess = effective_sample_size(
        sub.assign(loss_differential=loss["market"] - loss["candidate"]),
        game_column="game", loss_column="loss_differential")
    row["icc_by_game"], row["design_effect"], row["n_eff"] = ess["rho"], ess["design_effect"], ess["n_eff"]
    _, inf = flag_ticks(sub.sort_values(["game", "ts"], kind="mergesort"), game_col="game",
                        ts_col="ts", market_col="market", model_col="model")
    row["n_informative"] = int(inf["n_informative"])
    row["w_c_mean"] = float(sub["w_c"].mean())
    return row


def summarize(scored: pd.DataFrame, folds: List[dict], n_all: int, n_games_all: int) -> Dict[str, Any]:
    target = score_cell(scored[target_mask(scored)])
    ci = (target.get("dm", {}).get("candidate_vs_market", {}) or {}).get("ci95")
    cleared = bool(target.get("n")
                   and target["improvement"]["candidate_vs_market"] >= IMPROVEMENT_BAR
                   and ci is not None and ci[0] > 0.0
                   and target["improvement"]["candidate_vs_cellrecal"] > 0.0)
    w_table = {str(f["fold"]): f.get("w_by_cell", {}) for f in folds if f["status"] == "OK"}
    cells = sorted({c for w in w_table.values() for c in w})
    spread = {c: {"min": min(w.get(c, 0.0) for w in w_table.values()),
                  "max": max(w.get(c, 0.0) for w in w_table.values()),
                  "mean": float(np.mean([w.get(c, 0.0) for w in w_table.values()]))} for c in cells}
    return {
        "spec_id": "scripts.platformkit.eval_gate.s94_nba_early_shrinkage:nba_phase_shrinkage_v1",
        "sport": "nba", "tier": "SCREEN (uncharged, no prereg seal, no K read, no ledger write)",
        "label": "SINGLE-WINDOW", "edge_claimed": False,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {"path": str(S86_CSV), "side": "S86 SCREEN only (verdict side never read)",
                   "n_ticks": n_all, "n_games": n_games_all},
        "candidate": "p = sigmoid((1 - w_c) * logit(market) + w_c * logit(prior_state)); "
                     "prior_state = S86 price_checkpoint over the as-of Elo prior",
        "nulls": {"recal": "global logistic [1, logit(market)] on the identical train rows",
                  "cellrecal": "per-cell logistic [1, logit(market)] on the identical train rows"},
        "design": {"folds": N_FOLDS, "embargo_days": EMBARGO_DAYS, "purge": "by game",
                   "order": "game-first date", "w_grid_step": 0.005,
                   "min_cell_train_ticks": MIN_CELL_TRAIN,
                   "fit_on": "TRAIN folds only (w_c and both recalibrations)"},
        "improvement_bar": IMPROVEMENT_BAR,
        "target_cell": "P1-P2 | close_le5 | rem_gt12",
        "n_scored_ticks": int(len(scored)), "n_scored_games": int(scored["game"].nunique()),
        "overall": score_cell(scored), "target": target,
        "by_cell": {str(c): score_cell(sub) for c, sub in scored.groupby("cell", sort=True)},
        "w_by_fold": w_table, "w_spread_across_folds": spread, "folds": folds,
        "prereg_draft_warranted": cleared,
        "honest_note": "Calibration (tick-weighted Brier / ECE) only. No dollar, ROI, profit or "
                       "edge claim. A candidate that does not beat the per-cell recalibration "
                       "null is recalibration, not shrinkage.",
    }


def run(out_dir: Path = OUT_DIR, stem: str = STEM,
        frame: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    df = load_screen() if frame is None else frame
    scored, folds = walk_forward(df)
    summary = summarize(scored, folds, int(len(df)), int(df["game"].nunique()))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    series = scored[["game", "game_date", "ts", "fold", "cell", "y", "market", "model",
                     "w_c", "p_recal", "p_cellrecal", "p_candidate"]].copy()
    for name, col in (("loss_market", "market"), ("loss_recal", "p_recal"),
                      ("loss_cellrecal", "p_cellrecal"), ("loss_candidate", "p_candidate")):
        series[name] = (series[col].to_numpy(dtype=float) - series["y"].to_numpy(dtype=float)) ** 2
    series["d_candidate_vs_market"] = series["loss_market"] - series["loss_candidate"]
    series["d_candidate_vs_cellrecal"] = series["loss_cellrecal"] - series["loss_candidate"]
    series["cluster_id"] = series["game"]
    csv_path = Path(out_dir) / (stem + ".csv")
    series.to_csv(csv_path, index=False, encoding="ascii")
    summary["per_tick_csv"] = str(csv_path)                      # Q9: the paired-loss series
    (Path(out_dir) / (stem + ".json")).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    s = run()
    for name in ("overall", "target"):
        r = s[name]
        print("%-7s n %6d games %4d inf %6d n_eff %8.1f | market %.6f recal %.6f cellrecal %.6f "
              "cand %.6f" % (name.upper(), r["n"], r["n_games"], r["n_informative"], r["n_eff"],
                             r["brier"]["market"], r["brier"]["recal"], r["brier"]["cellrecal"],
                             r["brier"]["candidate"]))
        for a in ("market", "recal", "cellrecal"):
            print("         vs %-9s impr %+.6f ci %s" % (a, r["improvement"]["candidate_vs_" + a],
                                                         r["dm"]["candidate_vs_" + a]["ci95"]))
    print("w spread across folds (target cells):")
    for c in ("P1|close_le5|rem_gt12", "P2|close_le5|rem_gt12"):
        if c in s["w_spread_across_folds"]:
            print("  %-24s %s" % (c, s["w_spread_across_folds"][c]))
    print("prereg_draft_warranted %s (bar %+.4f)" % (s["prereg_draft_warranted"], s["improvement_bar"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
