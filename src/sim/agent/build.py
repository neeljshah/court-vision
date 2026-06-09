"""src/sim/agent/build.py — P1.1 Stage-0: build a typed TeamAgent from the live caches.

ROADMAP: D01 §9 Step 2 (build.py — typed clone of TeamModel.from_cache + to_legacy_team_model).
GATE (test_brain_agent_build.py): (1) every SimAgent field mirrors TeamModel.rate[pid] field-by-field
(RED-C5 float equality); (2) seed-locked sim on ``to_legacy_team_model(agent)`` is BYTE-IDENTICAL to a
fresh ``TeamModel.from_cache`` (the Stage-2 cutover path); (3) ``schema.validate(agent)`` passes.

Stage-0 design (D01 §migration): the TeamAgent WRAPS the real TeamModel — ``to_legacy_team_model``
returns that wrapped model, so the cutover is byte-identical BY CONSTRUCTION (no float-drift from a
reconstructed clone, RED-C5). The typed SimAgents are built alongside for the typed interface +
provenance; policy.py (P1.1 next) will route _possession through them at Stage-3.

DEFAULT-OFF: importing/using this module changes no live path; predict_ensemble keeps calling
TeamModel.from_cache until the Stage-2 cutover flag is flipped (D01).  numpy/torch never imported here.
"""
from __future__ import annotations

import os
from typing import Optional

from sim.agent.provenance import built_from_mtimes, stamp, stamp_agent
from sim.agent.schema import LeverPack, SimAgent, TeamAgent

_THIS = os.path.dirname(os.path.abspath(__file__))                 # src/sim/agent
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS)))   # nba-ai-system
_TS = os.path.join(_ROOT, "data", "cache", "team_system")
_SOURCE_PARQUETS = (
    "player_rates.parquet", "player_roles.parquet", "player_ratings.parquet",
    "player_attributes.parquet", "recency_rates.parquet", "assist_network.parquet",
)

_LEGACY_ATTR = "_legacy_team_model"


def _is_present(v) -> bool:
    """True iff v is a real number (not None / NaN) — decides FULL_PBP vs VAULT_PROXY tier."""
    if v is None:
        return False
    try:
        return not (v != v)  # NaN != NaN
    except Exception:
        return True


def _sim_agent(pid: int, r: dict) -> SimAgent:
    """Map one TeamModel.rate[pid] dict to a frozen SimAgent (raw values — no rounding)."""
    return SimAgent(
        pid=int(r.get("pid", pid)),
        name=str(r.get("player", "")),
        team=str(r.get("team", "")),
        use_per_min=r["use_per_min"], shot_share=r["shot_share"], tov_share=r["tov_share"],
        ft_share=r["ft_share"], ft_pct=r["ft_pct"], fg3_rate=r["fg3_rate"], fg3_pct=r["fg3_pct"],
        z_rim=r["z_rim"], z_paint=r["z_paint"], z_mid=r["z_mid"], z_3=r["z_3"],
        fg_rim=r["fg_rim"], fg_paint=r["fg_paint"], fg_mid=r["fg_mid"],
        ast_per_min=r["ast_per_min"], oreb_per_min=r["oreb_per_min"], dreb_per_min=r["dreb_per_min"],
        stl_per_min=r["stl_per_min"], blk_per_min=r["blk_per_min"], pf_per_min=r["pf_per_min"],
        pts_pg=r["pts_pg"], ft_pts_share=r["ft_pts_share"], mpg=r["mpg"],
        # archetype is NOT in TeamModel.rate (lives in player_roles) — Stage-1 enrichment via policy.py
        archetype=str(r.get("archetype", "")),
        creation=r["creation"], self_create=r["self_create"], pm_prop=r["pm_prop"],
        int_d=r["int_d"], perim_d=r["perim_d"], height=r["height"], age_fatigue_w=r["age_fatigue_w"],
        pts_pg_rec=r.get("pts_pg_rec"), reb_pg_rec=r.get("reb_pg_rec"),
        ast_pg_rec=r.get("ast_pg_rec"), mpg_rec=r.get("mpg_rec"),
        assist_feeders={},
    )


def build_team_agent(tri: str, out_ids: Optional[set] = None) -> TeamAgent:
    """Build a typed TeamAgent wrapping ``TeamModel.from_cache(tri, out_ids=out_ids)``.

    All CV_AGENT_* levers default-NEUTRAL (LeverPack defaults) so behaviour is unchanged.
    The wrapped TeamModel is stashed for the byte-identical Stage-2 cutover.
    """
    from sim.basketball_sim import TeamModel  # local import keeps module load light

    tm = TeamModel.from_cache(tri, out_ids=out_ids)

    built_from = built_from_mtimes([os.path.join(_TS, f) for f in _SOURCE_PARQUETS])

    agents, levers, provenance = {}, {}, {}
    for pid, r in tm.rate.items():
        ag = _sim_agent(pid, r)
        agents[pid] = ag
        levers[pid] = LeverPack()
        tier = "FULL_PBP" if _is_present(r.get("pts_pg_rec")) else "VAULT_PROXY"
        # P1.2: real provenance — content_hash (Blake2b) + parquet mtimes filled by the stamper
        provenance[pid] = stamp_agent(ag, tier, built_from)

    team_tier = "FULL_PBP" if any(p.tier == "FULL_PBP" for p in provenance.values()) else "VAULT_PROXY"
    scheme_prov = stamp(team_tier, built_from)

    ta = TeamAgent(
        tri=tm.tri, agents=agents, levers=levers, provenance=provenance, scheme_provenance=scheme_prov,
        pace=tm.pace, ast_rate_on_make=tm.ast_rate_on_make, oreb_per_miss=tm.oreb_per_miss,
        tov_force=tm.tov_force, ft_force=tm.ft_force, def_rtg=tm.def_rtg, ortg=tm.ortg,
        rim_d=tm.rim_d, perim_d=tm.perim_d,
        lineup_ids=list(tm.lineup_ids), assist_net=tm.assist_net,
        player_xfg=dict(tm.player_xfg), mult=dict(tm.mult), pace_mult=tm.pace_mult, lineup_p=tm.lineup_p,
    )
    # Stash the wrapped model for the byte-identical cutover (Stage-2). Not a declared field so it
    # never participates in equality/serialisation; retrieved via to_legacy_team_model().
    object.__setattr__(ta, _LEGACY_ATTR, tm)
    return ta


def to_legacy_team_model(ta: TeamAgent):
    """Return the wrapped TeamModel for the byte-identical Stage-2 cutover.

    predict_ensemble16's constructor switches from ``TeamModel.from_cache(tri)`` to
    ``to_legacy_team_model(build_team_agent(tri))`` — both yield an equivalent model, so the
    seed-locked sim is unchanged (gated, reversible by one import revert).
    """
    legacy = getattr(ta, _LEGACY_ATTR, None)
    if legacy is None:  # built without the stash (e.g. a future pure-typed path) — rebuild
        from sim.basketball_sim import TeamModel
        legacy = TeamModel.from_cache(ta.tri)
    return legacy
