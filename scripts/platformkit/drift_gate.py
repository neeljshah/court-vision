"""Adversarial-validation gate for feature-family distribution drift.

This is calibration hygiene, not a prediction or edge measure.  An AMBER or
RED family should have its calibration refit before it is trusted again.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold


LEDGER_PATH = Path(os.environ.get("DRIFT_LEDGER_PATH", "data/ab_reports/drift_ledger.jsonl"))
_FAMILIES = ("per36", "load", "embedding", "elasticity")


def _family(column: str) -> str:
    """Map a feature name to its documented prefix family, or base."""
    name = str(column).lower()
    for family in _FAMILIES:
        if name.startswith(family + "_") or name == family:
            return family
    if "_per36_" in name or name.endswith("_per36"):
        return "per36"
    if name.startswith("style_embedding_"):
        return "embedding"
    return "base"


def _status(auc: float) -> str:
    if auc >= 0.90:
        return "RED"
    if auc >= 0.75:
        return "AMBER"
    return "GREEN"


def _append(rows: Sequence[dict[str, object]]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, allow_nan=False) + "\n")


def _print_table(rows: Sequence[dict[str, object]]) -> None:
    print("family       auc    status")
    print("------------ ------ ------")
    for row in rows:
        print("{0:12s} {1:0.3f}  {2}".format(str(row["family"]), float(row["auc"]), row["status"]))


def check_drift(matrix: object, dates: Sequence[object], feature_cols: Sequence[str],
                window_days: int = 30) -> dict[str, dict[str, object]]:
    """Classify old versus recent rows and report three-fold AUC by family.

    Recent rows are those within the final ``window_days`` calendar days of the
    supplied date range.  An AUC of at least .75 is AMBER; at least .90 is RED.
    """
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    frame = pd.DataFrame(matrix, columns=list(feature_cols)).copy()
    if len(frame) != len(dates):
        raise ValueError("matrix and dates must have the same number of rows")
    if not feature_cols or frame.shape[1] != len(feature_cols):
        raise ValueError("feature_cols must describe every matrix column")
    stamp = pd.to_datetime(pd.Series(dates), errors="raise", utc=True)
    recent = (stamp > stamp.max() - pd.Timedelta(days=window_days)).to_numpy(dtype=int)
    if recent.min() == recent.max() or min(np.bincount(recent)) < 3:
        raise ValueError("need at least three old and three recent rows")

    frame = frame.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    groups: dict[str, list[str]] = {}
    for column in feature_cols:
        groups.setdefault(_family(column), []).append(column)
    splitter = StratifiedKFold(n_splits=3, shuffle=True, random_state=0)
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, object]] = []
    for family, columns in groups.items():
        scores = []
        values = frame.loc[:, columns]
        for train, test in splitter.split(values, recent):
            model = HistGradientBoostingClassifier(random_state=0).fit(values.iloc[train], recent[train])
            scores.append(roc_auc_score(recent[test], model.predict_proba(values.iloc[test])[:, 1]))
        auc = float(np.mean(scores))
        rows.append({"ts": now, "family": family, "auc": auc, "status": _status(auc)})
    _append(rows)
    _print_table(rows)
    return {str(row["family"]): {"auc": row["auc"], "status": row["status"]} for row in rows}


def main() -> None:
    """Run the gate on the signal-foundry minutes matrix."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-days", type=int, default=30)
    args = parser.parse_args()
    from scripts.platformkit.signal_foundry import build_features
    from scripts.platformkit.teacher_student_ab import LOAD_FEATURES

    nba = Path(os.environ.get("NBA_DATA_ROOT", "data")) / "nba"
    frame = build_features(
        pd.read_parquet(nba / "player_tracking_features_asof.parquet"),
        pd.read_parquet(nba / "player_load_state_asof.parquet"),
        pd.read_parquet(nba / "player_embeddings_asof.parquet"),
    ).dropna(subset=["gameDate"])
    columns = [name for name in frame if name.endswith(("_per36_l5", "_per36_l10"))
               or name in LOAD_FEATURES or name.startswith("style_embedding_")
               or name.startswith("elasticity_") or name in ("minutes_expanding", "minutes_l5")]
    check_drift(frame.loc[:, columns], frame["gameDate"], columns, args.window_days)


if __name__ == "__main__":
    main()
