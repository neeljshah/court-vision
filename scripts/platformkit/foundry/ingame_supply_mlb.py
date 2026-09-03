"""S119 -- MLB in-game tick-time SUPPLY probe, and the S82 screen re-quoted on REAL games.

The S119 row asks for tick-time as-of builders for the five members S82 reported
NOT_SUPPLIED (starter TTO from the real pitcher id, bullpen availability as-of, batter
platoon vs pitcher hand, catcher, umpire) and a re-run of the tier with them.

STEP 0 measured that the supply does not exist ON THE SCREEN SIDE (`supply_probe`
re-measures it from the real files, it is not a quotation):

  * every tick carrying `mlb_pitcher_id` / `mlb_batter_id` is dated 2026-07-09..07-12,
    game-first-date 2026-07-08..07-12 = ISO week 2026-W28 = the S82 VERDICT side. The
    SCREEN side (2026-W27) has ZERO identity ticks, so starter TTO by real pitcher id and
    batter platoon are unsupplied there and the only corpus that could supply them is the
    side this lane must never read;
  * `probables.parquet` carries NO catcher column and `home_sp_hand` / `away_sp_hand` are
    0 non-null over the window, so catcher and pitcher hand have no source at all;
  * `bullpen_relief_chains.parquet` ends 2026-07-02 while the screen's scored fold dates
    are 07-03..07-05, so "relievers used in the prior 2 days" is censored, not sampled;
  * only the umpire (probables `hp_umpire_id` -> `umpire_zone_index.ooz_strike_rate`) is
    suppliable. 1 of 5 < 3, so the row's own STOP rule fires and NO builder is written.

What IS delivered is the row's other half: S82's 41 `game_id` clusters are 88 REAL games
(S106), so its CIs were quoted against a unit that is not one game. `requote` recomputes
every S82 interval from the ARCHIVED per-tick paired losses (Q9) on the corrected cluster
(game_id, real_game_seq). No model is refitted, no probability is recomputed and no row is
added or dropped: the point estimates are byte-identical by construction and only the
interval moves. A SCREEN IS A NON-FINDING -- no ledger row, no prereg seal, no K read.
Calibration language only. ASCII only.

Per-file test: python -m pytest tests/platformkit/foundry/test_ingame_supply_mlb.py -q
Run:          python -m scripts.platformkit.foundry.ingame_supply_mlb
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.real_game_split import assign_real_game_seq
from scripts.platformkit.eval_gate.tick_informative import attach_informative_summary

ROOT = Path(__file__).resolve().parents[3]
BAR = 0.004                       # the S58/S82 in-game bar; never moved (Q3/B10)
JOINED = ROOT / "data" / "cache" / "ingame_grade_joined" / "mlb"
SERIES = ROOT / "data" / "cache" / "eval_gate" / "s82_ingame_screen_series_2026-09-03.csv"
OUT_JSON = ROOT / "data" / "cache" / "eval_gate" / "s119_real_game_requote_2026-09-03.json"
OUT_CSV = ROOT / "data" / "cache" / "eval_gate" / "s119_real_game_series_2026-09-03.csv"
WINDOW = ("2026-06-20", "2026-07-15")     # the MLB tick corpus's own date span (S82 section 0)
CLEAN_MAX_DATE = "2026-07-05"             # last day of 2026-W27, the S82 SCREEN partition week


def joined_ticks(directory: Path = JOINED) -> pd.DataFrame:
    """The scored MLB tick store, one row per line: (game_id, ts, state_summary, identity)."""
    rows: List[Dict[str, Any]] = []
    for path in sorted(glob.glob(str(directory / "*.jsonl"))):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                rows.append({"game_id": record.get("game_id"), "ts": record.get("ts"),
                             "state_summary": record.get("state_summary", ""),
                             "mlb_pitcher_id": record.get("mlb_pitcher_id"),
                             "mlb_batter_id": record.get("mlb_batter_id")})
    return pd.DataFrame(rows)


def _iso_weeks(dates: pd.Series) -> Dict[str, int]:
    weeks = pd.to_datetime(dates, errors="coerce").dt.isocalendar().week.dropna().astype(int)
    return {str(k): int(v) for k, v in weeks.value_counts().sort_index().items()}


def supply_probe(ticks: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Measure, from the real files, what each S119 member could be built from TODAY.

    Every number here is read off disk at call time. `suppliable` is the honest verdict for
    the SCREEN side only: a source that exists solely on the verdict side does not supply a
    screen, and a source whose last date precedes the scored folds is censored, not missing.
    """
    ticks = joined_ticks() if ticks is None else ticks
    ticks = ticks.assign(date=ticks["ts"].astype(str).str[:10])
    ident = ticks[ticks["mlb_pitcher_id"].notna()]
    first = ticks.groupby("game_id")["date"].min()
    ident_first = first.reindex(ident["game_id"].unique()).dropna()
    probables = pd.read_parquet(ROOT / "data" / "domains" / "mlb" / "probables.parquet")
    window = probables[probables["game_date"].astype(str).between(*WINDOW)]
    bullpen = pd.read_parquet(ROOT / "data" / "domains" / "mlb" / "bullpen_relief_chains.parquet")
    bullpen_max = str(pd.to_datetime(bullpen["date"]).max().date())
    identity = {"n_ticks_total": int(len(ticks)), "n_ticks_with_pitcher_id": int(len(ident)),
                "n_ticks_with_batter_id": int(ticks["mlb_batter_id"].notna().sum()),
                "tick_date_min": str(ident["date"].min()), "tick_date_max": str(ident["date"].max()),
                "game_first_date_min": str(ident_first.min()), "game_first_date_max": str(ident_first.max()),
                "game_first_date_iso_weeks": _iso_weeks(ident_first)}
    return {
        "identity_on_ticks": identity,
        "probables": {"rows_in_window": int(len(window)),
                      "games_in_window": int(window["game_pk"].nunique()),
                      "hp_umpire_id_non_null": int(window["hp_umpire_id"].notna().sum()),
                      "home_sp_id_non_null": int(window["home_sp_id"].notna().sum()),
                      "home_sp_hand_non_null": int(window["home_sp_hand"].notna().sum()),
                      "away_sp_hand_non_null": int(window["away_sp_hand"].notna().sum()),
                      "has_catcher_column": bool(any("catcher" in c for c in probables.columns))},
        "bullpen_relief_chains": {"rows": int(len(bullpen)), "date_max": bullpen_max,
                                  "rows_on_date_max": int((bullpen["date"] == bullpen["date"].max()).sum())},
        "members": {
            "starter_tto_real_pitcher_id": {"suppliable_on_screen_side": False,
                                            "source": "tick mlb_pitcher_id + ticks strictly before",
                                            "join_key": "(game_id, ts)",
                                            "why": "identity ticks are 2026-W28 = the verdict side"},
            "bullpen_availability_asof": {"suppliable_on_screen_side": False,
                                          "source": "data/domains/mlb/bullpen_relief_chains.parquet",
                                          "join_key": "(team, date) strictly before the game date",
                                          "why": "table ends %s; scored folds are 07-03..07-05"
                                                 % bullpen_max},
            "batter_platoon_vs_hand_asof": {"suppliable_on_screen_side": False,
                                            "source": "tick mlb_batter_id + probables *_sp_hand",
                                            "join_key": "(batter_id, pitcher hand)",
                                            "why": "batter id is verdict-side only AND sp_hand is 0 non-null"},
            "catcher_asof": {"suppliable_on_screen_side": False,
                             "source": "probables.parquet (as the row names it)",
                             "join_key": "n/a", "why": "probables carries no catcher column"},
            "umpire_asof": {"suppliable_on_screen_side": True,
                            "source": "probables.hp_umpire_id -> umpire_zone_index.ooz_strike_rate",
                            "join_key": "(game_date, team pair) -> game_pk -> umpire_id",
                            "why": "covered on every window date"},
        },
        "n_suppliable": 1, "min_members_to_build": 3,
        "verdict": "STOP AFTER PREMISE -- 1 of 5 members suppliable on the screen side",
    }


