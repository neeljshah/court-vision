"""scripts.research_harness.research_loop — End-to-end offline research pipeline.

Wires hypothesis_enumerator -> research_ledger -> belief_store -> research_writeup.
Consumes EXISTING catalog verdicts (never runs the live gate).

Flow: enumerate -> ingest catalogs -> update ledger -> update BeliefStore
      (persist beliefs.json) -> render markdown writeup -> emit summary.

No edge is claimed.  REJECT verdicts are first-class findings.
P(ship) posteriors are historical ship-rate priors, NOT edge claims.

Usage:
    python -m scripts.research_harness.research_loop [--vault PATH] [--dry-run]
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

from research_ledger import Ledger, ResearchFinding, VAULT_SPORTS  # noqa: E402
from research_writeup import render_writeup  # noqa: E402
from hypothesis_enumerator import compute_all_coverage, format_summary  # noqa: E402
from research_digest import format_digest  # noqa: E402

# BeliefStore imported gracefully — loop works without it.
_BELIEF_STORE_AVAILABLE: bool = False
try:
    from belief_store import BeliefStore  # noqa: E402
    _BELIEF_STORE_AVAILABLE = True
except Exception:  # pragma: no cover
    BeliefStore = None  # type: ignore[assignment,misc]

# gap_observer imported gracefully — loop works without it.
_GAP_OBSERVER_AVAILABLE: bool = False
try:
    from gap_observer import rank_gaps  # noqa: E402
    _GAP_OBSERVER_AVAILABLE = True
except Exception:  # pragma: no cover
    rank_gaps = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_LEDGER = _ROOT / "data" / "research" / "findings.jsonl"
_DEFAULT_OUT_MD = _ROOT / "vault" / "Sports" / "_Research_Findings.md"
_DEFAULT_BELIEFS = _ROOT / "data" / "research" / "beliefs.json"

# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------


def run_research_loop(
    ledger_path: Optional[Path] = None,
    vault_root: Optional[Path] = None,
    out_md: Optional[Path] = None,
    beliefs_path: Optional[Path] = None,
    dry_run: bool = False,
    verbose: bool = True,
    top_gaps_n: int = 5,
) -> Dict:
    """Run the end-to-end offline research pipeline.

    Returns a dict with keys: n_ingested, n_total, out_md, coverage_summary,
    verdict_summary, skipped_no_data, beliefs_path, belief_summary, top_gaps.
    belief_summary is {sport -> {family -> posterior_mean}} or {}.
    top_gaps is a list of RankedGap (search-completeness ranking, not edge claims).
    """
    resolved_ledger = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    resolved_out_md = Path(out_md) if out_md else _DEFAULT_OUT_MD
    resolved_vault = Path(vault_root) if vault_root else VAULT_SPORTS
    resolved_beliefs = Path(beliefs_path) if beliefs_path else _DEFAULT_BELIEFS

    def _log(msg: str) -> None:
        if verbose:
            print(msg)

    # 1 — Enumerate candidate hypothesis space
    _log("[research_loop] Step 1: enumerating hypothesis candidates …")
    coverage_summary = format_summary(compute_all_coverage())

    # 2 — Open / create ledger
    _log(f"[research_loop] Step 2: opening ledger at {resolved_ledger}")
    ledger = Ledger(path=resolved_ledger)
    n_before = ledger.summarize()["total"]

    # 3 — Ingest existing catalog verdict reports (offline, no gate)
    _log(f"[research_loop] Step 3: ingesting catalog reports from {resolved_vault} …")
    skipped_no_data = False
    if not resolved_vault.exists():
        _log("  vault/Sports not found — no verdicts to ingest (graceful no-op).")
        skipped_no_data = True
    else:
        n_ingested = _ingest_from_vault(resolved_vault, ledger, dry_run, _log)
        if n_ingested == 0 and ledger.summarize()["total"] == n_before:
            _log("  No new findings — ledger already up to date.")
            skipped_no_data = True

    # 4 — Build / update BeliefStore from ledger; persist to JSON
    belief_store = None
    belief_summary: Dict = {}
    written_beliefs_path: Optional[Path] = None

    if _BELIEF_STORE_AVAILABLE and BeliefStore is not None:
        _log("[research_loop] Step 4: updating belief store …")
        try:
            belief_store = BeliefStore()
            belief_store.update_from_ledger(ledger)
            for bel in belief_store.all_beliefs():
                belief_summary.setdefault(bel.sport, {})[bel.family] = round(
                    bel.posterior_mean, 4
                )
            if not dry_run:
                written_beliefs_path = belief_store.save(resolved_beliefs)
                _log(f"  Beliefs written: {written_beliefs_path}")
            else:
                _log(
                    f"  [dry-run] would write {resolved_beliefs} "
                    f"({len(belief_store.all_beliefs())} family beliefs)"
                )
        except Exception as exc:  # pragma: no cover
            _log(f"  [belief_store] WARNING: update failed ({exc}); skipping.")
            belief_store = None
    else:
        _log("[research_loop] Step 4: belief_store unavailable — skipping.")

    # 5 — Compute top research gaps (search-completeness, not edge claims)
    top_gaps: List = []
    if _GAP_OBSERVER_AVAILABLE and rank_gaps is not None:
        _log("[research_loop] Step 5: computing research gaps via gap_observer …")
        try:
            enumerator_results = compute_all_coverage()
            top_gaps = rank_gaps(
                enumerator_results=enumerator_results,
                findings=ledger.all_findings(),
                belief_store=belief_store,
                top_n=top_gaps_n,
            )
            _log(f"  top_gaps computed: {len(top_gaps)} gaps ranked.")
        except Exception as exc:  # pragma: no cover
            _log(f"  [gap_observer] WARNING: rank_gaps failed ({exc}); skipping.")
    else:
        _log("[research_loop] Step 5: gap_observer unavailable — skipping.")

    # 6 — Render consolidated markdown note
    _log("[research_loop] Step 6: rendering research note …")
    md_content = render_writeup(ledger, generated_by="research_loop.py",
                                belief_store=belief_store,
                                gaps=top_gaps if top_gaps else None)
    if not dry_run:
        resolved_out_md.parent.mkdir(parents=True, exist_ok=True)
        resolved_out_md.write_text(md_content, encoding="utf-8")
        _log(f"  Written: {resolved_out_md}")
    else:
        _log(f"  [dry-run] would write {resolved_out_md} ({len(md_content)} chars)")

    # 7 — Emit summary
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
        "beliefs_path": written_beliefs_path,
        "belief_summary": belief_summary,
        "top_gaps": top_gaps,
    }


def _ingest_from_vault(vault_sports: Path, ledger: Ledger, dry_run: bool, log_fn) -> int:
    """Walk vault_sports/<Sport>/Signals/_Catalog*.md and ingest each file."""
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
            log_fn(f"  {catalog}: {n} rows {'(dry-run)' if dry_run else 'appended'}")
            total += n
    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research_loop",
        description=(
            "Offline research pipeline: enumerate -> ingest catalog verdicts -> "
            "update ledger + beliefs -> render note. No edge is claimed."
        ),
    )
    p.add_argument("--ledger", metavar="PATH", default=None,
                   help="Path to findings.jsonl")
    p.add_argument("--vault", metavar="PATH", default=None,
                   help="vault/Sports root directory")
    p.add_argument("--out", metavar="PATH", default=None,
                   help="Output markdown path")
    p.add_argument("--beliefs", metavar="PATH", default=None,
                   help="Output beliefs.json path")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be written without touching files")
    p.add_argument("--quiet", action="store_true", help="Suppress progress output")
    p.add_argument("--digest", action="store_true",
                   help="Print a concise honest health summary after the run")
    return p


def main(argv: Optional[List[str]] = None) -> None:
    """CLI entry point."""
    args = _build_parser().parse_args(argv)
    result = run_research_loop(
        ledger_path=Path(args.ledger) if args.ledger else None,
        vault_root=Path(args.vault) if args.vault else None,
        out_md=Path(args.out) if args.out else None,
        beliefs_path=Path(args.beliefs) if args.beliefs else None,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )
    if args.digest:
        print(format_digest(result))


if __name__ == "__main__":
    main(sys.argv[1:])
