"""scripts.platformkit.live_edge.combine.persist_minutes -- LIVE-EDGE D1-PREREQS.

STEP 0 (premise check, 2026-07-14): minutes_combiner.py fits+scores a model
every run but never persists one -- data/omni/live_edge/combine held only
report JSON (confirmed: no .pkl on disk). The shadow conditioner's
c1_minutes_prior mechanism is registered but forced INACTIVE for exactly this
reason (shadow/conditioner.py:14-21). This module closes that gap: refit the
SAME winning configuration minutes_combiner.py's own report already selected
(hist_gb, features=[baseline_min, foul_rate_prior], seed=0 -- see
data/omni/live_edge/combine/minutes_combiner_report.json:
best_model="hist_gb:baseline_plus_foul_rate_seed0"), reusing its exact
feature-build and split (mc._add_features, ksn.split_discovery_reserve,
mc._fit_predict, mc._pinball_median -- no forked logic), and persist the
fitted estimator + its feature spec via joblib.

Does NOT edit minutes_combiner.py (import only, per lane OWNS boundary).

INVARIANTS: pandas/sklearn/joblib + stdlib only. <=300 LOC. ASCII stdout.
Never writes data/registry/ or the claims journal. No $/edge claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_persist_minutes.py -q
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import joblib
import pandas as pd

from scripts.platformkit.io_atomic import write_text_atomic
from scripts.platformkit.live_edge.combine import minutes_combiner as mc
from scripts.platformkit.omni import k_sweep_nba as ksn

_OUT_DIR = pathlib.Path("data/omni/live_edge/combine")
_PKL_NAME = "minutes_estimator.pkl"
_META_NAME = "minutes_estimator_meta.json"

# The exact winning config minutes_combiner.py's own OOS sweep selected
# (best_model="hist_gb:baseline_plus_foul_rate_seed0" in the real report).
# Hardcoded, not re-derived by argmax here: the fidelity test's job is to
# prove THIS artifact reproduces THAT reported number, not to re-discover it.
_MODEL_NAME = "hist_gb"
_FEATURE_COLS = ["baseline_min", "foul_rate_prior"]
_SEED = 0


def fit_and_persist(source=None, out_dir: pathlib.Path | None = None) -> dict[str, Any]:
    """Refit C1's winning combiner config on discovery, score on reserve, and
    persist the fitted estimator + feature spec. Returns a report dict
    (mirrors minutes_combiner's blocked-frame contract)."""
    if isinstance(source, pd.DataFrame) and source.empty:
        return {"blocked": True, "reason": "empty sweep frame"}
    df = ksn._load_sweep_frame(source)  # noqa: SLF001 -- same shared loader C1 uses
    if df.empty:
        return {"blocked": True, "reason": "empty sweep frame"}
    df = mc._add_features(df)  # noqa: SLF001 -- reuse C1's exact leak-free feature build
    discovery, reserve = ksn.split_discovery_reserve(df)
    discovery = discovery.dropna(subset=_FEATURE_COLS)
    reserve = reserve.dropna(subset=_FEATURE_COLS)
    if len(discovery) < 50 or len(reserve) < 50:
        return {"blocked": True, "reason": f"insufficient rows after cold-start drop "
                                            f"(discovery={len(discovery)}, reserve={len(reserve)})"}

    X_train, y_train = discovery[_FEATURE_COLS].to_numpy(), discovery["min"].to_numpy()
    X_test, y_test = reserve[_FEATURE_COLS].to_numpy(), reserve["min"].to_numpy()
    model, y_pred = mc._fit_predict(_MODEL_NAME, X_train, y_train, X_test, _SEED)  # noqa: SLF001
    reserve_pinball = mc._pinball_median(y_test, y_pred)  # noqa: SLF001

    meta = {
        "model_name": _MODEL_NAME, "feature_cols": _FEATURE_COLS, "seed": _SEED,
        "n_discovery": int(len(discovery)), "n_reserve": int(len(reserve)),
        "reserve_pinball_at_fit": reserve_pinball,
        "source_claim": mc._FOUL_META_CLAIM_ID, "market_family": "ingame.props.minutes",
    }
    d = out_dir or _OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, d / _PKL_NAME)
    write_text_atomic(d / _META_NAME, json.dumps(meta, indent=2, default=str))
    return meta


def load_estimator(out_dir: pathlib.Path | None = None):
    """(model, meta) if a persisted estimator exists, else (None, None) --
    the shadow conditioner's own not-fabricating-an-edge contract."""
    d = out_dir or _OUT_DIR
    pkl_path, meta_path = d / _PKL_NAME, d / _META_NAME
    if not pkl_path.is_file() or not meta_path.is_file():
        return None, None
    return joblib.load(pkl_path), json.loads(meta_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    out = fit_and_persist()
    for k, v in out.items():
        print(f"[persist_minutes] {k}: {v}")


__all__ = ["fit_and_persist", "load_estimator"]
