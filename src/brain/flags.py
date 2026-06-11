"""Single flag registry for the ``src.brain`` package.

ROADMAP phase: P0 (preconditions) — this module is the very first deliverable; every other
phase in .planning/brain/ROADMAP.md references one or more flag names defined here.

GATE to flip any flag ON: the gate criteria are listed per-flag in the ``FLAGS`` dict
(field "gate"). No flag may be set to ON in production until its gate criteria are met
AND the gate verdict is recorded in the honest-reject ledger. Flags default to OFF
unconditionally; reading an env var that is absent / empty / "0" / "false" / "no" / "off"
returns False.

Pre-existing flags (read by their owning modules; NOT registered here — do not add them):
  CV_LLM_CONTEXT           src/ingame/
  CV_INGAME_SBS            src/ingame/sbs_shadow.py
  CV_LIVE_SIM              src/sim/live_game_simulator.py
  CV_AVAIL_PARQUET_FALLBACK src/prediction/availability.py
  CV_ENSEMBLE16_DECORR     src/prediction/ (decorrelation layer)
  CV_ENGINE_RELIABILITY_WEIGHTS  src/prediction/ (engine weighting)

All names above are excluded from FLAGS to avoid a second-authority for flags that already
have a canonical home. ``assert_registered`` will raise for any name that belongs here.

Pure stdlib only (no torch / pandas / numpy at module load).
"""
from __future__ import annotations

import os
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Truthy env-var spellings (same set used across the codebase).
# ---------------------------------------------------------------------------
_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes", "on", "y", "t"})

# ---------------------------------------------------------------------------
# Names that are pre-existing and explicitly NOT registered here.
# Callers that pass these names to assert_registered will get a clear error.
# ---------------------------------------------------------------------------
_PREEXISTING_FLAGS: frozenset[str] = frozenset({
    "CV_LLM_CONTEXT",
    "CV_INGAME_SBS",
    "CV_LIVE_SIM",
    "CV_AVAIL_PARQUET_FALLBACK",
    "CV_ENSEMBLE16_DECORR",
    "CV_ENGINE_RELIABILITY_WEIGHTS",
})

