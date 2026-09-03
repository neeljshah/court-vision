"""scripts.platformkit.eval_gate.s92_nba_lineup_dynamic -- S92 NON-STATIC NBA lineup terms.

S84's ONE lineup term was STATIC (pregame season-to-date PIE summed over the ten on the
floor) and NULL. S92 screens the non-static successors on the SAME lineup-at-tick machinery
(imported from S84, never reimplemented), extended from S84's 577 rated games to ALL 1,331
bridged games with a lineup, since fatigue needs no player rating. Three terms, each ONE
extra logistic column on the incumbent: `fatigue_min` (minutes played SO FAR THIS GAME by
the ten on the floor, from substitutions strictly before the tick, home minus away),
`fatigue_share` (the same weighted by each player's season as-of workload share -- the store
carries possessions_asof, NOT minutes; an unrated player weighs 1.0) and `unit_onoff` (the
home five's net rating over its EARLIER games this season, score deltas while exactly that
five was on the floor, shrunk n/(n+200) possessions, minus the away five's).
Incumbent = nba_mechanism_ladder BASE. NULL = S94's recalibration null on identical rows, a
logistic on [logit(market_prob)] fit on the same TRAIN fold. Market = market_prob. Screen
side only via S84's partition procedure (seed 0): the rated games reproduce S84's screen sha
byte-for-byte (checked, reported) and the unrated remainder is partitioned SEPARATELY, so no
S84 VERDICT game is read. Game-first-date walk-forward, train purged (asserted game-disjoint),
1-day embargo, standardisation fit inside each TRAIN fold. A SCREEN is a NON-FINDING: no
prereg seal, no charge, no K read. SINGLE-WINDOW. Calibration language only (tick-weighted
Brier); no dollar, ROI or edge claim. ASCII only.
Evidence: docs/evidence/harness/S92_nba_lineup_dynamic_2026-09-03.md
Test: python -m pytest tests/platformkit/ingame/test_s92_nba_lineup_dynamic.py -q
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict
from datetime import date as _date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.catalog_rescreen import verdict_of
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.s84_nba_lineup_at_tick import (ADV, PBP_GLOB,
                                                                  assert_strictly_before,
                                                                  elapsed_of, game_events,
                                                                  lineup_at)
from scripts.platformkit.eval_gate.s92_unit_ledger import unit_history
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.foundry.tiers import partition_corpus
from scripts.platformkit.ingame.nba_mechanism_ladder import (_BASE_COLS, _fit_predict,
                                                             build_crosswalk, load_corpus)

REPO = Path(__file__).resolve().parents[3]
GAMES = REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s92_nba_lineup_dynamic_2026-09-03"
FEATURES = ("fatigue_min", "fatigue_share", "unit_onoff")
SHARE = "possessions_asof"      # the only as-of workload column the store carries (no minutes)
S84_SCREEN_SHA = "0e770bd263297b09c5f1d1da6153355a2da504a4d55f091dfdfe39e310adc07e"
PARTITION_SEED, MIN_TRAIN_TICKS, IMPROVEMENT_BAR, EPS = 0, 500, 0.004, 1e-6
_PROVENANCE = {
    "tier": "SCREEN (uncharged, no prereg seal, no K read, FWER ledger never opened)",
    "incumbent": "nba_mechanism_ladder BASE -- logistic on standardized [logit_p0 (first "
                 "traded), signed margin, margin/sqrt(rem_frac)]",
    "null_arm": "S94 recalibration null -- logistic on [logit(market_prob)], same TRAIN fold",
    "market_column": "market_prob (Polymarket in-play, same tick)",
    "protocol": "purge by game (train asserted disjoint from test); standardisation fit on "
                "TRAIN inside each fold (_fit_predict) and applied to TEST",
    "single_window": True, "improvement_bar": IMPROVEMENT_BAR, "sport": "nba",
    "honest_note": "Calibration (tick-weighted Brier) only; no dollar, ROI or edge claim. "
                   "One capture window of priced NBA in-play ticks -- SINGLE-WINDOW.",
}
_TICK_COLS = ("ts", "game_date", "period", "elapsed", "outcome_home_win", "market_prob",
              "logit_p0", "margin_s", "z")


def minutes_so_far(subs: Sequence[dict], starters: Dict[str, frozenset],
                   tick_elapsed: float) -> Dict[int, float]:
    """Seconds on the floor so far THIS GAME per player, from events strictly before the tick."""
    used = [s for s in subs if float(s["elapsed"]) < float(tick_elapsed)]
    assert_strictly_before(used, tick_elapsed, "minutes_so_far")
    entered = {int(p): 0.0 for five in starters.values() for p in five}
    secs: Dict[int, float] = defaultdict(float)
    for ev in used:
        pid = int(ev["player"])
        if ev["sub"] == "in":
            entered.setdefault(pid, float(ev["elapsed"]))
        elif pid in entered:
            secs[pid] += float(ev["elapsed"]) - entered.pop(pid)
    for pid, start in entered.items():
        secs[pid] += float(tick_elapsed) - start
    return dict(secs)


def shares(adv: pd.DataFrame) -> Dict[str, Dict[int, float]]:
    """Per game, each rated player's as-of workload share relative to that game's own mean."""
    out: Dict[str, Dict[int, float]] = {}
    for gid, block in adv.groupby(adv["game_id"].astype(str), sort=False):
        vals = pd.to_numeric(block[SHARE], errors="coerce")
        mean = float(vals.mean()) if vals.notna().any() else 0.0
        if mean:
            out[gid] = {int(p): float(v) / mean
                        for p, v in zip(block["player_id"], vals) if pd.notna(v)}
    return out


def build_frame(corpus: pd.DataFrame, crosswalk: pd.DataFrame, adv: pd.DataFrame,
                pbp: Dict[str, str]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Every live-clock priced tick of a bridged 5v5 game, with the three S92 terms."""
    share_of, rated = shares(adv), set(adv["game_id"].astype(str))
    cw = crosswalk[crosswalk["nba_game_id"].astype(str).isin(pbp)].copy()
    cover = {"n_games_priced": int(corpus["game_id"].nunique()),
             "n_games_bridged": int(len(crosswalk)), "n_games_bridged_with_pbp": int(len(cw)),
             "n_games_with_rating": int(cw["nba_game_id"].astype(str).isin(rated).sum())}
    live = corpus[corpus["game_clock_s"] > 0.0].copy()
    live["elapsed"] = [elapsed_of(p, c) for p, c in zip(live["period"], live["game_clock_s"])]
    blocks = dict(tuple(live.groupby("game_id")))
    rows, need, n_bad, n_not5 = [], defaultdict(set), 0, 0
    for rec in cw.itertuples(index=False):
        block, nba_id = blocks.get(rec.game_id), str(rec.nba_game_id)
        if block is None:
            continue
        subs, starters = game_events(pbp[nba_id])
        if sorted(starters) != sorted([rec.home, rec.away]) or any(
                len(v) != 5 for v in starters.values()):
            n_bad += 1
            continue
        share = share_of.get(nba_id, {})
        for tick in block.itertuples(index=False):
            floor = lineup_at(subs, starters, tick.elapsed)
            home, away = floor[rec.home], floor[rec.away]
            if len(home) != 5 or len(away) != 5:
                n_not5 += 1
                continue
            secs = minutes_so_far(subs, starters, tick.elapsed)
            row = {c: getattr(tick, c) for c in _TICK_COLS}
            row.update(game=str(rec.game_id), nba_game_id=nba_id, rated=nba_id in rated,
                       home_five="|".join(str(p) for p in sorted(home)),
                       away_five="|".join(str(p) for p in sorted(away)),
                       fatigue_min=(sum(secs.get(p, 0.0) for p in home)
                                    - sum(secs.get(p, 0.0) for p in away)) / 60.0,
                       fatigue_share=(sum(secs.get(p, 0.0) * share.get(p, 1.0) for p in home)
                                      - sum(secs.get(p, 0.0) * share.get(p, 1.0)
                                            for p in away)) / 60.0)
            rows.append(row)
            need[nba_id].update((home, away))
    frame = pd.DataFrame(rows)
    cover.update(n_games_lineup=int(frame["game"].nunique()) if len(frame) else 0,
                 n_ticks_live_clock=int(len(live)), n_ticks_lineup=int(len(frame)),
                 n_games_starters_not_5v5=int(n_bad), n_ticks_floor_not_5v5=int(n_not5))
    if frame.empty:
        return frame, cover
    hist = unit_history(dict(need), pbp)
    frame["unit_onoff"] = [hist.get(g, {}).get(frozenset(int(p) for p in h.split("|")), 0.0)
                           - hist.get(g, {}).get(frozenset(int(p) for p in a.split("|")), 0.0)
                           for g, h, a in zip(frame["nba_game_id"], frame["home_five"],
                                              frame["away_five"])]
    cover["n_games_with_unit_history"] = int(sum(1 for g in need if hist.get(g)))
    clip = np.clip(frame["market_prob"].to_numpy(dtype=float), EPS, 1.0 - EPS)
    frame["logit_market"] = np.log(clip / (1.0 - clip))
    frame["date"] = frame["game"].map(frame.groupby("game")["game_date"].min())
    return frame.sort_values(["ts", "game"], kind="stable").reset_index(drop=True), cover


