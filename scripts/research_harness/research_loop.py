"""scripts.research_harness.research_loop — End-to-end offline research pipeline.

Wires hypothesis_enumerator -> research_ledger -> research_writeup into a
single DETERMINISTIC, OFFLINE run that consumes EXISTING catalog verdicts
(never runs the live gate).

Flow
----
1. enumerate_candidates (hypothesis_enumerator) — build the bounded candidate
   space for every sport.
2. ingest_all_catalogs (research_ledger) — parse existing _Catalog*.md verdict
   reports from vault/Sports/<Sport>/Signals/; graceful no-op when absent.
3. Ledger.append (dedup/idempotent) — each finding is recorded once.
4. render_writeup (research_writeup) — emit a consolidated markdown note.
5. Emit a short coverage + verdict summary to stdout.

No edge is claimed.  REJECT verdicts are first-class findings.

Usage (CLI):
    python -m scripts.research_harness.research_loop
    python -m scripts.research_harness.research_loop --vault /path/to/vault
    python -m scripts.research_harness.research_loop --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup — allow running as a module or as a plain script
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
_HARNESS = Path(__file__).resolve().parent
if str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))

from research_ledger import (  # noqa: E402
    Ledger,
    ResearchFinding,
    VAULT_SPORTS,
    ingest_all_catalogs,
)
from research_writeup import render_writeup  # noqa: E402

# Hypothesis enumerator lives one directory up in scripts/research_harness
from hypothesis_enumerator import compute_all_coverage, format_summary  # noqa: E402

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_LEDGER = _ROOT / "data" / "research" / "findings.jsonl"
_DEFAULT_OUT_MD = _ROOT / "vault" / "Sports" / "_Research_Findings.md"

_WHAT_DEFAULT = (
    "A second independent corpus (different seasons / books / exchanges) showing "
    "consistent positive CLV above vig, with FDR-corrected p < 0.05."
)

# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------


def run_research_loop(
    ledger_path: Optional[Path] = None,
    vault_root: Optional[Path] = None,
    out_md: Optional[Path] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> Dict:
    """Run the end-to-end offline research pipeline.

    Parameters
    ----------
    ledger_path : Path, optional
        Path to the findings JSONL ledger.  Defaults to
        data/research/findings.jsonl relative to repo root.
    vault_root : Path, optional
        Root of the Sports vault directory (vault/Sports).  Defaults to the
        value set in research_ledger.VAULT_SPORTS.
    out_md : Path, optional
        Destination for the consolidated markdown research note.
        Defaults to vault/Sports/_Research_Findings.md.
    dry_run : bool
        When True, nothing is written to disk (ledger or markdown file).
    verbose : bool
        Print progress lines to stdout.

    Returns
    -------
    dict with keys:
        "n_ingested"    : int  — new findings appended this run
        "n_total"       : int  — total findings in ledger after run
        "out_md"        : Path — path of written markdown note (or None)
        "coverage_summary" : str — plain-text coverage table
        "verdict_summary"  : dict — {REJECT/DEFER/SHIP counts}
        "skipped_no_data"  : bool — True when no catalog reports were found
    """
    # Resolve paths
    resolved_ledger = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    resolved_out_md = Path(out_md) if out_md else _DEFAULT_OUT_MD
    resolved_vault_sports = Path(vault_root) if vault_root else VAULT_SPORTS

    def _log(msg: str) -> None:
        if verbose:
            print(msg)

    # ------------------------------------------------------------------
    # Step 1 — Enumerate candidate hypothesis space (fast, offline)
    # ------------------------------------------------------------------
    _log("[research_loop] Step 1: enumerating hypothesis candidates …")
    coverage_results = compute_all_coverage()
    coverage_summary = format_summary(coverage_results)

    # ------------------------------------------------------------------
    # Step 2 — Open / create ledger
    # ------------------------------------------------------------------
    _log(f"[research_loop] Step 2: opening ledger at {resolved_ledger}")
    ledger = Ledger(path=resolved_ledger)
    n_before = ledger.summarize()["total"]

    # ------------------------------------------------------------------
    # Step 3 — Ingest existing catalog verdict reports (offline, no gate)
    # ------------------------------------------------------------------
    _log(
        f"[research_loop] Step 3: ingesting catalog reports from "
        f"{resolved_vault_sports} …"
    )
    skipped_no_data = False
    n_ingested = 0
    if not resolved_vault_sports.exists():
        _log(
            "  vault/Sports directory not found — no source verdicts to ingest "
            "(graceful no-op; this is expected on a clean clone)."
        )
        skipped_no_data = True
    else:
        # Use ingest_all_catalogs but with our potentially-overridden vault path.
        # ingest_all_catalogs uses the module-level VAULT_SPORTS; we replicate
        # its logic so we can honor a custom vault_root.
        n_ingested = _ingest_from_vault(resolved_vault_sports, ledger, dry_run, _log)
        if n_ingested == 0 and ledger.summarize()["total"] == n_before:
            _log("  No new findings found — ledger already up to date.")
            skipped_no_data = True

    # ------------------------------------------------------------------
    # Step 4 — Render consolidated markdown note
    # ------------------------------------------------------------------
    _log("[research_loop] Step 4: rendering research note …")
    md_content = render_writeup(
        ledger,
        generated_by="research_loop.py",
    )
    if not dry_run:
        resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
        resolved_out_md.write_text(md_content, encoding="utf-8")
        _log(f"  Written: {resolved_out_md}")
    else:
        _log(f"  [dry-run] would write {resolved_out_md} ({len(md_content)} chars)")

    # ------------------------------------------------------------------
    # Step 5 — Emit summary
    # ------------------------------------------------------------------
    n_after = ledger.summarize()["total"]
    verdict_counts = ledger.summarize()["by_verdict"]

    _log("\n" + coverage_summary)
    _log(
        f"\n[research_loop] Done. "
        f"Findings: {n_before} -> {n_after} (appended {n_after - n_before} new). "
        f"Verdicts: {verdict_counts}"
    )

    return {
        "n_ingested": n_after - n_before,
        "n_total": n_after,
        "out_md": None if dry_run else resolved_out_md,
        "coverage_summary": coverage_summary,
        "verdict_summary": verdict_counts,
        "skipped_no_data": skipped_no_data,
    }


def _ingest_from_vault(
    vault_sports: Path,
    ledger: Ledger,
    dry_run: bool,
    log_fn,
) -> int:
    """Walk vault_sports/<Sport>/Signals/_Catalog*.md and ingest each file.

    This mirrors research_ledger.ingest_all_catalogs but respects a caller-
    supplied vault path rather than the module-level constant.
    """
    from research_ledger import ingest_catalog  # local import to avoid circular

    total = 0
    for sport_dir in sorted(vault_sports.iterdir()):
        if not sport_dir.is_dir():
            continue
        sig_dir = sport_dir / "Signals"
        if not sig_dir.exists():
            continue
        sport_id = sport_dir.name.lower().replace(" ", "_")
        for catalog in sorted(sig_dir.glob("_Catalog*.md")):
            n = ingest_catalog(catalog, sport_id, ledger, dry_run=dry_run)
            log_fn(
                f"  {catalog}: {n} rows "
                f"{'(dry-run)' if dry_run else 'appended'}"
            )
            total += n
    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research_loop",
        description=(
            "Offline research pipeline: enumerate hypotheses -> ingest existing "
            "catalog verdicts -> update ledger -> render research note. "
            "No edge is claimed; REJECT verdicts are first-class findings."
        ),
    )
    p.add_argument(
        "--ledger",
        metavar="PATH",
        default=None,
        help="Path to findings.jsonl (default: data/research/findings.jsonl)",
    )
    p.add_argument(
        "--vault",
        metavar="PATH",
        default=None,
        help="vault/Sports root directory (default: vault/Sports inside repo)",
    )
    p.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="Output markdown path (default: vault/Sports/_Research_Findings.md)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching any files",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    return p


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point."""
    args = _build_parser().parse_args(argv)
    run_research_loop(
        ledger_path=Path(args.ledger) if args.ledger else None,
        vault_root=Path(args.vault) if args.vault else None,
        out_md=Path(args.out) if args.out else None,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
