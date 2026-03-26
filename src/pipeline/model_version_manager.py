"""
model_version_manager.py -- Phase D5: Model version tracking for predictions.

Every prediction is tagged with:
  - model_version: semver string (e.g. "1.0.0")
  - feature_hash:  MD5 of the sorted feature list used at train time
  - trained_at:    ISO timestamp of last retrain

When a model retrains, its version bumps automatically (patch → minor → major).
Old predictions remain traceable — compare v1 vs v2 accuracy retrospectively.

Public API
----------
    get_version(model_name)                           -> dict
    register_retrain(model_name, metrics, features)  -> dict  (new version record)
    get_all_versions(model_name)                     -> list[dict]
    compare_versions(model_name, v1, v2, n_games)   -> dict
    tag_prediction(model_name, prediction)           -> dict  (prediction + version tags)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_VERSION_LOG = os.path.join(PROJECT_DIR, "data", "models", "model_versions.json")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_log() -> dict:
    """Load or initialize version log. Returns {model_name: [version_records]}."""
    if os.path.exists(_VERSION_LOG):
        try:
            return json.load(open(_VERSION_LOG))
        except Exception:
            pass
    return {}


def _save_log(log: dict) -> None:
    os.makedirs(os.path.dirname(_VERSION_LOG), exist_ok=True)
    with open(_VERSION_LOG, "w") as f:
        json.dump(log, f, indent=2)


def _feature_hash(features: list) -> str:
    """MD5 of sorted feature names — detects feature set changes."""
    canon = json.dumps(sorted(features), separators=(",", ":"))
    return hashlib.md5(canon.encode()).hexdigest()[:12]


def _bump_version(current: str, bump: str = "patch") -> str:
    """Bump semver string. bump ∈ {'major', 'minor', 'patch'}."""
    try:
        major, minor, patch = [int(x) for x in current.split(".")]
    except Exception:
        return "1.0.0"
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


# ── Core API ──────────────────────────────────────────────────────────────────

def get_version(model_name: str) -> dict:
    """
    Return the active version record for a model.

    Returns:
        {
            "model_name":    str,
            "version":       str,   # e.g. "1.2.0"
            "feature_hash":  str,
            "metrics":       dict,
            "trained_at":    str,
            "is_active":     bool,
        }
        or {"model_name": str, "version": "0.0.0", "trained_at": None}
        if never registered.
    """
    log = _load_log()
    records = log.get(model_name, [])
    actives = [r for r in records if r.get("is_active")]
    if actives:
        return actives[-1]
    if records:
        return records[-1]
    return {"model_name": model_name, "version": "0.0.0", "trained_at": None, "metrics": {}}


def register_retrain(
    model_name: str,
    metrics: dict,
    features: Optional[list] = None,
    bump: str = "patch",
) -> dict:
    """
    Register a new model version after a retrain.

    Args:
        model_name: e.g. "props_pts", "win_probability", "matchup"
        metrics:    {mae, r2, accuracy, ...} — whatever the model produces
        features:   List of feature names used at train time
        bump:       Version bump type: "major" | "minor" | "patch"

    Returns:
        New version record dict.
    """
    log = _load_log()

    # Determine new version
    records = log.get(model_name, [])
    if records:
        current_ver = records[-1].get("version", "0.0.0")
    else:
        current_ver = "0.0.0"

    # Auto-detect bump level: if feature set changed → minor bump
    fhash = _feature_hash(features) if features else ""
    if records and fhash and fhash != records[-1].get("feature_hash", ""):
        bump = "minor"

    new_version = _bump_version(current_ver, bump) if current_ver != "0.0.0" else "1.0.0"

    # Mark all existing records inactive
    for r in records:
        r["is_active"] = False

    record = {
        "model_name":   model_name,
        "version":      new_version,
        "feature_hash": fhash,
        "metrics":      metrics,
        "trained_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
        "is_active":    True,
        "features":     features or [],
    }
    records.append(record)
    log[model_name] = records

    _save_log(log)
    _sync_to_db(record)

    print(f"[model_version_manager] {model_name} v{new_version} registered "
          f"(fhash={fhash or 'N/A'}, metrics={metrics})")
    return record


def get_all_versions(model_name: str) -> list:
    """Return all version records for a model, oldest first."""
    log = _load_log()
    return log.get(model_name, [])


def list_active_versions() -> dict:
    """Return {model_name: version_string} for all active models."""
    log = _load_log()
    result = {}
    for name, records in log.items():
        actives = [r for r in records if r.get("is_active")]
        if actives:
            result[name] = actives[-1]["version"]
    return result


def compare_versions(
    model_name: str,
    v1: str,
    v2: str,
    n_games: int = 20,
) -> dict:
    """
    Compare accuracy metrics between two versions of a model.

    Pulls actual vs predicted from the outcomes table, filtered by model_version.

    Returns:
        {
            "model":    str,
            "v1":       {"version": str, "mae": float, "r2": float, "n": int},
            "v2":       {"version": str, "mae": float, "r2": float, "n": int},
            "delta_mae": float,   # negative = v2 is better
            "winner":   "v1" | "v2" | "tie",
        }
    """
    def _pull_metrics(version: str) -> dict:
        try:
            from src.data.db import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT actual_value, predicted_value
                        FROM outcomes
                        WHERE stat_name LIKE %s
                          AND model_version = %s
                          AND predicted_value IS NOT NULL
                        ORDER BY recorded_at DESC
                        LIMIT %s
                        """,
                        (f"%{model_name.split('_')[-1]}%", version, n_games * 15),
                    )
                    rows = cur.fetchall()
            if rows:
                actual = [r[0] for r in rows]
                pred   = [r[1] for r in rows]
                errors = [abs(a - p) for a, p in zip(actual, pred)]
                mae    = round(sum(errors) / len(errors), 4)
                mean_a = sum(actual) / len(actual)
                ss_res = sum((a - p) ** 2 for a, p in zip(actual, pred))
                ss_tot = sum((a - mean_a) ** 2 for a in actual)
                r2     = round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0
                return {"version": version, "mae": mae, "r2": r2, "n": len(rows)}
        except Exception:
            pass

        # Fallback: read stored metrics from version log
        for r in get_all_versions(model_name):
            if r.get("version") == version:
                m = r.get("metrics", {})
                return {
                    "version": version,
                    "mae": m.get("mae"),
                    "r2":  m.get("r2"),
                    "n":   m.get("n", 0),
                }
        return {"version": version, "mae": None, "r2": None, "n": 0}

    m1 = _pull_metrics(v1)
    m2 = _pull_metrics(v2)

    delta = None
    winner = "unknown"
    if m1["mae"] is not None and m2["mae"] is not None:
        delta  = round(m2["mae"] - m1["mae"], 4)
        winner = "v2" if delta < 0 else ("v1" if delta > 0 else "tie")

    return {
        "model":     model_name,
        "v1":        m1,
        "v2":        m2,
        "delta_mae": delta,
        "winner":    winner,
    }


