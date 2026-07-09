"""Model placement on the freshness-premium curve (Lane A item 7).

The 8225abe8 freshness curve (freshness_premium.py) measured the MARKET's own
Brier vs time-to-start and was explicitly MARKET-ONLY: no leak-free as-of
pregame model prob existed on disk to compare against. This module fills that
gap for the sports where a leak-free dated Elo + a matching game-identity join
actually exist:

NBA: domains.basketball_nba.ratings.walk_forward_elo already gives a strictly
  pre-game Elo win prob per game (K=20, HFA=76, elo_config.py -- unedited,
  reused as-is). games.parquet is REGULAR SEASON ONLY (ends 2026-04-12) but the
  Kalshi nba_price_series corpus is 2026-04-26..06-13 (PLAYOFFS). To get any
  overlap at all we extend the regular-season games_df with playoff results
  from the on-disk espn_boxscores.parquet (home_score/away_score, ESPN abbr
  fixed to games.parquet's tricode convention for the 3 known exceptions
  GS->GSW / NY->NYK / SA->SAS -- verified by set-difference against the 30
  tricodes, no other exceptions in the 82-row playoff slice) so the walk-
  forward carries on through the same 2025-26 season (no regression trigger --
  season string unchanged). Game identity per Kalshi event_key is resolved with
  the SAME (date,away,home) ticker-split machinery nba_outcome_resolver already
  uses (reused directly, not reimplemented): tail = AWAY+HOME concatenated.

TENNIS: now TESTED (was NOT_TESTABLE). domains.tennis.results_2026_bridge joins
  the ESPN 2026 scoreboard ingest onto Sackmann player_id (52.66% match-level
  join rate, 3125/5934 comp_ids, WTA recovered via wta_matches.parquet since
  players.parquet turned out to carry zero WTA rows -- see that module's
  docstring), extending the SAME walk-forward Elo through the Kalshi corpus's
  2026-05-27..07-05 window. See tennis_freshness_placement.py.

For each horizon bucket already defined in freshness_premium.HORIZONS, this
computes, on the INTERSECTION of games with both a market price and a resolved
model prediction: market Brier, model Brier, and the PAIRED per-game delta
(model_se - market_se) with a game-clustered bootstrap 95% CI on the mean
delta (more informative than eyeballing two separate overlapping CIs).

Output: data/frontend/ops/freshness_model_placement.json. edge_claimed: false.
Run:  python -m scripts.platformkit.ingame.freshness_model_placement
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from domains.basketball_nba.adapter import _season_to_int
from domains.basketball_nba.ratings import walk_forward_elo as nba_walk_forward_elo
from scripts.platformkit.ingame.freshness_premium import (
    HORIZONS,
    _bootstrap_ci,
    _devig,
    _last_at_or_before,
    load_games,
)
from scripts.platformkit.ingame.nba_outcome_resolver import (
    _build_name_index,
    _split_tail,
    parse_nba_ticker,
)
from scripts.platformkit.ingame.tennis_freshness_placement import tennis_placement

_ROOT = Path(__file__).resolve().parents[3]
_GAMES_PARQUET = _ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_BOX_PARQUET = _ROOT / "data" / "domains" / "basketball_nba" / "espn_boxscores.parquet"
_OUT = _ROOT / "data" / "frontend" / "ops" / "freshness_model_placement.json"

# ESPN abbr -> games.parquet tricode; only 3 exceptions verified in the 82-row
# post-2026-04-12 playoff slice (set-difference against games.parquet's 30
# tricodes). A code not in this map is assumed to already match verbatim.
_ESPN_ABBR_FIX = {"GS": "GSW", "NY": "NYK", "SA": "SAS"}



def _extended_nba_games() -> pd.DataFrame:
    """Regular-season games.parquet + playoff rows derived from espn_boxscores
    (dates after games.parquet's own max) so the walk-forward Elo carries
    through the same season into the Kalshi playoff odds window."""
    reg = pd.read_parquet(_GAMES_PARQUET)
    cutoff = reg["date"].max()
    box = pd.read_parquet(_BOX_PARQUET, columns=[
        "date", "home_abbr", "away_abbr", "home_score", "away_score", "status"])
    po = box[(box["date"] > cutoff) & (box["status"] == "STATUS_FINAL")].copy()
    po = po.dropna(subset=["home_score", "away_score"])
    po["home_team"] = po["home_abbr"].map(lambda a: _ESPN_ABBR_FIX.get(a, a))
    po["away_team"] = po["away_abbr"].map(lambda a: _ESPN_ABBR_FIX.get(a, a))
    po["home_win"] = (po["home_score"] > po["away_score"]).astype(float)
    po["season"] = reg.loc[reg["date"] == cutoff, "season"].iloc[0]
    po["game_id"] = "PO" + po.index.astype(str)
    ext = pd.concat([reg[["game_id", "date", "season", "home_team", "away_team", "home_win"]],
                     po[["game_id", "date", "season", "home_team", "away_team", "home_win"]]],
                    ignore_index=True)
    ext["season"] = ext["season"].apply(_season_to_int)
    return ext, len(po)


def _nba_model_lookup() -> tuple[dict, dict]:
    """(date,away,home) -> pre-game p_home_elo, + the ticker name-index."""
    ext, n_playoff = _extended_nba_games()
    priced = nba_walk_forward_elo(ext)
    lut = {}
    for r in priced.itertuples(index=False):
        key = (pd.Timestamp(r.date).date(), r.away_team, r.home_team)
        lut[key] = float(r.p_home_elo)
    names = set(ext["home_team"]) | set(ext["away_team"])
    return lut, {"name_index": _build_name_index(names), "n_playoff_rows_appended": n_playoff}


def _resolve_model_prob(event_key: str, lut: dict, name_index: dict) -> float | None:
    """Model P(ref side wins) for one Kalshi event_key, ref = alphabetically-
    first team code (mirrors freshness_premium's own devig-reference side)."""
    parsed = parse_nba_ticker(event_key)
    if parsed is None:
        return None
    date, tail, _ = parsed
    split = _split_tail(tail, name_index)
    if split is None:
        return None
    away, home = split
    for delta in (0, -1, 1):
        key = (date + dt.timedelta(days=delta), away, home)
        if key in lut:
            p_home = lut[key]
            ref = min(away, home)
            return p_home if ref == home else 1.0 - p_home
    return None


def _paired_bootstrap_ci(deltas: np.ndarray, b: int = 1000, seed: int = 0) -> tuple[float, float]:
    if len(deltas) < 3:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    n = len(deltas)
    means = [deltas[rng.integers(0, n, n)].mean() for _ in range(b)]
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def nba_placement() -> dict:
    lut, meta = _nba_model_lookup()
    games, diag = load_games("nba")
    rows = []
    for lbl, sec in HORIZONS:
        m_probs, mo_probs, outs = [], [], []
        for gm in games:
            model_p = _resolve_model_prob(gm["event_key"], lut, meta["name_index"])
            if model_p is None:
                continue
            cutoff = gm["start"] - sec
            r = _last_at_or_before(gm["ref_ts"], gm["ref_p"], cutoff)
            o = _last_at_or_before(gm["oth_ts"], gm["oth_p"], cutoff) if len(gm["oth_ts"]) else None
            mkt = _devig(r, o)
            if mkt is None:
                continue
            mkt = min(max(mkt, 1e-6), 1 - 1e-6)
            model_p = min(max(model_p, 1e-6), 1 - 1e-6)
            m_probs.append(mkt)
            mo_probs.append(model_p)
            outs.append(gm["outcome"])
        m_probs, mo_probs, outs = np.asarray(m_probs), np.asarray(mo_probs), np.asarray(outs)
        n = len(outs)
        if n == 0:
            rows.append({"horizon": lbl, "n": 0, "market_brier": None, "model_brier": None,
                         "delta_model_minus_market": None, "delta_ci95": [None, None]})
            continue
        mkt_se = (m_probs - outs) ** 2
        mod_se = (mo_probs - outs) ** 2
        delta = mod_se - mkt_se
        lo, hi = _paired_bootstrap_ci(delta)
        rows.append({
            "horizon": lbl, "n": int(n),
            "market_brier": round(float(mkt_se.mean()), 5),
            "model_brier": round(float(mod_se.mean()), 5),
            "delta_model_minus_market": round(float(delta.mean()), 5),
            "delta_ci95": [round(lo, 5), round(hi, 5)],
        })
    return {"sport": "nba", "n_playoff_rows_appended": meta["n_playoff_rows_appended"],
            "games_in_market_corpus": diag["games_kept"], "horizons": rows,
            "edge_claimed": False}


def build() -> dict:
    out = {"generated_at": "STABLE", "benchmark_name": "freshness_model_placement",
           "edge_claimed": False, "sports": {}}
    try:
        out["sports"]["nba"] = nba_placement()
    except Exception as e:  # noqa: BLE001 -- a missing input must not sink the run
        out["sports"]["nba"] = {"sport": "nba", "error": str(e)}
    try:
        out["sports"]["tennis"] = tennis_placement()
    except Exception as e:  # noqa: BLE001 -- a missing input must not sink the run
        out["sports"]["tennis"] = {"sport": "tennis", "error": str(e)}
    return out


def main() -> None:
    res = build()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(res, indent=2), encoding="ascii")
    nba = res["sports"]["nba"]
    if "error" in nba:
        print(f"nba: ERROR {nba['error']}")
    else:
        print(f"nba: {nba['games_in_market_corpus']} market games, "
              f"{nba['n_playoff_rows_appended']} playoff rows appended to Elo replay")
        for h in nba["horizons"]:
            print(f"  {h['horizon']:>17}  n={h['n']:>4}  market={h['market_brier']}  "
                  f"model={h['model_brier']}  delta={h['delta_model_minus_market']}  "
                  f"ci95={h['delta_ci95']}")
    tennis = res["sports"]["tennis"]
    if "error" in tennis:
        print(f"tennis: ERROR {tennis['error']}")
    else:
        print(f"tennis: {tennis['status']}  {tennis['games_in_market_corpus']} market games, "
              f"join_rate={tennis['espn_2026_join_rate']}, "
              f"{tennis['n_tickers_resolved_to_players']} tickers resolved")
        for h in tennis["horizons"]:
            print(f"  {h['horizon']:>17}  n={h['n']:>4}  market={h['market_brier']}  "
                  f"model={h['model_brier']}  delta={h['delta_model_minus_market']}  "
                  f"ci95={h['delta_ci95']}")
    print(f"wrote {_OUT}")


if __name__ == "__main__":
    main()
