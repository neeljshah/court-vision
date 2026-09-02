"""scripts.platformkit.eval_gate.catalog_rescreen -- UNCHARGED market-relative SCREEN.

The 60 catalog classes and the 86 registry signals were all recorded REJECT /
NOT_EVALUABLE with their per-signal loss differentials never archived
(spa_catalog_report.txt: "historical per-signal loss differentials are not
archived"). This supplies what was missing: per signal, a walk-forward
single-feature logistic on [logit(incumbent), feature] scored against the
incumbent alone, per corpus_unit ordered by event_date (S50), with the paired
per-unit differential ARCHIVED (Q9) beside a summary JSON. A SCREEN, never a
finding: no FWER charge, no prereg. Calibration language only.

Incumbent, always LABELLED: soccer/tennis -> the devigged decimal close
(close_join.gate_corpus_states); nba/mlb -> p_base, the corpus's own base.

Leak contract: rows sorted by event_date within each corpus_unit; expanding
-window folds (stack_fit.expanding_window_splits); a training row must predate
the test block by walkforward.EMBARGO_DAYS (imported, never restated);
standardizer + logistic fit on TRAIN rows only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.combo.corpus_cache import load_gate_corpus  # noqa: E402
from scripts.platformkit.combo.stack_fit import (  # noqa: E402
    build_design, expanding_window_splits, fit_logistic, fit_standardizer, logit,
    predict_proba, standardize)
from scripts.platformkit.eval_gate.dm_test import diebold_mariano  # noqa: E402
from scripts.platformkit.eval_gate.walkforward import EMBARGO_DAYS  # noqa: E402
from scripts.platformkit.foundry import catalogue  # noqa: E402

SPORTS: Tuple[str, ...] = ("nba", "mlb", "soccer", "tennis")
OUT_JSON = _REPO / "docs/evidence/harness/CATALOG_RESCREEN_2026-09-03.json"
DIFF_DIR = _REPO / "data/cache/eval_gate/differentials"
REGISTRY = _REPO / "data/registry/signal_registry.parquet"
DATE_COL = "event_date"
N_FOLDS = 5
MIN_TRAIN = 200      # rows a fold's train window must hold before it is fit
MIN_UNIT_ROWS = 60   # rows a corpus_unit must hold before it is walked
ALPHA = 0.05
_EMPTY: Dict[str, Any] = {"n": 0, "n_eff": 0, "brier_delta": None, "dm_p": None,
                          "corpus_unit": [], "verdict": "NOT_TESTABLE"}

# Each domain signal_catalog's frozen base-column contract; `base_frame` rebuilds
# them on event_id via the SAME replays feature_bundle calls.
INGREDIENTS: Dict[str, Tuple[str, ...]] = {
    "nba": ("elo_home", "elo_away", "elo_diff_hfa", "rest_days_home",
            "rest_days_away", "home_b2b", "away_b2b", "rolling_win10_home"),
    "mlb": ("elo_home", "elo_away", "elo_diff_hfa", "rest_days_home",
            "rest_days_away", "h2h_rate"),
    "soccer": ("lam_home", "lam_away", "lam_total", "rest_days_home", "rest_days_away"),
    "tennis": ("elo_diff", "surf_diff", "best_of", "rest_days_a", "rest_days_b"),
}

# The two signal_catalog modules per sport holding the 60 classes; each module's
# own transform fn and class tuple are resolved by name.
CATALOG_MODULES: Dict[str, Tuple[str, ...]] = {
    "nba": ("domains.basketball_nba.signal_catalog",
            "domains.basketball_nba.signal_catalog_joint"),
    "mlb": ("domains.mlb.signal_catalog", "domains.mlb.signal_catalog_joint"),
    "soccer": ("domains.soccer.signal_catalog", "domains.soccer.signal_catalog_joint"),
    "tennis": ("domains.tennis.signal_catalog", "domains.tennis.signal_catalog_joint"),
}


def base_frame(sport: str) -> pd.DataFrame:
    """event_id + the sport's base ingredient columns, from the domain replays."""
    if sport == "nba":
        from domains.basketball_nba.adapter import _add_rolling_win10, _season_to_int
        from domains.basketball_nba.ratings import walk_forward_elo
        games = pd.read_parquet(_REPO / "data/domains/basketball_nba/games.parquet").copy()
        games["season"] = games["season"].apply(_season_to_int)
        wf = _add_rolling_win10(walk_forward_elo(games))
        wf["event_id"] = wf["game_id"].astype(str)
    elif sport == "mlb":
        from domains.mlb.adapter import MLBAdapter, _add_context
        from domains.mlb.ratings import walk_forward_elo
        wf = _add_context(walk_forward_elo(MLBAdapter()._get_games()))
    elif sport == "soccer":
        from domains.soccer.adapter import SoccerAdapter, _add_rest_days
        from domains.soccer.ratings import walk_forward_goals
        wf = _add_rest_days(walk_forward_goals(SoccerAdapter()._get_matches()))
    elif sport == "tennis":
        from domains.tennis.adapter import TennisAdapter
        from domains.tennis.adapter_helpers import _add_rest_days
        from domains.tennis.elo_walkforward import walk_forward_elo
        wf = _add_rest_days(walk_forward_elo(TennisAdapter()._get_matches()))
        wf["elo_diff"] = wf.get("p1_elo", np.nan) - wf.get("p2_elo", np.nan)
        wf["surf_diff"] = wf.get("p1_surface_elo", np.nan) - wf.get("p2_surface_elo", np.nan)
    else:
        raise ValueError(f"unknown sport {sport!r}")
    wf["event_id"] = wf["event_id"].astype(str)
    wf = wf.reindex(columns=["event_id", *INGREDIENTS[sport]])
    return wf.drop_duplicates("event_id", keep="first").reset_index(drop=True)


