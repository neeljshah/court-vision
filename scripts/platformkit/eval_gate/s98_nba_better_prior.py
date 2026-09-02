"""scripts.platformkit.eval_gate.s98_nba_better_prior -- S98: a better as-of pregame prior and
a state-dependent margin sigma for the NBA in-play tick surface.

S86/S94/S96/S97 all priced the as-of prior as ONE Elo number p0 through price_checkpoint(p0,
home, away, period, clock, margin_sigma=13.5); it trails the line pooled (-0.004857) while
matching in 16/27 cells, so the MODEL sensor is the crude half. STEP 0 measured (memo): the gate
corpus has NO p_model column, its `p_base` and `p_elo` are byte-identical to each other and to
walk_forward_elo(games).p_home_elo -- the SAME Elo family as the S86 p0 -- and it is BEHIND that
p0 at the first tick, so the candidate is scored honestly rather than dropped. Pricing is
vectorised (`price_vec`, asserted to reproduce the scalar price_checkpoint on an evenly spaced
sample) and row-wise, so `assert_no_future_read` re-prices each game's first ticks with every
later tick withheld. Sigma is fit per phase cell on TRAIN folds only, the blend weight is one
global w on TRAIN; expanding walk-forward by game-first date, purged by game, 1-day embargo, 5
folds, SCREEN side only. A SCREEN is a NON-FINDING: no prereg seal, no ledger charge, no K read,
no ledger write. SINGLE-WINDOW. ASCII only.
Test: python -m pytest tests/platformkit/ingame/test_s98_nba_better_prior.py -q
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.special import erf, ndtri

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate import s94_nba_early_shrinkage as s94
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size
from scripts.platformkit.ingame.nba_checkpoint_benchmark import price_checkpoint

REPO = Path(__file__).resolve().parents[3]
S86_CSV = REPO / "data" / "cache" / "eval_gate" / "s86_nba_every_tick_2026-09-03.csv"
CHECKPOINTS = REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
GAMES = REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
GATE_CORPUS = REPO / "data" / "cache" / "combo" / "gate_corpus_nba.parquet"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s98_nba_better_prior_2026-09-03"
IMPROVEMENT_BAR = s94.IMPROVEMENT_BAR       # the row's bar, defined once; NEVER lowered (Q3)
MIN_CELL_TRAIN, N_FOLDS, EMBARGO_DAYS = s94.MIN_CELL_TRAIN, s94.N_FOLDS, s94.EMBARGO_DAYS
SIGMA_GRID = np.round(np.arange(6.0, 24.0 + 1e-9, 0.5), 4)
SIGMA_DEFAULT, FULL_MINUTES, OT_MINUTES = 13.5, 48.0, 5.0   # the NBARepricer defaults
PRIOR_COLS = {"elo": "p0_asof", "cand": "p0_cand"}     # the two as-of pregame priors
ARMS = ("elo", "elo_sig", "cand", "cand_sig", "blend", "recal")
ARM_DOC = {"elo/cand": "price_checkpoint(p0_asof | walk_forward_elo p_home_elo, state, 13.5); "
                       "*_sig = the same prior, margin_sigma fit per cell on TRAIN folds",
           "blend": "sigmoid((1-w) logit(market) + w logit(best TRAIN arm)), one global w; "
                    "recal = the S94 global logistic [1, logit(market)] NULL"}
COLS = ["game_id", "game_date", "ts", "period", "game_clock_s", "score_home", "score_away",
        "margin", "elapsed", "period_bucket", "margin_bucket", "rem_bucket", "p0_asof",
        "model", "market", "y"]

def price_vec(p0, margin, elapsed, sigma) -> np.ndarray:
    """Vectorised NBARepricer win_home, the closed form price_checkpoint evaluates row-wise:
    Normal(margin + sigma*Phi^-1(p0)*rem, (sigma*sqrt(rem))^2), buzzer surface at rem <= 0."""
    p = np.clip(np.asarray(p0, dtype=float), 1e-6, 1.0 - 1e-6)
    m, e, s = (np.asarray(margin, float), np.asarray(elapsed, float), np.asarray(sigma, float))
    rem = np.maximum(0.0, np.where(e <= FULL_MINUTES, FULL_MINUTES - e, OT_MINUTES
                                   - np.mod(e - FULL_MINUTES, OT_MINUTES)) / FULL_MINUTES)
    live = 0.5 * (1.0 + erf((m + s * ndtri(p) * rem)
                            / np.maximum(1e-6, s * np.sqrt(rem)) / np.sqrt(2.0)))
    return np.where(rem <= 0.0, np.where(m > 0, 1.0, np.where(m == 0, 0.5, 0.0)), live)

def assert_reproduces_scalar(frame: pd.DataFrame, n: int = 2000) -> Dict[str, Any]:
    """price_vec must reproduce the scalar price_checkpoint on an EVENLY spaced sample (A3/B7)."""
    sub = frame.iloc[np.unique(np.linspace(0, len(frame) - 1, min(n, len(frame))).astype(int))]
    scalar = [price_checkpoint(r.p0_asof, r.score_home, r.score_away, int(r.period),
                               r.game_clock_s, SIGMA_DEFAULT) for r in sub.itertuples()]
    vec = price_vec(sub["p0_asof"], sub["margin"], sub["elapsed"], SIGMA_DEFAULT)
    delta = float(np.max(np.abs(vec - np.array(scalar))))
    assert delta <= 1e-12, "price_vec != price_checkpoint (%.3g)" % delta   # 1 ulp, not a rule
    return {"n_sampled": int(len(sub)), "max_abs_delta_vs_price_checkpoint": delta}

def assert_no_future_read(frame: pd.DataFrame, prior_col: str, keep: int = 4) -> Dict[str, Any]:
    """THE guard, two parts: the prior must be CONSTANT within a game (a within-game-varying
    "prior" is carrying tick-time information -- the classic planted leak), and re-pricing each
    game's first `keep` ticks with every LATER tick withheld must reproduce the price exactly."""
    values = int(frame.groupby("game")[prior_col].nunique().max())
    assert values == 1, "%s takes %d values inside one game -- not a pregame prior" % (
        prior_col, values)
    full = price_vec(frame[prior_col], frame["margin"], frame["elapsed"], SIGMA_DEFAULT)
    pos = frame.reset_index(drop=True).groupby("game", sort=False).head(keep).index.to_numpy()
    prefix = frame.iloc[pos]
    redone = price_vec(prefix[prior_col], prefix["margin"], prefix["elapsed"], SIGMA_DEFAULT)
    delta = float(np.max(np.abs(redone - full[pos]))) if len(pos) else 0.0
    assert delta == 0.0, "truncation moved %d prices (%.3g)" % (len(pos), delta)
    return {"n_ticks_repriced": int(len(pos)), "max_abs_delta": delta, "ticks_withheld": keep,
            "max_prior_values_per_game": values}

