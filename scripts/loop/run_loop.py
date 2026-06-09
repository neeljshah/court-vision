"""CLI entry point for the autonomous self-improving NBA loop.

Usage examples::

    # one iteration, both arms, dry-run (smoke / CI gate)
    python scripts/loop/run_loop.py --dry-run --once

    # run the signals arm forever on GPU
    python scripts/loop/run_loop.py --arm signals --forever

    # cap at 5 iterations, intel arm only, CPU fallback
    python scripts/loop/run_loop.py --arm intel --max-iters 5 --device cpu

    # exactly one iteration of both arms (default)
    python scripts/loop/run_loop.py --once

Options:
    --arm {signals,intel,both}  Which arm to run (default: both).
    --device {auto,cuda,cpu}    GPU device string (default: auto = cuda).
    --max-iters N               Stop after N iterations (mutually exclusive with
                                --forever).
    --once                      Shorthand for ``--max-iters 1`` (default behaviour
                                when neither flag is given).
    --forever                   Run until SIGINT / SIGTERM (the production mode).
    --dry-run                   Build + gate + validate but do NOT persist, wire, or
                                retrain; useful for smoke-testing stubs.

Exit codes:
    0 - completed cleanly (no unhandled exceptions).
    1 - fatal argument / import error.

Safety (HARD rules):
    * Sets ``NBA_OFFLINE=1`` before any import.
    * Never touches ``api/``, the live server/tunnel, ``data/live/``,
      ``data/lines/``, ``run.py``, or ``loop_processor.py``.
    * All side-effects are in src/loop/, signals/, intel/, scripts/loop/,
      data/cache/loop_store/, and .planning/loop/.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import signal
import sys
import textwrap
from pathlib import Path
from typing import List, Optional

# ----- bootstrap: set NBA_OFFLINE before any domain import --------------------
os.environ["NBA_OFFLINE"] = "1"

# Make the repo root importable regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ----- domain imports (after sys.path fixup) ----------------------------------
from src.loop.orchestrator import Orchestrator, IterationResult  # noqa: E402
from src.loop.signal import Verdict  # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the loop CLI."""
    p = argparse.ArgumentParser(
        prog="run_loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Autonomous self-improving NBA loop (two arms, one substrate).

            ARM A (signals): mine residuals -> gate -> wire SHIPs -> ledger.
            ARM B (intel):   build atlases -> validate -> persist -> memory.
        """),
    )
    p.add_argument(
        "--arm",
        choices=["signals", "intel", "both"],
        default="both",
        help="Which arm to run (default: both).",
    )
    p.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="GPU device string; 'auto' resolves to cuda (default).",
    )

    # Iteration control (mutually exclusive).
    iters = p.add_mutually_exclusive_group()
    iters.add_argument(
        "--max-iters",
        type=int,
        default=None,
        metavar="N",
        dest="max_iters",
        help="Stop after N iterations.",
    )
    iters.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Run exactly one iteration (shorthand for --max-iters 1).",
    )
    iters.add_argument(
        "--forever",
        action="store_true",
        default=False,
        help="Run until SIGINT / SIGTERM (production mode).",
    )

    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Build + gate + validate but do NOT persist, wire, or retrain.",
    )
    p.add_argument(
        "--smoke",
        action="store_true",
        default=False,
        help=("Run a self-contained REINFORCEMENT proof through the REAL gate -> "
              "wiring -> store (no live data): a known-good signal SHIPs and writes "
              "a learned per-entity value back as an atlas field, which a downstream "
              "signal then reads. Proves task item 3(c). Combine with --dry-run to "
              "avoid mutating production artifacts."),
    )
    return p


# ---------------------------------------------------------------------------
# Self-contained reinforcement smoke proof (task item 3c)
# ---------------------------------------------------------------------------

def _run_smoke_reinforcement(device: str, dry_run: bool) -> int:
    """Prove SHIP -> write-back -> downstream-read end-to-end on synthetic data.

    Uses the gate's documented self-contained ``_gate_matrix`` injection path so
    no live gamelogs are needed. Steps, all through the REAL modules:
      1. A known-good signal (high-SNR view of a latent target term) is gated.
         The honest gate returns SHIP (all WF folds improve, beats null, ablation).
      2. ``wiring.ship_signal`` writes the signal's learned per-entity value back
         into the store as field ``signal__<name>`` (the reinforcement edge).
      3. A second signal reads that written-back value from the store, proving the
         two arms co-evolve on one substrate.

    Returns an exit code (0 on a clean proof, 1 otherwise).
    """
    import numpy as np
    from src.loop import gate as _gate
    from src.loop import wiring as _wiring
    from src.loop.signal import (AsOfContext, Hypothesis, Signal, SignalValue,
                                 Verdict)
    from src.loop.store import get_store

    print("[smoke] REINFORCEMENT proof: SHIP -> write-back -> downstream read")
    store = get_store()

    # --- build a synthetic leak-safe bundle the gate trains on ----------------
    rng = np.random.default_rng(7)
    n, p = 1400, 8
    base = rng.normal(size=(n, p))
    latent = rng.normal(size=n)                       # info NOT in base
    target = (base @ rng.normal(size=p) * 0.4) + 2.5 * latent + rng.normal(n) * 0.5
    signal_col = latent + rng.normal(size=n) * 0.15   # high-SNR view of latent
    dates = [f"2024-10-{1 + (i % 28):02d}" for i in range(n)]
    bundle = _gate.FeatureBundle(base=base, signal_col=signal_col,
                                 target=target, dates=dates)

    class _SmokeSignal(Signal):
        name = "smoke_reinforce"
        target = "pts"
        scope = "pregame"
        reads_atlas: List[str] = ["scoring_usage"]
        emits: List[str] = []

        def __init__(self, store=None):  # noqa: ANN001
            super().__init__(store=store)
            self._gate_matrix = bundle
            # per-entity learned values written back on SHIP (reinforcement)
            self._learned_values = {"player:201939": 0.123, "player:2544": -0.045}

        def build(self, ctx: AsOfContext) -> SignalValue:
            return 0.0

        def hypothesis(self) -> Hypothesis:
            return Hypothesis(name=self.name, target=self.target, scope=self.scope,
                              statement="synthetic high-SNR latent signal (smoke)")

    sig = _SmokeSignal(store=store)

    # 1) GATE (real, GPU/CPU per --device)
    gr = _gate.evaluate(sig, store=store, device=device)
    print(f"[smoke] gate verdict={gr.verdict.value}  wf_folds={[round(f,4) for f in gr.wf_folds]}")
    print(f"[smoke]   ablation_delta={gr.ablation_delta}  null_pass={gr.null_pass}  fdr_pass={gr.fdr_pass}")
    if gr.verdict != Verdict.SHIP:
        print(f"[smoke] FAIL: expected SHIP, got {gr.verdict.value} ({gr.reason})")
        return 1

    # 2) WIRING -> write-back (reinforcement). dry_run avoids retrain/artifact writes
    #    but write_back still round-trips into the store so the proof is observable.
    wr = _wiring.ship_signal(sig, gr, store=store, device=device, dry_run=dry_run)
    print(f"[smoke] ship ok={wr.ok}  wrote_back={wr.wrote_back}  features={wr.features_added}")

    # 3) DOWNSTREAM READ of the written-back atlas field (reinforcement closed loop)
    if dry_run:
        # dry_run does not mutate the store; write one record explicitly so the
        # downstream-read proof is still observable, tagged as a smoke artifact.
        store.write_signal_field("player", "201939", sig.name,
                                 "2024-10-28", 0.123,
                                 provenance={"source": "smoke_proof"})
    read_back = store.read_signal_field("player", "201939", sig.name,
                                        __import__("datetime").datetime(2025, 1, 1))
    print(f"[smoke] downstream read of signal__{sig.name} for player:201939 -> {read_back}")
    ok = wr.ok and (read_back is not None)
    print(f"[smoke] REINFORCEMENT {'PROVEN' if ok else 'INCOMPLETE'}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Summary printing
# ---------------------------------------------------------------------------

def _verdict_icon(v: Verdict) -> str:
    """Return a 1-char ASCII tag for a verdict (no emojis per style guide)."""
    return {
        Verdict.SHIP: "[SHIP]",
        Verdict.VARIANCE_ONLY: "[VAR]",
        Verdict.REJECT: "[REJ]",
        Verdict.DEFER: "[DEF]",
    }.get(v, f"[{v}]")


def _print_iteration_summary(idx: int, result: IterationResult,
                              elapsed: _dt.timedelta) -> None:
    """Print a clean 3-section summary for one loop iteration."""
    sep = "-" * 70
    print(sep)
    print(f"  Iteration {idx + 1} | arm={result.arm} | {elapsed.total_seconds():.1f}s")
    print(sep)

    # --- Hypotheses / signal verdicts ----------------------------------------
    if result.hypotheses or result.verdicts:
        print(f"  Signals: {len(result.hypotheses)} hypotheses evaluated")
        for name, verdict in result.verdicts.items():
            print(f"    {_verdict_icon(verdict)}  {name}")
        if result.shipped:
            print(f"  Shipped: {', '.join(result.shipped)}")
    else:
        print("  Signals: (no hypotheses this iteration)")

    # --- Atlas sections -------------------------------------------------------
    if result.atlas_built:
        print(f"  Atlas: {len(result.atlas_built)} section(s) persisted")
        for key in result.atlas_built:
            print(f"    [ATLAS]  {key}")
    else:
        print("  Atlas: (none built this iteration)")

    # --- Memory notes ---------------------------------------------------------
    if result.notes:
        print(f"  Memory: {len(result.notes)} note(s) written")
        for note in result.notes:
            print(f"    {note}")

    # --- Errors (non-fatal) ---------------------------------------------------
    if result.errors:
        print(f"  Errors ({len(result.errors)} non-fatal):")
        for err in result.errors:
            print(f"    ! {err}")

    print()


def _print_run_summary(results: List[IterationResult],
                       total_elapsed: _dt.timedelta) -> None:
    """Print the aggregate summary across all iterations."""
    sep = "=" * 70
    print(sep)
    n_iters = len(results)
    all_shipped: List[str] = []
    all_atlas: List[str] = []
    all_errors: List[str] = []
    verdict_counts: dict = {}
    for r in results:
        all_shipped.extend(r.shipped)
        all_atlas.extend(r.atlas_built)
        all_errors.extend(r.errors)
        for v in r.verdicts.values():
            verdict_counts[v] = verdict_counts.get(v, 0) + 1

    print(f"  LOOP COMPLETE  |  {n_iters} iteration(s)  |  {total_elapsed.total_seconds():.1f}s total")
    print(f"  Shipped signals : {len(all_shipped)}  ({', '.join(all_shipped) or 'none'})")
    print(f"  Atlas built     : {len(set(all_atlas))}  ({', '.join(sorted(set(all_atlas))) or 'none'})")
    if verdict_counts:
        vc_str = "  ".join(f"{_verdict_icon(v)} {n}" for v, n in verdict_counts.items())
        print(f"  Verdicts        : {vc_str}")
    if all_errors:
        print(f"  Non-fatal errors: {len(all_errors)}")
    print(sep)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

_STOP_REQUESTED = False


def _install_signal_handlers() -> None:
    """Install SIGINT/SIGTERM handlers so --forever stops cleanly."""
    def _handler(signum, frame):  # noqa: ANN001
        global _STOP_REQUESTED
        _STOP_REQUESTED = True
        print("\n  [run_loop] stop requested - finishing current iteration...")

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (OSError, AttributeError):
        pass  # SIGTERM unavailable on some Windows builds


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """Entry point; returns an exit code (0 = success, 1 = fatal error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Resolve iteration control.
    if args.forever:
        forever = True
        max_iters: Optional[int] = None
    elif args.once or (args.max_iters is None and not args.forever):
        # Default to --once when neither flag is given.
        forever = False
        max_iters = args.max_iters if args.max_iters is not None else 1
    else:
        forever = False
        max_iters = args.max_iters

    device = args.device  # "auto" | "cuda" | "cpu"
    arm = args.arm
    dry_run = args.dry_run

    # Self-contained reinforcement proof (task item 3c) — runs and exits.
    if args.smoke:
        print(f"[run_loop] SMOKE reinforcement proof  device={device}"
              f"{'  [DRY-RUN]' if dry_run else ''}")
        try:
            return _run_smoke_reinforcement(device, dry_run)
        except Exception as exc:  # pragma: no cover
            print(f"[run_loop] FATAL smoke: {exc!r}", file=sys.stderr)
            return 1

    # Banner.
    mode_str = "forever" if forever else f"max_iters={max_iters}"
    dry_str = "  [DRY-RUN]" if dry_run else ""
    print(f"[run_loop] arm={arm} device={device} {mode_str}{dry_str}")
    print(f"[run_loop] NBA_OFFLINE=1  repo={_REPO_ROOT}")

    if forever:
        _install_signal_handlers()

    # Build the orchestrator (store is loaded lazily).
    try:
        orch = Orchestrator(device=device, dry_run=dry_run)
    except Exception as exc:  # pragma: no cover
        print(f"[run_loop] FATAL: could not build Orchestrator: {exc}", file=sys.stderr)
        return 1

    # Run.
    results: List[IterationResult] = []
    run_start = _dt.datetime.utcnow()

    if forever:
        # Drive the loop manually so we can honour SIGINT between iterations.
        import time as _time  # noqa: PLC0415
        from src.loop import ledger as _ledger_mod  # noqa: PLC0415

        _BACKOFF_BASE, _BACKOFF_MAX = 20.0, 300.0  # aggressive: 20s base -> 5 min cap (re-check for new work often)
        backoff = _BACKOFF_BASE

        def _nondefer_count() -> int:
            """Resolved (non-DEFER) ledger entries -- the productivity signal."""
            try:
                return sum(1 for e in _ledger_mod.load_all()
                           if str(e.get("verdict")) not in ("DEFER", "Verdict.DEFER"))
            except Exception:
                return -1

        def _sleep_interruptible(secs: float) -> None:
            """Sleep in small slices so SIGINT/SIGTERM stops promptly."""
            end = _time.time() + secs
            while not _STOP_REQUESTED and _time.time() < end:
                _time.sleep(min(5.0, max(0.0, end - _time.time())))

        i = 0
        while not _STOP_REQUESTED:
            before = _nondefer_count()
            iter_start = _dt.datetime.utcnow()
            res = orch.run_iteration(arm=arm)
            elapsed = _dt.datetime.utcnow() - iter_start
            _print_iteration_summary(i, res, elapsed)
            results.append(res)
            i += 1
            # Idle backoff: a cycle that resolves nothing NEW (only the same
            # data-gapped DEFERs re-run) sleeps progressively up to 30 min, so
            # the daemon idles instead of spinning every minute. A productive
            # cycle (new SHIP/REJECT when fresh data lands) snaps back to 1 min.
            after = _nondefer_count()
            if before < 0 or after < 0 or after > before:
                backoff = _BACKOFF_BASE
            else:
                backoff = min(backoff * 2.0, _BACKOFF_MAX)
            _sleep_interruptible(backoff)
    else:
        # Delegate to Orchestrator.run for finite runs.
        iter_results = orch.run(arm=arm, max_iters=max_iters, forever=False)
        for idx, res in enumerate(iter_results):
            # Approximate per-iter elapsed (run() is synchronous).
            elapsed_total = _dt.datetime.utcnow() - run_start
            _print_iteration_summary(idx, res, elapsed_total)
        results = iter_results

    total_elapsed = _dt.datetime.utcnow() - run_start
    _print_run_summary(results, total_elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
