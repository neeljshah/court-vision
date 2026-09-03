"""S117: the in-game screen tier on soccer -- the first sport it has run on outside MLB/NBA.

S82 built the tier and ran it on the MLB Kalshi tick store; S102 swept NBA. soccer_intl was
skipped because its joined store then carried only a bare `state_summary = "live"` sentinel.
S104 showed the writer cut over to a structured KV string on 2026-06-27, so score and minute
are on disk from 2026-06-28 and the tier can finally be pointed at a third sport.

WHAT IS REUSED VERBATIM (never re-implemented here): `ingame_screen.BAR` (+0.004, the S58
in-game bar, never moved), `ingame_screen.assert_tick_asof` (tick-time as-of by truncation
invariance), `ingame_screen.walk_forward_feature` (game-first-date folds, purge on SETTLEMENT
with a 1-day embargo, null arm = the same [1, logit(p_model)] recalibration on identical rows),
`screen_rows`, `score_feature` and `partition`. This module supplies only the soccer corpus
loader and the soccer state grammar.

TWO PARTITIONS ARE REPORTED, because iso_week is lopsided on a tournament corpus (S99): the
SF-1 iso_week screen/verdict split -- the SCREEN side is the scored side, always -- and, inside
it, the game-first-date walk-forward folds that actually produce every number.

INCUMBENT: `model_prob` from the joined store (the live soccer model). There is no e4 for
soccer; the market line is reported beside it, never as the incumbent.
PREGAME PRIOR: the game's OWN first captured `model_prob`. The soccer gate corpus is club
leagues through 2026-05-24 and carries no p_close, so it supplies no prior for these
internationals -- see the memo. The substitute is causal (a value observed at t0 <= t).

A SCREEN IS A NON-FINDING. No ledger row, no prereg seal, no charge, no K read. Calibration
language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/foundry/test_ingame_screen_soccer.py -q
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.foundry import ingame_screen
from scripts.platformkit.foundry.ingame_screen import (BAR, ROOT, assert_tick_asof, partition,
                                                       score_feature, screen_rows,
                                                       walk_forward_feature)

STORE = ROOT / "data" / "cache" / "ingame_grade_joined" / "soccer_intl"
OUT = ROOT / "data" / "cache" / "eval_gate"
_KV = re.compile(r"(\w+)=([\w\.\-]+)")
DECAY_TAU = 30.0        # minutes; a lead matters more the closer the whole-match clock is to 90
FULL_TIME = 90.0
TARGET = 0.002          # the half-width the extrapolation is quoted against

# feature name -> the column build_features supplies. Every one is a function of this game's
# events with a stamp <= the tick's own, plus the game's own first captured model probability.
FEATURES: Dict[str, str] = {
    "minute": "minute",
    "score_diff": "score_diff",
    "goals_total": "goals_total",
    "score_diff_decayed": "score_diff_decayed",
    "minute_x_score_diff": "minute_x_score_diff",
    "prior_vs_line_gap": "prior_vs_line_gap",
    "minutes_since_last_goal": "minutes_since_last_goal",
}


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return float(np.log(p / (1.0 - p)))


def load_ticks(store: Path = STORE) -> Tuple[List[dict], Dict[str, str], dict]:
    """Every soccer_intl tick carrying structured state AND a line AND a settled outcome.

    A tick whose `state_summary` is the legacy bare "live" sentinel, or which is missing the
    minute, has no state to screen on and is dropped from the DENOMINATOR here rather than
    quarantined downstream -- the census of what was dropped is returned beside the ticks (B3).
    """
    kept: List[dict] = []
    census = {"files": 0, "ticks": 0, "no_state": 0, "no_minute": 0, "no_market": 0,
              "no_outcome": 0}
    for path in sorted(Path(store).glob("*.jsonl")):
        census["files"] += 1
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            census["ticks"] += 1
            kv = dict(_KV.findall(rec.get("state_summary") or ""))
            if "home_score" not in kv or "away_score" not in kv:
                census["no_state"] += 1
                continue
            if "minute" not in kv:
                census["no_minute"] += 1
                continue
            if rec.get("market_prob") is None or rec.get("model_prob") is None:
                census["no_market"] += 1
                continue
            if rec.get("outcome") is None:
                census["no_outcome"] += 1
                continue
            kept.append({"game": str(rec["game_id"]), "timestamp": str(rec["ts"]),
                         "market_prob": float(rec["market_prob"]),
                         "model_prob": float(rec["model_prob"]),
                         "outcome": float(rec["outcome"]),
                         "home_score": float(kv["home_score"]),
                         "away_score": float(kv["away_score"]),
                         "minute": float(kv["minute"]), "_row_id": len(kept)})
    first: Dict[str, str] = {}
    for tick in kept:
        date = tick["timestamp"][:10]
        if tick["game"] not in first or date < first[tick["game"]]:
            first[tick["game"]] = date
    census["kept"] = len(kept)
    census["games"] = len(first)
    return kept, first, census


def causal_source(ticks: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """The loader's own causal ordering: ticks sorted by (timestamp, game), stable."""
    frame = pd.DataFrame([{k: t[k] for k in ("game", "timestamp", "market_prob", "model_prob",
                                             "home_score", "away_score", "minute", "_row_id")}
                          for t in ticks])
    return frame.sort_values(["timestamp", "game"], kind="stable").reset_index(drop=True)


