"""domains.tennis.profiles.attribute_registry -- single source of truth for
the tennis attribute engine's per-attribute status/floor/weight_ledger_family.
build_profiles.py reads this dict for metadata (coverage report, status
column, floor checks); the actual math per attribute lives in
build_profiles.py + ingredients.py as plain functions -- NOT a generic
formula executor (six attributes don't earn one; see ponytail rung 1).

STATUS enum (task-declared, verbatim):
  VALIDATED_MECHANISM -- only pressure_serve: raw_value is literally the
    per-player break-point-vs-baseline delta whose SIGN/SIGNIFICANCE was
    independently REPLICATED (same-sign, p<alpha in BOTH slam_points and
    charting_points 2016+) as H1 in prereg_point_mechanisms.py.
  VALIDATED_CLAIM -- reserved for an attribute whose value is a straight
    passthrough of an ALREADY claims_validator-VERIFIED ("green") claims
    family distinct from pressure_serve's own mechanism designation. No
    attribute below currently qualifies -- pressure_serve is explicitly
    VALIDATED_MECHANISM per the task spec, not this. Kept in the enum so a
    future attribute (e.g. a straight reuse of tennis_pressure_claims'
    bp_save_delta ranking under a new name) has a home without a schema
    change.
  DESCRIPTIVE -- everything else: real, floor-gated, but no prereg/
    replication/independent-validation claim attached.
  BLOCKED -- registered but NOT built; `reason` explains why, so the
    registry stays the single place that documents every attribute the
    task asked for, built or not.

surface_splits emits SIX concrete attribute names (one per direction x
surface); generated below by a plain loop, not a runtime abstraction.
"""
from __future__ import annotations

VALIDATED_MECHANISM = "VALIDATED_MECHANISM"
VALIDATED_CLAIM = "VALIDATED_CLAIM"
DESCRIPTIVE = "DESCRIPTIVE"
BLOCKED = "BLOCKED"

SURFACES = ("Hard", "Clay", "Grass")

ATTRIBUTES: dict[str, dict] = {
    "serve_dominance": {
        "description": (
            "Hold-adjacent serve strength: mean of whichever of "
            "{charting service-point win rate, serve_return_profiles.py's "
            "match-aggregate serve_strength} are available for (entity_id, window)."
        ),
        "entity": "player",
        "ingredients": ["charting_svc_win_rate", "match_agg_serve_strength"],
        "formula": "mean(available of [charting_svc_win_rate, match_agg_serve_strength])",
        "status": DESCRIPTIVE,
        "floor": {"charting_svc_n": 1000},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "return_strength": {
        "description": (
            "Return strength: mean of whichever of {charting return-point win "
            "rate, serve_return_profiles.py's match-aggregate return_strength} "
            "are available for (entity_id, window)."
        ),
        "entity": "player",
        "ingredients": ["charting_return_win_rate", "match_agg_return_strength"],
        "formula": "mean(available of [charting_return_win_rate, match_agg_return_strength])",
        "status": DESCRIPTIVE,
        "floor": {"charting_return_n": 1000},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "pressure_serve": {
        "description": (
            "Break-point serve delta vs the player's own baseline serve-win "
            "rate (bp_save_rate - baseline), REUSED verbatim from "
            "pressure_claims.py's snapshot -- the same computation backing "
            "H1's replicated break-point-serve-dip mechanism."
        ),
        "entity": "player",
        "ingredients": ["charting_bp_save_rate", "charting_baseline_serve_win_rate"],
        "formula": "bp_save_rate - baseline",
        "status": VALIDATED_MECHANISM,
        "floor": {"n_bp_faced": 200},
        "weight_ledger_family": "tennis_pressure_serve_mechanism",
    },
    "second_serve_reliability": {
        "description": (
            "Second-serve point win rate (charting is_second_serve split); "
            "first-serve win rate carried as a same-window ingredient for context."
        ),
        "entity": "player",
        "ingredients": ["charting_second_serve_win_rate", "charting_first_serve_win_rate"],
        "formula": "second_serve_win_rate",
        "status": DESCRIPTIVE,
        "floor": {"first_serve_n": 300, "second_serve_n": 300},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
    "rally_tolerance": {
        "description": "Rally-length-conditioned performance -- NOT BUILT.",
        "entity": "player",
        "ingredients": [],
        "formula": None,
        "status": BLOCKED,
        "floor": {},
        "weight_ledger_family": None,
        "reason": (
            "no usable rally-length signal in either point corpus: "
            "charting_points.rally_length is 100% null by design (verified "
            "this session); slam_points.rally is 78.9% null and the "
            "missingness is not declared random -- neither clears a floor "
            "worth setting."
        ),
    },
    "surface_splits": {
        "description": (
            "Career-only serve/return win rate by surface, joined via "
            "charting-m/w-matches.csv's own Surface column keyed on the same "
            "match_id charting_points.parquet uses (100% coverage, verified). "
            "Emits 6 concrete attribute rows: surface_splits_{serve,return}_"
            "{Hard,Clay,Grass}."
        ),
        "entity": "player",
        "ingredients": ["charting_serve_win_rate_by_surface", "charting_return_win_rate_by_surface"],
        "formula": "serve_won/serve_n (or return_won/return_n) grouped by surface, career window only",
        "status": DESCRIPTIVE,
        "floor": {"n": 300},
        "weight_ledger_family": "tennis_profile_descriptive",
    },
}

# surface_splits concrete attribute names, generated from the one family entry
# above (plain loop -- not a runtime formula engine).
for _direction in ("serve", "return"):
    for _surface in SURFACES:
        ATTRIBUTES[f"surface_splits_{_direction}_{_surface}"] = {
            **{k: v for k, v in ATTRIBUTES["surface_splits"].items() if k != "description"},
            "description": f"Career {_direction} win rate on {_surface} (see surface_splits family entry above).",
        }
del ATTRIBUTES["surface_splits"]  # family entry stays documentation-only; concrete rows are the 6 above


def concrete_attributes() -> list[str]:
    """All attribute names that build_profiles.py actually writes rows for (excludes BLOCKED)."""
    return [name for name, spec in ATTRIBUTES.items() if spec["status"] != BLOCKED]


def blocked_attributes() -> dict[str, str]:
    """attribute_name -> reason, for the ones registered but never built."""
    return {name: spec["reason"] for name, spec in ATTRIBUTES.items() if spec["status"] == BLOCKED}
