"""Real gap-arm per-tick series + game-level CPCV states for the Hedge trial.

Prereg: docs/research/organization-sprint/HEDGE_TRIAL_PREREG_2026-09-01.md.
Every arm series is produced by the arm module's OWN walk-forward code (private
helpers are called, never re-implemented); absent = None. Calibration only.
ASCII only; <=300 LOC. Per-file test: scripts/platformkit/test_hedge_trial_arms.py
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.ingame import gap_blend_arm, gap_offset_arm, gap_regime_arm, hedge_combiner as hc
from scripts.platformkit.ingame.run_gap_arms_real_corpus import _load_ticks
from scripts.platformkit.ingame_state_lift import _feature_matrix
from scripts.platformkit.mlb_state_features import parse_state
from scripts.platformkit.regime_calibration import buckets, fit_per_regime
from scripts.platformkit.wp_diag_oos import _game_dates
from scripts.platformkit.wp_diag_series import load_records

Series = List[Optional[float]]


def load_corpus(store: Path, sport: str) -> tuple[List[Dict[str, Any]], Optional[pd.DataFrame]]:
    """MLB: canonical de-duplicated ticks + state features (the real runner's loader).
    soccer_intl: normalized ticks only; in_window is undefined there -> True."""
    if sport == "mlb":
        return _load_ticks(store)
    ticks = load_records(store / sport)
    for row_id, tick in enumerate(ticks):
        tick.update({"_row_id": row_id, "in_window": True})
    return ticks, score_diff_features(ticks)


def score_diff_features(ticks: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """E4's signal for a non-MLB store: home minus away score parsed from
    state_summary by the sport-blind parse_state regex; NaN where absent."""
    rows = []
    for t in ticks:
        state = parse_state(t.get("state_summary") or t.get("raw", {}).get("state_summary"))
        home, away = state["home_score"], state["away_score"]
        rows.append({"game": t["game"], "timestamp": t["timestamp"],
                     "score_diff": home - away if None not in (home, away) else float("nan")})
    return pd.DataFrame(rows)


def _by_row(frame: pd.DataFrame, n: int, column: str = "arm_b_prob") -> Series:
    out: Series = [None] * n
    for row_id, value in zip(frame["_row_id"], frame[column]):
        out[int(row_id)] = float(value) if math.isfinite(float(value)) else None
    return out


def e4_blend_series(ticks: Sequence[Mapping[str, Any]], features: pd.DataFrame,
                    w_max: float = gap_blend_arm._DEFAULT_W_MAX,
                    max_dev: float = gap_blend_arm._DEFAULT_MAX_DEVIATION,
                    column: str = "arm_b_prob") -> Series:
    """E4 via the module's own walk-forward; column arm_a_prob = guard only (weight 0)."""
    signal = features.set_index(["game", "timestamp"])["score_diff"].to_dict()
    keep = [t for t in ticks if pd.notna(signal.get((t["game"], t["timestamp"])))]
    rows = [{**t, "state_signal": float(signal[(t["game"], t["timestamp"])])} for t in keep]
    frame = gap_blend_arm._frame(rows)
    assert len(frame) == len(rows), "gap_blend_arm._frame dropped rows; alignment lost"
    frame["_row_id"] = [int(t["_row_id"]) for t in rows]
    scored, _ = gap_blend_arm._walk_forward(frame, w_max, max_dev)
    return _by_row(scored, len(ticks), column)


def e1_offset_series(ticks: Sequence[Mapping[str, Any]], features: pd.DataFrame,
                     max_estimators: int = 300) -> Series:
    usable = [dict(t, raw=t.get("raw", {})) for t in ticks
              if all(t.get(k) is not None for k in ("model_prob", "market_prob", "outcome"))]
    joined, columns = _feature_matrix(usable, features)
    assert "model_prob" not in columns and not any("market" in c.lower() for c in columns)
    scored, _ = gap_offset_arm._walk_forward(joined, columns, _game_dates(usable), max_estimators)
    return _by_row(scored, len(ticks))


def e2_regime_series(ticks: Sequence[Mapping[str, Any]], min_n: int = 200) -> Series:
    """gap_regime_arm.evaluate's loop, re-driven from its own helpers (it discards
    per-tick scores). Same filter: required keys present AND in_window."""
    required = {"game", "model_prob", "market_prob", "outcome"}
    usable = [dict(t) for t in ticks if required.issubset(t) and t.get("in_window", True)]
    out: Series = [None] * len(ticks)
    dates = sorted({gap_regime_arm._date(t) for t in usable})
    for test_date in dates[1:]:
        train = [t for t in usable if gap_regime_arm._date(t) < test_date]
        test = [t for t in usable if gap_regime_arm._date(t) == test_date]
        if not train or not test:
            continue
        assert max(gap_regime_arm._date(t) for t in train) < test_date
        fits = fit_per_regime([float(t["model_prob"]) for t in train], [float(t["outcome"]) for t in train],
                              buckets(gap_regime_arm._month_confidence_rows(train)), min_n=min_n)
        probs, _ = gap_regime_arm._apply(fits, buckets(gap_regime_arm._month_confidence_rows(test)),
                                         [float(t["model_prob"]) for t in test])
        for t, p in zip(test, probs):
            out[int(t["_row_id"])] = float(p) if math.isfinite(float(p)) else None
    return out


def arm_series(ticks: Sequence[Mapping[str, Any]], features: Optional[pd.DataFrame],
               sport: str, max_estimators: int = 300,
               only: Optional[Sequence[str]] = None) -> Dict[str, Series]:
    """Hedge mode (only=None): S5's arm set. Candidate mode: just the named arms."""
    want = set(only) if only else {"raw_model", "e2_regime"} | ({"e4_blend", "e1_offset"} if sport == "mlb" else set())
    arms: Dict[str, Series] = {"raw_model": [float(t["model_prob"]) for t in ticks]}
    if "e4_blend" in want:
        assert features is not None
        arms["e4_blend"] = e4_blend_series(ticks, features)
    if "e1_offset" in want:
        arms["e1_offset"] = e1_offset_series(ticks, features, max_estimators)
    if "e2_regime" in want:
        arms["e2_regime"] = e2_regime_series(ticks)
    return arms


def hedge_series(ticks: Sequence[Mapping[str, Any]], arms: Mapping[str, Series], t_rounds: int) -> Series:
    """Per-tick Hedge predictions in evaluate()'s exact fold order, via the
    combiner's public state API. The runner asserts its Brier equals evaluate()'s."""
    names = tuple(arms)
    games, _ = hc._group_games(ticks, arms, names)
    by_date: Dict[str, List[str]] = defaultdict(list)
    for gid, game in games.items():
        by_date[game["date"]].append(gid)
    dates = sorted(by_date)
    state = hc.initial_state(names, t_rounds)
    out: Series = [None] * len(ticks)
    for idx in range(1, len(dates)):
        for gid in sorted(by_date[dates[idx - 1]]):
            game = games[gid]
            state = hc.fold_settlement(state, gid, {n: p for n, p in game["arm_ticks"].items() if p},
                                       game["outcome"])
        for gid in sorted(by_date[dates[idx]]):
            for i in games[gid]["indices"]:
                out[i] = hc.predict(state, {n: arms[n][i] for n in names})
    return out


def _iso(stamp: str) -> datetime:
    return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))


