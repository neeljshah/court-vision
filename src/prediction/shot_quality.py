"""
Shot quality model: xPTS = expected points per shot attempt.

Training: logistic regression on (shot_zone, defender_dist, shot_clock,
catch_and_shoot) from CV games (shot_log_enriched.csv).

For non-CV games, applies spatial priors from SpatialPrior to impute
defender_distance / shot_clock before predicting.

Outputs:
  - xFG  (expected field goal probability)
  - xPTS (xFG * shot_value, where 3pt zones score 3, else 2)
  - confidence (0-1, from SourceValue)

Model persisted to data/models/shot_quality.pkl.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_MODEL_PATH  = Path("data/models/shot_quality.pkl")
_DATA_PATH   = Path("data/shot_log_enriched.csv")
_3PT_ZONES   = {"3pt_arc", "corner_3", "long_2"}   # zones worth 3 pts

_ZONE_CATS = [
    "paint", "mid_range", "3pt_arc", "corner_3", "long_2", "backcourt", "other"
]

# ── feature building ─────────────────────────────────────────────────────────

def _zone_to_int(zone: str) -> int:
    try:
        return _ZONE_CATS.index(zone)
    except ValueError:
        return len(_ZONE_CATS) - 1   # "other"


def _shot_value(zone: str) -> int:
    return 3 if zone in _3PT_ZONES else 2


def _build_features(df: pd.DataFrame) -> np.ndarray:
    """Build feature matrix from shot DataFrame."""
    zone_int    = df["court_zone"].apply(_zone_to_int).values
    def_dist    = df["defender_distance"].fillna(5.0).clip(0, 30).values
    shot_clock  = df.get("shot_clock", pd.Series(12.0, index=df.index)).fillna(12.0).clip(0, 24).values
    catch_shoot = df.get("catch_and_shoot", pd.Series(0, index=df.index)).fillna(0).astype(float).values
    return np.column_stack([zone_int, def_dist, shot_clock, catch_shoot])


# ── model class ───────────────────────────────────────────────────────────────

class ShotQualityModel:
    """
    xPTS model trained on CV shot log data.

    If insufficient labeled data (<10 shots with known outcomes), falls back
    to a zone-based heuristic (NBA average FG% by zone).
    """

    _ZONE_BASELINE: Dict[str, float] = {
        "paint":    0.60,
        "mid_range": 0.40,
        "3pt_arc":  0.36,
        "corner_3": 0.39,
        "long_2":   0.34,
        "backcourt": 0.10,
        "other":    0.42,
    }

    def __init__(self) -> None:
        self._model: Optional[Any] = None
        self._fitted = False
        self._n_train = 0

    # ── public ────────────────────────────────────────────────────────────

    def fit(self, df: Optional[pd.DataFrame] = None) -> "ShotQualityModel":
        """
        Train on labeled shots. df must have court_zone, defender_distance,
        shot_clock, catch_and_shoot, made columns.
        """
        if df is None:
            if not _DATA_PATH.exists():
                log.warning("ShotQualityModel: no data at %s; using heuristic", _DATA_PATH)
                return self
            df = pd.read_csv(_DATA_PATH)

        labeled = df[df["made"].notna()].copy()
        if len(labeled) < 10:
            log.warning(
                "ShotQualityModel: only %d labeled shots — heuristic fallback", len(labeled)
            )
            return self

        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline

            X = _build_features(labeled)
            y = labeled["made"].astype(int).values

            pipe = Pipeline([
                ("scaler", StandardScaler()),
                ("lr",     LogisticRegression(max_iter=500, C=1.0)),
            ])
            pipe.fit(X, y)
            self._model   = pipe
            self._fitted  = True
            self._n_train = len(labeled)
            log.info("ShotQualityModel: trained on %d shots", self._n_train)
        except ImportError:
            log.error("ShotQualityModel: sklearn not available; heuristic fallback")
        except Exception as exc:
            log.error("ShotQualityModel fit failed: %s", exc)

        return self

    def predict(
        self,
        shot_zone: str,
        defender_distance: float,
        shot_clock: float = 12.0,
        catch_and_shoot: int = 0,
    ) -> Tuple[float, float, float]:
        """
        Predict (xFG, xPTS, confidence).

        confidence = 0.60 if model fitted, 0.35 for heuristic.
        """
        sv = _shot_value(shot_zone)

        if self._fitted and self._model is not None:
            row = pd.DataFrame([{
                "court_zone":       shot_zone,
                "defender_distance": defender_distance,
                "shot_clock":        shot_clock,
                "catch_and_shoot":   catch_and_shoot,
            }])
            X    = _build_features(row)
            xfg  = float(self._model.predict_proba(X)[0, 1])
            conf = min(0.60, 0.30 + 0.001 * self._n_train)
        else:
            xfg  = self._ZONE_BASELINE.get(shot_zone, 0.42)
            conf = 0.35

        return xfg, round(xfg * sv, 4), round(conf, 4)

    def predict_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorized prediction on a shot DataFrame."""
        results = []
        for _, row in df.iterrows():
            xfg, xpts, conf = self.predict(
                shot_zone        = str(row.get("court_zone", "other")),
                defender_distance = float(row.get("defender_distance", 5.0) or 5.0),
                shot_clock        = float(row.get("shot_clock", 12.0) or 12.0),
                catch_and_shoot   = int(row.get("catch_and_shoot", 0) or 0),
            )
            results.append({"xFG": xfg, "xPTS": xpts, "xpts_confidence": conf})
        return pd.DataFrame(results, index=df.index)

    def save(self, path: Path = _MODEL_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump({"model": self._model, "n_train": self._n_train}, fh)
        log.info("ShotQualityModel saved to %s", path)

    @classmethod
    def load(cls, path: Path = _MODEL_PATH) -> "ShotQualityModel":
        obj = cls()
        path = Path(path)
        if path.exists():
            try:
                with open(path, "rb") as fh:
                    state = pickle.load(fh)
                obj._model    = state["model"]
                obj._n_train  = state.get("n_train", 0)
                obj._fitted   = obj._model is not None
                log.info("ShotQualityModel loaded from %s", path)
            except Exception as exc:
                log.warning("ShotQualityModel load failed: %s", exc)
        return obj


# ── singleton helper ──────────────────────────────────────────────────────────

_instance: Optional[ShotQualityModel] = None


def get_shot_quality_model(retrain: bool = False) -> ShotQualityModel:
    """Return the fitted singleton model (load from disk if available)."""
    global _instance
    if _instance is None or retrain:
        _instance = ShotQualityModel.load()
        if not _instance._fitted or retrain:
            _instance = ShotQualityModel().fit()
            _instance.save()
    return _instance
