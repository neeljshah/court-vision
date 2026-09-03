"""S81 -- the OPEN-to-close move: the one pregame target the close cannot contain.

S108 showed the devigged close already contains every as-of feature we hold, so a screen
that targets the OUTCOME against the close is asking the market to be wrong about itself.
The OPEN-to-close move is different by construction: the opening price cannot contain the
information that arrived after it, so `logit(close) - logit(open)` is a target the close is
not allowed to see.

Target        m = logit(p_close) - logit(p_open), on the SCREEN side of the frozen partition.
Features      every S108 as-of column (name-guarded by `screen_predictor.check_feature_name`)
              PLUS logit(p_open); plus logit(p_base) where the incumbent is not the close.
Model         elastic-net LINEAR (sklearn) with the penalty chosen by an INNER expanding
              walk-forward inside each outer train window; purge + embargo via the S108 date gap.
Nulls         (1) ZERO move; (2) an AR(1)-style mean reversion, m = c (logit(pbar) - logit(open))
              with c and the base rate pbar fit on the train fold only.
Reported      out-of-fold R^2 and sign accuracy against both nulls, unit-clustered CIs on the
              paired squared-error differential, AND the calibration consequence: Brier of
              sigmoid(logit(open) + m_hat) against the OUTCOME, versus the raw open and versus
              the close (the close is the ceiling, never the thing being beaten).

Open/close sources, stated as rules:
  soccer  Pinnacle `ou_open_*` (open) and `ou_close_*` (close) on the over/under-2.5 market,
          devigged by `close_join.close_column`; `avg*` is the documented fallback.
  mlb     `mlb_price_series.parquet`, Kalshi only: the FIRST and the LAST two-sided quote
          strictly before the first-pitch clock the Kalshi ticker carries (the close_join_mlb
          rule). Polymarket has no clock and is excluded, exactly as close_join_mlb excludes it.
  nba / tennis  have NO opening price locally -- see the memo's premise table.

No charge, no seal, no ledger read or write; `data/registry/` untouched; the VERDICT side is
never built. A NULL is a success. Calibration language only.

Per-file test:
  python -m pytest tests/platformkit/eval_gate/test_s81_market_move.py -q
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet

from scripts.platformkit.eval_gate.close_join import close_column
from scripts.platformkit.eval_gate.s108_features import ROOT, build
from scripts.platformkit.eval_gate.s108_pregame_full_model import (
    INNER_FOLDS, OUTER_FOLDS, _logit, _prep, _score, _sigmoid, folds)

IMPROVEMENT_BAR = 0.004          # Q3: the register row's Brier bar, never moved
ALPHAS = (0.0003, 0.001, 0.003, 0.01, 0.03, 0.1)
L1_RATIO = 0.5
SPORTS_WITH_OPEN = ("soccer", "mlb")


class _PairSpec:
    """The two-sided-decimal shape close_column reads; no winner/loser column can reach it."""

    side_a, side_b, fallback_a, fallback_b, price_suffixes = "a", "b", "a", "b", ()


def _devig_pair(price_a: np.ndarray, price_b: np.ndarray) -> np.ndarray:
    """Fair probability of side A from a two-sided DECIMAL pair (reuses close_column/devig2)."""
    frame = pd.DataFrame({"a": np.asarray(price_a, dtype=float),
                          "b": np.asarray(price_b, dtype=float)})
    return close_column(frame, _PairSpec()).to_numpy(dtype=float)


def _soccer_open_close() -> pd.DataFrame:
    """Pinnacle open and close on the over/under market, indexed by event_id."""
    odds = pd.read_parquet(ROOT / "data" / "domains" / "soccer" / "odds.parquet")
    out = pd.DataFrame(index=pd.Index(odds["event_id"].astype(str), name="event_id"))
    for label, over, under, f_over, f_under in (
            ("p_open", "ou_open_over", "ou_open_under", "avg_over", "avg_under"),
            ("p_close", "ou_close_over", "ou_close_under", "avgc_over", "avgc_under")):
        a = odds[over].where(odds[over].notna(), odds[f_over]).to_numpy(dtype=float)
        b = odds[under].where(odds[under].notna(), odds[f_under]).to_numpy(dtype=float)
        out[label] = _devig_pair(a, b)
    return out[~out.index.duplicated(keep=False)]


def _mlb_open_close() -> pd.DataFrame:
    """First and last TRADED two-sided Kalshi quote strictly before first pitch, by event_id.

    `traded` is load-bearing, not a convenience filter: the first UNTRADED tick is the
    placeholder listing quote and sits at exactly 0.500 on 87.1% of events (measured), which
    would make `logit(open)` a constant and turn the move into the close itself -- the
    degenerate denominator B9 forbids. On traded ticks only 3.2% sit at 0.500.
    """
    from scripts.platformkit.eval_gate import close_join_mlb as cjm

    series = pd.read_parquet(cjm.SERIES_PATH)
    series = series.loc[(series["market_type"].astype(str) == "moneyline")
                        & series["traded"].astype(bool)].copy()
    series["ts_utc"] = pd.to_datetime(series["ts"], unit="s")
    kal = series.loc[series["venue"].astype(str) == "kalshi"]
    events = cjm._kalshi_events(kal, {"unparsed_ticker": 0, "unknown_team_token": 0})
    ticks = kal.merge(events[["event_key", "start_utc"]], on="event_key", how="inner")
    pre = ticks.loc[ticks["ts_utc"] < ticks["start_utc"]].sort_values("ts")
    home = events.set_index("event_key")["home"]
    seat = np.where(pre["side"].map(lambda s: cjm._spine_code(str(s))).to_numpy()
                    == pre["event_key"].map(home).to_numpy(), "prob_home", "prob_away")
    grouped = pre.assign(seat=seat).groupby(["event_key", "seat"], sort=False)
    frames = {}
    for label, part in (("p_open", grouped.head(1)), ("p_close", grouped.tail(1))):
        wide = part.pivot_table(index="event_key", columns="seat", values="prob", aggfunc="last")
        for column in ("prob_home", "prob_away"):
            if column not in wide:
                wide[column] = np.nan
        wide = wide.dropna(subset=["prob_home", "prob_away"])
        frames[label] = pd.Series(
            _devig_pair(1.0 / wide["prob_home"].to_numpy(float),
                        1.0 / wide["prob_away"].to_numpy(float)), index=wide.index, name=label)
    gap = (grouped.tail(1).groupby("event_key")["ts"].max()
           - grouped.head(1).groupby("event_key")["ts"].min()) / 3600.0
    out = pd.concat([frames["p_open"], frames["p_close"], gap.rename("open_close_hours")], axis=1)

    spine = pd.read_parquet(cjm.SPINE_PATH)
    spine["date"] = pd.to_datetime(spine["date"])
    keys = ["date", "home_team", "away_team"]
    lookup = spine.loc[~spine.duplicated(keys, keep=False), keys + ["event_id"]].rename(
        columns={"home_team": "home", "away_team": "away"})
    joined = events.merge(lookup, on=["date", "home", "away"], how="inner").set_index("event_key")
    out = out.join(joined["event_id"], how="inner").dropna(subset=["event_id"])
    out["event_id"] = out["event_id"].astype(str)
    out = out.loc[~out["event_id"].duplicated(keep=False)].set_index("event_id")
    return out.dropna(subset=["p_open", "p_close"])


OPEN_CLOSE = {"soccer": _soccer_open_close, "mlb": _mlb_open_close}


def build_move(sport: str) -> dict:
    """S108's screen-side design matrix, restricted to events carrying an open AND a close."""
    if sport not in OPEN_CLOSE:
        raise ValueError("%s carries no local opening price (see the S81 premise table)" % sport)
    bundle = build(sport)
    prices = OPEN_CLOSE[sport]().reindex(bundle["X"].index)
    keep = (np.isfinite(prices["p_open"].to_numpy(float))
            & np.isfinite(prices["p_close"].to_numpy(float)))
    if keep.sum() < 30:
        raise ValueError("%s: only %d events carry both prices" % (sport, int(keep.sum())))
    X = bundle["X"].loc[keep].copy()
    p_open = prices["p_open"].to_numpy(float)[keep]
    p_close = prices["p_close"].to_numpy(float)[keep]
    X["logit_open"] = _logit(p_open)
    if bundle["incumbent"] != "devig_close":         # the close is never a feature; a base is
        X["logit_p_base"] = _logit(bundle["p_inc"][keep])
    return {**bundle, "X": X, "p_open": p_open, "p_close": p_close,
            "m": _logit(p_close) - _logit(p_open),
            "y": bundle["y"][keep], "dates": bundle["dates"][keep],
            "units": bundle["units"][keep], "cluster_ids": bundle["cluster_ids"][keep],
            "p_inc": bundle["p_inc"][keep], "n_with_both": int(keep.sum())}


