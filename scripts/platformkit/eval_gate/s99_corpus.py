"""scripts.platformkit.eval_gate.s99_corpus -- the S99 re-keyed corpus builders.

Split out of `s99_cross_market` only to hold that module under the 300-LOC rail; it adds no
behaviour of its own. Everything here is READ-ONLY over the price stores and the joined
state stores -- the re-key is a VIEW (a derived game_key column), never a rewrite.

Per-file test: python -m pytest tests/platformkit/ingame/test_s99_cross_market.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.ingame.soccer_outcome import (SoccerOutcomeResolver, _resolve_code,
                                                       parse_wc_ticker)

REPO = Path(__file__).resolve().parents[3]
PRICES = REPO / "data" / "cache" / "inplay_odds"
JOINED = REPO / "data" / "cache" / "ingame_grade_joined"

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
_MLB_TICKER = re.compile(r"^(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)$")
# Kalshi abbreviation -> the abbreviation used in data/domains/mlb/games_current.parquet.
_K2G = {"AZ": "ARI", "CHC": "CUB", "KC": "KAN", "SD": "SDG", "SF": "SFO",
        "TB": "TAM", "WSH": "WAS", "ATH": "OAK"}
# ESPN finals spelling -> the spelling in data/domains/soccer_intl/results.parquet.
_SOCCER_ALIAS = {"Bosnia-Herzegovina": "Bosnia and Herzegovina", "Congo DR": "DR Congo",
                 "Czechia": "Czech Republic"}
_KV = re.compile(r"(\w+)=([\w\.\-]+)")
# A joined-store state series stops when the capture stops, but the price series runs to
# settlement, so a backward as-of join would silently carry a 2-hour-stale score forward.
# Ticks further than this from their last observed state are DROPPED, never guessed.
STATE_TOLERANCE_S = 300


# ---------------------------------------------------------------- (a) re-keyed view
def rekey(sport: str, prices_dir: Path = PRICES) -> pd.DataFrame:
    """Kalshi price ticks for one sport with a game_key = event_key minus its series prefix.

    Reads the store; never writes it. Non-Kalshi venues (polymarket) key their events in a
    different space entirely and carry moneyline only, so they cannot join and are dropped.
    """
    cols = ["game_date", "event_key", "market_type", "side", "ts", "prob"]
    frame = pd.read_parquet(Path(prices_dir) / ("%s_price_series.parquet" % sport), columns=cols,
                            filters=[("venue", "==", "kalshi")])   # pushed down: 13.4M -> 4.2M
    frame["game_key"] = frame.pop("event_key").str.split("-", n=1).str[1].astype("category")
    frame["market_type"] = frame["market_type"].astype("category")
    return frame


def game_key_view(sports=("mlb", "soccer_intl"), prices_dir: Path = PRICES) -> pd.DataFrame:
    """One row per (sport, game_key, market_type): the additive view the S99 row asks for."""
    out: List[pd.DataFrame] = []
    for sport in sports:
        frame = rekey(sport, prices_dir)
        agg = (frame.groupby(["game_key", "market_type"], observed=True)
               .agg(n_ticks=("ts", "size"), n_strikes=("side", "nunique"),
                    ts_min=("ts", "min"), ts_max=("ts", "max"), game_date=("game_date", "min"))
               .reset_index())
        agg.insert(0, "sport", sport)
        agg["n_markets_on_game"] = (agg.groupby("game_key", observed=True)["market_type"]
                                    .transform("nunique"))
        out.append(agg)
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------- state + as-of rates
def load_state(path: Path) -> pd.DataFrame:
    """Per-tick on-disk state from a joined-store jsonl: epoch ts + the parsed state_summary."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        kv = dict(_KV.findall(rec.get("state_summary") or ""))
        rows.append({"ts": int(pd.Timestamp(rec["ts"]).timestamp()),
                     "cur_h": float(kv.get("home_score", "nan")),
                     "cur_a": float(kv.get("away_score", "nan")),
                     "inning": float(kv.get("inning", "nan")),
                     "half": kv.get("half", ""), "outs": float(kv.get("outs", "nan")),
                     "minute": float(kv.get("minute", "nan"))})
    return pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)


def mlb_asof_rates(games: pd.DataFrame, date: dt.date) -> Tuple[Dict[str, float], float]:
    """Team runs per half-inning from games STRICTLY BEFORE `date` in the same season."""
    prior = games[games["d"] < date]
    prior = prior[prior["season"] == prior["season"].max()] if len(prior) else prior
    league = float((prior["home_runs"].sum() + prior["away_runs"].sum()) /
                   max(1, 2 * len(prior))) / 9.0 if len(prior) else 0.5
    rates: Dict[str, float] = {}
    for team in set(prior["home_team"]) | set(prior["away_team"]):
        h, a = prior[prior["home_team"] == team], prior[prior["away_team"] == team]
        n = len(h) + len(a)
        if n >= 5:
            rates[team] = float(h["home_runs"].sum() + a["away_runs"].sum()) / (9.0 * n)
    return rates, league


