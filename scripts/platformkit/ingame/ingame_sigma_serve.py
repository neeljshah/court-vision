"""scripts.platformkit.ingame.ingame_sigma_serve -- serve calibrated in-game sigma.

PURPOSE
-------
Reads the pre-built ingame_sigma_table.json (produced by
src/prediction/ingame_sigma.py; read-only here, never rebuilt) and exposes
a thin, honest sigma look-up alongside the p_win serve path.

The sigma table has shape:
    {
      "sigma_table": {
        "<stat>": {
          "<bucket_label>": {
            "calibrated_sigma": <float>,   # the primary field served
            "elapsed_min": <float>,
            "n": <int>,
            "coverage_at_1sig": <float>,
            ...
          }, ...
        }, ...
      },
      "bucket_order": [...],
      "bucket_elapsed_min": { "<bucket_label>": <float>, ... },
      ...
    }

PUBLIC API
----------
  load_sigma_table(path=None) -> dict | None
      Load the JSON; None if file is absent or unreadable.

  get_sigma(stat, bucket, *, table=None, path=None) -> float | None
      Return the calibrated_sigma for (stat, bucket).
      Returns None -- never a fabricated/interpolated value -- when:
        - the table file is missing
        - stat is not in the table
        - bucket is not in the table for that stat
        - the entry lacks a "calibrated_sigma" key

  serve_sigma(stat, bucket, *, table=None, path=None) -> dict
      Return a dict ready to attach alongside serve_ingame() output:
        {
          "stat":              str,
          "bucket":            str,
          "calibrated_sigma":  float | None,
          "elapsed_min":       float | None,
          "n":                 int   | None,
          "coverage_at_1sig":  float | None,
          "sigma_found":       bool,
          "honesty":           str,
        }
      sigma_found=False when the (stat,bucket) pair is absent from the table.
      Never raises; always degrades gracefully.

HONESTY INVARIANTS
------------------
- Read-only: never writes to data/models/.
- sigma=None when the table is missing or the key is absent; never interpolated.
- No $ fields. calibrated_sigma is a CALIBRATION metric (residual dispersion),
  not a market edge or a profit forecast.
- ASCII-only, <=300 LOC.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

_DEFAULT_TABLE_PATH = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
    "data", "models", "ingame_sigma_table.json",
)

_HONESTY_NOTICE = (
    "calibrated_sigma = empirical p68 residual dispersion; "
    "CALIBRATION metric only, not a market edge or profit forecast"
)


# ---------------------------------------------------------------------------
# Table loader
# ---------------------------------------------------------------------------

def load_sigma_table(path: Optional[str] = None) -> Optional[Dict]:
    """Load and return the sigma table dict.

    Returns None (not an exception) when the file is absent, unreadable,
    or not a valid JSON object.  The table is expected to have a
    "sigma_table" key at the top level.
    """
    resolved = path if path is not None else _DEFAULT_TABLE_PATH
    try:
        with open(resolved, encoding="ascii", errors="replace") as fh:
            obj = json.load(fh)
        if not isinstance(obj, dict):
            return None
        return obj
    except (OSError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Core look-up
# ---------------------------------------------------------------------------

def get_sigma(
    stat: str,
    bucket: str,
    *,
    table: Optional[Dict] = None,
    path: Optional[str] = None,
) -> Optional[float]:
    """Return the calibrated_sigma for (stat, bucket), or None.

    Never raises.  Never interpolates.  Returns None for any absent key,
    missing table file, or malformed entry.

    Parameters
    ----------
    stat   : e.g. "pts", "reb", "ast"
    bucket : e.g. "24min(endQ2/half)", "36min(endQ3)"
    table  : pre-loaded table dict (avoids re-loading on hot paths)
    path   : override path to ingame_sigma_table.json
    """
    if table is None:
        table = load_sigma_table(path=path)
    if table is None:
        return None
    sigma_section = table.get("sigma_table")
    if not isinstance(sigma_section, dict):
        return None
    stat_section = sigma_section.get(stat)
    if not isinstance(stat_section, dict):
        return None
    entry = stat_section.get(bucket)
    if not isinstance(entry, dict):
        return None
    val = entry.get("calibrated_sigma")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Rich serve helper
# ---------------------------------------------------------------------------

def serve_sigma(
    stat: str,
    bucket: str,
    *,
    table: Optional[Dict] = None,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a serve-ready sigma dict for (stat, bucket).

    Always returns a dict; never raises.  sigma_found=False when the
    (stat, bucket) pair is absent from the table.

    Schema
    ------
    stat              : the requested stat string
    bucket            : the requested bucket string
    calibrated_sigma  : float if found, else None
    elapsed_min       : float from the entry, else None
    n                 : int sample count from the entry, else None
    coverage_at_1sig  : float from the entry, else None
    sigma_found       : bool -- True iff calibrated_sigma is not None
    honesty           : human-readable disclaimer (ASCII)
    """
    if table is None:
        table = load_sigma_table(path=path)

    cal_sigma: Optional[float] = None
    elapsed_min: Optional[float] = None
    n_count: Optional[int] = None
    coverage: Optional[float] = None

    if table is not None:
        sigma_section = table.get("sigma_table")
        if isinstance(sigma_section, dict):
            stat_section = sigma_section.get(stat)
            if isinstance(stat_section, dict):
                entry = stat_section.get(bucket)
                if isinstance(entry, dict):
                    v = entry.get("calibrated_sigma")
                    if v is not None:
                        try:
                            cal_sigma = float(v)
                        except (TypeError, ValueError):
                            cal_sigma = None
                    v2 = entry.get("elapsed_min")
                    if v2 is not None:
                        try:
                            elapsed_min = float(v2)
                        except (TypeError, ValueError):
                            pass
                    v3 = entry.get("n")
                    if v3 is not None:
                        try:
                            n_count = int(v3)
                        except (TypeError, ValueError):
                            pass
                    v4 = entry.get("coverage_at_1sig")
                    if v4 is not None:
                        try:
                            coverage = float(v4)
                        except (TypeError, ValueError):
                            pass

    return {
        "stat": stat,
        "bucket": bucket,
        "calibrated_sigma": cal_sigma,
        "elapsed_min": elapsed_min,
        "n": n_count,
        "coverage_at_1sig": coverage,
        "sigma_found": cal_sigma is not None,
        "honesty": _HONESTY_NOTICE,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import sys
    args = sys.argv[1:]
    if len(args) == 2:
        stat, bucket = args[0], args[1]
        result = serve_sigma(stat, bucket)
        print(json.dumps(result, indent=2))
    elif len(args) == 0:
        # Print available stats and buckets from table
        tbl = load_sigma_table()
        if tbl is None:
            print("sigma table not found at", _DEFAULT_TABLE_PATH)
            sys.exit(1)
        sigma_sec = tbl.get("sigma_table", {})
        print("Available stats:", list(sigma_sec.keys()))
        print("Bucket order:", tbl.get("bucket_order", []))
    else:
        print(
            "usage: ingame_sigma_serve <stat> <bucket>",
            "  e.g. pts '24min(endQ2/half)'",
            sep="\n",
        )


if __name__ == "__main__":
    _main()
