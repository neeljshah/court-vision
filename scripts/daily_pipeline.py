"""
daily_pipeline.py -- Single command run each morning.

Steps (in order):
  1. Refresh injury reports
  2. Fetch today's props (DK, 15min TTL) -> data/props/props_{today}.json
  3. Run full prediction cascade + edge detection
  4. Log predictions to outcome recorder (CLV tracking)
  5. Print + save edge report -> data/edges/edges_{today}.json
  6. Check auto_retrain milestones
  7. Check feature drift (2-sigma statistical threshold)
  8. Print summary

Usage:
    conda activate basketball_ai
    python scripts/daily_pipeline.py [--min-ev 0.03] [--season 2025-26] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date as _date

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("daily_pipeline")

TODAY = _date.today().isoformat()


def _step(n: int, label: str) -> None:
    log.info("--- Step %d: %s", n, label)


def _ok(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    log.info("    ✓ %s%s", label, suffix)


def _warn(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    log.warning("    ✗ %s%s", label, suffix)


# -- Step 1 -- Refresh injuries -------------------------------------------------

def step_injuries() -> dict:
    _step(1, "Refresh injury reports")
    result: dict = {"status": "ok", "players": 0}
    try:
        from src.data.injury_monitor import InjuryMonitor
        summary = InjuryMonitor().refresh()
        n = len(summary) if isinstance(summary, (list, dict)) else 0
        _ok("Injury reports refreshed", f"{n} entries")
        result["players"] = n
    except Exception as e:
        _warn("Injury refresh", str(e))
        result["status"] = "failed"
    return result


# -- Step 2 -- Fetch props ------------------------------------------------------

def step_props(dry_run: bool = False) -> dict:
    _step(2, "Fetch today's props (DraftKings)")
    result: dict = {"status": "ok", "props": 0, "path": None}
    try:
        from src.data.props_scraper import get_current_props
        props = get_current_props("draftkings") if not dry_run else []
        n = len(props)

        props_dir = os.path.join(PROJECT_DIR, "data", "props")
        os.makedirs(props_dir, exist_ok=True)
        path = os.path.join(props_dir, f"props_{TODAY}.json")
        if not dry_run:
            with open(path, "w") as f:
                json.dump(props, f, indent=2)
        _ok("Props saved", f"{n} player lines -> {path}")
        result["props"] = n
        result["path"] = path
    except Exception as e:
        _warn("Props fetch", str(e))
        result["status"] = "failed"
    return result


# -- Step 3 -- Prediction cascade + edges --------------------------------------

def step_predict(min_ev: float, season: str, dry_run: bool = False) -> tuple[list, dict]:
    _step(3, f"Prediction cascade + edge detection (min_ev={min_ev})")
    edges: list = []
    result: dict = {"status": "ok", "edges": 0}
    if dry_run:
        _ok("Dry run -- skipping prediction cascade")
        return edges, result
    try:
        from src.pipeline.prediction_orchestrator import PredictionOrchestrator
        orch = PredictionOrchestrator(season=season)
        edges = orch.get_today_edges(min_ev=min_ev) or []
        _ok("Prediction cascade complete", f"{len(edges)} edges found")
        result["edges"] = len(edges)
    except Exception as e:
        _warn("Prediction cascade", str(e))
        result["status"] = "failed"
    return edges, result


# -- Step 4 -- Log predictions for CLV -----------------------------------------

def step_log_predictions(edges: list, dry_run: bool = False) -> dict:
    _step(4, "Log predictions to outcome recorder (CLV tracking)")
    result: dict = {"status": "ok"}
    if dry_run:
        _ok("Dry run -- skipping log")
        return result
    try:
        from src.pipeline.outcome_recorder import log_predictions
        log_predictions(edges)
        _ok("Predictions logged", f"{len(edges)} edges -> data/predictions/predictions_{TODAY}.json")
    except Exception as e:
        _warn("Log predictions", str(e))
        result["status"] = "failed"
    return result


# -- Step 5 -- Edge report ------------------------------------------------------

def step_edge_report(edges: list, dry_run: bool = False) -> dict:
    _step(5, "Print + save edge report")
    result: dict = {"status": "ok", "path": None}
    try:
        from src.analytics.edge_detector import EdgeDetector
        report = EdgeDetector().format_edge_report(edges)
        print("\n" + report)

        if not dry_run:
            edges_dir = os.path.join(PROJECT_DIR, "data", "edges")
            os.makedirs(edges_dir, exist_ok=True)
            path = os.path.join(edges_dir, f"edges_{TODAY}.json")

            def _edge_to_dict(e):
                if isinstance(e, dict):
                    return e
                return {k: getattr(e, k, None) for k in (
                    "player_id", "player_name", "stat", "direction",
                    "line", "projection", "ev", "kelly_fraction",
                    "confidence", "model_agreement", "game_id", "date",
                )}

            with open(path, "w") as f:
                json.dump([_edge_to_dict(e) for e in edges], f, indent=2)
            _ok("Edge report saved", path)
            result["path"] = path
    except Exception as e:
        _warn("Edge report", str(e))
        result["status"] = "failed"
    return result


# -- Step 6 -- Auto retrain -----------------------------------------------------

def step_retrain(season: str, dry_run: bool = False) -> dict:
    _step(6, f"Check auto_retrain milestones (season={season})")
    result: dict = {"status": "ok", "retrained": []}
    if dry_run:
        _ok("Dry run -- skipping retrain check")
        return result
    try:
        from src.pipeline.auto_retrain import check_and_retrain
        summary = check_and_retrain(game_id="daily_check", season=season)
        retrained = summary if isinstance(summary, list) else []
        _ok("Retrain check complete", f"{len(retrained)} models retrained")
        result["retrained"] = retrained
    except Exception as e:
        _warn("Auto retrain", str(e))
        result["status"] = "failed"
    return result


# -- Step 7 -- Feature drift check ---------------------------------------------

def step_drift() -> dict:
    """Check feature importance drift using 2-sigma statistical threshold."""
    _step(7, "Check feature drift (2-sigma)")
    try:
        from src.pipeline.feature_drift_detector import FeatureDriftDetector
        detector = FeatureDriftDetector()
        report = detector.run_full_check()
        degraded = report.get("degraded_models", [])
        if degraded:
            _warn("Drift alert", f"{len(degraded)} models degraded: {', '.join(degraded)}")
        else:
            _ok("Drift check", f"{len(report.get('model_drift', {}))} models healthy")
        return {"status": "ok", "degraded_models": degraded}
    except Exception as exc:  # noqa: BLE001
        _warn("Drift check", str(exc))
        return {"status": "failed"}


# -- Step 8 -- Summary ----------------------------------------------------------

def step_summary(
    injuries: dict,
    props: dict,
    predict: dict,
    retrain: dict,
    edges: list,
) -> None:
    _step(8, "Daily summary")
    n_edges = len(edges)
    print("\n" + "=" * 60)
    print(f"  NBA AI Daily Pipeline -- {TODAY}")
    print("=" * 60)
    print(f"  Injury alerts : {injuries.get('players', 0)} players")
    print(f"  Props fetched : {props.get('props', 0)} lines")
    print(f"  Edges found   : {n_edges} (min_ev threshold applied)")

    # Top 3 edges by EV
    if edges:
        print("\n  Top 3 edges by EV:")
        top = sorted(edges, key=lambda e: float(getattr(e, "ev", 0) if not isinstance(e, dict) else e.get("ev", 0)), reverse=True)[:3]
        for i, edge in enumerate(top, 1):
            if isinstance(edge, dict):
                name = edge.get("player_name", "?")
                stat = edge.get("stat", "?")
                ev   = edge.get("ev", 0)
                line = edge.get("line", "?")
                proj = edge.get("projection", "?")
            else:
                name = getattr(edge, "player_name", "?")
                stat = getattr(edge, "stat", "?")
                ev   = getattr(edge, "ev", 0)
                line = getattr(edge, "line", "?")
                proj = getattr(edge, "projection", "?")
            print(f"    {i}. {name} {stat} | proj={proj:.1f} line={line} EV={ev:.3f}")

    retrained = retrain.get("retrained", [])
    if retrained:
        print(f"\n  Models retrained: {', '.join(retrained)}")
    else:
        print("\n  No models retrained today")
    print("=" * 60 + "\n")


# -- Main ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="NBA AI daily morning pipeline")
    parser.add_argument("--min-ev",  type=float, default=0.03, help="Minimum EV to flag an edge")
    parser.add_argument("--season",  default="2025-26", help="NBA season string")
    parser.add_argument("--dry-run", action="store_true", help="Log steps without writing or fetching live data")
    args = parser.parse_args()

    log.info("Starting daily pipeline -- %s  (dry_run=%s)", TODAY, args.dry_run)

    injuries = step_injuries()
    props    = step_props(dry_run=args.dry_run)
    edges, predict_result = step_predict(args.min_ev, args.season, dry_run=args.dry_run)
    step_log_predictions(edges, dry_run=args.dry_run)
    step_edge_report(edges, dry_run=args.dry_run)
    retrain  = step_retrain(args.season, dry_run=args.dry_run)
    step_drift()
    step_summary(injuries, props, predict_result, retrain, edges)


if __name__ == "__main__":
    main()
