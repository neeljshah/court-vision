"""edge_engine -- one-shot fetch CLI for the live-text -> structured-facts seam.

Fetches every wired (source, sport) once and prints an ASCII count/freshness summary. Idempotent:
dedupe in the store means a re-run adds 0 rows. No LLM, no secret required (rule path is default).

  python -m scripts.platformkit.edge_engine.cli            # fetch all wired sources once
  python -m scripts.platformkit.edge_engine.cli --dry-run  # fetch + count, do NOT write the store

Stdlib only. <=300 LOC. Per-file test: test_cli.py.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

try:  # package import
    from scripts.platformkit.edge_engine import injury_facts, news_facts  # type: ignore
    from scripts.platformkit.edge_engine.facts_store import store_summary  # type: ignore
except ImportError:  # direct-script fallback
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.platformkit.edge_engine import injury_facts, news_facts  # type: ignore
    from scripts.platformkit.edge_engine.facts_store import store_summary  # type: ignore


def run_once(dry_run: bool = False) -> List[dict]:
    """Fetch every wired (kind, sport) once. Returns per-target result dicts (no printing)."""
    results: List[dict] = []
    targets: List[Tuple[str, str, object]] = []
    for sp in injury_facts.WIRED_SPORTS:
        targets.append(("injury", sp, injury_facts.store_injuries))
    for sp in news_facts.WIRED_SPORTS:
        targets.append(("news", sp, news_facts.store_news))

    for kind, sport, store_fn in targets:
        try:
            if dry_run:
                fetch_fn = (injury_facts.fetch_injuries if kind == "injury"
                            else news_facts.fetch_news)
                n_fetched, n_added = len(fetch_fn(sport)), 0
            else:
                n_fetched, n_added = store_fn(sport)  # type: ignore[operator]
            summ = store_summary(kind, sport)
            results.append({"kind": kind, "sport": sport, "fetched": n_fetched,
                            "added": n_added, "total": summ["rows"],
                            "latest": summ["latest"], "error": ""})
        except Exception as exc:  # keep going -- one dead feed must not block the rest
            results.append({"kind": kind, "sport": sport, "fetched": 0, "added": 0,
                            "total": 0, "latest": "-", "error": type(exc).__name__})
    return results


def format_summary(results: List[dict]) -> str:
    """ASCII table -- cp1252 safe (no unicode)."""
    head = "{:<8} {:<6} {:>8} {:>6} {:>7}  {:<25} {}".format(
        "KIND", "SPORT", "FETCHED", "ADDED", "TOTAL", "LATEST", "ERROR")
    lines = [head, "-" * len(head)]
    for r in results:
        lines.append("{:<8} {:<6} {:>8} {:>6} {:>7}  {:<25} {}".format(
            r["kind"], r["sport"], r["fetched"], r["added"], r["total"],
            r["latest"], r["error"]))
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="fetch edge_engine injury/news facts once")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + count only; do not write the JSONL store")
    args = ap.parse_args(argv)
    results = run_once(dry_run=args.dry_run)
    print(format_summary(results))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