def _minutes_since_last_goal(group: pd.DataFrame) -> List[float]:
    """Minutes since this game's last score CHANGE; minutes since kickoff before the first."""
    out, last, prev = [], 0.0, None
    for minute, total in zip(group["minute"], group["goals_total"]):
        if prev is not None and total != prev:
            last = float(minute)
        prev = total
        out.append(float(minute) - last)
    return out


def build_features(src: pd.DataFrame) -> pd.DataFrame:
    """Soccer state features at each tick. Every column is prefix-safe: it reads this game's
    rows up to and including the tick's own, and nothing later (assert_tick_asof enforces it).
    """
    out = src.copy()
    out["score_diff"] = out["home_score"] - out["away_score"]
    out["goals_total"] = out["home_score"] + out["away_score"]
    remaining = (FULL_TIME - out["minute"]).clip(lower=0.0)
    out["score_diff_decayed"] = out["score_diff"] * np.exp(-remaining / DECAY_TAU)
    out["minute_x_score_diff"] = out["minute"] * out["score_diff"]
    prior = out.groupby("game")["model_prob"].transform("first")
    out["prior_vs_line_gap"] = (np.array([_logit(p) for p in prior])
                                - np.array([_logit(p) for p in out["market_prob"]]))
    since = pd.Series(np.nan, index=out.index, dtype=float)
    for _, group in out.groupby("game", sort=False):
        since.loc[group.index] = _minutes_since_last_goal(group)
    out["minutes_since_last_goal"] = since
    return out[["game", "timestamp", "_row_id"] + sorted(set(FEATURES.values()))]


def _extrapolate(half_width: float, n_games: int) -> Optional[float]:
    """Games needed for a `TARGET` half-width, by the 1/sqrt(n) rule. LABELLED, not measured."""
    if not (half_width and half_width > 0.0 and n_games > 0):
        return None
    return float(n_games * (half_width / TARGET) ** 2)


def run(ticks, first_dates, table, *, out_json: Optional[Path] = None,
        out_csv: Optional[Path] = None, census: Optional[dict] = None,
        min_train: int = ingame_screen.MIN_TRAIN) -> dict:
    """Screen every soccer state feature on the SCREEN side of the iso_week split.

    `min_train` is the reused walk-forward's own TRAIN FLOOR, not a bar: BAR (+0.004) is never
    touched. The default is the tier's verbatim 1000, which was sized for a 50k-tick MLB store
    and eats most of a 3.7k-tick soccer one; any other value is a SENSITIVITY arm and is
    labelled as such in the artifact, never as the headline.
    """
    rows = screen_rows(ticks, [t["model_prob"] for t in ticks], table, first_dates)
    part = partition(rows)
    side = rows[rows["game"].isin(part.screen_ids)].reset_index(drop=True)
    results: List[dict] = []
    series: List[pd.DataFrame] = []
    floor_was, ingame_screen.MIN_TRAIN = ingame_screen.MIN_TRAIN, int(min_train)
    try:
        _screen_all(side, results, series)
    finally:
        ingame_screen.MIN_TRAIN = floor_was
    results.sort(key=lambda r: -(r.get("improvement_vs_null", -9.9)))
    report = {"tier": "in-game screen (S82) on soccer (S117)", "verdict": "SCREEN (a non-finding)",
              "sport": "soccer_intl", "bar": BAR, "target_half_width": TARGET,
              "incumbent": "model_prob", "prior": "game's own first captured model_prob",
              "train_floor": int(min_train), "train_floor_verbatim": floor_was,
              "arm": "headline (verbatim train floor)" if int(min_train) == floor_was
                     else "SENSITIVITY (train floor lowered for corpus size; BAR untouched)",
              "census": dict(census or {}),
              "partition": {"basis": part.basis, "scored_side": "screen",
                            "screen_sha256": part.screen_sha256,
                            "verdict_sha256": part.verdict_sha256,
                            "n_screen_games": len(part.screen_ids),
                            "n_verdict_games": len(part.verdict_ids)},
              "corpus": {"n_scored_ticks": int(len(rows)),
                         "n_scored_games": int(rows["game"].nunique()),
                         "n_screen_ticks": int(len(side)),
                         "n_screen_games": int(side["game"].nunique()),
                         "ts_min": str(rows["ts"].min()), "ts_max": str(rows["ts"].max())},
              "results": results,
              "n_clearing_bar": sum(1 for r in results if r.get("clears_bar")),
              "per_tick_series": str(out_csv) if out_csv else None}
    if out_csv and series:
        pd.concat(series, ignore_index=True).to_csv(out_csv, index=False)
    if out_json:
        Path(out_json).write_text(json.dumps(report, indent=1, sort_keys=True, default=str),
                                  "ascii")
    return report