def screen_sides(frame: pd.DataFrame) -> Dict[str, Any]:
    """S84's partition on the rated games (its exact split) + a SEPARATE one on the rest."""
    out = {}
    for tag, sub in (("rated", frame[frame["rated"]]), ("unrated", frame[~frame["rated"]])):
        if not sub.empty:
            out[tag] = partition_corpus(
                [{"game_id": g, "corpus_unit": g, "state_ts": d + "T00:00:00"}
                 for g, d in sub.groupby("game")["date"].min().items()], seed=PARTITION_SEED)
    return out


def walk_forward(frame: pd.DataFrame, *, embargo_days: int) -> Tuple[pd.DataFrame, List[dict]]:
    """Game-first-date walk-forward; train games are purged (disjoint) and embargoed."""
    scored, folds = [], []
    for day in sorted(frame["date"].unique()):
        cut = str(_date.fromisoformat(day) - timedelta(days=int(embargo_days)))
        train, test = frame[frame["date"] < cut], frame[frame["date"] == day].copy()
        if len(train) < MIN_TRAIN_TICKS or train["outcome_home_win"].nunique() < 2:
            folds.append({"test_date": day, "status": "INSUFFICIENT", "n_train": int(len(train))})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= day, "embargo/ordering violated"
        test["p_incumbent"] = _fit_predict(train, test, list(_BASE_COLS))
        test["p_null"] = _fit_predict(train, test, ["logit_market"])
        for feat in FEATURES:
            test["p_" + feat] = _fit_predict(train, test, list(_BASE_COLS) + [feat])
        scored.append(test)
        folds.append({"test_date": day, "status": "OK", "embargo_cut": cut,
                      "train_date_max": str(train["date"].max()),
                      "n_train_ticks": int(len(train)), "n_test_ticks": int(len(test)),
                      "n_test_games": int(test["game"].nunique())})
    return (pd.concat(scored, ignore_index=True) if scored else frame.iloc[0:0].copy()), folds


