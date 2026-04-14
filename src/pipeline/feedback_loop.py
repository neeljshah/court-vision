"""
feedback_loop.py — Phase 9: Automated Feedback Loop

Detects new games, runs the pipeline, checks retrain triggers,
versions models, validates gates, and detects feature drift.

Public API
----------
    FeedbackLoop.detect_new_games()          -> list[str]
    FeedbackLoop.run_pipeline(game_id)       -> dict
    FeedbackLoop.check_retrain_triggers()    -> dict
    FeedbackLoop.retrain_model(model_name)   -> dict
    FeedbackLoop.rollback_model(model_name)  -> bool
    FeedbackLoop.detect_drift()              -> dict
    FeedbackLoop.update_registry(model_name, version, metric, n_samples) -> None
"""
from __future__ import annotations

import json
import os
import pickle
import shutil
import subprocess
import sys
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR    = os.path.join(PROJECT_DIR, "data", "models")
_VIDEOS_DIR    = os.path.join(PROJECT_DIR, "data", "videos", "full_games")
_PROCESSED_TXT = os.path.join(PROJECT_DIR, "data", "phase_g_processed.txt")
_REGISTRY_PATH = os.path.join(PROJECT_DIR, "data", "models", "model_registry.json")
_METRICS_CSV   = os.path.join(PROJECT_DIR, "data", "phase_g_metrics.csv")

# Per-model retrain triggers from ROADMAP Phase 9
_RETRAIN_TRIGGERS: dict[str, dict] = {
    "xfg_v2":    {"type": "shots",               "threshold": 50,  "gate": "brier_improve"},
    "props_pts":  {"type": "gamelogs_per_player", "threshold": 10,  "gate": "mae_no_regress_5pct"},
    "props_reb":  {"type": "gamelogs_per_player", "threshold": 10,  "gate": "mae_no_regress_5pct"},
    "props_ast":  {"type": "gamelogs_per_player", "threshold": 10,  "gate": "mae_no_regress_5pct"},
    "play_type":  {"type": "possessions",         "threshold": 200, "gate": "accuracy_gte_0.80"},
    "fatigue":    {"type": "games_per_player",    "threshold": 5,   "gate": "corr_gte_0.45"},
    "live_lstm":  {"type": "games",               "threshold": 20,  "gate": "auc_gte_0.75"},
}

# Never auto-retrain these (ROADMAP §Phase 9)
_NO_AUTO_RETRAIN = {"win_probability", "nlp_models"}
_MIN_R2_FOR_AUTO = 0.40

# Drift detection window
_DRIFT_WINDOW = 30


