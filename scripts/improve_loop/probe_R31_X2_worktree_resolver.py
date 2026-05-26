"""probe_R31_X2_worktree_resolver.py — verify worktree-aware resolver
works end-to-end across all 4 production loaders.

Extends R21_N1 (prop_pergame only) by validating that game_models,
residual_heads, and injury_availability ALL fall back to the host repo's
data/models when this worktree's data/models is empty.

How it works:
  1. Reads each loader's resolved dir (`_MODEL_DIR`, `_M2_FAMILY_DIR`,
     `HEAD_DIR`, `_CACHE_DIR`) AS-IS — these are computed at import time.
  2. Records whether each dir exists and contains its expected canary.
  3. Optionally re-imports each module after temporarily setting
     `NBA_DATA_DIR` to confirm the env override fires.
  4. Persists every observation to data/cache/probe_R31_X2_results.json.

Ship gate: all 4 loaders resolve to a populated dir (either local or
host repo). On a worktree with no local artifacts, every dir resolves
to host. On the host itself, every dir resolves to host (its own dir).

Usage:
    python scripts/improve_loop/probe_R31_X2_worktree_resolver.py
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_DIR)

OUT_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R31_X2_results.json"
)


def _module_obs(mod_name: str, attrs: dict) -> dict:
    """Capture (re-imported) module attributes + on-disk reality checks.

    Returns {attr_name: {value, exists, has_canary}}.
    """
    # Force a re-import so we see the resolution under whatever env state
    # the caller has set.
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    try:
        mod = importlib.import_module(mod_name)
    except Exception as exc:  # noqa: BLE001
        return {"_import_error": f"{type(exc).__name__}: {exc}"}
    out: dict = {}
    for attr, canary in attrs.items():
        if not hasattr(mod, attr):
            out[attr] = {"present": False}
            continue
        val = getattr(mod, attr)
        rec = {
            "present": True,
            "value": str(val),
            "exists": bool(val and os.path.isdir(str(val))),
        }
        if canary:
            rec["has_canary"] = bool(
                val and os.path.exists(os.path.join(str(val), canary))
            )
        out[attr] = rec
    return out


def run_probe() -> dict:
    """Run the full 4-loader resolver probe + persist results."""
    host_root: str | None = None
    from src.prediction._paths import host_repo_root  # noqa: PLC0415
    host_root = host_repo_root(project_dir=PROJECT_DIR)

    # Pass 1 — no env vars set, inherit whatever state the harness has.
    saved_env = {
        k: os.environ.get(k)
        for k in ("NBA_MODEL_DIR", "NBA_DATA_DIR", "NBA_INJURY_CACHE_DIR")
    }
    for k in saved_env:
        os.environ.pop(k, None)

    no_env = {
        "prop_pergame": _module_obs(
            "src.prediction.prop_pergame",
            {"_MODEL_DIR": "props_pg_pts.json"},
        ),
        "game_models": _module_obs(
            "src.prediction.game_models",
            {
                "_MODEL_DIR": "game_game_total.json",
                "_M2_FAMILY_DIR": "manifest.json",
            },
        ),
        "residual_heads": _module_obs(
            "src.prediction.residual_heads",
            {
                "HEAD_DIR": "pts.lgb",
                "HEAD_DIR_ENDQ2": "pts.lgb",
                "HEAD_DIR_ENDQ1": "pts.lgb",
            },
        ),
        "injury_availability": _module_obs(
            "src.prediction.injury_availability",
            {"_CACHE_DIR": None},
        ),
    }

    # Pass 2 — set NBA_DATA_DIR to the host repo's data/ and re-resolve.
    with_data_env: dict = {}
    if host_root is not None and os.path.isdir(
        os.path.join(host_root, "data")
    ):
        os.environ["NBA_DATA_DIR"] = os.path.join(host_root, "data")
        with_data_env = {
            "prop_pergame": _module_obs(
                "src.prediction.prop_pergame",
                {"_MODEL_DIR": "props_pg_pts.json"},
            ),
            "game_models": _module_obs(
                "src.prediction.game_models",
                {
                    "_MODEL_DIR": "game_game_total.json",
                    "_M2_FAMILY_DIR": "manifest.json",
                },
            ),
            "residual_heads": _module_obs(
                "src.prediction.residual_heads",
                {
                    "HEAD_DIR": "pts.lgb",
                    "HEAD_DIR_ENDQ2": "pts.lgb",
                    "HEAD_DIR_ENDQ1": "pts.lgb",
                },
            ),
            "injury_availability": _module_obs(
                "src.prediction.injury_availability",
                {"_CACHE_DIR": None},
            ),
        }
        del os.environ["NBA_DATA_DIR"]

    # Restore env so subsequent imports see the same state as on entry.
    for k, v in saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    def _summarise(pass_data: dict) -> dict:
        n_resolved = 0
        n_total = 0
        for mod_name, attrs in pass_data.items():
            for attr_name, rec in attrs.items():
                if not isinstance(rec, dict) or not rec.get("present"):
                    continue
                n_total += 1
                # "Resolved" means the dir EXISTS (graceful default counts;
                # canary presence indicates artifacts are loadable too).
                if rec.get("exists"):
                    n_resolved += 1
        return {"n_resolved": n_resolved, "n_total": n_total}

    result = {
        "probe":      "R31_X2",
        "timestamp":  datetime.utcnow().isoformat() + "Z",
        "project_dir": PROJECT_DIR,
        "host_root":   host_root,
        "in_worktree": host_root is not None,
        "no_env_pass": no_env,
        "no_env_summary": _summarise(no_env),
        "with_data_env_pass": with_data_env,
        "with_data_env_summary": _summarise(with_data_env) if with_data_env
                                  else None,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    return result


if __name__ == "__main__":
    out = run_probe()
    print(json.dumps(out, indent=2))
    s1 = out["no_env_summary"]
    print(f"\nResolved (no env):  {s1['n_resolved']}/{s1['n_total']}")
    if out["with_data_env_summary"]:
        s2 = out["with_data_env_summary"]
        print(f"Resolved (NBA_DATA_DIR=host/data): "
              f"{s2['n_resolved']}/{s2['n_total']}")
    print(f"\nWrote -> {OUT_PATH}")