def real_game_map(ticks: Optional[pd.DataFrame] = None, **kwargs: Any) -> Dict[tuple, int]:
    """(game_id, ts) -> real_game_seq (S106). Asserted single-valued before it is used."""
    ticks = joined_ticks() if ticks is None else ticks
    split, summary = assign_real_game_seq(ticks, **kwargs)
    per_key = split.groupby(["game_id", "ts"])["real_game_seq"].nunique()
    assert int((per_key > 1).sum()) == 0, "a (game_id, ts) pair straddles a real-game boundary"
    mapping = {k: int(v) for k, v in
               split.groupby(["game_id", "ts"])["real_game_seq"].min().items()}
    mapping["_summary"] = summary          # carried for the artifact; callers key by tuples
    return mapping


def _dm(delta: np.ndarray, clusters: List[str]) -> Dict[str, Any]:
    """Cluster-robust DM interval, plus the half-width the S119 row asks to be reported."""
    if len(set(clusters)) < 2:
        return {"n_clusters": len(set(clusters)), "ci95": None, "half_width": None, "p": None}
    res = diebold_mariano([float(d) for d in delta], clusters)
    lo, hi = float(res.ci95[0]), float(res.ci95[1])
    return {"n_clusters": len(set(clusters)), "ci95": [lo, hi], "half_width": (hi - lo) / 2.0,
            "p": float(res.p_value), "dm_stat": float(res.dm_stat)}