# ---------------------------------------------------------------------------
# The single flag registry.
# Schema per entry:
#   default: bool   -- always False (architecture invariant)
#   phase:   str    -- roadmap phase that owns this flag (e.g. "P1.3")
#   gate:    str    -- human-readable gate criteria; must be met before flip
#   desc:    str    -- one-line description
# ---------------------------------------------------------------------------
FLAGS: Dict[str, Dict[str, Any]] = {
    # ------------------------------------------------------------------
    # P1 — Entity-Agent layer (L1 / D01)
    # ------------------------------------------------------------------
    "CV_AGENT_DEF_SUPP": {
        "default": False,
        "phase": "P1.3",
        "gate": (
            "sim walk-forward gate.evaluate: all folds improve; null-z>=3; "
            "calib-ok; n_min_per_season>=3000 player-games; "
            "5-team holdout (CLE/DAL/BOS) lift holds; seed-stable; "
            "verdict written to agent_registry"
        ),
        "desc": (
            "Defender-suppression L1 lever (cross-season r=0.60). "
            "The ONLY sim-fidelity lever with a ship path on current data. "
            "TIER-NOW. All other fidelity levers (play-type, foul-state, "
            "fatigue) are flag_allowed_on=FALSE until season-2 PBP."
        ),
    },
    "CV_AGENT_PLAYTYPE": {
        "default": False,
        "phase": "P1.S2",
        "gate": (
            "DATA_BLOCKED_UNTIL_2SEASON_PBP. "
            "flag_allowed_on=FALSE: a 4-game / 1-season-PBP slope sweep "
            "may NOT produce a SHIP verdict. Gate only opens with >=2-season "
            "PBP corpus + n_min + cross-season holdout."
        ),
        "desc": (
            "Play-type routing lever (research-only, TIER-S2). "
            "Built as a stub; must NOT be set ON in production until "
            "the season-2 PBP corpus is available and the gate passes."
        ),
    },
    "CV_AGENT_FOUL_STATE": {
        "default": False,
        "phase": "P1.S2",
        "gate": (
            "DATA_BLOCKED_UNTIL_2SEASON_PBP. "
            "flag_allowed_on=FALSE: same substrate requirement as CV_AGENT_PLAYTYPE. "
            "Gate only opens with >=2-season PBP corpus + n_min + cross-season holdout."
        ),
        "desc": (
            "Foul-state lever (research-only, TIER-S2). "
            "Stub only; must NOT be turned ON until the 2-season PBP gate passes."
        ),
    },
    "CV_AGENT_FATIGUE": {
        "default": False,
        "phase": "P1.S2",
        "gate": (
            "DATA_BLOCKED_UNTIL_2SEASON_PBP. "
            "flag_allowed_on=FALSE: intra-game fatigue requires >=2-season PBP; "
            "4-game Finals calibration forbidden from a SHIP verdict."
        ),
        "desc": (
            "Intra-game fatigue lever (research-only, TIER-S2). "
            "Stub only; must NOT be turned ON until the 2-season PBP gate passes."
        ),
    },
    # ------------------------------------------------------------------
    # P2 — Control Brain Rung 0/1 (L3 / D03)
    # ------------------------------------------------------------------
    "CV_BRAIN_GLS": {
        "default": False,
        "phase": "P2.2",
        "gate": (
            "Rung-1 GLS redundancy down-weight: weights derived from the "
            "correlation matrix ONLY (no skill claim); measured N_eff change "
            "reported; byte-identical when OFF; "
            "Rung-0 equal-weight passthrough recorded as the validated default "
            "(B8 marker written); no regime-skill claim on 1-season corpus."
        ),
        "desc": (
            "GLS redundancy down-weight for the control brain (Rung 1). "
            "Rung 0 (equal-weight passthrough) is the default and is always ON "
            "unconditionally. This flag gates only the GLS correlation correction. "
            "Rung-2 regime skill is DATA_BLOCKED (TIER-S2) and has no flag here."
        ),
    },
    "CV_BRAIN_WEIGHTS": {
        "default": False,
        "phase": "P2",
        "gate": (
            "Cutover hook in predict_ensemble16.py: when ON, eng_w is supplied by "
            "control_brain.engine_weights(preds). Rung 0 returns equal weights so "
            "eq_margin == margins.mean() -> BYTE-IDENTICAL to the default path. "
            "OFF (default) -> hook returns None -> live ensemble unchanged. "
            "Proven by tests/test_brain_cutover.py; CV_ENSEMBLE16_DECORR takes precedence."
        ),
        "desc": (
            "Routes the 16-engine fusion weight through the control brain. "
            "Default-OFF + byte-identical; the seam that makes the brain LIVE behind a flag."
        ),
    },
    # ------------------------------------------------------------------
    # P3 — In-game state engine (L4 / D04 + D06)
    # ------------------------------------------------------------------
    "CV_INGAME_STATE": {
        "default": False,
        "phase": "P3.1",
        "gate": (
            "Typed GameState superset (P0.4) + per-event apply_event hook; "
            "leak-free truncation-invariance test passes; "
            "drift distribution of |incremental-snapshot| at resync: mean~0; "
            "no LLM import on the hot path (B10 latency gate)."
        ),
        "desc": (
            "Routes the in-game layer through the typed unified GameState "
            "(src/ingame/game_state.py). Default OFF = existing inplay paths "
            "unchanged. TIER-NOW."
        ),
    },
    "CV_INGAME_SHRINK": {
        "default": False,
        "phase": "P3.3",
        "gate": (
            "frozen_score_shrink must beat the UNSHRUNK sim mean on BOTH "
            "RMSE and bias (not just MAE — the MAE-vs-RMSE artifact from "
            "project_ingame_mae_rmse_artifact_2026-06-05.md applies here). "
            "If it cannot beat on RMSE+bias, ships as a no-op serving the "
            "sim mean. Resim-parity gate also required. "
            "Requires P3.1 (CV_INGAME_STATE) and P5 (freshness) for full value."
        ),
        "desc": (
            "Frozen-score shrink between-poll re-price + RestOfGameSim at "
            "30s poll boundary. Has its OWN RMSE+bias serve gate independent "
            "of the resim-parity gate. TIER-NOW."
        ),
    },
    "CV_INGAME_UNIVERSAL_WP": {
        "default": False,
        "phase": "P3.4",
        "gate": (
            "No Brier regression vs production routing at EVERY game-time "
            "(floors: sim 0.126 / v6_hp 0.135). "
            "No sim-WP before endQ3. "
            "coverage_class != mc -> existing inplay_winprob stack (fail-closed). "
            "'Brier<=0.183' bar is DELETED per RED-B5 — only no-regression counts. "
            "B10 latency gate: full refresh (NumPy + 16 LGB heads + WP stack) "
            "worst-case under budget."
        ),
        "desc": (
            "Universal win-probability interface (projected-final+time). "
            "Routing stays measured; league-wide fails closed to inplay_winprob "
            "for non-mc coverage teams. TIER-NOW (5-team fast path only)."
        ),
    },
    # ------------------------------------------------------------------
    # P6 — Narration (L8 / D09)
    # ------------------------------------------------------------------
    "CV_NARRATE": {
        "default": False,
        "phase": "P6.1",
        "gate": (
            "Template engine produces a brief with ANTHROPIC_API_KEY unset "
            "(pure template, no LLM call at runtime/serving). "
            "Zero prediction-path change confirmed. "
            "Haiku runtime import excised from any non-narration code path. "
            "chat.py classified as opt-in dev tool only."
        ),
        "desc": (
            "Template-based narration engine (D09). Default OFF = no narration "
            "output; zero effect on predictions. Lowest-priority phase. TIER-NOW."
        ),
    },
    # ------------------------------------------------------------------
    # P7 — LLM scheme-prior layer (the LLM shapes sim knobs, never predicts)
    # ------------------------------------------------------------------
    "CV_LLM_SCHEME": {
        "default": False,
        "phase": "P7.1",
        "gate": (
            "The LLM-scheme sim must BEAT the no-LLM baseline on win-prob Brier AND "
            "score/margin RMSE+bias (not MAE), leak-free walk-forward, on >=2 independent "
            "corpora, seed-stable, truncation-invariant. flag_allowed_on=FALSE on current "
            "data: leak-free scout inputs (team four-factor/pace identity + expanding "
            "recency) are already encoded by the sim, so the layer is expected REDUNDANT "
            "for the betting number (cf. CV_AGENT_DEF_SUPP). All rich vs-scheme / defender "
            "rel-to-self / clutch reads are in_season-leaky -> scouting-only, never a number. "
            "No prior-season corpus exists (2024-25 absent) -> no leak-free vs-coverage split."
        ),
        "desc": (
            "LLM scheme-prior layer: the LLM emits bounded, named, justified, confidence-"
            "weighted multipliers on EXISTING sim knobs (src/sim/scheme_prior.py); the "
            "possession sim still computes every number. Default OFF = apply_scheme_priors "
            "never called = byte-identical CPU+GPU. Betting mode rejects leak_safe=false fields."
        ),
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_on(name: str) -> bool:
    """Return True iff the named flag is enabled via its environment variable.

    Rules (architecture-invariant):
    - Default is ALWAYS False (OFF), regardless of whether the name is registered.
    - Truthy spellings: ``1``, ``true``, ``yes``, ``on``, ``y``, ``t``
      (case-insensitive). Everything else, including absent / empty / ``"0"``,
      is False.
    - The function does NOT raise for unregistered names; use ``assert_registered``
      separately if you need that check.

    Args:
        name: The environment-variable / flag name (e.g. ``"CV_BRAIN_GLS"``).

    Returns:
        bool: True only when the env var is set to a truthy spelling.

    Example::

        if is_on("CV_BRAIN_GLS"):
            # import and use the GLS engine
            ...
    """
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def all_flags() -> Dict[str, Dict[str, Any]]:
    """Return a shallow copy of the full FLAGS registry dict.

    Each key is a flag name; each value is a dict with keys:
    ``default``, ``phase``, ``gate``, ``desc``.

    Returns:
        dict: Copy of the FLAGS registry (safe to mutate the copy).
    """
    return dict(FLAGS)


def assert_registered(name: str) -> None:
    """Assert that ``name`` belongs to the brain package's flag registry.

    Raises ``KeyError`` with a descriptive message if:
    - ``name`` is a pre-existing flag owned by another module (listed in
      ``_PREEXISTING_FLAGS`` — callers should import from the owning module).
    - ``name`` is not in either set (unknown flag).

    Does NOT raise for registered names in ``FLAGS``.

    Args:
        name: The flag name to check.

    Raises:
        KeyError: When the name is pre-existing (wrong module) or unknown.

    Example::

        assert_registered("CV_AGENT_DEF_SUPP")  # passes
        assert_registered("CV_INGAME_SBS")       # KeyError: pre-existing flag
    """
    if name in FLAGS:
        return
    if name in _PREEXISTING_FLAGS:
        raise KeyError(
            f"Flag {name!r} is a pre-existing flag owned by another module "
            f"(not the brain package). Import it from its canonical location. "
            f"Pre-existing flags: {sorted(_PREEXISTING_FLAGS)}"
        )
    raise KeyError(
        f"Flag {name!r} is not registered in src.brain.flags.FLAGS "
        f"and is not a known pre-existing flag. "
        f"Registered brain flags: {sorted(FLAGS)}"
    )


# ---------------------------------------------------------------------------
# TODO(P0.1): Wire assert_registered into the build-check that ensures no
#             unlisted weight/reliability JSON exists (ARCHITECTURE.md §3 + §2).
#             The check should iterate FLAGS and confirm every phase in the
#             "phase" field exists in the canonical roadmap.json.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TODO(P2.1): After brain/control_brain.py is built, re-export its Rung-0
#             passthrough here so the brain package is the single import point
#             for callers: from src.brain import route_ensemble.
# ---------------------------------------------------------------------------
