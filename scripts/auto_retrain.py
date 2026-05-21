"""
auto_retrain.py -- 14-day staleness gate for prop .pkl models.

Scans data/models/ for .pkl files older than 14 days.  If any are stale,
calls train_all_meta() and train_calibration() from prop_model_stack, then
appends ONE line to vault/Improvements/Engineering Knowledge.md.

Integration note: daily_run integration is pending task 16-01.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import List

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

_MODELS_DIR = PROJECT_DIR / "data" / "models"
_VAULT_LOG = PROJECT_DIR / "vault" / "Improvements" / "Engineering Knowledge.md"
_STALE_DAYS = 14
_STALE_SECONDS = _STALE_DAYS * 86400


# ── helpers ──────────────────────────────────────────────────────────────────

def _stale_pkls() -> List[Path]:
    """Return .pkl paths whose mtime is older than 14 days."""
    cutoff = time.time() - _STALE_SECONDS
    return [
        p for p in _MODELS_DIR.glob("*.pkl")
        if p.stat().st_mtime < cutoff
    ]


def _log_outcome(line: str) -> None:
    """Append *line* to Engineering Knowledge.md, deduplicating on prefix.

    If a line starting with 'auto_retrain:' already exists, replace it
    (sharpen rather than duplicate).  Otherwise append.
    """
    marker = "auto_retrain:"
    try:
        if _VAULT_LOG.exists():
            text = _VAULT_LOG.read_text(encoding="utf-8")
            lines = text.splitlines(keepends=True)
            new_lines = [l for l in lines if not l.startswith(marker)]
            new_lines.append(line + "\n")
            _VAULT_LOG.write_text("".join(new_lines), encoding="utf-8")
        else:
            _VAULT_LOG.parent.mkdir(parents=True, exist_ok=True)
            _VAULT_LOG.write_text(line + "\n", encoding="utf-8")
    except Exception as exc:  # never crash the pipeline over a log write
        print(f"[auto_retrain] vault log error: {exc}")


# ── public entry point ────────────────────────────────────────────────────────

def run_retrain_if_stale() -> dict:
    """Check staleness and retrain if needed.

    Returns:
        {
            "stale": list[str],   # basenames of stale .pkl files
            "retrained": bool,
            "meta_results": dict | None,
            "calib_results": dict | None,
        }
    """
    stale = _stale_pkls()
    stale_names = [p.name for p in stale]

    if not stale:
        timestamp = time.strftime("%Y-%m-%d")
        _log_outcome(
            f"auto_retrain: {timestamp} — skipped (all .pkl models < {_STALE_DAYS} days old)"
        )
        print(f"[auto_retrain] All models fresh — skipped.")
        return {"stale": [], "retrained": False, "meta_results": None, "calib_results": None}

    print(f"[auto_retrain] {len(stale)} stale model(s): {stale_names}")

    meta_results: dict | None = None
    calib_results: dict | None = None

    # train_all_meta() — no required args
    try:
        from src.prediction.prop_model_stack import train_all_meta
        meta_results = train_all_meta()
        print(f"[auto_retrain] train_all_meta done: {list(meta_results.keys())}")
    except Exception as exc:
        print(f"[auto_retrain] train_all_meta error: {exc}")

    # train_calibration() — no required args (stat=None trains all)
    try:
        from src.prediction.prop_model_stack import train_calibration
        calib_results = train_calibration()
        print(f"[auto_retrain] train_calibration done: {list(calib_results.keys())}")
    except Exception as exc:
        print(f"[auto_retrain] train_calibration error: {exc}")

    # One concise vault line — dedup via _log_outcome
    timestamp = time.strftime("%Y-%m-%d")
    stale_summary = ", ".join(stale_names[:5])
    if len(stale_names) > 5:
        stale_summary += f" … +{len(stale_names) - 5} more"
    _log_outcome(
        f"auto_retrain: {timestamp} — retrained {len(stale_names)} stale .pkl(s): {stale_summary}"
    )

    return {
        "stale": stale_names,
        "retrained": True,
        "meta_results": meta_results,
        "calib_results": calib_results,
    }


if __name__ == "__main__":
    result = run_retrain_if_stale()
    import json
    safe = {k: v for k, v in result.items() if k != "meta_results" and k != "calib_results"}
    safe["meta_keys"] = list(result["meta_results"].keys()) if result["meta_results"] else None
    safe["calib_keys"] = list(result["calib_results"].keys()) if result["calib_results"] else None
    print(json.dumps(safe, indent=2))
