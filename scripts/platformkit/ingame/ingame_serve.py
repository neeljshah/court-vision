"""scripts.platformkit.ingame.ingame_serve -- PERSIST + SERVE the proven in-game
calibration model per sport.

The generic gate (ingame_gate_generic.py) FITS the BASE (state_diff,frac_elapsed -> P)
and the +PRIOR weight-surface per call but persists NO servable artifact. This module
bridges gate -> live serving:

  fit_servable(sport)  : pool ALL of a sport's corpora, fit BASE (a,b) + the +PRIOR
                         weight surface on the pool (for SERVING we use all data), read
                         the sport's REPLICATION verdict from the gate, and persist a
                         versioned artifact to data/cache/ingame/models/<sport>_ingame.json
                         (atomic tmp + os.replace).
  serve_ingame(sport, state_diff, frac_elapsed, p0)
                       : load the artifact, return {p_win, model, provenance}.

HONESTY (the load-bearing rule): the served model NEVER applies an unproven prior blend
as if proven.
  * +PRIOR is served as 'base+prior(proven)'        iff gate verdict == REPLICATED.
  * +PRIOR is served as 'base+prior(experimental)'  iff verdict == PARTIAL (marked).
  * otherwise (REJECT / INVALID_BASE / INSUFFICIENT_DATA) we serve BASE only.
Per-sport (this repo, 2026-06-18 gate runs): NBA=REPLICATED, TENNIS=REPLICATED (proven);
SOCCER=PARTIAL (experimental); MLB=REJECT (base only).

Degrades to BASE when the surface is missing; degrades to p0 when state is missing.
Never fabricates. No $ anywhere -- verdict is CALIBRATION (Brier), not a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_serve fit <sport>
     python -m scripts.platformkit.ingame.ingame_serve serve <sport> <diff> <frac> <p0>
"""
from __future__ import annotations

import glob
import json
import os
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.eval_gate.ingame_blend import blend, margin_bucket
from scripts.platformkit.ingame.ingame_gate_generic_models import (
    base_predict,
    fit_base,
    fit_prior_surface,
    load_states,
)
from scripts.platformkit.ingame import ingame_serve_persist as _P

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_GATE_DIR = os.path.join(_REPO, "data", "frontend", "ingame")
_MODEL_DIR = os.path.join(_STATE_DIR, "models")
_VERSION = 1

# Persist + provenance helpers live in ingame_serve_persist (sibling-split for <=300 LOC).
# These thin aliases keep the internal call sites + tests' monkeypatch of srv._MODEL_DIR
# working; _MODEL_DIR is resolved HERE on every call so a patched dir takes effect.
_PROVEN = _P.PROVEN
_EXPERIMENTAL = _P.EXPERIMENTAL
_prior_status = _P.prior_status
_time_bucket = _P.time_bucket
_base_p = _P.base_p
_result = _P.result


def _persist(sport: str, art: Dict) -> str:
    return _P.persist(_MODEL_DIR, sport, art)


def load_artifact(sport: str) -> Optional[Dict]:
    return _P.load_artifact(_MODEL_DIR, sport)

# Minimum game count embedded in a served artifact to qualify its verdict as 'proven'.
# An artifact fit on fewer games is served as BASE only (honest degrade), even if its
# embedded verdict says REPLICATED (e.g. a thin/test artifact accidentally persisted).
_MIN_GAMES_PROVEN = 50


# --------------------------------------------------------------- corpus discovery
def _corpora_for(sport: str) -> List[str]:
    """All frozen-schema state parquets for a sport (generic naming)."""
    pats = [f"{sport}_states__*.parquet"]
    if sport == "nba":
        pats.append("pbp_states_*.parquet")  # NBA's native fine-grained corpus
    out: List[str] = []
    for p in pats:
        out += glob.glob(os.path.join(_STATE_DIR, p))
    return sorted(set(out))


def _states_for_path(path: str) -> List[dict]:
    """Generic-schema state dicts for ONE corpus parquet (NBA pbp via the adapter)."""
    if os.path.basename(path).startswith("pbp_states_"):
        return list(_nba_states(path))
    return list(load_states(path))


def _load_pool(sport: str) -> List[dict]:
    """Pool ALL corpora into one list of generic-schema state dicts.

    NBA's native pbp_states parquet is not in the frozen schema (it carries
    seconds_remaining/home_margin + no p0); reuse the NBA gate's own adapter
    (states_from_pbp) to map it to {game_id,state_diff,frac_elapsed,p0,outcome}.
    """
    pool: List[dict] = []
    for path in _corpora_for(sport):
        pool.extend(_states_for_path(path))
    return pool