def score(scored: pd.DataFrame, folds: List[dict], parts: Dict[str, Any], *, tag: str,
          embargo_days: int, cover: Dict[str, Any]) -> Tuple[dict, pd.DataFrame]:
    """Tick-weighted Brier + game-clustered DM vs the incumbent, the market and the S94 null."""
    y = scored["outcome_home_win"].to_numpy(dtype=float)
    games = scored["game"].astype(str).tolist()
    loss = {n: (scored[c].to_numpy(dtype=float) - y) ** 2 for n, c in
            [("incumbent", "p_incumbent"), ("null", "p_null"), ("market", "market_prob")]
            + [(f, "p_" + f) for f in FEATURES]}

    def _dm(values) -> dict:
        r = diebold_mariano(list(values), games)
        return {"stat": float(r.dm_stat), "p_value": float(r.p_value),
                "n_clusters": int(r.n_clusters), "ci95": [float(r.ci95[0]), float(r.ci95[1])]}

    summary: Dict[str, Any] = dict(
        _PROVENANCE, corpus=tag, coverage=cover, folds=folds, terms={},
        spec_id="scripts.platformkit.eval_gate.s92_nba_lineup_dynamic:%s" % tag,
        embargo_days=int(embargo_days), n_ticks=int(len(scored)),
        n_games=int(scored["game"].nunique()),
        brier={k: float(v.mean()) for k, v in loss.items()},
        reproduces_s84_screen_sha256=bool(
            "rated" in parts and parts["rated"].screen_sha256 == S84_SCREEN_SHA),
        partitions={k: {"basis": p.basis, "seed": p.seed, "screen_sha256": p.screen_sha256,
                        "verdict_sha256": p.verdict_sha256, "n_screen": len(p.screen_ids),
                        "n_verdict": len(p.verdict_ids)} for k, p in parts.items()})
    series = scored[["game", "nba_game_id", "ts", "date", "period", "elapsed",
                     "outcome_home_win", "home_five", "away_five", "market_prob",
                     "p_incumbent", "p_null"] + list(FEATURES)].copy()
    for name in ("incumbent", "null", "market"):
        series["loss_" + name] = loss[name]
    for feat in FEATURES:
        series["p_" + feat] = scored["p_" + feat].to_numpy(dtype=float)
        series["loss_" + feat] = loss[feat]
        series["d_" + feat] = loss["incumbent"] - loss[feat]      # >0 -> the candidate lost less
        vs_mkt, vs_null = loss["market"] - loss[feat], loss["null"] - loss[feat]
        dm_inc, dm_mkt, dm_null = _dm(series["d_" + feat]), _dm(vs_mkt), _dm(vs_null)
        gain = float(loss["incumbent"].mean() - loss[feat].mean())
        block = {"improvement_vs_incumbent": gain, "improvement_vs_market": float(vs_mkt.mean()),
                 "improvement_vs_null": float(vs_null.mean()), "dm_vs_incumbent": dm_inc,
                 "dm_vs_market": dm_mkt, "dm_vs_null": dm_null,
                 "verdict": verdict_of(gain, float(dm_inc["p_value"]))}
        block["prereg_draft_warranted"] = bool(
            block["improvement_vs_market"] >= IMPROVEMENT_BAR and dm_mkt["ci95"][0] > 0.0
            and block["improvement_vs_null"] > 0.0)
        attach_informative_summary(block, series, "d_" + feat, ts_col="ts",
                                   market_col="market_prob", model_col="p_" + feat)
        summary["terms"][feat] = block
    series["cluster_id"] = series["game"]
    return summary, series


