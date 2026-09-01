"""Fail-closed runtime availability registry for declared signal columns.

Only signals explicitly registered as RUNTIME may enter a live inference
manifest.  Producers declare their columns through an ``OUTPUT_COLUMNS``
constant; missing not-yet-built producers are tolerated during discovery, but
an installed producer must exactly match the rows registered for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Iterable, Mapping


RUNTIME = "RUNTIME"
TRAIN = "TRAIN"
TRAIN_PRIOR = "TRAIN_PRIOR"
VALID_TAGS = frozenset((RUNTIME, TRAIN, TRAIN_PRIOR))
OUTPUT_COLUMNS_NAMES = ("OUTPUT_COLUMNS", "RUNTIME_COLUMNS")


class RuntimeRegistryError(ValueError):
    """Raised when the registry or a live feature manifest is unsafe."""


@dataclass(frozen=True)
class SignalRegistration:
    """Runtime contract metadata for one signal column."""

    tag: str
    producing_module: str
    as_of_rule: str
    source: str
    license: str
    added_on: str
    frozen_prior_last_game_as_of: str | None = None


VENUE_TABLE = "scripts.platformkit.signals.venue_table"
SCHEDULE_CONTEXT = "scripts.platformkit.signals.schedule_context"
MARKET_MICRO = "scripts.platformkit.signals.market_micro_asof"
MARKET_COHERENCE = "scripts.platformkit.signals.market_coherence"
TEMPO_PBP = "scripts.platformkit.signals.tempo_pbp_asof"
OFFICIALS = "scripts.platformkit.signals.officials_asof"

PRODUCER_MODULES = (
    VENUE_TABLE,
    SCHEDULE_CONTEXT,
    MARKET_MICRO,
    MARKET_COHERENCE,
    TEMPO_PBP,
    OFFICIALS,
)


def _rows(
    module: str, tag: str, as_of_rule: str, source: str, names: tuple[str, ...]
) -> dict[str, SignalRegistration]:
    return {
        name: SignalRegistration(
            tag=tag,
            producing_module=module,
            as_of_rule=as_of_rule,
            source=source,
            license="internal",
            added_on="2026-08-31",
        )
        for name in names
    }


# The entries mirror N10-N14's declared output columns.  N14 priors are TRAIN
# because an assignment may only be observed post-game; runtime_available itself
# is available from the snapshot check.
REGISTRY: Mapping[str, SignalRegistration] = {
    **_rows(
        VENUE_TABLE,
        RUNTIME,
        "static venue reference known before schedule publication",
        "official venue directories",
        (
            "venue_id",
            "team_ids",
            "lat",
            "lon",
            "elevation_m",
            "tz_name",
            "home_plate_to_center_bearing_deg",
            "capacity",
        ),
    ),
    **_rows(
        SCHEDULE_CONTEXT,
        RUNTIME,
        "schedule state strictly before the game start",
        "schedule plus static venue table",
        (
            "rest_differential",
            "games_in_last_7_days_diff",
            "travel_km_since_last_game",
            "timezone_shift_signed",
            "circadian_hour_at_start",
            "altitude_delta_m",
        ),
    ),
    **_rows(
        MARKET_MICRO,
        RUNTIME,
        "own tick archive truncated at the declared pregame horizon",
        "owned line-history archive",
        (
            "price_drift_T6_to_T1",
            "cross_book_dispersion",
            "quote_cadence_seconds",
            "realized_vol_of_prob",
            "jump_count_pregame",
        ),
    ),
    **_rows(
        MARKET_COHERENCE,
        RUNTIME,
        "same-timestamp market snapshot at the declared pregame horizon",
        "owned line-history archive",
        ("overround_level", "shin_z_estimate", "related_market_coherence"),
    ),
    **_rows(
        TEMPO_PBP,
        RUNTIME,
        "strictly prior play-by-play events at the decision timestamp",
        "hoopR or nba_api play-by-play",
        (
            "possession_seconds_p25_asof",
            "possession_seconds_p50_asof",
            "possession_seconds_p75_asof",
            "late_clock_share_asof",
            "transition_possession_rate_asof",
            "tempo_by_score_state_asof",
            "garbage_time_exposure_prior_asof",
        ),
    ),
    **_rows(
        OFFICIALS,
        TRAIN,
        "historical prior; assignment must be captured before the horizon",
        "official assignment and historical officiating logs",
        ("crew_foul_rate_prior", "umpire_strike_zone_prior"),
    ),
    **_rows(
        OFFICIALS,
        RUNTIME,
        "assignment-snapshot availability at the decision horizon",
        "official assignment snapshot",
        ("runtime_available",),
    ),
}


def validate_registry(registry: Mapping[str, SignalRegistration] | None = None) -> None:
    """Raise unless every registry row has complete, internally valid metadata."""
    active = REGISTRY if registry is None else registry
    if not isinstance(active, Mapping) or not active:
        raise RuntimeRegistryError("runtime registry is missing or empty")
    for signal_id, row in active.items():
        if not isinstance(signal_id, str) or not signal_id:
            raise RuntimeRegistryError("runtime registry contains an invalid signal id")
        if not isinstance(row, SignalRegistration):
            raise RuntimeRegistryError("runtime registry row is invalid: " + signal_id)
        if row.tag not in VALID_TAGS:
            raise RuntimeRegistryError("runtime registry tag is invalid: " + signal_id)
        required = (row.producing_module, row.as_of_rule, row.source, row.license, row.added_on)
        if not all(isinstance(value, str) and value for value in required):
            raise RuntimeRegistryError("runtime registry metadata is incomplete: " + signal_id)
        if row.tag == TRAIN_PRIOR and not row.frozen_prior_last_game_as_of:
            raise RuntimeRegistryError("TRAIN_PRIOR lacks frozen prior date: " + signal_id)


def declared_output_columns(module_name: str) -> frozenset[str] | None:
    """Load an installed producer's declared columns, or None when absent."""
    try:
        module: ModuleType = import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        raise
    declarations = [
        getattr(module, name)
        for name in OUTPUT_COLUMNS_NAMES
        if hasattr(module, name)
    ]
    if not declarations:
        raise RuntimeRegistryError(
            "producer lacks output-column declaration: " + module_name
        )
    columns = declarations[0]
    if any(declaration != columns for declaration in declarations[1:]):
        raise RuntimeRegistryError("producer output-column declarations disagree: " + module_name)
    if not isinstance(columns, (tuple, list, frozenset)) or not all(
        isinstance(column, str) and column for column in columns
    ):
        raise RuntimeRegistryError("producer has invalid OUTPUT_COLUMNS: " + module_name)
    if len(columns) != len(set(columns)):
        raise RuntimeRegistryError("producer has duplicate OUTPUT_COLUMNS: " + module_name)
    return frozenset(columns)


def registered_columns(module_name: str) -> frozenset[str]:
    """Return every registry column owned by one producer module."""
    validate_registry()
    return frozenset(
        signal_id
        for signal_id, row in REGISTRY.items()
        if row.producing_module == module_name
    )


def assert_registered_producers_match() -> dict[str, frozenset[str] | None]:
    """Check every installed N10-N14 producer against the declared registry."""
    validate_registry()
    discovered: dict[str, frozenset[str] | None] = {}
    for module_name in PRODUCER_MODULES:
        columns = declared_output_columns(module_name)
        discovered[module_name] = columns
        if columns is not None and columns != registered_columns(module_name):
            raise RuntimeRegistryError("producer columns are unregistered: " + module_name)
    return discovered


def assert_runtime_safe(columns: Iterable[str]) -> None:
    """Raise unless every requested column is explicitly registered RUNTIME."""
    validate_registry()
    for column in columns:
        row = REGISTRY.get(column)
        if row is None:
            raise RuntimeRegistryError("unregistered runtime column: " + repr(column))
        if row.tag != RUNTIME:
            raise RuntimeRegistryError("non-runtime column: " + column + " (" + row.tag + ")")
