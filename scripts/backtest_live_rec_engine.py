"""backtest_live_rec_engine.py — R25_R5.

Retrospectively grade R23_P8's `live_recommendation_engine` over the
universe of NBA games for which we have ground-truth boxscores
(`data/cache/quarter_box/<gid>_q[1-4].json`).

The honest data constraint
--------------------------
The repo only ships ONE real `predictions_cache_<date>.parquet` and ONE
priced lines snapshot (2026-05-26). A literal "last 30 days" backtest of
the real engine is therefore impossible — the snapshots simply do not
exist in history.

What this script does instead
-----------------------------
* Treats every NBA game with a final boxscore (`<gid>_q4.json` present)
  as a candidate "settled" event.
* Buckets games into pseudo-"dates" by chunking sequential `game_id`s
  (the NBA API assigns ids in chronological order within a season).
* For each pseudo-date `d`, builds **point-in-time** per-player
  predictions from ONLY games strictly before `d` (shift(1).expanding
  mean and stddev). This mirrors the leak-free shape of the real model.
* Synthesises realistic FD-style lines around the predicted mean
  (`q50 ± U(-0.4, +0.4)` rounded to .5, vig -110/-110 by default).
* Runs `live_recommendation_engine.compute_recommendations` on this
  exact snapshot.
* Settles each rec against the actual boxscore.
* Sweeps `min_edge ∈ {0.03, 0.05, 0.08, 0.12}` × `top ∈ {3, 5, 10}` and
  records which config wins by ROI.

The time-leakage risk is explicit: predictions are built from games
strictly before the pseudo-date, lines are sampled from a deterministic
RNG seeded on `gid` only, and settlement uses the boxscore that the
engine never sees. The synthetic lines understate the casino's edge
(real books move on news the model can't see), so the absolute ROI is
optimistic — but the **relative ranking** of (min_edge, top) configs is
informative.

CLI:
    python scripts/backtest_live_rec_engine.py --bankroll 1000 \
        --min-edge 0.05 --top 5 --max-dates 30

Public API used by tests:
    chunk_games_to_pseudo_dates(qb_dir, n_per_date) -> list[(date_str, [gid,...])]
    build_pointintime_predictions(qb_dir, prior_gids) -> pd.DataFrame
    synthesise_lines(predictions, gids, seed) -> pd.DataFrame
    grade_recs(recs, qb_dir, gids) -> list[dict]
    run_backtest(...) -> dict
    sweep_configs(...) -> dict
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import sys
import unicodedata
from datetime import date as _date_cls
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Pull the engine + tracker primitives we need to grade results.
from scripts.live_recommendation_engine import (  # noqa: E402
    compute_recommendations,
    american_payout,
)
from scripts.live_rec_tracker import (  # noqa: E402
    _player_key,
    _grade_rec,
    _profit_for,
    _STAT_TO_BOX_FIELD,
)

DEFAULT_QB_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
DEFAULT_RESULTS_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "backtest_live_rec_results.json"
)
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SWEEP_MIN_EDGES = (0.03, 0.05, 0.08, 0.12)
SWEEP_TOPS = (3, 5, 10)


# ============================================================================ #
# Box-score loaders                                                            #
# ============================================================================ #
def _load_q4_box(gid: str, qb_dir: str) -> Optional[Dict[str, Dict[str, float]]]:
    """Return {player_key: {stat: value}} or None if the q4 file is absent."""
    path = os.path.join(qb_dir, f"{gid}_q4.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    out: Dict[str, Dict[str, float]] = {}
    for p in data.get("players") or []:
        pkey = _player_key(p.get("player_name", ""))
        if not pkey:
            continue
        row: Dict[str, float] = {"team": str(p.get("team_abbreviation") or "")}
        for fld in ("pts", "reb", "ast", "fg3m", "stl", "blk", "to"):
            try:
                row[fld] = float(p.get(fld) or 0.0)
            except Exception:
                row[fld] = 0.0
        out[pkey] = row
    return out


def _list_final_gids(qb_dir: str) -> List[str]:
    """Return sorted list of game_ids that have a q4 file."""
    paths = sorted(glob.glob(os.path.join(qb_dir, "*_q4.json")))
    return [os.path.basename(p).split("_q4")[0] for p in paths]


# ============================================================================ #
# Pseudo-date chunking                                                         #
# ============================================================================ #
def chunk_games_to_pseudo_dates(
    qb_dir: str,
    n_per_date: int = 12,
    min_chunks: int = 5,
    start_offset: int = 0,
) -> List[Tuple[str, List[str]]]:
    """Group sequential game_ids into pseudo-dates of ~n_per_date games.

    Returns [(date_str, [gid, ...]), ...] sorted ascending by date_str.
    Date strings are synthesised in YYYY-MM-DD form starting from a fixed
    base (2025-01-01) — they exist only so the rec_id hash treats each
    chunk as distinct.
    """
    gids = _list_final_gids(qb_dir)
    if not gids:
        return []
    chunks: List[List[str]] = []
    for i in range(0, len(gids), n_per_date):
        chunks.append(gids[i : i + n_per_date])
    if len(chunks) < min_chunks:
        return []
    out: List[Tuple[str, List[str]]] = []
    base = _date_cls(2025, 1, 1)
    from datetime import timedelta
    for i, ch in enumerate(chunks[start_offset:], start=start_offset):
        d = (base + timedelta(days=i)).isoformat()
        out.append((d, ch))
    return out


# ============================================================================ #
# Point-in-time predictions                                                    #
# ============================================================================ #
def build_pointintime_predictions(
    qb_dir: str,
    prior_gids: Sequence[str],
    min_games: int = 3,
) -> "pd.DataFrame":
    """For every player seen in `prior_gids`, return q10/q50/q90/sigma per stat.

    Uses ONLY the boxscores from `prior_gids`. This guarantees no leakage
    into the date being predicted.

    q50 = mean of prior games. sigma = max(stddev, 1.0) to avoid divide-by-zero.
    q10 = q50 - 1.2816 * sigma, q90 = q50 + 1.2816 * sigma.
    """
    import pandas as pd
    from math import sqrt

    # accumulate per (player, stat) -> list of values
    accum: Dict[Tuple[str, str], List[float]] = {}
    teams: Dict[str, str] = {}
    name_map: Dict[str, str] = {}
    for gid in prior_gids:
        box = _load_q4_box(gid, qb_dir)
        if not box:
            continue
        for pkey, vals in box.items():
            display_name = name_map.setdefault(pkey, pkey)
            teams.setdefault(pkey, str(vals.get("team", "")))
            for stat in STATS:
                fld = _STAT_TO_BOX_FIELD[stat]
                val = vals.get(fld)
                if val is None:
                    continue
                try:
                    accum.setdefault((pkey, stat), []).append(float(val))
                except Exception:
                    pass
    # also capture proper-case names by re-scanning a single sample game
    for gid in prior_gids[-1:]:
        path = os.path.join(qb_dir, f"{gid}_q4.json")
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for p in data.get("players") or []:
            pkey = _player_key(p.get("player_name", ""))
            if pkey and p.get("player_name"):
                name_map.setdefault(pkey, str(p["player_name"]))

    rows: List[Dict[str, Any]] = []
    for (pkey, stat), vals in accum.items():
        if len(vals) < min_games:
            continue
        mean = sum(vals) / len(vals)
        if len(vals) >= 2:
            var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
            sigma = sqrt(max(var, 0.0))
        else:
            sigma = 1.0
        sigma = max(sigma, 0.75)  # avoid degenerate band -> Normal blows up
        q10 = mean - 1.2816 * sigma
        q90 = mean + 1.2816 * sigma
        rows.append({
            "player_name": name_map.get(pkey, pkey),
            "stat":        stat,
            "team":        teams.get(pkey, ""),
            "q10":         max(q10, 0.0),
            "q50":         max(mean, 0.0),
            "q90":         max(q90, 0.0),
            "sigma":       sigma,
            "_n_prior":    len(vals),
        })
    return pd.DataFrame(rows)


# ============================================================================ #
# Synthetic lines (deterministic per game_id chunk)                            #
# ============================================================================ #
def synthesise_lines(
    df_preds: "pd.DataFrame",
    gids: Sequence[str],
    qb_dir: str,
    seed: int = 0,
    line_jitter: float = 0.4,
    odds: int = -110,
) -> "pd.DataFrame":
    """Build a `_read_lines_csv`-shaped DataFrame.

    For every (player, stat) in `df_preds` whose player ALSO appears in
    `gids`'s boxscores, sample a line around q50 with deterministic jitter
    and write OVER+UNDER prices at `odds`.

    The jitter is seeded by hash(player+stat+gid_chunk) so the test is
    reproducible. The line is rounded to the nearest .5 so it behaves
    like a sportsbook line.
    """
    import pandas as pd
    # collect players actually playing today
    playing: set = set()
    pname_for_key: Dict[str, str] = {}
    team_for_key: Dict[str, str] = {}
    game_for_player: Dict[str, str] = {}
    for gid in gids:
        box = _load_q4_box(gid, qb_dir)
        if not box:
            continue
        for pkey, vals in box.items():
            playing.add(pkey)
            team_for_key.setdefault(pkey, str(vals.get("team", "")))
            game_for_player.setdefault(pkey, gid)
    # Build lines
    chunk_token = "_".join(gids[:1]) if gids else "chunk"
    rng = random.Random(f"{seed}:{chunk_token}")
    rows: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for _, r in df_preds.iterrows():
        pkey = _player_key(r["player_name"])
        if pkey not in playing:
            continue
        q50 = float(r["q50"])
        # jitter line ~ U(-line_jitter, +line_jitter), round to .5
        jit = rng.uniform(-line_jitter, line_jitter)
        raw_line = q50 + jit
        line = round(raw_line * 2.0) / 2.0
        if line <= 0:
            line = 0.5
        rows.append({
            "captured_at": now_iso,
            "book":        "syn",
            "game_id":     game_for_player.get(pkey, ""),
            "player_id":   0,
            "player_name": r["player_name"],
            "stat":        r["stat"],
            "line":        line,
            "over_price":  odds,
            "under_price": odds,
            "start_time":  now_iso,
            "is_alt_line": False,
        })
    return pd.DataFrame(rows)


# ============================================================================ #
# Grading                                                                      #
# ============================================================================ #
def grade_recs(
    recs: List[Dict[str, Any]],
    qb_dir: str,
    gids: Sequence[str],
) -> List[Dict[str, Any]]:
    """For each rec, look up actual stat in box and return graded copies."""
    combined: Dict[str, Dict[str, float]] = {}
    for gid in gids:
        box = _load_q4_box(gid, qb_dir)
        if not box:
            continue
        for pkey, vals in box.items():
            cur = combined.get(pkey)
            if cur is None or sum(
                vals.get(f, 0) for f in ("pts", "reb", "ast")
            ) > sum(cur.get(f, 0) for f in ("pts", "reb", "ast")):
                combined[pkey] = vals
    out: List[Dict[str, Any]] = []
    for r in recs:
        pkey = _player_key(r.get("player", ""))
        stat = str(r.get("stat", "")).lower()
        side = str(r.get("side", "")).upper()
        line = float(r.get("line", 0.0))
        odds = int(r.get("odds", -110))
        bx = combined.get(pkey)
        actual: Optional[float] = None
        result = "UNGRADED"
        if bx is not None:
            fld = _STAT_TO_BOX_FIELD.get(stat, stat)
            v = bx.get(fld)
            if v is not None:
                try:
                    actual = float(v)
                    result = _grade_rec(side, line, actual)
                except Exception:
                    pass
        # stake_unit = 1.0 so profit is in units (matches live_rec_tracker math)
        profit = _profit_for(result, odds, stake=1.0)
        graded = dict(r)
        graded["actual"] = actual
        graded["result"] = result
        graded["profit"] = profit
        graded["stake_unit"] = 1.0
        out.append(graded)
    return out


# ============================================================================ #
# Per-date backtest                                                            #
# ============================================================================ #
def backtest_one_date(
    date_str: str,
    today_gids: Sequence[str],
    prior_gids: Sequence[str],
    qb_dir: str,
    bankroll: float,
    min_edge: float,
    top: int,
    seed: int = 0,
) -> Dict[str, Any]:
    df_preds = build_pointintime_predictions(qb_dir, prior_gids)
    if df_preds.empty:
        return {
            "date": date_str, "ok": False,
            "reason": "no prior games for predictions",
            "n_recs": 0, "n_graded": 0,
        }
    snapshots = synthesise_lines(
        df_preds, today_gids, qb_dir, seed=seed
    )
    if snapshots.empty:
        return {
            "date": date_str, "ok": False,
            "reason": "no overlap between predictions and tonight's players",
            "n_recs": 0, "n_graded": 0,
        }
    rec_payload = compute_recommendations(
        df_preds=df_preds,
        books={"syn": snapshots},
        out_players=set(),
        bankroll=float(bankroll),
        min_edge=float(min_edge),
        top=int(top),
    )
    recs = rec_payload.get("recommendations", [])
    graded = grade_recs(recs, qb_dir, today_gids)
    wins = sum(1 for g in graded if g["result"] == "WIN")
    losses = sum(1 for g in graded if g["result"] == "LOSS")
    pushes = sum(1 for g in graded if g["result"] == "PUSH")
    ungraded = sum(1 for g in graded if g["result"] == "UNGRADED")
    non_push = wins + losses
    win_rate = (wins / non_push) if non_push > 0 else 0.0
    total_stake = float(non_push)  # 1 unit per non-push bet
    total_profit = float(sum(g["profit"] for g in graded))
    roi = (total_profit / total_stake) if total_stake > 0 else 0.0
    mean_edge_w = sum(g["edge"] for g in graded if g["result"] == "WIN") / wins \
        if wins > 0 else None
    mean_edge_l = sum(g["edge"] for g in graded if g["result"] == "LOSS") / losses \
        if losses > 0 else None
    by_stat: Dict[str, Dict[str, float]] = {}
    for g in graded:
        s = str(g.get("stat", "")).lower()
        st = by_stat.setdefault(s, {"n": 0, "wins": 0, "losses": 0,
                                      "pushes": 0, "profit": 0.0,
                                      "stake": 0.0})
        st["n"] += 1
        if g["result"] == "WIN":
            st["wins"] += 1
            st["stake"] += 1.0
        elif g["result"] == "LOSS":
            st["losses"] += 1
            st["stake"] += 1.0
        elif g["result"] == "PUSH":
            st["pushes"] += 1
        st["profit"] += float(g["profit"])
    for s, st in by_stat.items():
        st["win_rate"] = (st["wins"] / (st["wins"] + st["losses"])) \
            if (st["wins"] + st["losses"]) > 0 else 0.0
        st["roi"] = (st["profit"] / st["stake"]) if st["stake"] > 0 else 0.0
    return {
        "date":          date_str,
        "ok":            True,
        "n_prior_gids":  len(prior_gids),
        "n_today_gids":  len(today_gids),
        "n_predictions": int(len(df_preds)),
        "n_snapshots":   int(len(snapshots)),
        "n_recs":        len(graded),
        "n_graded":      wins + losses + pushes,
        "n_ungraded":    ungraded,
        "wins":          wins,
        "losses":        losses,
        "pushes":        pushes,
        "win_rate":      round(win_rate, 4),
        "roi":           round(roi, 4),
        "total_stake":   round(total_stake, 4),
        "total_profit":  round(total_profit, 4),
        "mean_edge_win": round(mean_edge_w, 4) if mean_edge_w is not None else None,
        "mean_edge_loss": round(mean_edge_l, 4) if mean_edge_l is not None else None,
        "by_stat":       {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                              for kk, vv in v.items()}
                          for k, v in by_stat.items()},
    }


# ============================================================================ #
# Multi-date aggregation                                                       #
# ============================================================================ #
def aggregate_daily(dailies: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [d for d in dailies if d.get("ok")]
    if not ok:
        return {"ok": False, "reason": "no successful dates",
                "n_dates": 0, "n_recs": 0,
                "win_rate": 0.0, "roi": 0.0}
    wins = sum(d.get("wins", 0) for d in ok)
    losses = sum(d.get("losses", 0) for d in ok)
    pushes = sum(d.get("pushes", 0) for d in ok)
    non_push = wins + losses
    total_stake = float(non_push)
    total_profit = sum(d.get("total_profit", 0.0) for d in ok)
    win_rate = (wins / non_push) if non_push > 0 else 0.0
    roi = (total_profit / total_stake) if total_stake > 0 else 0.0
    by_stat: Dict[str, Dict[str, float]] = {}
    for d in ok:
        for s, st in (d.get("by_stat") or {}).items():
            cur = by_stat.setdefault(s, {"n": 0, "wins": 0, "losses": 0,
                                          "pushes": 0, "profit": 0.0,
                                          "stake": 0.0})
            cur["n"] += int(st.get("n", 0))
            cur["wins"] += int(st.get("wins", 0))
            cur["losses"] += int(st.get("losses", 0))
            cur["pushes"] += int(st.get("pushes", 0))
            cur["profit"] += float(st.get("profit", 0.0))
            cur["stake"] += float(st.get("stake", 0.0))
    for s, st in by_stat.items():
        st["win_rate"] = (st["wins"] / (st["wins"] + st["losses"])) \
            if (st["wins"] + st["losses"]) > 0 else 0.0
        st["roi"] = (st["profit"] / st["stake"]) if st["stake"] > 0 else 0.0
        st["win_rate"] = round(st["win_rate"], 4)
        st["roi"] = round(st["roi"], 4)
        st["profit"] = round(st["profit"], 4)
        st["stake"] = round(st["stake"], 4)
    return {
        "ok":             True,
        "n_dates":        len(ok),
        "n_recs":         wins + losses + pushes,
        "wins":           wins,
        "losses":         losses,
        "pushes":         pushes,
        "win_rate":       round(win_rate, 4),
        "roi":            round(roi, 4),
        "total_stake":    round(total_stake, 4),
        "total_profit":   round(total_profit, 4),
        "by_stat":        by_stat,
    }


# ============================================================================ #
# Top-level orchestration                                                      #
# ============================================================================ #
def run_backtest(
    *,
    qb_dir: str = DEFAULT_QB_DIR,
    bankroll: float = 1000.0,
    min_edge: float = 0.05,
    top: int = 5,
    n_per_date: int = 12,
    max_dates: Optional[int] = None,
    seed: int = 0,
) -> Dict[str, Any]:
    """Single-config backtest. Returns a payload with daily + aggregate."""
    chunks = chunk_games_to_pseudo_dates(qb_dir, n_per_date=n_per_date)
    if not chunks:
        return {"ok": False, "reason": "no game chunks built",
                "config": {"bankroll": bankroll, "min_edge": min_edge,
                           "top": top}, "dailies": [], "aggregate": {}}
    # Need at least 2 chunks (first is warm-up for predictions).
    dailies: List[Dict[str, Any]] = []
    cumulative_prior: List[str] = []
    for date_str, today_gids in chunks:
        if cumulative_prior:
            res = backtest_one_date(
                date_str=date_str, today_gids=today_gids,
                prior_gids=list(cumulative_prior), qb_dir=qb_dir,
                bankroll=bankroll, min_edge=min_edge, top=top, seed=seed,
            )
            dailies.append(res)
            if max_dates is not None and len(dailies) >= max_dates:
                cumulative_prior.extend(today_gids)
                break
        cumulative_prior.extend(today_gids)
    aggregate = aggregate_daily(dailies)
    return {
        "ok":      bool(dailies),
        "config":  {"bankroll": bankroll, "min_edge": min_edge,
                    "top": top, "n_per_date": n_per_date, "seed": seed},
        "dailies": dailies,
        "aggregate": aggregate,
    }


def sweep_configs(
    *,
    qb_dir: str = DEFAULT_QB_DIR,
    bankroll: float = 1000.0,
    n_per_date: int = 12,
    max_dates: Optional[int] = None,
    seed: int = 0,
    min_edges: Sequence[float] = SWEEP_MIN_EDGES,
    tops: Sequence[int] = SWEEP_TOPS,
) -> Dict[str, Any]:
    """Run the backtest across the cross product of (min_edge, top)."""
    matrix: List[Dict[str, Any]] = []
    for me in min_edges:
        for tp in tops:
            res = run_backtest(
                qb_dir=qb_dir, bankroll=bankroll, min_edge=float(me),
                top=int(tp), n_per_date=n_per_date,
                max_dates=max_dates, seed=seed,
            )
            agg = res.get("aggregate") or {}
            matrix.append({
                "min_edge":      float(me),
                "top":           int(tp),
                "n_dates":       int(agg.get("n_dates", 0)),
                "n_recs":        int(agg.get("n_recs", 0)),
                "wins":          int(agg.get("wins", 0)),
                "losses":        int(agg.get("losses", 0)),
                "pushes":        int(agg.get("pushes", 0)),
                "win_rate":      float(agg.get("win_rate", 0.0)),
                "roi":           float(agg.get("roi", 0.0)),
                "total_profit":  float(agg.get("total_profit", 0.0)),
            })
    # rank by ROI; tie-break by n_recs (more bets > fewer at same ROI)
    viable = [m for m in matrix if m["n_recs"] > 0]
    viable.sort(key=lambda m: (m["roi"], m["n_recs"]), reverse=True)
    best = viable[0] if viable else None
    return {
        "ok":          bool(matrix),
        "matrix":      matrix,
        "n_viable":    len(viable),
        "best_config": best,
    }


# ============================================================================ #
# CLI                                                                          #
# ============================================================================ #
def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qb-dir",      type=str,   default=DEFAULT_QB_DIR)
    ap.add_argument("--bankroll",    type=float, default=1000.0)
    ap.add_argument("--min-edge",    type=float, default=0.05)
    ap.add_argument("--top",         type=int,   default=5)
    ap.add_argument("--n-per-date",  type=int,   default=12)
    ap.add_argument("--max-dates",   type=int,   default=None)
    ap.add_argument("--seed",        type=int,   default=0)
    ap.add_argument("--out",         type=str,   default=DEFAULT_RESULTS_PATH)
    ap.add_argument("--sweep",       action="store_true")
    ap.add_argument("--json",        action="store_true")
    return ap.parse_args()


def _fmt_summary(res: Dict[str, Any]) -> str:
    if "aggregate" in res:
        a = res["aggregate"]
        c = res["config"]
        return (
            f"BACKTEST  bankroll=${c['bankroll']:.0f} "
            f"min_edge={c['min_edge']} top={c['top']}\n"
            f"  dates={a.get('n_dates',0)}  recs={a.get('n_recs',0)}  "
            f"W/L/P={a.get('wins',0)}/{a.get('losses',0)}/{a.get('pushes',0)}\n"
            f"  win-rate={a.get('win_rate',0)*100:.2f}%  "
            f"ROI={a.get('roi',0)*100:+.2f}%  "
            f"profit={a.get('total_profit',0):+.2f}u"
        )
    if "matrix" in res:
        lines = ["BACKTEST SWEEP — ranked by ROI:"]
        viable = [m for m in res["matrix"] if m["n_recs"] > 0]
        viable.sort(key=lambda m: m["roi"], reverse=True)
        lines.append(f"{'min_edge':>9} {'top':>4} {'recs':>5} "
                     f"{'win%':>7} {'ROI%':>8} {'profit':>9}")
        for m in viable:
            lines.append(
                f"{m['min_edge']:>9.2f} {m['top']:>4d} {m['n_recs']:>5d} "
                f"{m['win_rate']*100:>6.2f}% {m['roi']*100:>+7.2f}% "
                f"{m['total_profit']:>+9.2f}"
            )
        b = res.get("best_config")
        if b:
            lines.append(
                f"BEST: min_edge={b['min_edge']} top={b['top']}  "
                f"ROI={b['roi']*100:+.2f}%  ({b['n_recs']} recs)"
            )
        return "\n".join(lines)
    return json.dumps(res, indent=2, default=str)


def main() -> int:
    args = _parse_args()
    if args.sweep:
        result = sweep_configs(
            qb_dir=args.qb_dir, bankroll=args.bankroll,
            n_per_date=args.n_per_date, max_dates=args.max_dates,
            seed=args.seed,
        )
    else:
        result = run_backtest(
            qb_dir=args.qb_dir, bankroll=args.bankroll,
            min_edge=args.min_edge, top=args.top,
            n_per_date=args.n_per_date, max_dates=args.max_dates,
            seed=args.seed,
        )
    # Persist results
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(_fmt_summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
