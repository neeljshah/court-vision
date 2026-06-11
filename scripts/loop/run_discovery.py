"""scripts/loop/run_discovery.py — LLM-free autonomous feature proposer CLI.

Runs the deterministic discovery engine (``src.loop.discovery.discover``) for
one or more target stats, records every verdict to the discovered-signals ledger
(``.planning/loop/discovered_signals.jsonl``), and prints a per-target verdict
table.  The honest gate inside ``discover()`` decides what ships; this script is
purely a scheduler / reporter.

NOTE: Do NOT run this during tests or CI — ``discover()`` loads the full
per-game matrix (~30 s + GPU XGBoost).  The unit tests in
``tests/test_brain_discovery_cli.py`` monkeypatch ``discover`` and
``record_discovered`` so no heavy I/O occurs.

Usage examples::

    # discover for pts (default)
    python scripts/loop/run_discovery.py

    # run all 7 stat targets
    python scripts/loop/run_discovery.py --targets all

    # discover for reb + ast on CPU, top-8 candidates each
    python scripts/loop/run_discovery.py --targets reb ast --top-k 8 --device cpu

    # override the date tag written into the ledger
    python scripts/loop/run_discovery.py --date 2026-06-09

Options:
    --targets     One or more stat names, or the special value 'all' which expands to
                  all 7 pergame stats (pts reb ast fg3m stl blk tov).
    --top-k       Number of top-screened candidates to pass to the honest gate (default 8).
    --device      XGBoost device string: 'auto' (default) | 'cuda' | 'cpu'.
    --date        ISO date tag written into the ledger (default: today).
    --ledger      Override the discovered-signals ledger path.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Make the repo root importable regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Ensure src/ sub-packages resolve correctly.
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.loop.discovery import discover, load_discovered_families, record_discovered  # noqa: E402
from src.loop.signal import Verdict  # noqa: E402

_ALL_TARGETS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def run(
    targets: List[str],
    *,
    top_k: int,
    device: str,
    date: str,
    ledger_path: Optional[str] = None,
) -> Dict[str, dict]:
    """Run the discovery engine for each target and record verdicts to the ledger.

    Does NOT call ``datetime`` internally — the caller passes ``date`` so tests
    can inject a fixed date without monkeypatching time.

    Args:
        targets:      List of stat target strings (e.g. ``["pts", "reb"]``).
        top_k:        Number of screened candidates forwarded to the gate per target.
        device:       XGBoost device string: ``"auto" | "cuda" | "cpu"``.
        date:         ISO date string tagged onto every ledger record (``"YYYY-MM-DD"``).
        ledger_path:  Override the default discovered-signals ledger path.  If
                      ``None``, the discovery module's default path is used.

    Returns:
        Summary dict keyed by target::

            {
              "pts": {
                "n": 8,
                "tally": {"SHIP": 0, "REJECT": 7, "VARIANCE_ONLY": 1, "DEFER": 0},
                "ships": [],
                "variance": ["disc_zscore__pts_l5"],
              },
              ...
            }
    """
    record_kwargs: dict = {}
    if ledger_path is not None:
        record_kwargs["path"] = ledger_path

    summary: Dict[str, dict] = {}

    for target in targets:
        # Load already-seen family keys to avoid re-rolling tested candidates.
        seen = load_discovered_families(
            **({} if ledger_path is None else {"path": ledger_path})
        )

        results = discover(target, top_k=top_k, device=device, seen_families=seen)

        tally: Dict[str, int] = {v.value: 0 for v in Verdict}
        ships: List[str] = []
        variance: List[str] = []

        for dr in results:
            record_discovered(dr, date=date, **record_kwargs)
            verdict_val = dr.gate.verdict.value
            tally[verdict_val] = tally.get(verdict_val, 0) + 1
            if dr.gate.verdict == Verdict.SHIP:
                ships.append(dr.spec.name)
            elif dr.gate.verdict == Verdict.VARIANCE_ONLY:
                variance.append(dr.spec.name)

        summary[target] = {
            "n": len(results),
            "tally": tally,
            "ships": ships,
            "variance": variance,
        }

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_summary(summary: Dict[str, dict], results_map: Dict[str, list]) -> None:
    """Print a readable per-target verdict table to stdout."""
    sep = "-" * 68
    for target, info in summary.items():
        print(sep)
        print(f"  Target: {target}  |  candidates gated: {info['n']}")
        tally = info["tally"]
        tally_str = "  ".join(
            f"{k}:{v}" for k, v in tally.items() if v > 0
        )
        print(f"  Verdict tally : {tally_str or '(none)'}")

        # SHIP details
        ships = info["ships"]
        if ships:
            print(f"  SHIP ({len(ships)}):")
            for name in ships:
                dr = next((r for r in results_map.get(target, [])
                           if r.spec.name == name), None)
                if dr is not None:
                    nz = dr.gate.metrics.get("null_z", 0.0)
                    print(f"    {name}")
                    print(f"      screen_score={dr.screen_score:.4f}  null_z={nz:.3f}")
                else:
                    print(f"    {name}")

        # VARIANCE_ONLY details
        variance = info["variance"]
        if variance:
            print(f"  VARIANCE_ONLY ({len(variance)}):")
            for name in variance:
                dr = next((r for r in results_map.get(target, [])
                           if r.spec.name == name), None)
                if dr is not None:
                    nz = dr.gate.metrics.get("null_z", 0.0)
                    print(f"    {name}")
                    print(f"      screen_score={dr.screen_score:.4f}  null_z={nz:.3f}")
                else:
                    print(f"    {name}")

    print(sep)


def main(argv=None) -> int:
    """Entry point for the discovery CLI.

    Returns:
        0 on success, 1 on fatal error.
    """
    parser = argparse.ArgumentParser(
        prog="run_discovery",
        description=(
            "LLM-free autonomous feature proposer: enumerate transforms -> "
            "cheap screen -> honest gate decides.  Ledger records every verdict "
            "to prevent re-rolling tested candidates."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["pts"],
        metavar="STAT",
        help=(
            "Target stat(s) to discover for (default: pts). "
            "Special value 'all' expands to: " + " ".join(_ALL_TARGETS) + "."
        ),
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
        dest="top_k",
        help="Top-K screened candidates forwarded to the honest gate per target (default 8).",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="XGBoost device string (default: auto -> cuda if available, else cpu).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="ISO date tag for ledger records (default: today's date).",
    )
    parser.add_argument(
        "--ledger",
        default=None,
        metavar="PATH",
        help="Override the discovered-signals ledger file path.",
    )

    args = parser.parse_args(argv)

    # Expand 'all' -> all 7 targets.
    raw_targets: List[str] = args.targets
    if len(raw_targets) == 1 and raw_targets[0] == "all":
        targets = list(_ALL_TARGETS)
    else:
        targets = raw_targets

    # Compute today's date HERE (in main), not inside run().
    date_str: str = args.date or datetime.date.today().isoformat()

    print(
        f"[run_discovery] targets={targets}  top_k={args.top_k}"
        f"  device={args.device}  date={date_str}"
    )
    if args.ledger:
        print(f"[run_discovery] ledger override: {args.ledger}")

    # Capture raw results for the detailed per-spec print.
    results_map: Dict[str, list] = {}

    def _patched_run() -> Dict[str, dict]:
        """Thin wrapper that also captures DiscoveryResult objects for printing."""
        record_kwargs: dict = {}
        if args.ledger:
            record_kwargs["path"] = args.ledger

        summary: Dict[str, dict] = {}
        for target in targets:
            seen = load_discovered_families(
                **({} if args.ledger is None else {"path": args.ledger})
            )
            drs = discover(target, top_k=args.top_k, device=args.device,
                           seen_families=seen)
            results_map[target] = drs

            tally: Dict[str, int] = {v.value: 0 for v in Verdict}
            ships: List[str] = []
            variance: List[str] = []
            for dr in drs:
                record_discovered(dr, date=date_str, **record_kwargs)
                verdict_val = dr.gate.verdict.value
                tally[verdict_val] = tally.get(verdict_val, 0) + 1
                if dr.gate.verdict == Verdict.SHIP:
                    ships.append(dr.spec.name)
                elif dr.gate.verdict == Verdict.VARIANCE_ONLY:
                    variance.append(dr.spec.name)

            summary[target] = {"n": len(drs), "tally": tally,
                                "ships": ships, "variance": variance}
        return summary

    try:
        summary = _patched_run()
    except Exception as exc:
        print(f"[run_discovery] FATAL: {exc}", file=sys.stderr)
        return 1

    _print_summary(summary, results_map)
    return 0


if __name__ == "__main__":
    sys.exit(main())
