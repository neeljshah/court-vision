"""scripts.platformkit.ingame.ingame_edge_priorinteract_mlb -- GATE-RUN for the
PRIOR-CONDITIONED in-game INTERACTION candidates the audit ranked most-likely to carry
residual in-game signal (E2 prior x margin and E8 run-conditioned-on-prior), on the
multi-season MLB win-prob corpora (mlb_states__<season>).

THE QUESTION: the PROVEN in-game champion is the (run_diff, frac_elapsed) BASE blended
with the leak-free pregame prior p0 (base+prior, REPLICATED cross-corpus). Do these
PRIOR-CONDITIONED INTERACTION terms -- which the additive base+prior blend cannot by
construction express -- beat that champion on held-out Brier, REPLICATED in BOTH
cross-corpus directions, DM clustered by game_id, without tripping the degenerate-base
guard AND with the planted-null correctly rejecting?

CANDIDATE FEATURES (all leak-free, as-of state[:i+1] only; standardized by TRAIN spread
inside the gate):
  * prior_x_margin = (p0 - 0.5) * state_diff
        whether the prior's pull should SCALE with the current lead (a prior x current-
        margin interaction the additive blend(p0, BASE, w(time,margin)) cannot capture:
        the blend mixes p0 and BASE, it never multiplies p0 BY the live margin).
  * prior_x_time   = (p0 - 0.5) * frac_elapsed
        whether the prior's pull should decay/grow MULTIPLICATIVELY with elapsed time
        beyond the per-cell w(time,*) the blend already fits.
  * run_x_prior    = run_signed * (p0 - 0.5)
        the run conditioned on the prior (E8). raw run REJECTED across 4 sports; here we
        test ONLY the run x prior interaction (run = signed delta in state_diff over the
        last <=3 as-of ticks within the game; a same-side run is +, an opp run is -).
        run alone failing does NOT predict the interaction fails -- so we gate it, but
        the honest prior is REJECT (interaction rarely rescues a dead main effect).

CHAMPION (control, fit on TRAIN only):  blend(p0, BASE_run, w(time,margin))   -- PROVEN.
CANDIDATE (fit on TRAIN only):          blend(p0, BASE_run + c*z_feat, w)      -- c grid.
  This is the IDENTICAL machinery as ingame_shot_gate_soccer.gate (the soccer red-card /
  shot / xgloc gates all reuse it). We only swap in MLB-derived interaction features, so
  the candidate is judged by EXACTLY the gate that judged those -- no weakened bar.

GATE (identical, never weakened): TRUE cross-corpus A<->B (disjoint SEASONS) + DM
CLUSTERED by game_id BOTH directions + degenerate-base guard + a PLANTED-NULL control run
through the IDENTICAL gate that MUST reject (else the run is UNTRUSTWORTHY). REPLICATED
iff cand<champ Brier AND DM p<eps in BOTH directions. A single fold/direction lift is an
ARTIFACT. INSUFFICIENT_DATA (honest) if <2 corpora on disk.

HONEST EXPECTATION: REJECT-leaning. The additive base+prior is already strong (MLB BASE
Brier ~0.13-0.16, skillful); interaction terms rarely rescue. A REJECT here is a SUCCESS
(validated efficiency, not a failure); a both-direction cross-corpus survivor over a
SKILLFUL non-degenerate base with the null rejecting would be a real PROPOSAL -- and is
NEVER force-fed into the served model.

NO $ anywhere; verdict is CALIBRATION (held-out Brier), never a market edge.
PROPOSAL-ONLY: writes only data/frontend/funnel JSON, never data/registry/, never a flag.
INVARIANTS: never edit src/kernel; <=300 LOC; ASCII; numpy/pandas/stdlib + reuse.
CLI: python -m scripts.platformkit.ingame.ingame_edge_priorinteract_mlb
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
_RUN_WINDOW = 3  # as-of ticks for the signed run (within-game, leak-free trailing window)

# candidate features (gated independently) + the mandatory planted-null control.
_FEATS = ("prior_x_margin", "prior_x_time", "run_x_prior")
_NULL_FEAT = "planted_null"


def _planted_null_col(game_id: str, asof_idx: int) -> float:
    """Deterministic pure-noise value keyed to (game_id, asof_idx) -- carries NO outcome
    info by construction; the gate MUST fail it. Reproducible (fixed salt)."""
    h = hash((str(game_id), int(asof_idx), "planted-null-salt-priorinteract-2026"))
    return ((h % 100003) / 100003.0) * 4.0 - 2.0


def _signed_run(prev_diffs: List[float], cur_diff: float) -> float:
    """Signed run = cur_diff minus the diff _RUN_WINDOW ticks ago (within the SAME game).

    Leak-free: uses only prior as-of states[:i]. A same-side scoring run is +, an
    opponent run is -. Early (no window yet) -> 0 (no fabricated run).
    """
    if not prev_diffs:
        return 0.0
    ref = prev_diffs[-_RUN_WINDOW] if len(prev_diffs) >= _RUN_WINDOW else prev_diffs[0]
    return float(cur_diff - ref)


def load_states(path: str) -> List[dict]:
    """Load one mlb_states corpus, derive the leak-free as-of interaction features.

    Frozen base schema (game_id, asof_idx, state_diff, frac_elapsed, p0, outcome) +
    the derived candidate features + the planted-null. Rows are processed per game in
    asof_idx order so the signed run only ever looks BACKWARD (states[:i])."""
    df = pd.read_parquet(path)
    df = df[["game_id", "asof_idx", "state_diff", "frac_elapsed", "p0", "outcome"]].copy()
    df["game_id"] = df["game_id"].astype(str)
    df = df.sort_values(["game_id", "asof_idx"])
    out: List[dict] = []
    cur_gid = None
    prev_diffs: List[float] = []
    for r in df.itertuples(index=False):
        gid = str(r.game_id)
        if gid != cur_gid:
            cur_gid, prev_diffs = gid, []
        sd = float(r.state_diff)
        fe = max(0.0, min(1.0, float(r.frac_elapsed)))
        p0 = float(r.p0)
        pc = p0 - 0.5
        run = _signed_run(prev_diffs, sd)
        out.append({
            "game_id": gid, "state_diff": sd, "frac_elapsed": fe, "p0": p0,
            "outcome": int(r.outcome),
            "prior_x_margin": pc * sd,
            "prior_x_time": pc * fe,
            "run_x_prior": run * pc,
            _NULL_FEAT: _planted_null_col(gid, int(r.asof_idx)),
        })
        prev_diffs.append(sd)
    return out


def _find_corpora() -> List[str]:
    return sorted(glob.glob(os.path.join(_STATE_DIR, "mlb_states__*.parquet")))


def _gate_one(states_a: List[dict], states_b: List[dict], feat: str,
              la: str, lb: str) -> Dict:
    """Run the proven candidate gate for one feature + report cand_beats both dirs."""
    real = gate(states_a, states_b, feat, la, lb)
    nullv = gate(states_a, states_b, _NULL_FEAT, la, lb)
    null_rejects = nullv.verdict != "REPLICATED"
    real_repl = real.verdict == "REPLICATED"
    if not null_rejects:
        final = "NOT_TESTABLE"
    elif real_repl:
        final = "SHIP"
    else:
        final = "REJECT"
    a2b, b2a = real.a_to_b, real.b_to_a
    base_skillful = bool(
        a2b and b2a
        and not a2b.get("base_degenerate") and not b2a.get("base_degenerate"))
    return {
        "feature": feat, "verdict": final,
        "cand_beats_a_to_b": bool(a2b.get("cand_beats_champ")),
        "cand_beats_b_to_a": bool(b2a.get("cand_beats_champ")),
        "dm_p_a_to_b": a2b.get("dm_p"), "dm_p_b_to_a": b2a.get("dm_p"),
        "brier_champ_a_to_b": a2b.get("brier_champ"),
        "brier_cand_a_to_b": a2b.get("brier_cand"),
        "brier_champ_b_to_a": b2a.get("brier_champ"),
        "brier_cand_b_to_a": b2a.get("brier_cand"),
        "base_degenerate_a_to_b": bool(a2b.get("base_degenerate")),
        "base_degenerate_b_to_a": bool(b2a.get("base_degenerate")),
        "base_skillful": base_skillful,
        "null_rejected": bool(null_rejects),
        "null_verdict": nullv.verdict,
        "real_layer": real.to_dict(),
        "wired_into_served": final == "SHIP",
    }


def run() -> Dict:
    os.makedirs(_OUT_DIR, exist_ok=True)
    paths = _find_corpora()
    if len(paths) < 2:
        verdict = {
            "verdict": "INSUFFICIENT_DATA", "gate": "ingame_shot_gate_soccer.gate",
            "candidates": list(_FEATS),
            "reason": f"need >=2 mlb_states__*.parquet corpora; found {len(paths)}",
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
            "PLANTED-NULL did NOT reject for >=1 feature: the gate cannot FAIL a signal "
            "-> the run is UNTRUSTWORTHY.")
    elif any_ship:
        survivors = [f for f, d in per_feat.items() if d["verdict"] == "SHIP"]
        final, why = "PROPOSAL", (
            "prior-conditioned interaction SURVIVED both directions over a SKILLFUL "
            "base with the null rejecting: %s -- PROPOSAL ONLY, not force-fed into the "
            "served model; needs CLV-vs-close before any claim." % survivors)
    else:
        final, why = "REJECT", (
            "no prior-conditioned interaction replicated both directions vs the proven "
            "base+prior champion; planted-null correctly REJECTED. Kept as VALIDATED "
            "in-game SCOUTING; NOT force-fed into the served model.")

    verdict = {
        "verdict": final, "reason": why, "gate": "ingame_shot_gate_soccer.gate",
        "candidates": list(_FEATS), "corpora": [la, lb], "n_corpora": 2,
        "champion": "blend(p0, sigmoid((a+b*frac)*run_diff), w) -- PROVEN base+prior",
        "candidate_form": "blend(p0, sigmoid((a+b*frac)*run_diff + c*z_interaction), w)",
        "per_feature": per_feat,
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "units_only": True, "proposal_only": True,
        "wired_into_served": final == "PROPOSAL" and any_ship,
    }
    _write(verdict)
    _report(verdict)
    return verdict


def _write(v: Dict) -> str:
    out = os.path.join(_OUT_DIR, "mlb_priorinteract_ingame_edge.json")
    with open(out, "w", encoding="ascii") as f:
        json.dump(v, f, indent=2, sort_keys=True)
    print(f"wrote {out}")
    return out


def _report(v: Dict) -> None:
    print("=" * 72)
    print("IN-GAME PRIOR-CONDITIONED INTERACTION EDGE GATE-RUN [mlb]")
    print("=" * 72)
    print(f"gate    : {v['gate']}   corpora: {v.get('corpora')}")
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
