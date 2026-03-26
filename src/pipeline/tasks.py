"""
tasks.py -- Phase C3: Celery task definitions for batch game processing.

Pipeline chain per game:
  track_game     -> GPU: CV tracker -> events JSON
  enrich_game    -> async: NBA API enrichment (outcomes, lineups)
  extract_features -> CPU: feature engineering
  run_inference  -> fast GPU: model predictions
  store_to_db    -> PostgreSQL write

Usage:
    # Start worker (requires Redis running)
    celery -A src.pipeline.tasks worker --loglevel=info --concurrency=4

    # Monitor (requires flower)
    celery -A src.pipeline.tasks flower

    # Submit a single game
    from src.pipeline.tasks import process_game_chain
    process_game_chain.delay("path/to/game.mp4", "0022401234")

    # Redis on Windows: use Redis Cloud free tier OR WSL + redis-server
    # Redis URL: set REDIS_URL env var (default: redis://localhost:6379/0)
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

# ── Celery app setup ──────────────────────────────────────────────────────────

try:
    from celery import Celery, chain

    _REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    app = Celery(
        "nba_ai_tasks",
        broker=_REDIS_URL,
        backend=_REDIS_URL,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_acks_late=True,           # re-queue on worker crash
        worker_prefetch_multiplier=1,  # one task at a time per worker (GPU constraint)
        task_track_started=True,
        result_expires=86400,          # results expire after 24h
    )
    _CELERY_AVAILABLE = True
except ImportError:
    _CELERY_AVAILABLE = False
    app = None

_DATA_DIR    = os.path.join(PROJECT_DIR, "data")
_EVENTS_DIR  = os.path.join(_DATA_DIR, "events")
_MODELS_DIR  = os.path.join(_DATA_DIR, "models")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _events_path(game_id: str) -> str:
    os.makedirs(_EVENTS_DIR, exist_ok=True)
    return os.path.join(_EVENTS_DIR, f"{game_id}_events.json")


def _is_already_processed(game_id: str) -> bool:
    """Check PostgreSQL if game already processed (fast path: check events file)."""
    if os.path.exists(_events_path(game_id)):
        return True
    try:
        from src.data.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM games WHERE game_id = %s LIMIT 1", (game_id,)
                )
                return cur.fetchone() is not None
    except Exception:
        return False


# ── Task: track_game ──────────────────────────────────────────────────────────

if _CELERY_AVAILABLE:
    @app.task(
        name="tasks.track_game",
        bind=True,
        max_retries=2,
        default_retry_delay=60,
    )
    def track_game(self, video_path: str, game_id: str) -> dict:
        """
        GPU stage: Run CV tracker on game video, save events JSON.

        Args:
            video_path: Path to .mp4 file
            game_id:    NBA Stats game ID (e.g. "0022401234")

        Returns:
            {"game_id": str, "events_path": str, "n_frames": int, "n_possessions": int}
        """
        if _is_already_processed(game_id):
            existing = _events_path(game_id)
            return {"game_id": game_id, "events_path": existing, "skipped": True}

        try:
            from src.pipeline.unified_pipeline import run_game_pipeline
        except ImportError as e:
            raise self.retry(exc=e, countdown=30)

        try:
            result = run_game_pipeline(
                video_path=video_path,
                game_id=game_id,
                output_events=_events_path(game_id),
            )
            return {
                "game_id":       game_id,
                "events_path":   _events_path(game_id),
                "n_frames":      result.get("n_frames", 0),
                "n_possessions": result.get("n_possessions", 0),
            }
        except Exception as exc:
            raise self.retry(exc=exc, countdown=60)


# ── Task: enrich_game ─────────────────────────────────────────────────────────

if _CELERY_AVAILABLE:
    @app.task(
        name="tasks.enrich_game",
        bind=True,
        max_retries=3,
        default_retry_delay=30,
    )
    def enrich_game(self, track_result: dict) -> dict:
        """
        Async NBA API enrichment: fetch outcomes, lineups, PBP for a game.

        Args:
            track_result: Output from track_game task

        Returns:
            {"game_id": str, "enriched": bool, "shots_linked": int}
        """
        game_id = track_result.get("game_id", "")
        if not game_id:
            return {"game_id": game_id, "enriched": False, "error": "missing game_id"}

        try:
            from src.data.nba_enricher import enrich_game as nba_enrich
            result = nba_enrich(game_id)
            return {
                "game_id":      game_id,
                "events_path":  track_result.get("events_path", ""),
                "enriched":     True,
                "shots_linked": result.get("shots_linked", 0),
                "pbp_rows":     result.get("pbp_rows", 0),
            }
        except Exception as exc:
            raise self.retry(exc=exc, countdown=30)


# ── Task: extract_features ────────────────────────────────────────────────────

if _CELERY_AVAILABLE:
    @app.task(
        name="tasks.extract_features",
        bind=True,
        max_retries=2,
        default_retry_delay=30,
    )
    def extract_features(self, enrich_result: dict) -> dict:
        """
        CPU stage: Build ML feature rows from tracking + NBA API data.

        Returns:
            {"game_id": str, "n_feature_rows": int, "features_path": str}
        """
        game_id = enrich_result.get("game_id", "")
        if not game_id:
            return {"game_id": game_id, "error": "missing game_id"}

        try:
            from src.features.feature_engineering import build_game_features
            feats = build_game_features(
                game_id=game_id,
                events_path=enrich_result.get("events_path", ""),
            )
            features_path = os.path.join(_EVENTS_DIR, f"{game_id}_features.json")
            with open(features_path, "w") as f:
                json.dump(feats, f)
            return {
                "game_id":        game_id,
                "n_feature_rows": len(feats) if isinstance(feats, list) else 1,
                "features_path":  features_path,
            }
        except Exception as exc:
            raise self.retry(exc=exc, countdown=30)


# ── Task: run_inference ───────────────────────────────────────────────────────

if _CELERY_AVAILABLE:
    @app.task(
        name="tasks.run_inference",
        bind=True,
        max_retries=2,
        default_retry_delay=30,
    )
    def run_inference(self, feat_result: dict) -> dict:
        """
        Fast GPU: Run model predictions on extracted features.

        Returns:
            {"game_id": str, "predictions": dict, "players_predicted": int}
        """
        game_id = feat_result.get("game_id", "")
        features_path = feat_result.get("features_path", "")

        try:
            from src.pipeline.model_pipeline import run_predictions
            preds = run_predictions(game_id=game_id, features_path=features_path)
            return {
                "game_id":           game_id,
                "features_path":     features_path,
                "predictions":       preds,
                "players_predicted": len(preds.get("props", {})),
            }
        except Exception as exc:
            raise self.retry(exc=exc, countdown=30)


# ── Task: store_to_db ─────────────────────────────────────────────────────────

if _CELERY_AVAILABLE:
    @app.task(
        name="tasks.store_to_db",
        bind=True,
        max_retries=3,
        default_retry_delay=60,
    )
    def store_to_db(self, inference_result: dict) -> dict:
        """
        PostgreSQL write: persist game tracking, features, and predictions.

        Returns:
            {"game_id": str, "stored": bool, "rows_written": int}
        """
        game_id = inference_result.get("game_id", "")
        features_path = inference_result.get("features_path", "")
        predictions   = inference_result.get("predictions", {})

        try:
            from src.data.db import get_connection
            rows_written = 0
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Upsert game record
                    cur.execute(
                        """
                        INSERT INTO games (game_id, processed_at, status)
                        VALUES (%s, NOW(), 'complete')
                        ON CONFLICT (game_id) DO UPDATE SET processed_at = NOW(), status = 'complete'
                        """,
                        (game_id,),
                    )
                    rows_written += 1

                    # Store predictions if available
                    if predictions and features_path and os.path.exists(features_path):
                        cur.execute(
                            """
                            INSERT INTO predictions (game_id, model_version, predictions_json, created_at)
                            VALUES (%s, %s, %s, NOW())
                            ON CONFLICT (game_id, model_version) DO NOTHING
                            """,
                            (game_id, "v1", json.dumps(predictions)),
                        )
                        rows_written += 1
                conn.commit()
            return {"game_id": game_id, "stored": True, "rows_written": rows_written}
        except Exception as exc:
            raise self.retry(exc=exc, countdown=60)


# ── Pipeline chain ────────────────────────────────────────────────────────────

def process_game_chain(video_path: str, game_id: str):
    """
    Submit full pipeline chain for a single game.

    Returns a Celery chain result if Celery available, else runs synchronously.
    """
    if not _CELERY_AVAILABLE:
        raise RuntimeError("Celery not installed. Run: pip install celery[redis]")

    return chain(
        track_game.s(video_path, game_id),
        enrich_game.s(),
        extract_features.s(),
        run_inference.s(),
        store_to_db.s(),
    ).apply_async()


if __name__ == "__main__":
    if not _CELERY_AVAILABLE:
        print("[tasks] Celery not installed. Install with: pip install celery[redis]")
    else:
        print(f"[tasks] Celery app ready. Broker: {_REDIS_URL}")
        print("  Start worker: celery -A src.pipeline.tasks worker --loglevel=info")
        print("  Monitor:      celery -A src.pipeline.tasks flower")
