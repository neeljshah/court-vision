"""domains.basketball_wnba.profiles.ingredients_schedule_rest -- WNBA
schedule/rest attributes off data/domains/wnba/player_boxscores.parquet ONLY
(NOT schedule_density.parquet: its team column is the full team NAME while
this boxscore's team_id is numeric -- joining them would silently mismatch
every row, per the build spec's explicit source directive).

Team-grain (entity="team", floor=TEAM_FLOOR games-with-known-rest):
  avg_rest_days, b2b_rate (rest<=1), short_rest_rate (rest<=2). Rest is
  computed from each team's own distinct (team_id, game_date) sequence, so a
  team's first game in the corpus has no prior game and is EXCLUDED (rest
  undefined, never zero-filled).
  entity_id/entity_name = the espn_scoreboard DISPLAY NAME ("Las Vegas
  Aces"), resolved from boxscore numeric team_id by attach_team_names()'s
  home-date vote-join -- the SAME entity space ingredients_team_form.py
  uses, so one team carries BOTH families' attributes (2026-07-18 fix: the
  numeric-id twin entity made these attrs unreachable by name). Verified on
  real data: all 15 WNBA teams map with the winner >=3 votes ahead of any
  runner-up; the two national-team exhibition ids (NIGERIA/JAPAN, no home
  games in the scoreboard) fall back to str(team_id) and can never clear
  the floor=10 anyway.

Player-grain (entity="player", floor=PLAYER_FLOOR = min(n_short, n_long)):
  rest_split_pts_per36, rest_split_efg -- delta (short-rest minus long-rest)
  where short-rest = games on <=2 days rest, long-rest = games on >=3 days
  rest (this family's OWN threshold, looser than the team-grain b2b_rate's
  <=1 cut -- see HONESTY FLAG). DNP rows (played=False) are excluded before
  splitting -- a scoreless bench DNP is not a "short rest game" observation.

HONESTY FLAG (verified 2026-07-18): 2026 has only 7 true b2b (rest<=1) of
336 team-games (rest histogram: {1:7, 2:142, 3:84, 4:43, ...}). A player
rest-split keyed on that <=1 cut would starve almost every player's "short"
group to n<5. The <=2/>=3 cut used here is looser but still genuinely
descriptive; most players will STILL fail the n_short>=5 AND n_long>=5
floor below, and that is the INTENDED honest behavior -- this family's real
job is turning a not_supported probe into an evidenced refusal (n=k, no
support), not manufacturing a signal. Every delta ships a seeded bootstrap
CI95 in `ingredients` (percentile method, resampling games within each
group independently) so a caller sees "no support" as a CI straddling
zero, not a bare missing number. DESCRIPTIVE, NOT a predictive edge
(no-edge rule): rest is backward-looking by construction (computed from the
PRIOR game's date), so the split itself is as-of-safe, but no walk-forward/
OOS claim is made here.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_schedule_rest.py -q
"""
from __future__ import annotations

import random
from typing import Callable

import pandas as pd

from domains.basketball_wnba.profiles.ingredients_team_form import SEASON

TEAM_FLOOR = 10  # games-with-known-rest, declared (spec gave no explicit team floor for this family)
SHORT_REST_MAX = 2  # days -- PLAYER split short-rest group (looser than b2b's <=1 cut, see HONESTY FLAG)
LONG_REST_MIN = 3
BOOTSTRAP_ITERS = 2000
BOOTSTRAP_SEED = 7


def attach_team_names(box: pd.DataFrame, scoreboard: pd.DataFrame) -> pd.DataFrame:
    """Attach a team_name column (espn_scoreboard display name -- the entity
    space ingredients_team_form.py keys on) to the boxscore frame by
    HOME-DATE VOTE: for each team_id, join its distinct home game_dates to
    the scoreboard's home_team names on that date and take the majority name.
    A team's true name appears on every one of its home dates; a co-hosting
    name only on shared dates -- verified unambiguous on real 2026 data
    (winner >=3 votes clear). Unmapped ids (national-team exhibitions with
    no scoreboard home games) get NaN team_name -> builders fall back to
    str(team_id).
    ponytail: vote-join instead of a hardcoded id->name table -- expansion
    teams keep working without a fossil dict; revisit only if a future
    season's boxscore drops is_home."""
    sb = scoreboard[scoreboard["season"].astype(str) == SEASON].copy()
    sb["date_str"] = pd.to_datetime(sb["date"]).dt.strftime("%Y-%m-%d")
    home = box[box["is_home"]].drop_duplicates(["team_id", "game_date"])[["team_id", "game_date"]].copy()
    home["game_date"] = pd.to_datetime(home["game_date"]).dt.strftime("%Y-%m-%d")
    joined = home.merge(sb[["date_str", "home_team"]], left_on="game_date", right_on="date_str")
    votes = joined.groupby(["team_id", "home_team"]).size().reset_index(name="n")
    best = votes.sort_values(["n", "home_team"]).groupby("team_id").tail(1)  # deterministic tie-break
    name_map = dict(zip(best["team_id"], best["home_team"]))
    out = box.copy()
    out["team_name"] = out["team_id"].map(name_map)
    return out