def _incumbent(sport: str, corpus: pd.DataFrame) -> Tuple[pd.Series, str]:
    """Incumbent probability per corpus row, plus its honest label."""
    if sport not in ("soccer", "tennis"):
        return corpus["p_base"].astype(float), "p_base"
    from scripts.platformkit.eval_gate.close_join import gate_corpus_states
    close = pd.Series({str(s["game_id"]): float(s["devig_close_prob"])
                       for s in gate_corpus_states(sport, "1900-01-01", "2100-01-01")})
    return corpus["event_id"].astype(str).map(close).astype(float), "devigged_close"


def verdict_of(delta: float, p_value: float) -> str:
    """SCREEN verdict. Positive delta = the candidate lost less than the incumbent."""
    if not (np.isfinite(delta) and np.isfinite(p_value)) or p_value >= ALPHA:
        return "SCREEN_NULL"
    return "SCREEN_POSITIVE" if delta > 0 else "SCREEN_NEGATIVE"


def screen_feature(frame: pd.DataFrame, *, n_folds: int = N_FOLDS, min_train: int = MIN_TRAIN,
                   min_unit_rows: int = MIN_UNIT_ROWS) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Walk one feature per corpus_unit -> (summary, per-row differential).
    `frame` carries event_id, corpus_unit, event_date, y, p_inc, feature."""
    rows: List[pd.DataFrame] = []
    for unit, grp in frame.groupby("corpus_unit", sort=True):
        grp = grp.sort_values(DATE_COL, kind="mergesort")
        keep = np.isfinite(grp[["feature", "p_inc", "y"]].to_numpy(float)).all(axis=1)
        grp = grp.loc[keep].reset_index(drop=True)
        if len(grp) < min_unit_rows:
            continue
        cols = np.column_stack([logit(grp["p_inc"].to_numpy(float)), grp["feature"]])
        y = grp["y"].to_numpy(float)
        p_inc = np.clip(grp["p_inc"].to_numpy(float), 1e-6, 1 - 1e-6)
        dates = pd.to_datetime(grp[DATE_COL]).to_numpy("datetime64[ns]")
        for split in expanding_window_splits(len(grp), 0.5, n_folds):
            test = split.test_idx
            if len(test) == 0:
                continue
            cut = dates[test[0]] - np.timedelta64(EMBARGO_DAYS, "D")
            train = split.train_idx[dates[split.train_idx] < cut]
            if len(train) < min_train:
                continue
            params = fit_standardizer(cols[train])

            def design(idx, _p=params):
                return build_design(list(standardize(cols[idx], _p).T))
            fit = fit_logistic(design(train), y[train])
            p_model = np.clip(predict_proba(design(test), fit.weights), 1e-6, 1 - 1e-6)
            rows.append(pd.DataFrame({
                "event_id": grp["event_id"].to_numpy()[test].astype(str),
                "corpus_unit": str(unit), DATE_COL: dates[test], "y": y[test],
                "p_incumbent": p_inc[test], "p_model": p_model,
                "loss_incumbent": (p_inc[test] - y[test]) ** 2,
                "loss_model": (p_model - y[test]) ** 2}))
    diff = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if diff.empty:
        return dict(_EMPTY, absent_columns=["<no fold met the leak-free minimums>"]), diff
    diff["d"] = diff["loss_incumbent"] - diff["loss_model"]
    dm = diebold_mariano(diff["d"].to_numpy(float), diff["event_id"].tolist())
    return {"n": int(len(diff)), "n_eff": int(dm.n_clusters),
            "brier_delta": float(dm.mean_diff), "dm_p": float(dm.p_value),
            "corpus_unit": sorted(diff["corpus_unit"].unique().tolist()),
            "verdict": verdict_of(dm.mean_diff, dm.p_value)}, diff


def _archive(sport: str, signal: str, diff: pd.DataFrame) -> str:
    """Write the per-unit paired differential (Q9) and return its repo path."""
    path = DIFF_DIR / sport / (re.sub(r"[^A-Za-z0-9._-]", "_", signal) + ".parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    diff.to_parquet(path, index=False)
    return os.path.relpath(path, _REPO).replace("\\", "/")


def _record(sport: str, signal: str, kind: str, incumbent: str,
            frame: Optional[pd.DataFrame], absent: List[str]) -> Dict[str, Any]:
    """One summary row: screen it when the feature resolved, else NOT_TESTABLE."""
    row: Dict[str, Any] = {"signal": signal, "sport": sport, "kind": kind,
                           "incumbent": incumbent}
    if frame is None:
        row.update(_EMPTY, differential_path=None, absent_columns=absent)
        return row
    summary, diff = screen_feature(frame)
    row.update(summary)
    row["absent_columns"] = absent if summary["verdict"] == "NOT_TESTABLE" else []
    row["differential_path"] = _archive(sport, signal, diff) if not diff.empty else None
    return row



def _spine(corpus: pd.DataFrame, inc: pd.Series) -> pd.DataFrame:
    """Keys, label and incumbent that every screened feature attaches to."""
    return pd.DataFrame({
        "event_id": corpus["event_id"].astype(str), "corpus_unit": corpus["corpus_unit"],
        DATE_COL: corpus[DATE_COL], "y": corpus["y"].astype(float),
        "p_inc": inc.to_numpy(float)})


def catalog_rows(sport: str, corpus: pd.DataFrame, inc: pd.Series,
                 label: str) -> List[Dict[str, Any]]:
    """Screen every catalog class of one sport off its own transform fn."""
    from importlib import import_module
    names = list(INGREDIENTS[sport])
    try:
        joined = corpus[["event_id"]].astype(str).merge(base_frame(sport), "left", "event_id")
        matrix = joined[names].to_numpy(float)
        # An unjoined row is all-NaN, but a threshold transform turns that into a
        # finite 0.0 (which once invented a whole WTA unit); mask those rows out.
        joined_rows = np.isfinite(matrix).any(axis=1)
        absent_all = [c for i, c in enumerate(names) if not np.isfinite(matrix[:, i]).any()]
    except Exception as exc:  # a source parquet the replay needs is absent
        matrix = joined_rows = None
        absent_all = [f"{c} (base replay failed: {type(exc).__name__})" for c in names]
    spine, out = _spine(corpus, inc), []
    for module in (import_module(m) for m in CATALOG_MODULES[sport]):
        compute = getattr(module, "_compute_joint_signal_col", None) or module._compute_signal_col
        for cls in getattr(module, "CATALOG_JOINT_SIGNALS", None) or module.CATALOG_SIGNALS:
            name = f"{sport}:{cls.__name__}"
            feature = None if matrix is None else np.where(
                joined_rows, np.asarray(compute(cls, matrix), float), np.nan)
            finite = np.empty(0) if feature is None else feature[np.isfinite(feature)]
            usable = finite.size >= MIN_UNIT_ROWS and np.unique(finite).size >= 2
            frame = spine.assign(feature=feature) if usable else None
            out.append(_record(sport, name, "catalog", label, frame, [] if frame is not None
                               else absent_all or ["<feature is constant on this corpus>"]))
    return out


def _column_index(corpora: Dict[str, pd.DataFrame]) -> Dict[str, Tuple[str, Optional[Path]]]:
    """column -> (sport, parquet path; None means the gate corpus itself)."""
    import pyarrow.parquet as pq
    index: Dict[str, Tuple[str, Optional[Path]]] = {
        col: (sport, None) for sport, frame in corpora.items() for col in frame.columns}
    for entry in catalogue.entries():
        try:
            names = pq.read_schema(entry.path).names
        except Exception:
            continue
        if "event_id" in names or "game_id" in names:
            for col in names:
                index.setdefault(col, (entry.sport, entry.path))
    return index


def registry_rows(corpora: Dict[str, pd.DataFrame], incumbents: Dict[str, Tuple[pd.Series, str]]
                  ) -> List[Dict[str, Any]]:
    """Screen every registry signal whose feature column exists on disk."""
    if not REGISTRY.exists():
        return []
    registry = pd.read_parquet(REGISTRY)  # READ-ONLY: never written here
    index, out = _column_index(corpora), []
    for signal_id in registry["signal_id"].astype(str):
        wanted = (signal_id, signal_id.split(".")[-1])
        column = next((c for c in wanted if c in index), None)
        if column is None:
            out.append(_record("nba", signal_id, "registry", "p_base", None, list(wanted)))
            continue
        sport, path = index[column]
        corpus, (inc, label) = corpora[sport], incumbents[sport]
        values = corpus[column] if path is None else _join_column(corpus, path, column)
        frame = _spine(corpus, inc).assign(feature=pd.to_numeric(values, errors="coerce"))
        out.append(_record(sport, signal_id, "registry", label, frame, []))
    return out


def _join_column(corpus: pd.DataFrame, path: Path, column: str) -> pd.Series:
    side = pd.read_parquet(path)
    key = "event_id" if "event_id" in side.columns else "game_id"
    side = side[[key, column]].rename(columns={key: "event_id"})
    side["event_id"] = side["event_id"].astype(str)
    side = side.drop_duplicates("event_id", keep="first")
    return corpus[["event_id"]].astype(str).merge(
        side, on="event_id", how="left")[column]


def run(out_path: Path = OUT_JSON) -> Dict[str, Any]:
    """Re-screen all 146 signals and write the summary JSON. Uncharged."""
    corpora = {s: load_gate_corpus(s) for s in SPORTS}
    incumbents = {s: _incumbent(s, corpora[s]) for s in SPORTS}
    rows: List[Dict[str, Any]] = [row for sport in SPORTS for row in
                                  catalog_rows(sport, corpora[sport], *incumbents[sport])]
    rows.extend(registry_rows(corpora, incumbents))
    counts = dict(Counter(r["verdict"] for r in rows))
    report = {"generated_for": "S64", "charged": False, "prereg": None, "n_signals": len(rows),
              "note": "SCREEN only -- no charged trial, no finding, calibration language only",
              "verdict_counts": counts, "signals": rows}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":  # pragma: no cover - operator readout
    _r = run()
    print("signals={0} {1}".format(_r["n_signals"], _r["verdict_counts"]))