# RT-13. `home`/`away` below are SYNTHESIZED from the game_id suffix, not carried
# from the corpus: `mlb-2026-06-28-NYY-BOS` -> home='' away='BOS' (measured), so
# `_same_team` is True for every pair of dash-form ids; a Kalshi ticker
# `KXMLBGAME-26JUL011310AAABBB0` -> home='BB0' away='AAB', which shifts the real
# codes by the trailing sequence digit. The purge that cpcv_engine runs on these
# keys is therefore NOT a team purge, and n_train / any "purged by team" wording
# in an artifact must not be read as one. Every state carries TEAM_KEY_SOURCE so a
# consumer can see that. Carrying the real home/away through load_corpus would
# change n_train on both corpora, so it is PROPOSED, not applied here.
TEAM_KEY_SOURCE = "game_id_suffix (synthesized -- NOT real team codes, RT-13)"


def game_states(ticks: Sequence[Mapping[str, Any]], arms: Mapping[str, Series]) -> List[dict]:
    """One walk_forward-shaped state per game for cpcv_evaluate. Checkpoint = the
    median tick by timestamp; state_ts = last tick + 1s; feature_avail = last tick.

    `home`/`away` are synthesized from the game_id suffix -- see TEAM_KEY_SOURCE."""
    groups: Dict[str, List[int]] = defaultdict(list)
    for i, t in enumerate(ticks):
        if t.get("outcome") is not None and t.get("market_prob") is not None:
            groups[str(t["game"])].append(i)
    states = []
    for gid, idx in groups.items():
        idx = sorted(idx, key=lambda i: str(ticks[i]["timestamp"]))
        mid, last = idx[len(idx) // 2], _iso(ticks[idx[-1]]["timestamp"])
        code = gid.rsplit("-", 1)[-1][-6:]
        states.append({
            "game_id": gid, "state_ts": (last + timedelta(seconds=1)).isoformat(),
            "home": code[3:], "away": code[:3], "team_key_source": TEAM_KEY_SOURCE,
            "outcome": int(float(ticks[mid]["outcome"])),
            "devig_close_prob": float(ticks[mid]["market_prob"]),
            "features": {"checkpoint": {n: arms[n][mid] for n in arms},
                         "arm_ticks": {n: [p for p in (arms[n][i] for i in idx) if p is not None] for n in arms}},
            "feature_avail": {"checkpoint": last.isoformat(), "arm_ticks": last.isoformat()}})
    return sorted(states, key=lambda s: s["state_ts"])


def hedge_predictor(arm_names: Sequence[str], t_rounds: int):
    """Batch Hedge over a CPCV path's purged train games (final weights are
    order-invariant), cached per train-set CONTENT.

    RT-2: keying on ``id(train)`` served one split's Hedge state to another --
    cpcv_evaluate rebinds ``train_states`` per split and CPython reuses the
    freed address (64 states / 28 splits -> 3 distinct addresses, 400 of 448
    predictor calls served a stale split's weights, which can include the
    current test block). The key is the train game_id set, so a different
    train set can never hit another split's entry."""
    cache: Dict[tuple, hc.HedgeState] = {}

    def predict(train: List[dict], test: dict, _select_inside: bool) -> float:
        key = tuple(sorted(str(s["game_id"]) for s in train))
        if key not in cache:
            state = hc.initial_state(arm_names, t_rounds)
            for s in train:
                state = hc.fold_settlement(state, s["game_id"], s["features"]["arm_ticks"], s["outcome"])
            cache[key] = state
        p = hc.predict(cache[key], test["features"]["checkpoint"])
        return float(p if p is not None else test["features"]["checkpoint"]["raw_model"])
    return predict


def raw_predictor(_train: List[dict], test: dict, _select_inside: bool) -> float:
    return float(test["features"]["checkpoint"]["raw_model"])


def brier(p: Sequence[float], y: Sequence[float]) -> float:
    p_arr, y_arr = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    return float(np.mean((p_arr - y_arr) ** 2)) if len(p_arr) else float("nan")
