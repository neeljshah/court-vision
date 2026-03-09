"""
CoordinateWriter: Batch-insert TrackedObject records to tracking_coordinates.

Buffers tracked objects in memory and flushes to PostgreSQL in configurable
batches. Uses parameterized SQL with cursor.executemany() — never string
formatting — to prevent SQL injection.

Phase 1 scope: player_id is always NULL. Track IDs are not yet mapped to
player records; that join is Phase 2 feature-engineering work.
"""
from typing import List

from tracking.database import get_connection
from tracking.tracker import TrackedObject


class CoordinateWriter:
    """Buffers and bulk-inserts tracked coordinates to PostgreSQL.

    Usage::

        writer = CoordinateWriter(game_id=game_id)
        for frame results:
            writer.write_batch(tracked_objects)
        writer.flush()  # commit any remaining buffered rows
    """

    _INSERT_SQL = """
        INSERT INTO tracking_coordinates
            (game_id, player_id, frame_number, timestamp_ms,
             x, y, velocity_x, velocity_y, speed, direction_degrees,
             object_type, confidence)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    def __init__(self, game_id: str, batch_size: int = 500) -> None:
        """
        Args:
            game_id: UUID of the game being processed. Written to every row.
            batch_size: Number of TrackedObject rows to buffer before an
                        automatic flush to the database.
        """
        self.game_id = game_id
        self.batch_size = batch_size
        self._buffer: List[TrackedObject] = []

    def write_batch(self, tracked_objects: List[TrackedObject]) -> None:
        """Add tracked objects to the buffer; flush automatically if full.

        Args:
            tracked_objects: List of TrackedObject instances from ObjectTracker.
        """
        self._buffer.extend(tracked_objects)
        if len(self._buffer) >= self.batch_size:
            self._flush_buffer()

    def flush(self) -> None:
        """Commit any remaining buffered rows to the database."""
        if self._buffer:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Execute a bulk INSERT for all rows currently in the buffer.

        Uses cursor.executemany() with parameterized %s placeholders.
        player_id is always None in Phase 1 — track IDs are not yet mapped
        to the players dimension table.
        """
        rows = [
            (
                self.game_id,
                None,                        # player_id — NULL in Phase 1
                obj.frame_number,
                obj.timestamp_ms,
                obj.cx,                      # x coordinate
                obj.cy,                      # y coordinate
                obj.velocity_x,
                obj.velocity_y,
                obj.speed,
                obj.direction_degrees,
                obj.object_type,
                obj.confidence,
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
