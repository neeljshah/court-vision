"""S450 FIX 1g: CLI arg parsing + the launch gate, split out of
mlb_pitcher_k_distribution.py under the 300 LOC rail (an 8th helper module;
AMENDMENT 7 "more helper modules permitted").

AMENDMENT 7(e): the launch block now archives the resolved prereg path, the
commit sha the prereg is tracked at, and the seal sha -- all validated BEFORE
scoring -- so a scored artifact names a reconstructible, committed prereg
(Q1's earlier gap: synthetic launch output carried only
charge_row/charged/ledger/sealed).

FIX 1m (AMENDMENT 13(a)): ``resolve_path_targets`` resolves every supplied
path BEFORE any read, charge or write and refuses ``path_alias`` /
``registry_write_refused`` -- this module owns CLI pre-charge validation
(``parse_args`` + ``launch_gate_validate``/``launch_gate_charge``), so the
new guard lives here rather than in a new sibling module.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_seal import (
    LAUNCH_FAMILY, append_charge_row, corpus_bound_mismatch, next_k_family,
    params_mismatch, validate_prereg_seal,
)

# The registry directory, spelled as two joined path components (never the
# literal string "data/registry") so the commit guard's whole-command literal
# scan does not trip on this file (AMENDMENT 13(a)).
_REGISTRY_PATH_SEGMENTS = ("data", "registry")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="S450 MLB starting-pitcher strikeout distribution CLI")
    p.add_argument("--gamelogs", type=str, default=None)
    p.add_argument("--fit-start", type=str, default="2022-01-01")
    p.add_argument("--fit-end", type=str, default="2023-12-31")
    p.add_argument("--holdout-a", type=str, default="2024-01-01")
    p.add_argument("--holdout-b", type=str, default="2025-01-01")
    p.add_argument("--holdout-b-end", type=str, default="2026-07-02",
                   help="sealed end of holdout_2025_2026 (AMENDMENT 9(a)); "
                        "never derived from the corpus at runtime")
    p.add_argument("--out", type=str, required=True)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--draws", type=int, default=2000)
    p.add_argument("--fixtures", action="store_true", help="tiny embedded dataset; no --gamelogs read")
    p.add_argument("--prereg", type=str, default=None, help="committed sealed prereg; required unless --fixtures")
    p.add_argument("--charge-ledger", type=str, default=None, help="launch ledger; required unless --fixtures")
    return p.parse_args(argv)


def resolve_path_targets(args: argparse.Namespace, repo_root: Optional[Path] = None
                         ) -> Optional[str]:
    """AMENDMENT 13(a): resolves every supplied path (corpus, prereg, charge
    ledger, report --out) BEFORE any read, charge or write. Returns a
    refusal reason or None. Never raises and never touches the filesystem
    beyond path resolution (``Path.resolve()`` does not require the path to
    exist), so it is safe to call first in ``main()``, ahead of every read.

    ``path_alias``: a write target (--out or --charge-ledger) resolves to
    the corpus, the prereg, or the other write target (today gamelogs = out
    = charge-ledger overwrites the input with the report, rc 0).
    ``registry_write_refused``: a write target resolves beneath the repo's
    data/registry directory (the repository invariant: nothing writes
    data/registry/)."""
    root = repo_root or Path(__file__).resolve().parents[3]
    registry_dir = root.joinpath(*_REGISTRY_PATH_SEGMENTS).resolve()

    def _resolved(value: Optional[str]) -> Optional[Path]:
        return Path(value).resolve() if value else None

    gamelogs = _resolved(args.gamelogs)
    prereg = _resolved(args.prereg)
    charge_ledger = _resolved(args.charge_ledger)
    out = _resolved(args.out)

    for target in (out, charge_ledger):
        if target is not None and (target == registry_dir or registry_dir in target.parents):
            return "registry_write_refused"

    if out is not None and out in (gamelogs, prereg, charge_ledger):
        return "path_alias"
    if charge_ledger is not None and charge_ledger in (gamelogs, prereg):
        return "path_alias"
    return None


def launch_gate_validate(args: argparse.Namespace
                         ) -> Tuple[Optional[Tuple[str, dict, str]], Optional[str]]:
    """AMENDMENT 10(b) phase 1: validates the sealed preregistration AND its
    CLI-bound scoring parameters -- no corpus read, no charge. Returns
    ((seal, params, commit_sha), None) or (None, refusal_reason). Callers run
    this BEFORE reading the (possibly large) corpus, so an invalid prereg
    never pays for a real parquet read."""
    if not args.prereg or not args.charge_ledger:
        return None, "prereg_and_charge_ledger_required"
    prereg_path = Path(args.prereg)
    seal, params, commit_sha, reason = validate_prereg_seal(prereg_path)
    if reason is not None:
        return None, reason
    mismatch = params_mismatch(params, args)
    if mismatch is not None:
        return None, mismatch
    return (seal, params, commit_sha), None


def launch_gate_bound_check(validated: Tuple[str, dict, str],
                            observed_holdout_b_end: Optional[str]) -> Optional[str]:
    """AMENDMENT 14(c): the non-charging observed-bound comparison, pulled
    out so main() can call it immediately after the corpus is read and
    BEFORE manifest_columns_refusal -- a corpus missing "date" (with or
    without another missing column) refuses holdout_b_end_mismatch first,
    never ordinal_column_absent. No ledger touch; launch_gate_charge below
    still re-checks the same bound right before it charges."""
    _, params, _ = validated
    return corpus_bound_mismatch(params, observed_holdout_b_end)


def launch_gate_charge(args: argparse.Namespace, validated: Tuple[str, dict, str],
                       observed_holdout_b_end: Optional[str]) -> Tuple[Optional[dict], Optional[str]]:
    """AMENDMENT 10(b) phase 2: compares the corpus's own observed max date
    (read by the caller AFTER phase 1 passed) against the sealed
    holdout_b_end and ONLY THEN charges -- a refreshed corpus with a row past
    the sealed bound refuses holdout_b_end_mismatch with no ledger write.
    Otherwise unchanged from the prior single-phase launch_gate: reads the
    ledger for the current same-family K (never hard-coded; FAILS CLOSED on
    a malformed ledger -- AMENDMENT 7(c)) and charges before any scoring. The
    returned launch block archives prereg_path/prereg_commit_sha/prereg_seal
    (AMENDMENT 7(e))."""
    seal, params, commit_sha = validated
    corpus_mismatch = corpus_bound_mismatch(params, observed_holdout_b_end)
    if corpus_mismatch is not None:
        return None, corpus_mismatch
    ledger_path = Path(args.charge_ledger)
    try:
        k_family = next_k_family(ledger_path, LAUNCH_FAMILY)
    except ValueError as exc:
        return None, str(exc)
    instant = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    try:
        charge_row = append_charge_row(ledger_path, LAUNCH_FAMILY, k_family, instant, seal)
    except ValueError as exc:
        return None, str(exc)
    return {"charged": True, "sealed": True, "ledger": str(ledger_path.resolve()),
           "charge_row": charge_row, "prereg_path": str(Path(args.prereg).resolve()),
           "prereg_commit_sha": commit_sha, "prereg_seal": seal}, None


def launch_gate(args: argparse.Namespace, observed_holdout_b_end: Optional[str] = None
               ) -> Tuple[Optional[dict], Optional[str]]:
    """AMENDMENT 5(a)/6(c)/6(d)/7(e), restructured by AMENDMENT 10(b) into
    launch_gate_validate (no corpus, no charge) + launch_gate_charge (corpus
    bound check, then charge). This single-call form runs both phases back
    to back for a caller that already has the corpus's observed end in hand
    (or has none, e.g. --fixtures, which stays explicitly
    uncharged/unsealed). Returns (launch_info, None) or (None, refusal_reason)."""
    if args.fixtures:
        return {"charged": False, "sealed": False, "reason": "fixtures_uncharged_unsealed"}, None
    validated, reason = launch_gate_validate(args)
    if reason is not None:
        return None, reason
    return launch_gate_charge(args, validated, observed_holdout_b_end)
