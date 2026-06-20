"""scripts.platformkit.ingame.ingame_xgloc_gate_soccer -- GATE-RUN for the new
soccer in-game LOCATION-xG-proxy detail layer (domains/soccer/ingest_shotxg_states.py).

THE QUESTION: the PROVEN soccer in-game champion is the goal-diff base+pregame-prior
(REPLICATED). Does adding the location-weighted xG-proxy term `xgloc_diff` (as-of-minute,
leak-free) beat that champion on held-out Brier, REPLICATED in BOTH cross-corpus
directions, DM clustered by game_id, without tripping the degenerate-base guard?

This is the IDENTICAL machinery as ingame_shot_gate_soccer (champion = goal base+prior;
candidate = goal base + c*z_feat + prior; cross-corpus A<->B; DM clustered by game_id;
degenerate-base guard; graceful-degrade so a noise term fits c->0 -> REJECT). We only
swap the candidate feature to the new layer's `xgloc_diff`, so the new layer is judged by
EXACTLY the gate that judged the type-only proxy -- no weakened bar.

GATE used: scripts.platformkit.ingame.ingame_shot_gate_soccer.gate
  (which inherits ingame_gate_generic_models: fit_base, base/prior predict, the
   degenerate-base guard) + scripts.platformkit.eval_gate.dm_test.diebold_mariano
  (DM clustered by game_id).

CROSS-CORPUS: two INDEPENDENT corpora on disk -- combo_eng_ger (EPL+Bundesliga) and
combo_esp_ita (La Liga+Serie A). If the new layer parquets are not materialized for
both, we report INSUFFICIENT_DATA honestly (we never 0-fill missing coverage into a win).

PLANTED-NULL CONTROL: a pure-noise column (seeded per (game_id,asof_idx)) is run through
the IDENTICAL gate. It MUST NOT REPLICATE. If the null DOES replicate, the gate cannot
fail a signal and the whole run is UNTRUSTWORTHY -- we say so and refuse to ship.

NO $ anywhere; verdict is CALIBRATION (held-out Brier), never a market edge.
PROPOSAL-ONLY: writes only data/frontend/ingame JSON, never data/registry/, never a flag.
INVARIANTS: never edit src/kernel; <=300 LOC; ASCII; numpy/pandas/stdlib + reuse.
CLI: python -m scripts.platformkit.ingame.ingame_xgloc_gate_soccer
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.ingame.ingame_shot_gate_soccer import ShotVerdict, gate

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_OUT_DIR = os.path.join(_REPO, "data", "frontend", "ingame")
_COMBOS = ("combo_eng_ger", "combo_esp_ita")
_FEAT = "xgloc_diff"
_NULL_FEAT = "planted_null"


def _base_path(label: str) -> str:
    return os.path.join(_STATE_DIR, f"soccer_states__{label}.parquet")


def _layer_path(label: str) -> str:
    return os.path.join(_STATE_DIR, f"soccer_shotxgstates__{label}.parquet")


def _planted_null_col(game_id: str, asof_idx: int) -> float:
    """Deterministic pure-noise value keyed to (game_id, asof_idx).

    A fixed hash -> uniform float in [-2, 2]. It carries NO outcome information by
    construction; the gate MUST fail it. Deterministic so the control is reproducible.
    """
    h = hash((str(game_id), int(asof_idx), "planted-null-salt-2026"))
    return ((h % 100003) / 100003.0) * 4.0 - 2.0


def load_joined(label: str) -> List[dict]:
    """Join FROZEN base combo states with the new xgloc layer on (game_id, asof_idx).

    inner-join so candidate (xgloc) and champion (goal+prior) see the SAME rows -- a fair
    head-to-head. Adds the planted-null column on the SAME rows. Leak-free: no future /
    final-aggregate column is read; missing layer rows are DROPPED, never 0-filled.
    """
    base = pd.read_parquet(_base_path(label))
    layer = pd.read_parquet(_layer_path(label))
    base["game_id"] = base["game_id"].astype(str)
    layer["game_id"] = layer["game_id"].astype(str)
    df = base.merge(layer[["game_id", "asof_idx", _FEAT]],
                    on=["game_id", "asof_idx"], how="inner")
    out: List[dict] = []
    for r in df.itertuples(index=False):
        out.append({
            "game_id": str(r.game_id), "state_diff": float(r.state_diff),
            "frac_elapsed": float(r.frac_elapsed), "p0": float(r.p0),
            "outcome": int(r.outcome), _FEAT: float(getattr(r, _FEAT)),
            _NULL_FEAT: _planted_null_col(r.game_id, int(r.asof_idx)),
        })
    return out


def _avail() -> List[str]:
    return [lb for lb in _COMBOS
            if os.path.exists(_base_path(lb)) and os.path.exists(_layer_path(lb))]


def run() -> Dict:
    """Materialized-layer gate-run: real-feature gate + planted-null control, both dirs."""
    os.makedirs(_OUT_DIR, exist_ok=True)
    av = _avail()
    if len(av) < 2:
        verdict = {
            "verdict": "INSUFFICIENT_DATA", "gate": "ingame_shot_gate_soccer.gate",
            "reason": f"need 2 materialized xgloc corpora; found {len(av)}: {av}",
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "proposal_only": True,
        }
        _write(verdict)
        return verdict

    la, lb = av[0], av[1]
    states_a, states_b = load_joined(la), load_joined(lb)

    real = gate(states_a, states_b, _FEAT, la, lb)
    nullv = gate(states_a, states_b, _NULL_FEAT, la, lb)

    null_rejects = nullv.verdict != "REPLICATED"
    real_repl = real.verdict == "REPLICATED"
    if not null_rejects:
        final, why = "NOT_TESTABLE", (
            "PLANTED-NULL did NOT reject (verdict=%s): the gate cannot FAIL a signal here, "
            "so the real-layer result is UNTRUSTWORTHY." % nullv.verdict)
    elif real_repl:
        final, why = "SHIP", (
            "xgloc_diff REPLICATED both directions vs the goal-base+prior champion; "
            "planted-null correctly REJECTED -> gate can fail a signal.")
    else:
        final, why = "REJECT", (
            "xgloc_diff did NOT replicate both directions (verdict=%s) vs the "
            "goal-base+prior champion; planted-null correctly REJECTED." % real.verdict)

    verdict = {
        "verdict": final, "reason": why, "gate": "ingame_shot_gate_soccer.gate",
        "feature": _FEAT, "corpora": [la, lb], "n_corpora": 2,
        "real_layer": real.to_dict(),
        "planted_null": {"verdict": nullv.verdict, "rejects": bool(null_rejects),
                         "a_to_b": nullv.a_to_b, "b_to_a": nullv.b_to_a},
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "proposal_only": True,
    }
    _write(verdict)
    _report(verdict)
    return verdict


def _write(v: Dict) -> str:
    out = os.path.join(_OUT_DIR, "xgloc_gate_soccer.json")
    with open(out, "w", encoding="ascii") as f:
        json.dump(v, f, indent=2, sort_keys=True)
    print(f"wrote {out}")
    return out


def _dir_line(name: str, d: Dict) -> str:
    if not d:
        return f"  {name}: (none)"
    return (f"  {name}: CHAMP {d.get('brier_champ')} -> CAND {d.get('brier_cand')} "
            f"(delta {d.get('brier_delta')})  DM p {d.get('dm_p')}  "
            f"cand_beats_champ={d.get('cand_beats_champ')} degen={d.get('base_degenerate')}")


def _report(v: Dict) -> None:
    print("=" * 72)
    print("IN-GAME xG-LOCATION-PROXY GATE-RUN [soccer / xgloc_diff]")
    print("=" * 72)
    print(f"gate     : {v['gate']}   corpora: {v.get('corpora')}")
    rl = v.get("real_layer", {})
    print(f"REAL  verdict={rl.get('verdict')}   coverage={rl.get('coverage')}")
    print(_dir_line("A->B", rl.get("a_to_b", {})))
    print(_dir_line("B->A", rl.get("b_to_a", {})))
    pn = v.get("planted_null", {})
    print(f"NULL  verdict={pn.get('verdict')}  rejects={pn.get('rejects')}")
    print(_dir_line("A->B", pn.get("a_to_b", {})))
    print(_dir_line("B->A", pn.get("b_to_a", {})))
    print("-" * 72)
    print(f"FINAL VERDICT: {v['verdict']}  -- {v['reason']}")
    print("=" * 72)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