def candidate_prior() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """The one other as-of pregame probability on disk: walk_forward_elo p_home_elo, bridged by
    the incumbent's own crosswalk, with the gate-corpus identity check."""
    from domains.basketball_nba.adapter import _season_to_int
    from domains.basketball_nba.ratings import walk_forward_elo
    from scripts.platformkit.ingame.nba_mechanism_ladder import build_crosswalk
    games = pd.read_parquet(GAMES)
    games["season"] = games["season"].apply(_season_to_int)
    wf = walk_forward_elo(games)[["game_id", "p_home_elo"]].copy()
    wf["game_id"] = wf["game_id"].astype(str)
    gate = pd.read_parquet(GATE_CORPUS)
    gate["event_id"] = gate["event_id"].astype(str)
    chk = gate.merge(wf, left_on="event_id", right_on="game_id", how="inner")
    same = {"n_gate_rows": int(len(gate)), "n_matched_to_walk_forward_elo": int(len(chk)),
            "gate_columns": sorted(gate.columns), "has_p_model_column": bool("p_model" in gate),
            "max_abs_p_base_minus_p_elo": float((gate["p_base"] - gate["p_elo"]).abs().max()),
            "max_abs_p_base_minus_wf_elo": float((chk["p_base"] - chk["p_home_elo"]).abs().max())}
    cw = build_crosswalk(pd.read_parquet(
        CHECKPOINTS, columns=["game_id", "game_date", "market_ticker", "outcome_home_win"]))
    cw["nba_game_id"] = cw["nba_game_id"].astype(str)
    bridge = cw.merge(wf.rename(columns={"game_id": "nba_game_id", "p_home_elo": "p0_cand"}),
                      on="nba_game_id", how="left").dropna(subset=["p0_cand"])
    bridge["game"] = bridge["game_id"].astype(str)
    return bridge[["game", "nba_game_id", "p0_cand"]], same