def _ar1(open_logit_tr, m_tr, open_logit_te, y_tr):
    """Mean-reversion null: m = c (logit(base rate) - logit(open)), c fit on the train fold."""
    base = _logit(np.full(1, float(np.mean(y_tr))))[0]
    pull_tr = base - open_logit_tr
    denom = float(pull_tr @ pull_tr)
    c = float(pull_tr @ m_tr) / denom if denom > 1e-12 else 0.0
    return c * (base - open_logit_te), c


def _oof(bundle: dict, k: int) -> pd.DataFrame:
    """Nested walk-forward: inner expanding folds pick the penalty, outer folds are scored."""
    X, m, dates = bundle["X"], bundle["m"], bundle["dates"]
    split = folds(dates, k)
    if len(split) < 3:
        raise ValueError("%s produced only %d outer folds" % (bundle["sport"], len(split)))
    open_logit = _logit(bundle["p_open"])
    rows = []
    for fold, (train, test) in enumerate(split):
        Ztr, Zte = _prep(X, train, test)
        inner = folds(dates[train], INNER_FOLDS)
        score = np.zeros(len(ALPHAS))
        for itr, ite in inner:
            Wtr, Wte = _prep(X.iloc[train], itr, ite)
            for j, alpha in enumerate(ALPHAS):
                fit = ElasticNet(alpha=alpha, l1_ratio=L1_RATIO, max_iter=5000).fit(
                    Wtr, m[train][itr])
                score[j] += float(np.mean((fit.predict(Wte) - m[train][ite]) ** 2))
        pick = int(np.argmin(score)) if len(inner) else len(ALPHAS) - 1
        model = ElasticNet(alpha=ALPHAS[pick], l1_ratio=L1_RATIO, max_iter=5000).fit(Ztr, m[train])
        m_ar1, c = _ar1(open_logit[train], m[train], open_logit[test], bundle["y"][train])
        rows.append(pd.DataFrame({
            "row": test, "fold": fold, "alpha": ALPHAS[pick],
            "nonzero_coefs": int(np.count_nonzero(model.coef_)), "ar1_c": c,
            "n_train": len(train), "inner_folds": len(inner),
            "m_hat_enet": model.predict(Zte), "m_hat_ar1": m_ar1}))
    return pd.concat(rows, ignore_index=True)


