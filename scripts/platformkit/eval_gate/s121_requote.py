"""S121 -- re-quote the in-game screens on the TICK-CLEAN partition, from the archives alone.

THE DEFECT (S121): `ingame_screen.partition` blocks by the TICKER's game-first-date ISO week
and `run()` then screens every tick of a screen-side ticker. A Kalshi ticker parks several
nights under one key (S105/S106), so 495 of the 15,702 S82 screen ticks are dated 2026-07-06 /
07-07 = 2026-W28 = the VERDICT week. `tick_partition.screen_side(mode="tick_week")` blocks each
tick by its own ISO week, with each real game coalesced to its first tick's week.

THIS SCRIPT REFITS NOTHING. `p_null` / `p_candidate` are the archived walk-forward predictions;
the tick-clean side is a SUBSET of the archived rows, so every number here is a re-quote of the
same paired losses on fewer ticks. A SCREEN IS A NON-FINDING: no ledger row, no prereg seal, no
K read. Calibration language only. ASCII only.

Per-file test: python -m pytest tests/platformkit/eval_gate/test_s121_requote.py -q
Run:           python -m scripts.platformkit.eval_gate.s121_requote
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.real_game_split import assign_real_game_seq, cluster_ids
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary
from scripts.platformkit.foundry.tick_partition import tick_partition

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "cache" / "eval_gate"
BAR = 0.004                       # the S58/S82 in-game bar; never moved (Q3/B10)
MLB_SERIES = CACHE / "s82_ingame_screen_series_2026-09-03.csv"
S119_JSON = CACHE / "s119_real_game_requote_2026-09-03.json"
SOCCER_ARMS = {"headline": CACHE / "s117_soccer_ingame_screen_2026-09-03_series.csv",
               "mintrain200": CACHE / "s117_soccer_ingame_screen_mintrain200_2026-09-03_series.csv"}
OUT_JSON = CACHE / "s121_requote_2026-09-03.json"


def _iso_week(stamps: pd.Series) -> pd.Series:
    iso = pd.to_datetime(stamps.astype(str).str.replace("Z", "", regex=False)).dt.isocalendar()
    return iso.year.astype(str) + "-W" + iso.week.astype(int).astype(str).str.zfill(2)


def clean_tick_ids(series: pd.DataFrame, state_summary: Optional[List[Any]] = None) -> Dict[str, Any]:
    """The archived tick ids whose OWN ISO week is a SCREEN block, plus what was dropped.

    A single-block archive has nothing to partition: every tick is already on the screen side
    and `partition_corpus` would refuse an empty verdict side, so that case is reported, not
    forced (missing != bad, contract B3)."""
    ticks = series.drop_duplicates("tick_index").reset_index(drop=True)
    rows = ticks.rename(columns={"tick_index": "row_id", "timestamp": "ts"})[["row_id", "game", "ts"]]
    weeks = _iso_week(rows["ts"])
    ticker_weeks = sorted(set(_iso_week(rows.groupby("game")["ts"].transform("min"))))
    if weeks.nunique() < 2:
        return {"n_ticks": int(len(rows)), "tick_weeks": sorted(set(weeks)),
                "ticker_weeks": ticker_weeks, "screen_weeks": sorted(set(weeks)),
                "keep": set(rows["row_id"]), "n_dropped": 0, "single_block": True,
                "real_game_purged": state_summary is not None}
    part = tick_partition(rows, state_summary=state_summary)
    keep = {int(r) for r in rows["row_id"] if str(r) in part.screen_ids}
    on_screen = rows["row_id"].isin(keep).to_numpy()
    assert not (part.screen_ids & part.verdict_ids), "the two tick sides are not disjoint"
    assert len(part.screen_ids) + len(part.verdict_ids) == len(rows), "a tick landed on neither side"
    straddle: List[str] = []
    if state_summary is not None:      # no REAL GAME may contribute to both sides (S106 purge)
        frame = pd.DataFrame({"game_id": rows["game"].astype(str).to_numpy(),
                              "ts": rows["ts"].astype(str).to_numpy(),
                              "state_summary": list(state_summary)})
        split, _ = assign_real_game_seq(frame)
        sides = pd.DataFrame({"cluster": cluster_ids(split).to_numpy(), "screen": on_screen}
                             ).groupby("cluster")["screen"].nunique()
        straddle = sorted(sides.index[sides > 1])
        assert not straddle, "real games on both partition sides: %s" % straddle[:5]
    return {"n_ticks": int(len(rows)), "tick_weeks": sorted(set(weeks)),
            "ticker_weeks": ticker_weeks, "keep": keep,
            "screen_weeks": sorted(set(weeks[on_screen])),
            "kept_outside_screen_week": int((weeks[on_screen] != weeks[on_screen].iloc[0]).sum())
                                        if state_summary is not None else 0,
            "n_dropped": int(len(rows) - len(keep)), "single_block": False,
            "real_game_purged": state_summary is not None}


def _dm(delta: np.ndarray, clusters: List[str]) -> Dict[str, Any]:
    if len(set(clusters)) < 2:
        return {"n_clusters": len(set(clusters)), "ci95": None, "half_width": None, "p": None}
    res = diebold_mariano([float(d) for d in delta], clusters)
    lo, hi = float(res.ci95[0]), float(res.ci95[1])
    return {"n_clusters": len(set(clusters)), "ci95": [lo, hi], "half_width": (hi - lo) / 2.0,
            "p": float(res.p_value), "dm_stat": float(res.dm_stat)}


def score_series(series: pd.DataFrame, *, null_col: str = "p_null",
                 cand_col: str = "p_candidate") -> List[Dict[str, Any]]:
    """Per feature: improvement over the null, the game-clustered DM CI, and n_eff.

    Nothing is refitted -- the two probability columns are the archived predictions."""
    out: List[Dict[str, Any]] = []
    for name, block in series.groupby("feature", sort=True):
        y = block["y"].to_numpy(float)
        loss_n = (block[null_col].to_numpy(float) - y) ** 2
        loss_c = (block[cand_col].to_numpy(float) - y) ** 2
        delta = loss_n - loss_c                        # > 0 means the feature helped
        improvement = float(loss_n.mean() - loss_c.mean())
        row: Dict[str, Any] = {
            "feature": name, "n_ticks": int(len(block)), "n_games": int(block["game"].nunique()),
            "brier_null_recal": float(loss_n.mean()), "brier_candidate": float(loss_c.mean()),
            "improvement_vs_null": improvement, "bar": BAR,
            "by_game": _dm(delta, [str(g) for g in block["game"]]),
            "clears_bar": bool(improvement >= BAR
                               and (_dm(delta, [str(g) for g in block["game"]])["ci95"]
                                    or [0.0])[0] > 0.0)}
        attach_informative_summary(
            row, block.assign(loss_differential=delta, model=block[cand_col]),
            "loss_differential", game_col="game", ts_col="timestamp",
            market_col="market", model_col="model")
        out.append(row)
    out.sort(key=lambda r: -r["improvement_vs_null"])
    return out


def _pair(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per feature: the archived quote beside the tick-clean one, verdicts labelled."""
    by_new = {r["feature"]: r for r in new}
    rows = []
    for was in old:
        now = by_new.get(was["feature"])
        if now is None:
            rows.append({"feature": was["feature"], "status": "DROPPED_ENTIRELY"})
            continue
        rows.append({
            "feature": was["feature"],
            "n_old": was["n_ticks"], "n_new": now["n_ticks"],
            "n_eff_old": was.get("tick_informative", {}).get("n_eff_icc"),
            "n_eff_new": now.get("tick_informative", {}).get("n_eff_icc"),
            "improvement_old": was["improvement_vs_null"], "improvement_new": now["improvement_vs_null"],
            "ci_old": (was.get("by_game") or was.get("by_real_game") or {}).get("ci95"),
            "ci_new": (now.get("by_game") or now.get("by_real_game") or {}).get("ci95"),
            "clears_bar_old": bool(was.get("clears_bar") or was.get("clears_bar_real_game")),
            "clears_bar_new": bool(now.get("clears_bar") or now.get("clears_bar_real_game")),
            "verdict": "SCREEN_NULL (unchanged)"
                       if not (was.get("clears_bar") or was.get("clears_bar_real_game")
                               or now.get("clears_bar") or now.get("clears_bar_real_game"))
                       else "RE-LABELLED"})
    rows.sort(key=lambda r: -(r.get("improvement_new") or -9.9))
    return rows


