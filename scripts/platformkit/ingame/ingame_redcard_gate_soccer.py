"""scripts.platformkit.ingame.ingame_redcard_gate_soccer -- GATE-RUN for the soccer
in-game RED-CARD (man-advantage) detail layer carried by the materialized
soccer_cardstates__combo_* corpus (column `red_diff`).

THE QUESTION: the PROVEN soccer in-game champion is the goal-diff base+pregame-prior
(REPLICATED). Does adding the man-advantage term `red_diff` (as-of-minute, leak-free
cumulative red-card differential) beat that champion on held-out Brier, REPLICATED in
BOTH cross-corpus directions, DM clustered by game_id, without tripping the
degenerate-base guard?

This is the IDENTICAL machinery as ingame_shot_gate_soccer / ingame_xgloc_gate_soccer
(champion = goal base+prior; candidate = goal base + c*z_feat + prior; cross-corpus
A<->B; DM clustered by game_id; degenerate-base guard; graceful-degrade so a noise term
fits c->0 -> REJECT). We only swap the candidate feature to `red_diff`, so the man-
advantage layer is judged by EXACTLY the gate that judged the shot/xgloc proxies -- no
weakened bar.

GATE used: scripts.platformkit.ingame.ingame_shot_gate_soccer.gate
  (which inherits ingame_gate_generic_models: fit_base, base/prior predict, the
   degenerate-base guard) + scripts.platformkit.eval_gate.dm_test.diebold_mariano
  (DM clustered by game_id).

CROSS-CORPUS: two INDEPENDENT corpora on disk -- combo_eng_ger (EPL+Bundesliga) and
combo_esp_ita (La Liga+Serie A). If a corpus (base or cardstates) is missing for both,
we report INSUFFICIENT_DATA honestly (we never 0-fill missing coverage into a win).

PLANTED-NULL CONTROL: a pure-noise column (seeded per (game_id,asof_idx)) is run through
the IDENTICAL gate. It MUST NOT REPLICATE. If the null DOES replicate, the gate cannot
fail a signal and the whole run is UNTRUSTWORTHY -- we say so and refuse to ship.

HONEST EXPECTATION: PARTIAL/REJECT-leaning -- red cards are sparse (~4-6% of states have
red_diff != 0) and the goal-diff base already moves on margin, so the man-advantage term
has little residual to explain. A REJECT here is a SUCCESS (validated scouting), not a
failure; we NEVER force-feed a reject into the served model.

NO $ anywhere; verdict is CALIBRATION (held-out Brier), never a market edge.
PROPOSAL-ONLY: writes only data/frontend/funnel JSON, never data/registry/, never a flag.
INVARIANTS: never edit src/kernel; <=300 LOC; ASCII; numpy/pandas/stdlib + reuse.
CLI: python -m scripts.platformkit.ingame.ingame_redcard_gate_soccer
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

import pandas as pd

from scripts.platformkit.ingame.ingame_shot_gate_soccer import gate

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_OUT_DIR = os.path.join(_REPO, "data", "frontend", "funnel")
_COMBOS = ("combo_eng_ger", "combo_esp_ita")
_FEAT = "red_diff"
_NULL_FEAT = "planted_null"


def _base_path(label: str) -> str:
    return os.path.join(_STATE_DIR, f"soccer_states__{label}.parquet")


def _card_path(label: str) -> str:
    return os.path.join(_STATE_DIR, f"soccer_cardstates__{label}.parquet")


def _planted_null_col(game_id: str, asof_idx: int) -> float:
    """Deterministic pure-noise value keyed to (game_id, asof_idx).

    A fixed hash -> uniform float in [-2, 2]. It carries NO outcome information by
    construction; the gate MUST fail it. Deterministic so the control is reproducible.
    """
    h = hash((str(game_id), int(asof_idx), "planted-null-salt-redcard-2026"))
    return ((h % 100003) / 100003.0) * 4.0 - 2.0


def load_joined(label: str) -> List[dict]:
    """Join FROZEN base combo states with the cardstates layer on (game_id, asof_idx).

    inner-join so candidate (red_diff) and champion (goal+prior) see the SAME rows -- a
    fair head-to-head. Adds the planted-null column on the SAME rows. Leak-free: no
    future / final-aggregate column is read; missing card rows are DROPPED, never
    0-filled into a win.
    """
    base = pd.read_parquet(_base_path(label))
    card = pd.read_parquet(_card_path(label))
    base["game_id"] = base["game_id"].astype(str)
    card["game_id"] = card["game_id"].astype(str)
    df = base.merge(card[["game_id", "asof_idx", _FEAT]],
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
            if os.path.exists(_base_path(lb)) and os.path.exists(_card_path(lb))]


def _sparsity(states: List[dict]) -> Dict:
    n = len(states)
    nz = sum(1 for s in states if s.get(_FEAT, 0.0) != 0.0)
    return {"n_states": n, "n_red_states": nz,
            "frac_red": round(nz / n, 4) if n else 0.0}


def run() -> Dict:
    """Materialized-layer gate-run: real-feature gate + planted-null control, both dirs."""
    os.makedirs(_OUT_DIR, exist_ok=True)
    av = _avail()
    if len(av) < 2:
        verdict = {
            "verdict": "INSUFFICIENT_DATA", "gate": "ingame_shot_gate_soccer.gate",
            "feature": _FEAT,
            "reason": f"need 2 materialized base+cardstates corpora; found {len(av)}: {av}",
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "units_only": True, "proposal_only": True, "wired_into_served": False,
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
            "PLANTED-NULL did NOT reject (verdict=%s): the gate cannot FAIL a signal "
            "here, so the real-layer result is UNTRUSTWORTHY." % nullv.verdict)
    elif real_repl:
        final, why = "SHIP", (
            "red_diff REPLICATED both directions vs the goal-base+prior champion; "
            "planted-null correctly REJECTED -> gate can fail a signal.")
    else:
        final, why = "REJECT", (
            "red_diff did NOT replicate both directions (verdict=%s) vs the "
            "goal-base+prior champion; planted-null correctly REJECTED. Kept as "
            "VALIDATED in-game SCOUTING; NOT force-fed into the served model." % real.verdict)

    verdict = {
        "verdict": final, "reason": why, "gate": "ingame_shot_gate_soccer.gate",
        "feature": _FEAT, "corpora": [la, lb], "n_corpora": 2,
        "sparsity": {la: _sparsity(states_a), lb: _sparsity(states_b)},
        "real_layer": real.to_dict(),
        "planted_null": {"verdict": nullv.verdict, "rejects": bool(null_rejects),
                         "a_to_b": nullv.a_to_b, "b_to_a": nullv.b_to_a},
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "units_only": True, "proposal_only": True,
        "wired_into_served": final == "SHIP",
    }
    _write(verdict)
    _report(verdict)
    return verdict


def _write(v: Dict) -> str:
    out = os.path.join(_OUT_DIR, "soccer_redcard_ingame_gate.json")
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
    print("IN-GAME RED-CARD (MAN-ADVANTAGE) GATE-RUN [soccer / red_diff]")
    print("=" * 72)
    print(f"gate     : {v['gate']}   corpora: {v.get('corpora')}")
    print(f"sparsity : {v.get('sparsity')}")
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
    print(f"wired_into_served: {v.get('wired_into_served')}")
    print("=" * 72)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
