"""scripts.platformkit.prop_tiering -- MEASURED calibration -> evidence tiers.

Reads our OWN out-of-sample, leak-free per-stat calibration (brier_skill_score
on 24 World Cup matches, cached by props_eval.write_calibration_cache) and turns
it into honest evidence labels for the prop-edge board. A stat we PROVED skill on
(Saves, Fouls) is promoted; a stat we measured no / negative skill on (Shots On
Target, Cards, Assists, Goals) is demoted and flagged -- shown, never hidden.

HONESTY (binding): "proven" here means OOS-CALIBRATED on real WC results (thin: 24
matches), NOT a $-edge / CLV / profit claim. Calibration says the probabilities
are honest, not that the line is beatable. The cache I/O is split out here so the
board reads it cheaply; both functions are guarded and NEVER raise.

Per-file test: python -m pytest scripts/platformkit/test_props_eval_cache.py -q
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default cache location (relative to repo root / cwd).
CALIBRATION_PATH = os.path.join(
    "data", "domains", "soccer", "prop_calibration.json")

# Thresholds (rationale): BSS > 0 means we beat the base-rate reference OOS, i.e.
# our probabilities carry real information. We require a clear margin (0.05) AND a
# non-thin sample (>=100 settled predictions) before calling a stat "proven", so a
# lucky small-n positive cannot be promoted. 0.0..0.05 is honest-but-slim skill
# ("marginal"); BSS < 0 is measured NO skill ("weak", demoted); not-in-cache is
# "unmeasured" (treated like the prior un-tiered behavior).
PROVEN_BSS = 0.05
PROVEN_N = 100


def current_settle_version() -> Optional[str]:
    """The live soccer settlement-logic version, or None if unavailable.

    Stamped into the calibration cache so a result measured under OLD settlement
    logic can be detected and refused the PROVEN tier. None -> the guard is
    inert (no soccer settle module here), which keeps non-soccer paths unchanged.
    Never raises.
    """
    try:
        from domains.soccer.prop_settle import SETTLE_LOGIC_VERSION
        return SETTLE_LOGIC_VERSION
    except Exception:  # noqa: BLE001 -- never raise
        return None


def write_calibration_cache_json(payload: Dict[str, Any], out_path: str) -> bool:
    """Atomically write the calibration payload JSON. False on failure; no raise."""
    try:
        path = out_path or CALIBRATION_PATH
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="ascii") as fh:
            json.dump(payload, fh, ensure_ascii=True, indent=2, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001 -- never raise
        logger.warning("calibration cache write failed: %s", exc)
        return False


def build_calibration_payload(res: Dict[str, Any]) -> Dict[str, Any]:
    """Slim a backtest_calibration result into the cache payload (per-stat bss).

    Keeps only stats with settled predictions (n>0). Never raises.
    """
    from datetime import datetime, timezone
    per_stat: Dict[str, Any] = {}
    for stat, d in ((res or {}).get("per_stat") or {}).items():
        if isinstance(d, dict) and d.get("n", 0):
            per_stat[stat] = {
                "bss": d.get("brier_skill_score"), "brier": d.get("brier"),
                "ece": d.get("ece"), "n": d.get("n", 0),
            }
    ov = (res or {}).get("overall", {}) or {}
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "settle_logic_version": current_settle_version(),
        "mode": (res or {}).get("mode"),
        "overall": {"bss": ov.get("brier_skill_score"), "brier": ov.get("brier"),
                    "ece": ov.get("ece"), "n": ov.get("n", 0)},
        "per_stat": per_stat,
        "note": (res or {}).get("note", ""),
    }


def load_calibration(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Per-stat calibration map {stat: {bss, n, brier, ece}} from the cache.

    Returns {} when the cache is absent / unreadable / malformed (so the board
    degrades to "unmeasured" and the prior behavior). NEVER raises.
    """
    try:
        p = path or CALIBRATION_PATH
        if not os.path.exists(p):
            return {}
        with open(p, "r", encoding="ascii") as fh:
            payload = json.load(fh)
        per_stat = (payload or {}).get("per_stat")
        if not isinstance(per_stat, dict):
            return {}
        # STALENESS GUARD: a calibration result computed under OLD settlement
        # logic must NEVER drive a PROVEN label. We compare the version stamped
        # into the cache against the live settle-logic version. On mismatch (or a
        # cache that predates stamping -> None), we flag every record _stale so
        # classify() downgrades it (proven -> unmeasured). The bss/n stay visible
        # so the board still shows the (now-untrusted) number, just never PROVEN.
        cur = current_settle_version()
        cached = (payload or {}).get("settle_logic_version")
        stale = cur is not None and cached != cur
        if stale:
            logger.warning(
                "calibration cache stale: stamped=%r live=%r -> refusing "
                "PROVEN tier (treating as unmeasured)", cached, cur)
        out: Dict[str, Dict[str, Any]] = {}
        for stat, d in per_stat.items():
            if isinstance(d, dict):
                rec = dict(d)
                if stale:
                    rec["_stale_version"] = True
                out[stat] = rec
        return out
    except Exception as exc:  # noqa: BLE001 -- never raise
        logger.warning("calibration cache load failed: %s", exc)
        return {}


