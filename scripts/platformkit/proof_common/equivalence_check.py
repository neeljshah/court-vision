"""SWAP-GATE (K-PR-005): OLD proof_runner vs NEW generic harness exact result-dict equality.

Dual validity:
  PRE-swap  — old-vs-new equivalence: authorises K-PR-006 shim conversion.
  POST-swap — shim-delegation identity: permanent drift guard.

CLI: python equivalence_check.py --sport {tennis,soccer,mlb} [--league-filter {NL,AL}]
Exit 0 all-PASS, 1 any FAIL, 2 corpus absent.  Sport tokens confined to DISPATCH only.
"""
from __future__ import annotations

import argparse
import math
import sys
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Deep exact-diff comparator
# ---------------------------------------------------------------------------

def _deep_diff(old: Any, new: Any, path: str = "") -> List[str]:
    """Recursive exact comparator; returns list of divergence messages (empty = identical).

    float: equal iff ``a == b`` OR both NaN — NO tolerance, exact IEEE equality.
    """
    diffs: List[str] = []
    if type(old) is not type(new):
        return [f"{path}: type old={type(old).__name__} new={type(new).__name__}"]
    if isinstance(old, dict):
        for k in sorted(set(old) - set(new)):
            diffs.append(f"{path}.{k}: key only-in-old")
        for k in sorted(set(new) - set(old)):
            diffs.append(f"{path}.{k}: key only-in-new")
        for k in sorted(set(old) & set(new)):
            diffs.extend(_deep_diff(old[k], new[k], f"{path}.{k}"))
    elif isinstance(old, (list, tuple)):
        if len(old) != len(new):
            diffs.append(f"{path}: length old={len(old)} new={len(new)}")
        for i, (o, n) in enumerate(zip(old, new)):
            diffs.extend(_deep_diff(o, n, f"{path}[{i}]"))
    elif isinstance(old, float):
        if not (math.isnan(old) and math.isnan(new)) and old != new:
            diffs.append(f"{path}: old={old!r} new={new!r}")
    else:
        if old != new:
            diffs.append(f"{path}: old={old!r} new={new!r}")
    return diffs


# ---------------------------------------------------------------------------
# Corpus builders — exact copies of each run_proof._load_adapter
# ---------------------------------------------------------------------------

def _build_tennis_adapter(corpus_dir: Path) -> Any:
    """Verbatim from proof_tennis/run_proof._load_adapter."""
    from domains.tennis.adapter import TennisAdapter
    mp = corpus_dir / "matches.parquet"
    if not mp.exists():
        raise FileNotFoundError(mp)
    matches_df = pd.read_parquet(mp)
    odds_df: Optional[pd.DataFrame] = None
    op = corpus_dir / "odds.parquet"
    if op.exists():
        try:
            odds_df = pd.read_parquet(op)
        except Exception:
            pass
    return TennisAdapter(matches_df=matches_df, odds_df=odds_df)


def _build_soccer_adapter(corpus_dir: Path) -> Any:
    """Verbatim from proof_soccer/run_proof._load_adapter."""
    from domains.soccer.adapter import SoccerAdapter
    mp = corpus_dir / "matches.parquet"
    if not mp.exists():
        raise FileNotFoundError(mp)
    matches_df = pd.read_parquet(mp)
    odds_df: Optional[pd.DataFrame] = None
    op = corpus_dir / "odds.parquet"
    if op.exists():
        try:
            odds_df = pd.read_parquet(op)
        except Exception:
            pass
    return SoccerAdapter(matches_df=matches_df, odds_df=odds_df)


def _build_mlb_adapter(corpus_dir: Path) -> Any:
    """Verbatim from proof_mlb/run_proof._load_adapter."""
    from domains.mlb.adapter import MLBAdapter
    gp = corpus_dir / "games.parquet"
    if not gp.exists():
        raise FileNotFoundError(gp)
    games_df = pd.read_parquet(gp)
    odds_df: Optional[pd.DataFrame] = None
    op = corpus_dir / "odds.parquet"
    if op.exists():
        try:
            odds_df = pd.read_parquet(op)
        except Exception:
            pass
    return MLBAdapter(games_df=games_df, odds_df=odds_df)


# ---------------------------------------------------------------------------
# DISPATCH TABLE — the ONLY place sport tokens are permitted (test instrument).
# ---------------------------------------------------------------------------