def mlb_block() -> Dict[str, Any]:
    """S82's 14-feature table and S119's real-game table, re-quoted on the tick-clean side."""
    from scripts.platformkit.foundry.ingame_supply_mlb import joined_ticks, real_game_map, requote

    series = pd.read_csv(MLB_SERIES)
    ticks = joined_ticks()
    summary_by_key = dict(zip(zip(ticks["game_id"].astype(str), ticks["ts"].astype(str)),
                              ticks["state_summary"]))
    unique = series.drop_duplicates("tick_index")
    state = [summary_by_key.get((str(g), str(t)))
             for g, t in zip(unique["game"], unique["timestamp"])]
    clean = clean_tick_ids(series, state_summary=state)     # HEADLINE: real games kept whole
    naive = clean_tick_ids(series)                          # the S119 calendar-clean cross-check
    mapping = real_game_map(ticks)
    split_summary = mapping.pop("_summary")

    def _on(ids):
        return requote(series[series["tick_index"].isin(ids)].reset_index(drop=True), mapping)

    old, new, naive_table = requote(series, mapping), _on(clean["keep"]), _on(naive["keep"])
    archived = json.loads(S119_JSON.read_text("ascii"))

    def _drift(a, b):
        return max(abs(x["improvement_vs_null"] - y["improvement_vs_null"])
                   for x, y in zip(sorted(a, key=lambda r: r["feature"]),
                                   sorted(b, key=lambda r: r["feature"])))

    return {"sport": "mlb", "source_series": str(MLB_SERIES),
            "partition": {k: v for k, v in clean.items() if k != "keep"},
            "partition_naive_tick_week": {k: v for k, v in naive.items() if k != "keep"},
            "real_game_split": split_summary,
            "a2_reproduction_vs_s119": _drift(old, archived["results"]),
            "a2_reproduction_vs_s119_clean":
                _drift(naive_table, archived["calendar_clean_sensitivity"]["results"]),
            "table_old": old, "table_new": new, "table_naive_tick_week": naive_table,
            "comparison": _pair(old, new)}


