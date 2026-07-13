"""scripts.platformkit.interaction_factory.builders_market_micro -- B5: MLB
MARKET-MICROSTRUCTURE conditioning features (mlb_market_micro_self_cross
template), split out per the builders_umpire.py / builders_weather_park.py
convention. Same contract as any other runner builder: `builder(attrs, tpl)
-> {"frame", "cluster", "corpus", "kind", ...} | None` -- registered into
runner._BUILDERS by runner.py itself.

BINDING FRAME: every attr below is a CONDITIONING FEATURE for an in-game/
pregame model -- NEVER an edge/signal to bet. The market is the benchmark,
not the prey. See .claude/rules/no-edge-claims.md.

STEP0 PREMISE (checked live this session, 2026-07-13):
 * data/cache/line_history/mlb/*.jsonl -- OUR OWN scraped feed, 27 daily
   files (2026-06-18..2026-07-13), one row per (game, market_type, side,
   book, captured_at) scrape event. MULTI-SNAPSHOT per game (one scrape
   cycle roughly every ~65s; a single game sees 300-750+ distinct
   captured_at timestamps across its pregame window) -- the ONLY joinable
   multi-snapshot-per-game corpus found on disk. Rejected: data/cache/
   odds_api/historical_odds/*_us,eu.json (2026-07-09 paid-API backfill) is
   sparse weekly/point-in-time captures, not a per-game time series -- no
   velocity is computable from it.
 * Only 2 books ever report `market_type=='total'` in this feed: espn:
   DraftKings and pinnacle (kalshi is moneyline-only and keys off its own
   ticker id dialect -- verified live, 0 kalshi rows have market_type
   'total'). A minority of rows (223/603 distinct total-market games this
   corpus, a later-arriving 'fd:'-prefixed id scheme) use a THIRD id
   dialect this module does not resolve -- they honestly drop out of the
   game_id inner-join below (never crash, never guessed).
 * OUTCOME SOURCE -- FALSE PREMISE CAUGHT: B3/B4's total_runs source
   (domains.mlb.weather_totals_gate.build_weather_corpus(), backed by
   data/domains/mlb/games_current.parquet) is STALE -- verified live, its
   max date is 2026-06-16, ZERO overlap with this odds corpus's window
   (2026-06-18 onward). domains.mlb.umpire_totals_gate's total_runs source
   is staler still (statcast_fuller__2022/2023.parquet, capped 2023-10-01).
   Substituted data/domains/mlb/espn_boxscores.parquet instead (mtime
   2026-07-13, STATUS_FINAL through 2026-07-12, 3919 unique event_id, 0
   dupes, 0 null venue) -- its `event_id` IS this odds corpus's own numeric
   `game_id` (verified live: event_id 401815806 == game_id "401815806",
   BOS/TOR 2026-06-18 on both sides), so the outcome join is an EXACT id
   match, no team-name/date fuzzy bridge needed for the self-cross pool.
   total_runs = home_score + away_score (STATUS_FINAL rows only).
 * Live measured coverage: build_market_micro_corpus() returns 334 game
   rows (any game carrying a numeric ESPN-dialect game_id that resolves to
   a STATUS_FINAL espn_boxscores row -- some of those 334 have snapshots
   only AFTER commence_time, e.g. scraping that started late, so their 4
   attrs are honestly all-NaN, not dropped at the corpus level), 31
   distinct venues (cluster key; MIN_CLUSTERS=5 easily cleared). 311/334
   have a real velocity/abs/frac (>=2 pregame snapshot timestamps);
   cross_book_divergence_at_close is non-null for 290/334 (fewer than 2
   books at the close timestamp -> honest NaN, never guessed).
 * CROSS-TEMPLATE OVERLAP CHECKED LIVE, CURRENTLY ZERO: this module's own
   games (2026-06-18+) do not overlap build_weather_park_corpus()'s date
   range (...-2026-06-16) or the umpire pool's (...2023-10-01) at all --
   the mlb_market_micro_weather_cross builder below implements the REAL
   game_pk bridge (probables.parquet's home_team/away_team display names
   match this odds corpus's own home/away strings verbatim, so no team-
   code translation is needed) but will honestly return None until
   games_current.parquet is refreshed past 2026-06-16 -- NOT_TESTABLE
   today, not a fabricated result, and it self-resolves the moment that
   refresh lands (no code change needed).

ATTRS (STATIC_POOLS key "mlb_market_micro_asof", atomic_unit "game"), all
computed ONLY from this game's own pregame snapshots (captured_at <=
commence_time -- the leak trap; a post-first-pitch snapshot must never
enter any of these 4 numbers):
 * line_move_velocity_pregame = (close_total - open_total) / hours_between
   the first and last pregame snapshot's pooled (mean-across-books-present)
   total line. NaN if <2 distinct snapshot timestamps or hours_between<=0.
 * line_move_total_abs = |close_total - open_total|.
 * cross_book_divergence_at_close = population stddev (ddof=0) of the raw
   per-book total line at the LAST pregame snapshot timestamp -- honest NaN
   if fewer than 2 books reported at that exact timestamp.
 * time_of_last_move_frac = fraction of the open->close window elapsed at
   the LAST timestamp the pooled line changed value; 0.0 if the line never
   moved; NaN under the same <2-timestamps/zero-window condition as velocity.

OUTCOME: y = total_runs (this game's own REAL total, not as-of).

LEAK RULE (binding): every attr is built from a per-game snapshot table
ALREADY FILTERED to captured_at <= commence_time before any aggregation --
see compute_market_micro_game_features's internal filter and
test_builders_market_micro.py's post-commence poison trap. Market data
is EXOGENOUS (not a downstream outcome of the game, same framing builders_
weather_park.py's wind_out_mph_raw note uses) so no cross-game as-of shift
is needed -- only the within-game temporal cutoff matters here.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_market_micro.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from scripts.platformkit.interaction_factory.builders_weather_park import (
    build_weather_park_corpus, build_weather_park_game_frame, WEATHER_POOL_ATTRS,
)

REPO = Path(__file__).resolve().parents[3]
_LINE_HISTORY_DIR = REPO / "data" / "cache" / "line_history" / "mlb"
_ESPN_BOX = REPO / "data" / "domains" / "mlb" / "espn_boxscores.parquet"
_PROBABLES = REPO / "data" / "domains" / "mlb" / "probables.parquet"
_MARKET_MICRO_SOURCES = (_LINE_HISTORY_DIR, _ESPN_BOX)
_MARKET_MICRO_CORPUS_ID = "line_history_mlb_x_espn_boxscores_market_micro"
_CROSS_CORPUS_ID = "line_history_mlb_x_probables_x_weather_park_market_micro"

MARKET_MICRO_POOL_ATTRS = (
    "line_move_velocity_pregame", "line_move_total_abs",
    "cross_book_divergence_at_close", "time_of_last_move_frac",
)


def compute_market_micro_game_features(snaps: pd.DataFrame) -> Dict[str, float]:
    """One game's total-line features from its RAW (possibly post-commence-
    contaminated) snapshot rows. `snaps` columns: captured_dt, commence_dt
    (tz-aware Timestamps), book, line. LEAK TRAP applied first (binding):
    only captured_dt <= commence_dt rows ever reach the aggregation below."""
    s = snaps[snaps["captured_dt"] <= snaps["commence_dt"]]
    out = {a: float("nan") for a in MARKET_MICRO_POOL_ATTRS}
    if s.empty:
        return out
    per_ts = s.groupby("captured_dt")["line"].mean().sort_index()
    if len(per_ts) >= 2:
        open_ts, open_line = per_ts.index[0], per_ts.iloc[0]
        close_ts, close_line = per_ts.index[-1], per_ts.iloc[-1]
        hours = (close_ts - open_ts).total_seconds() / 3600.0
        if hours > 0:
            out["line_move_velocity_pregame"] = (close_line - open_line) / hours
            changed = per_ts[per_ts.diff().fillna(0.0) != 0.0]
            last_move_ts = changed.index[-1] if len(changed) else open_ts
            out["time_of_last_move_frac"] = (last_move_ts - open_ts).total_seconds() / (
                (close_ts - open_ts).total_seconds())
        out["line_move_total_abs"] = abs(close_line - open_line)
        close_books = s.loc[s["captured_dt"] == close_ts, "line"]
        if len(close_books) >= 2:
            out["cross_book_divergence_at_close"] = float(close_books.std(ddof=0))
    return out


def _load_total_snapshots() -> pd.DataFrame:
    """Every OUR-OWN total-market row across the line_history feed, one row
    per (game, book, captured_at) -- 'over'/'under' share the same book
    line so only 'over' rows are kept (no double count)."""
    rows: List[Dict[str, Any]] = []
    for fn in sorted(_LINE_HISTORY_DIR.glob("*.jsonl")):
        with open(fn, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("market_type") == "total" and r.get("side") == "over":
                    rows.append(r)
    cols = ["game_id", "home", "away", "commence_time", "captured_at", "book", "line"]
    if not rows:
        return pd.DataFrame(columns=cols + ["captured_dt", "commence_dt"])
    df = pd.DataFrame(rows)[cols]
    df["captured_dt"] = pd.to_datetime(df["captured_at"], format="ISO8601", utc=True)
    df["commence_dt"] = pd.to_datetime(df["commence_time"], format="ISO8601", utc=True)
    return df


def build_market_micro_corpus() -> pd.DataFrame:
    """Game-grain frame: raw feature columns (see MARKET_MICRO_POOL_ATTRS) +
    home/away/commence_time (kept for the cross builder's probables bridge)
    + total_runs/venue (espn_boxscores, exact event_id==game_id match,
    STATUS_FINAL only). Games that never resolve an ESPN-dialect id or a
    FINAL boxscore are dropped (inner join), never guessed."""
    snaps = _load_total_snapshots()
    if snaps.empty:
        return pd.DataFrame(columns=["game_id", "home", "away", "commence_time",
                                      "total_runs", "venue", *MARKET_MICRO_POOL_ATTRS])
    keys = snaps.drop_duplicates(subset=["game_id"])[["game_id", "home", "away", "commence_time"]]
    feats = snaps.groupby("game_id", as_index=False).apply(
        lambda g: pd.Series(compute_market_micro_game_features(g)), include_groups=False)
    feats = feats.merge(keys, on="game_id", how="left")

    box = pd.read_parquet(str(_ESPN_BOX))
    box = box[box["status"] == "STATUS_FINAL"].copy()
    box["game_id"] = box["event_id"].astype(str)
    box["total_runs"] = box["home_score"] + box["away_score"]
    return feats.merge(box[["game_id", "venue", "total_runs"]], on="game_id", how="inner")


def build_market_micro_game_frame(corpus: pd.DataFrame, attrs: List[str]) -> pd.DataFrame:
    d = corpus.copy()
    d["y"] = d["total_runs"]
    for a in attrs:
        if a in MARKET_MICRO_POOL_ATTRS and a in d.columns:
            d["asof__" + a] = d[a]
    keep = ["game_id", "venue", "y"] + [
        "asof__" + a for a in attrs if ("asof__" + a) in d.columns]
    return d[keep].copy()


def _bridge_to_game_pk(keys: pd.DataFrame, probables: pd.DataFrame) -> pd.DataFrame:
    """(home, away, commence_time) -> game_pk via probables' own display-name
    dialect (matches this odds corpus verbatim, no team-code translation).
    Tries commence_time's UTC date, then UTC-date-minus-1 (west-coast
    evening starts roll past UTC midnight). Doubleheader-ambiguous (home,
    away, date) keys (>1 distinct game_pk) are dropped, never guessed --
    same honesty convention domains.mlb.game_pk_bridge uses."""
    prob = probables[["game_pk", "game_date", "home_team", "away_team"]].copy()
    prob["game_date_str"] = prob["game_date"].astype(str)
    n_pk = prob.groupby(["home_team", "away_team", "game_date_str"])["game_pk"].transform("nunique")
    prob_u = prob[n_pk == 1].drop_duplicates(subset=["home_team", "away_team", "game_date_str"])

    k = keys.copy()
    k["commence_dt"] = pd.to_datetime(k["commence_time"], format="ISO8601", utc=True)
    k["date_utc"] = k["commence_dt"].dt.date.astype(str)
    k["date_utc_m1"] = (k["commence_dt"] - pd.Timedelta(days=1)).dt.date.astype(str)
    m = k.merge(prob_u, left_on=["home", "away", "date_utc"],
                right_on=["home_team", "away_team", "game_date_str"], how="left")
    missing = m["game_pk"].isna()
    if missing.any():
        fb = k.loc[missing, ["home", "away", "commence_time", "date_utc_m1"]].merge(
            prob_u, left_on=["home", "away", "date_utc_m1"],
            right_on=["home_team", "away_team", "game_date_str"], how="left")
        m.loc[missing, "game_pk"] = fb["game_pk"].values
    return m[["home", "away", "commence_time", "game_pk"]].dropna(subset=["game_pk"])


def _mlb_market_micro_asof_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _LINE_HISTORY_DIR.exists() or not any(_LINE_HISTORY_DIR.glob("*.jsonl")) or not _ESPN_BOX.exists():
        return None
    corpus = build_market_micro_corpus()
    if corpus.empty:
        return None
    frame = build_market_micro_game_frame(corpus, attrs)
    return {"frame": frame, "cluster": "venue", "corpus": _MARKET_MICRO_CORPUS_ID, "kind": "ols"}


def _mlb_market_micro_weather_cross_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if (not _LINE_HISTORY_DIR.exists() or not any(_LINE_HISTORY_DIR.glob("*.jsonl"))
            or not _ESPN_BOX.exists() or not _PROBABLES.exists()):
        return None
    mm_attrs = [a for a in attrs if a in MARKET_MICRO_POOL_ATTRS]
    weather_attrs = [a for a in attrs if a in WEATHER_POOL_ATTRS]
    raw = build_market_micro_corpus()
    if raw.empty:
        return None
    bridge = _bridge_to_game_pk(raw[["home", "away", "commence_time"]].drop_duplicates(),
                                 pd.read_parquet(str(_PROBABLES)))
    if bridge.empty:
        return None
    mm = raw.merge(bridge, on=["home", "away", "commence_time"], how="inner")
    if mm.empty:
        return None
    mm_frame = build_market_micro_game_frame(mm.assign(game_id=mm["game_pk"]), mm_attrs)
    wp_frame = build_weather_park_game_frame(build_weather_park_corpus(), weather_attrs)
    merged = mm_frame.drop(columns=["venue"]).rename(columns={"game_id": "game_pk"}).merge(
        wp_frame.drop(columns=["y"]), on="game_pk", how="inner")
    if merged.empty:
        return None
    return {"frame": merged, "cluster": "venue", "corpus": _CROSS_CORPUS_ID, "kind": "ols"}


__all__ = [
    "compute_market_micro_game_features", "build_market_micro_corpus", "build_market_micro_game_frame",
    "_mlb_market_micro_asof_builder", "_mlb_market_micro_weather_cross_builder",
    "MARKET_MICRO_POOL_ATTRS",
]