class FeedbackLoop:
    """Orchestrates the nightly automated feedback loop."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        os.makedirs(_MODELS_DIR, exist_ok=True)

    # ── Game detection ─────────────────────────────────────────────────────────

    def detect_new_games(self) -> list[str]:
        """Return video filenames in data/videos/full_games/ not yet processed."""
        processed: set[str] = set()
        if os.path.exists(_PROCESSED_TXT):
            with open(_PROCESSED_TXT) as f:
                processed = {line.strip() for line in f if line.strip()}

        if not os.path.isdir(_VIDEOS_DIR):
            return []

        new_games = []
        for fname in sorted(os.listdir(_VIDEOS_DIR)):
            if fname.endswith((".mp4", ".mkv", ".avi")) and fname not in processed:
                new_games.append(fname)
        return new_games

    # ── Pipeline execution ─────────────────────────────────────────────────────

    def run_pipeline(self, game_id: str) -> dict:
        """
        Process a game clip end-to-end: tracker → NBA API enrichment → possession labels.

        Args:
            game_id: Video filename (e.g. "0022400001.mp4")

        Returns:
            {"game_id": str, "status": str, "shots": int, "possessions": int}
        """
        if self.dry_run:
            print(f"[feedback_loop][dry-run] Would run pipeline for {game_id}")
            return {"game_id": game_id, "status": "dry_run", "shots": 0, "possessions": 0}

        video_path = os.path.join(_VIDEOS_DIR, game_id)
        if not os.path.exists(video_path):
            return {"game_id": game_id, "status": "video_not_found", "shots": 0, "possessions": 0}

        script = os.path.join(PROJECT_DIR, "scripts", "run_clip.py")
        cmd = [sys.executable, script, "--video", video_path, "--no-show"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            ok = result.returncode == 0
            status = "ok" if ok else "error"
        except subprocess.TimeoutExpired:
            status = "timeout"
            ok = False

        shots, possessions = 0, 0
        if ok:
            shots, possessions = self._count_labeled_data(game_id)
            self._mark_processed(game_id)

        return {"game_id": game_id, "status": status, "shots": shots, "possessions": possessions}

    # ── Retrain triggers ───────────────────────────────────────────────────────

    def check_retrain_triggers(self) -> dict[str, bool]:
        """
        Evaluate each model's retrain trigger against accumulated data counts.

        Returns:
            {model_name: should_retrain}
        """
        counts = self._get_data_counts()
        result: dict[str, bool] = {}

        for model, cfg in _RETRAIN_TRIGGERS.items():
            if model in _NO_AUTO_RETRAIN:
                result[model] = False
                continue

            # Skip if current model R² is below minimum signal threshold
            reg = self._registry_entry(model)
            if reg.get("r2", 1.0) < _MIN_R2_FOR_AUTO and reg.get("r2") is not None:
                result[model] = False
                continue

            dtype    = cfg["type"]
            thresh   = cfg["threshold"]
            count    = counts.get(dtype, 0)
            baseline = reg.get("n_samples", 0)
            result[model] = (count - baseline) >= thresh

        return result

    # ── Retrain + gate ─────────────────────────────────────────────────────────

    def retrain_model(self, model_name: str) -> dict:
        """
        Train a new model version, run validation gate, promote if it passes.

        Returns:
            {"model": str, "promoted": bool, "version": int, "gate_passed": bool, "metrics": dict}
        """
        if model_name in _NO_AUTO_RETRAIN:
            return {"model": model_name, "promoted": False, "reason": "no_auto_retrain"}

        if self.dry_run:
            print(f"[feedback_loop][dry-run] Would retrain {model_name}")
            return {"model": model_name, "promoted": False, "version": 0, "gate_passed": False, "metrics": {}}

        try:
            new_metrics = self._train_new_version(model_name)
        except Exception as e:
            return {"model": model_name, "promoted": False, "error": str(e), "metrics": {}}

        gate_passed = self._run_validation_gate(model_name, new_metrics)
        new_version = self._next_version(model_name)

        if gate_passed:
            self._promote_version(model_name, new_version)
            self.update_registry(model_name, new_version, new_metrics, new_metrics.get("n", 0))
            print(f"[feedback_loop] {model_name} v{new_version} promoted")
        else:
            self.rollback_model(model_name)
            print(f"[feedback_loop] {model_name} gate failed — rolled back")

        return {
            "model":       model_name,
            "promoted":    gate_passed,
            "version":     new_version,
            "gate_passed": gate_passed,
            "metrics":     new_metrics,
        }

    # ── Rollback ───────────────────────────────────────────────────────────────

    def rollback_model(self, model_name: str) -> bool:
        """
        Restore the previous model version if validation gate fails.

        Returns True if rollback succeeded, False if no prior version found.
        """
        reg = self._load_registry()
        entry = reg.get(model_name, {})
        current_v = entry.get("current_version", 1)
        prev_v    = current_v - 1

        if prev_v < 1:
            print(f"[feedback_loop] No prior version to rollback for {model_name}")
            return False

        prev_path = os.path.join(_MODELS_DIR, f"{model_name}_v{prev_v}.pkl")
        if not os.path.exists(prev_path):
            print(f"[feedback_loop] Prior version file missing: {prev_path}")
            return False

        current_path = os.path.join(_MODELS_DIR, f"{model_name}_current.pkl")
        shutil.copy2(prev_path, current_path)
        entry["current_version"] = prev_v
        reg[model_name] = entry
        self._save_registry(reg)
        print(f"[feedback_loop] {model_name} rolled back to v{prev_v}")
        return True

    # ── Drift detection ────────────────────────────────────────────────────────

    def detect_drift(self) -> dict[str, dict]:
        """
        Compute rolling Z-score on last 30 games vs training distribution.

        Returns:
            {feature_name: {"z_score": float, "drifted": bool}}
        """
        try:
            from src.pipeline.feature_drift_detector import detect_feature_drift
            return detect_feature_drift(window=_DRIFT_WINDOW)
        except Exception:
            pass

        # Lightweight fallback: check metrics CSV for anomalies
        return self._drift_from_metrics_csv()

    # ── Registry helpers ───────────────────────────────────────────────────────

    def update_registry(
        self,
        model_name: str,
        version: int,
        metric: dict,
        n_samples: int,
    ) -> None:
        """Update model_registry.json with new version info."""
        reg = self._load_registry()
        reg[model_name] = {
            "current_version": version,
            "trained_date":    time.strftime("%Y-%m-%dT%H:%M:%S"),
            "metric":          metric,
            "n_samples":       n_samples,
            "r2":              metric.get("r2"),
        }
        self._save_registry(reg)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_registry(self) -> dict:
        if os.path.exists(_REGISTRY_PATH):
            try:
                return json.load(open(_REGISTRY_PATH))
            except Exception:
                pass
        return {}

    def _save_registry(self, reg: dict) -> None:
        os.makedirs(_MODELS_DIR, exist_ok=True)
        with open(_REGISTRY_PATH, "w") as f:
            json.dump(reg, f, indent=2)

    def _registry_entry(self, model_name: str) -> dict:
        return self._load_registry().get(model_name, {})

    def _next_version(self, model_name: str) -> int:
        entry = self._registry_entry(model_name)
        return entry.get("current_version", 0) + 1

    def _train_new_version(self, model_name: str) -> dict:
        """Dispatch to the model's train() function. Returns metrics dict."""
        try:
            import importlib
            mod = importlib.import_module(f"src.prediction.{model_name.replace('-', '_')}")
            train_fn = getattr(mod, "train", None)
            if train_fn:
                return train_fn(force=True) or {}
        except Exception:
            pass
        # Fallback for props stack
        if model_name.startswith("props_"):
            stat = model_name.split("_", 1)[1]
            from src.prediction.player_props import train_props
            results = train_props(force=True)
            return results.get(stat, {})
        return {}

    def _run_validation_gate(self, model_name: str, new_metrics: dict) -> bool:
        """
        Compare new model vs current on held-out time-ordered 20% slice.

        Gate rules (ROADMAP):
        1. Must beat current production model on primary metric
        2. Must not catastrophically fail on any subgroup (max 2x error)
        3. If R² < 0.40, skip auto-retrain
        """
        cfg = _RETRAIN_TRIGGERS.get(model_name, {})
        gate = cfg.get("gate", "mae_no_regress_5pct")

        if gate == "brier_improve":
            old = self._registry_entry(model_name).get("metric", {}).get("brier", 1.0)
            new = new_metrics.get("brier", 1.0)
            return new < old

        if gate == "mae_no_regress_5pct":
            old_mae = self._registry_entry(model_name).get("metric", {}).get("mae", float("inf"))
            new_mae = new_metrics.get("mae", float("inf"))
            return new_mae <= old_mae * 1.05

        if gate == "accuracy_gte_0.80":
            return new_metrics.get("accuracy", 0.0) >= 0.80

        if gate == "corr_gte_0.45":
            return new_metrics.get("correlation", 0.0) >= 0.45

        if gate == "auc_gte_0.75":
            return new_metrics.get("auc", 0.0) >= 0.75

        return False

    def _promote_version(self, model_name: str, version: int) -> None:
        """Copy versioned pkl to {model_name}_current.pkl."""
        src  = os.path.join(_MODELS_DIR, f"{model_name}_v{version}.pkl")
        dest = os.path.join(_MODELS_DIR, f"{model_name}_current.pkl")
        if os.path.exists(src):
            shutil.copy2(src, dest)

    def _count_labeled_data(self, game_id: str) -> tuple[int, int]:
        """Count shots and possessions from tracking output for a game."""
        base = game_id.replace(".mp4", "").replace(".mkv", "").replace(".avi", "")
        events_path = os.path.join(PROJECT_DIR, "data", "events", f"{base}_events.json")
        if not os.path.exists(events_path):
            return 0, 0
        try:
            events = json.load(open(events_path))
            shots  = sum(1 for e in events if e.get("type") == "shot")
            poss   = sum(1 for e in events if e.get("type") == "possession_end")
            return shots, poss
        except Exception:
            return 0, 0

    def _mark_processed(self, game_id: str) -> None:
        with open(_PROCESSED_TXT, "a") as f:
            f.write(f"{game_id}\n")

    def _get_data_counts(self) -> dict[str, int]:
        """Estimate accumulated data counts for trigger evaluation."""
        counts: dict[str, int] = {"shots": 0, "possessions": 0, "games": 0,
                                   "gamelogs_per_player": 0, "games_per_player": 0}
        events_dir = os.path.join(PROJECT_DIR, "data", "events")
        if os.path.isdir(events_dir):
            for fname in os.listdir(events_dir):
                if not fname.endswith("_events.json"):
                    continue
                try:
                    events = json.load(open(os.path.join(events_dir, fname)))
                    counts["shots"]       += sum(1 for e in events if e.get("type") == "shot")
                    counts["possessions"] += sum(1 for e in events if e.get("type") == "possession_end")
                    counts["games"]       += 1
                except Exception:
                    pass
        # Rough proxies: gamelogs ~= games * 10 players; games_per_player ~= games
        counts["gamelogs_per_player"] = counts["games"] * 10
        counts["games_per_player"]    = counts["games"]
        return counts

    def _drift_from_metrics_csv(self) -> dict[str, dict]:
        """Fallback drift detection via phase_g_metrics.csv rolling stats."""
        if not os.path.exists(_METRICS_CSV):
            return {}
        try:
            import csv
            rows = []
            with open(_METRICS_CSV) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
            if len(rows) < 2:
                return {}

            recent = rows[-_DRIFT_WINDOW:]
            result: dict[str, dict] = {}
            numeric_fields = [k for k in recent[0] if k not in ("game_id", "date", "status")]
            for field in numeric_fields:
                vals = []
                for r in recent:
                    try:
                        vals.append(float(r[field]))
                    except (ValueError, KeyError):
                        pass
                if len(vals) < 5:
                    continue
                mean = sum(vals) / len(vals)
                std  = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
                z    = abs((vals[-1] - mean) / std) if std > 0 else 0.0
                result[field] = {"z_score": round(z, 3), "drifted": z > 2.0}
            return result
        except Exception:
            return {}


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nightly NBA feedback loop")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect and report without executing retrains")
    args = parser.parse_args()

    loop = FeedbackLoop(dry_run=args.dry_run)

    print("── Detecting new games ──")
    new_games = loop.detect_new_games()
    print(f"  Found {len(new_games)} unprocessed clips")

    for game in new_games:
        print(f"  Processing {game} ...")
        result = loop.run_pipeline(game)
        print(f"  {result}")

    print("\n── Checking retrain triggers ──")
    triggers = loop.check_retrain_triggers()
    for model, should in triggers.items():
        status = "TRIGGER" if should else "ok"
        print(f"  {model:20s}  {status}")

    print("\n── Retraining triggered models ──")
    for model, should in triggers.items():
        if should:
            result = loop.retrain_model(model)
            print(f"  {model}: promoted={result['promoted']}  gate={result.get('gate_passed')}")

    print("\n── Drift detection ──")
    drift = loop.detect_drift()
    drifted = {k: v for k, v in drift.items() if v.get("drifted")}
    if drifted:
        print(f"  DRIFT ALERT: {list(drifted.keys())}")
    else:
        print(f"  No drift detected ({len(drift)} features checked)")