def load_screen(path: Path = S86_CSV) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """S86 SCREEN ticks joined to the candidate prior; only bridged games are scored."""
    raw = pd.read_csv(path, usecols=COLS)
    raw["game"] = raw["game_id"].astype(str)   # the cluster unit everywhere below
    raw["date"] = raw["game"].map(raw.groupby("game")["game_date"].min())
    raw["cell"] = raw["period_bucket"] + "|" + raw["margin_bucket"] + "|" + raw["rem_bucket"]
    assert (raw["margin"] == raw["score_home"] - raw["score_away"]).all(), "margin != score diff"
    bridge, same = candidate_prior()
    out = raw.merge(bridge, on="game", how="left")
    cover = {"n_screen_ticks": int(len(raw)), "n_screen_games": int(raw["game"].nunique()),
             "n_bridged_games": int(out.loc[out["p0_cand"].notna(), "game"].nunique()),
             "n_bridged_ticks": int(out["p0_cand"].notna().sum()), "gate_corpus_identity": same}
    out = out[out["p0_cand"].notna()].sort_values(["date", "game", "ts"], kind="stable")
    return out.reset_index(drop=True), cover

def first_tick_table(frame: pd.DataFrame) -> Dict[str, Any]:
    """STEP 0: Brier of each as-of prior vs the first traded price, at each game's first tick."""
    first = frame.groupby("game", sort=False).head(1)
    y = first["y"].to_numpy(dtype=float)
    cand = {"elo_p0_asof": first["p0_asof"], "candidate_walk_forward_elo": first["p0_cand"],
            "elo_state_priced_first_tick": first["model"], "market_first_traded": first["market"]}
    out = {k: float(np.mean((np.asarray(v, dtype=float) - y) ** 2)) for k, v in cand.items()}
    d = np.abs(first["p0_asof"].to_numpy(float) - first["p0_cand"].to_numpy(float))
    return {"n_games": int(len(first)), "brier": out, "prior_gap_mean_abs": float(d.mean()),
            "prior_gap_max_abs": float(d.max()), "candidate_beats_elo_p0":
                bool(out["candidate_walk_forward_elo"] < out["elo_p0_asof"])}

def fit_sigma(train: pd.DataFrame, prior_col: str) -> Dict[str, float]:
    """margin_sigma per phase cell on TRAIN rows only: the grid point minimising Brier."""
    out: Dict[str, float] = {}
    for cell, sub in train.groupby("cell", sort=True):
        if len(sub) < MIN_CELL_TRAIN or sub["y"].nunique() < 2:
            out[cell] = SIGMA_DEFAULT
            continue
        p0, m, e = sub[prior_col].to_numpy(), sub["margin"].to_numpy(), sub["elapsed"].to_numpy()
        y = sub["y"].to_numpy(dtype=float)
        losses = [float(np.mean((price_vec(p0, m, e, s) - y) ** 2)) for s in SIGMA_GRID]
        out[cell] = float(SIGMA_GRID[int(np.argmin(losses))])
    return out