def tag_prediction(model_name: str, prediction: dict) -> dict:
    """
    Attach version metadata to a prediction dict.

    Args:
        model_name:  e.g. "props_pts"
        prediction:  Existing prediction dict

    Returns:
        prediction dict with added fields:
            _model_version, _feature_hash, _model_trained_at
    """
    rec = get_version(model_name)
    prediction["_model_version"]    = rec.get("version", "unknown")
    prediction["_feature_hash"]     = rec.get("feature_hash", "")
    prediction["_model_trained_at"] = rec.get("trained_at", "")
    return prediction


# ── DB sync ───────────────────────────────────────────────────────────────────

def _sync_to_db(record: dict) -> None:
    """Write version record to PostgreSQL model_versions table."""
    try:
        from src.data.db import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO model_versions
                        (model_name, version, feature_hash, metrics_json,
                         trained_at, is_active)
                    VALUES (%s, %s, %s, %s, NOW(), %s)
                    ON CONFLICT (model_name, version) DO UPDATE
                        SET is_active   = EXCLUDED.is_active,
                            metrics_json = EXCLUDED.metrics_json
                    """,
                    (
                        record["model_name"],
                        record["version"],
                        record.get("feature_hash", ""),
                        json.dumps(record.get("metrics", {})),
                        record["is_active"],
                    ),
                )
                # Deactivate older versions in DB
                if record["is_active"]:
                    cur.execute(
                        """
                        UPDATE model_versions
                        SET is_active = FALSE
                        WHERE model_name = %s AND version != %s
                        """,
                        (record["model_name"], record["version"]),
                    )
            conn.commit()
    except Exception:
        pass


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Model version manager")
    parser.add_argument("--list",    action="store_true", help="List all active versions")
    parser.add_argument("--history", metavar="MODEL",     help="Show version history for a model")
    parser.add_argument("--compare", nargs=3, metavar=("MODEL", "V1", "V2"),
                        help="Compare two versions: --compare props_pts 1.0.0 1.1.0")
    parser.add_argument("--register", nargs=2, metavar=("MODEL", "METRICS_JSON"),
                        help="Register a retrain: --register props_pts '{\"mae\":2.1}'")
    args = parser.parse_args()

    if args.list:
        active = list_active_versions()
        if not active:
            print("[model_version_manager] No versions registered yet.")
        else:
            print("\nActive model versions:")
            for name, ver in sorted(active.items()):
                print(f"  {name:30s}  v{ver}")

    elif args.history:
        history = get_all_versions(args.history)
        if not history:
            print(f"[model_version_manager] No history for '{args.history}'.")
        else:
            print(f"\nVersion history for {args.history}:")
            for r in history:
                active_flag = " [ACTIVE]" if r.get("is_active") else ""
                print(f"  v{r['version']}  {r.get('trained_at','')}  "
                      f"metrics={r.get('metrics',{})}  fhash={r.get('feature_hash','')[:8]}"
                      f"{active_flag}")

    elif args.compare:
        model, v1, v2 = args.compare
        result = compare_versions(model, v1, v2)
        print(f"\nCompare {model}  v{v1} vs v{v2}:")
        print(f"  v{v1}: MAE={result['v1']['mae']}  R2={result['v1']['r2']}  n={result['v1']['n']}")
        print(f"  v{v2}: MAE={result['v2']['mae']}  R2={result['v2']['r2']}  n={result['v2']['n']}")
        print(f"  delta_mae={result['delta_mae']}  winner={result['winner']}")

    elif args.register:
        model, metrics_json = args.register
        try:
            metrics = json.loads(metrics_json)
        except json.JSONDecodeError as e:
            print(f"[model_version_manager] Invalid JSON: {e}")
            sys.exit(1)
        rec = register_retrain(model, metrics)
        print(f"[model_version_manager] Registered {model} v{rec['version']}")

    else:
        parser.print_help()