def _arm(m, m_hat, units, teams, base) -> dict:
    """R^2 and sign accuracy against a named null, with both clustered paired CIs.

    A one-unit corpus (mlb: `era_2022_2026`) makes the unit CI undefined, so the sport's
    DECLARED cluster key is reported beside it and is the one that binds there.
    """
    err, err0 = (m - m_hat) ** 2, (m - base) ** 2
    moved = m != 0.0
    return {"mse": float(err.mean()), "r2_vs_null": float(1.0 - err.mean() / err0.mean()),
            "sign_acc": float(np.mean(np.sign(m_hat[moved]) == np.sign(m[moved]))),
            "n_moved": int(moved.sum()), "paired_dm": _score(err0 - err, units),
            "declared_dm": _score(err0 - err, teams)}


def run_sport(sport: str, out_dir: Path, k: int = OUTER_FOLDS) -> dict:
    """Score one sport's move model and archive the per-event differential (Q9)."""
    bundle = build_move(sport)
    oof = _oof(bundle, k).sort_values("row").reset_index(drop=True)
    idx = oof["row"].to_numpy()
    m, y = bundle["m"][idx], bundle["y"][idx].astype(float)
    p_open, p_close = bundle["p_open"][idx], bundle["p_close"][idx]
    units, teams = bundle["units"][idx], bundle["cluster_ids"][idx]
    open_logit = _logit(p_open)
    p_adj = _sigmoid(open_logit + oof["m_hat_enet"].to_numpy())
    p_ar1 = _sigmoid(open_logit + oof["m_hat_ar1"].to_numpy())
    loss = {name: (p - y) ** 2 for name, p in
            (("open", p_open), ("close", p_close), ("adj", p_adj), ("ar1", p_ar1))}
    frame = pd.DataFrame({
        "event_id": bundle["X"].index.to_numpy()[idx], "event_date": bundle["dates"][idx],
        "corpus_unit": units, "cluster_id": teams,
        "fold": oof["fold"], "y": y, "p_open": p_open, "p_close": p_close,
        "m_true": m, "m_hat_enet": oof["m_hat_enet"], "m_hat_ar1": oof["m_hat_ar1"],
        "p_adj": p_adj, "loss_open": loss["open"], "loss_close": loss["close"],
        "loss_adj": loss["adj"], "loss_ar1": loss["ar1"],
        "d_adj_vs_open": loss["open"] - loss["adj"]})
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("s81_%s_2026-09-03.csv" % sport)
    frame.to_csv(path, index=False)
    zero, enet, ar1 = np.zeros(len(m)), oof["m_hat_enet"].to_numpy(), oof["m_hat_ar1"].to_numpy()
    result = {
        "sport": sport, "incumbent": bundle["incumbent"], "improvement_bar": IMPROVEMENT_BAR,
        "n_states": bundle["n_states"], "n_screen": bundle["n_screen"],
        "n_with_both_prices": bundle["n_with_both"], "n_scored": int(len(m)),
        "n_features": int(bundle["X"].shape[1]), "screen_sha256": bundle["screen_sha256"],
        "partition_basis": bundle["partition_basis"], "cluster_key": bundle["cluster_key"],
        "move_sd": float(m.std()), "move_mean": float(m.mean()),
        "folds": oof.groupby("fold")[["alpha", "nonzero_coefs", "ar1_c", "n_train",
                                      "inner_folds"]].first().reset_index().to_dict("records"),
        "move": {"enet_vs_zero": _arm(m, enet, units, teams, zero),
                 "ar1_vs_zero": _arm(m, ar1, units, teams, zero),
                 "enet_vs_ar1": _arm(m, enet, units, teams, ar1)},
        "brier": {name: float(value.mean()) for name, value in loss.items()},
        "adj_vs_open": {"improvement": float((loss["open"] - loss["adj"]).mean()),
                        "unit_dm": _score(loss["open"] - loss["adj"], units),
                        "declared_dm": _score(loss["open"] - loss["adj"], teams)},
        "ar1_vs_open": {"improvement": float((loss["open"] - loss["ar1"]).mean()),
                        "unit_dm": _score(loss["open"] - loss["ar1"], units),
                        "declared_dm": _score(loss["open"] - loss["ar1"], teams)},
        "close_vs_open_ceiling": float((loss["open"] - loss["close"]).mean()),
        "open_at_half_frac": float(np.mean(np.abs(p_open - 0.5) < 1e-9)),
        "artifact": path.as_posix()}
    # The binding CI is the unit CI where the corpus has >= 2 units, else the declared one.
    unit = result["adj_vs_open"]["unit_dm"]
    if unit["ci95"] is None:
        unit = result["adj_vs_open"]["declared_dm"]
    result["clears_bar"] = bool(result["adj_vs_open"]["improvement"] >= IMPROVEMENT_BAR
                                and unit["ci95"] is not None and unit["ci95"][0] > 0.0)
    result["binding_ci95"] = unit["ci95"]
    return result


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="S81 open-to-close market-move screen")
    ap.add_argument("--sports", default=",".join(SPORTS_WITH_OPEN))
    ap.add_argument("--outer-folds", type=int, default=OUTER_FOLDS)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "cache" / "eval_gate")
    args = ap.parse_args(argv)
    results = []
    for sport in [s for s in args.sports.split(",") if s]:
        result = run_sport(sport, args.out_dir, k=args.outer_folds)
        results.append(result)
        print("%-7s n=%-6d p=%-4d move_sd=%.4f enet_r2=%+.5f sign=%.4f ar1_r2=%+.5f "
              "brier open=%.6f adj=%.6f close=%.6f adj-open=%+.6f ci=%s clears=%s"
              % (sport, result["n_scored"], result["n_features"], result["move_sd"],
                 result["move"]["enet_vs_zero"]["r2_vs_null"],
                 result["move"]["enet_vs_zero"]["sign_acc"],
                 result["move"]["ar1_vs_zero"]["r2_vs_null"], result["brier"]["open"],
                 result["brier"]["adj"], result["brier"]["close"],
                 result["adj_vs_open"]["improvement"], result["binding_ci95"],
                 result["clears_bar"]), flush=True)
    path = args.out_dir / "s81_market_move_2026-09-03.json"
    path.write_text(json.dumps(results, indent=1, sort_keys=True, default=str), encoding="ascii")
    print("summary %s" % path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
