"""domains.basketball_wnba.elo_refresh_gate_spec -- pre-registered candidate
specs + caveat strings for elo_refresh_gate.py. Pure DATA literals, split out
to keep elo_refresh_gate.py (the gate math) under the 300 LOC cap (spec DATA
modules are exempt per .claude/rules/human-gated-paths.md).

F5: no src.*/kernel.*/other-domain imports. ASCII stdout only.
"""
from __future__ import annotations

CAND_SPEC = {
    "C1_mov": dict(use_mov=True, neutral_aware=False),
    "C2_neutral_hfa": dict(use_mov=False, neutral_aware=True),
    "C3_mov_neutral": dict(use_mov=True, neutral_aware=True),
}


def build_caveats(train_frac: float, adoption_bss_floor: float) -> list:
    return [
        "BASELINE params (ELO_K/MEAN/HFA/SEASON_REGRESS) reused unmodified; "
        "ratings.py/elo_config.py NOT edited. Per-fold p_base is "
        "_replay_candidate(use_mov=False, neutral_aware=False) COLD-started "
        "on the SAME single-season slice as the candidate (not the warm, "
        "multi-season walk_forward_elo column), so bss_delta isolates only "
        "the update-rule change (MOV / neutral-HFA), not cold/warm-start "
        "accumulation drift.",
        "Within-season %.0f/%.0f split per season, matching "
        "rest_covariate_gate's fold; 2024 = warmup only, never scored. "
        "Adoption floor: BSS delta >= %.3f on BOTH seasons, SAME sign -- "
        "split verdict is REJECT." % (train_frac * 100, (1 - train_frac) * 100,
                                       adoption_bss_floor),
        "PLANTED NULL (C1/C3): true margin shuffled within-season; null "
        "capturing >=50% of real BSS lift -> NOT_TESTABLE. No WNBA close "
        "corpus -- close_comparison PENDING; calibration never edge. If "
        "SHIP_CANDIDATE, params RECORDED here only -- the swap is a later, "
        "reviewed lane.",
    ]


__all__ = ["CAND_SPEC", "build_caveats"]
