"""
Fusion layer: entity resolver.

Maps CV tracker slots -> NBA player_game_id using:
  1. NBA API roster as prior (jersey# -> player_id)
  2. Hungarian matching on (jersey_ocr_conf, team_color_conf, minutes_prior)
  3. Falls back to name-distance on player_name if OCR produces a string

Output: slot_to_player_game_id dict and per-slot SourceValue for downstream.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.fusion.source_registry import SourceValue

log = logging.getLogger(__name__)

# ── optional scipy dep ──────────────────────────────────────────────────────
try:
    from scipy.optimize import linear_sum_assignment
    _SCIPY = True
except ImportError:
    _SCIPY = False
    log.warning("scipy not found; falling back to greedy match in entity_resolver")


@dataclass
class RosterEntry:
    """One player on the NBA API roster for this game."""
    player_id: int
    player_name: str
    jersey_number: Optional[int]        # None if unknown
    team_id: int
    team_abbrev: str
    minutes_prior: float = 0.0          # season avg minutes (used as weight)


@dataclass
class TrackObservation:
    """What the CV pipeline saw for one tracker slot."""
    slot: int
    team_abbrev: str
    jersey_number: Optional[int]        # None if OCR failed
    jersey_ocr_conf: float              # 0-1
    team_color_conf: float              # 0-1


@dataclass
class ResolvedPlayer:
    player_id: int
    player_game_id: str                 # "{game_id}_{player_id}"
    player_name: str
    slot: int
    match_method: str                   # "jersey_exact" | "hungarian" | "fallback"
    source_value: SourceValue


class EntityResolver:
    """
    Matches CV tracks to NBA roster entries for a given game.

    Usage
    -----
        resolver = EntityResolver(game_id, roster_entries)
        results  = resolver.resolve(track_observations)
        # results: Dict[int, ResolvedPlayer]  (slot -> ResolvedPlayer)
    """

    def __init__(self, game_id: str, roster: List[RosterEntry]) -> None:
        self.game_id = game_id
        self.roster  = roster
        # index by (team_abbrev, jersey_number) for O(1) exact lookup
        self._jersey_idx: Dict[Tuple[str, int], RosterEntry] = {}
        for entry in roster:
            if entry.jersey_number is not None:
                key = (entry.team_abbrev.upper(), entry.jersey_number)
                self._jersey_idx[key] = entry

    # ── public ────────────────────────────────────────────────────────────

    def resolve(
        self, observations: List[TrackObservation]
    ) -> Dict[int, ResolvedPlayer]:
        """
        Resolve a list of track observations to roster entries.
        Returns mapping slot -> ResolvedPlayer.
        """
        resolved: Dict[int, ResolvedPlayer] = {}
        unmatched_obs: List[TrackObservation] = []

        # Pass 1: exact jersey match
        for obs in observations:
            if obs.jersey_number is not None and obs.jersey_ocr_conf >= 0.60:
                key = (obs.team_abbrev.upper(), obs.jersey_number)
                entry = self._jersey_idx.get(key)
                if entry:
                    resolved[obs.slot] = self._make_resolved(
                        obs, entry, "jersey_exact"
                    )
                    continue
            unmatched_obs.append(obs)

        if not unmatched_obs:
            return resolved

        # Pass 2: Hungarian match on remaining slots vs unused roster entries
        used_ids = {r.player_id for r in resolved.values()}
        remaining_roster = [e for e in self.roster if e.player_id not in used_ids]

        if remaining_roster and unmatched_obs:
            matched = self._hungarian_match(unmatched_obs, remaining_roster)
            for obs, entry in matched:
                resolved[obs.slot] = self._make_resolved(obs, entry, "hungarian")
                unmatched_obs = [o for o in unmatched_obs if o.slot != obs.slot]

        # Pass 3: fallback — low-confidence prior for still-unmatched slots
        for obs in unmatched_obs:
            log.debug("slot %d unresolved after Hungarian; using prior fallback", obs.slot)
            sv = SourceValue.as_prior(None, slot=obs.slot, game_id=self.game_id)
            resolved[obs.slot] = ResolvedPlayer(
                player_id=-1,
                player_game_id=f"{self.game_id}_unknown",
                player_name="unknown",
                slot=obs.slot,
                match_method="fallback",
                source_value=sv,
            )

        return resolved

    # ── private ───────────────────────────────────────────────────────────

    def _make_resolved(
        self, obs: TrackObservation, entry: RosterEntry, method: str
    ) -> ResolvedPlayer:
        """Build a ResolvedPlayer with appropriate SourceValue confidence."""
        ocr_conf  = obs.jersey_ocr_conf
        color_conf = obs.team_color_conf
        combined  = round((ocr_conf * 0.6 + color_conf * 0.4), 4)

        sv = SourceValue.from_cv(
            value=entry.player_id,
            ocr_conf=combined,
            slot=obs.slot,
            jersey=obs.jersey_number,
            match_method=method,
        )
        return ResolvedPlayer(
            player_id=entry.player_id,
            player_game_id=f"{self.game_id}_{entry.player_id}",
            player_name=entry.player_name,
            slot=obs.slot,
            match_method=method,
            source_value=sv,
        )

    def _hungarian_match(
        self,
        observations: List[TrackObservation],
        roster: List[RosterEntry],
    ) -> List[Tuple[TrackObservation, RosterEntry]]:
        """
        Build cost matrix and solve assignment problem.

        Cost = 1 - similarity(obs, entry)
        Similarity uses jersey soft match + team color + minutes prior.
        """
        n_obs   = len(observations)
        n_rost  = len(roster)
        cost    = np.ones((n_obs, n_rost), dtype=float)

        for i, obs in enumerate(observations):
            for j, entry in enumerate(roster):
                if obs.team_abbrev.upper() != entry.team_abbrev.upper():
                    cost[i, j] = 2.0   # cross-team penalty
                    continue
                # jersey soft match: 1 if same number, 0.5 if obs None, 0 if differ
                if obs.jersey_number is None:
                    jersey_sim = 0.5
                elif obs.jersey_number == entry.jersey_number:
                    jersey_sim = 1.0
                else:
                    jersey_sim = 0.0

                # minutes prior normalised to [0,1] within roster
                max_min = max((e.minutes_prior for e in roster), default=1.0) or 1.0
                min_sim = entry.minutes_prior / max_min

                sim = (
                    jersey_sim       * obs.jersey_ocr_conf  * 0.55
                    + obs.team_color_conf                   * 0.25
                    + min_sim                               * 0.20
                )
                cost[i, j] = 1.0 - sim

        if _SCIPY:
            row_ind, col_ind = linear_sum_assignment(cost)
            pairs = [
                (observations[r], roster[c])
                for r, c in zip(row_ind, col_ind)
                if cost[r, c] < 1.5   # skip cross-team / hopeless assignments
            ]
        else:
            pairs = self._greedy_match(observations, roster, cost)

        return pairs

    @staticmethod
    def _greedy_match(
        observations: List[TrackObservation],
        roster: List[RosterEntry],
        cost: np.ndarray,
    ) -> List[Tuple[TrackObservation, RosterEntry]]:
        """Greedy fallback when scipy unavailable."""
        used_obs:   set[int] = set()
        used_rost:  set[int] = set()
        pairs:      List[Tuple[TrackObservation, RosterEntry]] = []

        flat = sorted(
            ((cost[i, j], i, j) for i in range(cost.shape[0]) for j in range(cost.shape[1])),
            key=lambda x: x[0],
        )
        for c, i, j in flat:
            if c >= 1.5:
                break
            if i in used_obs or j in used_rost:
                continue
            pairs.append((observations[i], roster[j]))
            used_obs.add(i)
            used_rost.add(j)

        return pairs


# ── convenience: build roster from NBA API boxscore dict ─────────────────

def roster_from_boxscore(game_id: str, boxscore: dict) -> List[RosterEntry]:
    """
    Parse a nba_api BoxScoreTraditionalV2 result dict into RosterEntry list.

    Args:
        game_id:   NBA game ID string.
        boxscore:  Raw dict returned by BoxScoreTraditionalV2.get_dict().
    """
    entries: List[RosterEntry] = []
    try:
        result_sets = boxscore.get("resultSets", [])
        player_set  = next((r for r in result_sets if r["name"] == "PlayerStats"), None)
        if player_set is None:
            log.warning("No PlayerStats in boxscore for game %s", game_id)
            return entries
        headers = player_set["headers"]
        idx = {h: i for i, h in enumerate(headers)}
        for row in player_set["rowSet"]:
            jersey_raw = row[idx.get("PLAYER_JERSEY_ID", -1)]
            try:
                jersey = int(jersey_raw) if jersey_raw is not None else None
            except (ValueError, TypeError):
                jersey = None
            min_str = row[idx.get("MIN", -1)] or "0:00"
            try:
                mins = float(min_str.split(":")[0])
            except Exception:
                mins = 0.0
            entries.append(RosterEntry(
                player_id    = int(row[idx["PLAYER_ID"]]),
                player_name  = str(row[idx["PLAYER_NAME"]]),
                jersey_number = jersey,
                team_id      = int(row[idx["TEAM_ID"]]),
                team_abbrev  = str(row[idx["TEAM_ABBREVIATION"]]),
                minutes_prior = mins,
            ))
    except Exception as exc:
        log.error("roster_from_boxscore failed: %s", exc)
    return entries
