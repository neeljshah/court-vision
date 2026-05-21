"""
auto_retrain.py -- Phase D4: Auto-retrain trigger after game milestones.

After each game stored to DB, checks total game count and triggers
model retrains at the right milestones:

  20 games  -> Tier 3 models (xFG v2, play type, pressure, spacing)
  50 games  -> Tier 4 models (fatigue curve, rebound positioning)
  100 games -> Tier 5 models (lineup chemistry, matchup matrix)
  any game  -> Retrain props if MAE > threshold (quality gate)

Public API
----------
    check_and_retrain(game_id, season)  -> dict  (retrain summary)
    get_game_count()                    -> int
    _props_mae_exceeds_threshold()      -> bool
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_VAULT_LOG = os.path.join(PROJECT_DIR, "vault", "Improvements", "Tracker Improvements Log.md")
_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_MILESTONE_STATE_PATH = os.path.join(_MODEL_DIR, "retrain_milestones.json")

# Quality gate: retrain props if rolling MAE exceeds these thresholds
_MAE_THRESHOLDS = {
    "pts":  2.0,
    "reb":  1.5,
    "ast":  1.2,
    "fg3m": 0.8,
}

# Model tier unlock milestones
_TIER_MILESTONES = {
    20:  "tier3",
    50:  "tier4",
    100: "tier5",
    200: "tier6",
}


def _load_milestone_state() -> dict:
    """Load persisted milestone state from JSON file."""
    if os.path.exists(_MILESTONE_STATE_PATH):
        try:
            with open(_MILESTONE_STATE_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_milestone_state(state: dict) -> None:
    """Persist milestone fired state to JSON file."""
    os.makedirs(_MODEL_DIR, exist_ok=True)
    with open(_MILESTONE_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def get_game_count() -> int:
    """Return number of fully processed games in the database."""
    try:
        from src.data.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM games WHERE status = 'complete'"
                )
                return int(cur.fetchone()[0])
    except Exception:
        # Fallback: count events JSON files
        events_dir = os.path.join(PROJECT_DIR, "data", "events")
        if not os.path.isdir(events_dir):
            return 0
        return len([f for f in os.listdir(events_dir) if f.endswith("_events.json")])


def _props_mae_exceeds_threshold(n_games: int = 10) -> dict:
    """
    Check if any prop model has MAE above threshold.

    Returns:
        {"exceeded": bool, "offenders": {stat: mae}}
    """
    from src.pipeline.outcome_recorder import get_model_accuracy
    offenders = {}
    for stat, threshold in _MAE_THRESHOLDS.items():
        result = get_model_accuracy(stat, n_games)
        mae = result.get("mae")
        if mae is not None and mae > threshold:
            offenders[stat] = mae
    return {"exceeded": bool(offenders), "offenders": offenders}


def _log_retrain(message: str) -> None:
    """Append a line to the vault improvement log."""
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    try:
        if os.path.exists(_VAULT_LOG):
            with open(_VAULT_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n### {timestamp} -- Auto-Retrain\n{message}\n")
    except Exception:
        pass


def check_and_retrain(
    game_id: str,
    season: str = "2024-25",
    force_props: bool = False,
) -> dict:
    """
    Check game count and trigger appropriate retrains.

    Args:
        game_id:     Game just processed
        season:      Current season
        force_props: Force prop retrain regardless of quality gate

    Returns:
        {
            "game_count":    int,
            "milestone_hit": str | None,
            "retrained":     list[str],
            "skipped":       list[str],
            "metrics":       dict,
        }
    """
    game_count = get_game_count()
    retrained  = []
    skipped    = []
    metrics    = {}

    print(f"[auto_retrain] Game count: {game_count}  (just processed: {game_id})")

    # ── Quality gate: retrain props if MAE exceeds threshold ─────────────────
    if force_props:
        _run_props_retrain(retrained, metrics)
    else:
        quality = _props_mae_exceeds_threshold(n_games=min(game_count, 20))
        if quality["exceeded"]:
            offenders = quality["offenders"]
            print(f"[auto_retrain] Props MAE exceeded threshold: {offenders}")
            _log_retrain(f"Props quality gate triggered: {offenders}")
            _run_props_retrain(retrained, metrics)
        else:
            skipped.append("props_quality_gate_ok")

    # ── Milestone retrains ────────────────────────────────────────────────────
    milestone_hit = None
    fired = _load_milestone_state()
    for threshold, tier in sorted(_TIER_MILESTONES.items()):
        # Trigger once when crossing the threshold; idempotent via JSON state file
        if game_count >= threshold and not fired.get(tier):
            milestone_hit = tier
            print(f"[auto_retrain] Milestone {threshold} games -> retrain {tier}")
            _log_retrain(f"Milestone {threshold} games reached: triggering {tier} retrain")

            if tier == "tier3":
                _retrain_tier3(retrained, metrics, season)
            elif tier == "tier4":
                _retrain_tier4(retrained, metrics, season)
            elif tier in ("tier5", "tier6"):
                print(f"[auto_retrain] {tier} models need to be built first (Phase 10/12)")
                skipped.append(tier)

            fired[tier] = True
            _save_milestone_state(fired)
            break

    # Always retrain props at every milestone
    if milestone_hit and "props" not in retrained:
        _run_props_retrain(retrained, metrics)

    return {
        "game_count":    game_count,
        "milestone_hit": milestone_hit,
        "retrained":     retrained,
        "skipped":       skipped,
        "metrics":       metrics,
    }


def _run_props_retrain(retrained: list, metrics: dict) -> None:
    """Retrain all 7 prop models and log results."""
    try:
        from src.prediction.player_props import train_props
        results = train_props(force=True)
        retrained.append("props")
        metrics["props"] = results
        _log_retrain(
            "Props retrained (auto):\n"
            + "\n".join(f"  - {s}: MAE={m.get('mae',0):.3f}" for s, m in results.items())
        )
        # Register new versions
        try:
            from src.pipeline.model_version_manager import register_retrain
            for stat, m in results.items():
                register_retrain(f"props_{stat}", m)
        except Exception:
            pass
        # Train Ridge meta to correct systematic bias
        try:
            from src.prediction.prop_model_stack import train_all_meta
            meta_results = train_all_meta()
            _log_retrain("Ridge meta retrained: " + ", ".join(
                f"{s}: coef={r['coef']:.3f} int={r['intercept']:.3f}"
                for s, r in meta_results.items()
            ))
        except Exception as e:
            print(f"[auto_retrain] Ridge meta error: {e}")
    except Exception as e:
        print(f"[auto_retrain] Props retrain error: {e}")


def _retrain_tier3(retrained: list, metrics: dict, season: str) -> None:
    """Tier 3 models (20 games): xFG v2, play type, pressure, spacing."""
    # These models don't exist yet — placeholder until Phase I builds them
    tier3_models = ["xfg_v2", "play_type", "pressure", "spacing"]
    for model in tier3_models:
        model_path = os.path.join(PROJECT_DIR, "data", "models", f"{model}.json")
        if os.path.exists(model_path):
            try:
                # Dynamic import when models exist
                mod = __import__(f"src.prediction.{model}", fromlist=["train"])
                train_fn = getattr(mod, "train", None)
                if train_fn:
                    result = train_fn(force=True, season=season)
                    retrained.append(model)
                    metrics[model] = result
            except Exception as e:
                print(f"[auto_retrain] {model} retrain error: {e}")
        else:
            print(f"[auto_retrain] {model} not yet built (Phase I)")


def _retrain_tier4(retrained: list, metrics: dict, season: str) -> None:
    """Tier 4 models (50 games): fatigue curve, rebound positioning."""
    print("[auto_retrain] Tier 4 models not yet built (Phase 10)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Check and trigger model retrains")
    parser.add_argument("--game-id",     default="manual_trigger")
    parser.add_argument("--season",      default="2024-25")
    parser.add_argument("--force-props", action="store_true",
                        help="Force prop retrain regardless of quality gate")
    parser.add_argument("--count",       action="store_true",
                        help="Just show game count")
    args = parser.parse_args()

    if args.count:
        n = get_game_count()
        print(f"[auto_retrain] Processed games: {n}")
    else:
        result = check_and_retrain(args.game_id, args.season, args.force_props)
        print(json.dumps(
            {k: v for k, v in result.items() if k != "metrics"},
            indent=2,
        ))
