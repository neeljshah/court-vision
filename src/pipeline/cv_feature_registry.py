"""
cv_feature_registry.py — Tracks which player-games have CV features available.

Stores cv_features rows in the SQLite/PostgreSQL database and exposes
has_cv_features() so prop models can decide whether to include the CV
feature group.

Public API
----------
    register(player_id, game_id, features_dict) -> None
    has_cv_features(player_id, game_id)          -> bool
    get_cv_features(player_id, game_id)          -> Dict[str, float]
    list_games_with_cv()                         -> List[str]
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# In-memory cache to avoid redundant DB queries
_cache: Dict[tuple, Dict[str, float]] = {}


def register(
    player_id: int,
    game_id: str,
    features: Dict[str, float],
    db_url: Optional[str] = None,
) -> None:
    """
    Store CV features for a player-game in the database.

    Args:
        player_id: NBA player_id integer.
        game_id:   NBA game_id string.
        features:  Dict of feature_name → float value.
        db_url:    Explicit DB URL (reads DATABASE_URL env var if None).
    """
    if not features:
        return

    key = (player_id, game_id)
    _cache[key] = features

    try:
        from src.data.db import get_connection, execute_batch
        conn = get_connection(db_url)
        rows = [
            (game_id, player_id, fname, float(fval))
            for fname, fval in features.items()
            if fval is not None
        ]
        sql = """
            INSERT OR REPLACE INTO cv_features
                (game_id, player_id, feature_name, feature_value)
            VALUES (?, ?, ?, ?)
        """
        with conn:
            with conn.cursor() as cur:
                execute_batch(cur, sql, rows)
        conn.close()
    except Exception as exc:
        log.debug("cv_feature_registry.register failed (non-fatal): %s", exc)


def register_game(
    game_id: str,
    cv_dict: Dict[int, Dict[str, float]],
    db_url: Optional[str] = None,
) -> int:
    """
    Register all player CV features for a game.

    Args:
        game_id:  NBA game ID.
        cv_dict:  Output of tracking_feature_extractor.extract().
        db_url:   Explicit DB URL (reads DATABASE_URL env var if None).

    Returns:
        Number of player records registered.
    """
    count = 0
    for pid, feats in cv_dict.items():
        register(player_id=int(pid), game_id=game_id,
                 features=feats, db_url=db_url)
        count += 1
    return count


def has_cv_features(
    player_id: int,
    game_id: str,
    db_url: Optional[str] = None,
) -> bool:
    """
    Return True if CV features exist for this player-game.

    Args:
        player_id: NBA player_id integer.
        game_id:   NBA game_id string.
        db_url:    Explicit DB URL.

    Returns:
        bool
    """
    if (player_id, game_id) in _cache:
        return bool(_cache[(player_id, game_id)])

    try:
        from src.data.db import get_connection
        conn = get_connection(db_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM cv_features "
                "WHERE player_id = ? AND game_id = ?",
                (player_id, game_id),
            )
            row = cur.fetchone()
        conn.close()
        return bool(row and row[0] > 0)
    except Exception:
        return False


def get_cv_features(
    player_id: int,
    game_id: str,
    db_url: Optional[str] = None,
) -> Dict[str, float]:
    """
    Retrieve CV features for a player-game.

    Returns:
        Dict of feature_name → float, empty if not found.
    """
    cached = _cache.get((player_id, game_id))
    if cached is not None:
        return cached

    try:
        from src.data.db import get_connection
        conn = get_connection(db_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT feature_name, feature_value FROM cv_features "
                "WHERE player_id = ? AND game_id = ?",
                (player_id, game_id),
            )
            rows = cur.fetchall()
        conn.close()
        feats = {r[0]: float(r[1]) for r in rows}
        _cache[(player_id, game_id)] = feats
        return feats
    except Exception:
        return {}


def list_games_with_cv(db_url: Optional[str] = None) -> List[str]:
    """
    Return distinct game_ids that have CV features in the DB.
    """
    try:
        from src.data.db import get_connection
        conn = get_connection(db_url)
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT game_id FROM cv_features ORDER BY game_id")
            rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []
