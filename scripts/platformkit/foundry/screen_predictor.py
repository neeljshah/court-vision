"""The real single-hypothesis T1 screen predictor (S58c) -- what the S16 p_base fixture stood in for.

For hypothesis h on sport corpus C the screen is ONE walk-forward logistic on
[1, logit(p_ref), z(transform(feature))], fit strictly inside `eval_gate.walk_forward`'s
expanding window (purged, embargoed, select_inside only) and scored by Brier against the
corpus's LABELLED incumbent: the devigged close where close_join carries one (soccer,
tennis), else p_base. The feature is as-of by construction -- a gate-corpus column because
corpus_cache built it so, a family-source column because it says `asof` and is one row per
event, or because it carries a DECLARED S85 bridge (`foundry.asof_supply`). A same-game
column is refused BY NAME before any value is read (S53, lifted to every sport). Transforms
use PRIOR rows only. A SCREEN is a NON-FINDING. Calibration language only.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.combo.corpus_cache import SOCCER_LEAKY_COLUMNS, load_gate_corpus
from scripts.platformkit.foundry.grammar import Hypothesis

ROOT = Path(__file__).resolve().parents[3]
# Every fit serves only test rows LATER than every row it was fit on. The cache identity below
# is a CPCV path identity, never a length bucket shared by disjoint train sets.
REFIT_EVERY, MIN_FIT_ROWS, RIDGE = 50, 30, 1e-3
# Spine, keys and the LABEL are never features. `p_base` / `p_elo` ARE: the corpus's own as-of
# base is a frozen member of every *_gate family ("does the base still add to the close?").
SPINE = frozenset(("event_id", "game_id", "corpus_unit", "event_date", "date", "season", "y", "index"))
INCUMBENT = {"soccer": "devig_close", "tennis": "devig_close", "nba": "p_base", "mlb": "p_base"}
# S113: nba/mlb OPT-IN market-relative incumbent. Default OFF -- the pod run is unchanged until the
# orchestrator exports FOUNDRY_CLOSE_INCUMBENT=1. ON: the incumbent is `p_close` from
# gate_corpus_{nba,mlb}_close and the served window is RESTRICTED to close-covered rows.
CLOSE_INCUMBENT_ENV = "FOUNDRY_CLOSE_INCUMBENT"
# The label is per close_source and never overstates what the source is: mlb's is a devigged
# two-sided close; nba's pregame source is a ONE-SIDED venue probability (close_join_nba_mlb
# forbids calling it a devigged close) and its fallback source is the first in-play tick.
CLOSE_LABEL = {"pre_first_pitch_two_sided": "devigged_close",
               "pregame_last_tick_before_commence": "pregame_venue_close",
               "first_inplay_tick": "first_inplay_tick"}
# S53's rule for every sport: a same-game or in-game column is refused by NAME. In-game state
# columns (`asof_idx`, `p0`, `state_diff`, ...) are as-of WITHIN a game, which is same-game
# relative to a pregame state, so they are named here even though some say `asof`.
LEAKY_NAMES = frozenset(SOCCER_LEAKY_COLUMNS) | frozenset((
    "y", "outcome", "home_win", "target_home_win", "home_final", "away_final", "home_margin",
    "home_goals", "away_goals", "home_runs", "away_runs", "home_reds", "away_reds", "red_diff",
    "yellow_diff", "sub_count_diff", "shot_zone_diff", "shot_diff", "xgproxy_diff", "xgloc_diff",
    "home_xgloc", "away_xgloc", "n_shots_loc", "state_diff", "frac_elapsed", "seconds_remaining",
    "asof_idx", "p0", "n_plays_seen", "run_diff", "possessions_elapsed", "pace_so_far",
    "poss_since_lead_change", "home_fouls", "away_fouls", "foul_diff", "count_balls",
    "count_strikes", "runners", "outs", "base_run_value", "base_out_known", "atbat_pitch_number",
    "pitch_velocity", "pitch_loc_x", "pitch_loc_y", "sp_pitch_count_prior", "velo_decline_vs_early"))
_SAME_GAME = re.compile(r"(^|_)(final|result|winner|margin|score|goals|runs)(_|$)")


class ScreenRefused(ValueError):
    """The feature cannot be screened honestly on this corpus; the reason is the message."""


def check_feature_name(name: str, corpus_columns: Sequence[str] = ()) -> None:
    """Refuse a same-game column by name; accept as-of names and gate-corpus columns."""
    if name in LEAKY_NAMES:
        raise ScreenRefused("leaky: %s is a same-game column" % name)
    if "asof" in name or name in set(corpus_columns) - SPINE:
        return
    if _SAME_GAME.search(name):
        raise ScreenRefused("leaky: %s names a same-game quantity" % name)
    raise ScreenRefused("unavailable: %s is neither an asof_ column nor a gate-corpus column" % name)


def _clip(p: float) -> float:
    return min(max(float(p), 0.001), 0.999)


def _logit(p: float) -> float:
    return math.log(_clip(p) / (1.0 - _clip(p)))


def _logistic(X: np.ndarray, y: np.ndarray, ridge: float = RIDGE, iters: int = 25) -> np.ndarray:
    """Ridge-stabilised Newton logistic; a few iterations on <= 800 x 3 is sub-millisecond."""
    w = np.zeros(X.shape[1])
    eye = ridge * np.eye(X.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-X @ w))
        step = np.linalg.solve((X * (p * (1.0 - p))[:, None]).T @ X + eye, X.T @ (p - y) + ridge * w)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


class RealScreenPredictor:
    """walk_forward's predict_fn for ONE hypothesis: logistic on [1, logit(p_ref), z(feature)].

    `archive()` returns the as-of fit state (every refit's train size and coefficients), so the
    model side of the comparison is reconstructible from the artifact alone (Q9).
    """

    def __init__(self, feature: str, refit_every: int = REFIT_EVERY) -> None:
        self.feature, self.refit_every = feature, int(refit_every)
        self._path_key, self._fit = None, None
        self.fits: list = []

    def _refit(self, train: Sequence[dict]) -> None:
        rows = [(s["features"]["p_ref"], s["features"][self.feature], s["outcome"])
                for s in train if s["features"].get(self.feature) is not None]
        self._fit = None
        if len(rows) >= MIN_FIT_ROWS:
            x = np.array([r[1] for r in rows], dtype=float)
            mu, sd = float(x.mean()), float(x.std()) or 1.0
            X = np.column_stack([np.ones(len(rows)), [_logit(r[0]) for r in rows], (x - mu) / sd])
            coef = _logistic(X, np.array([r[2] for r in rows], dtype=float))
            self._fit = (coef, mu, sd)
        self.fits.append({"n_train": len(train), "n_fit": len(rows),
                          "first_game_id": train[0]["game_id"] if train else "",
                          "last_game_id": train[-1]["game_id"] if train else "",
                          "train_sha256": hashlib.sha256("\n".join(
                              str(state["game_id"]) for state in train).encode("ascii")).hexdigest(),
                          "coef": None if self._fit is None else [float(c) for c in self._fit[0]],
                          "mu": None if self._fit is None else mu,
                          "sd": None if self._fit is None else sd})

    def __call__(self, train: Sequence[dict], test: dict, select_inside: bool) -> float:
        if not select_inside:
            raise ValueError("the screen fits inside the window only (select_inside=True)")
        p_ref = _clip(test["features"]["p_ref"])
        path_key = (id(train), train[0]["game_id"] if train else "",
                    train[-1]["game_id"] if train else "", len(train) // self.refit_every)
        if path_key != self._path_key:
            self._path_key = path_key
            self._refit(train)
        x = test["features"].get(self.feature)
        if self._fit is None or x is None:          # missing != bad: fall back to the incumbent
            return p_ref
        coef, mu, sd = self._fit
        eta = coef[0] + coef[1] * _logit(p_ref) + coef[2] * (float(x) - mu) / sd
        return _clip(1.0 / (1.0 + math.exp(-eta)))

    def archive(self) -> dict:
        return {"predictor": "real_logistic_v1", "feature": self.feature,
                "refit_every": self.refit_every, "min_fit_rows": MIN_FIT_ROWS, "ridge": RIDGE,
                "fits": list(self.fits)}


from scripts.platformkit.foundry.screen_predictor_supply import _families_of, _table, source_column


def _twin(name: str) -> Optional[str]:
    return next((b + name[len(a):] for a, b in (("home_", "away_"), ("p1_", "p2_"))
                 if name.startswith(a)), None)


def transform(x: pd.Series, name: str, params: tuple, frame: pd.DataFrame,
              twin: Optional[pd.Series] = None) -> pd.Series:
    """Grammar transforms on a date-ordered as-of series; prior = earlier rows of the same cluster."""
    if name == "raw":
        return x
    if name == "ew":
        halflife = dict(params)["halflife"]
        return x.groupby(frame["cluster"].values).transform(
            lambda s: s.shift(1).ewm(halflife=halflife, min_periods=1).mean())
    if name == "delta_vs_prior":
        return x - x.groupby(frame["cluster"].values).shift(1)
    if name == "rank_in_league":
        return x.groupby(frame["date"].values).rank(pct=True)
    if name == "z_vs_league":
        return (x - x.expanding().mean().shift(1)) / x.expanding().std().shift(1).replace(0.0, np.nan)
    if name == "ratio_to_opponent":
        if twin is None:
            raise ScreenRefused("unavailable: ratio_to_opponent needs a home_/away_ or p1_/p2_ twin")
        return x / twin.where(twin != 0)
    raise ValueError("unknown transform %r" % name)


class ScreenBinder:
    """Per-hypothesis (states, predict_fn) for the runner over ONE partition side.

    `states` are the SCREEN-side base states in date order (each carries `devig_close_prob` =
    the incumbent, `home`/`away`, `div` for soccer); `table` is the gate corpus indexed by
    event_id and `frame` the (date, home, away, cluster) context the S85 bridge joins on.
    Transforms run over the whole side so the first served row has a real prior; the served
    window is the LAST `rows` states, as the runner's `--screen-rows` always was.
    """

    def __init__(self, sport: str, states: Sequence[dict], table: pd.DataFrame, rows: int,
                 incumbent: str) -> None:
        self.sport, self.states, self.rows, self.incumbent = sport, list(states), int(rows), incumbent
        self.table = table.loc[[s["game_id"] for s in self.states]]
        self.frame = pd.DataFrame({
            "date": [s["game_date"] for s in self.states],
            "home": [s["home"] for s in self.states], "away": [s["away"] for s in self.states],
            "cluster": [s.get("div") or s["home"] for s in self.states]}, index=self.table.index)
        self.frame.attrs.update(sport=sport, served_rows=self.rows)  # S85 alias key; S111 window

    def feature_values(self, hypothesis: Hypothesis) -> pd.Series:
        x = source_column(hypothesis, hypothesis.feature, self.table, self.frame)
        twin_name = _twin(hypothesis.feature) if hypothesis.transform == "ratio_to_opponent" else None
        twin = None
        if twin_name is not None:
            try:
                twin = source_column(hypothesis, twin_name, self.table, self.frame)
            except ScreenRefused:
                twin = None
        return transform(x, hypothesis.transform, hypothesis.params, self.frame, twin)

    def __call__(self, hypothesis: Hypothesis) -> tuple:
        values = self.feature_values(hypothesis).to_numpy(dtype=float)
        name = "%s__%s" % (hypothesis.feature, hypothesis.transform)
        out = []
        for state, value in list(zip(self.states, values))[-self.rows:]:
            avail = "%sT00:00:00" % state["game_date"]
            row = dict(state)
            row["features"] = {"p_ref": float(state["devig_close_prob"]),
                               name: None if not np.isfinite(value) else float(value)}
            row["feature_avail"] = {"p_ref": avail, name: avail}
            out.append(row)
        return out, RealScreenPredictor(name)


def _teams(sport: str) -> pd.DataFrame:
    base = ROOT / "data" / "domains"
    if sport == "nba":
        games = pd.read_parquet(base / "basketball_nba" / "games.parquet")
        games["event_id"] = games["game_id"].astype(str)
    else:
        games = pd.concat([pd.read_parquet(base / "mlb" / f) for f in ("games.parquet", "games_current.parquet")])
        games["event_id"] = games["event_id"].astype(str)
    return games.drop_duplicates("event_id").set_index("event_id")[["home_team", "away_team"]]


def corpus_states(sport: str, close_incumbent: Optional[bool] = None) -> tuple:
    """(states, table, incumbent_label) for one gate corpus. soccer/tennis: close_join states,
    devigged close as incumbent; nba/mlb: p_base, LABELLED. corpus_unit is carried only where the
    spec's SF-1 basis is corpus_unit (soccer); two-unit corpora partition by ISO week (SF-11).

    S113: with `close_incumbent` (or FOUNDRY_CLOSE_INCUMBENT=1) the nba/mlb incumbent is the S112
    market close instead of Elo -- the corpus becomes gate_corpus_<sport>_close, the served rows are
    RESTRICTED to the close-covered ones, and the six close columns are dropped from the feature
    table so the incumbent can never be screened against itself. Default OFF = byte-identical.
    """
    from scripts.platformkit.eval_gate.close_join import gate_corpus_states

    # S75: honour the same portable flag tiers.run_tier passes (pod hosts lack the domain sources)
    portable = os.environ.get("FOUNDRY_PORTABLE_CORPUS") == "1"
    use_close = sport in ("nba", "mlb") and (os.environ.get(CLOSE_INCUMBENT_ENV) == "1"
                                             if close_incumbent is None else bool(close_incumbent))
    if use_close:
        from scripts.platformkit.eval_gate.close_join_nba_mlb import (CLOSE_COLUMNS,
                                                                      load_close_corpus)
        corpus = load_close_corpus(sport, portable=portable).copy()
        corpus = corpus[corpus["p_close"].notna()]
    else:
        CLOSE_COLUMNS = ()
        corpus = load_gate_corpus(sport, portable=portable).copy()
    corpus["event_id"] = corpus["event_id"].astype(str)
    table = corpus.drop_duplicates("event_id").set_index("event_id")
    units = table["corpus_unit"].astype(str)
    incumbent = INCUMBENT[sport]
    if sport in ("soccer", "tennis"):
        states = gate_corpus_states(sport, "1900-01-01", "2999-01-01")
        for state in states:
            if sport == "soccer":
                state["div"] = state["corpus_unit"] = units[state["game_id"]]
    else:
        teams = _teams(sport)
        rows = table.join(teams, how="inner").assign(event_date=lambda t: pd.to_datetime(t["event_date"]))
        rows = rows[rows["y"].notna() & rows["p_base"].notna()].sort_values("event_date")
        reference = "p_close" if use_close else "p_base"
        if use_close:
            incumbent = "+".join(sorted({CLOSE_LABEL.get(str(s), "close:%s" % s)
                                         for s in rows["close_source"]})) or INCUMBENT[sport]
        states = []
        for event_id, row in rows.iterrows():
            day = row["event_date"].date().isoformat()
            states.append({"game_id": event_id, "season": day[:4], "sport": sport, "regime": "pregame",
                           "game_date": day, "state_ts": "%sT12:00:00" % day,
                           "home": str(row["home_team"]), "away": str(row["away_team"]),
                           "features": {"p_base": float(row["p_base"])},
                           "feature_avail": {"p_base": "%sT00:00:00" % day},
                           "devig_close_prob": float(row[reference]), "truth_wp": float(row["y"]),
                           "outcome": int(row["y"]), "vintage": "SYNTHETIC"})
    numeric = table.select_dtypes(include="number")
    drop = SPINE | frozenset(CLOSE_COLUMNS)
    return states, numeric.loc[:, [c for c in numeric.columns if c not in drop]], incumbent
