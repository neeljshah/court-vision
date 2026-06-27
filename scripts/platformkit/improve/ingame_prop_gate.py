"""scripts.platformkit.improve.ingame_prop_gate -- consult the in-game ratchet verdicts.

Pure read-side of the in-game prop calibration ratchet (ingame_prop_ratchet). Given a
candidate in-game prop row (carrying sport + frac_elapsed), decide whether its
(sport, frac_bucket) calibration is trustworthy enough to PLACE. The ONLY suppression is a
REJECT verdict (calibration untrustworthy / planted-null leaked); every other state -- SHIP,
HOLD, INSUFFICIENT_DATA, or no measurement at all -- ALLOWS the bet. So the gate can only
ever HOLD or REMOVE proven-bad bets, never arm new ones (the ratchet invariant), and
default-allow keeps live placement byte-identical until a bucket is proven un-calibratable.

ARMING IS A FLAG, DEFAULT OFF: gate_if_enabled() returns a usable gate ONLY when the env
var CV_INGAME_CALIB_GATE is truthy; otherwise None (the placer applies no gate). This module
flips nothing on its own and the flag lives in exactly ONE place.

HONESTY: calibration != edge. PROPOSE/RECORD only; this module places nothing. ASCII; <=300 LOC.
Per-file test: tests/platformkit/improve/test_ingame_prop_gate.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.improve.ingame_prop_ratchet import bucket_for, DEFAULT_META_PATH

_DEFAULT_SUPPRESS = frozenset({"REJECT"})
_TRUTHY = frozenset({"1", "true", "on", "yes"})


def load_meta(meta_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the ratchet's gate read-surface; {} on any miss (-> default-allow)."""
    p = Path(meta_path) if meta_path else DEFAULT_META_PATH
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _suppress_set(meta: Dict[str, Any]) -> frozenset:
    sv = meta.get("suppress_verdicts")
    if isinstance(sv, (list, tuple)) and sv:
        return frozenset(str(v) for v in sv)
    return _DEFAULT_SUPPRESS


def _verdict_for(sport: str, bucket: str, meta: Dict[str, Any]) -> Optional[str]:
    for g in meta.get("groups", []) or []:
        if str(g.get("sport")) == sport and str(g.get("bucket")) == bucket:
            return g.get("verdict")
    return None


def allow(row: Dict[str, Any], meta: Optional[Dict[str, Any]] = None,
          meta_path: Optional[Path] = None) -> bool:
    """True = place this in-game prop; False = suppress (its bucket is REJECTed).

    Default-allow on every non-suppress state (missing meta, unknown bucket,
    INSUFFICIENT_DATA, HOLD, SHIP) so enabling the gate can only ever REMOVE proven-bad
    buckets -- never change which good bets place."""
    if not isinstance(row, dict):
        return True
    m = meta if meta is not None else load_meta(meta_path)
    if not m:
        return True
    bucket = bucket_for(row.get("frac_elapsed"))
    if bucket is None:
        return True
    sport = str(row.get("sport") or "").lower()
    verdict = _verdict_for(sport, bucket, m)
    return str(verdict) not in _suppress_set(m)


def make_gate(meta_path: Optional[Path] = None) -> Callable[[Dict[str, Any]], bool]:
    """Bind a row-level gate callable with the meta loaded ONCE (per tick)."""
    meta = load_meta(meta_path)
    return lambda row: allow(row, meta=meta)


def gate_if_enabled(meta_path: Optional[Path] = None
                    ) -> Optional[Callable[[Dict[str, Any]], bool]]:
    """A row-gate ONLY when CV_INGAME_CALIB_GATE is truthy; else None (no-op).

    Single home for the arming flag; default OFF -> live placement is byte-identical."""
    if os.environ.get("CV_INGAME_CALIB_GATE", "").strip().lower() not in _TRUTHY:
        return None
    return make_gate(meta_path)


__all__ = ["load_meta", "allow", "make_gate", "gate_if_enabled"]
