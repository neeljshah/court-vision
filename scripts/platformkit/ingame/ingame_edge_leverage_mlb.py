"""scripts.platformkit.ingame.ingame_edge_leverage_mlb -- GATE-RUN for the LEVERAGE /
CLUTCH-conditioning in-game candidate (audit E3), on the materialized MLB per-pitch
corpora (mlb_pitch_states__<season>) which carry an as-of `leverage_bucket`.

THE QUESTION: the PROVEN in-game champion is the (run_diff, frac_elapsed) BASE blended
with the leak-free pregame prior p0 (base+prior, REPLICATED). Does conditioning the
blend on LEVERAGE (clutch sensitivity of the win-prob to a marginal run at the as-of
state) beat that champion on held-out Brier, REPLICATED in BOTH cross-corpus directions,
DM clustered by game_id, without tripping the degenerate-base guard AND with the
planted-null rejecting?

Two leak-free as-of candidate features (standardized by TRAIN spread inside the gate):
  * leverage_score = {low:-1, mid:0, high:+1} from the as-of leverage_bucket
        an ADDITIVE leverage main-effect on the base logit.
  * leverage_x_prior = leverage_score * (p0 - 0.5)
        the PRIOR conditioned on leverage -- whether the pregame prior should be trusted
        MORE/LESS in high-leverage spots beyond what (run_diff,frac) already encodes.

HONEST PRIOR: REJECT. leverage_bucket is a near-deterministic function of (margin, outs,
runners, inning) -- much of which the (run_diff, frac_elapsed) base already sees -- so it
has little residual to explain. A REJECT here is a SUCCESS (validated efficiency).

CHAMPION (control, fit on TRAIN only):  blend(p0, BASE_run, w(time,margin))   -- PROVEN.
CANDIDATE (fit on TRAIN only):          blend(p0, BASE_run + c*z_feat, w)      -- c grid.
Reuses ingame_shot_gate_soccer.gate -- the IDENTICAL machinery as the soccer/red-card/
pitch gates; we only swap in the leverage feature, so no weakened bar.

GATE: TRUE cross-corpus A<->B (disjoint SEASONS) + DM CLUSTERED by game_id BOTH dirs +
degenerate-base guard + PLANTED-NULL (must reject). REPLICATED iff cand<champ Brier AND
DM p<eps BOTH dirs. Single-direction lift = ARTIFACT. INSUFFICIENT_DATA if <2 corpora.

NO $ anywhere; verdict is CALIBRATION (held-out Brier), never a market edge.
PROPOSAL-ONLY: writes only data/frontend/funnel JSON, never data/registry/, never a flag.
INVARIANTS: never edit src/kernel; <=300 LOC; ASCII; numpy/pandas/stdlib + reuse.
CLI: python -m scripts.platformkit.ingame.ingame_edge_leverage_mlb
"""
from __future__ import annotations

import glob
import json
import os
from typing import Dict, List

import pandas as pd

from scripts.platformkit.ingame.ingame_shot_gate_soccer import gate

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_OUT_DIR = os.path.join(_REPO, "data", "frontend", "funnel")

_LEV_MAP = {"low": -1.0, "mid": 0.0, "high": 1.0}
_FEATS = ("leverage_score", "leverage_x_prior")
_NULL_FEAT = "planted_null"


def _planted_null_col(game_id: str, asof_idx: int) -> float:
    """Deterministic pure-noise value keyed to (game_id, asof_idx) -- no outcome info;
    the gate MUST fail it. Reproducible (fixed salt)."""
    h = hash((str(game_id), int(asof_idx), "planted-null-salt-leverage-2026"))
    return ((h % 100003) / 100003.0) * 4.0 - 2.0


def load_states(path: str) -> List[dict]:
    """Load one mlb_pitch_states corpus; derive leak-free as-of leverage features.

    leverage_bucket -> ordinal leverage_score; leverage_x_prior = score*(p0-0.5). An
    unknown/NaN bucket maps to 0 (no fabricated leverage). Only the frozen base columns
    + the as-of leverage_bucket are read; no future / final-aggregate column."""
    df = pd.read_parquet(path)
    cols = ["game_id", "asof_idx", "state_diff", "frac_elapsed", "p0", "outcome",
            "leverage_bucket"]
    df = df[cols].copy()
    df["game_id"] = df["game_id"].astype(str)
    out: List[dict] = []
    for r in df.itertuples(index=False):
        lev = _LEV_MAP.get(str(r.leverage_bucket).strip().lower(), 0.0)
        p0 = float(r.p0)
        out.append({
            "game_id": str(r.game_id),
            "state_diff": float(r.state_diff),
            "frac_elapsed": max(0.0, min(1.0, float(r.frac_elapsed))),
            "p0": p0, "outcome": int(r.outcome),
            "leverage_score": lev,
            "leverage_x_prior": lev * (p0 - 0.5),
            _NULL_FEAT: _planted_null_col(str(r.game_id), int(r.asof_idx)),
        })
    return out


def _find_corpora() -> List[str]:
    return sorted(glob.glob(os.path.join(_STATE_DIR, "mlb_pitch_states__*.parquet")))


