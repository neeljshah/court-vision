"""
Fusion layer: spatial prior.

Learns defender_distance / spacing distributions from A/B-grade CV games
keyed on (shot_zone, clock_bucket, score_diff_bucket).

For non-CV games, returns a SourceValue with source="spatial_prior" and
confidence proportional to how much CV data exists for that context bucket.

Data source: data/shot_log_enriched.csv (or caller-supplied DataFrame).
Cache: data/fusion/spatial_prior_cache.parquet
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from src.fusion.source_registry import SourceValue

log = logging.getLogger(__name__)

_DATA_PATH   = Path("data/shot_log_enriched.csv")
_CACHE_PATH  = Path("data/fusion/spatial_prior_cache.parquet")
_MIN_SAMPLES = 3   # minimum CV observations to produce a prior (else returns None)

# ── bucketing helpers ─────────────────────────────────────────────────────

def _clock_bucket(shot_clock: float) -> str:
    if shot_clock <= 7:
        return "late"
    if shot_clock <= 15:
        return "mid"
    return "early"


def _score_diff_bucket(score_diff: int) -> str:
    if score_diff <= -10:
        return "losing_big"
    if score_diff <= -4:
        return "losing"
    if score_diff <= 4:
        return "close"
    if score_diff <= 10:
        return "winning"
    return "winning_big"


# ── main class ────────────────────────────────────────────────────────────

class SpatialPrior:
    """
    Fits spatial distributions from CV game data and serves per-bucket priors.

    Fit once, then call .get() for each shot context.
    """

    def __init__(
        self,
        data_path: Path = _DATA_PATH,
        cache_path: Path = _CACHE_PATH,
        min_samples: int = _MIN_SAMPLES,
    ) -> None:
        self._data_path  = Path(data_path)
        self._cache_path = Path(cache_path)
        self._min_samples = min_samples
        self._stats: Optional[pd.DataFrame] = None   # bucket -> (mean, std, count)
        self._global: dict = {}                       # fallback global stats

    # ── public ────────────────────────────────────────────────────────────

    def fit(self, df: Optional[pd.DataFrame] = None) -> "SpatialPrior":
        """
        Fit bucket distributions.

        Args:
            df: Pre-loaded shot DataFrame. If None, loads from _data_path.
        """
        if df is None:
            if not self._data_path.exists():
                log.warning("SpatialPrior: data file not found at %s", self._data_path)
                return self
            df = pd.read_csv(self._data_path)

        required = {"court_zone", "defender_distance"}
        if not required.issubset(df.columns):
            log.warning("SpatialPrior: missing columns %s", required - set(df.columns))
            return self

        df = df.copy()
        df["shot_clock"] = df.get("shot_clock", pd.Series(dtype=float)).fillna(12.0)
        df["score_diff"] = df.get("score_diff", pd.Series(dtype=int)).fillna(0).astype(int)
        df["clock_bucket"]      = df["shot_clock"].apply(_clock_bucket)
        df["score_diff_bucket"] = df["score_diff"].apply(_score_diff_bucket)

        group_cols = ["court_zone", "clock_bucket", "score_diff_bucket"]
        features   = ["defender_distance", "team_spacing"]
        available  = [c for c in features if c in df.columns]

        records = []
        for key, grp in df.groupby(group_cols):
            if len(grp) < self._min_samples:
                continue
            row: dict = dict(zip(group_cols, key))
            row["n"] = len(grp)
            for feat in available:
                row[f"{feat}_mean"] = float(grp[feat].mean())
                row[f"{feat}_std"]  = float(grp[feat].std())
            records.append(row)

        if records:
            self._stats = pd.DataFrame(records).set_index(group_cols)
            log.info("SpatialPrior: fit %d context buckets from %d shots",
                     len(records), len(df))
        else:
            log.warning("SpatialPrior: no buckets with >=%d samples", self._min_samples)

        # global fallback
        for feat in available:
            self._global[feat] = {
                "mean": float(df[feat].mean()),
                "std":  float(df[feat].std()),
                "n":    len(df),
            }

        self._cache(df)
        return self

    def get(
        self,
        feature: str,
        shot_zone: str,
        shot_clock: float,
        score_diff: int = 0,
    ) -> Optional[SourceValue]:
        """
        Return prior SourceValue for `feature` in a given game context.

        Returns None if no CV data at all.
        """
        if self._stats is None and not self._global:
            log.debug("SpatialPrior not fitted; returning None")
            return None

        cb  = _clock_bucket(shot_clock)
        sdb = _score_diff_bucket(score_diff)
        key = (shot_zone, cb, sdb)

        if self._stats is not None and key in self._stats.index:
            row     = self._stats.loc[key]
            mean_col = f"{feature}_mean"
            if mean_col not in row.index:
                return self._global_fallback(feature)
            n       = int(row["n"])
            value   = float(row[mean_col])
            # confidence scales with sample count, capped at 0.40
            conf    = min(0.40, 0.10 + 0.01 * n)
            return SourceValue(
                value=value,
                source="spatial_prior",
                confidence=round(conf, 4),
                meta={"bucket": key, "n": n, "std": float(row.get(f"{feature}_std", 0))},
            )

        return self._global_fallback(feature)

    def save(self) -> None:
        """Persist fitted stats to cache."""
        if self._stats is not None:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._stats.reset_index().to_parquet(self._cache_path, index=False)
            log.debug("SpatialPrior saved to %s", self._cache_path)

    @classmethod
    def load(cls, cache_path: Path = _CACHE_PATH) -> "SpatialPrior":
        """Load from cache without re-fitting."""
        prior = cls(cache_path=cache_path)
        cache_path = Path(cache_path)
        if cache_path.exists():
            df = pd.read_parquet(cache_path)
            group_cols = ["court_zone", "clock_bucket", "score_diff_bucket"]
            prior._stats = df.set_index(group_cols) if all(c in df.columns for c in group_cols) else None
            log.info("SpatialPrior loaded %d buckets from cache", len(df) if prior._stats is not None else 0)
        return prior

    # ── private ───────────────────────────────────────────────────────────

    def _global_fallback(self, feature: str) -> Optional[SourceValue]:
        if feature not in self._global:
            return None
        g = self._global[feature]
        return SourceValue(
            value=g["mean"],
            source="spatial_prior",
            confidence=0.25,   # low conf: global, not bucket-specific
            meta={"bucket": "global", "n": g["n"], "std": g["std"]},
        )

    def _cache(self, df: pd.DataFrame) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self._stats is not None:
                self._stats.reset_index().to_parquet(self._cache_path, index=False)
        except Exception as exc:
            log.warning("SpatialPrior cache write failed: %s", exc)
