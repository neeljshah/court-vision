"""probe_R28_U5_morning_brief.py — end-to-end probe for the operator brief.

Generates a brief against the REAL data sources but writes the output to a
probe-scoped temp path (NEVER ``vault/MORNING.md``). Verifies the 8
sections are all present in the rendered body, the file size is sane,
and persists results to ``data/cache/probe_R28_U5_results.json``.

Hard rules
----------
* LOCAL only.
* Never writes to ``vault/MORNING.md``.
* Never writes to ``data/backups/`` or any production cache.
* Read-only against every data source.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts import generate_morning_brief as mb  # noqa: E402

PROBE_RESULTS_PATH = os.path.join(
    _ROOT, "data", "cache", "probe_R28_U5_results.json"
)

EXPECTED_HEADINGS = (
    "# Morning Brief",
    "## Bankroll",
    "## Yesterday's Recs",
    "## Today's Top Recs",
    "## System Health",
    "## Recent Alerts",
    "## Feature Drift",
    "## Backup + Smoke",
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stub_engine_fn(*_args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Avoid running the real live_rec_engine in the probe — it depends on
    a fresh predictions_cache + line snapshots being present. We probe
    the brief renderer, not the engine."""
    return {
        "engine_version": "R23_P8 (probe stub)",
        "date":           kwargs.get("date") or _iso_now()[:10],
        "n_evaluated":    0,
        "n_recs":         0,
        "recommendations": [],
        "reason":         "probe stub — real engine not invoked",
    }


def _run_probe() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "probe":      "R28_U5",
        "started_at": _iso_now(),
    }
    try:
        # Probe-scoped output path so we NEVER touch vault/MORNING.md.
        tmp_dir = Path(tempfile.mkdtemp(prefix="R28_U5_probe_"))
        out_path = tmp_dir / "MORNING_probe.md"
        out["out_path"] = str(out_path)

        # Real data sources (read-only) from the maintainer's workspace.
        # The probe falls back to the worktree's own data/ first then to
        # the canonical maintainer path two levels up (matches R27_T7's
        # pattern for fresh-clone-friendly probing).
        candidate_roots = [
            Path(_ROOT),
            Path(_ROOT).parent.parent.parent,
        ]
        sources = {
            "bankroll_path":  None,
            "settled_path":   None,
            "registry_path":  None,
            "heartbeat_dir":  None,
            "alerts_vault":   None,
            "alerts_dir":     None,
            "drift_cache":    None,
            "backup_dir":     None,
            "smoke_dir":      None,
        }
        for root in candidate_roots:
            picks = {
                "bankroll_path": root / "data" / "cache" / "bankroll_state.json",
                "settled_path":  root / "data" / "cache" / "rec_tracker" / "rec_settled.parquet",
                "registry_path": root / "scripts" / "daemon_registry.json",
                "heartbeat_dir": root / "data" / "cache" / "daemon_heartbeats",
                "alerts_vault":  root / "vault" / "Improvements" / "alerts.md",
                "alerts_dir":    root / "data" / "cache" / "alerts",
                "drift_cache":   root / "data" / "cache" / "feature_drift_latest.json",
                "backup_dir":    root / "data" / "backups",
                "smoke_dir":     root / "data" / "cache",
            }
            for k, p in picks.items():
                if sources[k] is None and p.exists():
                    sources[k] = p
        # Fill any still-missing source with a known-nonexistent path so the
        # generator exercises its degrade-gracefully path for that section.
        for k, v in list(sources.items()):
            if v is None:
                sources[k] = tmp_dir / f"_missing_{k}"

        out["sources_resolved"] = {k: str(v) for k, v in sources.items()}

        res = mb.generate(
            out_path=out_path,
            bankroll_path=sources["bankroll_path"],
            settled_path=sources["settled_path"],
            registry_path=sources["registry_path"],
            heartbeat_dir=sources["heartbeat_dir"],
            alerts_vault=sources["alerts_vault"],
            alerts_dir=sources["alerts_dir"],
            drift_cache=sources["drift_cache"],
            backup_dir=sources["backup_dir"],
            smoke_dir=sources["smoke_dir"],
            engine_fn=_stub_engine_fn,
        )
        out["generate_ok"] = bool(res.get("ok"))
        out["size_bytes"] = int(res.get("size_bytes", 0) or 0)
        out["n_sections"] = int(res.get("n_sections", 0) or 0)
        out["n_sections_with_data"] = int(
            res.get("n_sections_with_data", 0) or 0
        )

        # Read the rendered brief and verify each expected heading is present.
        body = out_path.read_text(encoding="utf-8")
        present = []
        missing = []
        for h in EXPECTED_HEADINGS:
            (present if h in body else missing).append(h)
        out["headings_present"] = present
        out["headings_missing"] = missing
        out["all_sections_present"] = (len(missing) == 0)
        out["size_in_range"] = (500 <= out["size_bytes"] <= 50_000)

        # Sanity — file isn't dumped on top of vault/MORNING.md.
        out["touched_real_vault"] = (
            str(Path(out_path)).endswith("vault/MORNING.md")
            or str(Path(out_path)).endswith("vault\\MORNING.md")
        )

        out["ship_ok"] = bool(
            out.get("generate_ok")
            and out.get("all_sections_present")
            and out.get("size_in_range")
            and not out.get("touched_real_vault")
        )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        out["error"] = repr(exc)
        out["ship_ok"] = False

    out["ended_at"] = _iso_now()
    return out


def main() -> int:
    os.makedirs(os.path.dirname(PROBE_RESULTS_PATH), exist_ok=True)
    try:
        result = _run_probe()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        result = {
            "probe":     "R28_U5",
            "timestamp": _iso_now(),
            "ship_ok":   False,
            "error":     repr(exc),
        }
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ship_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
