"""Leak-free intelligence coupling for the possession-outcome simulator.

This module turns each team's OWN prior play-by-play into an as-of-before
"intelligence signature" that the possession-outcome model can consume as a
game-constant (exactly the same injection pattern as ``prior_strength`` in
``src.sim.possession_model.extract_possessions``):

  * OFFENSE playstyle mix   -- from team O's possessions AS OFFENSE in games
    strictly BEFORE this game's date: the empirical outcome-share signature
    (3-point attempt rate, FT-trip rate, turnover rate, points-per-possession,
    tempo). This is O's *style* learned leak-free, not a static atlas snapshot.
  * DEFENSE scheme/coverage -- from team D's possessions AS DEFENSE (i.e. the
    outcome distribution the OPPONENT produced against D) in games strictly
    BEFORE this date: 3PA rate ALLOWED, FT rate ALLOWED, turnovers FORCED,
    points-per-possession ALLOWED, tempo allowed. A drop-coverage / paint-heavy
    defense allows a different shot mix than a switch-everything / pressure
    defense, and this allowance signature is the leak-free proxy for scheme.
  * MATCHUP interactions     -- offense style x defense allowance, so the outcome
    distribution shifts with WHO is playing WHOM (the whole point).

WHY PBP-DERIVED AND NOT THE STATIC ATLASES
------------------------------------------
The ``atlas_*`` / ``defensive_schemes`` parquets are SINGLE 2025-26 snapshots
(``as_of=2026-05-31``, one row per team/player, no per-date breakdown). Applying
a 2025-26 atlas value to a 2022 game would be (a) a future leak and (b) a
season-mismatch. Deriving the same intelligence from each team's OWN games
strictly before the target date is genuinely leak-free and works across every
season in the PBP corpus, so we use that. (Where the atlas-only fields -- e.g.
drop/switch coverage tags -- have no per-date analogue, we capture the same
*effect* via the allowed-shot-mix signature, which is what scheme produces.)

LEAK DISCIPLINE
---------------
``IntelPriorStore.observe(rec_possessions, team_for_side, date)`` is called in
chronological order AFTER ``intel_priors_for`` has been read for that game, so a
target game only ever sees strictly-earlier games. Every emitted value is a pure
function of completed prior games -- no within-game state, no future, no
as-of-today aggregate. The module is PURE (no I/O, no globals); importing it
changes nothing in the serve path.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# League-average anchors for the signature dimensions (season-agnostic constants,
# NOT as-of-today aggregates -> not a leak). Used to (a) shrink thin priors and
# (b) center the matchup-interaction terms so a league-average matchup -> ~0.
LEAGUE_3PAR = 0.36          # share of possessions ending on a 3-pt attempt
LEAGUE_FT_RATE = 0.13       # share of possessions ending on an FT trip
LEAGUE_TOV_RATE = 0.135     # share of possessions ending on a turnover
LEAGUE_PPP = 1.12           # points per possession
LEAGUE_PACE = 99.0          # one team's possessions per 48 min

# Shrinkage strength in "prior possessions": with K possessions of league prior,
# a team needs ~K real possessions before its own rate gets half the weight.
# A team plays ~100 possessions/game, so K=300 ~= 3 games of evidence to half.
SHRINK_K = 300.0

# The intel feature names appended to the possession STATE_FEATURES. They are
# offense-POV (the possession's offense is "off", its opponent is "def").
INTEL_FEATURES: List[str] = [
    # offense playstyle signature (O's own prior offense)
    "off_intel_3par",
    "off_intel_ft_rate",
    "off_intel_tov_rate",
    "off_intel_ppp",
    "off_intel_pace",
    # defense scheme/coverage signature (D's own prior defense = what it allows)
    "def_intel_3par_allowed",
    "def_intel_ft_allowed",
    "def_intel_tov_forced",
    "def_intel_ppp_allowed",
    "def_intel_pace_allowed",
    # matchup interactions (centered so league-avg matchup ~ 0)
    "intel_3par_matchup",
    "intel_ft_matchup",
    "intel_tov_matchup",
    "intel_ppp_matchup",
    "intel_pace_matchup",
]


@dataclass
class _TeamSig:
    """Accumulated counts for one team across prior games (offense + defense)."""
    # AS OFFENSE
    off_poss: float = 0.0
    off_make3: float = 0.0
    off_miss3: float = 0.0
    off_ft: float = 0.0
    off_tov: float = 0.0
    off_pts: float = 0.0
    # AS DEFENSE (what the opponent did against this team)
    def_poss: float = 0.0
    def_make3: float = 0.0
    def_miss3: float = 0.0
    def_ft: float = 0.0
    def_tov: float = 0.0
    def_pts: float = 0.0
    # tempo (possessions/48 averaged over games this team appeared in)
    pace_games: List[float] = field(default_factory=list)


def _shrink(num: float, denom: float, league: float) -> float:
    """Shrink an empirical rate (num/denom) toward ``league`` with SHRINK_K."""
    if denom <= 0:
        return league
    rate = num / denom
    w = denom / (denom + SHRINK_K)
    return w * rate + (1.0 - w) * league


class IntelPriorStore:
    """As-of-before intelligence store built from prior-game possession rows.

    Usage (chronological walk-forward, identical posture to TeamPriorStore):

        store = IntelPriorStore()
        for rec in records_sorted_by_date:          # ascending date
            priors = store.intel_priors_for(off_team, def_team)   # read FIRST
            ...                                       # use for THIS game
            store.observe(possession_rows, home_team, away_team)  # THEN record

    Reading before observing guarantees a game only sees strictly-earlier games.
    """

    def __init__(self) -> None:
        self._sig: Dict[str, _TeamSig] = defaultdict(_TeamSig)

    # -- accumulate a completed game --------------------------------------
    def observe(self, rows: Sequence[Any], home_team: Optional[str],
                away_team: Optional[str]) -> None:
        """Fold one COMPLETED game's possession rows into both teams' signatures.

        ``rows`` are ``PossessionRow`` objects (have ``.off_side`` in
        {'home','away'}, ``.outcome``, ``.points``). ``home_team``/``away_team``
        are the tricodes for this game. Defense for an offense's possession is the
        other team. Tempo = total possessions scaled to 48 min, recorded per game.
        """
        if not home_team or not away_team:
            return
        side_team = {"home": home_team, "away": away_team}
        per_side_poss = {"home": 0, "away": 0}
        for r in rows:
            off_team = side_team.get(getattr(r, "off_side", ""))
            if off_team is None:
                continue
            def_team = away_team if off_team == home_team else home_team
            o = self._sig[off_team]
            d = self._sig[def_team]
            outcome = getattr(r, "outcome", "")
            pts = float(getattr(r, "points", 0) or 0)
            per_side_poss[getattr(r, "off_side")] += 1
            # offense bucket for off_team
            o.off_poss += 1
            o.off_pts += pts
            # defense bucket for def_team (allowed)
            d.def_poss += 1
            d.def_pts += pts
            if outcome == "make_3":
                o.off_make3 += 1; d.def_make3 += 1
            elif outcome == "miss_3":
                o.off_miss3 += 1; d.def_miss3 += 1
            elif outcome == "ft_trip":
                o.off_ft += 1; d.def_ft += 1
            elif outcome == "turnover":
                o.off_tov += 1; d.def_tov += 1
        # tempo: one-team possessions over a full 48 (each side ~ half of total)
        total_poss = per_side_poss["home"] + per_side_poss["away"]
        if total_poss > 0:
            one_team = total_poss / 2.0      # already a full game in this corpus
            self._sig[home_team].pace_games.append(one_team)
            self._sig[away_team].pace_games.append(one_team)

    # -- read an as-of-before matchup signature ---------------------------
    def has_prior(self, off_team: Optional[str], def_team: Optional[str]) -> bool:
        o = self._sig.get(off_team or "")
        d = self._sig.get(def_team or "")
        return bool(o and o.off_poss > 0 and d and d.def_poss > 0)

    def intel_priors_for(self, off_team: Optional[str], def_team: Optional[str]
                         ) -> Optional[Dict[str, float]]:
        """Return the offense-POV INTEL_FEATURES dict for this matchup, or None.

        None when EITHER team has no prior games (the eval then falls back to the
        un-coupled model for that game, so coupling never invents signal).
        """
        if not self.has_prior(off_team, def_team):
            return None
        o = self._sig[off_team]      # type: ignore[index]
        d = self._sig[def_team]      # type: ignore[index]
        return self._signature(o, d)

    # -- pure signature math (also used by the reactivity demo) -----------
    @staticmethod
    def _signature(o: "_TeamSig", d: "_TeamSig") -> Dict[str, float]:
        off_3par = _shrink(o.off_make3 + o.off_miss3, o.off_poss, LEAGUE_3PAR)
        off_ft = _shrink(o.off_ft, o.off_poss, LEAGUE_FT_RATE)
        off_tov = _shrink(o.off_tov, o.off_poss, LEAGUE_TOV_RATE)
        off_ppp = _shrink(o.off_pts, o.off_poss, LEAGUE_PPP)
        off_pace = float(np.mean(o.pace_games)) if o.pace_games else LEAGUE_PACE

        def_3par = _shrink(d.def_make3 + d.def_miss3, d.def_poss, LEAGUE_3PAR)
        def_ft = _shrink(d.def_ft, d.def_poss, LEAGUE_FT_RATE)
        def_tov = _shrink(d.def_tov, d.def_poss, LEAGUE_TOV_RATE)
        def_ppp = _shrink(d.def_pts, d.def_poss, LEAGUE_PPP)
        def_pace = float(np.mean(d.pace_games)) if d.pace_games else LEAGUE_PACE

        # matchup interactions: deviation of offense from league TIMES deviation
        # of defense-allowed from league, so a "3-happy O vs a D that allows 3s"
        # compounds, while "3-happy O vs a D that suppresses 3s" cancels. Centered
        # at 0 for a league-average matchup.
        m_3par = (off_3par - LEAGUE_3PAR) + (def_3par - LEAGUE_3PAR)
        m_ft = (off_ft - LEAGUE_FT_RATE) + (def_ft - LEAGUE_FT_RATE)
        m_tov = (off_tov - LEAGUE_TOV_RATE) + (def_tov - LEAGUE_TOV_RATE)
        m_ppp = (off_ppp - LEAGUE_PPP) + (def_ppp - LEAGUE_PPP)
        m_pace = ((off_pace - LEAGUE_PACE) + (def_pace - LEAGUE_PACE)) / LEAGUE_PACE

        return {
            "off_intel_3par": off_3par,
            "off_intel_ft_rate": off_ft,
            "off_intel_tov_rate": off_tov,
            "off_intel_ppp": off_ppp,
            "off_intel_pace": off_pace,
            "def_intel_3par_allowed": def_3par,
            "def_intel_ft_allowed": def_ft,
            "def_intel_tov_forced": def_tov,
            "def_intel_ppp_allowed": def_ppp,
            "def_intel_pace_allowed": def_pace,
            "intel_3par_matchup": m_3par,
            "intel_ft_matchup": m_ft,
            "intel_tov_matchup": m_tov,
            "intel_ppp_matchup": m_ppp,
            "intel_pace_matchup": m_pace,
        }

    # -- direct construction from explicit rate inputs (for the demo) -----
    @staticmethod
    def signature_from_rates(
        off_3par: float, off_ft: float, off_tov: float, off_ppp: float,
        off_pace: float, def_3par: float, def_ft: float, def_tov: float,
        def_ppp: float, def_pace: float,
    ) -> Dict[str, float]:
        """Build an INTEL_FEATURES dict directly from chosen rates.

        Lets the reactivity demo dial a single style knob (e.g. swap the defense
        from a low-3PA-allowed 'drop' profile to a high one) without re-running
        PBP, and see the simulator react.
        """
        o = _TeamSig(off_poss=1e9, off_make3=off_3par * 1e9, off_miss3=0.0,
                     off_ft=off_ft * 1e9, off_tov=off_tov * 1e9,
                     off_pts=off_ppp * 1e9, pace_games=[off_pace])
        d = _TeamSig(def_poss=1e9, def_make3=def_3par * 1e9, def_miss3=0.0,
                     def_ft=def_ft * 1e9, def_tov=def_tov * 1e9,
                     def_pts=def_ppp * 1e9, pace_games=[def_pace])
        return IntelPriorStore._signature(o, d)
