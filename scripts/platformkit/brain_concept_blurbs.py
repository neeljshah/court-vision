"""
brain_concept_blurbs.py -- one-line, person-free, no-edge descriptions for the
~60 concept folders that repeat across every sport in the organized brain.

These are CATEGORY descriptions (what kind of intelligence the folder holds),
never stats or predictions -- so they are safe to render in any index and stay
true regardless of the underlying corpus. Used by brain_folder_indexes (folder +
sport index purpose lines) and brain_enrich (child descriptions).

    from brain_concept_blurbs import blurb
    blurb("Mechanisms")  -> "How decided-by drivers co-occur / condition ..."
"""
from __future__ import annotations

# folder name -> one-line category description (ASCII, no edge/$ claims)
BLURBS: dict[str, str] = {
    "AdaptabilityVersatility": "How styles flex across roles, lineups and contexts.",
    "AdjustmentSpeed": "How fast tactics change after a punch or a run.",
    "AnticipationReads": "Reading cues early -- pre-snap / pre-pitch / pre-rotation.",
    "Archetypes": "Person-free role/style archetypes and their tendencies.",
    "ChainSequences": "Multi-step action chains and how they resolve.",
    "ClosingExecution": "Late-game / closing-time execution patterns.",
    "ConversionEfficiency": "Turning chances into outcomes per unit of input.",
    "DeceptionDisguise": "Disguise, misdirection and concealed intent.",
    "DecisionQuality": "Quality of the choice under realized constraints.",
    "DefensiveSchemes": "Defensive structures, coverages and their counters.",
    "DisciplineControl": "Fouls, errors, restraint and self-control.",
    "Drivers": "What decides outcomes -- the primary decided-by factors.",
    "DuelOutcomes": "One-on-one / matchup duel resolutions.",
    "EfficiencyCurves": "How efficiency scales with volume, load and context.",
    "Environment": "Venue, travel, altitude, weather and surroundings.",
    "ErrorCascades": "How one mistake compounds into a sequence.",
    "ExperienceComposure": "Poise, nerve and big-moment composure.",
    "FormDynamics": "Streaks, slumps and short-horizon form.",
    "GamePhases": "How play differs by phase / quarter / inning / set.",
    "InGameAdaptation": "Mid-game adjustment and counter-adjustment.",
    "InitiationProfiles": "Who/what starts the action and how.",
    "LeadManagement": "Protecting, extending or surrendering a lead.",
    "MatchupConcepts": "Structural matchup ideas and leverage points.",
    "MatchupExploitation": "Targeting and attacking a specific weakness.",
    "Mechanisms": "How decided-by drivers co-occur and condition on context.",
    "MomentumSwings": "Runs, shifts and momentum reversals.",
    "OfficialAdaptation": "Adapting to how a game is being officiated.",
    "OfficiatingDynamics": "Officiating tendencies and their effects.",
    "OpponentScouting": "Scouting tendencies and predictable patterns.",
    "PossessionControl": "Owning the ball / tempo / the run of play.",
    "PredictabilityTendencies": "How predictable a style or call sheet is.",
    "PressureResponse": "Performance under high-leverage pressure.",
    "ProgressionDynamics": "How advantage builds or decays through a possession.",
    "PsychologicalWarfare": "Mental edges, intimidation and rattling.",
    "RecoveryResilience": "Bouncing back after adversity or a deficit.",
    "Reference": "Reference tables: seasons, leagues, surfaces, scouting.",
    "ResourceAllocation": "Spending energy, fouls, timeouts and personnel.",
    "RiskProfiles": "Aggression vs caution and the risk taken.",
    "RosterConstruction": "How a roster/lineup is built and balanced.",
    "RoutineConsistency": "Repeatability and routine-driven stability.",
    "Schemes": "Named offensive/defensive schemes and counters.",
    "ShotProfiles": "Shot / attempt selection and location mix.",
    "Situational": "Context-specific situations and their handling.",
    "SpaceCreation": "Creating and using space / separation.",
    "SpacingGeometry": "Spatial geometry of formations and spacing.",
    "SpecialSituations": "Set pieces and special teams / situations.",
    "StartQuality": "Quality of starts -- first quarter / first innings.",
    "StatSignatures": "Realized box-stat signatures that separate outcomes.",
    "SubArchetypes": "Finer-grained sub-types within an archetype.",
    "Tactics": "Tactical plans and in-possession / out-of-possession ideas.",
    "TechniqueMechanics": "Technical mechanics of an action.",
    "TempoControl": "Dictating and controlling pace.",
    "TempoVariation": "Changing speeds to unsettle an opponent.",
    "ThreatBalance": "Balancing multiple threats so none can be sold out on.",
    "TransitionDynamics": "Transition between offense and defense.",
    "Trends": "Season-over-season style and value trends.",
    "VenueTravelEffects": "Home/away, travel and scheduling effects.",
    "VolatilityProfiles": "Outcome variance and boom/bust tendencies.",
    "WorkloadFatigue": "Minutes, pitch counts, load and fatigue.",
    "ZoneControl": "Controlling specific zones / areas of the field.",
}

_FALLBACK = "Person-free intelligence notes for this concept (calibration, not edge)."


def blurb(folder_name: str) -> str:
    """One-line description for a concept folder; safe generic fallback."""
    return BLURBS.get(folder_name.lstrip("_"), _FALLBACK)