def _gate_one(states_a, states_b, feat, la, lb) -> Dict:
    real = gate(states_a, states_b, feat, la, lb)
    nullv = gate(states_a, states_b, _NULL_FEAT, la, lb)
    null_rejects = nullv.verdict != "REPLICATED"
    if not null_rejects:
        final = "NOT_TESTABLE"
    elif real.verdict == "REPLICATED":
        final = "SHIP"
    else:
        final = "REJECT"
    a2b, b2a = real.a_to_b, real.b_to_a
    base_skillful = bool(a2b and b2a and not a2b.get("base_degenerate")
                         and not b2a.get("base_degenerate"))
    return {
        "feature": feat, "verdict": final,
        "cand_beats_a_to_b": bool(a2b.get("cand_beats_champ")),
        "cand_beats_b_to_a": bool(b2a.get("cand_beats_champ")),
        "dm_p_a_to_b": a2b.get("dm_p"), "dm_p_b_to_a": b2a.get("dm_p"),
        "brier_champ_a_to_b": a2b.get("brier_champ"),
        "brier_cand_a_to_b": a2b.get("brier_cand"),
        "brier_champ_b_to_a": b2a.get("brier_champ"),
        "brier_cand_b_to_a": b2a.get("brier_cand"),
        "base_skillful": base_skillful,
        "null_rejected": bool(null_rejects), "null_verdict": nullv.verdict,
        "real_layer": real.to_dict(), "wired_into_served": final == "SHIP",
    }


def _lev_sparsity(states: List[dict]) -> Dict:
    n = len(states)
    hi = sum(1 for s in states if s["leverage_score"] > 0.5)
    lo = sum(1 for s in states if s["leverage_score"] < -0.5)
    return {"n_states": n, "n_high": hi, "n_low": lo,
            "frac_high": round(hi / n, 4) if n else 0.0}


def run() -> Dict:
    os.makedirs(_OUT_DIR, exist_ok=True)
    paths = _find_corpora()
    if len(paths) < 2:
        verdict = {
            "verdict": "INSUFFICIENT_DATA", "gate": "ingame_shot_gate_soccer.gate",
            "candidates": list(_FEATS),
            "reason": f"need >=2 mlb_pitch_states__*.parquet corpora; found {len(paths)}",
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "units_only": True, "proposal_only": True, "wired_into_served": False,
        }
        _write(verdict)
        return verdict

    la = os.path.basename(paths[0]).split("__")[1].replace(".parquet", "")
    lb = os.path.basename(paths[1]).split("__")[1].replace(".parquet", "")
    states_a, states_b = load_states(paths[0]), load_states(paths[1])

    per_feat = {f: _gate_one(states_a, states_b, f, la, lb) for f in _FEATS}
    any_ship = any(d["verdict"] == "SHIP" for d in per_feat.values())
    untestable = any(d["verdict"] == "NOT_TESTABLE" for d in per_feat.values())
    if untestable:
        final, why = "NOT_TESTABLE", (
            "PLANTED-NULL did NOT reject for >=1 feature -> UNTRUSTWORTHY.")
    elif any_ship:
        survivors = [f for f, d in per_feat.items() if d["verdict"] == "SHIP"]
        final, why = "PROPOSAL", (
            "a leverage-conditioning feature SURVIVED both directions over a SKILLFUL "
            "base with the null rejecting: %s -- PROPOSAL ONLY, not force-fed; needs "
            "CLV-vs-close before any claim." % survivors)
    else:
        final, why = "REJECT", (
            "no leverage-conditioning feature replicated both directions vs the proven "
            "base+prior champion; planted-null correctly REJECTED. Kept as VALIDATED "
            "in-game SCOUTING; NOT force-fed into the served model.")

    verdict = {
        "verdict": final, "reason": why, "gate": "ingame_shot_gate_soccer.gate",
        "candidates": list(_FEATS), "corpora": [la, lb], "n_corpora": 2,
        "sparsity": {la: _lev_sparsity(states_a), lb: _lev_sparsity(states_b)},
        "champion": "blend(p0, sigmoid((a+b*frac)*run_diff), w) -- PROVEN base+prior",
        "candidate_form": "blend(p0, sigmoid((a+b*frac)*run_diff + c*z_leverage), w)",
        "per_feature": per_feat,
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "units_only": True, "proposal_only": True,
        "wired_into_served": final == "PROPOSAL" and any_ship,
    }
    _write(verdict)
    _report(verdict)
    return verdict


def _write(v: Dict) -> str:
    out = os.path.join(_OUT_DIR, "mlb_leverage_ingame_edge.json")
    with open(out, "w", encoding="ascii") as f:
        json.dump(v, f, indent=2, sort_keys=True)
    print(f"wrote {out}")
    return out


def _report(v: Dict) -> None:
    print("=" * 72)
    print("IN-GAME LEVERAGE / CLUTCH-CONDITIONING EDGE GATE-RUN [mlb]")
    print("=" * 72)
    print(f"gate    : {v['gate']}   corpora: {v.get('corpora')}")
    print(f"sparsity: {v.get('sparsity')}")
    for f, d in v.get("per_feature", {}).items():
        print("-" * 72)
        print(f"  {f}: VERDICT {d['verdict']}  base_skillful={d['base_skillful']}  "
              f"null_rejected={d['null_rejected']}")
        print(f"    A->B: CHAMP {d['brier_champ_a_to_b']} -> CAND {d['brier_cand_a_to_b']}"
              f"  DM p {d['dm_p_a_to_b']}  beats={d['cand_beats_a_to_b']}")
        print(f"    B->A: CHAMP {d['brier_champ_b_to_a']} -> CAND {d['brier_cand_b_to_a']}"
              f"  DM p {d['dm_p_b_to_a']}  beats={d['cand_beats_b_to_a']}")
    print("-" * 72)
    print(f"FINAL VERDICT: {v['verdict']}  -- {v['reason']}")
    print(f"wired_into_served: {v.get('wired_into_served')}")
    print("=" * 72)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