def _coerce_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None  # NaN guard
    except (TypeError, ValueError):
        return None


def classify(stat: str, calibration: Dict[str, Dict[str, Any]]):
    """(label, bss, n) for *stat* given the loaded calibration map.

    label in {"proven","marginal","weak","unmeasured"}. A stat not in the cache
    (or with an unusable bss) -> ("unmeasured", bss, n). Never raises.
    """
    rec = (calibration or {}).get(stat)
    if not isinstance(rec, dict):
        return "unmeasured", None, None
    # A record flagged stale (computed under OLD settlement logic) is UNMEASURED:
    # its bss cannot be trusted to drive a PROVEN label, so we refuse to tier it.
    if rec.get("_stale_version"):
        return "unmeasured", None, rec.get("n")
    bss = _coerce_float(rec.get("bss"))
    n = rec.get("n")
    try:
        n = int(n) if n is not None else None
    except (TypeError, ValueError):
        n = None
    if bss is None:
        return "unmeasured", None, n
    if bss >= PROVEN_BSS and (n is not None and n >= PROVEN_N):
        return "proven", bss, n
    if bss >= 0.0:
        return "marginal", bss, n
    return "weak", bss, n


def apply_tier(edge: Dict[str, Any],
               calibration: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Attach MEASURED-calibration labels to *edge* in place and return it.

    Adds: oos_bss, oos_n, calibration (proven/marginal/weak/unmeasured). Promotes
    tier to "CALIBRATION_PROVEN" only when calibration=="proven" AND the edge is
    reliable AND ev_flag=="ok"; otherwise tier stays "MODEL_VIEW". "proven" means
    OOS-calibrated on real WC results -- NOT a $-edge / CLV claim. Never raises.
    """
    try:
        label, bss, n = classify(edge.get("stat"), calibration)
        edge["oos_bss"] = round(bss, 4) if isinstance(bss, float) else None
        edge["oos_n"] = n
        edge["calibration"] = label
        reliable = bool(edge.get("reliable", False))
        ev_ok = edge.get("ev_flag") in (None, "ok")
        proven = (label == "proven" and reliable and ev_ok)
        edge["tier"] = "CALIBRATION_PROVEN" if proven else "MODEL_VIEW"
    except Exception as exc:  # noqa: BLE001 -- never raise
        logger.warning("apply_tier failed: %s", exc)
        edge.setdefault("calibration", "unmeasured")
        edge.setdefault("oos_bss", None)
        edge.setdefault("oos_n", None)
    return edge


# Calibration-rank buckets (lower sorts first): proven reliable+ok edges ALWAYS
# outrank marginal, which outrank weak/unmeasured/flagged -- so a weak-stat edge
# (e.g. Shots On Target) can NEVER outrank a proven-stat edge (Saves/Fouls) just
# because its raw EV is larger. Honesty-first ranking.
def calibration_rank_key(edge: Dict[str, Any]):
    """Sort key: (cal_bucket, flagged, priced, -score). Never raises."""
    reliable = bool(edge.get("reliable", False))
    ev_ok = edge.get("ev_flag") in (None, "ok")
    label = edge.get("calibration", "unmeasured")
    if label == "proven" and reliable and ev_ok:
        bucket = 0
    elif label == "marginal" and reliable and ev_ok:
        bucket = 1
    else:
        bucket = 2  # weak / unmeasured / thin / flagged
    flagged = 0 if (reliable and ev_ok) else 1
    is_priced = 0 if edge.get("edge_basis") == "ev_vs_priced" else 1
    score = edge.get("best_ev") if is_priced == 0 else edge.get("model_gap")
    score = score if isinstance(score, (int, float)) else -1.0
    return (bucket, flagged, is_priced, -score)


def label_distribution(edges) -> Dict[str, int]:
    """Count {proven, marginal, weak, unmeasured} among reliable + ev-ok edges."""
    out = {"proven": 0, "marginal": 0, "weak": 0, "unmeasured": 0}
    for e in edges or []:
        if not e.get("reliable", False) or e.get("ev_flag") not in (None, "ok"):
            continue
        lab = e.get("calibration", "unmeasured")
        if lab in out:
            out[lab] += 1
    return out


__all__ = [
    "CALIBRATION_PATH", "PROVEN_BSS", "PROVEN_N",
    "write_calibration_cache_json", "build_calibration_payload",
    "load_calibration", "classify", "apply_tier", "calibration_rank_key",
    "label_distribution",
]
