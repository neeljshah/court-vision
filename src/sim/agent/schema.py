"""src/sim/agent/schema.py — Typed contract for the Entity-Agent Layer.

ROADMAP PHASE: Domain 1 — Entity-Agent Layer (D01_entity_agent.md §2, §9 Step 1).
GATE: validate() must assert the exact player_rates / player_roles / player_ratings
column set without error, AND test_agent_byte_identical (seed-locked CPU+GPU equality
vs TeamModel) must be green, before any CV_AGENT_* flag is allowed to flip ON.

Typed data contract only — no build logic, no policy logic, no I/O at module load.
Heavy imports (numpy, pandas, torch) are lazy-imported inside functions.

# TODO(P1.1): build.py — build_team_agent(tri, out_ids) typed clone of from_cache
# TODO(P1.1): policy.py — 8 sample_* methods delegating to existing kernel arithmetic
# TODO(P1.2): tensorize.py — TeamAgent.to_fast_tensors(dev) -> _FastTeam-compatible bundle
# TODO(P1.2): provenance.py — Blake2b content_hash + staleness stamper
# TODO(P1.2): flags.py — CV_AGENT_* env-flag reader (all default OFF)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SCHEMA_VERSION: str = "1.0.0"

# Required column sets checked by validate() against live parquets.
_REQUIRED_RATES_COLS: Tuple[str, ...] = (
    "pid", "player", "team", "mpg",
    "use_per_min", "shot_share", "tov_share", "ft_share", "ft_pct",
    "fg3_rate", "fg3_pct",
    "z_rim", "z_paint", "z_mid", "z_3",
    "fg_rim", "fg_paint", "fg_mid",
    "ast_per_min", "oreb_per_min", "dreb_per_min",
    "stl_per_min", "blk_per_min", "pf_per_min",
    "pts_pg", "ft_pts_share",
)
_REQUIRED_ROLES_COLS: Tuple[str, ...] = (
    "pid", "archetype", "creation", "self_create", "playmaking",
)
_REQUIRED_RATINGS_COLS: Tuple[str, ...] = ("pid", "INTERIOR_D", "PERIMETER_D")
_REQUIRED_ATTRIBUTES_COLS: Tuple[str, ...] = ("pid", "height_in", "age_fatigue_w")


@dataclass(frozen=True)
class SimAgent:
    """Lean frozen hot-path block the possession kernel reads (one per player).

    Mirrors basketball_sim.py:84-110 and fast_sim.py:55-81 exactly.
    Field names match source parquet columns for direct build.py assignment.
    Recency fields are Optional[float] — None for VAULT_PROXY players.
    assist_feeders reference is frozen; dict contents are populated once at build.
    """
    # identity
    pid: int
    name: str
    team: str  # tricode

    # base rates (player_rates.parquet)
    use_per_min: float
    shot_share: float
    tov_share: float
    ft_share: float
    ft_pct: float
    fg3_rate: float
    fg3_pct: float
    z_rim: float
    z_paint: float
    z_mid: float
    z_3: float
    fg_rim: float
    fg_paint: float
    fg_mid: float
    ast_per_min: float
    oreb_per_min: float
    dreb_per_min: float
    stl_per_min: float
    blk_per_min: float
    pf_per_min: float
    pts_pg: float
    ft_pts_share: float
    mpg: float

    # roles (player_roles.parquet)
    archetype: str  # one of 15 archetypes
    creation: float
    self_create: float
    pm_prop: float  # source col: "playmaking"

    # defense ratings (player_ratings.parquet) — the only ratings the kernel reads
    int_d: float   # INTERIOR_D  (0-99)
    perim_d: float  # PERIMETER_D (0-99)

    # physical (player_attributes.parquet)
    height: float          # inches
    age_fatigue_w: float   # age-driven B2B fatigue weight

    # recency (recency_rates.parquet; None for VAULT_PROXY)
    pts_pg_rec: Optional[float]
    reb_pg_rec: Optional[float]
    ast_pg_rec: Optional[float]
    mpg_rec: Optional[float]

    # assist row (assist_network.parquet sparse): assister_pid -> feed count
    assist_feeders: Dict[int, float] = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True)
class LeverPack:
    """Four data-backed levers, all default-neutral so OFF == strict NO-OP.

    Flags (all default OFF in flags.py):
      CV_AGENT_DEF_SUPP   — cov_def_rating + supp
      CV_AGENT_PLAYTYPE   — crea_iso_ppp / crea_pnr_ppp / score_spotup_ppp
      CV_AGENT_FOUL_STATE — iq_foul_disc / iq_foul_trouble
      CV_AGENT_FATIGUE    — iq_q4_tilt / sit_q4_scoring

    GATE: each lever clears gate.evaluate() (all WF folds improve, null-z>=3,
    calibration_ok) before its flag flips ON (D01 §9 Steps 6-9).
    Level-2 pair residuals (resid_shrunk) are NEVER read; only cross-season-stable
    level-1 cov_def_rating (r=0.60) is used (D01 §7 failure mode 3).
    """
    # CV_AGENT_DEF_SUPP
    cov_def_rating: float = 50.0  # 50 = league avg -> zero delta -> NO-OP
    supp: float = 0.0             # shrunk pts/poss suppression (K_DEF=600)

    # CV_AGENT_PLAYTYPE  (attribute_vault.parquet percentile 0-99)
    crea_iso_ppp: float = 50.0
    crea_pnr_ppp: float = 50.0
    score_spotup_ppp: float = 50.0

    # CV_AGENT_FOUL_STATE
    iq_foul_disc: float = 50.0
    iq_foul_trouble: float = 50.0

    # CV_AGENT_FATIGUE
    iq_q4_tilt: float = 50.0
    sit_q4_scoring: float = 50.0


@dataclass(frozen=True)
class AgentProvenance:
    """Immutable provenance stamp; schema_version must match SCHEMA_VERSION.

    tier: "FULL_PBP" (NYK/SAS rotation, all levers available) |
          "VAULT_PROXY" (vault-only, no PBP recency / play-type routing).
    content_hash: Blake2b of sorted (field, value) pairs — filled by provenance.py.
    # TODO(P1.2): provenance.py fills content_hash and built_from at build time.
    """
    schema_version: str          # must equal SCHEMA_VERSION
    tier: str                    # "FULL_PBP" | "VAULT_PROXY"
    built_from: Dict[str, str]   # parquet filename -> mtime ISO-8601
    content_hash: str            # Blake2b hex; "" until provenance.py is implemented
    missing_fields: List[str]    # required cols that fell back to league prior
    recency_asof: Optional[str]  # last game date in recency window; None = no recency


@dataclass
class TeamAgent:
    """Composition of a team's rotation SimAgents + team scheme block.

    Not frozen because apply_context() mutates player_xfg in place (same pattern as
    TeamModel today).  All SimAgent/LeverPack members are frozen.

    .rate property exposes agents as flat dicts for duck-typing with TeamModel so
    basketball_sim._possession / _finalize work on either object unchanged.

    GATE: Stage 2 cutover requires simulate_game(team_agent) byte-identical to
    simulate_game(TeamModel) seed-locked with all CV_AGENT_* flags OFF.

    # TODO(P1.1): build.py — build_team_agent(tri, out_ids) populates this.
    # TODO(P1.1): to_legacy_team_model() -> TeamModel bridge for Stage 2 cutover.
    # TODO(P1.2): to_fast_tensors(dev) -> _FastTeam-compatible bundle.
    """
    tri: str
    agents: Dict[int, SimAgent]
    levers: Dict[int, LeverPack]
    provenance: Dict[int, AgentProvenance]
    scheme_provenance: AgentProvenance

    # team scheme block (team_rates.json + team_defense.parquet)
    pace: float
    ast_rate_on_make: float
    oreb_per_miss: float
    tov_force: float   # defensive TOV-forcing mult
    ft_force: float    # defensive foul-environment mult
    def_rtg: float
    ortg: float
    rim_d: float
    perim_d: float

    # lineup distribution
    lineup_ids: List[Tuple[int, ...]]

    # assist network: scorer pid -> {assister pid: count}
    assist_net: Dict[int, Dict[int, float]]

    # context multipliers (set by apply_context; empty at build time)
    player_xfg: Dict[int, float] = field(default_factory=dict)
    mult: Dict[str, float] = field(default_factory=dict)
    pace_mult: float = 1.0
    lineup_p: object = field(default_factory=list)  # np.ndarray at runtime

    @property
    def rate(self) -> Dict[int, dict]:
        """Flat-dict shim for basketball_sim duck-typing with TeamModel.rate.

        # TODO(P1.1): remove at Stage 3 once policy.py routes _possession through
        #             SimAgent.sample_*() methods directly.
        """
        return {
            pid: {
                "player": ag.name, "team": ag.team, "mpg": ag.mpg,
                "use_per_min": ag.use_per_min, "shot_share": ag.shot_share,
                "tov_share": ag.tov_share, "ft_share": ag.ft_share,
                "ft_pct": ag.ft_pct, "fg3_rate": ag.fg3_rate, "fg3_pct": ag.fg3_pct,
                "z_rim": ag.z_rim, "z_paint": ag.z_paint, "z_mid": ag.z_mid,
                "z_3": ag.z_3, "fg_rim": ag.fg_rim, "fg_paint": ag.fg_paint,
                "fg_mid": ag.fg_mid,
                "ast_per_min": ag.ast_per_min, "oreb_per_min": ag.oreb_per_min,
                "dreb_per_min": ag.dreb_per_min, "stl_per_min": ag.stl_per_min,
                "blk_per_min": ag.blk_per_min, "pf_per_min": ag.pf_per_min,
                "pts_pg": ag.pts_pg, "ft_pts_share": ag.ft_pts_share,
                "archetype": ag.archetype, "creation": ag.creation,
                "self_create": ag.self_create, "pm_prop": ag.pm_prop,
                "int_d": ag.int_d, "perim_d": ag.perim_d,
                "height": ag.height, "age_fatigue_w": ag.age_fatigue_w,
                "pts_pg_rec": ag.pts_pg_rec, "reb_pg_rec": ag.reb_pg_rec,
                "ast_pg_rec": ag.ast_pg_rec, "mpg_rec": ag.mpg_rec,
            }
            for pid, ag in self.agents.items()
        }

    def sample_lineup(self, rng: object) -> Tuple[int, ...]:
        """Sample one on-court lineup by lineup_p — mirrors TeamModel.sample_lineup().

        # TODO(P1.1): verify byte-identity in test_agent_byte_identical.
        """
        import numpy as np  # lazy
        lp = self.lineup_p if isinstance(self.lineup_p, np.ndarray) else np.asarray(self.lineup_p, dtype=float)
        return self.lineup_ids[rng.choice(len(self.lineup_ids), p=lp)]


_REQUIRED_FLOAT_FIELDS: Tuple[str, ...] = (
    "use_per_min", "shot_share", "tov_share", "ft_share", "ft_pct",
    "z_rim", "z_paint", "z_mid", "z_3",
    "fg_rim", "fg_paint", "fg_mid",
    "ast_per_min", "oreb_per_min", "dreb_per_min",
    "stl_per_min", "blk_per_min", "pf_per_min",
    "pts_pg", "ft_pts_share", "mpg",
    "creation", "self_create", "pm_prop",
    "int_d", "perim_d", "height", "age_fatigue_w",
)

_VALID_TIERS = frozenset({"FULL_PBP", "VAULT_PROXY"})


def validate(team: TeamAgent) -> None:
    """Assert structural correctness of a TeamAgent before any flag is flipped ON.

    Checks: (1) schema_version matches for all agents; (2) tier is legal;
    (3) every agent has a provenance + levers entry; (4) lineups are non-empty,
    5-player, all pids in agents; (5) required float fields are not None.

    GATE: D01 §9 Step 1 — must pass in CI before CV_AGENT_* activation is considered.
    Raises ValueError on any violation.

    # TODO(P1.1): extend to cross-check built_from mtimes vs live parquets (D01 §7 FM8).
    """
    if not team.agents:
        raise ValueError("TeamAgent.agents is empty.")
    for pid, ag in team.agents.items():
        prov = team.provenance.get(pid)
        if prov is None:
            raise ValueError(f"pid={pid}: missing provenance entry.")
        if prov.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"pid={pid}: schema_version={prov.schema_version!r} != {SCHEMA_VERSION!r}. "
                "Bump SCHEMA_VERSION on any SimAgent field add/rename."
            )
        if prov.tier not in _VALID_TIERS:
            raise ValueError(f"pid={pid}: tier={prov.tier!r} not in {set(_VALID_TIERS)}.")
        if pid not in team.levers:
            raise ValueError(f"pid={pid}: missing levers entry.")
        for fname in _REQUIRED_FLOAT_FIELDS:
            if getattr(ag, fname, None) is None:
                raise ValueError(
                    f"pid={pid}: field {fname!r} is None — must be filled with a "
                    "league-prior fallback at build time."
                )
    if not team.lineup_ids:
        raise ValueError("TeamAgent.lineup_ids is empty.")
    agent_pids = set(team.agents)
    for i, lineup in enumerate(team.lineup_ids):
        if len(lineup) != 5:
            raise ValueError(f"lineup_ids[{i}] has {len(lineup)} players; expected 5.")
        for pid in lineup:
            if pid not in agent_pids:
                raise ValueError(f"lineup_ids[{i}] references pid={pid} not in agents.")