def soccer_block() -> Dict[str, Any]:
    """S117's two arms. Their archives carry no tick dated outside their tickers' own weeks."""
    arms: Dict[str, Any] = {}
    for arm, path in SOCCER_ARMS.items():
        if not path.exists():
            arms[arm] = {"status": "ARCHIVE_ABSENT", "path": str(path)}
            continue
        series = pd.read_csv(path)
        clean = clean_tick_ids(series)
        old = score_series(series)
        new = (old if clean["n_dropped"] == 0
               else score_series(series[series["tick_index"].isin(clean["keep"])]))
        arms[arm] = {"source_series": str(path),
                     "partition": {k: v for k, v in clean.items() if k != "keep"},
                     "table_old": old, "table_new": new, "comparison": _pair(old, new)}
    return {"sport": "soccer_intl", "incumbent": "model_prob", "arms": arms}


def main() -> int:
    mlb, soccer = mlb_block(), soccer_block()
    part = mlb["partition"]
    print("MLB S82 screen archive: %d ticks, tick weeks %s, ticker weeks %s"
          % (part["n_ticks"], part["tick_weeks"], part["ticker_weeks"]))
    print("tick_week (real games kept whole) drops %d ticks; %d ticks dated in %s are KEPT because "
          "their real game began in the screen week"
          % (part["n_dropped"], part["kept_outside_screen_week"], part["screen_weeks"][-1]))
    print("naive tick-own-week (a real game may be cut in half) drops %d"
          % mlb["partition_naive_tick_week"]["n_dropped"])
    print("A2: reproduces the S119 real-game table to %.2e and its calendar-clean table to %.2e"
          % (mlb["a2_reproduction_vs_s119"], mlb["a2_reproduction_vs_s119_clean"]))
    print("%-24s %7s %7s %10s %10s %13s %13s %26s %s"
          % ("feature", "n_old", "n_new", "neff_old", "neff_new", "impr_old", "impr_new",
             "CI95 new (real game)", "verdict"))
    for row in mlb["comparison"]:
        ci = row["ci_new"] or [float("nan")] * 2
        print("%-24s %7d %7d %10.1f %10.1f %+13.6f %+13.6f  [%+.6f %+.6f] %s"
              % (row["feature"], row["n_old"], row["n_new"], row["n_eff_old"] or 0.0,
                 row["n_eff_new"] or 0.0, row["improvement_old"], row["improvement_new"],
                 ci[0], ci[1], row["verdict"]))
    for arm, block in soccer["arms"].items():
        if "partition" not in block:
            print("soccer %-12s %s" % (arm, block["status"]))
            continue
        p = block["partition"]
        print("soccer %-12s %d ticks, tick weeks %s, ticker weeks %s -> %d dropped"
              % (arm, p["n_ticks"], p["tick_weeks"], p["ticker_weeks"], p["n_dropped"]))
    report = {"row": "S121", "bar": BAR,
              "verdict": "SCREEN_NULL re-quoted on the tick-clean partition (a non-finding)",
              "mode": "tick_week", "mlb": mlb, "soccer": soccer,
              "n_clearing_bar_new": sum(1 for r in mlb["comparison"] if r["clears_bar_new"])
                                    + sum(1 for b in soccer["arms"].values()
                                          for r in b.get("comparison", []) if r["clears_bar_new"])}
    OUT_JSON.write_text(json.dumps(report, indent=1, sort_keys=True, default=str), "ascii")
    print("clearing the +%.3f bar on the tick-clean side: %d | %s"
          % (BAR, report["n_clearing_bar_new"], OUT_JSON))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