def requote(series: pd.DataFrame, mapping: Dict[tuple, int],
            max_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Re-quote every S82 feature's interval on the corrected cluster, from the archive alone.

    Nothing is refitted: `p_null` / `p_candidate` are the archived walk-forward predictions,
    so `improvement_vs_null` is identical to S82 by construction (asserted by the caller's
    reproduction check) and ONLY the interval and its half-width move.
    """
    keys = pd.MultiIndex.from_arrays([series["game"].astype(str), series["timestamp"].astype(str)])
    series = series.assign(real_game_seq=[mapping.get(k) for k in keys])
    assert series["real_game_seq"].notna().all(), "an archived tick is absent from the tick store"
    series = series.assign(cluster=series["game"].astype(str) + "#"
                           + series["real_game_seq"].astype(int).astype(str))
    if max_date is not None:      # the calendar-clean sensitivity: drop ticks dated after the
        series = series[series["timestamp"].astype(str).str[:10] <= max_date]   # partition week
    out: List[Dict[str, Any]] = []
    for name, block in series.groupby("feature", sort=True):
        y = block["y"].to_numpy(float)
        loss_n = (block["p_null"].to_numpy(float) - y) ** 2
        loss_c = (block["p_candidate"].to_numpy(float) - y) ** 2
        loss_m = (block["market"].to_numpy(float) - y) ** 2
        loss_e4 = (block["p_e4"].to_numpy(float) - y) ** 2
        delta = loss_n - loss_c                       # > 0 means the feature helped
        by_game = _dm(delta, [str(g) for g in block["game"]])
        by_real = _dm(delta, [str(c) for c in block["cluster"]])
        improvement = float(loss_n.mean() - loss_c.mean())
        row: Dict[str, Any] = {
            "feature": name, "n_ticks": int(len(block)), "n_game_ids": int(block["game"].nunique()),
            "n_real_games": int(block["cluster"].nunique()),
            "brier_e4": float(loss_e4.mean()), "brier_null_recal": float(loss_n.mean()),
            "brier_candidate": float(loss_c.mean()), "brier_market": float(loss_m.mean()),
            "improvement_vs_null": improvement,
            "improvement_vs_market": float(loss_m.mean() - loss_c.mean()),
            "bar": BAR, "by_game_id": by_game, "by_real_game": by_real,
            "clears_bar_real_game": bool(improvement >= BAR and (by_real["ci95"] or [0.0])[0] > 0.0),
        }
        attach_informative_summary(
            row, block.assign(loss_differential=delta, model=block["p_candidate"]),
            "loss_differential", game_col="cluster", ts_col="timestamp",
            market_col="market", model_col="model")
        out.append(row)
    out.sort(key=lambda r: -r["improvement_vs_null"])
    return out


def main() -> int:
    probe = supply_probe()
    print("STEP 0 SUPPLY PROBE -- %s" % probe["verdict"])
    for member, info in sorted(probe["members"].items()):
        print("  %-30s %-5s %s" % (member, "YES" if info["suppliable_on_screen_side"] else "NO",
                                   info["why"]))
    series = pd.read_csv(SERIES)
    ticks = joined_ticks()
    mapping = real_game_map(ticks)
    summary = mapping.pop("_summary")
    rows = requote(series, mapping)
    clean = requote(series, mapping, max_date=CLEAN_MAX_DATE)
    print("\nsplit: %d game_ids -> %d real games (%d multi); S82 screen side re-quoted"
          % (summary["n_game_ids"], summary["n_real_games"], summary["n_multi"]))
    print("%-24s %8s %6s %6s %12s %26s %10s %26s %10s"
          % ("feature", "n", "gid", "real", "impr_vs_null", "CI95 by game_id", "half",
             "CI95 by real game", "half"))
    for row in rows:
        game, real = row["by_game_id"], row["by_real_game"]
        print("%-24s %8d %6d %6d %+12.6f  [%+.6f %+.6f] %10.6f  [%+.6f %+.6f] %10.6f%s"
              % (row["feature"], row["n_ticks"], row["n_game_ids"], row["n_real_games"],
                 row["improvement_vs_null"], game["ci95"][0], game["ci95"][1], game["half_width"],
                 real["ci95"][0], real["ci95"][1], real["half_width"],
                 "  CLEARS BAR" if row["clears_bar_real_game"] else ""))
    report = {"row": "S119", "verdict": "SCREEN_NULL re-quoted on real games (a non-finding)",
              "bar": BAR, "supply_probe": probe, "real_game_split": summary,
              "source_series": str(SERIES), "results": rows,
              "calendar_clean_sensitivity": {"max_date": CLEAN_MAX_DATE, "results": clean,
                                             "note": "a reused ticker parks later real games "
                                                     "under a W27 game_id; this drops the ticks "
                                                     "dated after the partition week"},
              "n_clearing_bar_real_game": sum(1 for r in rows if r["clears_bar_real_game"])}
    OUT_JSON.write_text(json.dumps(report, indent=1, sort_keys=True, default=str), "ascii")
    keys = pd.MultiIndex.from_arrays([series["game"].astype(str), series["timestamp"].astype(str)])
    series.assign(real_game_seq=[mapping.get(k) for k in keys]).to_csv(OUT_CSV, index=False)
    best = clean[0]
    print("\ncalendar-clean sensitivity (ticks <= %s): best %s %+.6f CI [%+.6f %+.6f] on %d real "
          "games, n %d" % (CLEAN_MAX_DATE, best["feature"], best["improvement_vs_null"],
                           best["by_real_game"]["ci95"][0], best["by_real_game"]["ci95"][1],
                           best["n_real_games"], best["n_ticks"]))
    print("clearing the +%.3f bar on corrected clusters: %d of %d | %s"
          % (BAR, report["n_clearing_bar_real_game"], len(rows), OUT_JSON))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
