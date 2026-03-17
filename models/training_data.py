"""Training data loaders for all Phase 3 NBA AI models.

Each function accepts an optional game_id to scope queries to a single game
(None = full training set across all games). Returns a pandas DataFrame.

All functions open and close their own DB connection — no leaked connections.
If the query returns no rows, an empty DataFrame with correct column names is
returned and a warning is logged via the module logger.
"""

import logging
import math

import pandas as pd

from tracking.database import get_connection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_BASKET_X = 460
_BASKET_Y = 240


def _maybe_filter(base_sql: str, game_id: str | None, alias: str = "") -> str:
    """Append a WHERE clause scoping to game_id when provided."""
    prefix = f"{alias}." if alias else ""
    if game_id is not None:
        return f"{base_sql} WHERE {prefix}game_id = %(game_id)s"
    return base_sql


def _read(sql: str, params: dict | None, empty_columns: list[str]) -> pd.DataFrame:
    """Execute *sql* with *params*, return DataFrame; return empty DF on no rows."""
    conn = get_connection()
    try:
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()
    if df.empty:
        logger.warning("Query returned 0 rows. Returning empty DataFrame.")
        return pd.DataFrame(columns=empty_columns)
    return df


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_shot_data(game_id: str | None = None) -> pd.DataFrame:
    """Return shot-level features joined with spatial context.

    Columns returned (raw from DB):
        sl.x, sl.y, sl.made, fv.nearest_defender_dist, fv.closing_speed,
        sl.game_id, sl.track_id

    Derived columns (computed in Python):
        shot_angle  – abs(atan2(y - BASKET_Y, x - BASKET_X)) in degrees
        court_zone  – 'paint' | 'midrange' | 'three'
        fatigue_proxy – closing_speed * -1

    Args:
        game_id: Restrict to a single game UUID, or None for all games.

    Returns:
        pd.DataFrame with shot records, or empty DataFrame if no data found.
    """
    sql = """
        SELECT
            sl.x,
            sl.y,
            sl.made::int AS made,
            fv.nearest_defender_dist,
            fv.closing_speed,
            sl.game_id,
            sl.track_id
        FROM shot_logs sl
        JOIN feature_vectors fv
            ON sl.game_id = fv.game_id
            AND sl.frame_number = fv.frame_number
    """
    columns = [
        "x", "y", "made", "nearest_defender_dist", "closing_speed",
        "game_id", "track_id",
        "shot_angle", "court_zone", "fatigue_proxy",
    ]
    params = {"game_id": game_id} if game_id is not None else None
    if game_id is not None:
        sql += " WHERE sl.game_id = %(game_id)s"

    df = _read(sql, params, columns)
    if df.empty:
        return df

    # Derived columns
    df["shot_angle"] = df.apply(
        lambda r: abs(math.degrees(math.atan2(r.y - _BASKET_Y, r.x - _BASKET_X))),
        axis=1,
    )

    def _zone(x: float) -> str:
        if x < 120 or x > 800:
            return "paint"
        if x < 200 or x > 720:
            return "midrange"
        return "three"

    df["court_zone"] = df["x"].apply(_zone)
    df["fatigue_proxy"] = df["closing_speed"] * -1
    return df


def load_possession_data(game_id: str | None = None) -> pd.DataFrame:
    """Return possession-level spatial and momentum features.

    Columns:
        fv.game_id, fv.possession_id, fv.frame_number,
        fv.convex_hull_area, fv.avg_inter_player_dist,
        ms.scoring_run, ms.possession_streak, ms.swing_point
        won (placeholder 0 — real labels deferred to v2)

    The momentum snapshot is matched where segment_id = frame_number // 150
    (5-second segments at 30 fps).

    Args:
        game_id: Restrict to a single game UUID, or None for all games.

    Returns:
        pd.DataFrame with possession features, or empty DataFrame if no data found.
    """
    sql = """
        SELECT
            fv.game_id,
            fv.possession_id,
            fv.frame_number,
            fv.convex_hull_area,
            fv.avg_inter_player_dist,
            ms.scoring_run,
            ms.possession_streak,
            ms.swing_point::int AS swing_point
        FROM feature_vectors fv
        LEFT JOIN momentum_snapshots ms
            ON fv.game_id = ms.game_id
            AND ms.segment_id = fv.frame_number / 150
    """
    columns = [
        "game_id", "possession_id", "frame_number",
        "convex_hull_area", "avg_inter_player_dist",
        "scoring_run", "possession_streak", "swing_point", "won",
    ]
    params = {"game_id": game_id} if game_id is not None else None
    if game_id is not None:
        sql += " WHERE fv.game_id = %(game_id)s"

    df = _read(sql, params, columns)
    if df.empty:
        return df

    df["won"] = 0  # placeholder — real win labels deferred to v2
    return df


