"""scripts.platformkit.eval_gate.s93_mlb_every_tick -- S93 PREMISE CENSUS (Step 0 only).

The S93 row rests on one premise: that the 12,772,159-row / 3,780-event MLB moneyline
corpus in data/cache/inplay_odds/mlb_price_series.parquet can be given a model series, so
the S82 in-game screen can be re-run on ~24x the games and its CI half-width can fall from
~0.005 to the 0.002 target. That needs STATE at tick time, and this module measures how
much of it exists ON DISK (never a fetch).

WHAT THE MARKET HALF CARRIES: sport, venue, game_date, ticker_or_slug, event_key,
market_type, side, ts, prob, traded, close_time, result_where_known. A price and a
timestamp. NO score, NO inning, NO half, NO outs -- no state column of any kind.

WHAT SUPPLIES STATE: only live captures, all of them from 2026-06-19 on --
data/cache/ingame_grade_joined/mlb (the S82 corpus, rich state_summary),
data/domains/mlb/espn_wp/_archive/*_series.json (wallclock + score, and it carries the
Kalshi capture_name, so it is joinable), data/cache/ingame_grade/mlb (score/inning/half
only, keyed by ESPN event id with no on-disk bridge), data/domains/mlb/gumbo_live/_archive
(123 game_pk, 2026-07-04..07-15). The historical pitch corpus
data/cache/statcast/savant_full__*.parquet holds state for every 2023-2026 pitch but has
NO wall clock on any of its 42 columns, so a 60-second market tick cannot be placed in it.

A CENSUS IS A NON-FINDING. No prereg seal, no ledger row, no K read, no charge.
Calibration language only. ASCII only.
Per-file test: python -m pytest tests/platformkit/ingame/test_s93_mlb_every_tick.py -q
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
PRICES = REPO / "data" / "cache" / "inplay_odds" / "mlb_price_series.parquet"
JOINED = REPO / "data" / "cache" / "ingame_grade_joined" / "mlb"
ESPN_WP = REPO / "data" / "domains" / "mlb" / "espn_wp" / "_archive"
RAW_GRADE = REPO / "data" / "cache" / "ingame_grade" / "mlb"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s93_mlb_every_tick_premise_2026-09-03"

BAR = 0.004                  # the S58/S82 in-game bar; never moved (Q3)
TARGET_HALF_WIDTH = 0.002    # the S93 row's own target; never moved (Q3)
S82_SCREEN_CLUSTERS = 41     # S82 memo, SCREEN side
S82_HALF_WIDTH = 0.0053035   # S82 best feature tick_index_in_game: (0.008636 + 0.001971) / 2
SCREEN_SHARE = 41.0 / 227.0  # S82: 41 SCREEN clusters out of 227 scored games


def moneyline_events(prices: pd.DataFrame) -> pd.DataFrame:
    """One row per moneyline event whose outcome is known: venue, first game_date, n ticks."""
    known = prices["result_where_known"].notna() & (prices["result_where_known"].astype(str) != "")
    ml = prices[(prices["market_type"] == "moneyline") & known]
    out = ml.groupby("event_key").agg(venue=("venue", "first"), game_date=("game_date", "min"),
                                      n_ticks=("venue", "size"))
    return out.sort_index()


def state_bearing_tickers(joined_dir: Path = JOINED, espn_wp_dir: Path = ESPN_WP) -> Dict[str, str]:
    """Kalshi tickers for which a per-tick state series exists on disk, by source.

    The joined store is named by ticker directly; the ESPN win-probability captures carry
    `capture_name` (the ticker) beside their own event_id, and that is the ONLY on-disk
    ESPN-id -> ticker bridge (game_pk_bridge_live.py is a live-feed module, not one).
    """
    found: Dict[str, str] = {}
    for path in sorted(Path(joined_dir).glob("*.jsonl")):
        found[path.stem] = "ingame_grade_joined"
    for path in sorted(Path(espn_wp_dir).glob("*_series.json")):
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("capture_name")
        except (ValueError, OSError):
            continue
        if name:
            found.setdefault(str(name), "espn_wp_series")
    return found


def clusters_for_half_width(n_clusters: int, half_width: float, target: float) -> int:
    """Game clusters needed for `target`: a clustered CI shrinks as 1/sqrt(n_clusters)."""
    if target <= 0.0 or half_width <= 0.0:
        raise ValueError("half widths must be positive")
    return int(math.ceil(n_clusters * (half_width / target) ** 2))


def census(events: pd.DataFrame, tickers: Mapping[str, str],
           n_raw_state_games: int = 0) -> Dict[str, Any]:
    """The premise table: how much of the market corpus can be given a state series."""
    with_state = sorted(set(events.index) & set(tickers))
    window = [events.at[t, "game_date"] for t in with_state]
    lo, hi = (min(window), max(window)) if window else (None, None)
    in_window = (events[(events["game_date"] >= lo) & (events["game_date"] <= hi)]
                 if lo is not None else events.iloc[0:0])
    need = clusters_for_half_width(S82_SCREEN_CLUSTERS, S82_HALF_WIDTH, TARGET_HALF_WIDTH)
    reachable_screen = int(round(len(with_state) * SCREEN_SHARE))
    return {
        "corpus": {"path": str(PRICES), "n_events": int(len(events)),
                   "n_ticks": int(events["n_ticks"].sum()),
                   "date_min": str(events["game_date"].min()),
                   "date_max": str(events["game_date"].max()),
                   "by_venue": {str(v): int(n) for v, n in events["venue"].value_counts().items()},
                   "state_columns": []},
        "state_sources": {"n_tickers_on_disk": len(tickers),
                          "by_source": {s: sum(1 for v in tickers.values() if v == s)
                                        for s in sorted(set(tickers.values()))},
                          "n_espn_keyed_unbridged": int(n_raw_state_games)},
        "reconstructable": {
            "n_events": len(with_state), "share": round(len(with_state) / max(1, len(events)), 6),
            "capture_window": [lo, hi],
            "n_events_in_capture_window": int(len(in_window)),
            "n_events_outside_window_no_state_possible": int(len(events) - len(in_window)),
        },
        "resolution": {"bar": BAR, "target_half_width": TARGET_HALF_WIDTH,
                       "s82_screen_clusters": S82_SCREEN_CLUSTERS,
                       "s82_half_width": S82_HALF_WIDTH,
                       "screen_clusters_needed": need,
                       "scored_games_needed": int(math.ceil(need / SCREEN_SHARE)),
                       "screen_clusters_reachable_on_disk": reachable_screen,
                       "resolvable": bool(reachable_screen >= need)},
        "verdict": "CLOSED AT LIMIT" if reachable_screen < need else "BUILDABLE",
        "edge_claimed": False,
    }


def run(out_dir: Path = OUT_DIR, stem: str = STEM, prices_path: Path = PRICES) -> Dict[str, Any]:
    cols = ["venue", "game_date", "event_key", "market_type", "result_where_known"]
    events = moneyline_events(pd.read_parquet(prices_path, columns=cols))
    raw = len({p.stem for p in Path(RAW_GRADE).glob("*.jsonl")}) if Path(RAW_GRADE).exists() else 0
    report = census(events, state_bearing_tickers(), raw)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / (stem + ".json")).write_text(
        json.dumps(report, indent=1, sort_keys=True, default=str), encoding="ascii")
    return report


def main() -> int:
    r = run()
    c, s, res = r["corpus"], r["reconstructable"], r["resolution"]
    print("S93 PREMISE %s | corpus %d events / %d ticks %s..%s | state columns %s"
          % (r["verdict"], c["n_events"], c["n_ticks"], c["date_min"], c["date_max"],
             c["state_columns"] or "NONE"))
    print("  state on disk: %s | ESPN-keyed unbridged %d"
          % (r["state_sources"]["by_source"], r["state_sources"]["n_espn_keyed_unbridged"]))
    print("  reconstructable %d / %d (%.2f pct) in %s..%s; %d events lie outside any capture"
          % (s["n_events"], c["n_events"], 100.0 * s["share"], s["capture_window"][0],
             s["capture_window"][1], s["n_events_outside_window_no_state_possible"]))
    print("  half-width %.6f at %d clusters -> %d clusters (%d scored games) for %.4f; reachable %d"
          % (res["s82_half_width"], res["s82_screen_clusters"], res["screen_clusters_needed"],
             res["scored_games_needed"], res["target_half_width"],
             res["screen_clusters_reachable_on_disk"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