def pool_split_ab(sport: str) -> Tuple[List[dict], List[dict]]:
    """Split a sport's FULL server pool into two held-out-by-corpus groups (A, B).

    The split partitions the CANONICAL corpus FILES (the exact set _load_pool pools,
    incl. any rolling {sport}_states__refresh.parquet the living loop appends to) into
    two balanced groups by sorted-index parity -- a leak-free cross-corpus split that
    matches the verified per-sport verdicts (MLB 2023<->2024, tennis atp<->wta, soccer
    league groups). A+B is EXACTLY the served pool, so a gate run on (A,B) judges the
    SAME data ingame_serve.fit_servable serves -- gate==serve parity by construction.
    """
    a: List[dict] = []
    b: List[dict] = []
    for i, path in enumerate(_corpora_for(sport)):
        (a if i % 2 == 0 else b).extend(_states_for_path(path))
    return a, b


def _nba_states(pbp_path: str) -> List[dict]:
    """Map an NBA pbp_states parquet to generic schema via the NBA gate adapter."""
    from scripts.platformkit.ingame.ingame_finegrain_nba import states_from_pbp
    lines = {
        "pbp_states_2025_26.parquet": os.path.join(
            _REPO, "data", "domains", "basketball_nba", "linescores.parquet"),
        "pbp_states_2024_25.parquet": os.path.join(
            _REPO, "data", "domains", "basketball_nba", "linescores_2024_25.parquet"),
    }.get(os.path.basename(pbp_path))
    if not lines or not os.path.exists(lines):
        return []
    out = []
    for s in states_from_pbp(pbp_path, lines):
        # NBA adapter emits score_diff; the generic schema/key is state_diff.
        out.append({
            "game_id": s["game_id"], "state_diff": float(s["score_diff"]),
            "frac_elapsed": float(s["frac_elapsed"]), "p0": float(s["p0"]),
            "outcome": int(s["outcome"]),
        })
    return out


# --------------------------------------------------------------- gate verdict read
def _gate_verdict(sport: str) -> str:
    """Read the persisted replication verdict for a sport from the gate output.

    NBA's verdict lives in finegrain_nba.json; the other sports in gate_<sport>.json.
    Missing file -> UNKNOWN (serve BASE only, honest).

    C3 honesty: the LIVING loop (ingame_gate_refresh.gate_refresh_nba) re-writes
    finegrain_nba.json by gating the EXACT pool fit_servable re-fits, with the SAME
    grid-search BASE (fit_base) served here -- so once the loop has run, the served
    'proven' tag is earned on the served model, not borrowed from a fixed-slope gate.
    """
    cands = [os.path.join(_GATE_DIR, f"gate_{sport}.json")]
    if sport == "nba":
        cands = [os.path.join(_GATE_DIR, "finegrain_nba.json")] + cands
    for path in cands:
        if os.path.exists(path):
            try:
                with open(path, encoding="ascii") as f:
                    return str(json.load(f).get("verdict", "UNKNOWN"))
            except (OSError, ValueError):
                continue
    return "UNKNOWN"


# --------------------------------------------------------------- fit + persist
def fit_servable(sport: str, *, min_cell: int = 20) -> Dict:
    """Fit BASE + +PRIOR surface on ALL of a sport's pooled states; persist artifact.

    Returns the artifact dict. The +prior surface is fit regardless of verdict (so an
    experimental sport can serve a MARKED experimental prior), but serve_ingame only
    APPLIES it when the verdict proves/permits it -- never as 'proven' when it is not.
    """
    pool = _load_pool(sport)
    verdict = _gate_verdict(sport)
    prior_status = _prior_status(verdict)
    art: Dict = {
        "version": _VERSION, "sport": sport, "verdict": verdict,
        "prior_status": prior_status,
        "base_model": "sigmoid((a+b*frac_elapsed)*state_diff)",
        "prior_model": "blend(p0, BASE, w(time,margin))",
        "vs_close": "UNPROVEN -- CALIBRATION (held-out Brier) only, not a market edge",
        "n_states": len(pool),
        "n_games": len({s["game_id"] for s in pool}),
    }
    if not pool:
        art["base_slope"] = None
        art["weight_surface"] = None
        art["fit_ok"] = False
        _persist(sport, art)
        return art
    ab = fit_base(pool)
    base = base_predict(pool, ab)
    surf = fit_prior_surface(pool, base, min_cell=min_cell)
    edges = surf.grid.get("__edges__", (0.0,))
    # serialize the (time,margin)->w cells with string keys (JSON has no tuple keys)
    cells = {f"{k[0]},{k[1]}": float(v) for k, v in surf.grid.items()
             if isinstance(k, tuple) and len(k) == 2 and isinstance(k[0], int)}
    art["base_slope"] = [round(float(ab[0]), 8), round(float(ab[1]), 8)]
    art["weight_surface"] = {
        "edges": [round(float(e), 6) for e in edges],
        "default": float(surf.default),
        "cells": cells,
    }
    art["fit_ok"] = True
    _persist(sport, art)
    return art


