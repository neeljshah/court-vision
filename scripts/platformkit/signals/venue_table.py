"""Static, RUNTIME-available venue reference data for live schedule signals.

The visible schedule corpus in this worktree is NBA-only.  The table therefore
covers its 30 distinct home-team identifiers without making unavailable video or
post-game data part of an inference-time feature.  ``date`` is accepted by
``lookup`` so callers can keep one interface when dated venue histories are
added; current rows have no expiry.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Optional, Tuple, Union


RUNTIME = "RUNTIME"
RUNTIME_COLUMNS = (
    "venue_id", "team_ids", "lat", "lon", "elevation_m", "tz_name",
    "home_plate_to_center_bearing_deg", "capacity",
)


@dataclass(frozen=True)
class VenueRow:
    """A static reference row whose every field is available at runtime."""

    venue_id: str = field(metadata={"availability": RUNTIME})
    team_ids: Tuple[int, ...] = field(metadata={"availability": RUNTIME})
    lat: float = field(metadata={"availability": RUNTIME})
    lon: float = field(metadata={"availability": RUNTIME})
    elevation_m: float = field(metadata={"availability": RUNTIME})
    tz_name: str = field(metadata={"availability": RUNTIME})
    home_plate_to_center_bearing_deg: Optional[float] = field(
        metadata={"availability": RUNTIME}
    )
    capacity: int = field(metadata={"availability": RUNTIME})


# Each current NBA row cites the official NBA arena directory as its source.
# https://www.nba.com/arenas
VENUES: Tuple[VenueRow, ...] = (
    VenueRow("state_farm_arena", (1610612737,), 33.7573, -84.3963, 320.0, "America/New_York", None, 18118),  # https://www.nba.com/hawks/arena
    VenueRow("td_garden", (1610612738,), 42.3662, -71.0621, 3.0, "America/New_York", None, 19156),  # https://www.nba.com/celtics/tickets/arena
    VenueRow("barclays_center", (1610612751,), 40.6826, -73.9754, 12.0, "America/New_York", None, 17732),  # https://www.nba.com/nets/arena
    VenueRow("spectrum_center", (1610612766,), 35.2251, -80.8392, 229.0, "America/New_York", None, 19077),  # https://www.nba.com/hornets/arena
    VenueRow("united_center", (1610612741,), 41.8807, -87.6742, 181.0, "America/Chicago", None, 20917),  # https://www.nba.com/bulls/arena
    VenueRow("rocket_arena", (1610612739,), 41.4965, -81.6882, 199.0, "America/New_York", None, 19432),  # https://www.nba.com/cavaliers/arena
    VenueRow("american_airlines_center", (1610612742,), 32.7905, -96.8103, 131.0, "America/Chicago", None, 19200),  # https://www.nba.com/mavericks/arena
    VenueRow("ball_arena", (1610612743,), 39.7487, -105.0077, 1609.0, "America/Denver", None, 19520),  # https://www.nba.com/nuggets/arena
    VenueRow("little_caesars_arena", (1610612765,), 42.3411, -83.0553, 183.0, "America/Detroit", None, 20491),  # https://www.nba.com/pistons/arena
    VenueRow("chase_center", (1610612744,), 37.7680, -122.3877, 5.0, "America/Los_Angeles", None, 18064),  # https://www.nba.com/warriors/arena
    VenueRow("toyota_center", (1610612745,), 29.7508, -95.3621, 15.0, "America/Chicago", None, 18055),  # https://www.nba.com/rockets/arena
    VenueRow("gainbridge_fieldhouse", (1610612754,), 39.7639, -86.1555, 218.0, "America/Indiana/Indianapolis", None, 17923),  # https://www.nba.com/pacers/arena
    VenueRow("intuit_dome", (1610612746,), 33.9456, -118.3387, 29.0, "America/Los_Angeles", None, 18000),  # https://www.nba.com/clippers/arena
    VenueRow("crypto_com_arena", (1610612747,), 34.0430, -118.2673, 89.0, "America/Los_Angeles", None, 19067),  # https://www.nba.com/lakers/arena
    VenueRow("kaseya_center", (1610612748,), 25.7814, -80.1870, 2.0, "America/New_York", None, 19600),  # https://www.nba.com/heat/arena
    VenueRow("fiserv_forum", (1610612749,), 43.0451, -87.9173, 188.0, "America/Chicago", None, 17341),  # https://www.nba.com/bucks/arena
    VenueRow("target_center", (1610612750,), 44.9795, -93.2761, 254.0, "America/Chicago", None, 18978),  # https://www.nba.com/timberwolves/arena
    VenueRow("smoothie_king_center", (1610612740,), 29.9490, -90.0821, 2.0, "America/Chicago", None, 16867),  # https://www.nba.com/pelicans/arena
    VenueRow("madison_square_garden", (1610612752,), 40.7505, -73.9934, 18.0, "America/New_York", None, 19812),  # https://www.nba.com/knicks/arena
    VenueRow("paycom_center", (1610612760,), 35.4634, -97.5151, 366.0, "America/Chicago", None, 18203),  # https://www.nba.com/thunder/arena
    VenueRow("kia_center", (1610612753,), 28.5392, -81.3839, 30.0, "America/New_York", None, 18846),  # https://www.nba.com/magic/arena
    VenueRow("wells_fargo_center", (1610612755,), 39.9012, -75.1720, 12.0, "America/New_York", None, 20478),  # https://www.nba.com/sixers/arena
    VenueRow("footprint_center", (1610612756,), 33.4457, -112.0712, 331.0, "America/Phoenix", None, 17071),  # https://www.nba.com/suns/arena
    VenueRow("moda_center", (1610612757,), 45.5316, -122.6668, 8.0, "America/Los_Angeles", None, 19980),  # https://www.nba.com/blazers/arena
    VenueRow("golden_1_center", (1610612758,), 38.5802, -121.4997, 9.0, "America/Los_Angeles", None, 17608),  # https://www.nba.com/kings/arena
    VenueRow("frost_bank_center", (1610612759,), 29.4270, -98.4375, 199.0, "America/Chicago", None, 18418),  # https://www.nba.com/spurs/arena
    VenueRow("scotiabank_arena", (1610612761,), 43.6435, -79.3791, 76.0, "America/Toronto", None, 19800),  # https://www.nba.com/raptors/arena
    VenueRow("delta_center", (1610612762,), 40.7683, -111.9011, 1288.0, "America/Denver", None, 18306),  # https://www.nba.com/jazz/arena
    VenueRow("capital_one_arena", (1610612764,), 38.8981, -77.0209, 7.0, "America/New_York", None, 20356),  # https://www.nba.com/wizards/arena
    VenueRow("fedexforum", (1610612763,), 35.1382, -90.0506, 103.0, "America/Chicago", None, 17794),  # https://www.nba.com/grizzlies/arena
)

_BY_TEAM = {team_id: row for row in VENUES for team_id in row.team_ids}


def lookup(team_id: int, as_of: Union[date, datetime, str]) -> VenueRow:
    """Return the venue known for ``team_id`` on ``as_of``; raise for unknown teams."""
    if isinstance(as_of, str):
        date.fromisoformat(as_of[:10])
    elif isinstance(as_of, datetime):
        _ = as_of.date()
    elif not isinstance(as_of, date):
        raise TypeError("as_of must be a date, datetime, or ISO date string")
    try:
        return _BY_TEAM[int(team_id)]
    except (KeyError, TypeError, ValueError) as exc:
        raise KeyError("no runtime venue row for team_id=%r" % (team_id,)) from exc


def great_circle_km(a: VenueRow, b: VenueRow) -> float:
    """Return the spherical great-circle distance between two static venues."""
    if a == b:
        return 0.0
    lat1, lon1, lat2, lon2 = map(radians, (a.lat, a.lon, b.lat, b.lon))
    h = sin((lat2 - lat1) / 2.0) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2.0) ** 2
    return 6371.0088 * 2.0 * asin(sqrt(h))


def runtime_columns_are_tagged() -> bool:
    """True when every VenueRow column has the required RUNTIME availability tag."""
    return all(item.metadata.get("availability") == RUNTIME for item in fields(VenueRow))


__all__ = ["RUNTIME", "RUNTIME_COLUMNS", "VENUES", "VenueRow", "lookup",
           "great_circle_km", "runtime_columns_are_tagged"]
