"""scripts.platformkit.eval_gate.s99_cross_market -- S99: ONE GAME, ALL ITS IN-PLAY MARKETS.

THE GAP (HARNESS_GAPS S99; premises L14 + L20)
----------------------------------------------
`event_key` in data/cache/inplay_odds/*_price_series.parquet is MARKET-TYPE-SPECIFIC
(KXMLBGAME-... vs KXMLBTOTAL-...), so zero events carry two markets. Stripping the series
prefix re-keys them onto one game: 99 MLB games with moneyline + total, 96 soccer_intl
games with moneyline + spread + team_total. This module builds that re-keyed VIEW (it
never rewrites a store), prices a rest-of-game score DISTRIBUTION at each tick from the
as-of on-disk state, and scores it against BOTH markets on the SCREEN side.

THE MODEL (deliberately simple, and stated)
-------------------------------------------
MLB: runs in each remaining half-inning ~ Poisson at the batting team's as-of runs/inning
rate (games_current.parquet, strictly before the game date). Sums of independent Poissons
are Poisson, so the rest-of-game total is analytic -- no simulation. Home-win probability
is the Skellam tail of (home rest - away rest) against the current margin; an exact tie
goes to extras and is scored 0.5 (ponytail: no extra-innings model, and the home team's
skipped bottom of the 9th is not modelled -- both inflate rest-of-game variance slightly).
soccer_intl: goals per remaining minute ~ Poisson at the team's as-of goals/match rate over
prior internationals (results.parquet, strictly before). A draw loses the home moneyline.

A SCREEN IS A NON-FINDING. No prereg seal, no ledger row, no K read, no charge. Nothing is
FIT on the scored rows -- the only parameters are as-of rates computed strictly before each
game's date -- so there is no train fold to purge; the leak contract IS that strictly-before
guard, asserted in the per-file test. Calibration language only; ASCII only.

Per-file test: python -m pytest tests/platformkit/ingame/test_s99_cross_market.py -q
Run:           python -m scripts.platformkit.eval_gate.s99_cross_market
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from scipy.stats import poisson, skellam

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.s99_corpus import (STATE_TOLERANCE_S, build_mlb,
                                                     build_soccer, game_key_view)
from scripts.platformkit.foundry.tiers import partition_corpus

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
KEYS_PARQUET = OUT_DIR / "s99_game_keys.parquet"
STEM = "s99_cross_market_2026-09-03"

BAR = 0.004               # the standing in-game Brier bar; never moved (Q3)
SEED = 0                  # partition seed, frozen (matches S82)
MIN_GAMES = 30            # the row's own premise floor
CONSISTENCY_CAP = 20000   # evenly-spaced subsample cap for the L-solve (A3: never a head slice)
L_GRID = np.exp(np.linspace(np.log(0.01), np.log(30.0), 40))

# ---------------------------------------------------------------- the distribution
def p_total_at_least(cur: np.ndarray, lam: np.ndarray, strike: np.ndarray) -> np.ndarray:
    """P(final total >= strike): the Kalshi settlement rule, verified 1.000 on 917 settled
    (game, strike) pairs against data/domains/mlb/games_current.parquet."""
    need = np.asarray(strike, dtype=float) - np.asarray(cur, dtype=float)
    return np.where(need <= 0, 1.0, poisson.sf(np.ceil(need) - 1.0, np.maximum(lam, 1e-9)))


def p_home_win(cur_h, cur_a, lam_h, lam_a, tie_weight: float) -> np.ndarray:
    """Skellam tail of (home rest - away rest) against the current margin."""
    margin = np.asarray(cur_a, dtype=float) - np.asarray(cur_h, dtype=float)
    lam_h, lam_a = np.maximum(lam_h, 1e-9), np.maximum(lam_a, 1e-9)
    return skellam.sf(margin, lam_h, lam_a) + tie_weight * skellam.pmf(margin, lam_h, lam_a)


def crps_total(cur: np.ndarray, lam: np.ndarray, y: np.ndarray, kmax: int) -> np.ndarray:
    """Discrete CRPS of the final-total distribution against the realized total."""
    acc = np.zeros(len(cur), dtype=float)
    for k in range(kmax + 1):
        cdf = poisson.cdf(np.maximum(k - cur, -1.0), np.maximum(lam, 1e-9))
        acc += (cdf - (y <= k).astype(float)) ** 2
    return acc


# ---------------------------------------------------------------- scoring
def screen_side(rows: pd.DataFrame, seed: int = SEED):
    """S82's game-first-date ISO-week partition over the scored games."""
    states = [{"game_id": g, "state_ts": "%sT12:00:00" % d}
              for g, d in sorted(rows.groupby("game")["game_date"].min().items())]
    part = partition_corpus(states, seed=seed)
    return rows[rows["game"].isin(part.screen_ids)].reset_index(drop=True), part