def _screen_all(side: pd.DataFrame, results: List[dict], series: List[pd.DataFrame]) -> None:
    """One walk-forward screen per feature on the SCREEN side; archive the differential (Q9)."""
    for name, column in sorted(FEATURES.items()):
        candidate, null, folds = walk_forward_feature(side, column)
        if not candidate.notna().any():
            results.append({"feature": column, "grammar_member": name, "status": "UNSCORED",
                            "folds": folds})
            continue
        record = score_feature(side, candidate, null, column)
        index = record.pop("_index")
        scored = side.loc[index]
        frame = pd.DataFrame({
            "feature": column, "tick_index": scored["row_id"].to_numpy(),
            "game": scored["game"].to_numpy(), "timestamp": scored["ts"].to_numpy(),
            "y": scored["y"].to_numpy(), "p_model": scored["p_e4"].to_numpy(),
            "p_null": null[index].to_numpy(), "p_candidate": candidate[index].to_numpy(),
            "market": scored["market"].to_numpy(), "x": scored[column].to_numpy()})
        frame["loss_null"] = (frame["p_null"] - frame["y"]) ** 2
        frame["loss_candidate"] = (frame["p_candidate"] - frame["y"]) ** 2
        frame["loss_market"] = (frame["market"] - frame["y"]) ** 2
        frame["delta_vs_null"] = frame["loss_null"] - frame["loss_candidate"]
        frame["delta_vs_market"] = frame["loss_market"] - frame["loss_candidate"]
        series.append(frame)
        record["incumbent"] = "model_prob (live soccer model; no e4 exists for soccer)"
        record["brier_model"] = record.pop("brier_e4")
        record["improvement_vs_model"] = record.pop("improvement_vs_e4")
        record["dm_vs_model"] = record.pop("dm_vs_e4")
        half = (record["dm_ci95"][1] - record["dm_ci95"][0]) / 2.0
        record["ci95_half_width"] = half
        record["games_for_target_half_width"] = _extrapolate(half, record["n_games"])
        attach_informative_summary(record, frame.rename(columns={"p_candidate": "model"}),
                                   "delta_vs_null", ts_col="timestamp", market_col="market",
                                   model_col="model")
        record.update({"grammar_member": name, "status": "SCREENED", "folds": folds})
        results.append(record)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="S117 in-game screen on soccer_intl")
    parser.add_argument("--probes", type=int, default=8)
    parser.add_argument("--min-train", type=int, default=ingame_screen.MIN_TRAIN,
                        help="walk-forward train floor; anything but the verbatim 1000 is a "
                             "labelled SENSITIVITY arm. The BAR is never touched.")
    parser.add_argument("--tag", default="", help="artifact suffix for a sensitivity arm")
    args = parser.parse_args(argv)
    ticks, first_dates, census = load_ticks()
    print("census: %s" % json.dumps(census, sort_keys=True))
    src = causal_source(ticks)
    print("tick-time as-of guard: probes %s" % assert_tick_asof(src, build_features,
                                                                probes=args.probes))
    OUT.mkdir(parents=True, exist_ok=True)
    stem = "s117_soccer_ingame_screen%s_2026-09-03" % (("_" + args.tag) if args.tag else "")
    report = run(ticks, first_dates, build_features(src), census=census,
                 min_train=args.min_train, out_json=OUT / ("%s.json" % stem),
                 out_csv=OUT / ("%s_series.csv" % stem))
    corpus, part = report["corpus"], report["partition"]
    print("arm: %s | train floor %d (verbatim %d) | bar +%.3f"
          % (report["arm"], report["train_floor"], report["train_floor_verbatim"], BAR))
    print("SCREEN side: %d ticks / %d games of %d / %d scored | partition %s (screen is scored)"
          % (corpus["n_screen_ticks"], corpus["n_screen_games"], corpus["n_scored_ticks"],
             corpus["n_scored_games"], part["basis"]))
    for r in report["results"]:
        if r.get("status") != "SCREENED":
            print("  %-24s %s  folds %s" % (r["feature"], r["status"],
                                            json.dumps([f["status"] for f in r["folds"]])))
            continue
        info = r["tick_informative"]
        print("  %-24s n=%5d ninf=%5d neff=%6s g=%2d model %.6f null %.6f cand %.6f mkt %.6f "
              "impr_null %+.6f vs_mkt %+.6f ci95 [%+.6f %+.6f] half %.6f p %.3g%s"
              % (r["feature"], r["n_ticks"], info["n_informative"],
                 ("%.1f" % info["n_eff_icc"]) if info["n_eff_icc"] else "n/a", r["n_games"],
                 r["brier_model"], r["brier_null_recal"], r["brier_candidate"], r["brier_market"],
                 r["improvement_vs_null"], r["improvement_vs_market"], r["dm_ci95"][0],
                 r["dm_ci95"][1], r["ci95_half_width"], r["dm_p_raw"],
                 "  CLEARS BAR" if r["clears_bar"] else ""))
    print("clearing the +%.3f bar: %d of %d" % (BAR, report["n_clearing_bar"],
                                                len(report["results"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
