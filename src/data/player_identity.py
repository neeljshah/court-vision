"""
player_identity.py — Persistence layer for named player identity mapping.

Stores the OCR-confirmed jersey-number-to-player associations from a clip
into PostgreSQL, and back-fills the tracking_frames table with named player_id
values once identities are confirmed.

Phase 2 component — depends on src/data/db.py and database/schema.sql.

Functions
---------
persist_identity_map   Insert or update one confirmed slot in player_identity_map.
update_tracking_frames Patch player_id in tracking_frames from player_identity_map.
load_identity_map      Load existing confirmed identities for a (game_id, clip_id).
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import psycopg2

from .db import get_connection

logger = logging.getLogger(__name__)


def persist_identity_map(
    db_url: str,
    game_id: str,
    clip_id: str,
    slot: int,
    jersey_number: Optional[int],
    player_id: Optional[int],
    confirmed_frame: int,
    confidence: float,
) -> bool:
    """
    Insert or update one confirmed tracker slot in player_identity_map.

    Uses ON CONFLICT (game_id, clip_id, tracker_slot) DO UPDATE so the
    function is idempotent — safe to call multiple times per clip.

    Args:
        db_url:          psycopg2-compatible connection string.
        game_id:         NBA API game_id (e.g. '0022301234').
        clip_id:         UUID string identifying the clip.
        slot:            Tracker slot index (0-9).
        jersey_number:   Jersey number confirmed by OCR (None if unknown).
        player_id:       NBA API player_id (None until roster lookup resolves it).
        confirmed_frame: Frame index at which the identity was confirmed.
        confidence:      Confidence score for this confirmation (0.0-1.0).

    Returns:
        True on success, False on psycopg2 error (logs a warning).
    """
    sql = """
        INSERT INTO player_identity_map
            (game_id, clip_id, tracker_slot, jersey_number, player_id,
             confirmed_frame, confidence)
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s)
        ON CONFLICT (game_id, clip_id, tracker_slot) DO UPDATE
            SET jersey_number   = EXCLUDED.jersey_number,
                player_id       = EXCLUDED.player_id,
                confidence      = EXCLUDED.confidence,
                confirmed_frame = EXCLUDED.confirmed_frame
    """
    try:
        conn = get_connection(db_url)
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (game_id, clip_id, slot, jersey_number, player_id,
                 confirmed_frame, confidence),
            )
        conn.commit()
        conn.close()
        return True
    except psycopg2.Error as e:
        logger.warning("[player_identity] DB error: %s", e)
        return False


def update_tracking_frames(
    db_url: str,
    game_id: str,
    clip_id: str,
) -> int:
    """
    Back-fill player_id in tracking_frames using confirmed identities.

    Runs an UPDATE ... FROM join between tracking_frames and
    player_identity_map for the given (game_id, clip_id) pair, patching
    player_id on every row whose tracker_player_id matches a confirmed slot.

    Args:
        db_url:  psycopg2-compatible connection string.
        game_id: NBA API game_id.
        clip_id: UUID string identifying the clip.

    Returns:
        Number of tracking_frames rows updated.
    """
    sql = """
        UPDATE tracking_frames tf
        SET player_id = pim.player_id
        FROM player_identity_map pim
        WHERE tf.game_id         = pim.game_id
          AND tf.clip_id         = pim.clip_id::uuid
          AND tf.tracker_player_id = pim.tracker_slot
          AND tf.game_id         = %s
          AND pim.clip_id        = %s::uuid
          AND pim.player_id      IS NOT NULL
    """
    conn = get_connection(db_url)
    with conn.cursor() as cur:
        cur.execute(sql, (game_id, clip_id))
        rows_updated = cur.rowcount
    conn.commit()
    conn.close()
    return rows_updated


def load_identity_map(
    db_url: str,
    game_id: str,
    clip_id: str,
) -> Dict[int, int]:
    """
    Load confirmed tracker-slot-to-player_id mapping for a clip.

    Only returns slots where player_id IS NOT NULL (i.e. fully resolved).

    Args:
        db_url:  psycopg2-compatible connection string.
        game_id: NBA API game_id.
        clip_id: UUID string identifying the clip.

    Returns:
        Dict mapping tracker_slot (int) → player_id (int).
        Empty dict if no confirmed identities exist.
    """
    sql = """
        SELECT tracker_slot, player_id
        FROM player_identity_map
        WHERE game_id  = %s
          AND clip_id  = %s::uuid
          AND player_id IS NOT NULL
    """
    conn = get_connection(db_url)
    with conn.cursor() as cur:
        cur.execute(sql, (game_id, clip_id))
        rows = cur.fetchall()
    conn.close()
    return {int(slot): int(pid) for slot, pid in rows}