def load_momentum_data(game_id: str | None = None) -> pd.DataFrame:
    """Return momentum snapshots with lag features for streak modeling.

    Columns (raw):
        game_id, segment_id, scoring_run, possession_streak,
        swing_point (as int 0/1 — the label), timestamp_ms

    Derived lag features (computed via pandas groupby/shift within game_id):
        scoring_run_prev  – scoring_run shifted by 1 within each game
        streak_delta      – possession_streak - possession_streak.shift(1)

    Args:
        game_id: Restrict to a single game UUID, or None for all games.

    Returns:
        pd.DataFrame with momentum records, or empty DataFrame if no data found.
    """
    sql = """
        SELECT
            game_id,
            segment_id,
            scoring_run,
            possession_streak,
            swing_point::int AS swing_point,
            timestamp_ms
        FROM momentum_snapshots
    """
    columns = [
        "game_id", "segment_id", "scoring_run", "possession_streak",
        "swing_point", "timestamp_ms", "scoring_run_prev", "streak_delta",
    ]
    params = {"game_id": game_id} if game_id is not None else None
    if game_id is not None:
        sql += " WHERE game_id = %(game_id)s"
    sql += " ORDER BY game_id, segment_id"

    df = _read(sql, params, columns[:6])
    if df.empty:
        return pd.DataFrame(columns=columns)

    # Lag features within each game
    df = df.sort_values(["game_id", "segment_id"])
    df["scoring_run_prev"] = df.groupby("game_id")["scoring_run"].shift(1)
    df["streak_delta"] = (
        df["possession_streak"]
        - df.groupby("game_id")["possession_streak"].shift(1)
    )
    return df


def load_player_event_data(game_id: str | None = None) -> pd.DataFrame:
    """Return player-level event data joined with shot outcomes.

    Used to compute player impact metrics: shot made rate per player,
    event type distribution (cut, screen, drift) per player.

    Columns:
        de.track_id, de.game_id, de.event_type, de.confidence,
        sl.made (as int), sl.x, sl.y

    Args:
        game_id: Restrict to a single game UUID, or None for all games.

    Returns:
        pd.DataFrame with player event records, or empty DataFrame if no data found.
    """
    sql = """
        SELECT
            de.track_id,
            de.game_id,
            de.event_type,
            de.confidence,
            sl.made::int AS made,
            sl.x,
            sl.y
        FROM detected_events de
        JOIN shot_logs sl
            ON de.game_id = sl.game_id
            AND de.track_id = sl.track_id
    """
    columns = ["track_id", "game_id", "event_type", "confidence", "made", "x", "y"]
    params = {"game_id": game_id} if game_id is not None else None
    if game_id is not None:
        sql += " WHERE de.game_id = %(game_id)s"

    return _read(sql, params, columns)


def load_lineup_data(game_id: str | None = None) -> pd.DataFrame:
    """Return on-court lineup keys derived from tracking coordinates.

    Reconstructs which players (by track_id) were on-court each frame.
    Aggregates to one row per (game_id, lineup_key) where lineup_key is
    the sorted tuple of 5 track_ids active in the most common frame set.

    Raw columns pulled:
        game_id, frame_number, track_id  (object_type = 'player' only)

    Output columns:
        game_id, lineup_key (tuple of 5 sorted track_ids as str)

    Args:
        game_id: Restrict to a single game UUID, or None for all games.

    Returns:
        pd.DataFrame with lineup records, or empty DataFrame if no data found.
    """
    sql = """
        SELECT
            game_id,
            frame_number,
            track_id
        FROM tracking_coordinates
        WHERE object_type = 'player'
    """
    columns = ["game_id", "lineup_key"]
    params = {"game_id": game_id} if game_id is not None else None
    if game_id is not None:
        sql += " AND game_id = %(game_id)s"

    raw_df = _read(sql, params, ["game_id", "frame_number", "track_id"])
    if raw_df.empty:
        return pd.DataFrame(columns=columns)

    # Aggregate: for each (game_id, frame_number) collect set of track_ids
    grouped = (
        raw_df.groupby(["game_id", "frame_number"])["track_id"]
        .apply(lambda ids: tuple(sorted(ids)))
        .reset_index()
        .rename(columns={"track_id": "lineup_key"})
    )

    # Deduplicate: one row per unique (game_id, lineup_key)
    result = (
        grouped.groupby(["game_id", "lineup_key"])
        .size()
        .reset_index(name="frame_count")
        .drop(columns=["frame_count"])
    )
    return result