def add_arms(frame: pd.DataFrame, sigmas: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """Both priced priors, at the default sigma and at the TRAIN-fitted per-cell sigma."""
    out = frame.copy()
    for name, col in PRIOR_COLS.items():
        cs = out["cell"].map(sigmas[name]).fillna(SIGMA_DEFAULT).to_numpy(dtype=float)
        out["sigma_" + name] = cs
        out["p_" + name] = price_vec(out[col], out["margin"], out["elapsed"], SIGMA_DEFAULT)
        out["p_" + name + "_sig"] = price_vec(out[col], out["margin"], out["elapsed"], cs)
    return out

def apply_fold(train: pd.DataFrame, test: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Fit sigma per cell, one global blend weight and the recalibration null on TRAIN."""
    sigmas = {name: fit_sigma(train, col) for name, col in PRIOR_COLS.items()}
    out, tr = add_arms(test, sigmas), add_arms(train, sigmas)
    ytr = tr["y"].to_numpy(dtype=float)
    tb = {a: float(np.mean((tr["p_" + a].to_numpy() - ytr) ** 2)) for a in ARMS[:4]}
    base = min(tb, key=tb.get)                                   # TRAIN-only arm selection
    lm_tr, gap = s94.logit(tr["market"]), s94.logit(tr["p_" + base]) - s94.logit(tr["market"])
    w = float(s94.W_GRID[int(np.argmin([float(np.mean((s94.sigmoid(lm_tr + g * gap) - ytr) ** 2))
                                        for g in s94.W_GRID]))])
    lm = s94.logit(out["market"])
    out["p_blend"] = s94.sigmoid(lm + w * (s94.logit(out["p_" + base]) - lm))
    recal = s94._recal(tr.assign(logit_market=lm_tr))       # the S94 null, fit on TRAIN
    out["p_recal"] = recal.predict_proba(lm.reshape(-1, 1))[:, 1]
    out["blend_base_arm"], out["blend_w"] = base, w
    return out, dict({"sigma_" + k: v for k, v in sigmas.items()}, train_brier_by_arm=tb,
                     blend_base_arm=base, blend_w=w)

def walk_forward(frame: pd.DataFrame) -> Tuple[pd.DataFrame, List[dict]]:
    """Expanding walk-forward by game-first date; train purged by game and embargoed 1 day."""
    scored: List[pd.DataFrame] = []
    folds: List[dict] = []  # one row per fold: windows, fitted sigma, w, TRAIN Brier by arm
    for k, block in enumerate(s94.fold_dates(frame, N_FOLDS)[1:], start=1):
        day0 = min(block)
        cut = str(dt.date.fromisoformat(str(day0)) - dt.timedelta(days=int(EMBARGO_DAYS)))
        train, test = frame[frame["date"] < cut], frame[frame["date"].isin(set(block))]
        if train.empty or train["y"].nunique() < 2 or test.empty:
            folds.append({"fold": k, "status": "INSUFFICIENT", "n_train": int(len(train))})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= day0, "embargo/ordering violated"
        block_out, rec = apply_fold(train, test)
        block_out["fold"] = k
        scored.append(block_out)
        folds.append(dict(fold=k, status="OK", test_start=str(day0), test_end=str(max(block)),
                          embargo_cut=cut, train_date_max=str(train["date"].max()),
                          n_train_ticks=int(len(train)), n_test_ticks=int(len(test)),
                          n_train_games=int(train["game"].nunique()),
                          n_test_games=int(test["game"].nunique()), **rec))
    return (pd.concat(scored, ignore_index=True) if scored else frame.iloc[0:0].copy()), folds

def score_cell(sub: pd.DataFrame) -> Dict[str, Any]:
    """Tick-weighted Brier of every arm vs the RAW market, with game-clustered DM CIs."""
    if sub.empty:
        return {"n": 0}
    y = sub["y"].to_numpy(dtype=float)
    loss = {a: (sub["p_" + a].to_numpy(dtype=float) - y) ** 2 for a in ARMS}
    loss["market"] = (sub["market"].to_numpy(dtype=float) - y) ** 2
    row: Dict[str, Any] = {"n": int(len(sub)), "n_games": int(sub["game"].nunique()),
                           "improvement_vs_market": {}, "dm_ci95": {},
                           "brier": {a: float(v.mean()) for a, v in loss.items()}}
    games = sub["game"].astype(str).tolist()
    for a in ARMS:
        d = loss["market"] - loss[a]                 # d > 0 -> the arm lost less than the line
        row["improvement_vs_market"][a] = float(d.mean())
        dm = diebold_mariano([float(v) for v in d], games) if row["n_games"] >= 2 else None
        row["dm_ci95"][a] = [float(dm.ci95[0]), float(dm.ci95[1])] if dm else None
    head = sub.assign(loss_differential=loss["market"] - loss["cand_sig"])
    ess = effective_sample_size(head, game_column="game", loss_column="loss_differential")
    row.update(icc_by_game=ess["rho"], design_effect=ess["design_effect"], n_eff=ess["n_eff"])
    attach_informative_summary(row, head, "loss_differential", game_col="game", ts_col="ts",
                               market_col="market", model_col="p_cand_sig")
    return row

def clears(row: Dict[str, Any], arm: str) -> bool:
    """Bar (never lowered, Q3): +0.004 vs the RAW market, CI excluding 0, Brier under recal."""
    ci = row["dm_ci95"].get(arm)
    return bool(row["improvement_vs_market"][arm] >= IMPROVEMENT_BAR and ci and ci[0] > 0.0
                and row["brier"][arm] < row["brier"]["recal"])

def summarize(scored: pd.DataFrame, folds: List[dict], cover: Dict[str, Any],
              first: Dict[str, Any], repro: dict, guard: dict) -> Dict[str, Any]:
    overall = score_cell(scored)
    best = max(ARMS, key=lambda a: overall["improvement_vs_market"][a]) if overall["n"] else None
    by_cell = {str(c): score_cell(s) for c, s in scored.groupby("cell", sort=True)}
    cells = sorted(c for c, r in by_cell.items() if r.get("n") and any(clears(r, a) for a in ARMS))
    return {
        "spec_id": "scripts.platformkit.eval_gate.s98_nba_better_prior:nba_better_prior_sigma_v1",
        "sport": "nba", "tier": "SCREEN (uncharged, no prereg seal, no K read, no ledger write)",
        "label": "SINGLE-WINDOW", "edge_claimed": False,
        "source": {"path": str(S86_CSV), "side": "S86 SCREEN only (verdict side never read)",
                   "generated_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        "coverage": cover, "first_tick": first, "price_vec_reproduction": repro, "arms": ARM_DOC,
        "asof_guard": guard, "improvement_bar": IMPROVEMENT_BAR,
        "design": {"folds": N_FOLDS, "embargo_days": EMBARGO_DAYS, "purge": "by game",
                   "order": "game-first date", "min_cell_train_ticks": MIN_CELL_TRAIN,
                   "sigma_grid": [6.0, 24.0, 0.5], "fit_on": "TRAIN folds only"},
        "n_scored_ticks": int(len(scored)), "n_scored_games": int(scored["game"].nunique()),
        "overall": overall, "by_cell": by_cell, "folds": folds, "best_arm_overall": best,
        "cells_clearing_bar": cells, "honest_note": "Calibration (tick-weighted Brier) only; a "
        "prior that does not beat the raw line is an honest BEHIND.",
        "prereg_draft_warranted": bool(cells or (best and clears(overall, best))),
    }

def run(out_dir: Path = OUT_DIR, stem: str = STEM,
        frame: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    cover: Dict[str, Any] = {"gate_corpus_identity": "INJECTED FRAME"}
    if frame is None:
        frame, cover = load_screen()
    repro = assert_reproduces_scalar(frame)
    guard = {name: assert_no_future_read(frame, col) for name, col in PRIOR_COLS.items()}
    scored, folds = walk_forward(frame)
    summary = summarize(scored, folds, cover, first_tick_table(frame), repro, guard)
    series = scored[["game", "game_date", "ts", "fold", "cell", "y", "market", "p0_asof",
                     "p0_cand", "sigma_elo", "sigma_cand", "blend_base_arm", "blend_w"]
                    + ["p_" + a for a in ARMS]].copy()
    y = series["y"].to_numpy(dtype=float)  # Q9: both losses + the differential, per arm
    series["loss_market"] = (series["market"].to_numpy(dtype=float) - y) ** 2
    for a in ARMS:
        series["loss_" + a] = (series["p_" + a].to_numpy(dtype=float) - y) ** 2
        series["d_" + a + "_vs_market"] = series["loss_market"] - series["loss_" + a]
    series["cluster_id"] = series["game"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    series.to_csv(csv_path := Path(out_dir) / (stem + ".csv"), index=False, encoding="ascii")
    summary["per_tick_csv"] = str(csv_path)                       # Q9: the paired-loss series
    (Path(out_dir) / (stem + ".json")).write_text(json.dumps(
        summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary

def main() -> int:
    s = run()
    o = s["overall"]
    print("OVERALL n %d games %d inf %d n_eff %.1f market %.6f" % (o["n"], o["n_games"],
          o["tick_informative"]["n_informative"], o["n_eff"], o["brier"]["market"]))
    for a in ARMS:
        print("  %-9s brier %.6f impr %+.6f ci %s" % (a, o["brier"][a],
              o["improvement_vs_market"][a], o["dm_ci95"][a]))
    print("cells clearing %s | prereg_draft %s (bar %+.4f)" % (s["cells_clearing_bar"],
          s["prereg_draft_warranted"], s["improvement_bar"]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
