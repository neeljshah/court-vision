"""signal_attribution.py — Linear attribution of CLV to feature-group signal flags.

Fits a linear regression of CLV on four binary feature-group flags:
  cv_features, api_features, timing_signal, pinnacle_gate

Usage (file-based):
    python -m src.prediction.signal_attribution

Usage (programmatic):
    from src.prediction.signal_attribution import SignalAttributionModel
    model = SignalAttributionModel()
    result = model.fit("data/output/clv_training_data.csv")
    # or pass a DataFrame directly:
    result = model.fit(df)

Output: data/output/signal_attribution.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

log = logging.getLogger(__name__)

_FEATURE_GROUPS = ["cv_features", "api_features", "timing_signal", "pinnacle_gate"]
_CLV_COL = "clv"
_DEFAULT_INPUT = Path("data/output/clv_training_data.csv")
_DEFAULT_OUTPUT = Path("data/output/signal_attribution.json")


class SignalAttributionModel:
    """Fits a linear regression of CLV on feature-group flags."""

    def __init__(self) -> None:
        self._coefs: Optional[Dict[str, float]] = None
        self._intercept: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        source: Union[str, Path, pd.DataFrame],
        output_path: Union[str, Path] = _DEFAULT_OUTPUT,
    ) -> Dict[str, float]:
        """Fit the model and return a dict of {feature_group: coefficient}.

        Parameters
        ----------
        source:
            Path to the CSV file **or** a pre-loaded DataFrame.
            If a path, the file must contain the columns in ``_FEATURE_GROUPS``
            plus ``clv``.  If the file is absent the method returns an empty
            result without raising.
        output_path:
            Where to write ``signal_attribution.json``.

        Returns
        -------
        dict
            ``{"cv_features": float, "api_features": float, ...}``
            Empty dict if the input data is unavailable or invalid.
        """
        df = self._load(source)
        if df is None or df.empty:
            log.warning("SignalAttributionModel: no data available — skipping fit")
            return {}

        missing = [c for c in _FEATURE_GROUPS + [_CLV_COL] if c not in df.columns]
        if missing:
            log.warning("SignalAttributionModel: missing columns %s — skipping fit", missing)
            return {}

        X = df[_FEATURE_GROUPS].astype(float).values
        y = df[_CLV_COL].astype(float).values

        if len(y) < 2:
            log.warning("SignalAttributionModel: need ≥2 rows to fit — skipping")
            return {}

        reg = LinearRegression(fit_intercept=True)
        reg.fit(X, y)

        self._coefs = dict(zip(_FEATURE_GROUPS, reg.coef_.tolist()))
        self._intercept = float(reg.intercept_)

        result = dict(self._coefs)
        result["intercept"] = self._intercept

        self._print_coefficients()
        self._save(result, output_path)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(
        self, source: Union[str, Path, pd.DataFrame]
    ) -> Optional[pd.DataFrame]:
        """Load data from a path or DataFrame; return None on missing file."""
        if isinstance(source, pd.DataFrame):
            return source.copy()

        path = Path(source)
        if not path.exists():
            log.warning(
                "SignalAttributionModel: input file not found: %s", path
            )
            return None

        try:
            return pd.read_csv(path)
        except Exception as exc:  # noqa: BLE001
            log.error("SignalAttributionModel: failed to read %s — %s", path, exc)
            return None

    def _print_coefficients(self) -> None:
        """Print per-group contribution coefficients to stdout."""
        print("\n=== Signal Attribution Coefficients ===")
        for group, coef in (self._coefs or {}).items():
            print(f"  {group:<20s}: {coef:+.6f}")
        print(f"  {'intercept':<20s}: {self._intercept:+.6f}")
        print("=" * 40)

    def _save(
        self, result: Dict[str, float], output_path: Union[str, Path]
    ) -> None:
        """Persist result dict to JSON."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as fh:
            json.dump(result, fh, indent=2)
        log.info("SignalAttributionModel: saved → %s", out)
        print(f"\nOutput written to {out}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run attribution from the default CSV path."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    model = SignalAttributionModel()
    result = model.fit(_DEFAULT_INPUT)
    if not result:
        print("No output produced — input file absent or invalid.", file=sys.stderr)
        sys.exit(0)  # graceful exit, not an error


if __name__ == "__main__":
    main()
