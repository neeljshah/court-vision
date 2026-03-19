"""
CoordinateWriter: buffers TrackedObject records and bulk-inserts to PostgreSQL.

Uses ON CONFLICT DO NOTHING so the pipeline is safe to re-run (resume).
Stores both pixel coordinates (x, y) and court-feet coordinates (x_ft, y_ft).
"""
from typing import List

from legacy.tracking.database import get_connection
from legacy.tracking.tracker import TrackedObject


class CoordinateWriter:
    """Buffers and bulk-inserts tracked coordinates to PostgreSQL."""

    _INSERT_SQL = """
        INSERT INTO tracking_coordinates
            (game_id, player_id, track_id, frame_number, timestamp_ms,
             x, y, x_ft, y_ft,
             bbox_x1, bbox_y1, bbox_x2, bbox_y2,
             velocity_x, velocity_y, speed, direction_degrees,
             object_type, confidence, team)
        VALUES
            (%s, %s, %s, %s, %s,
             %s, %s, %s, %s,
             %s, %s, %s, %s,
             %s, %s, %s, %s,
             %s, %s, %s)
        ON CONFLICT (game_id, frame_number, track_id) DO NOTHING
    """

    def __init__(self, game_id: str, batch_size: int = 500) -> None:
        self.game_id = game_id
        self.batch_size = batch_size
        self._buffer: List[TrackedObject] = []

    def write_batch(self, tracked_objects: List[TrackedObject]) -> None:
        self._buffer.extend(tracked_objects)
        if len(self._buffer) >= self.batch_size:
            self._flush_buffer()

    def flush(self) -> None:
        if self._buffer:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        rows = [
            (
                self.game_id,
                None,           # player_id — phase 1: not yet mapped
                obj.track_id,
                obj.frame_number,
                int(obj.timestamp_ms),
                obj.cx,
                obj.cy,
                obj.x_ft,
                obj.y_ft,
                obj.bbox[0], obj.bbox[1], obj.bbox[2], obj.bbox[3],
                obj.velocity_x,
                obj.velocity_y,
                obj.speed,
                obj.direction_degrees,
                obj.object_type,
                obj.confidence,
                obj.team,
            )
            for obj in self._buffer
        ]

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(self._INSERT_SQL, rows)
            conn.commit()
        finally:
            conn.close()

        self._buffer = []
