"""scripts.platformkit.interaction_factory.builders_public_splits -- B6: MLB
PUBLIC-SPLITS CROWD conditioning features (mlb_public_splits_self_cross
template), same file-per-builder convention as builders_market_micro.py (B5).

BINDING FRAME: every attr below is a CONDITIONING FEATURE for a pregame model
-- NEVER a bet-against-the-public / edge signal. The market is the benchmark,
not the prey. See .claude/rules/no-edge-claims.md.

STEP0 PREMISE (checked live this session, 2026-07-13):
 * data/cache/public_splits/mlb/*.jsonl -- written by the m41_public_splits
   daemon (scripts/platformkit/data_frontier/an_public_splits.py), Action
   Network v2 scoreboard. 4 daily files (2026-07-09..2026-07-12), 5116 rows,
   59 distinct games, one row per (game, book, market, side, fetched_at)
   snapshot -- MULTIPLE fetched_at snapshots per game per day (batch pulls),
   so "last pregame snapshot" is a real, non-trivial aggregation, not a
   single fixed row. tickets_pct/money_pct populated for 4402/5116 rows
   (86%) -- NOT pay-gated in-season (matches the module's own prior finding).
   Join key to a game: (home_abbr, away_abbr, start_time) -- this feed's own
   `game_id` is Action Network's numeric id, unrelated to ESPN's event_id
   (unlike B5's own line_history corpus, whose game_id already happens to be
   ESPN-dialect). Below 300-game MIN_N (runner.py) -- registered anyway per
   this lane's rails (>=50 games on disk, honestly NOT_TESTABLE until the
   daemon accrues more days; see runner.py MIN_N gate).
 * OUTCOME SOURCE -- same espn_boxscores.parquet B5 substituted in (mtime
   2026-07-13, STATUS_FINAL through 2026-07-12). Its own id (`event_id`) is
   an ESPN-dialect numeric string, NOT this corpus's `game_id` -- so unlike
   B5's exact-id join, this module bridges via (home_abbr, away_abbr, LOCAL
   calendar date). Team-code mismatch caught live: this feed spells the
   White Sox `CWS`, espn_boxscores spells them `CHW` -- one alias entry
   fixes it (verified: 07-13 game "CWS vs ATH" home lookup resolves through
   the alias, no other abbr differs across the 30-team set observed).
 * DAY-BOUNDARY LANDMINE CAUGHT LIVE (would have silently mismatched real
   games): a naive "UTC calendar date, then UTC-date-minus-1" bridge (the
   convention builders_market_micro._bridge_to_game_pk uses against
   probables.parquet) picks the WRONG game whenever the same two teams play
   on back-to-back days (a normal MLB series) -- e.g. TEX@HOU game_id 291719
   (start 2026-07-11T00:05Z) naively resolves to event 401816122 (the
   07-11 game) under raw UTC-date, but its TRUE local (Houston, Central)
   calendar date is 2026-07-10, i.e. event 401816107 -- verified live, both
   candidate dates independently resolve to a DIFFERENT real FINAL game for
   45/59 corpus rows (a same-matchup-on-consecutive-days collision, not a
   genuine ambiguity) so a "drop if both UTC candidates match" rule would
   have thrown away most of the corpus for the WRONG reason. Fixed by
   converting each game's commence timestamp to the HOME team's actual local
   timezone (a static 30-team IANA-zone table, zoneinfo handles DST) before
   taking the calendar date -- this resolves the true local game-date
   unambiguously. Live result: 56/59 games bridge to a unique STATUS_FINAL
   event_id, 0 duplicate event_ids, 0 team-pair collisions (verified via
   `matched['event_id'].duplicated().sum() == 0`). The 3 non-bridged games
   are a genuine PIT@MIL doubleheader (2 distinct FINAL event_ids for one
   home/away/date key, dropped per the same never-guess convention B5's
   _bridge_to_game_pk already uses) plus one PIT@MIL game absent from
   espn_boxscores entirely (likely rescheduled).
 * CROSS-TEMPLATE OVERLAP CHECKED LIVE: build_market_micro_corpus() (B5,
   line_history 2026-06-18+) covers all 56 of this module's bridged games
   (verified live: `ps_ids & mm_ids` has 56/56 members) -- the natural
   cross exists today, not NOT_TESTABLE.

ATTRS (STATIC_POOLS key "mlb_public_splits_asof", atomic_unit "game"), all
computed ONLY from this game's own pregame snapshots (fetched_at <=
start_time -- the leak trap, same within-game temporal-cutoff framing B5's
docstring uses; market/crowd data is exogenous, no cross-game as-of shift
needed):
 * public_bet_pct_home / public_money_pct_home = mean tickets%/money% on the
   HOME side of the moneyline market, pooled across books present at the
   LAST pregame snapshot timestamp. NaN if no pregame moneyline rows, or the
   book(s) present at that timestamp never populated the field.
 * bet_money_divergence = |public_bet_pct_home - public_money_pct_home| --
   the classic bet%-vs-money%-split proxy (a large gap flags that the two
   crowds disagree, i.e. many small tickets vs fewer large ones on opposite
   sides). Named exactly per this lane's spec; no "sharp" language used.
 * public_line_gap = signed continuous gap between the pooled moneyline's
   OWN implied-probability move (open pregame snapshot -> last pregame
   snapshot, American-odds -> implied-prob conversion so the metric is
   monotonic) and the public's ticket-majority side at the close: positive
   = the market moved WITH the ticket-majority side, negative = AGAINST it.
   NaN if <2 distinct pregame snapshot timestamps, either side's odds are
   missing, or the ticket split is exactly 50/50 (no majority to sign by).

OUTCOME: y = home_win (home_score > away_score, espn_boxscores STATUS_FINAL
rows only) -- the natural target for a moneyline-split conditioning feature
(B5's own outcome, total_runs, does not apply to a moneyline-only feed).

LEAK RULE (binding): every attr is built from a per-game snapshot table
ALREADY FILTERED to fetched_at <= start_time before any aggregation -- see
compute_public_splits_game_features's internal filter and this module's
poison-snapshot test.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_public_splits.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.platformkit.interaction_factory import builders_market_micro as _bmm

REPO = Path(__file__).resolve().parents[3]
_PUBLIC_SPLITS_DIR = REPO / "data" / "cache" / "public_splits" / "mlb"
_ESPN_BOX = REPO / "data" / "domains" / "mlb" / "espn_boxscores.parquet"
_PUBLIC_SPLITS_CORPUS_ID = "an_public_splits_mlb_x_espn_boxscores"
_CROSS_CORPUS_ID = "an_public_splits_x_line_history_market_micro_mlb"

# Action Network -> espn_boxscores team-code alias (only known mismatch,
# verified live against the 30-team set on disk).
_ABBR_ALIAS = {"CWS": "CHW"}

# Home team -> its ballpark's IANA timezone, used to resolve the TRUE local
# game date from a UTC commence timestamp (see module docstring's day-
# boundary landmine finding). Static MLB geography, zoneinfo handles DST.
_HOME_TZ = {
    "ARI": "America/Phoenix", "ATL": "America/New_York", "BAL": "America/New_York",
    "BOS": "America/New_York", "CHC": "America/Chicago", "CHW": "America/Chicago",
    "CIN": "America/New_York", "CLE": "America/New_York", "COL": "America/Denver",
    "DET": "America/New_York", "HOU": "America/Chicago", "KC": "America/Chicago",
    "LAA": "America/Los_Angeles", "LAD": "America/Los_Angeles", "MIA": "America/New_York",
    "MIL": "America/Chicago", "MIN": "America/Chicago", "NYM": "America/New_York",
    "NYY": "America/New_York", "PHI": "America/New_York", "PIT": "America/New_York",
    "SD": "America/Los_Angeles", "SEA": "America/Los_Angeles", "SF": "America/Los_Angeles",
    "STL": "America/Chicago", "TB": "America/New_York", "TEX": "America/Chicago",
    "TOR": "America/New_York", "WSH": "America/New_York", "ATH": "America/Los_Angeles",
}

PUBLIC_SPLITS_POOL_ATTRS = (
    "public_bet_pct_home", "public_money_pct_home",
    "bet_money_divergence", "public_line_gap",
)


def _implied_prob(american_odds: float) -> float:
    """American odds -> implied win probability (monotonic, unlike raw
    odds across the +100/-100 boundary)."""
    if american_odds < 0:
        return -american_odds / (-american_odds + 100.0)
    return 100.0 / (american_odds + 100.0)


def compute_public_splits_game_features(snaps: pd.DataFrame) -> Dict[str, float]:
    """One game's crowd-split features from its RAW (possibly post-commence-
    contaminated) moneyline snapshot rows. `snaps` columns: fetched_dt,
    commence_dt (tz-aware Timestamps), side ('home'/'away'), tickets_pct,
    money_pct, odds. LEAK TRAP applied first (binding): only fetched_dt <=
    commence_dt rows ever reach the aggregation below."""
    out = {a: float("nan") for a in PUBLIC_SPLITS_POOL_ATTRS}
    s = snaps[snaps["fetched_dt"] <= snaps["commence_dt"]]
    if s.empty:
        return out
    ts_sorted = sorted(s["fetched_dt"].unique())
    last_ts = ts_sorted[-1]
    home_last = s[(s["fetched_dt"] == last_ts) & (s["side"] == "home")]
    bet_pct_home = float(home_last["tickets_pct"].mean()) if not home_last.empty else float("nan")
    money_pct_home = float(home_last["money_pct"].mean()) if not home_last.empty else float("nan")
    out["public_bet_pct_home"] = bet_pct_home
    out["public_money_pct_home"] = money_pct_home
    out["bet_money_divergence"] = abs(bet_pct_home - money_pct_home)  # NaN propagates
    if len(ts_sorted) >= 2 and pd.notna(bet_pct_home) and bet_pct_home != 50.0:
        open_ts = ts_sorted[0]
        home_open = s[(s["fetched_dt"] == open_ts) & (s["side"] == "home")]
        odds_open = home_open["odds"].mean() if not home_open.empty else float("nan")
        odds_close = home_last["odds"].mean() if not home_last.empty else float("nan")
        if pd.notna(odds_open) and pd.notna(odds_close):
            move = _implied_prob(odds_close) - _implied_prob(odds_open)
            sign = 1.0 if bet_pct_home > 50.0 else -1.0
            out["public_line_gap"] = move * sign
    return out


def _load_moneyline_snapshots() -> pd.DataFrame:
    """Every moneyline row across the public_splits feed, one row per
    (game, book, side, fetched_at)."""
    rows: List[Dict[str, Any]] = []
    for fn in sorted(_PUBLIC_SPLITS_DIR.glob("*.jsonl")):
        with open(fn, encoding="ascii") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("market") == "moneyline":
                    rows.append(r)
    cols = ["game_id", "home_abbr", "away_abbr", "start_time", "fetched_at",
            "side", "tickets_pct", "money_pct", "odds"]
    if not rows:
        return pd.DataFrame(columns=cols + ["fetched_dt", "commence_dt"])
    df = pd.DataFrame(rows)[cols]
    df["fetched_dt"] = pd.to_datetime(df["fetched_at"], format="ISO8601", utc=True)
    df["commence_dt"] = pd.to_datetime(df["start_time"], format="ISO8601", utc=True)
    return df


def _bridge_to_espn(keys: pd.DataFrame) -> pd.DataFrame:
    """(game_id, home_abbr, away_abbr, start_time) -> espn event_id/venue/
    home_win via team-abbr + HOME-timezone-local calendar date (see module
    docstring's day-boundary landmine). A home team missing from _HOME_TZ,
    or a (home,away,date) key matching >1 distinct FINAL event_id
    (doubleheader), is honestly dropped -- never guessed."""
    k = keys.copy()
    k["home_n"] = k["home_abbr"].replace(_ABBR_ALIAS)
    k["away_n"] = k["away_abbr"].replace(_ABBR_ALIAS)
    k["commence_dt"] = pd.to_datetime(k["start_time"], format="ISO8601", utc=True)
    k = k[k["home_n"].isin(_HOME_TZ)].copy()
    k["local_date"] = [
        row.commence_dt.tz_convert(ZoneInfo(_HOME_TZ[row.home_n])).date().isoformat()
        for row in k.itertuples()
    ]

    box = pd.read_parquet(str(_ESPN_BOX))
    box = box[box["status"] == "STATUS_FINAL"].copy()
    box["date_str"] = box["date"].dt.date.astype(str)
    n_ev = box.groupby(["home_abbr", "away_abbr", "date_str"])["event_id"].transform("nunique")
    box_u = box[n_ev == 1].drop_duplicates(subset=["home_abbr", "away_abbr", "date_str"])
    box_u = box_u[["home_abbr", "away_abbr", "date_str", "event_id", "venue",
                    "home_score", "away_score"]].rename(
        columns={"home_abbr": "eh", "away_abbr": "ea", "date_str": "ed"})

    m = k.merge(box_u, left_on=["home_n", "away_n", "local_date"],
                right_on=["eh", "ea", "ed"], how="inner")
    m["home_win"] = (m["home_score"] > m["away_score"]).astype(float)
    return m[["game_id", "event_id", "venue", "home_win"]]


def build_public_splits_corpus() -> pd.DataFrame:
    """Game-grain frame: raw feature columns (PUBLIC_SPLITS_POOL_ATTRS) +
    event_id (kept for the cross builder's market-micro bridge) + venue/
    home_win (espn_boxscores, team+local-date bridge, STATUS_FINAL only).
    Games that never resolve a unique FINAL boxscore are dropped (inner
    join), never guessed."""
    snaps = _load_moneyline_snapshots()
    empty_cols = ["game_id", "venue", "home_win", "event_id", *PUBLIC_SPLITS_POOL_ATTRS]
    if snaps.empty:
        return pd.DataFrame(columns=empty_cols)
    keys = snaps.drop_duplicates(subset=["game_id"])[["game_id", "home_abbr", "away_abbr", "start_time"]]
    feats = snaps.groupby("game_id", as_index=False).apply(
        lambda g: pd.Series(compute_public_splits_game_features(g)), include_groups=False)
    feats = feats.merge(keys, on="game_id", how="left")
    bridge = _bridge_to_espn(keys)
    if bridge.empty:
        return pd.DataFrame(columns=empty_cols)
    return feats.merge(bridge, on="game_id", how="inner")


def build_public_splits_game_frame(corpus: pd.DataFrame, attrs: List[str]) -> pd.DataFrame:
    d = corpus.copy()
    d["y"] = d["home_win"]
    for a in attrs:
        if a in PUBLIC_SPLITS_POOL_ATTRS and a in d.columns:
            d["asof__" + a] = d[a]
    keep = ["game_id", "venue", "y"] + [
        "asof__" + a for a in attrs if ("asof__" + a) in d.columns]
    return d[keep].copy()


def _mlb_public_splits_asof_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _PUBLIC_SPLITS_DIR.exists() or not any(_PUBLIC_SPLITS_DIR.glob("*.jsonl")) or not _ESPN_BOX.exists():
        return None
    corpus = build_public_splits_corpus()
    if corpus.empty:
        return None
    frame = build_public_splits_game_frame(corpus, attrs)
    return {"frame": frame, "cluster": "venue", "corpus": _PUBLIC_SPLITS_CORPUS_ID, "kind": "logit"}


def _mlb_public_splits_market_micro_cross_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _PUBLIC_SPLITS_DIR.exists() or not any(_PUBLIC_SPLITS_DIR.glob("*.jsonl")) or not _ESPN_BOX.exists():
        return None
    ps_attrs = [a for a in attrs if a in PUBLIC_SPLITS_POOL_ATTRS]
    mm_attrs = [a for a in attrs if a in _bmm.MARKET_MICRO_POOL_ATTRS]
    ps_corpus = build_public_splits_corpus()
    if ps_corpus.empty:
        return None
    ps_frame = build_public_splits_game_frame(ps_corpus, ps_attrs)
    ps_frame = ps_frame.merge(ps_corpus[["game_id", "event_id"]], on="game_id", how="left")
    mm_corpus = _bmm.build_market_micro_corpus()
    if mm_corpus.empty:
        return None
    mm_frame = _bmm.build_market_micro_game_frame(mm_corpus, mm_attrs).drop(
        columns=["y", "venue"]).rename(columns={"game_id": "espn_game_id"})
    merged = ps_frame.merge(mm_frame, left_on="event_id", right_on="espn_game_id",
                             how="inner").drop(columns=["event_id", "espn_game_id"])
    if merged.empty:
        return None
    return {"frame": merged, "cluster": "venue", "corpus": _CROSS_CORPUS_ID, "kind": "logit"}


__all__ = [
    "compute_public_splits_game_features", "build_public_splits_corpus", "build_public_splits_game_frame",
    "_mlb_public_splits_asof_builder", "_mlb_public_splits_market_micro_cross_builder",
    "PUBLIC_SPLITS_POOL_ATTRS",
]