def consistency(rows: pd.DataFrame, tie_weight: float,
                cap: int = CONSISTENCY_CAP) -> Dict[str, Any]:
    """(d) Is the MARKET internally consistent? Hold the as-of team SPLIT fixed, solve the
    rest-of-game scoring volume L that reproduces the market's own moneyline, then read that
    distribution's total probability off and compare it to the market's own total price."""
    both = rows[rows["market"] != "moneyline"].dropna(subset=["ml_price"])
    if not len(both):
        return {"n_ticks": 0}
    step = max(1, len(both) // cap)
    sub = both.iloc[::step].reset_index(drop=True)   # evenly spaced, never a head slice (A3)
    split = (sub["lam_h"] / np.maximum(sub["lam_h"] + sub["lam_a"], 1e-9)).to_numpy()
    best_err, best_l = np.full(len(sub), np.inf), np.zeros(len(sub))
    for scale in L_GRID:
        p = p_home_win(sub["cur_h"], sub["cur_a"], split * scale, (1.0 - split) * scale, tie_weight)
        take = np.abs(p - sub["ml_price"].to_numpy()) < best_err
        best_err = np.where(take, np.abs(p - sub["ml_price"].to_numpy()), best_err)
        best_l = np.where(take, scale, best_l)
    per_team = "cur_team" in sub.columns
    cur = sub["cur_team"].to_numpy() if per_team else (sub["cur_h"] + sub["cur_a"]).to_numpy()
    lam = best_l * (split if per_team else 1.0)
    implied = p_total_at_least(cur, lam, sub["strike"].to_numpy())
    sub = sub.assign(inconsistency=np.abs(implied - sub["price"].to_numpy()),
                     identified=best_err <= 0.02)
    by_phase = (sub.groupby("phase")["inconsistency"].agg(["mean", "size"]))
    return {"n_ticks": int(len(sub)), "subsample_step": int(step),
            "share_moneyline_identified": float(sub["identified"].mean()),
            "mean_abs_inconsistency": float(sub["inconsistency"].mean()),
            "by_phase": {str(k): {"mean_abs_inconsistency": float(v["mean"]), "n": int(v["size"])}
                         for k, v in by_phase.iterrows()}}


def price_rows(rows: pd.DataFrame, meta: Dict[str, Any]) -> pd.DataFrame:
    """Attach the model probability and BOTH paired losses to every tick (Q9: the differential
    is archived beside the summary, and its as-of state travels with it)."""
    ml = rows["market"] == "moneyline"
    per_team = "cur_team" in rows.columns
    cur = rows["cur_team"] if per_team else rows["cur_h"] + rows["cur_a"]
    lam = rows["lam_team"] if per_team else rows["lam_h"] + rows["lam_a"]
    model = np.where(ml,
                     p_home_win(rows["cur_h"], rows["cur_a"], rows["lam_h"], rows["lam_a"],
                                meta["tie_weight"]),
                     p_total_at_least(cur.to_numpy(), lam.to_numpy(),
                                      rows["strike"].fillna(0.0).to_numpy()))
    y = rows["y"].to_numpy()
    ml_price = (rows[ml].drop_duplicates(["game", "ts"]).set_index(["game", "ts"])["price"])
    return rows.assign(p_model=model, loss_model=(model - y) ** 2,
                       loss_market=(rows["price"].to_numpy() - y) ** 2,
                       ml_price=rows.join(ml_price.rename("_p"), on=["game", "ts"])["_p"])


def paired(sub: pd.DataFrame) -> Dict[str, Any]:
    """Brier of each side plus the game-clustered CI on (market loss - model loss)."""
    lm, lk = sub["loss_model"].to_numpy(), sub["loss_market"].to_numpy()
    res = diebold_mariano((lk - lm).tolist(), [str(g) for g in sub["game"]])
    return {"n_ticks": int(len(sub)), "n_games": int(res.n_clusters),
            "brier_model": float(lm.mean()), "brier_market": float(lk.mean()),
            "delta_market_minus_model": float(res.mean_diff),
            "ci95": [float(res.ci95[0]), float(res.ci95[1])], "dm_p_raw": float(res.p_value)}


def score_sport(rows: pd.DataFrame, meta: Dict[str, Any]) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Everything the S99 bar asks for, on the SCREEN side only."""
    rows = price_rows(rows, meta)
    side, part = screen_side(rows)
    rows = rows.assign(partition_side=np.where(rows["game"].isin(part.screen_ids),
                                               "screen", "verdict"))
    out: Dict[str, Any] = {
        "partition": {"basis": part.basis, "seed": SEED, "screen_sha256": part.screen_sha256,
                      "verdict_sha256": part.verdict_sha256,
                      "n_screen_games": len(part.screen_ids),
                      "n_verdict_games": len(part.verdict_ids)},
        "corpus": dict(meta, n_games_with_ticks=int(rows["game"].nunique()),
                       n_screen_ticks=int(len(side)),
                       n_screen_games=int(side["game"].nunique()),
                       state_tolerance_s=STATE_TOLERANCE_S,
                       ticks_by_market={str(k): int(v) for k, v
                                        in side["market"].value_counts().items()})}
    m = side[side["market"] == "moneyline"]
    out["moneyline"] = paired(m)
    crps = crps_total((m["cur_h"] + m["cur_a"]).to_numpy(), (m["lam_h"] + m["lam_a"]).to_numpy(),
                      m["y_total"].to_numpy(), meta["crps_kmax"])
    out["crps_total"] = {"n_ticks": int(len(crps)), "n_games": int(m["game"].nunique()),
                         "mean_crps_model": float(crps.mean()),
                         "note": "model-side CRPS only; the market's strike ladder is scored as "
                                 "Brier below, not converted into a rival distribution"}
    out["total"] = paired(side[side["market"] != "moneyline"])
    out["cross_market_consistency"] = consistency(side, meta["tie_weight"])
    delta, ci = out["total"]["delta_market_minus_model"], out["total"]["ci95"]
    out["prereg_draft_warranted"] = bool(delta >= BAR and ci[0] > 0.0)
    out["bar"] = BAR
    return out, rows


def run(out_dir: Path = OUT_DIR, stem: str = STEM) -> Dict[str, Any]:
    view = game_key_view()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    view.to_parquet(KEYS_PARQUET, index=False)
    report: Dict[str, Any] = {"row": "S99", "tier": "cross-market screen",
                              "verdict": "SCREEN (a non-finding)", "bar": BAR,
                              "game_key_view": str(KEYS_PARQUET), "edge_claimed": False,
                              "premise": {}, "sports": {}}
    for sport, builder in (("mlb", build_mlb), ("soccer_intl", build_soccer)):
        block = view[view["sport"] == sport]
        multi = block[block["n_markets_on_game"] >= 2]
        report["premise"][sport] = {
            "n_kalshi_games": int(block["game_key"].nunique()),
            "n_games_ge2_markets": int(multi["game_key"].nunique()),
            "ticks_by_market": {str(k): int(v) for k, v
                                in multi.groupby("market_type")["n_ticks"].sum().items()},
            "meets_min_games": bool(multi["game_key"].nunique() >= MIN_GAMES)}
        scored, archive = score_sport(*builder())
        archive.to_csv(Path(out_dir) / ("%s_%s_series.csv" % (stem, sport)), index=False)
        report["sports"][sport] = scored
    (Path(out_dir) / (stem + ".json")).write_text(
        json.dumps(report, indent=1, sort_keys=True, default=str), encoding="ascii")
    return report


def main() -> int:
    rep = run()
    for sport, block in sorted(rep["sports"].items()):
        c = block["corpus"]
        print("%s: %d games joined, %d with ticks (%d multi-market) | SCREEN %d ticks / %d games"
              % (sport, c["n_games_joined"], c["n_games_with_ticks"],
                 c["n_multi_market_games"], c["n_screen_ticks"], c["n_screen_games"]))
        for leg in ("moneyline", "total"):
            r = block[leg]
            print("  %-9s n=%d/%dg model %.6f market %.6f delta %+.6f CI [%+.6f, %+.6f]"
                  % (leg, r["n_ticks"], r["n_games"], r["brier_model"], r["brier_market"],
                     r["delta_market_minus_model"], r["ci95"][0], r["ci95"][1]))
        print("  dropped games %s" % c["dropped"])
        print("  CRPS(total) model %.4f on %d ticks | prereg draft warranted: %s"
              % (block["crps_total"]["mean_crps_model"], block["crps_total"]["n_ticks"],
                 block["prereg_draft_warranted"]))
        k = block["cross_market_consistency"]
        print("  market self-consistency %.4f mean abs (n=%d, identified %.3f) | %s"
              % (k.get("mean_abs_inconsistency", float("nan")), k.get("n_ticks", 0),
                 k.get("share_moneyline_identified", float("nan")),
                 {p: round(v["mean_abs_inconsistency"], 4)
                  for p, v in sorted(k.get("by_phase", {}).items())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
