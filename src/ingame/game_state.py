"""Typed, mutable, numpy-backed GameState — the SINGLE authority for in-game state.

ROADMAP PHASE: P3.1 (In-Game State Engine — D04 ⊕ D06 merged, per ARCHITECTURE §3).

GATE (must pass before ``CV_INGAME_STATE`` flag may flip ON):
  1. Leak-free / truncation-invariance: replaying a full PBP stream then reading
     this object must equal ``state_featurizer.featurize_game`` at that event for
     every shared field (extends ``tests/test_ingame_leak_free.py``).
  2. Between-poll drift instrumentation: every ``resync()`` call logs the
     distribution of ``|incremental − snapshot|`` so systematic feed bias cannot
     hide between poll boundaries (RED-B Attack 8).
  3. Round-trip: ``from_snapshot(to_snapshot(gs))`` is identity for every fixture.

DESIGN DECISIONS (ARCHITECTURE §3 + RED-B Attack 2 resolution):
  - ONE superset: D04's per-period splits (``q_pts``/``q_min``) + D06's four-factor
    team counters (``home_fgm``/``fga``/``ftm``/``fg3a`` + away) + ``on_court`` bool
    arrays + pace fields.  Neither the frozen D04 variant nor the D11 variant is used.
  - MUTABLE + numpy-backed: D06's choice.  A frozen dataclass forces ``dataclasses.
    replace`` (deep-copies the whole ``players`` dict) per event — unacceptable at
    220 poss/game on the hot path.
  - ``apply_event`` returns ``list[int]`` of changed ``player_id`` values and mutates
    in place; it is O(changed_pids), never a full-array scan.
  - ``prior_projection`` (the Bayesian prior) is FROZEN at tip in the ``ServeTable``
    (D06 §2.1 ``proj`` array) and NEVER recomputed during ``resync()`` — this is the
    guard against the co-fit-prior leak (RED-B Attack 4).
  - numpy is lazy-imported inside functions so module load is safe with no heavy deps.

DEFAULT-OFF: this module is never imported by any live path unless ``CV_INGAME_STATE``
is set to a truthy value.  When the flag is OFF, ``live_engine.project_from_snapshot``
runs exactly as today — byte-identical.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (mirrors state_featurizer.py values — kept local so this module
# has zero import from the featurizer at module-load time).
# ---------------------------------------------------------------------------
REG_GAME_LEN_SEC: int = 2880   # 48 min in seconds
BONUS_FOULS: int = 5           # team fouls in period that trigger bonus
STAT_COLS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
STAT_IDX: Dict[str, int] = {s: i for i, s in enumerate(STAT_COLS)}


# ---------------------------------------------------------------------------
# Clock parsing (P3.1 — fills the from_snapshot clock TODO).
# Kept consistent with game_state_events._elapsed: reg periods 720s, OT 300s.
# ---------------------------------------------------------------------------

def _parse_clock_remaining_sec(clock: Any) -> Optional[float]:
    """Parse a clock value into seconds-remaining-in-the-current-period, or None.

    Accepts: numeric seconds (int/float); ``"MM:SS"`` / ``"M:SS"`` strings (the live
    snapshot form); ISO-8601 ``"PT07M24.00S"`` (the CDN feed form). Returns ``None``
    for an absent / empty / unparseable value so the caller can fall back to tip-off
    defaults (this is what keeps a clock-less snapshot byte-identical to pre-P3.1).
    """
    if clock is None:
        return None
    if isinstance(clock, (int, float)):
        return max(0.0, float(clock))
    s = str(clock).strip()
    if not s:
        return None
    su = s.upper()
    if su.startswith("PT"):  # ISO-8601 duration, e.g. PT07M24.00S
        import re
        m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?$", su)
        if not m or (m.group(1) is None and m.group(2) is None):
            return None
        mins = float(m.group(1)) if m.group(1) else 0.0
        secs = float(m.group(2)) if m.group(2) else 0.0
        return mins * 60.0 + secs
    if ":" in s:  # MM:SS
        parts = s.split(":")
        try:
            return float(parts[0]) * 60.0 + float(parts[1])
        except (ValueError, IndexError):
            return None
    try:  # bare numeric string
        return max(0.0, float(s))
    except ValueError:
        return None


def _clock_fields(snap: Dict[str, Any], period: int) -> Tuple[int, float, float, float]:
    """Return ``(clock_s, game_elapsed_sec, game_remaining_sec, remaining_frac)``.

    Precedence: explicit ``game_elapsed_sec`` / ``game_remaining_sec`` (round-trip from
    ``to_snapshot``) > parsed ``clock_remaining_sec`` / ``clock`` > tip-off defaults
    ``(0, 0.0, REG_GAME_LEN_SEC, 1.0)``. The tip-off default branch preserves the exact
    pre-P3.1 behaviour for any snapshot that carries no clock (existing tests + leak gate).
    """
    if snap.get("game_remaining_sec") is not None or snap.get("game_elapsed_sec") is not None:
        elapsed = float(snap.get("game_elapsed_sec", 0.0) or 0.0)
        rem_raw = snap.get("game_remaining_sec")
        remaining = float(rem_raw) if rem_raw is not None else max(0.0, REG_GAME_LEN_SEC - elapsed)
        clock_s = int(round(float(snap.get("clock_remaining_sec", 0) or 0)))
        return clock_s, elapsed, remaining, min(1.0, max(0.0, remaining / REG_GAME_LEN_SEC))

    raw = snap.get("clock_remaining_sec")
    if raw is None:
        raw = snap.get("clock")
    cr = _parse_clock_remaining_sec(raw)
    if cr is None:
        return 0, 0.0, float(REG_GAME_LEN_SEC), 1.0
    if period <= 4:
        elapsed = max(0.0, (period - 1) * 720.0 + (720.0 - cr))
    else:
        elapsed = max(0.0, 2880.0 + (period - 5) * 300.0 + (300.0 - cr))
    remaining = max(0.0, REG_GAME_LEN_SEC - elapsed)
    return int(round(cr)), elapsed, remaining, min(1.0, max(0.0, remaining / REG_GAME_LEN_SEC))

# ---------------------------------------------------------------------------
# PlayerSuff — per-player accumulated sufficient statistics
# ---------------------------------------------------------------------------

@dataclass
class PlayerSuff:
    """Accumulated sufficient statistics for one player as-of event E.

    Fields are MUTABLE so ``apply_event`` can increment them in place.
    ``q_pts`` / ``q_min`` carry per-period splits needed by the heat-regime
    detector (D04 §2.2).  Arrays are NOT stored here to keep the per-player
    object tiny; the numpy board lives in ``GameState.cur``.
    """

    player_id: int
    team: str                      # "home" | "away"
    min_so_far: float
    on_court: bool
    available: bool                # False if ejected / fouled-out (pf >= 6)
    pf: int                        # personal fouls accumulated
    # per-stat accumulated counts (aligned to STAT_COLS)
    suff: Dict[str, float]         # {pts, reb, ast, fg3m, stl, blk, tov}
    # per-period splits for heat detection (q1, q2, q3)
    q_pts: Tuple[float, ...]       # pts per completed period
    q_min: Tuple[float, ...]       # minutes per completed period


# ---------------------------------------------------------------------------
# GameState — the SINGLE mutable authority
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    """Mutable, numpy-backed superset game-state object (D04 ⊕ D06, ARCHITECTURE §3).

    Field-name set is pinned against:
      - ``rest_of_game_sim.EmpiricalPossessionModel.team_params`` reads:
        ``home_score``, ``away_score``, ``home_poss``, ``away_poss``,
        ``home_fgm``, ``home_fga``, ``home_fg3a``, ``home_ftm``,
        ``away_fgm``, ``away_fga``, ``away_fg3a``, ``away_ftm``,
        ``game_remaining_sec``, ``game_elapsed_sec``, ``total_poss_count``
      - ``state_featurizer.GAME_STATE_FIELDS`` / ``PACE_STATE_FIELDS`` /
        ``PLAYER_STATE_FIELDS`` (for truncation-invariance test compatibility)
      - D04's heat-regime fields: ``q_pts`` / ``q_min`` per player

    The ``prior_projection`` numpy array (shape ``(P, S)``) is the FROZEN
    pregame projection loaded once from ``ServeTable.proj``; it is NEVER updated
    during ``resync()`` — see RED-B Attack 4 mitigation.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    game_id: str
    home_team: str
    away_team: str

    # ------------------------------------------------------------------
    # Clock (3 scalars, updated every event)
    # ------------------------------------------------------------------
    period: int
    clock_s: int                    # seconds remaining within the current period
    game_elapsed_sec: float         # absolute seconds elapsed (0 at tip-off)
    game_remaining_sec: float       # = max(0, REG_GAME_LEN_SEC - game_elapsed_sec) + OT
    remaining_frac: float           # game_remaining_sec / REG_GAME_LEN_SEC (clamped [0,1])

    # ------------------------------------------------------------------
    # Team sufficient stats — ADDITIVE counters; reset between periods where noted
    # ------------------------------------------------------------------
    home_score: int
    away_score: int
    home_poss: int                  # possession count so far (aligned with rest_of_game_sim)
    away_poss: int
    total_poss_count: int           # home_poss + away_poss

    # four-factor numerators (pinned against EmpiricalPossessionModel.team_params)
    home_fgm: int
    home_fga: int
    home_ftm: int
    home_fg3a: int
    away_fgm: int
    away_fga: int
    away_ftm: int
    away_fg3a: int

    # foul state (reset to 0 on period change)
    home_team_fouls_period: int
    away_team_fouls_period: int
    home_in_bonus: bool             # home has committed >= BONUS_FOULS fouls this period
    away_in_bonus: bool

    # pace
    pace_so_far: float              # combined possessions per 48 min (one-team basis)

    # ------------------------------------------------------------------
    # Score context (derived once per event; cheap 2-op update)
    # ------------------------------------------------------------------
    score_margin: int               # home_score - away_score (NEVER fed raw to win-prob)
    score_bucket: int               # bucket index from score_bucket_edges

    # ------------------------------------------------------------------
    # On-court (numpy bool arrays, length P, aligned to pid_index)
    # ------------------------------------------------------------------
    # Lazy-typed as Any to allow numpy at runtime without a top-level import.
    on_court: Any                   # np.ndarray[bool], shape (P,)

    # ------------------------------------------------------------------
    # Per-player numpy boards (P rows, S=7 stat columns, aligned to pid_index)
    # ------------------------------------------------------------------
    cur: Any                        # np.ndarray[float32], shape (P, S) — stat-so-far
    min_so_far: Any                 # np.ndarray[float32], shape (P,)
    pf: Any                         # np.ndarray[int8], shape (P,)

    # FROZEN at tip — NEVER updated during resync() (RED-B Attack 4 guard)
    prior_projection: Any           # np.ndarray[float32], shape (P, S)

    # ------------------------------------------------------------------
    # Per-player rich objects (for heat-regime & availability tracking)
    # ------------------------------------------------------------------
    players: Dict[int, PlayerSuff]  # player_id -> PlayerSuff
    pid_index: Dict[int, int]       # player_id -> row index in cur/min_so_far/pf/on_court

    # ------------------------------------------------------------------
    # Snapshot provenance
    # ------------------------------------------------------------------
    snapshot_point: str             # "endQ1"/"endQ2"/"endQ3"/"midQ*"/"" etc.

    # ------------------------------------------------------------------
    # Drift instrumentation (RED-B Attack 8)
    # ------------------------------------------------------------------
    resync_corrections: List[Dict[str, Any]] = field(default_factory=list)

    # ==================================================================
    # Factory: build from a live snapshot dict
    # ==================================================================

    @classmethod
    def from_snapshot(cls, snap: Dict[str, Any],
                      prior_projection: Optional[Any] = None) -> "GameState":
        """Build a ``GameState`` from a live snapshot dict.

        Args:
            snap: The canonical snapshot dict (same schema as consumed by
                ``live_engine.project_from_snapshot``; keys documented in
                ``D04 §2.1``).
            prior_projection: Optional numpy array of shape ``(P, S)`` — the
                FROZEN pregame projection.  If ``None``, filled with zeros.
                Callers MUST pass the ServeTable-derived array; do NOT compute
                it inside this function (would violate the freeze-at-tip rule).

        Returns:
            A freshly-built ``GameState`` aligned to the players in ``snap``.

        # TODO(P3.1): implement clock parsing via live_factors._parse_clock_remaining
        #   (reuse the existing helper to convert "PT07M24.00S" / "MM:SS" formats).
        # TODO(P3.1): implement four-factor extraction from snap['players'] and
        #   the team-level snap fields; align pid_index to the snap player list.
        # TODO(P3.1): compute score_bucket from score_bucket_edges (load edges from
        #   ServeTable or use a default edge set matching _state_mult_tensor).
        # TODO(P3.1): populate per-player PlayerSuff objects from snap['players'].
        # TODO(P3.1): populate on_court / cur / min_so_far / pf numpy arrays.
        # TODO(P3.1): derive snapshot_point via
        #   period_specific_heads.snapshot_point_for(period, clock_remaining).
        """
        import numpy as np  # lazy import — safe at function level

        # Minimal stub so the object is constructable; executor fills all bodies.
        game_id: str = str(snap.get("game_id", ""))
        home_team: str = str(snap.get("home_team", ""))
        away_team: str = str(snap.get("away_team", ""))
        period: int = int(snap.get("period", 1) or 1)
        home_score: int = int(snap.get("home_score", 0) or 0)
        away_score: int = int(snap.get("away_score", 0) or 0)

        # P3.1: real clock fields (no-op tip-off defaults when the snapshot carries no clock,
        # which preserves the leak-gate / existing-test behaviour exactly).
        clock_s, game_elapsed_sec, game_remaining_sec, remaining_frac = _clock_fields(snap, period)

        score_margin: int = home_score - away_score

        # Player alignment — TODO(P3.1): build from snap['players']
        player_list: List[Dict[str, Any]] = list(snap.get("players", []) or [])
        pid_index: Dict[int, int] = {}
        players: Dict[int, PlayerSuff] = {}
        P: int = max(1, len(player_list))

        for idx, p in enumerate(player_list):
            pid = int(p.get("player_id", 0) or 0)
            pid_index[pid] = idx
            players[pid] = PlayerSuff(
                player_id=pid,
                team=str(p.get("team", "")),
                min_so_far=float(p.get("min_so_far", 0.0) or 0.0),
                on_court=bool(p.get("on_court", False)),
                available=True,
                pf=int(p.get("pf", 0) or 0),
                suff={s: float(p.get(s, 0.0) or 0.0) for s in STAT_COLS},
                q_pts=(
                    float(p.get("pts_q1", 0.0) or 0.0),
                    float(p.get("pts_q2", 0.0) or 0.0),
                    float(p.get("pts_q3", 0.0) or 0.0),
                ),
                q_min=(
                    float(p.get("min_q1", 0.0) or 0.0),
                    float(p.get("min_q2", 0.0) or 0.0),
                    float(p.get("min_q3", 0.0) or 0.0),
                ),
            )

        S: int = len(STAT_COLS)
        cur = np.zeros((P, S), dtype=np.float32)
        min_arr = np.zeros(P, dtype=np.float32)
        pf_arr = np.zeros(P, dtype=np.int8)
        oc_arr = np.zeros(P, dtype=bool)

        # P0.4: fill cur/min_arr/pf_arr/oc_arr from player_list (was a stub returning zeros)
        for _idx, _p in enumerate(player_list):
            for _j, _s in enumerate(STAT_COLS):
                cur[_idx, _j] = float(_p.get(_s, 0.0) or 0.0)
            min_arr[_idx] = float(_p.get("min_so_far", 0.0) or 0.0)
            pf_arr[_idx] = int(_p.get("pf", 0) or 0)
            oc_arr[_idx] = bool(_p.get("on_court", False))

        if prior_projection is None:
            prior_projection = np.zeros((P, S), dtype=np.float32)

        return cls(
            game_id=game_id,
            home_team=home_team,
            away_team=away_team,
            period=period,
            clock_s=clock_s,
            game_elapsed_sec=game_elapsed_sec,
            game_remaining_sec=game_remaining_sec,
            remaining_frac=remaining_frac,
            home_score=home_score,
            away_score=away_score,
            home_poss=int(snap.get("home_poss", 0) or 0),
            away_poss=int(snap.get("away_poss", 0) or 0),
            total_poss_count=int(snap.get("total_poss_count", 0) or 0),
            home_fgm=int(snap.get("home_fgm", 0) or 0),
            home_fga=int(snap.get("home_fga", 0) or 0),
            home_ftm=int(snap.get("home_ftm", 0) or 0),
            home_fg3a=int(snap.get("home_fg3a", 0) or 0),
            away_fgm=int(snap.get("away_fgm", 0) or 0),
            away_fga=int(snap.get("away_fga", 0) or 0),
            away_ftm=int(snap.get("away_ftm", 0) or 0),
            away_fg3a=int(snap.get("away_fg3a", 0) or 0),
            home_team_fouls_period=int(snap.get("home_team_fouls_period", 0) or 0),
            away_team_fouls_period=int(snap.get("away_team_fouls_period", 0) or 0),
            home_in_bonus=bool(snap.get("home_in_bonus", False)),
            away_in_bonus=bool(snap.get("away_in_bonus", False)),
            pace_so_far=float(snap.get("pace_so_far", 0.0) or 0.0),
            score_margin=score_margin,
            score_bucket=0,  # TODO(P3.1): compute from edges
            on_court=oc_arr,
            cur=cur,
            min_so_far=min_arr,
            pf=pf_arr,
            prior_projection=prior_projection,
            players=players,
            pid_index=pid_index,
            snapshot_point=str(snap.get("snapshot_point", "")),
            resync_corrections=[],
        )

    # ==================================================================
    # Serialise / deserialise (for snapshot round-trip test)
    # ==================================================================

    def to_snapshot(self) -> Dict[str, Any]:
        """Serialise the mutable state back to a snapshot-compatible dict.

        Used by the round-trip gate and by ``resync()`` delta computation.

        # TODO(P3.1): emit all fields that ``from_snapshot`` reads so the
        #   round-trip is exact (extend as executor fills in the field set).
        """
        import numpy as np  # lazy import

        snap: Dict[str, Any] = {
            "game_id": self.game_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "period": self.period,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "home_poss": self.home_poss,
            "away_poss": self.away_poss,
            "total_poss_count": self.total_poss_count,
            "home_fgm": self.home_fgm,
            "home_fga": self.home_fga,
            "home_ftm": self.home_ftm,
            "home_fg3a": self.home_fg3a,
            "away_fgm": self.away_fgm,
            "away_fga": self.away_fga,
            "away_ftm": self.away_ftm,
            "away_fg3a": self.away_fg3a,
            "home_team_fouls_period": self.home_team_fouls_period,
            "away_team_fouls_period": self.away_team_fouls_period,
            "home_in_bonus": self.home_in_bonus,
            "away_in_bonus": self.away_in_bonus,
            "game_elapsed_sec": self.game_elapsed_sec,
            "game_remaining_sec": self.game_remaining_sec,
            "pace_so_far": self.pace_so_far,
            "score_margin": self.score_margin,
            "snapshot_point": self.snapshot_point,
            "players": [
                {
                    "player_id": ps.player_id,
                    "team": ps.team,
                    "min_so_far": ps.min_so_far,
                    "on_court": ps.on_court,
                    "pf": ps.pf,
                    **{s: ps.suff[s] for s in STAT_COLS},
                    "pts_q1": ps.q_pts[0] if len(ps.q_pts) > 0 else 0.0,
                    "pts_q2": ps.q_pts[1] if len(ps.q_pts) > 1 else 0.0,
                    "pts_q3": ps.q_pts[2] if len(ps.q_pts) > 2 else 0.0,
                    "min_q1": ps.q_min[0] if len(ps.q_min) > 0 else 0.0,
                    "min_q2": ps.q_min[1] if len(ps.q_min) > 1 else 0.0,
                    "min_q3": ps.q_min[2] if len(ps.q_min) > 2 else 0.0,
                }
                for ps in self.players.values()
            ],
        }
        return snap

    # ==================================================================
    # Incremental event update  (O(changed_pids), hot path)
    # ==================================================================

    def apply_event(self, event: Dict[str, Any]) -> List[int]:
        """Apply one PBP event delta to the mutable state; return changed_pids.

        Contract (D06 §2.3):
          - Touches ONLY the entities named in the event (scorer, fouler, sub).
          - All updates are additive ``+=`` on numpy rows — no full-array scan.
          - A ``sub`` event flips two ``on_court`` bits and two PlayerSuff flags.
          - ``end_period`` zeros both ``*_team_fouls_period`` counters.
          - Clock scalars are SET (not incremented) from the authoritative echo
            carried in the event.
          - Returns the list of ``player_id`` values whose ``cur`` row changed.
            Callers use this to invalidate / re-price only those rows.

        Playoff guard (RED-B, D04 §7):
          AST trust_w is kept at BASE for game_id starting with "004" (playoffs).
          This method does NOT enforce that guard (it lives in bayes_player_update);
          it is noted here for cross-reference.

        Event logic is implemented in game_state_events.apply_event (split for the 300-LOC rule).

        # TODO(P3.1): implement each event type:
        #   "made_fg"   — cur[pid, pts_idx] += pts; home/away_score from echo;
        #                 home/away_fgm += 1; home/away_fga += 1;
        #                 if fg3: away/home_fg3a += 1
        #   "miss_fg"   — fga += 1; (fg3a += 1 if 3PA)
        #   "ft"        — cur[pid, pts_idx] += pts; ftm += 1
        #   "reb"       — cur[pid, reb_idx] += 1
        #   "ast"       — cur[pid, ast_idx] += 1
        #   "stl"       — cur[pid, stl_idx] += 1
        #   "blk"       — cur[pid, blk_idx] += 1
        #   "tov"       — cur[pid, tov_idx] += 1; team tov counter
        #   "foul"      — pf[idx] += 1; team_fouls_period += 1;
        #                 recompute home/away_in_bonus; availability if pf>=6
        #   "sub"       — flip on_court bits for sub_in/sub_out pids;
        #                 update PlayerSuff.on_court
        #   "end_period"— zero home_team_fouls_period + away_team_fouls_period;
        #                 home_in_bonus = away_in_bonus = False; advance period
        #   (unknown)   — log warning, return []
        # TODO(P3.1): update clock scalars (clock_s, game_elapsed_sec,
        #   game_remaining_sec, remaining_frac) from event["clock_remaining_sec"]
        #   and event["period"] using the same arithmetic as state_featurizer.
        # TODO(P3.1): recompute score_margin and score_bucket after score change.
        # TODO(P3.1): update PlayerSuff.suff + q_pts/q_min incrementally.
        # TODO(P3.1): update min_so_far for on-court players from clock delta.
        """
        from ingame.game_state_events import apply_event as _apply_event  # lazy: avoids circular import
        return _apply_event(self, event)

    # ==================================================================
    # Drift guard (RED-B Attack 8 — between-poll instrumentation)
    # ==================================================================

    def resync(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Hard-reset the MUTABLE counters from the authoritative snapshot echo.

        The ``prior_projection`` array is NEVER touched here — it stays frozen
        at tip (RED-B Attack 4 guard).

        Records the delta between the incremental state and the authoritative
        snapshot so callers can analyse the distribution of drift.  Returns
        a correction dict logged to ``self.resync_corrections``.

        # TODO(P3.1): implement full field comparison:
        #   1. For each scalar field (home_score, away_score, period, …):
        #      compute |incremental − snapshot|; log if non-zero.
        #   2. For each numpy row: compare cur[pid_index[pid]] to snapshot player
        #      stats; hard-reset on mismatch.
        #   3. Recompute score_bucket, remaining_frac, home/away_in_bonus.
        #   4. Do NOT recompute prior_projection (frozen at tip).
        #   5. Append correction record to self.resync_corrections.
        # TODO(P3.1): return a Dict with keys:
        #   {"n_scalar_corrections", "n_player_corrections",
        #    "home_score_delta", "away_score_delta", "ts_utc"}
        """
        correction: Dict[str, Any] = {
            "home_score_delta": int(snapshot.get("home_score", 0)) - self.home_score,
            "away_score_delta": int(snapshot.get("away_score", 0)) - self.away_score,
            "n_scalar_corrections": 0,   # TODO(P3.1): count non-zero deltas
            "n_player_corrections": 0,   # TODO(P3.1): count player-row resets
        }
        # Hard-reset scores from authoritative echo (always safe)
        self.home_score = int(snapshot.get("home_score", self.home_score) or self.home_score)
        self.away_score = int(snapshot.get("away_score", self.away_score) or self.away_score)
        self.score_margin = self.home_score - self.away_score
        self.resync_corrections.append(correction)
        logger.debug("resync correction: %s", correction)
        return correction
