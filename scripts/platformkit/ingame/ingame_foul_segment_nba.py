"""scripts.platformkit.ingame.ingame_foul_segment_nba -- NBA foul-trouble segment recal.

The full-panel foul gate REJECTED (c=0 no-op in all time-buckets). This module applies
the segment_filter pattern: restrict the correction to Q4 + |foul_diff|>=2 (where foul
trouble has the strongest theoretical rationale) and apply UNDER-only (only when the
correction REDUCES home-win prob). All non-segment rows are bit-identical to M0.

SEGMENT: frac_elapsed >= 0.75 AND |foul_diff| >= SEG_MIN_DIFF (default 2).
UNDER-ONLY: apply only when c * z < 0 (correction reduces p_home).
IDENTITY: non-segment rows of M1 == M0 exactly (enforced by test assertion).
DISCIPLINE: true cross-corpus A<->B; c fit on TRAIN segment rows (grid incl 0);
  DM clustered by game_id; SHIP requires both directions; honest REJECT is a SUCCESS.

NO $ anywhere; verdict is CALIBRATION (held-out Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_foul_segment_nba
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.eval_gate.ingame_blend import (
    blended_predictions,
    fit_weight_surface,
)
from scripts.platformkit.ingame.ingame_foul_gate_nba import (
    FOUL_A, FOUL_B, LINES_A, LINES_B,
    _C_GRID, _logit, _sigmoid,
    states_from_foul_pbp,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "foul_segment_nba.json")

SEG_FRAC_THRESH = 0.75   # Q4 (frac_elapsed >= 0.75)
SEG_MIN_DIFF = 2.0       # |foul_diff| must be >= 2 to enter the segment
_LOGIT_CLIP = 1e-6
_MIN_SEG_STATES = 30     # minimum segment rows in TRAIN to attempt fitting c


def _in_segment(states: List[dict]) -> np.ndarray:
    """Boolean mask: True for rows in the Q4 + meaningful-foul-diff segment."""
    frac = np.array([s["frac_elapsed"] for s in states], float)
    fd = np.array([s["foul_diff"] for s in states], float)
    return (frac >= SEG_FRAC_THRESH) & (np.abs(fd) >= SEG_MIN_DIFF)


def fit_segment_c(train: List[dict], m0_train: np.ndarray,
                  seg_mask: np.ndarray) -> Tuple[float, float, bool]:
    """Fit foul logit slope on SEGMENT rows of TRAIN by Brier grid (includes 0).

    Returns (c, spread, fitted). fitted=False + c=0 when segment is too thin.
    """
    seg_idx = np.where(seg_mask)[0]
    if len(seg_idx) < _MIN_SEG_STATES:
        return 0.0, 1.0, False
    fd_seg = np.array([train[i]["foul_diff"] for i in seg_idx], float)
    y_seg = np.array([train[i]["outcome"] for i in seg_idx], float)
    m0_seg = m0_train[seg_idx]
    spread = float(np.std(fd_seg)) or 1.0
    z_seg = fd_seg / spread
    lg_seg = np.log(np.clip(m0_seg, _LOGIT_CLIP, 1.0 - _LOGIT_CLIP)
                    / np.clip(1.0 - m0_seg, _LOGIT_CLIP, 1.0 - _LOGIT_CLIP))
    best_c = 0.0
    best_b = float(np.mean((m0_seg - y_seg) ** 2))
    for c in _C_GRID:
        p = _sigmoid(lg_seg + c * z_seg)
        b = float(np.mean((p - y_seg) ** 2))
        if b < best_b:
            best_b, best_c = b, float(c)
    return best_c, spread, True


def apply_segment_correction(states: List[dict], m0: np.ndarray,
                              seg_mask: np.ndarray, c: float,
                              spread: float) -> np.ndarray:
    """UNDER-only segment correction: M1=M0 outside segment; inside segment, only
    apply when c*z<0 (correction reduces home-win prob). M1 never exceeds M0.
    """
    m1 = m0.copy()
    fd = np.array([s["foul_diff"] for s in states], float)
    z = fd / (spread or 1.0)
    correction = c * z
    # UNDER-only: apply only where correction pushes prob down
    active = seg_mask & (correction < 0.0)
    if not active.any():
        return m1
    lg = np.log(np.clip(m0, _LOGIT_CLIP, 1.0 - _LOGIT_CLIP)
                / np.clip(1.0 - m0, _LOGIT_CLIP, 1.0 - _LOGIT_CLIP))
    m1[active] = _sigmoid(lg[active] + correction[active])
    return m1


def cross_direction(train: List[dict], test: List[dict], eps: float = 0.05) -> Dict:
    """Fit M0 blend + segment c on TRAIN; score segment M0 vs M1 on TEST."""
    surf = fit_weight_surface(train, min_cell=20)
    m0_tr = blended_predictions(train, surf)
    seg_tr = _in_segment(train)
    c, spread, fitted = fit_segment_c(train, m0_tr, seg_tr)

    m0 = blended_predictions(test, surf)
    seg_te = _in_segment(test)
    m1 = apply_segment_correction(test, m0, seg_te, c, spread)

    y = np.array([s["outcome"] for s in test], float)
    gids = [s["game_id"] for s in test]
    n_seg = int(seg_te.sum())

    if n_seg > 0:
        b0_seg = float(brier(m0[seg_te], y[seg_te]))
        b1_seg = float(brier(m1[seg_te], y[seg_te]))
        gids_seg = [gids[i] for i in np.where(seg_te)[0]]
        d_seg = (m0[seg_te] - y[seg_te]) ** 2 - (m1[seg_te] - y[seg_te]) ** 2
        dm_seg = diebold_mariano(d_seg, gids_seg)
        seg_beats = bool((b1_seg < b0_seg) and (dm_seg.p_value < eps)
                         and fitted and abs(c) > 1e-6)
    else:
        b0_seg = b1_seg = 0.0
        dm_seg = type("DM", (), {"dm_stat": 0.0, "p_value": 1.0, "n_clusters": 0})()
        seg_beats = False

    # identity guard: non-segment M1 must equal M0 exactly
    non_seg = ~seg_te
    identity_ok = bool(np.array_equal(m1[non_seg], m0[non_seg])) if non_seg.any() else True
    fd_te = np.array([s["foul_diff"] for s in test], float)
    n_modified = int((seg_te & ((c * fd_te / (spread or 1.0)) < 0.0)).sum())

    return {
        "n_train_states": len(train), "n_train_seg": int(seg_tr.sum()),
        "n_test_states": len(test), "n_test_seg": n_seg,
        "n_test_modified": n_modified, "n_seg_games": dm_seg.n_clusters,
        "seg_frac_thresh": SEG_FRAC_THRESH, "seg_min_diff": SEG_MIN_DIFF,
        "c_fit": round(c, 4), "spread_fit": round(spread, 4), "fitted": fitted,
        "brier_m0_seg": round(b0_seg, 5), "brier_m1_seg": round(b1_seg, 5),
        "brier_delta_seg": round(b0_seg - b1_seg, 6),
        "dm_stat_seg": round(float(dm_seg.dm_stat), 4),
        "dm_p_seg": round(float(dm_seg.p_value), 6),
        "seg_beats_m0": seg_beats, "identity_outside_ok": identity_ok,
    }


def decide(a_to_b: Dict, b_to_a: Dict) -> str:
    """SHIP iff segment Brier improves in BOTH directions; PARTIAL if one; REJECT else.
    REJECT if identity guard fails in either direction.
    """
    if not (a_to_b.get("identity_outside_ok") and b_to_a.get("identity_outside_ok")):
        return "REJECT"
    a = bool(a_to_b.get("seg_beats_m0"))
    b = bool(b_to_a.get("seg_beats_m0"))
    if a and b:
        return "SHIP"
    return "PARTIAL" if (a or b) else "REJECT"


@dataclass
class FoulSegVerdict:
    verdict: str
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)
    coverage: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "layer": "foul_segment (Q4 + |foul_diff|>=2, UNDER-only)",
            "reference_model": "M0 = PROVEN blend(p0_elo, p_live(margin,frac), w)",
            "candidate_model": (
                "M1=sigmoid(logit(M0)+c*z) for Q4+|fd|>=2+c*z<0 rows; M0 elsewhere"
            ),
            "design": (
                "true cross-corpus A<->B; c fit on TRAIN segment only; "
                "DM clustered by game_id; grid incl 0; identity outside segment"
            ),
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "a_to_b": self.a_to_b, "b_to_a": self.b_to_a,
            "coverage": self.coverage, "caveats": list(self.caveats),
        }


def run_gate(states_a: List[dict], states_b: List[dict],
             caveats: Optional[List[str]] = None) -> FoulSegVerdict:
    a_to_b = cross_direction(states_a, states_b)
    b_to_a = cross_direction(states_b, states_a)
    cov = {
        "a_states": len(states_a), "a_games": len({s["game_id"] for s in states_a}),
        "b_states": len(states_b), "b_games": len({s["game_id"] for s in states_b}),
    }
    return FoulSegVerdict(decide(a_to_b, b_to_a), a_to_b, b_to_a, cov,
                          list(caveats or []))


def run(foul_a: str = FOUL_A, foul_b: str = FOUL_B,
        lines_a: str = LINES_A, lines_b: str = LINES_B) -> FoulSegVerdict:
    states_a = states_from_foul_pbp(foul_a, lines_a)
    states_b = states_from_foul_pbp(foul_b, lines_b)
    caveats = [
        f"Segment = Q4 (frac>={SEG_FRAC_THRESH}) AND |foul_diff|>={SEG_MIN_DIFF}; "
        "non-segment rows are bit-identical to M0.",
        "UNDER-only: correction applied only when c*z<0 (reduces home-win prob). "
        "Foul trouble on the leading side nudges toward trailing side winning.",
        "c fit on TRAIN segment rows (Brier grid incl 0 -> collapses to no-op on null); "
        "spread from TRAIN segment; no look-ahead.",
        "True cross-corpus A<->B + DM clustered by game_id. "
        "SHIP requires both directions; honest REJECT is a SUCCESS.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier), never a market edge.",
    ]
    return run_gate(states_a, states_b, caveats)


def write(verdict: FoulSegVerdict, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(verdict.to_dict(), f, indent=2, sort_keys=True)
    return out


def _dir_report(name: str, d: Dict) -> List[str]:
    return [
        f"  {name}:",
        f"    train {d.get('n_train_states')} ({d.get('n_train_seg')} in seg) "
        f"-> test {d.get('n_test_states')} ({d.get('n_test_seg')} in seg, "
        f"{d.get('n_test_modified')} modified)",
        f"    c_fit={d.get('c_fit')}  spread={d.get('spread_fit')}  fitted={d.get('fitted')}",
        f"    seg OOS Brier: M0 {d.get('brier_m0_seg')}  M1 {d.get('brier_m1_seg')}"
        f"  (delta {d.get('brier_delta_seg')})",
        f"    DM(seg): stat {d.get('dm_stat_seg')}  p {d.get('dm_p_seg')}",
        f"    seg_beats_m0={d.get('seg_beats_m0')}  "
        f"identity_ok={d.get('identity_outside_ok')}",
    ]


def _report(v: FoulSegVerdict) -> str:
    c = v.coverage
    lines = [
        "=" * 72,
        "IN-GAME FOUL-SEGMENT RECAL (NBA): Q4 + |foul_diff|>=2, UNDER-only",
        "=" * 72,
        f"VERDICT  : {v.verdict}",
        f"coverage : A {c.get('a_games')} games / {c.get('a_states')} states ; "
        f"B {c.get('b_games')} games / {c.get('b_states')} states",
        "-" * 72,
    ]
    lines += _dir_report("A->B (train 2024-25, test 2025-26)", v.a_to_b)
    lines.append("-" * 72)
    lines += _dir_report("B->A (train 2025-26, test 2024-25)", v.b_to_a)
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
