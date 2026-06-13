"""daily_obs.py — Read-only daily observability composer.

Composes three existing obs modules into one consolidated daily report dict:
    {
        "generated_at": "<ISO-8601 UTC>",
        "health":       <health_snapshot.snapshot() output>,
        "slos":         <slo.evaluate(context, sink) output>,
        "drift":        <drift_report.build_report() output>,
    }

The default mode is --dry-run (prints report, fires NO alerts, writes nothing).
An explicit ``alert_sink`` must be passed to ``build_daily_report()`` to route
SLO breaches anywhere — no alerts are fired by default.

Usage (CLI)::

    python scripts/platformkit/obs/daily_obs.py          # dry-run: print JSON
    python -m scripts.platformkit.obs.daily_obs           # same via module

Importable API::

    from scripts.platformkit.obs.daily_obs import build_daily_report
    report = build_daily_report()   # pure, offline, no alerts
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repo-root / sys.path wiring (mirrors the pattern used in sibling modules)
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Walk up from __file__ until a directory containing CLAUDE.md is found."""
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[3]  # fallback


REPO_ROOT: Path = _find_repo_root()
_OBS_DIR: Path = Path(__file__).resolve().parent

# Add obs/ to sys.path so siblings are importable as bare names (same
# pattern used by test_health_snapshot.py and test_slo.py).
if str(_OBS_DIR) not in sys.path:
    sys.path.insert(0, str(_OBS_DIR))


# ---------------------------------------------------------------------------
# Lazy imports of the three sub-modules
# ---------------------------------------------------------------------------

def _import_health_snapshot() -> Any:
    """Lazy import of health_snapshot module."""
    try:
        import health_snapshot as _hs  # noqa: PLC0415
        return _hs
    except ImportError:
        # Fallback: try via package path
        import importlib  # noqa: PLC0415
        spec_path = str(_OBS_DIR / "health_snapshot.py")
        import importlib.util  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location("health_snapshot", spec_path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod


def _import_slo() -> Any:
    """Lazy import of slo module."""
    try:
        import slo as _slo  # noqa: PLC0415
        return _slo
    except ImportError:
        import importlib.util  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location("slo", str(_OBS_DIR / "slo.py"))
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod


def _import_drift_report() -> Any:
    """Lazy import of drift_report module."""
    try:
        import drift_report as _dr  # noqa: PLC0415
        return _dr
    except ImportError:
        import importlib.util  # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "drift_report", str(_OBS_DIR / "drift_report.py")
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod


# ---------------------------------------------------------------------------
# Null alert sink — default for build_daily_report
# ---------------------------------------------------------------------------

def _null_sink(slo_name: str, detail: str) -> None:  # noqa: ARG001
    """No-op alert sink: swallows all SLO breach notifications silently."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

AlertSink = Callable[[str, str], None]


def build_daily_report(
    alert_sink: Optional[AlertSink] = None,
) -> Dict[str, Any]:
    """Build and return the consolidated daily observability report.

    Composes health_snapshot.snapshot(), slo.evaluate(), and
    drift_report.build_report() into a single JSON-serialisable dict.

    Args:
        alert_sink: Optional callable ``(slo_name: str, detail: str) -> None``
            invoked by the SLO evaluator for each breach.  Defaults to a
            no-op sink — no alerts are fired unless an explicit sink is
            provided.

    Returns:
        Dict with keys: ``generated_at``, ``health``, ``slos``, ``drift``.
        All sub-reports degrade gracefully when data files are absent.

    Side-effects:
        None (read-only).  The sub-modules write nothing by default.
    """
    sink = alert_sink if alert_sink is not None else _null_sink

    # --- 1. Health snapshot -------------------------------------------------
    health: Dict[str, Any]
    try:
        hs_mod = _import_health_snapshot()
        health = hs_mod.snapshot()
    except Exception as exc:  # noqa: BLE001
        log.warning("health_snapshot.snapshot() failed: %s", exc)
        health = {"error": str(exc)}

    # --- 2. SLO evaluation --------------------------------------------------
    slos: List[Dict[str, Any]]
    try:
        slo_mod = _import_slo()
        # Pass the health snapshot as context so SLOs evaluate against
        # live health data without a second network call.
        slos = slo_mod.evaluate(context=health, alert_sink=sink)
    except Exception as exc:  # noqa: BLE001
        log.warning("slo.evaluate() failed: %s", exc)
        slos = [{"error": str(exc)}]

    # --- 3. Drift report ----------------------------------------------------
    drift: Dict[str, Any]
    try:
        dr_mod = _import_drift_report()
        drift = dr_mod.build_report()
    except Exception as exc:  # noqa: BLE001
        log.warning("drift_report.build_report() failed: %s", exc)
        drift = {"error": str(exc)}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "health": health,
        "slos": slos,
        "drift": drift,
    }


# ---------------------------------------------------------------------------
# CLI entry point (dry-run by default)
# ---------------------------------------------------------------------------

def _summarise(report: Dict[str, Any]) -> str:
    """Return a one-line human-readable summary of the report."""
    slos: List[Dict[str, Any]] = report.get("slos", [])
    breached = [s["name"] for s in slos if isinstance(s, dict) and not s.get("ok", True)]
    drift_flags: List[str] = report.get("drift", {}).get("all_flags", [])
    health_err = "error" in report.get("health", {})

    parts = []
    if breached:
        parts.append(f"SLO breaches: {', '.join(breached)}")
    else:
        parts.append("SLOs: all OK")
    if drift_flags:
        parts.append(f"drift flags: {len(drift_flags)}")
    else:
        parts.append("drift: clean")
    if health_err:
        parts.append("health: error")
    return " | ".join(parts)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point.  Default mode: dry-run (print JSON, fire no alerts).

    Args:
        argv: Optional argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success).
    """
    import argparse  # noqa: PLC0415

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        prog="daily_obs",
        description="Compose health + SLO + drift into one daily report (read-only).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(default) Print composed report; fire no alerts, write nothing.",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Reserved for future use — no current effect (compose + print still happens).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output raw JSON (default: pretty-printed JSON).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    report = build_daily_report()  # null sink → no alerts

    indent = None if args.json else 2
    print(json.dumps(report, indent=indent, default=str))
    print(f"\n# {_summarise(report)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