def soccer_asof_rates(results: pd.DataFrame, date: dt.date) -> Tuple[Dict[str, float], float]:
    """Team goals per minute from internationals STRICTLY BEFORE `date` (a 6-year window)."""
    prior = results[(results["d"] < date) & (results["d"] >= date - dt.timedelta(days=2192))]
    league = float((prior["home_score"].sum() + prior["away_score"].sum()) /
                   max(1, 2 * len(prior))) / 90.0 if len(prior) else 1.3 / 90.0
    rates: Dict[str, float] = {}
    for team in set(prior["home_team"]) | set(prior["away_team"]):
        h, a = prior[prior["home_team"] == team], prior[prior["away_team"] == team]
        n = len(h) + len(a)
        if n >= 5:
            rates[team] = float(h["home_score"].sum() + a["away_score"].sum()) / (90.0 * n)
    return rates, league


def mlb_remaining(inning: np.ndarray, half: np.ndarray, outs: np.ndarray):
    """Remaining (away, home) half-innings of a 9-inning game from the as-of state."""
    frac = np.clip(1.0 - np.nan_to_num(outs) / 3.0, 0.0, 1.0)
    full = np.clip(9.0 - inning, 0.0, None)
    top = half == "top"
    away = np.where(top, frac + full, full)
    home = np.where(top, np.clip(10.0 - inning, 0.0, None), frac + full)
    return away, home


# ---------------------------------------------------------------- corpora
def _mlb_games() -> pd.DataFrame:
    games = pd.read_parquet(REPO / "data" / "domains" / "mlb" / "games_current.parquet")
    games["d"] = pd.to_datetime(games["date"]).dt.date
    return games