def run(tag: str, frame: pd.DataFrame, parts: Dict[str, Any], cover: Dict[str, Any], *,
        embargo_days: int = 1, out_dir: Path = OUT_DIR) -> dict:
    """Walk, score and archive (Q9) ONE corpus side; returns the summary that was written."""
    scored, folds = walk_forward(frame, embargo_days=embargo_days)
    if scored.empty:
        return {"corpus": tag, "verdict": "SCREEN_INFEASIBLE", "coverage": cover, "folds": folds}
    summary, series = score(scored, folds, parts, tag=tag, embargo_days=embargo_days, cover=cover)
    summary["n_screen_ticks_available"] = int(len(frame))
    out_dir.mkdir(parents=True, exist_ok=True)
    series.to_csv(out_dir / ("%s_%s.csv" % (STEM, tag)), index=False)
    summary["per_tick_series"] = str(out_dir / ("%s_%s.csv" % (STEM, tag)))
    (out_dir / ("%s_%s.json" % (STEM, tag))).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    corpus = load_corpus()
    adv = pd.read_parquet(ADV, columns=["player_id", "game_id", SHARE])
    pbp = {os.path.basename(p)[:-5]: p for p in glob.glob(PBP_GLOB)}
    frame, cover = build_frame(corpus, build_crosswalk(corpus), adv, pbp)
    parts = screen_sides(frame)
    screen = frame[frame["game"].isin(set().union(*(p.screen_ids for p in parts.values())))]
    for tag, sub in (("all", screen), ("rated", screen[screen["rated"]])):
        res = run(tag, sub.reset_index(drop=True), parts, cover)
        print("%s | n_ticks %d n_games %d | s84_sha %s | brier %s" % (
            tag, res["n_ticks"], res["n_games"], res["reproduces_s84_screen_sha256"],
            {k: round(v, 6) for k, v in res["brier"].items()}))
        for feat, t in res["terms"].items():
            print("  %-14s vs_inc %+.6f p %.4g ci %s | vs_mkt %+.6f | vs_null %+.6f | %s | %s"
                  % (feat, t["improvement_vs_incumbent"], t["dm_vs_incumbent"]["p_value"],
                     [round(c, 6) for c in t["dm_vs_incumbent"]["ci95"]],
                     t["improvement_vs_market"], t["improvement_vs_null"], t["verdict"],
                     {k: t["tick_informative"][k] for k in ("n", "n_informative", "n_eff_icc")}))
        print("  coverage %s" % res["coverage"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
