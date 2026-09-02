"""S108 feature assembly -- every numeric as-of column the gate corpus and the domain
as-of tables supply, for the SCREEN side of the frozen partition only.

Every candidate name passes through `screen_predictor.check_feature_name`, so a same-game
or in-game column is refused BY NAME before any value is read; the refusals are returned
and printed by the caller. A source with >1 row per event (player / tick grain) is refused
whole. Nothing here reads the VERDICT side. Calibration measurement only.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.combo.corpus_cache import load_gate_corpus
from scripts.platformkit.foundry.screen_predictor import (
    SPINE, ScreenRefused, check_feature_name, corpus_states)
from scripts.platformkit.foundry.tiers import _cluster_ids, partition_corpus

ROOT = Path(__file__).resolve().parents[3]
SPORT_DIR = {"nba": "basketball_nba", "mlb": "mlb", "soccer": "soccer", "tennis": "tennis"}
SEED = 20260903


def asof_sources(sport: str) -> list:
    """Every one-row-per-event as-of parquet under the sport's domain dir, name-sorted."""
    base = ROOT / "data" / "domains" / SPORT_DIR[sport]
    found = set(glob.glob(str(base / "asof_*.parquet"))) | set(glob.glob(str(base / "*_asof*.parquet")))
    return sorted(found)


def _add(cols: dict, name: str, series: pd.Series) -> None:
    """First table wins; a later table only FILLS the gaps of a same-named column."""
    cols[name] = series if name not in cols else cols[name].combine_first(series)


def build(sport: str) -> dict:
    """Assemble the SCREEN-side design matrix + incumbent + labels for one sport."""
    states, table, incumbent = corpus_states(sport)
    part = partition_corpus(states, seed=SEED)
    screen = [s for s in states if str(s.get("event_id", s["game_id"])) in part.screen_ids]
    screen.sort(key=lambda s: (s["state_ts"], str(s["game_id"])))
    ids = [str(s["game_id"]) for s in screen]
    if len(set(ids)) != len(ids):
        raise ValueError("screen side carries a duplicated event_id")
    index = pd.Index(ids, name="event_id")
    p_inc = np.array([float(s["devig_close_prob"]) for s in screen])

    refusals: dict = {}
    cols: dict = {}
    for name in table.columns:                       # the gate corpus's own numeric columns
        try:
            check_feature_name(name, table.columns)
        except ScreenRefused as exc:
            refusals[name] = str(exc)
            continue
        _add(cols, name, pd.to_numeric(table[name], errors="coerce").reindex(index))
    sources: dict = {}
    for path in asof_sources(sport):
        frame = pd.read_parquet(path)
        short = os.path.basename(path)
        key = next((k for k in ("event_id", "game_id") if k in frame.columns), None)
        if key is None:
            refusals[short] = "unavailable: no event_id/game_id key"
            continue
        keys = frame[key].astype(str)
        if keys.duplicated().any():
            refusals[short] = "unavailable: >1 row per %s (player/tick grain)" % key
            continue
        frame = frame.assign(**{key: keys}).set_index(key)
        taken = 0
        for name in frame.select_dtypes(include="number").columns:
            if name in SPINE or name == key:
                continue
            try:
                check_feature_name(name, table.columns)
            except ScreenRefused as exc:
                refusals["%s:%s" % (short, name)] = str(exc)
                continue
            series = pd.to_numeric(frame[name], errors="coerce").reindex(index)
            if not np.isfinite(series.to_numpy(dtype=float)).any():
                refusals["%s:%s" % (short, name)] = "unavailable: no overlap with the screen side"
                continue
            _add(cols, name, series)
            taken += 1
        sources[short] = taken

    frame = pd.DataFrame(cols, index=index)
    dropped = {}
    for name in list(frame.columns):                 # a copy of the offset is not a feature
        values = frame[name].to_numpy(dtype=float)
        if np.nanmax(np.abs(np.nan_to_num(values - p_inc, nan=0.0))) == 0.0:
            dropped[name] = "identical to the incumbent"
        elif np.unique(values[np.isfinite(values)]).size < 2:
            dropped[name] = "constant or empty on the screen side"
    frame = frame.drop(columns=list(dropped))
    missing = [c for c in frame.columns if frame[c].isna().any()]
    for name in missing:                             # missing != bad: median + indicator (B3)
        frame[name + "__isna"] = frame[name].isna().astype(float)

    unit_map = load_gate_corpus(sport, portable=os.environ.get("FOUNDRY_PORTABLE_CORPUS") == "1")
    unit_map = unit_map.assign(event_id=lambda t: t["event_id"].astype(str))
    unit_map = unit_map.drop_duplicates("event_id").set_index("event_id")["corpus_unit"].astype(str)
    cluster_key, cluster_ids = _cluster_ids(screen, sport)
    return {"sport": sport, "incumbent": incumbent, "X": frame, "p_inc": p_inc,
            "y": np.array([int(s["outcome"]) for s in screen]),
            "dates": np.array([np.datetime64(s["game_date"]) for s in screen]),
            "units": unit_map.reindex(index).fillna("NA").to_numpy(),
            "cluster_key": cluster_key, "cluster_ids": np.array(cluster_ids),
            "n_states": len(states), "n_screen": len(screen), "n_missing_cols": len(missing),
            "screen_sha256": part.screen_sha256, "partition_basis": part.basis,
            "refusals": refusals, "sources": sources, "dropped": dropped}
