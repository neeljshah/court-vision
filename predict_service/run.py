"""predict_service.run -- thin CLI entry point for the predict-service.

Subcommands:
  produce-once [--sport nba]  -- call produce.produce_once and print the result
  serve                       -- launch the Auto-API via uvicorn
  loop [--interval 1200]      -- run scheduler.serve_forever (blocks until Ctrl-C)

Delegates entirely to the validated modules (produce, app, scheduler); NO
business logic lives here. Port/host via env PREDICT_SERVICE_PORT /
PREDICT_SERVICE_HOST (defaults 8099 / 127.0.0.1) matching app.py conventions.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge claims; thin delegation only.

Usage:
    python -m predict_service.run produce-once --sport nba
    python -m predict_service.run serve
    python -m predict_service.run loop --interval 600
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Subcommand handlers                                                          #
# --------------------------------------------------------------------------- #

def _cmd_produce_once(args: argparse.Namespace) -> int:
    """Produce + persist one SnapshotEnvelope for --sport (default nba)."""
    from predict_service import produce, store  # noqa: PLC0415
    sport = str(args.sport).lower()
    out_dir = getattr(args, "out_dir", None)
    try:
        path = produce.produce_once(sport, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001
        logger.error("produce-once failed for %s: %s", sport, exc)
        print("ERROR: produce-once failed for %s: %s" % (sport, exc),
              file=sys.stderr)
        return 1
    env = store.read_latest(sport, out_dir=out_dir)
    print("sport=%s status=%s predictions=%d edges=%d" % (
        sport, env.status, len(env.predictions), len(env.edges)))
    print("saved=%s" % path)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Launch the Auto-API (predict_service.app:app) via uvicorn."""
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:
        print("ERROR: uvicorn is not installed -- pip install uvicorn",
              file=sys.stderr)
        return 1
    from predict_service.app import app  # noqa: PLC0415
    port = int(os.environ.get("PREDICT_SERVICE_PORT", "8099"))
    host = os.environ.get("PREDICT_SERVICE_HOST", "127.0.0.1")
    print("Serving predict-service Auto-API on "
          "http://{}:{}/  (Ctrl-C to stop)".format(host, port))
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def _cmd_loop(args: argparse.Namespace) -> int:
    """Run the always-on producer scheduler (blocks; use Ctrl-C to stop)."""
    from predict_service import scheduler  # noqa: PLC0415
    interval = int(args.interval)
    out_dir = getattr(args, "out_dir", None)
    print("Starting predict-service scheduler loop (interval=%ds)..." % interval)
    try:
        scheduler.serve_forever(interval=interval, out_dir=out_dir)
    except KeyboardInterrupt:
        print("Scheduler stopped.")
    return 0


# --------------------------------------------------------------------------- #
# Parser                                                                       #
# --------------------------------------------------------------------------- #

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="predict_service.run",
        description=(
            "predict-service CLI: produce-once | serve | loop. "
            "Calibrated decision-support only; no $ edge is claimed."
        ),
    )
    sub = ap.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    sub.required = True

    # produce-once
    p_produce = sub.add_parser(
        "produce-once",
        help="Produce + persist one SnapshotEnvelope for --sport (default nba).",
    )
    p_produce.add_argument("--sport", default="nba",
                           help="Sport key, e.g. nba | mlb | soccer (default: nba).")
    p_produce.add_argument("--out-dir", default=None, dest="out_dir",
                           help="Override store output directory (optional).")
    p_produce.set_defaults(func=_cmd_produce_once)

    # serve
    p_serve = sub.add_parser(
        "serve",
        help=(
            "Launch the Auto-API (predict_service.app:app) on "
            "PREDICT_SERVICE_HOST:PREDICT_SERVICE_PORT (default 127.0.0.1:8099)."
        ),
    )
    p_serve.set_defaults(func=_cmd_serve)

    # loop
    p_loop = sub.add_parser(
        "loop",
        help="Run the always-on producer scheduler (blocks until Ctrl-C).",
    )
    p_loop.add_argument(
        "--interval", type=int, default=1200,
        help="Polling interval in seconds (default: 1200).",
    )
    p_loop.add_argument("--out-dir", default=None, dest="out_dir",
                        help="Override store output directory (optional).")
    p_loop.set_defaults(func=_cmd_loop)

    return ap


# --------------------------------------------------------------------------- #
# Entry points                                                                 #
# --------------------------------------------------------------------------- #

def main(argv: Optional[List[str]] = None) -> int:
    """Parse *argv* (or sys.argv[1:]) and dispatch to the subcommand handler."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    ap = _build_parser()
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