def _team_game_rest(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (team_id, game_date) with rest_days = days since that
    team's PRIOR game_date (NaN for a team's first game in the corpus)."""
    tg = df.drop_duplicates(["team_id", "game_date"])[["team_id", "game_date"]].copy()
    tg["game_date"] = pd.to_datetime(tg["game_date"])
    tg = tg.sort_values(["team_id", "game_date"])
    tg["rest_days"] = tg.groupby("team_id")["game_date"].diff().dt.days
    return tg


def _team_rest_metric_builder(metric: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def _builder(df: pd.DataFrame) -> pd.DataFrame:
        tg = _team_game_rest(df).dropna(subset=["rest_days"])
        g = tg.groupby("team_id")
        n = g.size()
        if metric == "avg_rest_days":
            value = g["rest_days"].mean()
        elif metric == "b2b_rate":
            value = g["rest_days"].apply(lambda s: (s <= 1).mean())
        elif metric == "short_rest_rate":
            value = g["rest_days"].apply(lambda s: (s <= 2).mean())
        else:
            raise ValueError(f"unknown metric: {metric}")
        b2b_count = g["rest_days"].apply(lambda s: int((s <= 1).sum()))
        out = pd.DataFrame({"team_id": value.index, "raw_value": value.values, "n": n.values,
                             "b2b_count": b2b_count.values})
        # display-name entity space (same as ingredients_team_form) via the
        # loader-attached team_name column; str(team_id) fallback for
        # unmapped ids or a frame loaded without attach_team_names.
        if "team_name" in df.columns:
            names = df.dropna(subset=["team_name"]).drop_duplicates("team_id").set_index("team_id")["team_name"]
        else:
            names = pd.Series(dtype=object)
        out["entity_id"] = out["team_id"].map(lambda t: str(names.get(t, t)))
        out["entity_name"] = out["entity_id"]
        out["ingredients"] = out.apply(lambda r: {
            "b2b_count": int(r.b2b_count), "games_with_known_rest": int(r.n),
        }, axis=1)
        return out[["entity_id", "entity_name", "raw_value", "n", "ingredients"]]
    return _builder


build_avg_rest_days = _team_rest_metric_builder("avg_rest_days")
build_b2b_rate = _team_rest_metric_builder("b2b_rate")
build_short_rest_rate = _team_rest_metric_builder("short_rest_rate")


def _bootstrap_delta_ci(short_vals: list[float], long_vals: list[float],
                         iters: int = BOOTSTRAP_ITERS, seed: int = BOOTSTRAP_SEED) -> list[float] | None:
    """Percentile bootstrap CI95 on mean(short) - mean(long), resampling each
    group independently with replacement (seeded, deterministic) -- same
    2.5/97.5 percentile-cut convention as states_gate_ci.bootstrap_delta_ci."""
    rng = random.Random(seed)
    ns, nl = len(short_vals), len(long_vals)
    if ns == 0 or nl == 0:
        return None
    deltas = []
    for _ in range(iters):
        sample_s = [short_vals[rng.randrange(ns)] for _ in range(ns)]
        sample_l = [long_vals[rng.randrange(nl)] for _ in range(nl)]
        deltas.append(sum(sample_s) / ns - sum(sample_l) / nl)
    deltas.sort()
    lo, hi = int(0.025 * iters), min(int(0.975 * iters), iters - 1)
    return [round(deltas[lo], 4), round(deltas[hi], 4)]


def _pts_per36_compute(g: pd.DataFrame) -> tuple[float, list[float]]:
    total = 36.0 * g["pts"].sum() / g["minutes"].sum()
    valid = g[g["minutes"] > 0]
    per_game = (36.0 * valid["pts"] / valid["minutes"]).tolist()
    return total, per_game


def _efg_compute(g: pd.DataFrame) -> tuple[float, list[float]]:
    total = (g["fgm"].sum() + 0.5 * g["fg3m"].sum()) / g["fga"].sum()
    valid = g[g["fga"] > 0]
    per_game = ((valid["fgm"] + 0.5 * valid["fg3m"]) / valid["fga"]).tolist()
    return total, per_game


def _rest_split_builder(compute) -> Callable[[pd.DataFrame], pd.DataFrame]:
    def _builder(df: pd.DataFrame) -> pd.DataFrame:
        tg = _team_game_rest(df).dropna(subset=["rest_days"])
        played = df[df["played"]].copy()
        played["game_date"] = pd.to_datetime(played["game_date"])
        merged = played.merge(tg[["team_id", "game_date", "rest_days"]], on=["team_id", "game_date"], how="inner")
        rows = []
        for pid, g in merged.groupby("player_id"):
            short = g[g["rest_days"] <= SHORT_REST_MAX]
            long_ = g[g["rest_days"] >= LONG_REST_MIN]
            n_short, n_long = len(short), len(long_)
            if n_short == 0 or n_long == 0:
                continue
            short_val, short_per_game = compute(short)
            long_val, long_per_game = compute(long_)
            rows.append({
                "entity_id": str(pid), "entity_name": g["player_name"].iloc[-1],
                "raw_value": short_val - long_val, "n": min(n_short, n_long),
                "ingredients": {
                    "short_rest_value": round(float(short_val), 4), "long_rest_value": round(float(long_val), 4),
                    "n_short": int(n_short), "n_long": int(n_long),
                    "delta_ci95": _bootstrap_delta_ci(short_per_game, long_per_game),
                },
            })
        return pd.DataFrame(rows, columns=["entity_id", "entity_name", "raw_value", "n", "ingredients"])
    return _builder


build_rest_split_pts_per36 = _rest_split_builder(_pts_per36_compute)
build_rest_split_efg = _rest_split_builder(_efg_compute)

BUILDERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "avg_rest_days": build_avg_rest_days,
    "b2b_rate": build_b2b_rate,
    "short_rest_rate": build_short_rest_rate,
    "rest_split_pts_per36": build_rest_split_pts_per36,
    "rest_split_efg": build_rest_split_efg,
}