_DISPATCH: Dict[str, Dict[str, Any]] = {
    "tennis": {
        "corpus_subdir": "tennis",
        "builder": _build_tennis_adapter,
        "old_module": "scripts.platformkit.proof_tennis.proof_runner",
        "spec_module": "scripts.platformkit.proof_tennis.spec",
    },
    "soccer": {
        "corpus_subdir": "soccer",
        "builder": _build_soccer_adapter,
        "old_module": "scripts.platformkit.proof_soccer.proof_runner",
        "spec_module": "scripts.platformkit.proof_soccer.spec",
    },
    "mlb": {
        "corpus_subdir": "mlb",
        "builder": _build_mlb_adapter,
        "old_module": "scripts.platformkit.proof_mlb.proof_runner",
        "spec_module": "scripts.platformkit.proof_mlb.spec",
    },
}


# ---------------------------------------------------------------------------
# Equivalence runner
# ---------------------------------------------------------------------------

def run_equivalence(sport: str, league_filter: Optional[str] = None) -> bool:
    """Run OLD vs NEW for *sport*, print PASS/FAIL per version; return True if all pass."""
    import importlib

    entry = _DISPATCH[sport]
    corpus_dir = _REPO / "data" / "domains" / entry["corpus_subdir"]
    print(f"[equivalence_check] sport={sport}  league_filter={league_filter!r}")
    print(f"[equivalence_check] corpus={corpus_dir}")

    # Two FRESH adapter instances guard against any in-adapter caching divergence
    adapter_old = entry["builder"](corpus_dir)
    adapter_new = entry["builder"](corpus_dir)

    old = importlib.import_module(entry["old_module"])
    spec_mod = importlib.import_module(entry["spec_module"])
    from scripts.platformkit.proof_common import runner, paper

    SPEC = spec_mod.SPEC
    is_mlb = sport == "mlb"
    lf_kw: Dict[str, Any] = {"league_filter": league_filter} if is_mlb else {}

    pairs: List[Tuple[str, Dict, Dict]] = []

    print("[equivalence_check] V1: Calibration...")
    pairs.append(("V1",
                  old.run_v1(adapter_old, **lf_kw),
                  runner.run_v1(SPEC, adapter_new, ctx=league_filter)))

    print("[equivalence_check] V2: CLV mechanics...")
    pairs.append(("V2",
                  old.run_v2(adapter_old, **lf_kw),
                  runner.run_v2(SPEC, adapter_new, ctx=league_filter)))

    print("[equivalence_check] V3: Honest gate...")
    pairs.append(("V3",
                  old.run_v3(adapter_old, **lf_kw),
                  runner.run_v3(SPEC, adapter_new, ctx=league_filter)))

    print("[equivalence_check] V4: Paper portfolio...")
    v4_old_kw: Dict[str, Any] = {"paper_book_dir": None, **lf_kw}
    pairs.append(("V4",
                  old.run_v4(adapter_old, **v4_old_kw),
                  paper.run_v4(SPEC, adapter_new, paper_book_dir=None, ctx=league_filter)))

    all_pass = True
    for label, res_old, res_new in pairs:
        diffs = _deep_diff(res_old, res_new, label)
        if diffs:
            all_pass = False
            print(f"  {label}: FAIL")
            for d in diffs[:10]:
                print(f"    DIFF: {d}")
            if len(diffs) > 10:
                print(f"    ... ({len(diffs) - 10} more)")
        else:
            print(f"  {label}: PASS")

    print(f"\nEQUIVALENCE: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    """Parse args and run the gate."""
    parser = argparse.ArgumentParser(
        description=(
            "SWAP-GATE (K-PR-005): run OLD proof_runner and NEW generic harness "
            "side-by-side and assert exact result-dict equality.  "
            "PRE-swap: authorises shim conversion.  POST-swap: permanent drift guard."
        )
    )
    parser.add_argument("--sport", choices=list(_DISPATCH), required=True,
                        help="Sport to check.")
    parser.add_argument("--league-filter", choices=["NL", "AL"], default=None,
                        help="MLB only: run a single corpus (NL or AL).")
    args = parser.parse_args(argv)

    if args.league_filter and args.sport != "mlb":
        parser.error("--league-filter is only valid for --sport mlb")

    try:
        ok = run_equivalence(args.sport, league_filter=args.league_filter)
    except FileNotFoundError as exc:
        print(f"[equivalence_check] corpus absent: {exc}", file=sys.stderr)
        return 2

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