def build_mlb() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Moneyline + total ticks for every MLB game carrying both, with as-of state and lambdas."""
    ticks, games = rekey("mlb"), _mlb_games()
    ticks = ticks[ticks.groupby("game_key", observed=True)["market_type"].transform("nunique") >= 2]
    rows, kept, dropped = [], [], {"unparsed": 0, "no_state": 0, "no_outcome": 0}
    for key, block in ticks.groupby("game_key", observed=True):
        match = _MLB_TICKER.match(key)
        state_path = JOINED / "mlb" / ("KXMLBGAME-%s.jsonl" % key)
        if match is None or not state_path.exists():
            dropped["unparsed" if match is None else "no_state"] += 1
            continue
        date = dt.date(2000 + int(match.group(1)), _MONTHS[match.group(2)], int(match.group(3)))
        # The ticker tail is away+home concatenated with no delimiter. Some games captured only
        # ONE moneyline side, so split the tail on whichever side WAS captured; MLB has no draw,
        # so an away-only series is inverted rather than dropped.
        sides = sorted(block[block["market_type"] == "moneyline"]["side"].astype(str).unique())
        tail, pair = match.group(5), None
        for s in sides:
            if tail.endswith(s) and tail[:-len(s)]:
                pair = (tail[:-len(s)], s)
            elif tail.startswith(s) and tail[len(s):]:
                pair = (s, tail[len(s):])
        if pair is None or pair[0] == pair[1]:
            dropped["unparsed"] += 1
            continue
        away, home = pair
        final = games[(games["d"] == date) & (games["home_team"] == _K2G.get(home, home)) &
                      (games["away_team"] == _K2G.get(away, away))]
        if len(final) != 1:
            dropped["no_outcome"] += 1
            continue
        hr, ar = float(final["home_runs"].iloc[0]), float(final["away_runs"].iloc[0])
        rates, league = mlb_asof_rates(games, date)
        rate_h = rates.get(_K2G.get(home, home), league)
        rate_a = rates.get(_K2G.get(away, away), league)
        state = load_state(state_path)
        for market in ("moneyline", "total"):
            leg = block[block["market_type"] == market]
            price = leg["prob"].to_numpy()
            if market == "moneyline":
                keep = leg["side"].astype(str) == (home if home in sides else away)
                leg, price = leg[keep], price[keep.to_numpy()]
                price = price if home in sides else 1.0 - price
            if not len(leg):
                continue
            frame = pd.DataFrame({"ts": leg["ts"].to_numpy(), "price": price,
                                  "strike": (np.nan if market == "moneyline"
                                             else pd.to_numeric(leg["side"]).to_numpy())})
            frame = pd.merge_asof(frame.sort_values("ts"), state, on="ts", direction="backward",
                                  tolerance=STATE_TOLERANCE_S)
            frame = frame.dropna(subset=["cur_h", "inning"])
            if not len(frame):
                continue
            rem_a, rem_h = mlb_remaining(frame["inning"].to_numpy(), frame["half"].to_numpy(),
                                         frame["outs"].to_numpy())
            frame["lam_h"], frame["lam_a"] = rate_h * rem_h, rate_a * rem_a
            frame["market"], frame["game"], frame["game_date"] = market, key, str(date)
            frame["y_total"] = hr + ar
            frame["y"] = (float(hr > ar) if market == "moneyline"
                          else (hr + ar >= frame["strike"]).astype(float))
            frame["phase"] = pd.cut(frame["inning"], [0, 3, 6, 99],
                                    labels=["inn 1-3", "inn 4-6", "inn 7+"]).astype(str)
            rows.append(frame)
        kept.append(key)
    meta = {"n_multi_market_games": int(ticks["game_key"].nunique()), "n_games_joined": len(kept),
            "dropped": dropped, "tie_weight": 0.5, "crps_kmax": 40}
    return pd.concat(rows, ignore_index=True), meta


def build_soccer() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Moneyline + team_total ticks for every soccer_intl game carrying both."""
    ticks = rekey("soccer_intl")
    ticks = ticks[ticks.groupby("game_key", observed=True)["market_type"].transform("nunique") >= 2]
    resolver = SoccerOutcomeResolver()
    results = pd.read_parquet(REPO / "data" / "domains" / "soccer_intl" / "results.parquet")
    results = results.dropna(subset=["home_score", "away_score"]).copy()
    results["d"] = pd.to_datetime(results["date"]).dt.date
    rows, kept, dropped = [], [], {"unparsed": 0, "no_state": 0, "no_outcome": 0}
    for key, block in ticks.groupby("game_key", observed=True):
        parsed = parse_wc_ticker("KXWCGAME-%s" % key)
        state_path = JOINED / "soccer_intl" / ("KXWCGAME-%s.jsonl" % key)
        if parsed is None or not state_path.exists():
            dropped["unparsed" if parsed is None else "no_state"] += 1
            continue
        date, code_a, code_b = parsed
        names = [_resolve_code(c, resolver._name_index) for c in (code_a, code_b)]
        hit = None
        if all(names):
            pair = frozenset(n.upper() for n in names)
            for delta in (0, -1, 1):
                hit = hit or resolver._by_pair.get((date + dt.timedelta(days=delta), pair))
        if hit is None:
            dropped["no_outcome"] += 1
            continue
        home_name, away_name, hs, as_ = hit
        home = code_a if names[0] == home_name else code_b
        away = code_b if home == code_a else code_a
        rates, league = soccer_asof_rates(results, date)
        rate = {home: rates.get(_SOCCER_ALIAS.get(home_name, home_name), league),
                away: rates.get(_SOCCER_ALIAS.get(away_name, away_name), league)}
        goals = {home: float(hs), away: float(as_)}
        state = load_state(state_path)
        for market in ("moneyline", "team_total"):
            leg = block[block["market_type"] == market]
            leg = (leg[leg["side"] == home] if market == "moneyline"
                   else leg[leg["side"].str[:3].isin(rate)])
            if not len(leg):
                continue
            team = (np.array([home] * len(leg)) if market == "moneyline"
                    else leg["side"].str[:3].to_numpy())
            frame = pd.DataFrame({"ts": leg["ts"].to_numpy(), "price": leg["prob"].to_numpy(),
                                  "team": team,
                                  "strike": (np.nan if market == "moneyline"
                                             else pd.to_numeric(leg["side"].str[3:]).to_numpy())})
            frame = pd.merge_asof(frame.sort_values("ts"), state, on="ts", direction="backward",
                                  tolerance=STATE_TOLERANCE_S)
            frame = frame.dropna(subset=["cur_h", "minute"])
            if not len(frame):
                continue
            left = np.clip(90.0 - frame["minute"].to_numpy(), 0.0, 90.0)
            frame["lam_h"], frame["lam_a"] = rate[home] * left, rate[away] * left
            frame["market"], frame["game"], frame["game_date"] = market, key, str(date)
            frame["y_total"] = float(hs + as_)
            is_home = frame["team"].to_numpy() == home
            frame["cur_team"] = np.where(is_home, frame["cur_h"], frame["cur_a"])
            frame["lam_team"] = np.where(is_home, frame["lam_h"], frame["lam_a"])
            realized = np.array([goals[t] for t in frame["team"]], dtype=float)
            frame["y"] = (float(hs > as_) if market == "moneyline"
                          else (realized >= frame["strike"]).astype(float))
            frame["phase"] = pd.cut(frame["minute"], [0, 30, 60, 200],
                                    labels=["min 0-30", "min 31-60", "min 61+"]).astype(str)
            rows.append(frame)
        kept.append(key)
    meta = {"n_multi_market_games": int(ticks["game_key"].nunique()), "n_games_joined": len(kept),
            "dropped": dropped, "tie_weight": 0.0, "crps_kmax": 12}
    return pd.concat(rows, ignore_index=True), meta

