"""Systematic edge mining: search (stat x edge-magnitude x context) for
model-vs-line DISAGREEMENTS that are profitable OUT-OF-SAMPLE and ACROSS SEASONS.

Reframe: stop optimizing MAE (at ceiling). Optimize EDGE directly = the
model-vs-market disagreement that WINS, conditioned by context, validated on
bet OUTCOMES (P(bet wins)), gated cross-season.

This is the disciplined, anti-overfit generalization of the AST/pace finding.
The ONLY antidote to in-sample pattern mining (how the fake +18.38% was born):
  - temporal split (train early half, test held-out late half)
  - cross-SEASON replication (2024-25 oddsapi)
  - >=1 independent corpus (extended_oos, different book)
  - |odds| >= 100 ALWAYS (drops the +900%-payout artifact)
  - NO in-sample filter tuning on the test set

Corpora (all canonical schema: date,player,opp,venue,stat,closing_line,
over_odds,under_odds,actual_value):
  - MAIN (2025-26):     benashkar_2026_canonical.csv      (DK/FD/MGM)
  - 2ND CORPUS:         extended_oos_canonical.csv        (diff book, mostly 2024 playoffs window)
  - CROSS-SEASON:       regular_season_2024_25_oddsapi.csv (2024-25 SEASON)
  - aux 2025-26 reg:    regular_season_2025_26_oddsapi.csv

Bet side = sign(pred - line) from prod-stack OOF (pregame_oof.parquet).
Label   = bet won at ACTUAL odds.

Outputs JSON to data/cache/edge_mining.json; the .md report is written by hand.
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_LINES = _ROOT / "data" / "external" / "historical_lines"
_NBA = _ROOT / "data" / "nba"
_OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
_TEAM_ADV = _ROOT / "data" / "team_advanced_stats.parquet"
_OUT = _ROOT / "data" / "cache" / "edge_mining.json"

STAT_COLS = {"pts": "PTS", "reb": "REB", "ast": "AST",
             "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}

CORPORA = {
    "benashkar_2526": "benashkar_2026_canonical.csv",       # MAIN 2025-26 (Jan-May 2026, DK/FD/MGM)
    "oddsapi_2425": "regular_season_2024_25_oddsapi.csv",    # CROSS-SEASON (2024-25)
    "oddsapi_2526reg": "regular_season_2025_26_oddsapi.csv", # 2025-26 reg, diff scrape (Oct25-Apr26)
    "reisneriv_2024po": "reisneriv_2024_canonical.csv",      # 2nd corpus: 2024 PLAYOFFS (diff season+book)
    "playoffs_2526": "playoffs_2025_26_oddsapi.csv",         # 2026 playoffs
    # extended_oos_canonical.csv EXCLUDED: after OOF-join it is byte-identical
    # to benashkar_2526 (same 3751 keys) -> NOT an independent corpus.
}

MIN_ODDS = 100.0  # |odds| >= 100 ALWAYS


# ─────────────────────────────────────────────────────────────────────
# loaders
# ─────────────────────────────────────────────────────────────────────
def build_name_to_pid() -> dict:
    out = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        p = _NBA / f"player_avgs_{season}.json"
        if not p.exists():
            continue
        try:
            for name_lc, info in json.load(open(p, encoding="utf-8")).items():
                pid = info.get("player_id")
                if pid is not None:
                    out[name_lc.strip().lower()] = int(pid)
        except Exception:
            continue
    return out


def load_oof_index() -> dict:
    df = pd.read_parquet(_OOF)
    df["gd"] = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")
    idx = {}
    for r in df.itertuples(index=False):
        idx[(int(r.player_id), r.gd, r.stat)] = float(r.oof_pred)
    return idx


# ── leak-free context from gamelogs (strictly prior games) ──
_GL_CACHE: dict = {}


def _parse_glog_date(s):
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def load_gamelog(pid: int):
    if pid in _GL_CACHE:
        return _GL_CACHE[pid]
    rows = []
    for season in ("2023-24", "2024-25", "2025-26"):
        p = _NBA / f"gamelog_{pid}_{season}.json"
        if not p.exists():
            continue
        try:
            for r in json.load(open(p, encoding="utf-8")):
                d = _parse_glog_date(r.get("GAME_DATE", ""))
                if d:
                    rows.append((d, r))
        except Exception:
            continue
    rows.sort(key=lambda kv: kv[0])
    _GL_CACHE[pid] = rows
    return rows


def context_from_gamelog(pid: int, gdate: datetime) -> dict:
    """Returns leak-free context computed from games STRICTLY before gdate."""
    rows = load_gamelog(pid)
    prior = [(d, r) for d, r in rows if d.date() < gdate.date()]
    if not prior:
        return {}
    mins = []
    for d, r in prior:
        try:
            mins.append(float(r.get("MIN") or 0))
        except (TypeError, ValueError):
            pass
    last_d = prior[-1][0]
    rest = (gdate.date() - last_d.date()).days
    return {
        "l10_min": float(np.mean(mins[-10:])) if mins else np.nan,
        "rest_days": float(min(rest, 7)),  # cap
        "games_played": float(len(prior)),
    }


# ── leak-free opp pace/def: expanding season-to-date team mean (prior games) ──
def build_team_context():
    """opp_pace, opp_def_rtg keyed by (tricode, date) = expanding mean of that
    team's games STRICTLY before date, within the same season window.
    Only covers up through 2025-04 (team_advanced_stats has no 2025-26)."""
    if not _TEAM_ADV.exists():
        return {}
    df = pd.read_parquet(_TEAM_ADV).sort_values(["team_tricode", "game_date"])
    df["game_date"] = pd.to_datetime(df["game_date"])
    out = {}
    for tri, g in df.groupby("team_tricode"):
        g = g.sort_values("game_date")
        # expanding mean shifted by 1 (strictly prior)
        pace = g["pace"].expanding().mean().shift(1)
        drtg = g["def_rtg"].expanding().mean().shift(1)
        for dt, p, d in zip(g["game_date"], pace, drtg):
            out[(tri, dt.strftime("%Y-%m-%d"))] = (p, d)
    # also build a per-(tri) fallback = full-season-to-date last value lookup
    return out


def venue_to_home(v) -> float:
    if isinstance(v, str):
        return 1.0 if v.strip().lower() == "home" else 0.0
    return np.nan


# ── opp tricode -> nearest prior team-context value (forward-fill style) ──
def opp_context_lookup(team_ctx: dict, tri: str, gd: str):
    if (tri, gd) in team_ctx:
        return team_ctx[(tri, gd)]
    # find latest prior date for this tri
    cands = [(d, v) for (t, d), v in team_ctx.items() if t == tri and d < gd]
    if not cands:
        return (np.nan, np.nan)
    cands.sort()
    return cands[-1][1]


# ─────────────────────────────────────────────────────────────────────
# build the bet table
# ─────────────────────────────────────────────────────────────────────
def payout(odds: float, win: bool) -> float:
    if not win:
        return -100.0
    return (100.0 / abs(odds) * 100.0) if odds < 0 else (odds / 100.0 * 100.0)


def build_bet_table(corpus_key: str, n2p, oofidx, team_ctx, with_ctx=True) -> pd.DataFrame:
    fn = CORPORA[corpus_key]
    df = pd.read_csv(_LINES / fn, on_bad_lines="skip", engine="python")
    df["stat"] = df["stat"].str.lower()
    df = df[df["stat"].isin(STAT_COLS)]
    df["pid"] = df["player"].str.strip().str.lower().map(n2p)
    df = df[df["pid"].notna()].copy()
    df["pid"] = df["pid"].astype(int)
    df["gd"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["gdate"] = pd.to_datetime(df["date"])
    for c in ("closing_line", "over_odds", "under_odds", "actual_value"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["closing_line", "actual_value", "over_odds", "under_odds"])

    recs = []
    for r in df.itertuples(index=False):
        pred = oofidx.get((r.pid, r.gd, r.stat))
        if pred is None:
            continue
        line = float(r.closing_line)
        actual = float(r.actual_value)
        if abs(pred - line) < 1e-9 or abs(actual - line) < 1e-9:
            continue  # no signal / push
        bet_over = pred > line
        odds = float(r.over_odds) if bet_over else float(r.under_odds)
        if abs(odds) < MIN_ODDS:
            continue  # |odds| >= 100 gate
        won = (bet_over and actual > line) or (not bet_over and actual < line)
        pnl = payout(odds, won)
        rec = {
            "corpus": corpus_key, "pid": r.pid, "gd": r.gd, "gdate": r.gdate,
            "stat": r.stat, "line": line, "actual": actual, "pred": pred,
            "edge": pred - line, "abs_edge": abs(pred - line),
            "bet_over": bet_over, "odds": odds, "won": int(won), "pnl": pnl,
            "is_home": venue_to_home(getattr(r, "venue", None)),
            "opp": str(getattr(r, "opp", "")).strip().upper(),
        }
        recs.append(rec)
    bt = pd.DataFrame(recs)
    if bt.empty or not with_ctx:
        return bt
    # attach context
    ctx_rows = []
    for r in bt.itertuples(index=False):
        c = context_from_gamelog(r.pid, r.gdate)
        op, od = opp_context_lookup(team_ctx, r.opp, r.gd)
        c["opp_pace"] = op
        c["opp_def_rtg"] = od
        ctx_rows.append(c)
    cdf = pd.DataFrame(ctx_rows)
    for col in cdf.columns:
        bt[col] = cdf[col].values
    return bt


# ─────────────────────────────────────────────────────────────────────
# ROI helpers
# ─────────────────────────────────────────────────────────────────────
def roi(sub: pd.DataFrame) -> dict:
    n = len(sub)
    if n == 0:
        return {"n": 0, "roi": 0.0, "win": 0.0, "pnl": 0.0}
    return {"n": int(n), "roi": float(sub["pnl"].mean()),
            "win": float(sub["won"].mean() * 100), "pnl": float(sub["pnl"].sum())}


if __name__ == "__main__":
    print("building name->pid + OOF index ...")
    n2p = build_name_to_pid()
    oofidx = load_oof_index()
    team_ctx = build_team_context()
    print(f"  name->pid={len(n2p)} oof={len(oofidx)} team_ctx_keys={len(team_ctx)}")

    tables = {}
    for k in CORPORA:
        bt = build_bet_table(k, n2p, oofidx, team_ctx)
        tables[k] = bt
        if len(bt):
            r = roi(bt)
            print(f"  {k:18s} n={r['n']:6d}  roi={r['roi']:+6.2f}%  win={r['win']:.1f}%")
        else:
            print(f"  {k:18s} EMPTY")

    # persist combined table for downstream analyses
    allbt = pd.concat([t for t in tables.values() if len(t)], ignore_index=True)
    allbt.to_parquet(_ROOT / "data" / "cache" / "edge_mining_bets.parquet")
    print(f"\nsaved {len(allbt)} total bets -> edge_mining_bets.parquet")
