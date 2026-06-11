"""src/sim/scheme_prior.py — the LLM SCHEME-PRIOR layer (gate CV_LLM_SCHEME, default-OFF).

Architecture law (enforced as code):
  * The LLM is a PRIOR GENERATOR, never a predictor.  It emits BOUNDED, NAMED, JUSTIFIED,
    CONFIDENCE-WEIGHTED multipliers on the sim's EXISTING interpretable knobs.  The possession
    sim still plays every game and computes every number — the LLM moves a knob, not a result.
  * Every adjustment is hard-clamped per-param so a confidently-wrong call can nudge but never
    dominate.  Confidence shrink: eff = 1 + confidence*(mult-1), then clamp to the param band.
  * In BETTING mode any leak_safe=false adjustment is REJECTED (in-season vs-scheme / rel-to-self
    splits manufacture a fake lift — they may inform a scouting narrative, never a bettable number).
  * Default-OFF byte-identical: OFF => apply_scheme_priors is never called => the sim is unchanged.

This module only MUTATES a built TeamModel's existing fields (rate-dict knobs + team attrs).
It adds no new sim key and touches neither _possession nor _finalize, so the CPU + GPU engines
are byte-identical when the gate is OFF.

Py3.10, pure-stdlib at import (no torch/pandas/numpy needed to validate/apply).
honesty_class = "research".
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
TS = os.path.join(_ROOT, "data", "cache", "team_system")
SCHEME_DIR = os.path.join(TS, "scheme_adj")
GATE = "CV_LLM_SCHEME"
_TRUTHY = frozenset({"1", "true", "yes", "on", "y", "t"})

# ---------------------------------------------------------------------------
# Per-param hard clamps.  kind: how the EFFECTIVE (confidence-shrunk) multiplier
# is applied.  player_mult -> rate[pid][param] *= eff ; team_mult -> model.attr *= eff ;
# All bands are deliberately tight: the layer SHAPES, it does not dominate.
# ---------------------------------------------------------------------------
PARAM_SPEC: Dict[str, Dict[str, Any]] = {
    # ---- offensive per-player knobs (keys in TeamModel.rate[pid]) ----
    "use_per_min":  {"kind": "player_mult", "lo": 0.85, "hi": 1.18},
    "shot_share":   {"kind": "player_mult", "lo": 0.85, "hi": 1.18},
    "z_rim":        {"kind": "player_mult", "lo": 0.80, "hi": 1.20},
    "z_paint":      {"kind": "player_mult", "lo": 0.80, "hi": 1.20},
    "z_mid":        {"kind": "player_mult", "lo": 0.80, "hi": 1.20},
    "z_3":          {"kind": "player_mult", "lo": 0.80, "hi": 1.20},
    "fg_rim":       {"kind": "player_mult", "lo": 0.92, "hi": 1.08},
    "fg_paint":     {"kind": "player_mult", "lo": 0.92, "hi": 1.08},
    "fg_mid":       {"kind": "player_mult", "lo": 0.92, "hi": 1.08},
    "fg3_pct":      {"kind": "player_mult", "lo": 0.92, "hi": 1.08},
    "self_create":  {"kind": "player_mult", "lo": 0.80, "hi": 1.20},
    "ast_per_min":  {"kind": "player_mult", "lo": 0.85, "hi": 1.18},
    "tov_share":    {"kind": "player_mult", "lo": 0.82, "hi": 1.20},
    "ft_share":     {"kind": "player_mult", "lo": 0.85, "hi": 1.18},
    "ft_pts_share": {"kind": "player_mult", "lo": 0.85, "hi": 1.18},
    "oreb_per_min": {"kind": "player_mult", "lo": 0.85, "hi": 1.18},
    # ---- team-level knobs (TeamModel attributes) ----
    "tov_force":    {"kind": "team_mult", "attr": "tov_force", "lo": 0.90, "hi": 1.12},
    "ft_force":     {"kind": "team_mult", "attr": "ft_force",  "lo": 0.90, "hi": 1.12},
    "pace":         {"kind": "team_mult", "attr": "pace_mult", "lo": 0.92, "hi": 1.08},
    "int_d":        {"kind": "team_mult", "attr": "rim_d",     "lo": 0.90, "hi": 1.12},
    "perim_d":      {"kind": "team_mult", "attr": "perim_d",   "lo": 0.90, "hi": 1.12},
}

VALID_PARAMS = frozenset(PARAM_SPEC)


@dataclass
class SchemeAdjustment:
    """One bounded knob nudge proposed by the scout/LLM.  NEVER a probability or score."""
    entity: Any              # player_id (int) for player knobs; "TEAM" for team knobs
    param: str               # must be in VALID_PARAMS
    mult: float              # raw proposed multiplier (pre confidence-shrink, pre-clamp)
    confidence: float        # [0,1] — shrink weight
    horizon: str             # e.g. "g4" | "season"
    leak_safe: bool          # True iff derived ONLY from leak-free (prior-window / physical) info
    why: str                 # human justification (required; no unexplained edits)
    source: str = "scout"    # "scout" | "llm"


# ---------------------------------------------------------------------------
def _scheme_on() -> bool:
    """True iff CV_LLM_SCHEME is set to a truthy spelling (matches brain.flags.is_on)."""
    return os.environ.get(GATE, "").strip().lower() in _TRUTHY


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def validate_adjustment(d: Dict[str, Any]) -> SchemeAdjustment:
    """Validate one raw dict into a SchemeAdjustment. Raises ValueError on any contract breach."""
    req = ("entity", "param", "mult", "confidence", "horizon", "leak_safe", "why")
    miss = [k for k in req if k not in d]
    if miss:
        raise ValueError(f"scheme adjustment missing fields: {miss}")
    param = d["param"]
    if param not in VALID_PARAMS:
        raise ValueError(f"unknown param {param!r}; valid: {sorted(VALID_PARAMS)}")
    try:
        mult = float(d["mult"]); conf = float(d["confidence"])
    except (TypeError, ValueError):
        raise ValueError("mult and confidence must be numeric")
    if not (0.0 <= conf <= 1.0):
        raise ValueError(f"confidence {conf} out of [0,1]")
    if not (0.5 <= mult <= 1.6):
        raise ValueError(f"raw mult {mult} implausible (outside [0.5,1.6] sanity bound)")
    if not isinstance(d["leak_safe"], bool):
        raise ValueError("leak_safe must be a bool")
    if not str(d.get("why", "")).strip():
        raise ValueError("every adjustment must carry a non-empty 'why' justification")
    return SchemeAdjustment(
        entity=d["entity"], param=param, mult=mult, confidence=conf,
        horizon=str(d["horizon"]), leak_safe=bool(d["leak_safe"]),
        why=str(d["why"]), source=str(d.get("source", "scout")),
    )


def effective_mult(adj: SchemeAdjustment) -> float:
    """Confidence-shrunk, hard-clamped multiplier actually applied to the knob."""
    spec = PARAM_SPEC[adj.param]
    eff = 1.0 + _clamp(adj.confidence, 0.0, 1.0) * (adj.mult - 1.0)
    return _clamp(eff, spec["lo"], spec["hi"])


def apply_scheme_priors(model, adjustments: List[SchemeAdjustment],
                        betting_mode: bool = False) -> Dict[str, Any]:
    """Mutate a built TeamModel IN PLACE by the bounded scheme adjustments for its team.

    Args:
      model: a TeamModel (has .tri, .rate dict, .tov_force, .ft_force, .pace_mult, .rim_d, .perim_d).
      adjustments: list of SchemeAdjustment (already validated). Only those whose entity is a pid in
        model.rate (player knobs) or "TEAM"/model.tri (team knobs) are applied.
      betting_mode: if True, any leak_safe=False adjustment is REJECTED (scouting-only fields must
        never move a bettable number). Default False (research/scouting sim).

    Returns a report dict {applied, rejected, clamped} for provenance. apply([]) is a no-op.
    """
    report: Dict[str, List[Dict[str, Any]]] = {"applied": [], "rejected": [], "clamped": []}
    tri = getattr(model, "tri", None)
    for adj in adjustments:
        spec = PARAM_SPEC.get(adj.param)
        if spec is None:
            report["rejected"].append({"adj": _adj_tag(adj), "reason": "unknown_param"})
            continue
        if betting_mode and not adj.leak_safe:
            report["rejected"].append({"adj": _adj_tag(adj), "reason": "leak_unsafe_in_betting"})
            continue
        eff = effective_mult(adj)
        raw_eff = 1.0 + _clamp(adj.confidence, 0.0, 1.0) * (adj.mult - 1.0)
        if abs(raw_eff - eff) > 1e-12:
            report["clamped"].append({"adj": _adj_tag(adj), "raw": round(raw_eff, 5), "clamped_to": round(eff, 5)})

        if spec["kind"] == "player_mult":
            try:
                pid = int(adj.entity)
            except (TypeError, ValueError):
                report["rejected"].append({"adj": _adj_tag(adj), "reason": "player_knob_needs_int_pid"})
                continue
            r = model.rate.get(pid)
            if r is None:
                report["rejected"].append({"adj": _adj_tag(adj), "reason": "pid_not_in_rotation"})
                continue
            cur = r.get(adj.param)
            if cur is None or not isinstance(cur, (int, float)):
                report["rejected"].append({"adj": _adj_tag(adj), "reason": "knob_absent_on_player"})
                continue
            r[adj.param] = float(cur) * eff
            report["applied"].append({"adj": _adj_tag(adj), "eff": round(eff, 5)})

        elif spec["kind"] == "team_mult":
            if adj.entity not in ("TEAM", tri, None):
                report["rejected"].append({"adj": _adj_tag(adj), "reason": "team_knob_entity_mismatch"})
                continue
            attr = spec["attr"]
            cur = getattr(model, attr, None)
            if cur is None or not isinstance(cur, (int, float)):
                report["rejected"].append({"adj": _adj_tag(adj), "reason": f"attr_{attr}_absent"})
                continue
            setattr(model, attr, float(cur) * eff)
            report["applied"].append({"adj": _adj_tag(adj), "eff": round(eff, 5)})

    return report


def _adj_tag(adj: SchemeAdjustment) -> str:
    return f"{adj.entity}:{adj.param}"


# ---------------------------------------------------------------------------
def _artifact_path(tri: str, asof: Optional[str]) -> str:
    tag = asof or "latest"
    return os.path.join(SCHEME_DIR, f"{tri.upper()}_{tag}.json")


def load_scheme_adjustments(tri: str, asof: Optional[str] = None) -> List[SchemeAdjustment]:
    """Load + validate the cached scheme-adjustment artifact for a team. [] if absent/empty.

    Mirrors the CV_AGENT_DEF_SUPP loader: a missing file yields [] (so ON-without-artifact is a
    no-op and never errors). Invalid entries are skipped with a warning, not fatal.
    """
    path = _artifact_path(tri, asof)
    if not os.path.exists(path):
        return []
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception as exc:
        log.warning("scheme_prior: failed to read %s: %s", path, exc)
        return []
    items = raw.get("adjustments", raw) if isinstance(raw, dict) else raw
    out: List[SchemeAdjustment] = []
    for d in (items or []):
        try:
            out.append(validate_adjustment(d))
        except ValueError as exc:
            log.warning("scheme_prior: skipping invalid adjustment %s: %s", d, exc)
    return out


def write_scheme_adjustments(tri: str, adjustments: List[Dict[str, Any]],
                             asof: Optional[str] = None, meta: Optional[dict] = None) -> str:
    """Validate + persist a team's scheme-adjustment artifact (used by the scout). Returns the path."""
    validated = [validate_adjustment(d) for d in adjustments]  # raises on any malformed entry
    os.makedirs(SCHEME_DIR, exist_ok=True)
    path = _artifact_path(tri, asof)
    payload = {
        "team": tri.upper(), "asof": asof, "honesty_class": "research",
        "n": len(validated), "meta": meta or {},
        "adjustments": [vars(a) for a in validated],
    }
    json.dump(payload, open(path, "w", encoding="utf-8"), indent=2, default=str)
    return path