# --------------------------------------------------------------- serve
def serve_ingame(sport: str, *, state_diff: Optional[float], frac_elapsed: Optional[float],
                 p0: Optional[float]) -> Dict:
    """Serve the live in-game calibrated win-prob for a sport.

    Degrades honestly:
      * artifact / base missing  -> p_win = p0 (or 0.5 if p0 also missing), model='p0'.
      * state missing            -> p_win = p0, model='p0'.
      * base present, prior not proven/permitted, or surface missing -> model='base'.
      * prior PROVEN             -> model='base+prior(proven)'.
      * prior PARTIAL            -> model='base+prior(experimental)'.
    NEVER applies an unproven prior as proven. Returns a $-free dict.
    """
    art = load_artifact(sport)
    prov: List[str] = []
    p0v = float(p0) if p0 is not None else None
    if art is None or not art.get("fit_ok") or art.get("base_slope") is None:
        prov.append("no servable artifact -> degrade to pregame prior p0")
        return _result(p0v if p0v is not None else 0.5, "p0", sport, "UNKNOWN", prov)
    verdict = str(art.get("verdict", "UNKNOWN"))
    # SUFFICIENCY GUARD: an artifact fit on fewer than _MIN_GAMES_PROVEN games cannot
    # qualify as 'proven' regardless of its embedded verdict (a thin/test artifact
    # persisted by mistake would otherwise be served as proven). Degrade to base only.
    n_games = int(art.get("n_games", 0))
    if n_games < _MIN_GAMES_PROVEN and verdict in _PROVEN:
        prov.append(
            f"SUFFICIENCY GUARD: artifact has only {n_games} games "
            f"(< {_MIN_GAMES_PROVEN}); demoted from proven to base-only (honest)")
        verdict = "INSUFFICIENT_DATA"
    if state_diff is None or frac_elapsed is None:
        prov.append("no live state -> degrade to pregame prior p0")
        return _result(p0v if p0v is not None else 0.5, "p0", sport, verdict, prov)
    ab = art["base_slope"]
    base_p = _base_p(state_diff, frac_elapsed, ab)
    prov.append(f"base=sigmoid((a+b*frac)*diff) a,b={ab}")
    status = art.get("prior_status", _prior_status(verdict))
    # Re-derive status if the sufficiency guard demoted the verdict.
    if n_games < _MIN_GAMES_PROVEN and art.get("prior_status") == "proven":
        status = "none"
    surf = art.get("weight_surface")
    if status == "none" or surf is None or p0v is None:
        if status == "none":
            prov.append(f"+prior NOT served (verdict={verdict}); BASE only")
        elif p0v is None:
            prov.append("no p0 -> cannot blend; BASE only")
        else:
            prov.append("no weight surface -> BASE only")
        return _result(base_p, "base", sport, verdict, prov)
    # apply blend with the persisted (time,margin) weight cell
    edges = tuple(surf.get("edges", (0.0,)))
    key = f"{_time_bucket(frac_elapsed)},{margin_bucket(float(state_diff), edges)}"
    w = float(surf.get("cells", {}).get(key, surf.get("default", 0.0)))
    p = blend(p0v, base_p, w)
    label = "base+prior(proven)" if status == "proven" else "base+prior(experimental)"
    prov.append(f"+prior({status}) blend w={w:.3f} cell=({key}) p0={p0v:.4f}")
    return _result(p, label, sport, verdict, prov)


# --------------------------------------------------------------- CLI
def main() -> None:
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "fit":
        art = fit_servable(sys.argv[2])
        print(json.dumps({k: art[k] for k in (
            "sport", "verdict", "prior_status", "n_states", "n_games",
            "base_slope", "fit_ok")}, indent=2))
    elif len(sys.argv) >= 6 and sys.argv[1] == "serve":
        sp, d, fe, p0 = sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
        print(json.dumps(serve_ingame(sp, state_diff=d, frac_elapsed=fe, p0=p0), indent=2))
    else:
        print("usage: ingame_serve fit <sport> | serve <sport> <diff> <frac> <p0>")


if __name__ == "__main__":
    main()
