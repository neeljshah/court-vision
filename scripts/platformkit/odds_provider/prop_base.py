"""scripts.platformkit.odds_provider.prop_base -- player-prop normalized schema.

Player PROPS are a DIFFERENT shape than the team-moneyline OddsEvent (one row =
one player + one stat + one over/under line), so this module defines a PARALLEL
record, PropLine, NOT a reuse of OddsEvent. Every prop provider parses its native
payload into a list of PropLine (or returns the UNAVAILABLE sentinel from .base).

Pricing: over_price / under_price are DECIMAL odds (> 1.0) when the source quotes a
real two-sided price (payout_type "sportsbook"). DFS pick'em products that quote a
flat profit-multiple rather than a true two-sided line set both prices to None and
payout_type "dfs_pickem" -- we never fabricate a price we cannot honestly derive.

canon_stat() normalizes source stat labels to our cross-book vocabulary so the same
stat from different books lines up. An unknown label passes through unchanged (so
nothing is silently dropped) -- callers can see the raw label and add a mapping.

No network in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable

# Reuse the honest unavailable sentinel + guard from the team-odds base.
from .base import is_unavailable, unavailable  # noqa: F401  (re-exported)

# Canonical stat vocabulary. Keys are LOWERCASED raw source labels; values are our
# canonical names. Covers the PrizePicks / Underdog World Cup (soccer) surface and
# the MLB player-prop surface (values are domains/mlb MLB_CANON keys).
_STAT_CANON: Dict[str, str] = {
    # Shots
    "shots": "Shots",
    "shots attempted": "Shots",
    "shot attempts": "Shots",
    "total shots": "Shots",
    "shots on target": "Shots On Target",
    "shots on goal": "Shots On Target",
    "sog": "Shots On Target",
    # Fouls
    "fouls": "Fouls",
    "fouls committed": "Fouls",
    "fouls for": "Fouls",
    "fouls drawn": "Fouls Drawn",
    "fouls against": "Fouls Drawn",
    "fouls suffered": "Fouls Drawn",
    # Cards / discipline
    "cards": "Cards",
    "card": "Cards",
    "bookings": "Cards",
    # Defensive
    "tackles": "Tackles",
    "tackles won": "Tackles",
    # Creation / scoring
    "assists": "Assists",
    "goal+assist": "Goal+Assist",
    "goals + assists": "Goal+Assist",
    "goals+assists": "Goal+Assist",
    "goal + assist": "Goal+Assist",
    "goals": "Goals",
    "anytime goal": "Goals",
    "offsides": "Offsides",
    "offside": "Offsides",
    # Passing
    "passes attempted": "Passes Attempted",
    "passes": "Passes Attempted",
    "pass attempts": "Passes Attempted",
    "passes completed": "Passes Completed",
    # Keeper
    "goalie saves": "Saves",
    "saves": "Saves",
    "keeper saves": "Saves",
    # ---- MLB (probed Underdog sport_id "MLB" + PrizePicks league "MLB",
    # 2026-06-18). Values are domains/mlb/player_rates_mlb.MLB_CANON keys.
    # Batter stats:
    "hits": "Hits",
    "total bases": "Total Bases",
    "rbis": "RBIs",
    "rbi": "RBIs",
    "runs": "Runs",
    "home runs": "Home Runs",
    # Bare "Walks" / "Batter Walks" on a batter is the engine's batter Walks key;
    # pitcher walks are the distinct "Walks Allowed" label below.
    "walks": "Walks",
    "batter walks": "Walks",
    "hitter walks": "Walks",
    # Batter strikeouts: DFS books split between "Batter" and "Hitter" wording.
    "batter strikeouts": "Batter Strikeouts",
    "hitter strikeouts": "Batter Strikeouts",
    "stolen bases": "Stolen Bases",
    # "Hits + Runs + RBIs" (Underdog spaced) and "Hits+Runs+RBIs" (PrizePicks)
    # both normalize via whitespace-collapse to the same key after lowercasing;
    # we map both spellings explicitly so a label change on either book is safe.
    "hits + runs + rbis": "Hits+Runs+RBIs",
    "hits+runs+rbis": "Hits+Runs+RBIs",
    # Pitcher stats. Bare "Strikeouts" on a pitcher line == "Pitcher Strikeouts";
    # batter punchouts always carry "Batter"/"Hitter" so bare maps to pitcher.
    "strikeouts": "Pitcher Strikeouts",
    "pitcher strikeouts": "Pitcher Strikeouts",
    # Pitching outs: Underdog "Pitching Outs", others "Pitcher Outs" / "Outs".
    "outs": "Outs",
    "pitching outs": "Outs",
    "pitcher outs": "Outs",
    "earned runs": "Earned Runs",
    "earned runs allowed": "Earned Runs",
    "hits allowed": "Hits Allowed",
    "walks allowed": "Walks Allowed",
    # NOT MAPPED (no engine MLB_CANON key -- pass through raw, never guessed):
    #   Fantasy Points, Pitcher/Hitter Fantasy Score, Singles, Doubles,
    #   Pitches Thrown, Plate Appearances, Pitcher Strikeouts (Combo),
    #   and all "1st Inn."/"1st Inning" first-inning splits.
}


def canon_stat(raw: Optional[str]) -> Optional[str]:
    """Map a raw source stat label to our canonical name.

    Case / whitespace insensitive. An unrecognized label is returned UNCHANGED
    (never dropped, never guessed) so callers can surface and map it. None/empty
    pass through as given.
    """
    if raw is None:
        return None
    key = " ".join(str(raw).strip().lower().split())
    if not key:
        return raw
    return _STAT_CANON.get(key, raw)


@dataclass
class PropLine:
    """One normalized player-prop over/under line.

    over_price / under_price are DECIMAL odds (> 1.0) or None when the source does
    not quote a true two-sided price (a flat DFS pick'em multiple -> None + the
    payout_type flag below). stat is the CANONICAL name (see canon_stat).
    """

    sport: str
    event_id: str
    match: Optional[str]
    player: str
    team: Optional[str]
    stat: str
    line: float
    over_price: Optional[float] = None
    under_price: Optional[float] = None
    payout_type: str = "dfs_pickem"  # "dfs_pickem" | "sportsbook"
    source: str = ""
    as_of: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sport": self.sport,
            "event_id": self.event_id,
            "match": self.match,
            "player": self.player,
            "team": self.team,
            "stat": self.stat,
            "line": self.line,
            "over_price": self.over_price,
            "under_price": self.under_price,
            "payout_type": self.payout_type,
            "source": self.source,
            "as_of": self.as_of,
        }


@runtime_checkable
class PropProvider(Protocol):
    """A normalized player-prop source.

    fetch_props(sport) returns either a list[PropLine] on success or the
    UNAVAILABLE sentinel dict (see unavailable()) when the source is down /
    disabled / has no rows for the sport. It must NEVER raise and NEVER fabricate.
    """

    name: str

    def fetch_props(self, sport: str) -> Union[List[PropLine], Dict[str, str]]:
        ...


__all__ = [
    "PropLine",
    "PropProvider",
    "canon_stat",
    "unavailable",
    "is_unavailable",
]
