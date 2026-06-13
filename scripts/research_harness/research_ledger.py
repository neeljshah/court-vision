"""research_ledger.py — Append-only quant research lab notebook.

Records REJECT/DEFER/SHIP verdicts for signal families so null results
compound and are never blindly re-tested.  Markets are efficient; honest
REJECTs are first-class findings, not failures.

Usage (CLI):
    python scripts/research_harness/research_ledger.py --help
    python scripts/research_harness/research_ledger.py --dry-run
    python scripts/research_harness/research_ledger.py --ingest-catalogs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "data" / "research" / "findings.jsonl"
VAULT_SPORTS = ROOT / "vault" / "Sports"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

VALID_VERDICTS = {"REJECT", "DEFER", "SHIP", "VARIANCE_ONLY"}


@dataclass
class ResearchFinding:
    """One immutable research finding.

    Fields
    ------
    sport          : sport identifier, e.g. "tennis", "soccer", "mlb", "nba"
    family         : signal family name, e.g. "tennis_abs_rest_diff"
    hypothesis     : plain-English statement of what was tested
    verdict        : "REJECT" | "DEFER" | "SHIP"
    evidence       : dict with keys like n, splits, metric, p_value, clv
    what_would_change_my_mind : conditions under which this verdict should be
                                revisited (required — keeps null results useful)
    dated          : ISO-8601 date string "YYYY-MM-DD" when the verdict was set
    """

    sport: str
    family: str
    hypothesis: str
    verdict: str
    evidence: Dict
    what_would_change_my_mind: str
    dated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(
                f"verdict must be one of {VALID_VERDICTS}, got {self.verdict!r}"
            )
        if not self.what_would_change_my_mind.strip():
            raise ValueError("what_would_change_my_mind must not be empty")

    @property
    def key(self) -> tuple:
        """Dedup key: (sport, family, hypothesis)."""
        return (self.sport, self.family, self.hypothesis)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "ResearchFinding":
        return cls(
            sport=d["sport"],
            family=d["family"],
            hypothesis=d["hypothesis"],
            verdict=d["verdict"],
            evidence=d.get("evidence", {}),
            what_would_change_my_mind=d["what_would_change_my_mind"],
            dated=d.get("dated", ""),
        )


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

class Ledger:
    """Append-only JSONL research ledger.

    Parameters
    ----------
    path : Path or str, optional
        Path to the JSONL file.  Defaults to data/research/findings.jsonl.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else DEFAULT_LEDGER
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: Dict[tuple, ResearchFinding] = {}
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load existing findings from disk (idempotent)."""
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    f = ResearchFinding.from_dict(json.loads(line))
                    self._seen[f.key] = f
                except (KeyError, ValueError):
                    pass  # skip malformed rows; never raise on load

    def _flush(self, finding: ResearchFinding) -> None:
        """Append a single finding to disk (raw append, no rewrite)."""
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(finding.to_dict()) + "\n")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, finding: ResearchFinding) -> bool:
        """Append a finding; silently skips exact-key duplicates.

        Returns True if the finding was written, False if deduped.
        """
        if finding.key in self._seen:
            return False
        self._seen[finding.key] = finding
        self._flush(finding)
        return True

    def all_findings(self) -> List[ResearchFinding]:
        return list(self._seen.values())

    def summarize(self) -> Dict:
        """Return counts by verdict and by sport."""
        by_verdict: Dict[str, int] = {v: 0 for v in VALID_VERDICTS}
        by_sport: Dict[str, Dict[str, int]] = {}
        for f in self._seen.values():
            by_verdict[f.verdict] = by_verdict.get(f.verdict, 0) + 1
            sport_row = by_sport.setdefault(f.sport, {v: 0 for v in VALID_VERDICTS})
            sport_row[f.verdict] = sport_row.get(f.verdict, 0) + 1
        return {
            "total": len(self._seen),
            "by_verdict": by_verdict,
            "by_sport": by_sport,
        }

    @property
    def path(self) -> Path:
        return self._path


# ---------------------------------------------------------------------------
# Catalog parser (vault/Sports/<Sport>/Signals/_Catalog*.md)
# ---------------------------------------------------------------------------

# Matches verdict table rows: | signal_name | ... | REJECT/DEFER/SHIP | ... |
_VERDICT_ROW = re.compile(
    r"^\|\s*(?P<family>[a-z][a-zA-Z0-9_]+)\s*"
    r"\|\s*(?P<expected>\w+)\s*"
    r"\|\s*(?P<actual>REJECT|DEFER|SHIP)\s*"
    r"\|[^|]*\|\s*(?P<n>\d+)\s*"
    r"\|[^|]*\|\s*(?P<reason>[^|]+)\|",
)

_WHAT_DEFAULT = (
    "A second independent corpus (different seasons / books / exchanges) showing "
    "consistent positive CLV above vig, with FDR-corrected p < 0.05."
)


def ingest_catalog(catalog_path: Path, sport: str, ledger: Ledger, dry_run: bool = False) -> int:
    """Parse one _Catalog*.md and append findings to ledger.

    Returns the number of rows appended.
    """
    written = 0
    with catalog_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            m = _VERDICT_ROW.match(line)
            if not m:
                continue
            family = m.group("family")
            verdict = m.group("actual")
            n = int(m.group("n"))
            reason = m.group("reason").strip()
            finding = ResearchFinding(
                sport=sport,
                family=family,
                hypothesis=f"{family}: pure transform of leak-free base; tested on {n} rows",
                verdict=verdict,
                evidence={"n": n, "reason": reason},
                what_would_change_my_mind=_WHAT_DEFAULT,
            )
            if dry_run:
                print(f"[DRY-RUN] would append: {finding.key}")
                written += 1
            else:
                if ledger.append(finding):
                    written += 1
    return written


def ingest_all_catalogs(ledger: Ledger, dry_run: bool = False) -> int:
    """Walk vault/Sports/<Sport>/Signals/_Catalog*.md; graceful if absent."""
    if not VAULT_SPORTS.exists():
        print("vault/Sports not found — skipping catalog ingest (this is normal).")
        return 0
    total = 0
    for sport_dir in sorted(VAULT_SPORTS.iterdir()):
        if not sport_dir.is_dir():
            continue
        sig_dir = sport_dir / "Signals"
        if not sig_dir.exists():
            continue
        sport_id = sport_dir.name.lower().replace(" ", "_")
        for catalog in sorted(sig_dir.glob("_Catalog*.md")):
            n = ingest_catalog(catalog, sport_id, ledger, dry_run=dry_run)
            print(f"  {catalog.relative_to(ROOT)}: {n} rows {'(dry-run)' if dry_run else 'appended'}")
            total += n
    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research_ledger",
        description=(
            "Append-only research lab notebook.  "
            "Null results (REJECT/DEFER) are first-class citizens.  "
            "No edge is claimed."
        ),
    )
    p.add_argument(
        "--ledger",
        metavar="PATH",
        default=str(DEFAULT_LEDGER),
        help="Path to the JSONL findings file (default: %(default)s)",
    )
    p.add_argument(
        "--ingest-catalogs",
        action="store_true",
        help="Parse vault/Sports catalog markdown files and append findings",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be appended without writing",
    )
    p.add_argument(
        "--summarize",
        action="store_true",
        help="Print summary counts from existing ledger and exit",
    )
    return p


def main(argv: Optional[List[str]] = None) -> None:
    args = _build_parser().parse_args(argv)
    ledger = Ledger(path=args.ledger)

    if args.summarize:
        s = ledger.summarize()
        print(json.dumps(s, indent=2))
        return

    if args.ingest_catalogs or args.dry_run:
        total = ingest_all_catalogs(ledger, dry_run=args.dry_run)
        print(f"\nTotal rows {'(dry-run) ' if args.dry_run else ''}processed: {total}")
    else:
        # Default: just show summary of existing ledger
        s = ledger.summarize()
        print("Ledger summary (no --ingest-catalogs flag; reading existing records only):")
        print(json.dumps(s, indent=2))
        print(f"\nLedger path: {ledger.path}")


if __name__ == "__main__":
    main(sys.argv[1:])
